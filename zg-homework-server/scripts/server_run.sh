#!/usr/bin/env python3
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


def fail(message):
    raise RuntimeError(message)


def run(*args):
    try:
        return subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=15)
    except (OSError, subprocess.TimeoutExpired) as exc:
        fail(f'cannot execute {args[0]}: {exc}')


def properties():
    names = ['LoadState', 'ActiveState', 'SubState', 'WorkingDirectory', 'ExecStart',
             'ExecStartPre', 'ExecStartPost', 'ExecCondition', 'ExecStop', 'ExecStopPost',
             'Environment', 'EnvironmentFiles', 'RootDirectory', 'RootImage', 'Type',
             'MainPID', 'ControlGroup', 'KillMode', 'FragmentPath', 'NeedDaemonReload',
             'PassEnvironment', 'UnsetEnvironment', 'User', 'Group', 'PAMName']
    result = run('systemctl', 'show', UNIT, '--no-pager', *(f'--property={n}' for n in names))
    if result.returncode:
        fail('systemctl show failed; check systemd availability and permissions')
    values = dict(line.split('=', 1) for line in result.stdout.splitlines() if '=' in line)
    if any(n not in values for n in names):
        fail('systemd did not return all required properties')
    return values


def validate(p):
    if p['LoadState'] != 'loaded' or not p['FragmentPath'] or p['NeedDaemonReload'] != 'no':
        fail('unit is not loaded or needs daemon-reload')
    if p['WorkingDirectory'] != str(ROOT) or p['Type'] != 'simple' or p['KillMode'] != 'control-group':
        fail('unit working directory, Type or KillMode does not match the contract')
    if any(p[n] for n in ('ExecStartPre', 'ExecStartPost', 'ExecCondition', 'ExecStop', 'ExecStopPost', 'EnvironmentFiles', 'RootDirectory', 'RootImage')):
        fail('unit uses unsupported hooks, environment files or filesystem root')
    if p['Environment'] != 'PYTHONDONTWRITEBYTECODE=1' or p['PassEnvironment'] or p['UnsetEnvironment'] or p['PAMName']:
        fail('unit must set only PYTHONDONTWRITEBYTECODE=1 and not alter inherited environment or use PAM')
    manager = run('systemctl', 'show-environment')
    if manager.returncode:
        fail('cannot verify systemd manager environment')
    if any(line.startswith(('PYTHON', 'UVICORN_')) for line in manager.stdout.splitlines()):
        fail('systemd manager has unsupported PYTHON* or UVICORN_* variables')
    expected = f'{PYTHON} -m uvicorn app.main:app --host 127.0.0.1 --port {PORT} --workers 1'
    # systemctl show uses this structured format; reject extra commands and flags.
    pattern = r'^\{ path=(.*?) ; argv\[\]=(.*?) ; ignore_errors=no ; .* \}$'
    match = re.fullmatch(pattern, p['ExecStart'])
    if not match or match.group(1) != PYTHON or match.group(2) != expected:
        fail('unit ExecStart does not exactly match the required command')
    if p['ActiveState'] == 'active' and (not p['ControlGroup'].startswith('/') or '..' in p['ControlGroup'].split('/')):
        fail('unit control group cannot be verified')


def listeners():
    found = set()
    for name in ('tcp', 'tcp6'):
        try:
            lines = Path('/proc/net/' + name).read_text().splitlines()[1:]
        except OSError:
            fail('cannot inspect Linux TCP listeners')
        for line in lines:
            fields = line.split()
            if len(fields) >= 10 and fields[3] == '0A' and int(fields[1].split(':')[1], 16) == int(PORT):
                found.add(fields[9])
    return found


def active_owned(p):
    if p['ActiveState'] != 'active' or p['SubState'] != 'running':
        fail('unit is not in active/running state')
    try:
        pid = int(p['MainPID'])
        if pid <= 1:
            raise ValueError()
        proc = Path('/proc') / str(pid)
        cmd = proc.joinpath('cmdline').read_bytes().split(b'\0')
        expected = [PYTHON, '-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', PORT, '--workers', '1', '']
        if [os.fsdecode(x) for x in cmd] != expected or os.readlink(proc / 'cwd') != str(ROOT):
            fail('running main process does not match current source and command')
        groups = proc.joinpath('cgroup').read_text().splitlines()
        if not any(line.split(':', 2)[-1] == p['ControlGroup'] for line in groups):
            fail('running process is not in the unit control group')
        env = proc.joinpath('environ').read_bytes().split(b'\0')
        entries = [os.fsdecode(x) for x in env if x]
        if 'PYTHONDONTWRITEBYTECODE=1' not in entries or any(
            (x.startswith('PYTHON') and x != 'PYTHONDONTWRITEBYTECODE=1') or x.startswith('UVICORN_') for x in entries
        ):
            fail('running process has unsupported Python or Uvicorn environment')
        fds = {os.readlink(fd) for fd in proc.joinpath('fd').iterdir() if fd.exists()}
        owned = {x[8:-1] for x in fds if x.startswith('socket:[') and x.endswith(']')}
    except (OSError, ValueError) as exc:
        fail(f'cannot verify running process (permissions or process changed): {exc}')
    sockets = listeners()
    if not sockets or not sockets <= owned:
        fail('port is not exclusively held by the unit main process')


