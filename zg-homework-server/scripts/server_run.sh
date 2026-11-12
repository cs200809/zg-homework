#!/bin/sh
'''exec' python3 "$0" "$@"
' '''
"""Control one explicitly configured systemd unit, never processes by port/name."""
import json
import os
import re
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
UNIT = os.environ.get('SERVER_UNIT', 'zg-homework-server.service')
PORT = os.environ.get('SERVER_PORT', '8000')
PYTHON = os.environ.get('SERVER_PYTHON', str(ROOT / '.venv/bin/python'))
TIMEOUT = 30
CONFIG = Path('/etc/zg-homework-server/env')
APP_KEYS = frozenset(('APP_NAME', 'ENV', 'DEBUG', 'DATABASE_URL', 'DB_ECHO', 'JWT_SECRET',
                      'JWT_ALGORITHM', 'JWT_EXPIRE_DAYS', 'ADMIN_INIT_PASSWORD', 'CORS_ORIGINS',
                      'UPLOAD_DIR', 'PRIVATE_HOMEWORK_DIR', 'MAX_UPLOAD_MB', 'ALLOWED_EXTENSIONS',
                      'ARTICLE_ALLOWED_EXTENSIONS', 'ARTICLE_MAX_UPLOAD_MB', 'REGISTER_RATE_LIMIT',
                      'ACTION_RATE_LIMIT'))


def fail(message):
    raise RuntimeError(message)


def run(*args):
    try:
        return subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=15)
    except (OSError, subprocess.TimeoutExpired) as exc:
        fail(f'无法执行 {args[0]}：{exc}')


def properties():
    names = ['LoadState', 'ActiveState', 'SubState', 'WorkingDirectory', 'ExecStart',
             'ExecStartPre', 'ExecStartPost', 'ExecCondition', 'ExecStop', 'ExecStopPost',
             'Environment', 'EnvironmentFiles', 'RootDirectory', 'RootImage', 'Type',
             'MainPID', 'ControlGroup', 'KillMode', 'FragmentPath', 'NeedDaemonReload',
             'PassEnvironment', 'UnsetEnvironment', 'User', 'Group', 'PAMName']
    result = run('systemctl', 'show', UNIT, '--all', '--no-pager', *(f'--property={n}' for n in names))
    values = dict(line.split('=', 1) for line in result.stdout.splitlines() if '=' in line)
    if values.get('LoadState') == 'not-found':
        fail(f'未找到单元 {UNIT}；请安装该单元并运行 systemctl daemon-reload')
    if result.returncode:
        fail('systemctl show 失败；请检查 systemd 是否可用以及相关权限')
    # systemctl may omit empty array properties even with --all. Query each
    # missing array directly; never infer that an unavailable property is empty.
    array_types = {
        'ExecStartPre': 'a(sasbttttuii)', 'ExecStartPost': 'a(sasbttttuii)',
        'ExecCondition': 'a(sasbttttuii)', 'ExecStop': 'a(sasbttttuii)',
        'ExecStopPost': 'a(sasbttttuii)', 'EnvironmentFiles': 'a(sb)',
    }
    path = '/org/freedesktop/systemd1/unit/' + ''.join(
        chr(b) if (65 <= b <= 90 or 97 <= b <= 122 or (i > 0 and 48 <= b <= 57)) else f'_{b:02x}'
        for i, b in enumerate(UNIT.encode('utf-8'))
    )
    env_files = run('busctl', 'get-property', 'org.freedesktop.systemd1', path,
                    'org.freedesktop.systemd1.Service', 'EnvironmentFiles')
    if env_files.returncode or env_files.stdout.strip() != f'a(sb) 1 "{CONFIG}" false':
        fail('单元必须且只能使用必需的 /etc/zg-homework-server/env 环境文件')
    values['EnvironmentFiles'] = str(CONFIG)
    for name in names:
        if name not in values and name in array_types:
            prop = run('busctl', 'get-property', 'org.freedesktop.systemd1', path,
                       'org.freedesktop.systemd1.Service', name)
            if prop.returncode or prop.stdout.strip() != array_types[name] + ' 0':
                fail(f'无法验证单元属性 {name} 是否为空；请检查 systemd 配置和 D-Bus 访问权限')
            values[name] = ''
    missing = [n for n in names if n not in values]
    if missing:
        fail('systemd 未返回必需的属性：' + ', '.join(missing))
    return values


