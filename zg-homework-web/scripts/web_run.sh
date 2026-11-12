#!/bin/sh
# Production controller. All deployment state is outside the checkout.
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd -P)
export WEB_SOURCE_ROOT="$ROOT"
exec python3 - "$@" <<'PY'
import fcntl
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

root = Path(os.environ['WEB_SOURCE_ROOT'])
unit = os.environ.get('WEB_UNIT', 'zg-homework-web.service')
port = os.environ.get('WEB_PORT', '8080')
base = Path(os.environ.get('WEB_DEPLOY_DIR', '/var/lib/zg-homework-web'))
config = Path(os.environ.get('WEB_NGINX_CONFIG', '/etc/zg-homework-web/nginx.conf'))
nginx = os.environ.get('WEB_NGINX_BIN', '/usr/sbin/nginx')
upstream = os.environ.get('WEB_API_UPSTREAM', '127.0.0.1:8000')
command = sys.argv[1] if len(sys.argv) == 2 else 'help' if len(sys.argv) == 1 else ''

def fail(message):
    raise RuntimeError(message)

def run(args, check=True, **kwargs):
    return subprocess.run(args, check=check, text=True, **kwargs)

def output(args):
    return run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout.strip()

def usage():
    print('用法: web_run.sh {check|status|start|stop|restart|help}')
    print('可覆盖的环境变量: WEB_UNIT, WEB_PORT, WEB_DEPLOY_DIR, WEB_NGINX_CONFIG, WEB_NGINX_BIN, WEB_API_UPSTREAM')
    print('start 是幂等操作；restart 会构建新版本。所需的专用 nginx unit 和配置请参阅 Web README。')

def validate_inputs():
    if not re.fullmatch(r'[A-Za-z0-9_.@-]+\.service', unit): fail('无效的服务 unit 名称')
    if not port.isdigit() or not 1 <= int(port) <= 65535: fail('无效的端口')
    if not re.fullmatch(r'127\.0\.0\.1:[0-9]{1,5}', upstream) or not 1 <= int(upstream.split(':')[1]) <= 65535: fail('API 上游地址必须为 127.0.0.1:PORT')
    for p in (base, config, Path(nginx), root):
        if not p.is_absolute() or not re.fullmatch(r'/[A-Za-z0-9_./-]+', str(p)) or '..' in p.parts: fail('路径必须为绝对路径且只能包含安全字符')
    if base.resolve() != base or config.resolve() != config or Path(nginx).resolve() != Path(nginx): fail('部署目录、配置文件和 nginx 路径不得包含符号链接')
    if base == root or root in base.parents or base in root.parents: fail('部署目录必须位于代码检出目录之外')
    if not base.is_dir() or not (base / 'releases').is_dir() or (base / 'releases').is_symlink(): fail('请先创建真实的部署目录及 releases 子目录')
    if not config.is_file() or not os.access(nginx, os.X_OK): fail('缺少专用 nginx 配置文件或可执行文件')

def expected_config():
    return f'''worker_processes 1;
pid {base}/nginx.pid;
error_log stderr;
events {{ worker_connections 1024; }}
http {{
    include /etc/nginx/mime.types;
    default_type application/octet-stream;
    access_log /dev/stdout;
    server {{
        listen 127.0.0.1:{port};
        root {base}/current;
        index index.html;
        client_max_body_size 12m;
        location /homework_api/ {{
            proxy_pass http://{upstream};
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
        }}
        location / {{ try_files $uri $uri/ /index.html; }}
    }}
}}
'''

def properties():
    names = ['LoadState', 'FragmentPath', 'WorkingDirectory', 'ExecStart', 'ExecCondition', 'ExecStartPre', 'ExecStartPost', 'ExecStop', 'ExecStopPost', 'ExecReload', 'RootDirectory', 'RootImage', 'Type', 'ControlGroup', 'ActiveState', 'SubState', 'MainPID', 'NeedDaemonReload', 'KillMode', 'Environment', 'EnvironmentFiles', 'PassEnvironment', 'UnsetEnvironment']
    text = output(['systemctl', 'show', unit, '--all', '--no-pager'] + ['--property=' + n for n in names])
    props = dict(line.split('=', 1) for line in text.splitlines() if '=' in line)
    missing = [n for n in names if n not in props]
    if missing: fail('systemd 未返回必需的属性: ' + ', '.join(missing))
    return props

