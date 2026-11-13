#!/bin/sh
'''exec' python3 "$0" "$@"
' '''
"""安装服务端：渲染 systemd 单元、生成生产配置、建立数据目录。"""
import argparse
import grp
import os
from pathlib import Path
import pwd
import re
import secrets
import subprocess
import sys

UNIT_NAME = 'zg-homework-server.service'
DEFAULT_ENV_FILE = '/etc/zg-homework-server/env'
DEFAULT_UNIT_FILE = '/etc/systemd/system/' + UNIT_NAME
FORBIDDEN = re.compile(r'[\'"\\$]|[\x00-\x1f\x7f]')
# server_run.sh 用同一个正则检查配置里是否残留占位符。
PLACEHOLDER = re.compile(r'__[^\s]*?__')
# 模板里出现过的占位符名字；只认这些名字，避免合法的双下划线路径被误判。
PLACEHOLDER_NAMES = (
    '__REPLACE_ME__', '__SERVER_MODULE_DIR__', '__SERVER_PYTHON__',
    '__SERVICE_USER__', '__SERVICE_GROUP__', '__SERVER_PORT__',
)
# server_run.sh 只接受这些配置键；多余的键会让它直接拒绝整个配置文件。
ALLOWED_KEYS = frozenset((
    'APP_NAME', 'ENV', 'DEBUG', 'DATABASE_URL', 'DB_ECHO', 'JWT_SECRET',
    'JWT_ALGORITHM', 'JWT_EXPIRE_DAYS', 'ADMIN_INIT_PASSWORD', 'CORS_ORIGINS',
    'UPLOAD_DIR', 'PRIVATE_HOMEWORK_DIR', 'MAX_UPLOAD_MB', 'ALLOWED_EXTENSIONS',
    'ARTICLE_ALLOWED_EXTENSIONS', 'ARTICLE_MAX_UPLOAD_MB', 'REGISTER_RATE_LIMIT',
    'ACTION_RATE_LIMIT',
))
# server_run.sh 用同一个正则与同一句中文拒绝非法路径；这里必须逐字一致，
# 否则 install.sh 会渲染出 server_run.sh 永远管不了的单元。
SAFE_PATH = re.compile(r'/[A-Za-z0-9_./-]+')
PATH_RULE = 'Python 和检出目录路径必须为绝对路径，且只能包含 ASCII 字母、数字、_、-、. 和 /'


def fail(message):
    raise RuntimeError(message)


def translate_error(message):
    """把 argparse 的英文报错改写成中文。"""
    if re.search(r'[一-鿿]', message):  # 已经是中文的报错原样输出
        return message
    if message.startswith('unrecognized arguments: '):
        return '无法识别的参数：' + message[len('unrecognized arguments: '):]
    if message.startswith('the following arguments are required: '):
        return '缺少必填参数：' + message[len('the following arguments are required: '):]
    match = re.fullmatch(r'argument (--?[^\s:]+): expected one argument', message)
    if match:
        return f'参数 {match.group(1)} 缺少取值'
    match = re.fullmatch(r"invalid choice: '(.*?)' \(choose from (.*)\)", message)
    if match:
        return f'参数取值无效：{match.group(1)}（可选：{match.group(2)}）'
    if message.startswith('ambiguous option: '):
        return '参数有歧义：' + message[len('ambiguous option: '):]
    if 'expected one argument' in message:
        return '参数缺少取值'
    return f'参数无效：{message}'


class ChineseParser(argparse.ArgumentParser):
    """只使用 argparse 的公开接口，把提示与报错本地化为中文。"""

    def format_usage(self):
        return super().format_usage().replace('usage: ', '用法：')

    def format_help(self):
        return (super().format_help()
                .replace('usage: ', '用法：')
                .replace('options:', '选项：')
                .replace('show this help message and exit', '显示此帮助信息并退出'))

    def error(self, message):
        self.print_usage(sys.stderr)
        self.exit(2, f'{self.prog}：错误：{translate_error(message)}\n')


