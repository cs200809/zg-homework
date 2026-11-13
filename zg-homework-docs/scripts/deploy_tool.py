#!/usr/bin/env python3
"""本地部署与源码打包共用的配置和运行逻辑。"""
import importlib.metadata
import fcntl
import json
import os
from pathlib import Path
import re
import shutil
import signal
import socket
import subprocess
import sys
import tarfile
import tempfile
import time
from datetime import datetime
from urllib.parse import quote, urlsplit
from urllib.request import Request, urlopen

SERVER_KEYS = ('project.name', 'project.port', 'db.mysql.ip', 'db.mysql.port',
               'db.mysql.user', 'db.mysql.password', 'db.mysql.name', 'jwt.secret',
               'jwt.algorithm', 'jwt.expire_days', 'cors.origins', 'private.homework.dir',
               'max.upload_mb', 'allowed.extensions')
WEB_KEYS = ('project.name', 'project.port', 'server.domain')


def fail(message):
    raise ValueError(message)


def properties(path, required):
    if not path.is_file():
        fail(f'缺少配置文件：{path}')
    result = {}
    for number, line in enumerate(path.read_text(encoding='utf-8').splitlines(), 1):
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        key, sep, value = line.partition('=')
        key, value = key.strip(), value.strip()
        if not sep or not key or key in result:
            fail(f'配置格式错误或配置项重复：{path}:{number}')
        result[key] = value
    missing = [key for key in required if not result.get(key)]
    if missing:
        fail('缺少配置项：' + ', '.join(missing))
    return result


def positive(value, name, maximum=None):
    if not value.isascii() or not value.isdigit() or int(value) < 1 or (maximum and int(value) > maximum):
        fail(f'配置项 {name} 必须为有效的正整数' + (f'（最大 {maximum}）' if maximum else ''))


def server_config(config, environment):
    for key in ('project.port', 'db.mysql.port'):
        positive(config[key], key, 65535)
    for key in ('jwt.expire_days', 'max.upload_mb'):
        positive(config[key], key)
    if config['jwt.algorithm'] not in ('HS256', 'HS384', 'HS512'):
        fail('配置项 jwt.algorithm 必须为 HS256、HS384 或 HS512')
    url = ('mysql+pymysql://' + quote(config['db.mysql.user'], safe='') + ':'
           + quote(config['db.mysql.password'], safe='') + '@' + config['db.mysql.ip']
           + ':' + config['db.mysql.port'] + '/' + quote(config['db.mysql.name'], safe='')
           + '?charset=utf8mb4')
    return {'APP_NAME': config['project.name'], 'ENV': environment, 'DATABASE_URL': url,
            'JWT_SECRET': config['jwt.secret'], 'JWT_ALGORITHM': config['jwt.algorithm'],
            'JWT_EXPIRE_DAYS': config['jwt.expire_days'], 'CORS_ORIGINS': config['cors.origins'],
            'PRIVATE_HOMEWORK_DIR': config['private.homework.dir'],
            'MAX_UPLOAD_MB': config['max.upload_mb'], 'ALLOWED_EXTENSIONS': config['allowed.extensions']}


def web_config(config):
    positive(config['project.port'], 'project.port', 65535)
    domain = config['server.domain']
    url = domain if '://' in domain else 'http://' + domain
    try:
        parsed = urlsplit(url)
        if (parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username
                or parsed.password or parsed.path not in ('', '/') or parsed.query or parsed.fragment
                or any(c.isspace() for c in url) or (parsed.port is not None and not 1 <= parsed.port <= 65535)):
            raise ValueError()
    except ValueError:
        fail('配置项 server.domain 必须是有效的 HTTP(S) 地址')
    return url.rstrip('/') + '/homework_api'


def dotenv(values):
    return ''.join(f'{key}={json.dumps(value, ensure_ascii=False)}\n' for key, value in values.items())


def server_python(root):
    for candidate in (root / '.venv/bin/python', root.parent / '.venv/bin/python'):
        if candidate.is_file():
            return str(candidate)
    return shutil.which('python3.12') or sys.executable