def verify_unit():
    p = properties()
    if p['LoadState'] != 'loaded' or not p['FragmentPath'] or p['WorkingDirectory'] != str(root): fail('unit 不存在或不属于当前代码检出目录（WorkingDirectory 不匹配）')
    if p['Type'] != 'simple' or p['RootDirectory'] or p['RootImage']: fail('unit 必须使用 Type=simple 且不能更改根目录')
    if p['NeedDaemonReload'] != 'no' or p['KillMode'] != 'control-group': fail('unit 必须为最新状态并使用 KillMode=control-group')
    if any(p[k] for k in ('ExecCondition', 'ExecStartPre', 'ExecStartPost', 'ExecStop', 'ExecStopPost', 'ExecReload', 'Environment', 'EnvironmentFiles', 'PassEnvironment', 'UnsetEnvironment')): fail('unit 包含额外命令或环境配置，拒绝控制')
    prefix = '{ path=' + nginx + ' ; argv[]=' + nginx + ' -c ' + str(config) + ' -g daemon off; ; ignore_errors=no ;'
    if not p['ExecStart'].startswith(prefix) or p['ExecStart'].count('{ path=') != 1: fail('unit 的 ExecStart 与专用 nginx 命令不匹配')
    if config.read_text() != expected_config(): fail('nginx 配置与要求的专用配置不一致')
    return p

def verify_running(p):
    if p['ActiveState'] != 'active': return
    pid, group = p['MainPID'], p['ControlGroup']
    if not pid.isdigit() or int(pid) <= 1 or not group: fail('无法识别运行中的主进程')
    try:
        proc = Path('/proc', pid)
        args = (proc / 'cmdline').read_bytes().split(b'\0')
        args = [os.fsdecode(x) for x in args if x]
        groups = (proc / 'cgroup').read_text().splitlines()
        exe = os.readlink(proc / 'exe')
        cwd = os.readlink(proc / 'cwd')
    except OSError: fail('无法检查运行中的主进程')
    expected = [nginx, '-c', str(config), '-g', 'daemon off;']
    master_title = 'nginx: master process ' + ' '.join(expected)
    if args not in (expected, [master_title]) or exe != nginx or cwd != str(root): fail('运行中的进程与专用 unit 不匹配，拒绝控制')
    if not any(row.split(':', 2)[-1] == group for row in groups): fail('主进程不在预期的 unit cgroup 中')

def current_target():
    current = base / 'current'
    if not os.path.lexists(current): return None
    if not current.is_symlink(): fail('current 已存在但不是受管理的符号链接')
    target = current.resolve(strict=True)
    if target.parent != (base / 'releases') or not target.is_dir() or (target / '.web-run-owner').is_symlink(): fail('current 未指向受管理的版本')
    marker = target / '.web-run-owner'
    if not marker.is_file() or marker.read_text() != str(root) + '\n': fail('无法验证 current 版本的归属')
    return target

def dependencies(build_required):
    for executable in ('systemctl', 'ss'):
        if not shutil.which(executable): fail('缺少依赖: ' + executable)
    if not build_required: return
    for executable in ('node', 'npm'):
        if not shutil.which(executable): fail('缺少依赖: ' + executable)
    version = output(['node', '--version'])
    match = re.match(r'v(\d+)', version)
    if not match or int(match.group(1)) < 20: fail('需要 Node.js 20 或更高版本')
    for path in ('node_modules/.bin/tsc', 'node_modules/.bin/vite'):
        if not os.access(root / path, os.X_OK): fail('部署前请安装 Web 依赖: ' + path)

def port_check(p):
    # ss must expose PIDs; lack of visibility is treated as an unknown owner.
    text = output(['ss', '-H', '-ltnp', 'sport = :' + port])
    lines = text.splitlines()
    if not lines: return
    group = p['ControlGroup']
    if p['ActiveState'] != 'active' or not group: fail('端口被运行中 unit 之外的进程占用')
    for line in lines:
        ids = re.findall(r'pid=(\d+)', line)
        if not ids: fail('无法确定端口占用者；请使用足够的权限运行')
        for pid in ids:
            try: cg = Path('/proc', pid, 'cgroup').read_text().splitlines()
            except OSError: fail('无法验证端口占用者')
            if not any(row.split(':', 2)[-1] == group or row.split(':', 2)[-1].startswith(group + '/') for row in cg): fail('端口被 unit 之外的进程占用')

def http(method, path):
    request = urllib.request.Request('http://127.0.0.1:' + port + path, method=method)
    try:
        with urllib.request.urlopen(request, timeout=3) as response:
            data = response.read(1024 * 1024)
            if method == 'POST':
                result = json.loads(data)
                return response.status == 200 and result.get('code') == 0 and result.get('data', {}).get('status') == 'ok'
            return response.status == 200 and b'<html' in data.lower()
    except (OSError, ValueError, AttributeError): return False