def validate(p):
    if p['LoadState'] != 'loaded' or not p['FragmentPath'] or p['NeedDaemonReload'] != 'no':
        fail('单元未加载或需要执行 daemon-reload')
    if p['WorkingDirectory'] != str(ROOT) or p['Type'] != 'simple' or p['KillMode'] != 'control-group':
        fail('单元的工作目录、Type 或 KillMode 不符合约定')
    if any(p[n] for n in ('ExecStartPre', 'ExecStartPost', 'ExecCondition', 'ExecStop', 'ExecStopPost', 'RootDirectory', 'RootImage')):
        fail('单元使用了不支持的钩子或文件系统根目录')
    if p['EnvironmentFiles'] != str(CONFIG):
        fail('单元必须且只能使用必需的 /etc/zg-homework-server/env 环境文件')
    if (set(p['Environment'].split()) != {'PYTHONDONTWRITEBYTECODE=1', 'ZG_HOMEWORK_SYSTEMD_PRODUCTION=1'}
            or p['PassEnvironment'] or p['UnsetEnvironment'] or p['PAMName']):
        fail('单元环境设置不符合生产约定，或使用了 PAM')
    manager = run('systemctl', 'show-environment')
    if manager.returncode:
        fail('无法验证 systemd 管理器环境')
    for line in manager.stdout.splitlines():
        key = line.partition('=')[0].upper()
        if key in APP_KEYS or key == 'ZG_HOMEWORK_SYSTEMD_PRODUCTION' or key.startswith(('PYTHON', 'UVICORN_', 'LD_')):
            fail('systemd 管理器包含不支持的应用、Python、Uvicorn 或动态链接环境变量')
    expected = f'{PYTHON} -m uvicorn app.main:app --host 127.0.0.1 --port {PORT} --workers 1'
    # systemctl show uses this structured format; reject extra commands and flags.
    pattern = r'^\{ path=(.*?) ; argv\[\]=(.*?) ; ignore_errors=no ; .* \}$'
    match = re.fullmatch(pattern, p['ExecStart'])
    if not match or match.group(1) != PYTHON or match.group(2) != expected:
        fail('单元的 ExecStart 与要求的命令不完全一致')
    if p['ActiveState'] == 'active' and (not p['ControlGroup'].startswith('/') or '..' in p['ControlGroup'].split('/')):
        fail('无法验证单元的控制组')


def listeners():
    found = set()
    for name in ('tcp', 'tcp6'):
        try:
            lines = Path('/proc/net/' + name).read_text().splitlines()[1:]
        except OSError:
            fail('无法检查 Linux TCP 监听端口')
        for line in lines:
            fields = line.split()
            if len(fields) >= 10 and fields[3] == '0A' and int(fields[1].split(':')[1], 16) == int(PORT):
                found.add(fields[9])
    return found


def active_owned(p):
    if p['ActiveState'] != 'active' or p['SubState'] != 'running':
        fail('单元未处于 active/running 状态')
    try:
        pid = int(p['MainPID'])
        if pid <= 1:
            raise ValueError()
        proc = Path('/proc') / str(pid)
        cmd = proc.joinpath('cmdline').read_bytes().split(b'\0')
        expected = [PYTHON, '-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', PORT, '--workers', '1', '']
        if [os.fsdecode(x) for x in cmd] != expected or os.readlink(proc / 'cwd') != str(ROOT):
            fail('运行中的主进程与当前源码和命令不匹配')
        groups = proc.joinpath('cgroup').read_text().splitlines()
        if not any(line.split(':', 2)[-1] == p['ControlGroup'] for line in groups):
            fail('运行中的进程不在单元的控制组中')
        env = proc.joinpath('environ').read_bytes().split(b'\0')
        entries = [os.fsdecode(x) for x in env if x]
        if ('PYTHONDONTWRITEBYTECODE=1' not in entries or 'ZG_HOMEWORK_SYSTEMD_PRODUCTION=1' not in entries or any(
            (x.startswith('PYTHON') and x != 'PYTHONDONTWRITEBYTECODE=1') or x.startswith(('UVICORN_', 'LD_')) for x in entries
        )):
            fail('运行中的进程缺少生产标志或包含不支持的 Python、Uvicorn 或动态链接环境变量')
        fds = {os.readlink(fd) for fd in proc.joinpath('fd').iterdir() if fd.exists()}
        owned = {x[8:-1] for x in fds if x.startswith('socket:[') and x.endswith(']')}
    except (OSError, ValueError) as exc:
        fail(f'无法验证运行中的进程（权限不足或进程已变化）：{exc}')
    sockets = listeners()
    if not sockets or not sockets <= owned:
        fail('端口未由单元主进程独占')


