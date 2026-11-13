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
ENV_DEFAULTS = {
    'ENV': 'prod',
    'DEBUG': 'false',
    'DB_ECHO': 'false',
    'JWT_ALGORITHM': 'HS256',
    'JWT_EXPIRE_DAYS': '7',
    'ADMIN_INIT_PASSWORD': '',
    'MAX_UPLOAD_MB': '10',
    'ALLOWED_EXTENSIONS': 'jpg,jpeg,png,pdf',
    'ARTICLE_ALLOWED_EXTENSIONS': 'pdf,docx',
    'ARTICLE_MAX_UPLOAD_MB': '10',
    'REGISTER_RATE_LIMIT': '10',
    'ACTION_RATE_LIMIT': '10',
}
FORBIDDEN = re.compile(r'[\'"\\$]|[\x00-\x1f\x7f]')
PLACEHOLDER = re.compile(r'__[^\s]*?__')


def fail(message):
    raise RuntimeError(message)


def translate(message):
    return {
        'usage: ': '用法：',
        'options': '选项',
        'positional arguments': '位置参数',
        'show this help message and exit': '显示此帮助信息并退出',
        '%(prog)s: error: %(message)s\n': '%(prog)s：错误：%(message)s\n',
    }.get(message, message)


argparse._ = translate
parser = argparse.ArgumentParser(
    description='安装 zg-homework 服务端：渲染 systemd 单元、生成生产配置、建立数据目录。',
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
parser.add_argument('--env-file', default='/etc/zg-homework-server/env', help='生产配置路径')
parser.add_argument('--unit-file', default='/etc/systemd/system/' + UNIT_NAME, help='systemd 单元路径')
parser.add_argument('--root', default='/', help='根前缀；用于沙箱测试，默认 /')
parser.add_argument('--skip-venv', action='store_true', help='跳过虚拟环境创建')
parser.add_argument('--no-start', action='store_true', help='安装后不启动服务')
parser.add_argument('--force-env', action='store_true', help='覆盖已存在的生产配置')
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


def check_value(key, value):
    if FORBIDDEN.search(value):
        fail(f'{key} 的值包含不允许的字符')
    if PLACEHOLDER.search(value):
        fail(f'{key} 的值包含未替换的占位符')
    return value


def owner_ids(spec):
    name, _, group = spec.partition(':')
    try:
        uid = pwd.getpwnam(name).pw_uid
        gid = grp.getgrnam(group or name).gr_gid
    except KeyError:
        fail(f'无法解析属主 {spec}')
    return uid, gid


def write(path, text, mode):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')
    path.chmod(mode)


def render_unit(server_dir, python, user, group, port):
    template = Path(__file__).resolve().parent / 'zg-homework-server.service.example'
    text = template.read_text(encoding='utf-8')
    text = text.replace('__SERVER_MODULE_DIR__', str(server_dir))
    text = text.replace('__SERVER_PYTHON__', python)
    text = text.replace('__SERVICE_USER__', user)
    text = text.replace('__SERVICE_GROUP__', group)
    text = text.replace('__SERVER_PORT__', str(port))
    if '__' in text:
        fail('systemd 单元模板仍有未替换的占位符')
    expected = (f'{python} -m uvicorn app.main:app --host 127.0.0.1 '
                f'--port {port} --workers 1')
    if f'ExecStart={expected}' not in text:
        fail('渲染后的 ExecStart 与 server_run.sh 的约定不一致')
    return text


def build_env(server_dir, data_dir, jwt_secret, cors_origins):
    template = Path(__file__).resolve().parent / 'production.env.example'
    values = dict(ENV_DEFAULTS)
    for line in template.read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, _, value = line.partition('=')
        values[key] = value
    values.update({
        'DATABASE_URL': args.database_url,
        'JWT_SECRET': jwt_secret,
        'UPLOAD_DIR': str(data_dir / 'uploads'),
        'PRIVATE_HOMEWORK_DIR': str(data_dir / 'private_homework'),
        'CORS_ORIGINS': cors_origins,
    })
    for key, value in values.items():
        check_value(key, value)
    return ''.join(f'{key}={values[key]}\n' for key in sorted(values))


def random_secret():
    return secrets.token_hex(32)


def systemctl(*arguments):
    try:
        subprocess.run(['systemctl', *arguments], check=True)
    except FileNotFoundError:
        fail('找不到 systemctl；请确认在安装了 systemd 的生产机上以 root 运行')
    except subprocess.CalledProcessError:
        fail(f'systemctl {arguments[0]} 执行失败')


def main():
    if not args.database_url:
        parser.error('--database-url 是必填项')
    if not args.database_url.startswith('mysql+pymysql://'):
        fail('--database-url 必须使用 mysql+pymysql:// 驱动')
    if not args.database_url.endswith('charset=utf8mb4'):
        fail('--database-url 必须以 charset=utf8mb4 结尾')
    if not re.fullmatch(r'[0-9]{1,5}', args.api_port) or not 1 <= int(args.api_port) <= 65535:
        fail('--api-port 必须是 1-65535 的端口')
    server_dir = Path(args.server_dir).resolve()
    if not (server_dir / 'app' / 'main.py').is_file():
        fail(f'--server-dir 必须包含 app/main.py：{server_dir}')
    data_dir = Path(args.data_dir).resolve()
    if data_dir == server_dir or server_dir in data_dir.parents:
        fail('--data-dir 必须位于服务端检出目录之外')
    env_owner = args.env_owner or f'root:{args.service_group}'
    env_uid, env_gid = owner_ids(env_owner)
    try:
        service_uid = pwd.getpwnam(args.service_user).pw_uid
        service_gid = grp.getgrnam(args.service_group).gr_gid
    except KeyError:
        fail(f'无法解析服务身份 {args.service_user}:{args.service_group}')

    unit_path = under_root(args.unit_file)
    env_path = under_root(args.env_file)
    python = str(server_dir / '.venv' / 'bin' / 'python')

    write(unit_path, render_unit(server_dir, python, args.service_user,
                                 args.service_group, args.api_port), 0o644)

    existing = {}
    if env_path.is_file() and not args.force_env:
        for line in env_path.read_text(encoding='utf-8').splitlines():
            if line and not line.startswith('#') and '=' in line:
                key, _, value = line.partition('=')
                existing[key] = value
    previous = existing.get('JWT_SECRET') or ''
    if args.jwt_secret:
        jwt = args.jwt_secret
    elif previous and not PLACEHOLDER.search(previous):
        jwt = previous
    else:
        jwt = random_secret()
    cors = args.cors_origins if args.cors_origins is not None else existing.get('CORS_ORIGINS', '')
    write(env_path, build_env(server_dir, data_dir, jwt, cors), 0o640)
    set_owner(env_path, env_uid, env_gid)

    for name in ('uploads', 'private_homework'):
        target = data_dir / name
        target.mkdir(parents=True, exist_ok=True)
        target.chmod(0o750)
        set_owner(target, service_uid, service_gid)

    if not args.skip_venv:
        init = server_dir / 'scripts' / 'init_check.sh'
        if not init.is_file():
            fail(f'缺少虚拟环境初始化脚本：{init}')
        result = subprocess.run(['sh', str(init)], cwd=str(server_dir))
        if result.returncode:
            fail('虚拟环境初始化失败')

    systemctl('daemon-reload')
    if not args.no_start:
        systemctl('enable', '--now', UNIT_NAME)

    print('安装完成')
    print(f'  代码目录：{server_dir}')
    print(f'  生产配置：{env_path}')
    print(f'  systemd 单元：{unit_path}（{UNIT_NAME}）')
    print(f'  上传数据：{data_dir}/uploads、{data_dir}/private_homework')
    print('下一步：执行 python -m app.seed.initial_data 初始化数据库')
    print('        执行 sh scripts/server_run.sh check 校验运行契约')


try:
    main()
except RuntimeError as exc:
    print(f'错误：{exc}', file=sys.stderr)
    sys.exit(1)