parser = ChineseParser(
    description='安装 zg-homework 服务端：渲染 systemd 单元、生成生产配置、建立数据目录。',
    epilog='环境变量：INIT_PYTHON=python3.12 可指定创建虚拟环境所用的解释器（默认 python3，要求 3.12+）。',
    add_help=False)
parser.add_argument('--server-dir', default='/data/apps/zg-homework-server', help='服务端代码检出目录')
parser.add_argument('--api-port', default='8000', help='后端监听端口（仅 127.0.0.1）')
parser.add_argument('--service-user', default='www-data', help='systemd 运行用户')
parser.add_argument('--service-group', default='www-data', help='systemd 运行组')
parser.add_argument('--env-owner', default=None, help='env 文件属主 user:group（默认 root:<service-group>）')
parser.add_argument('--database-url', help='mysql+pymysql://…?charset=utf8mb4')
parser.add_argument('--jwt-secret', help='JWT 密钥；不给则随机生成 32 字节 hex')
parser.add_argument('--cors-origins', default=None,
                    help='允许的来源，逗号分隔；同域反代通常留空；不给则保留已有配置')
parser.add_argument('--data-dir', default='/var/lib/zg-homework', help='上传数据根目录')
parser.add_argument('--env-file', default=DEFAULT_ENV_FILE, help=f'生产配置路径（只能是 {DEFAULT_ENV_FILE}）')
parser.add_argument('--unit-file', default=DEFAULT_UNIT_FILE, help='systemd 单元路径')
parser.add_argument('--root', default='/', help='根前缀；用于沙箱测试，默认 /')
parser.add_argument('--skip-venv', action='store_true', help='跳过虚拟环境创建')
parser.add_argument('--no-start', action='store_true', help='安装后不启动服务')
parser.add_argument('--force-env', action='store_true', help='丢弃已有生产配置并整体重建')
parser.add_argument('-h', '--help', action='store_true', help='显示此帮助信息并退出')
args = parser.parse_args()

if args.help:
    print(parser.format_help())
    sys.exit(0)


def under_root(path):
    """把系统配置文件的写入路径映射到 root 前缀之下。"""
    root = Path(args.root).resolve()
    return root / str(path).lstrip('/')


def set_owner(path, uid, gid):
    try:
        os.chown(path, uid, gid)
    except OSError as exc:
        fail(f'无法设置 {path} 的属主：{exc.strerror or exc}；请以 root 运行')


def allowed_keys():
    """读取 server_run.sh 允许的键集合；读不到时退回本文件内置的同一份副本。"""
    controller = Path(__file__).resolve().parent / 'server_run.sh'
    try:
        text = controller.read_text(encoding='utf-8')
    except OSError:
        return set(ALLOWED_KEYS)
    match = re.search(r'APP_KEYS = frozenset\(\((.*?)\)\)', text, re.S)
    if not match:
        return set(ALLOWED_KEYS)
    keys = {item.strip().strip('\'"')
            for item in match.group(1).replace('\n', '').split(',') if item.strip()}
    return keys or set(ALLOWED_KEYS)


def check_value(key, value, source=None):
    """按 server_run.sh 的配置契约校验一个值。"""
    where = f'（{source}）' if source else ''
    if FORBIDDEN.search(value):
        fail(f'{key} 的值包含不允许的字符（引号、反斜杠、$ 或控制字符）{where}')
    if value != value.strip():
        fail(f'{key} 的值包含首尾空白{where}；server_run.sh 的配置校验会拒绝该格式')
    if any(name in value for name in PLACEHOLDER_NAMES):
        fail(f'{key} 的值仍包含未替换的占位符{where}')
    if key in ('DATABASE_URL', 'JWT_SECRET', 'UPLOAD_DIR', 'PRIVATE_HOMEWORK_DIR', 'CORS_ORIGINS') \
            and PLACEHOLDER.search(value):
        fail(f'{key} 的值包含 __ 形式的占位符{where}；server_run.sh 的配置校验会拒绝该格式')
    return value


def owner_ids(spec):
    name, _, group = spec.partition(':')
    try:
        uid = pwd.getpwnam(name).pw_uid
        gid = grp.getgrnam(group or name).gr_gid
    except KeyError:
        fail(f'无法解析属主 {spec}')
    return uid, gid