def check_server(root, env):
    python = server_python(root)
    code = '''import importlib.metadata as m, re, sys
if sys.version_info < (3, 12): sys.exit("需要 Python 3.12 或更高版本")
missing = []
for line in open(sys.argv[1], encoding="utf-8"):
    match = re.match(r"^([A-Za-z0-9_-]+)(?:\\[[^]]+\\])?==([^\\s]+)", line)
    if match:
        try: installed = m.version(match[1])
        except m.PackageNotFoundError: installed = None
        if installed != match[2]: missing.append(match[1] + "==" + match[2])
if missing: sys.exit("依赖缺失或版本不匹配：" + ", ".join(missing))
'''
    result = subprocess.run([python, '-c', code, str(root / 'requirements.txt')], text=True, capture_output=True)
    if result.returncode:
        fail(result.stderr.strip() or '服务端环境检查失败')
    if not env.get('DATABASE_URL') or not env.get('JWT_SECRET'):
        fail('缺少配置项：DATABASE_URL 或 JWT_SECRET')
    return python


def process_identity(pid):
    result = subprocess.run(['ps', '-p', str(pid), '-o', 'stat=', '-o', 'lstart=', '-o', 'command='],
                            capture_output=True, text=True, check=False)
    line = result.stdout.strip()
    if result.returncode or not line or line.split()[0].startswith('Z'):
        return None
    return ' '.join(line.split()[1:])


def managed_process(pidfile):
    if not pidfile.exists():
        return None
    try:
        data = json.loads(pidfile.read_text())
        pid = data['pid']
        if not isinstance(pid, int) or pid <= 1 or not isinstance(data['identity'], str):
            raise ValueError()
        positive(str(data['port']), 'project.port', 65535)
    except (ValueError, KeyError, TypeError):
        fail(f'进程记录无效：{pidfile}')
    identity = process_identity(pid)
    if identity is None:
        return None
    if identity != data['identity'] or os.getpgid(pid) != pid:
        fail(f'进程 {pid} 与记录不匹配，拒绝操作')
    return data


def stop_local(pidfile):
    data = managed_process(pidfile)
    if data is None:
        pidfile.unlink(missing_ok=True)
        print('状态：未运行')
        return
    os.killpg(data['pid'], signal.SIGTERM)
    for _ in range(100):
        if process_identity(data['pid']) != data['identity']:
            pidfile.unlink(missing_ok=True)
            print(f"状态：已停止，端口：{data['port']}")
            return
        time.sleep(0.1)
    fail(f"进程 {data['pid']} 未能停止，请检查服务日志")


def launch(command, root, env, port, health, log, pidfile=None):
    with socket.socket() as sock:
        if sock.connect_ex(('127.0.0.1', int(port))) == 0:
            fail(f'端口 {port} 已被占用，请先停止占用该端口的服务')
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open('ab') as output:
        proc = subprocess.Popen(command, cwd=root, env=env, stdout=output, stderr=subprocess.STDOUT,
                                start_new_session=True, stdin=subprocess.DEVNULL)
    for _ in range(60):
        if proc.poll() is not None:
            fail(f'服务启动失败，请查看日志：{log}')
        try:
            request = Request(f'http://127.0.0.1:{port}{health}', method='POST' if health else 'GET')
            with urlopen(request, timeout=1) as response:
                ready = response.status == 200
                if ready and health:
                    try:
                        body = json.load(response)
                        ready = body.get('code') == 0 and body.get('data', {}).get('status') == 'ok'
                    except (ValueError, AttributeError):
                        ready = False
                if ready:
                    if pidfile:
                        identity = process_identity(proc.pid)
                        if not identity or proc.poll() is not None:
                            if proc.poll() is None:
                                os.killpg(proc.pid, signal.SIGTERM)
                            fail('无法确认启动进程的身份')
                        try:
                            pidfile.write_text(json.dumps({'pid': proc.pid, 'port': port, 'identity': identity}))
                        except OSError:
                            os.killpg(proc.pid, signal.SIGTERM)
                            proc.wait(timeout=5)
                            raise
                    print(f'部署成功，状态：运行中，端口：{port}，PID：{proc.pid}，日志：{log}')
                    return
                time.sleep(0.5)
        except OSError:
            time.sleep(0.5)
    os.killpg(proc.pid, signal.SIGTERM)
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        fail(f'服务未就绪且进程未退出，请查看日志：{log}')
    fail(f'服务未就绪，请查看日志：{log}')