def health():
    web = http('GET', '/')
    api = http('POST', '/homework_api/health')
    print('Web HTTP:', 'ready' if web else 'FAILED')
    print('API proxy:', 'ready' if api else 'FAILED')
    return web and api

def publish(target):
    # Temporary link is unique and on the same filesystem as current.
    tmpdir = Path(tempfile.mkdtemp(prefix='.web-run-link-', dir=base))
    try:
        link = tmpdir / 'current'
        link.symlink_to(target)
        current_target()
        os.replace(link, base / 'current')
    finally:
        tmpdir.rmdir()

def build():
    release = Path(tempfile.mkdtemp(prefix='web-', dir=base / 'releases'))
    release.chmod(0o755)
    print('正在构建新版本:', release, flush=True)
    # No incremental TypeScript cache and no npm lifecycle scripts.
    run([str(root / 'node_modules/.bin/tsc'), '--noEmit', '--incremental', 'false'], cwd=root)
    env = os.environ.copy()
    env['VITE_API_BASE_URL'] = '/homework_api'
    run([str(root / 'node_modules/.bin/vite'), 'build', '--mode', 'production', '--outDir', str(release), '--emptyOutDir'], cwd=root, env=env)
    if not (release / 'index.html').is_file(): fail('构建未生成 index.html')
    (release / '.web-run-owner').write_text(str(root) + '\n')
    return release

def main():
    if command in ('help', '--help', '-h'):
        usage(); return 0
    if command not in ('check', 'status', 'start', 'stop', 'restart'):
        usage(); return 2
    validate_inputs()
    dependencies(command in ('check', 'start', 'restart'))
    # Lock an existing directory; check/status are read-only and do not take a lock.
    lock = None
    if command in ('start', 'stop', 'restart'):
        lock = os.open(base, os.O_RDONLY | os.O_DIRECTORY)
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    p = verify_unit()
    verify_running(p)
    old = current_target()
    port_check(p)
    print('Unit:', unit, 'state:', p['ActiveState'], '/', p['SubState'])
    print('Source:', root, 'release:', old or '(none)', 'listen: 127.0.0.1:' + port, flush=True)
    if command == 'check':
        print('配置和依赖检查通过；nginx 语法将在启动时检查。')
        return 0
    if command == 'status':
        if p['ActiveState'] != 'active': print('服务未运行'); return 1
        return 0 if health() else 1
    if command == 'stop':
        if p['ActiveState'] == 'inactive': print('服务已停止'); return 0
        latest = verify_unit()
        if latest['ActiveState'] != 'active' or latest['MainPID'] != p['MainPID']: fail('停止前 unit 状态已改变')
        verify_running(latest)
        port_check(latest)
        run(['systemctl', 'stop', unit]); return 0
    if command == 'start' and p['ActiveState'] == 'active':
        print('服务已运行；请使用 restart 部署更改')
        return 0 if health() else 1
    if p['ActiveState'] not in ('active', 'inactive', 'failed'): fail('unit 处于过渡状态')
    release = build()
    # Syntax check can write nginx's error log, but never changes shared nginx.
    run([nginx, '-t', '-c', str(config)])
    latest = verify_unit()
    if latest['ActiveState'] != p['ActiveState'] or latest['MainPID'] != p['MainPID']: fail('构建期间 unit 状态已改变')
    verify_running(latest)
    port_check(latest)
    publish(release)
    try:
        latest = verify_unit()
        if latest['ActiveState'] != p['ActiveState'] or latest['MainPID'] != p['MainPID']: fail('执行控制操作前 unit 状态已改变')
        verify_running(latest)
        port_check(latest)
        run(['systemctl', 'restart' if p['ActiveState'] == 'active' else 'start', unit])
        for _ in range(20):
            time.sleep(0.5)
            if properties()['ActiveState'] == 'active' and http('GET', '/'): break
        else: fail('Web 未能就绪')
    except Exception:
        if old is not None:
            publish(old)
            print('已恢复上一版本的符号链接；请检查 unit，必要时手动重启', file=sys.stderr)
        else:
            print('不存在上一版本；仍使用新版本', file=sys.stderr)
        raise
    if not health(): return 1
    return 0

try:
    sys.exit(main())
except (RuntimeError, OSError, subprocess.SubprocessError) as exc:
    print('web_run:', exc, file=sys.stderr)
    if command in ('start', 'stop', 'restart', 'status'):
        print('查看日志: journalctl -u ' + unit + ' -n 100 --no-pager', file=sys.stderr)
    sys.exit(1)
PY