def write_file(path, text, mode):
    """先以受限权限创建文件再放宽权限，避免秘密短暂可读。"""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        try:
            # os.open 的 mode 只在创建时生效；已存在的文件可能仍是 0644，
            # 必须在写入内容之前先用 fchmod 收紧权限。
            os.fchmod(fd, 0o600)
        except OSError:
            os.close(fd)
            raise
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            stream.write(text)
        os.chmod(path, mode)
    except OSError as exc:
        fail(f'无法写入文件 {path}：{exc.strerror or exc}')


def render_unit(server_dir, python, user, group, port):
    template = Path(__file__).resolve().parent / 'zg-homework-server.service.example'
    try:
        text = template.read_text(encoding='utf-8')
    except OSError as exc:
        fail(f'无法读取 systemd 单元模板 {template}：{exc.strerror or exc}')
    text = text.replace('__SERVER_MODULE_DIR__', str(server_dir))
    text = text.replace('__SERVER_PYTHON__', python)
    text = text.replace('__SERVICE_USER__', user)
    text = text.replace('__SERVICE_GROUP__', group)
    text = text.replace('__SERVER_PORT__', str(port))
    # 只认已知的占位符名字；合法的双下划线路径（如 /data/apps/my__app）不算占位符。
    if any(name in text for name in PLACEHOLDER_NAMES):
        fail('systemd 单元模板仍有未替换的占位符')
    expected = (f'{python} -m uvicorn app.main:app --host 127.0.0.1 '
                f'--port {port} --workers 1')
    if f'ExecStart={expected}' not in text:
        fail('渲染后的 ExecStart 与 server_run.sh 的约定不一致')
    return text


def env_key(line):
    """返回一行的配置键；不是配置行则返回 None。"""
    stripped = line.strip()
    if not stripped or stripped.startswith('#') or '=' not in line:
        return None
    return line.partition('=')[0]


def template_values():
    template = Path(__file__).resolve().parent / 'production.env.example'
    try:
        text = template.read_text(encoding='utf-8')
    except OSError as exc:
        fail(f'无法读取生产配置模板 {template}：{exc.strerror or exc}')
    values = {}
    for line in text.splitlines():
        key = env_key(line)
        if key is not None:
            values[key] = line.partition('=')[2]
    return values


def read_existing_env(path):
    """读取已有生产配置，返回 (原始行, 键值)。"""
    if not path.exists():
        return [], {}
    try:
        text = path.read_text(encoding='utf-8')
    except OSError as exc:
        fail(f'无法读取已有生产配置 {path}：{exc.strerror or exc}')
    lines = text.splitlines()
    values = {}
    for line in lines:
        key = env_key(line)
        if key is not None:
            values[key] = line.partition('=')[2]
    return lines, values


def build_env(existing_lines, existing_values, template, overrides):
    """以已有配置为基准生成新内容；只覆盖本次确定的键，其余一律保留。"""
    final = dict(template)
    final.update(existing_values)
    final.update(overrides)
    last = {}
    for index, line in enumerate(existing_lines):
        key = env_key(line)
        if key is not None:
            last[key] = index
    lines = []
    seen = set()
    for index, line in enumerate(existing_lines):
        key = env_key(line)
        if key is None:
            lines.append(line)
            continue
        if last[key] != index:
            continue  # 重复键只保留最后一次出现，避免 server_run.sh 拒绝整个文件
        lines.append(f'{key}={overrides[key]}' if key in overrides else line)
        seen.add(key)
    for key in sorted(final):
        if key not in seen:
            lines.append(f'{key}={final[key]}')
    return '\n'.join(lines) + '\n', final


def random_secret():
    """生成 32 字节 hex 密钥；优先 openssl rand -hex 32，缺失时回退 secrets。"""
    try:
        result = subprocess.run(['openssl', 'rand', '-hex', '32'],
                                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                text=True, timeout=15)
    except (OSError, subprocess.SubprocessError):
        result = None
    if result is not None and result.returncode == 0:
        value = result.stdout.strip()
        if re.fullmatch(r'[0-9a-f]{64}', value):
            return value
    return secrets.token_hex(32)