def runtime():
    if not Path(PYTHON).is_file() or not os.access(PYTHON, os.X_OK):
        fail('配置的 Python 可执行文件不可用')
    result = run(PYTHON, '-I', '-B', '-c', 'import sys, uvicorn; assert sys.version_info >= (3, 12)')
    if result.returncode:
        fail('需要 Python 3.12 或更高版本及已安装的 Uvicorn')
    manager = run('systemctl', 'show-environment')
    if manager.returncode:
        fail('无法检查管理器环境以验证配置')
    manager_env = dict(line.split('=', 1) for line in manager.stdout.splitlines() if '=' in line)
    if any(k.upper() in APP_KEYS or k.upper() == 'ZG_HOMEWORK_SYSTEMD_PRODUCTION'
           or k.upper().startswith(('PYTHON', 'UVICORN_', 'LD_')) for k in manager_env):
        fail('systemd 管理器包含不支持的应用、Python、Uvicorn 或动态链接环境变量')
    if not CONFIG.is_file():
        fail('生产配置需要 /etc/zg-homework-server/env 文件')
    # Never print configuration values or Python exception text, which may contain secrets.
    code = r'''
import os, re, sys
from pathlib import Path
try:
    allowed = set(sys.argv[3].split(','))
    v = {}
    with open(sys.argv[1], encoding='utf-8', newline='') as source:
        text = source.read()
    if any((ord(c) < 32 and c != '\n') or ord(c) == 127 for c in text):
        sys.exit(2)
    for line in text.split('\n'):
        if not line or line.startswith('#'):
            continue
        key, sep, value = line.partition('=')
        if (not sep or key not in allowed or key in v or value != value.strip()
                or any(ord(c) < 32 or ord(c) == 127 or c in "'\"\\$" for c in value)):
            sys.exit(2)
        v[key] = value
    mask = 0
    if v.get("ENV", "").lower() not in ("prod", "production"):
        mask |= 1
    if v.get("DEBUG", "").lower() not in ("false", "0", "no", "off"):
        mask |= 2
    if not v.get("DATABASE_URL", "").startswith("mysql+pymysql://"):
        mask |= 4
    if not v.get("JWT_SECRET") or v["JWT_SECRET"] == "change-me-in-production":
        mask |= 8
    for key, bit in (("DATABASE_URL", 4), ("JWT_SECRET", 8), ("UPLOAD_DIR", 16),
                     ("PRIVATE_HOMEWORK_DIR", 32), ("CORS_ORIGINS", 64)):
        if re.search(r"__[^\s]*?__", v.get(key) or ""):
            mask |= bit
    root = Path(sys.argv[2]).resolve()
    paths = []
    for key, bit in (("UPLOAD_DIR", 16), ("PRIVATE_HOMEWORK_DIR", 32)):
        if not v.get(key) or not Path(v[key]).is_absolute():
            mask |= bit
            paths.append(None)
            continue
        path = Path(v[key]).resolve()
        if path == root or root in path.parents:
            mask |= bit
        paths.append(path)
    a, b = paths
    if a is not None and b is not None and (a == b or a in b.parents or b in a.parents):
        mask |= 16 | 32
except Exception:
    sys.exit(1)
sys.exit(128 | mask if mask else 0)
'''
    try:
        config = subprocess.run([PYTHON, '-I', '-B', '-c', code, str(CONFIG), str(ROOT.parent), ','.join(sorted(APP_KEYS))],
                                env=manager_env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15)
    except (OSError, subprocess.TimeoutExpired):
        fail('无法检查生产配置')
    if config.returncode:
        if config.returncode == 2:
            fail('生产配置文件格式不受支持：请检查键名、重复项、引号、转义、插值及空白')
        if 129 <= config.returncode <= 255:
            checks = (
                (1, 'ENV 必须为 prod 或 production'),
                (2, 'DEBUG 必须关闭'),
                (4, 'DATABASE_URL 必须使用 mysql+pymysql:// 且不能含占位符'),
                (8, 'JWT_SECRET 必须非空、非默认值且不能含占位符'),
                (16, 'UPLOAD_DIR 必须为检出目录之外、不重叠的绝对路径且不能含占位符'),
                (32, 'PRIVATE_HOMEWORK_DIR 必须为检出目录之外、不重叠的绝对路径且不能含占位符'),
                (64, 'CORS_ORIGINS 不能含占位符'),
            )
            fail('生产配置校验失败：' + '；'.join(message for bit, message in checks if config.returncode & bit))
        fail('无法检查生产配置')
    app = ROOT / 'app'
    if app.is_symlink() or not app.is_dir():
        fail('app 必须是当前检出目录中的真实目录')
    for directory, dirs, files in os.walk(app, followlinks=False):
        for name in dirs + files:
            path = Path(directory) / name
            if path.is_symlink():
                fail('app 中的符号链接妨碍安全验证字节码和源码')
            if name.endswith(('.pyc', '.pyo')):
                fail('app 中存在字节码；请在启动前由运维人员检查并清除')