def local_server(root, pidfile):
    module = root / 'zg-homework-server'
    config = properties(root / 'zg-homework-docs/config-dev/server-build.config', SERVER_KEYS)
    values = server_config(config, 'dev')
    venv = module / '.venv'
    if not venv.exists():
        interpreter = shutil.which('python3.12')
        if not interpreter:
            fail('缺少 Python 3.12，请先安装 Python 3.12')
        print('正在创建服务端虚拟环境...', flush=True)
        subprocess.run([interpreter, '-m', 'venv', str(venv)], check=True)
    if not (venv / 'bin/python').is_file():
        fail(f'服务端虚拟环境不可用：{venv}')
    try:
        check_server(module, values)
    except ValueError as exc:
        if not str(exc).startswith('依赖缺失或版本不匹配：'):
            raise
        print('正在安装服务端依赖...', flush=True)
        subprocess.run([str(venv / 'bin/python'), '-m', 'pip', 'install', '-r',
                        str(module / 'requirements.txt')], check=True)
    python = check_server(module, values)
    env = os.environ.copy()
    env.update(values)
    launch([python, '-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', config['project.port']],
           module, env, config['project.port'], '/homework_api/health', root / '.dev-logs/server.log', pidfile)
    print('健康检查不代表数据库可用或已初始化。')


def local_web(root, pidfile):
    module = root / 'zg-homework-web'
    config = properties(root / 'zg-homework-docs/config-dev/web-build.config', WEB_KEYS)
    api = web_config(config)
    if not shutil.which('node') or not shutil.which('npm'):
        fail('缺少 Node.js 或 npm')
    version = subprocess.check_output(['node', '--version'], text=True).strip()
    if not re.match(r'^v(\d+)', version) or int(version[1:].split('.')[0]) < 20:
        fail('需要 Node.js 20 或更高版本')
    if not (module / 'node_modules/.bin/vite').is_file():
        fail('缺少前端依赖，请先执行 npm --prefix zg-homework-web ci')
    env = os.environ.copy()
    env['VITE_API_BASE_URL'] = api
    subprocess.run(['npm', 'run', 'build'], cwd=module, env=env, check=True)
    launch([str(module / 'node_modules/.bin/vite'), 'preview', '--host', '127.0.0.1', '--port', config['project.port'], '--strictPort'],
           module, env, config['project.port'], '', root / '.dev-logs/web.log', pidfile)


def local_control(root, kind, args):
    if args == ['--help']:
        print('用法：deploy_local.sh {start|stop|status|restart}；默认 start')
        return
    if len(args) > 1 or (args and args[0] not in ('start', 'stop', 'statu', 'status', 'restart')):
        fail('用法：deploy_local.sh {start|stop|statu|status|restart}')
    operation = args[0] if args else 'start'
    directory = root / '.dev-logs'
    directory.mkdir(parents=True, exist_ok=True)
    pidfile = directory / (kind + '.pid')
    with (directory / (kind + '.lock')).open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if operation in ('statu', 'status'):
            data = managed_process(pidfile)
            if data:
                print(f"状态：运行中，端口：{data['port']}，PID：{data['pid']}")
            else:
                print('状态：未运行')
        elif operation == 'stop':
            stop_local(pidfile)
        else:
            if operation == 'restart':
                if kind == 'server':
                    config = properties(root / 'zg-homework-docs/config-dev/server-build.config', SERVER_KEYS)
                    server_config(config, 'dev')
                else:
                    config = properties(root / 'zg-homework-docs/config-dev/web-build.config', WEB_KEYS)
                    web_config(config)
                stop_local(pidfile)
            else:
                data = managed_process(pidfile)
                if data:
                    fail(f"服务已运行于端口 {data['port']}，请使用 restart 部署当前代码")
            (local_server if kind == 'server' else local_web)(root, pidfile)