def systemctl(*arguments):
    try:
        subprocess.run(['systemctl', *arguments], check=True)
    except FileNotFoundError:
        fail('找不到 systemctl；请确认在安装了 systemd 的生产机上以 root 运行')
    except subprocess.CalledProcessError:
        fail(f'systemctl {arguments[0]} 执行失败')


def normalize_port(value):
    if not re.fullmatch(r'[0-9]{1,5}', value):
        fail('--api-port 必须是 1-65535 的端口')
    number = int(value)
    if not 1 <= number <= 65535:
        fail('--api-port 必须是 1-65535 的端口')
    return str(number)


def main():
    if not args.database_url:
        parser.error('--database-url 是必填项')
    database_url = args.database_url
    if not database_url.startswith('mysql+pymysql://'):
        fail('--database-url 必须使用 mysql+pymysql:// 驱动')
    if not database_url.endswith('charset=utf8mb4'):
        fail('--database-url 必须以 charset=utf8mb4 结尾')
    port = normalize_port(args.api_port)
    if args.env_file != DEFAULT_ENV_FILE:
        fail(f'--env-file 只能是 {DEFAULT_ENV_FILE}；systemd 单元的 EnvironmentFile '
             '必须逐字等于该路径，否则 server_run.sh 会拒绝这个单元')
    if args.unit_file != DEFAULT_UNIT_FILE:
        print(f'警告：--unit-file 不是 {DEFAULT_UNIT_FILE}；单元名仍固定为 {UNIT_NAME}，'
              '请确认目标路径在 systemd 的单元目录内', file=sys.stderr)
    server_dir = Path(args.server_dir).resolve()
    # server_run.sh 用同一条规则拒绝非法路径：这里必须先挡住，
    # 否则渲染出的 ExecStart 会被 systemd 按空白拆开，且 server_run.sh 永远不管这个单元。
    python = str(server_dir / '.venv' / 'bin' / 'python')
    for label, value in (('--server-dir', str(server_dir)), ('虚拟环境解释器', python)):
        if not SAFE_PATH.fullmatch(value):
            fail(f'{label} 不被 server_run.sh 接受：{value}；{PATH_RULE}')
    if not (server_dir / 'app' / 'main.py').is_file():
        fail(f'--server-dir 必须包含 app/main.py：{server_dir}')
    data_dir = Path(args.data_dir).resolve()
    checkout_parent = server_dir.parent
    if data_dir == checkout_parent or checkout_parent in data_dir.parents:
        fail(f'--data-dir 不得等于或位于服务端检出目录的上级目录（{checkout_parent}）之下；'
             'server_run.sh 的运行契约要求上传目录位于检出目录的上级目录之外')
    env_owner = args.env_owner or f'root:{args.service_group}'
    env_uid, env_gid = owner_ids(env_owner)
    if env_owner.split(':')[0] != 'root':
        print(f'警告：--env-owner 指定的属主 {env_owner} 不是 root，偏离了 root:<服务组> 的约定；'
              '请确认服务账号确实能读取生产配置', file=sys.stderr)
    try:
        service_uid = pwd.getpwnam(args.service_user).pw_uid
        service_gid = grp.getgrnam(args.service_group).gr_gid
    except KeyError:
        fail(f'无法解析服务身份 {args.service_user}:{args.service_group}')

    unit_path = under_root(args.unit_file)
    env_path = under_root(args.env_file)
    python = str(server_dir / '.venv' / 'bin' / 'python')

    # ---- 校验：所有取值检查通过后才允许写第一个文件 ----
    if args.force_env:
        existing_lines, existing_values = [], {}
    else:
        existing_lines, existing_values = read_existing_env(env_path)
        for index, line in enumerate(existing_lines, start=1):
            if line.strip() and not line.strip().startswith('#') and '=' not in line:
                fail(f'已有生产配置 {env_path} 第 {index} 行不是 KEY=value 格式；'
                     '请先修正该文件（server_run.sh 的配置校验会拒绝它）')
    previous_secret = existing_values.get('JWT_SECRET', '')
    if args.jwt_secret:
        jwt = args.jwt_secret
    elif previous_secret and previous_secret != 'change-me-in-production' \
            and not PLACEHOLDER.search(previous_secret):
        jwt = previous_secret
    else:
        jwt = random_secret()
    previous_cors = existing_values.get('CORS_ORIGINS')
    if args.cors_origins is not None:
        cors = args.cors_origins
    elif previous_cors is None or PLACEHOLDER.search(previous_cors):
        cors = ''
    else:
        cors = previous_cors
    overrides = {
        'DATABASE_URL': database_url,
        'JWT_SECRET': jwt,
        'CORS_ORIGINS': cors,
        'UPLOAD_DIR': str(data_dir / 'uploads'),
        'PRIVATE_HOMEWORK_DIR': str(data_dir / 'private_homework'),
    }
    env_text, final_values = build_env(existing_lines, existing_values,
                                       template_values(), overrides)
    for key, value in final_values.items():
        source = f'已有生产配置 {env_path}' if key in existing_values and key not in overrides else None
        check_value(key, value, source)
    unknown = sorted(key for key in final_values if key not in ALLOWED_KEYS)
    if unknown:
        print('警告：以下配置键不在 server_run.sh 允许的键集合内，校验时会被拒绝：'
              + '、'.join(unknown), file=sys.stderr)
    if final_values.get('ENV', '').lower() not in ('prod', 'production'):
        print('警告：ENV 不是 prod 或 production；server_run.sh 的配置校验会拒绝该文件',
              file=sys.stderr)
    if final_values.get('DEBUG', '').lower() not in ('false', '0', 'no', 'off'):
        print('警告：DEBUG 没有关闭；server_run.sh 的配置校验会拒绝该文件', file=sys.stderr)
    unit_text = render_unit(server_dir, python, args.service_user, args.service_group, port)

    # ---- 虚拟环境：已存在则复用，避免重复安装必然失败 ----
    venv = server_dir / '.venv'
    if venv.exists():
        print(f'复用已存在的虚拟环境：{venv}')
    elif not args.skip_venv:
        init = server_dir / 'scripts' / 'init_check.sh'
        if not init.is_file():
            fail(f'缺少虚拟环境初始化脚本：{init}')
        result = subprocess.run(['sh', str(init)], cwd=str(server_dir))
        if result.returncode:
            fail('虚拟环境初始化失败')

    # ---- 数据目录 ----
    for name in ('uploads', 'private_homework'):
        target = data_dir / name
        try:
            target.mkdir(parents=True, exist_ok=True)
            target.chmod(0o750)
        except OSError as exc:
            fail(f'无法建立数据目录 {target}：{exc.strerror or exc}')
        set_owner(target, service_uid, service_gid)

    # ---- 落盘：先写配置再写单元，避免出现没有配置的单元 ----
    write_file(env_path, env_text, 0o640)
    set_owner(env_path, env_uid, env_gid)
    write_file(unit_path, unit_text, 0o644)

    systemctl('daemon-reload')
    if not args.no_start:
        systemctl('enable', '--now', UNIT_NAME)

    print('安装完成')
    print(f'  监听端口：{port}（仅 127.0.0.1）')
    print(f'  代码目录：{server_dir}')
    print(f'  虚拟环境：{venv}')
    print(f'  生产配置：{env_path}')
    print(f'  systemd 单元：{unit_path}（{UNIT_NAME}）')
    print(f'  上传数据：{data_dir}/uploads、{data_dir}/private_homework')
    if port != '8000':
        print(f'注意：端口不是 8000，请以 SERVER_PORT={port} 执行 '
              'sh scripts/server_run.sh，否则它会拒绝本次安装的单元')
    print('下一步：执行 python -m app.seed.initial_data 初始化数据库')
    print('        执行 sh scripts/server_run.sh check 校验运行契约')


try:
    main()
except RuntimeError as exc:
    print(f'错误：{exc}', file=sys.stderr)
    sys.exit(1)
except OSError as exc:
    print(f'错误：文件操作失败：{exc.strerror or exc}', file=sys.stderr)
    sys.exit(1)