def health():
    try:
        req = urllib.request.Request(f'http://127.0.0.1:{PORT}/homework_api/health', data=b'', method='POST')
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(req, timeout=2) as response:
            data = json.load(response)
            return response.status == 200 and data.get('code') == 0 and data.get('data', {}).get('status') == 'ok'
    except (OSError, ValueError, AttributeError):
        return False


def state(p):
    print(f'unit={UNIT} state={p["ActiveState"]}/{p["SubState"]} port={PORT} source={ROOT}')
    if p['ActiveState'] == 'active':
        active_owned(p)
        if not health():
            fail('单元正在运行，但 POST 健康检查失败')
        print('health=ok（不验证数据库连接持续可用）')
    elif listeners():
        fail('单元未运行，但端口已被监听')
    else:
        print('port=free；服务未运行')


def main():
    if len(sys.argv) != 2 or sys.argv[1] in ('help', '-h', '--help'):
        print('用法：server_run.sh {check|status|start|stop|restart}\n'
              '环境变量：SERVER_UNIT（默认 zg-homework-server.service）、SERVER_PORT（8000）、'
              'SERVER_PYTHON（module/.venv/bin/python）。单元约定详见 README。')
        return 0 if len(sys.argv) == 2 and sys.argv[1] in ('help', '-h', '--help') else 2
    command = sys.argv[1]
    if command not in ('check', 'status', 'start', 'stop', 'restart'):
        fail('未知命令；请使用 --help 查看帮助')
    if not re.fullmatch(r'[A-Za-z0-9_.@-]+\.service', UNIT):
        fail('单元名称无效')
    if not PORT.isascii() or not PORT.isdecimal() or not 1 <= int(PORT) <= 65535 or str(int(PORT)) != PORT:
        fail('端口无效')
    if not os.path.isabs(PYTHON) or not re.fullmatch(r'/[A-Za-z0-9_./-]+', PYTHON) or not re.fullmatch(r'/[A-Za-z0-9_./-]+', str(ROOT)):
        fail('Python 和检出目录路径必须为绝对路径，且只能包含 ASCII 字母、数字、_、-、. 和 /')
    p = properties()
    validate(p)
    if command == 'status':
        state(p)
        return 0
    if command == 'check':
        runtime()
        state(p)
        print('运行环境和单元约定验证通过')
        return 0
    if p['ActiveState'] not in ('active', 'inactive', 'failed'):
        fail('单元正在切换状态；请等待状态稳定后重试')
    if p['ActiveState'] == 'active':
        active_owned(p)
        if command == 'start':
            if not health():
                fail('服务已运行但健康检查失败；请排查后使用 restart')
            print('服务已运行且健康；未执行任何操作')
            return 0
    elif command == 'stop':
        print('服务已停止；未执行任何操作')
        return 0
    if command in ('start', 'restart'):
        runtime()
        if p['ActiveState'] != 'active' and listeners():
            fail('端口已被占用；拒绝启动')
    # Re-read before control to detect changes since inspection.
    again = properties()
    validate(again)
    if again != p:
        fail('验证期间单元状态或配置发生变化；请重试')
    result = run('systemctl', command, UNIT)
    if result.returncode:
        fail(f'systemctl {command} 失败')
    if command == 'stop':
        if properties()['ActiveState'] != 'inactive':
            fail('单元未进入 inactive 状态')
        print('已停止')
        return 0
    deadline = time.monotonic() + TIMEOUT
    while time.monotonic() < deadline:
        current = properties()
        validate(current)
        if current['ActiveState'] in ('failed', 'inactive'):
            fail('单元在启动期间停止或进入 failed 状态')
        if current['ActiveState'] == 'active' and current['SubState'] == 'running':
            try:
                active_owned(current)
                if health():
                    print('运行中；POST health=ok（不保证数据库连接可用）')
                    return 0
            except RuntimeError:
                pass
        time.sleep(1)
    fail('启动超时，未能验证进程归属和 POST 健康检查')


if __name__ == '__main__':
    try:
        sys.exit(main())
    except RuntimeError as exc:
        print(f'错误：{exc}', file=sys.stderr)
        if re.fullmatch(r'[A-Za-z0-9_.@-]+\.service', UNIT):
            print(f'日志：journalctl -u {UNIT} -n 100 --no-pager', file=sys.stderr)
        sys.exit(1)