def package(root, args):
    if len(args) != 1 or args[0] not in ('--dev', '--prod'):
        fail('用法：package_all.sh --dev|--prod')
    mode = args[0][2:]
    directory = root / 'zg-homework-docs' / ('config-' + mode)
    server = properties(directory / 'server-build.config', SERVER_KEYS)
    web = properties(directory / 'web-build.config', WEB_KEYS)
    values = server_config(server, mode)
    api = web_config(web)
    if mode == 'prod':
        if not Path(server['private.homework.dir']).is_absolute():
            fail('生产配置项 private.homework.dir 必须为持久化绝对路径')
        if 'xxx.com' in web['server.domain'].lower():
            fail('生产配置项 server.domain 不能使用占位域名')
    destination = root / 'zg-homework-tests/tar'
    destination.mkdir(parents=True, exist_ok=True)
    output = destination / ('zg-homework-' + datetime.now().strftime('%Y%m%d-%H%M%S') + '.tar.gz')
    with tempfile.TemporaryDirectory(prefix='zg-package-') as temp:
        stage = Path(temp)
        for name, script, extra in (('zg-homework-server', 'server_package.sh', []),
                                    ('zg-homework-web', 'web_package.sh', ['--source'])):
            module_archive = stage / (name + '.tar.gz')
            subprocess.run(['sh', str(root / name / 'scripts' / script), *extra,
                            '--output', str(module_archive)], check=True)
            with tarfile.open(module_archive, 'r:gz') as archive:
                for member in archive.getmembers():
                    parts = Path(member.name).parts
                    if not parts or parts[0] != name or '..' in parts or not (member.isfile() or member.isdir()):
                        fail('模块源码包包含不安全的路径或文件')
                archive.extractall(stage, filter='data')
        backend = stage / 'zg-homework-server'
        safe_values = {key: value for key, value in values.items() if key not in ('DATABASE_URL', 'JWT_SECRET')}
        (backend / '.env').write_text(dotenv(safe_values), encoding='utf-8')
        (backend / '.env').chmod(0o600)
        (backend / '.deploy-port').write_text(server['project.port'] + '\n')
        (stage / 'zg-homework-web/.env.production').write_text(dotenv({'VITE_API_BASE_URL': api}), encoding='utf-8')
        shutil.copy2(Path(__file__), backend / 'scripts/deploy_tool.py')
        for name, action in (('install_server.sh', 'install'), ('deploy_server.sh', 'deploy')):
            script = backend / name
            script.write_text('#!/bin/sh\nset -eu\nROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)\nexec python3 "$ROOT/scripts/deploy_tool.py" ' + action + ' "$ROOT"\n')
            script.chmod(0o755)
        fd, temporary = tempfile.mkstemp(prefix='.zg-package-', dir=destination)
        try:
            with os.fdopen(fd, 'wb') as raw:
                with tarfile.open(fileobj=raw, mode='w:gz') as archive:
                    for name in ('zg-homework-server', 'zg-homework-web'):
                        archive.add(stage / name, arcname=name)
                raw.flush()
                os.fsync(raw.fileno())
            os.link(temporary, output)
        finally:
            os.unlink(temporary)
    print(f'打包成功：{output}（数据库连接和 JWT 密钥须在目标机单独提供）')


def packaged(root, deploy):
    envfile = root / '.env'
    required = ('APP_NAME', 'ENV', 'JWT_ALGORITHM', 'JWT_EXPIRE_DAYS',
                'CORS_ORIGINS', 'PRIVATE_HOMEWORK_DIR', 'MAX_UPLOAD_MB', 'ALLOWED_EXTENSIONS')
    raw = properties(envfile, required)
    try:
        values = {key: json.loads(value) for key, value in raw.items()}
        if not all(isinstance(value, str) and value for value in values.values()):
            raise ValueError()
    except (ValueError, TypeError):
        fail('服务端 .env 配置格式错误')
    missing = [key for key in ('DATABASE_URL', 'JWT_SECRET') if not os.environ.get(key)]
    if missing:
        fail('缺少配置项：' + ', '.join(missing))
    values.update({key: os.environ[key] for key in ('DATABASE_URL', 'JWT_SECRET')})
    port_file = root / '.deploy-port'
    if not port_file.is_file() or not port_file.read_text().strip():
        fail('缺少配置项：服务端端口')
    port = port_file.read_text().strip()
    positive(port, 'project.port', 65535)
    positive(values['JWT_EXPIRE_DAYS'], 'JWT_EXPIRE_DAYS')
    positive(values['MAX_UPLOAD_MB'], 'MAX_UPLOAD_MB')
    if not values['DATABASE_URL'].startswith('mysql+pymysql://') or values['JWT_ALGORITHM'] not in ('HS256', 'HS384', 'HS512'):
        fail('数据库地址或 JWT 算法配置无效')
    python = check_server(root, values)
    print('服务端环境与配置检查通过', flush=True)
    if deploy:
        env = os.environ.copy()
        env.update(values)
        launch([python, '-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', port],
               root, env, port, '/homework_api/health', root / 'logs/server.log')
        print('健康检查不代表数据库可用或已初始化。')


if __name__ == '__main__':
    try:
        action, base, *arguments = sys.argv[1:]
        base = Path(base).resolve()
        if action == 'local-server': local_control(base, 'server', arguments)
        elif action == 'local-web': local_control(base, 'web', arguments)
        elif action == 'package': package(base, arguments)
        elif action in ('install', 'deploy'): packaged(base, action == 'deploy')
        else: fail('未知操作')
    except (OSError, ValueError, subprocess.SubprocessError, tarfile.TarError) as exc:
        print(f'执行失败：{exc}', file=sys.stderr)
        sys.exit(1)