def runtime():
    if not Path(PYTHON).is_file() or not os.access(PYTHON, os.X_OK):
        fail('configured Python executable is unavailable')
    result = run(PYTHON, '-I', '-B', '-c', 'import sys, uvicorn; assert sys.version_info >= (3, 12)')
    if result.returncode:
        fail('Python 3.12+ and installed Uvicorn are required')
    manager = run('systemctl', 'show-environment')
    if manager.returncode:
        fail('cannot inspect manager environment for configuration checks')
    manager_env = dict(line.split('=', 1) for line in manager.stdout.splitlines() if '=' in line)
    if not (ROOT / '.env').is_file():
        fail('production configuration requires a module .env file')
    # Never print configuration values or Python exception text, which may contain secrets.
    code = '''
import os, sys
from pathlib import Path
from dotenv import dotenv_values
v = {k.upper(): value for k, value in dotenv_values(sys.argv[1]).items()}
v.update({k.upper(): value for k, value in os.environ.items()})
assert v.get("ENV", "").lower() in ("prod", "production")
assert v.get("DEBUG", "").lower() in ("false", "0", "no", "off")
assert v.get("DATABASE_URL", "").startswith("mysql+pymysql://")
assert v.get("JWT_SECRET") and v["JWT_SECRET"] != "change-me-in-production"
root = Path(sys.argv[1]).parent.parent.resolve()
for key in ("UPLOAD_DIR", "PRIVATE_HOMEWORK_DIR"):
    assert v.get(key) and Path(v[key]).is_absolute()
    path = Path(v[key]).resolve()
    assert path != root and root not in path.parents
'''
    try:
        config = subprocess.run([PYTHON, '-I', '-B', '-c', code, str(ROOT / '.env')],
                                env=manager_env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15)
    except (OSError, subprocess.TimeoutExpired):
        fail('could not inspect production configuration')
    if config.returncode:
        fail('production configuration requires ENV=prod, DEBUG=false, a MySQL DATABASE_URL, a non-default JWT_SECRET and absolute upload paths outside the checkout')
    app = ROOT / 'app'
    if app.is_symlink() or not app.is_dir():
        fail('app must be a real directory in the current checkout')
    for directory, dirs, files in os.walk(app, followlinks=False):
        for name in dirs + files:
            path = Path(directory) / name
            if path.is_symlink():
                fail('symlink in app prevents safe bytecode/source verification')
            if name.endswith(('.pyc', '.pyo')):
                fail('existing bytecode in app; have an operator inspect and remove it before startup')


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
            fail('unit is running but POST health check failed')
        print('health=ok (does not verify ongoing database connectivity)')
    elif listeners():
        fail('unit is not running and the port has a listener')
    else:
        print('port=free; service is not running')


def main():
    if len(sys.argv) != 2 or sys.argv[1] in ('help', '-h', '--help'):
        print('Usage: server_run.sh {check|status|start|stop|restart}\n'
              'Environment: SERVER_UNIT (default zg-homework-server.service), SERVER_PORT (8000), '
              'SERVER_PYTHON (module/.venv/bin/python). See README for the unit contract.')
        return 0 if len(sys.argv) == 2 and sys.argv[1] in ('help', '-h', '--help') else 2
    command = sys.argv[1]
    if command not in ('check', 'status', 'start', 'stop', 'restart'):
        fail('unknown command; use --help')
    if not re.fullmatch(r'[A-Za-z0-9_.@-]+\.service', UNIT):
        fail('invalid unit name')
    if not PORT.isascii() or not PORT.isdecimal() or not 1 <= int(PORT) <= 65535 or str(int(PORT)) != PORT:
        fail('invalid port')
    if not os.path.isabs(PYTHON) or not re.fullmatch(r'/[A-Za-z0-9_./-]+', PYTHON) or not re.fullmatch(r'/[A-Za-z0-9_./-]+', str(ROOT)):
        fail('Python and checkout paths must be absolute and contain only ASCII letters, digits, _, -, . and /')
    p = properties()
    validate(p)
    if command == 'status':
        state(p)
        return 0
    if command == 'check':
        runtime()
        state(p)
        print('runtime and unit contract verified')
        return 0
    if p['ActiveState'] not in ('active', 'inactive', 'failed'):
        fail('unit is transitioning; retry after it settles')
    if p['ActiveState'] == 'active':
        active_owned(p)
        if command == 'start':
            if not health():
                fail('already running but health check failed; use restart after investigation')
            print('already running and healthy; no action taken')
            return 0
    elif command == 'stop':
        print('already stopped; no action taken')
        return 0
    if command in ('start', 'restart'):
        runtime()
        if p['ActiveState'] != 'active' and listeners():
            fail('port is occupied; refusing to start')
        print('WARNING: application startup runs SQLAlchemy create_all against its configured database; no seeds or migrations are run.', flush=True)
    # Re-read before control to detect changes since inspection.
    again = properties()
    validate(again)
    if again != p:
        fail('unit state/configuration changed during verification; retry')
    result = run('systemctl', command, UNIT)
    if result.returncode:
        fail(f'systemctl {command} failed')
    if command == 'stop':
        if properties()['ActiveState'] != 'inactive':
            fail('unit did not reach inactive state')
        print('stopped')
        return 0
    deadline = time.monotonic() + TIMEOUT
    while time.monotonic() < deadline:
        current = properties()
        validate(current)
        if current['ActiveState'] in ('failed', 'inactive'):
            fail('unit stopped or failed during startup')
        if current['ActiveState'] == 'active' and current['SubState'] == 'running':
            try:
                active_owned(current)
                if health():
                    print('running; POST health=ok (not a database connectivity guarantee)')
                    return 0
            except RuntimeError:
                pass
        time.sleep(1)
    fail('startup timed out waiting for verified ownership and POST health')


if __name__ == '__main__':
    try:
        sys.exit(main())
    except RuntimeError as exc:
        print(f'error: {exc}', file=sys.stderr)
        if re.fullmatch(r'[A-Za-z0-9_.@-]+\.service', UNIT):
            print(f'Logs: journalctl -u {UNIT} -n 100 --no-pager', file=sys.stderr)
        sys.exit(1)
