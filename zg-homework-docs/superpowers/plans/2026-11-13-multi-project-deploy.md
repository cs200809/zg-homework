# 多项目共存的生产部署方案 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在生产机多项目共存（同域名 + 路径前缀）下，交付可用的安装与发布脚本，并让《生产部署打包方案.md》与项目实际完全对齐。

**Architecture:** 新增三个脚本——服务端 `install.sh`（渲染 systemd unit + 生成 env + 建数据目录）、前端 `install.sh`（生成共享 nginx 片段）、`web_deploy.sh`（从静态包或本机构建产物发布到 `releases/<版本>` 并原子切换 `current`）。既有 `server_run.sh` / `web_run.sh` / 两个打包脚本行为不变、契约测试零改动。前端默认走「静态包发布」模式，生产机不需要 Node。

**Tech Stack:** POSIX `sh` + 内嵌 Python 3（沿用 `server_run.sh` / `web_run.sh` 的 polyglot 风格）、Python `unittest`、systemd、nginx、Vite 6。

**Spec:** `zg-homework-docs/superpowers/specs/2026-11-13-multi-project-deploy-design.md`

## Global Constraints

以下约束对每个任务都生效：

- **端口**：后端固定 `127.0.0.1:8000`（可由 `--api-port` 覆盖）。多项目共存时端口与路径前缀都不得重复。
- **worker**：systemd `ExecStart` 必须是 `<python> -m uvicorn app.main:app --host 127.0.0.1 --port <port> --workers 1`。**永远单 worker**——成语接龙会话在进程内存（`app/routers/games.py` 的 `SessionStore`），多 worker 丢会话。
- **路径前缀**：前端 `/homework/`，API `/homework_api/`。`proxy_pass` **不带**末尾 `/`（服务端路由自带 `/homework_api` 前缀，带了会被剥掉导致 404）。`alias` **必须**带末尾 `/`。
- **环境文件**：唯一环境文件路径 `/etc/zg-homework-server/env`，权限 `0640`，属主 `root:<service-group>`。这是 `server_run.sh` 的强校验项。
- **env 值合法性**：值中不得出现 `'"\$`、控制字符、不可替换的 `__…__` 占位符（`server_run.sh` 的 `runtime()` 会直接拒绝）。
- **上传数据**：必须位于服务端检出目录之外，且 `UPLOAD_DIR` 与 `PRIVATE_HOMEWORK_DIR` 互不重叠（`server_run.sh` 强校验）。
- **nginx 写入边界**：任何脚本都**不得**写 `/etc/nginx/nginx.conf`、`/etc/nginx/sites-available/`、`/etc/nginx/sites-enabled/`。只允许写 `/etc/nginx/conf.d/zg-homework.conf`。片段内**只允许 `location` 块**。
- **reload 纪律**：任何 reload 前必须先 `nginx -t` 通过。
- **脚本语言**：服务端 `install.sh` 与 `web_deploy.sh` 用 `#!/bin/sh` + `'''exec' python3 "$0" "$@"` polyglot（内嵌 Python）；前端 `install.sh` 用纯 POSIX `sh`（`set -eu`，不用数组 / `[[ ]]` / 进程替换）。
- **`--root` 语义**：只映射「落地位置」——`--env-file`、`--unit-file`、`--snippet-file`、`--nginx-main-conf`、`--deploy-dir` 传**生产路径**（如 `/etc/zg-homework-server/env`、`/var/lib/zg-homework-web`），脚本内部拼上 `--root` 前缀落地。`--server-dir`、`--data-dir` 是**真实宿主路径**，不参与映射，且会原样写进 env。`--deploy-dir` 的值也原样出现在 nginx 片段的 `alias` 中（nginx 运行时用真实路径）。默认 `--root /` 即生产行为。
- **中文输出**：所有面向用户的提示与错误信息用中文，风格与既有脚本一致。
- **测试临时目录**：一律放仓库 `docs/` 下（既有约定，见 `zg-homework-tests/test_run_scripts.py` 的 `TEMP_DIR`）。
- **既有测试零改动**：`zg-homework-tests/test_run_scripts.py`、`test_production_contract.py`、`test_package_scripts.py` 不得修改。

---

## File Structure

| 文件 | 动作 | 职责 |
|---|---|---|
| `zg-homework-server/scripts/install.sh` | 新建 | 服务端安装：渲染 systemd unit、生成 env、建数据目录、建 venv、daemon-reload、enable |
| `zg-homework-web/scripts/install.sh` | 新建 | 前端安装：生成共享 nginx 片段、建发布目录、`nginx -t`、reload |
| `zg-homework-web/scripts/web_deploy.sh` | 新建 | 前端发布：模式 A 解包静态包 / 模式 B 本机构建 → `releases/<版本>` → 原子切 `current` → `nginx -t` → reload |
| `zg-homework-server/scripts/production.env.example` | 修改 | 修两处模板缺陷（`JWT_SECRET` 含单引号、`CORS_ORIGINS` 指向开发环境） |
| `zg-homework-server/scripts/server_package.sh` | 修改 | `FILES` 白名单加 `scripts/install.sh` |
| `zg-homework-tests/test_install_scripts.py` | 新建 | 服务端 + 前端 `install.sh` 的契约测试 |
| `zg-homework-tests/test_web_deploy.py` | 新建 | `web_deploy.sh` 的契约测试 |
| `zg-homework-docs/sys_doc/生产部署打包方案.md` | 重写 | 多项目共存版权威部署方案 |
| `CLAUDE.md` | 修改 | 同步脚本清单与生产部署一节 |

---

## Task 1: 修复模板缺陷 + 打包白名单

**Files:**
- Modify: `zg-homework-server/scripts/production.env.example`
- Modify: `zg-homework-server/scripts/server_package.sh:15-17`
- Test: `zg-homework-tests/test_install_scripts.py`（新建，本任务只写这一个测试类）

**Interfaces:**
- Consumes: 无
- Produces: `production.env.example` 中 `JWT_SECRET` 与 `CORS_ORIGINS` 的占位符形态 `__REPLACE_ME__`（供 Task 2 的 `install.sh` 识别并替换）；`server_package.sh` 打包白名单包含 `scripts/install.sh`（供 Task 2 的产物链路使用）。

- [ ] **Step 1: 写失败的测试**

新建 `zg-homework-tests/test_install_scripts.py`，本任务只放这一个测试类：

```python
"""服务端/前端安装脚本的契约测试；不触碰真实 /etc、/var 或 systemd。"""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
SERVER = REPO / 'zg-homework-server'
WEB = REPO / 'zg-homework-web'
DOCS = REPO / 'docs'


class TemplateTests(unittest.TestCase):
    def test_production_env_template_has_no_quote_or_dev_origin(self):
        text = (SERVER / 'scripts/production.env.example').read_text()
        values = dict(line.split('=', 1) for line in text.splitlines()
                      if line and not line.startswith('#') and '=' in line)
        for key in ('JWT_SECRET', 'CORS_ORIGINS'):
            with self.subTest(key=key):
                self.assertIn(key, values)
                self.assertNotIn("'", values[key])
                self.assertNotIn('"', values[key])
                self.assertNotIn('\\', values[key])
                self.assertFalse(values[key].startswith('http://localhost'))
                self.assertRegex(values[key], r'^__[A-Z0-9_]+__$')

    def test_server_package_includes_install_script(self):
        script = (SERVER / 'scripts/server_package.sh').read_text()
        self.assertIn("'scripts/install.sh'", script)
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python3 -m unittest zg-homework-tests.test_install_scripts` → 目录名含 `-` 不能作为包名，改用：

```bash
cd /Users/zg/PycharmProjects/zg-homework && python3 -m unittest discover -s zg-homework-tests -p test_install_scripts.py -v
```

Expected: FAIL —— `test_production_env_template_has_no_quote_or_dev_origin` 报 `JWT_SECRET` 仍是 `需要ti'huan`（含 `'` 且不匹配 `__…__`）；`test_server_package_includes_install_script` 报 `'scripts/install.sh' not found`。

- [ ] **Step 3: 修 `production.env.example`**

把这两行：

```
JWT_SECRET=需要ti'huan
```

```
CORS_ORIGINS=http://localhost:5173
```

改为：

```
# 生产环境务必修改；install.sh 会用 openssl rand -hex 32 生成并写入 /etc/zg-homework-server/env
JWT_SECRET=__REPLACE_ME__
```

```
# 同域反代部署时通常留空（由 install.sh --cors-origins 注入）；非空值不得含引号或反斜杠
CORS_ORIGINS=__REPLACE_ME__
```

`ENV=prod`、`DEBUG=false` 保持不变；其余键不动。

- [ ] **Step 4: 加打包白名单**

在 `zg-homework-server/scripts/server_package.sh` 的 `FILES` 元组中，把

```python
FILES = ('requirements.txt', '.env.example', 'Dockerfile', '.dockerignore',
         'README.md', 'scripts/server_run.sh', 'scripts/server_package.sh', 'scripts/init_check.sh',
         'scripts/production.env.example', 'scripts/zg-homework-server.service.example')
```

改为

```python
FILES = ('requirements.txt', '.env.example', 'Dockerfile', '.dockerignore',
         'README.md', 'scripts/server_run.sh', 'scripts/server_package.sh', 'scripts/install.sh',
         'scripts/init_check.sh', 'scripts/production.env.example',
         'scripts/zg-homework-server.service.example')
```

> 注意：`FILES` 里的每个路径都必须真实存在，否则 `require_regular()` 会抛 `不是普通文件`。本任务只加白名单，**不**创建 `install.sh`——Task 2 才创建。因此本任务末尾必须先创建 `install.sh` 的空壳，否则 `server_package.sh` 会开始失败。

- [ ] **Step 5: 创建 `install.sh` 空壳（保持打包可用）**

创建 `zg-homework-server/scripts/install.sh`：

```sh
#!/bin/sh
'''exec' python3 "$0" "$@"
' '''
"""安装服务端（占位实现，Task 2 填充）。"""
print('尚未实现')
raise SystemExit(1)
```

并 `chmod +x`。

> 空壳只需保证 `server_package.sh` 的白名单路径存在且是普通文件。Task 2 会整体替换本文件内容。

- [ ] **Step 6: 跑测试确认通过**

Run: `cd /Users/zg/PycharmProjects/zg-homework && python3 -m unittest discover -s zg-homework-tests -p test_install_scripts.py -v`

Expected: PASS —— 2 tests OK。

同时确认打包脚本仍可用：

Run: `cd /Users/zg/PycharmProjects/zg-homework && python3 zg-homework-tests/test_package_scripts.py 2>/dev/null || python3 -m unittest discover -s zg-homework-tests -p test_package_scripts.py -v`

Expected: 既有打包契约测试全部 PASS（`server_package.sh` 白名单变化不影响其断言）。

- [ ] **Step 7: 提交**

```bash
cd /Users/zg/PycharmProjects/zg-homework
git add zg-homework-server/scripts/production.env.example zg-homework-server/scripts/server_package.sh \
        zg-homework-server/scripts/install.sh zg-homework-tests/test_install_scripts.py
git commit -m "fix(server): 修正生产配置模板缺陷并把 install.sh 纳入打包白名单"
```

---

## Task 2: 服务端 `install.sh`

**Files:**
- Create: `zg-homework-server/scripts/install.sh`（覆盖 Task 1 的空壳）
- Modify: `zg-homework-tests/test_install_scripts.py`（追加 `ServerInstallTests`）
- Read-only 参考: `zg-homework-server/scripts/zg-homework-server.service.example`、`zg-homework-server/scripts/server_run.sh`（`validate()` / `runtime()` 的契约）

**Interfaces:**
- Consumes: Task 1 产出的 `production.env.example`（含 `__REPLACE_ME__` 占位符）、`zg-homework-server.service.example`（含 `__SERVER_MODULE_DIR__`、`__SERVER_PYTHON__`、`__SERVICE_USER__`、`__SERVICE_GROUP__`、`__SERVER_PORT__` 占位符）
- Produces: 命令行接口
  ```
  install.sh [--server-dir DIR] [--api-port N] [--service-user U] [--service-group G]
             [--env-owner user:group] [--database-url URL] [--jwt-secret S]
             [--cors-origins LIST] [--data-dir DIR] [--env-file PATH] [--unit-file PATH]
             [--root PREFIX] [--skip-venv] [--no-start] [--force-env] [--help]
  ```
  退出码：0 成功；2 参数错误；1 其它失败。Task 4 的 `web_deploy.sh` 与本任务无耦合。

- [ ] **Step 1: 写失败的测试**

在 `zg-homework-tests/test_install_scripts.py` 末尾追加：

```python
class ServerInstallTests(unittest.TestCase):
    def setUp(self):
        DOCS.mkdir(exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(prefix='install-server-', dir=DOCS)
        self.addCleanup(self.tmp.cleanup)
        self.work = Path(self.tmp.name)
        self.root = self.work / 'root'
        self.root.mkdir()
        self.server = self.work / 'server'
        (self.server / 'app').mkdir(parents=True)
        (self.server / 'app/main.py').write_text('')
        self.server.mkdir(exist_ok=True)
        shutil.copytree(SERVER / 'scripts', self.server / 'scripts')
        (self.server / 'requirements.txt').write_text('')
        self.bin = self.work / 'bin'
        self.bin.mkdir()
        self.log = self.work / 'calls.log'
        self.fake('systemctl', '#!/bin/sh\necho "systemctl $*" >> "$TEST_LOG"\nexit 0\n')
        self.fake('openssl', '#!/bin/sh\necho "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"\n')
        self.env = {**os.environ, 'PATH': str(self.bin) + os.pathsep + os.environ.get('PATH', ''),
                    'TEST_LOG': str(self.log)}

    def fake(self, name, body, directory=None):
        path = (directory or self.bin) / name
        path.write_text(body)
        path.chmod(0o755)

    def run_install(self, *args, expect=0):
        user = os.environ.get('USER', 'root')
        group = subprocess.run(['id', '-gn'], capture_output=True, text=True).stdout.strip() or 'root'
        command = ['sh', str(self.server / 'scripts/install.sh'),
                   '--root', str(self.root),
                   '--server-dir', str(self.server),
                   '--data-dir', str(self.work / 'data'),
                   '--env-file', '/etc/zg-homework-server/env',
                   '--unit-file', '/etc/systemd/system/zg-homework-server.service',
                   '--database-url', 'mysql+pymysql://u:p@127.0.0.1:3306/db?charset=utf8mb4',
                   '--service-user', user,
                   '--service-group', group,
                   '--env-owner', f'{user}:{group}',
                   '--skip-venv'] + list(args)
        result = subprocess.run(command, env=self.env, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, expect, result.stderr or result.stdout)
        return result

    def unit_text(self):
        return (self.root / 'etc/systemd/system/zg-homework-server.service').read_text()

    def env_text(self):
        return (self.root / 'etc/zg-homework-server/env').read_text()

    def test_unit_is_rendered_without_placeholders(self):
        self.run_install()
        text = self.unit_text()
        self.assertNotIn('__', text)
        self.assertIn('Type=simple', text)
        self.assertIn('KillMode=control-group', text)
        self.assertIn('EnvironmentFile=/etc/zg-homework-server/env', text)
        self.assertIn(f'WorkingDirectory={self.server}', text)
        self.assertIn(
            f'ExecStart={self.server}/.venv/bin/python -m uvicorn app.main:app '
            '--host 127.0.0.1 --port 8000 --workers 1', text)
        self.assertEqual(
            [line for line in text.splitlines() if line.startswith('Environment=')],
            ['Environment=PYTHONDONTWRITEBYTECODE=1',
             'Environment=ZG_HOMEWORK_SYSTEMD_PRODUCTION=1'])

    def test_env_is_written_with_valid_values_and_permissions(self):
        self.run_install()
        values = dict(line.split('=', 1) for line in self.env_text().splitlines()
                      if line and not line.startswith('#'))
        self.assertEqual(values['ENV'], 'prod')
        self.assertEqual(values['DEBUG'], 'false')
        self.assertTrue(values['DATABASE_URL'].startswith('mysql+pymysql://'))
        self.assertEqual(len(values['JWT_SECRET']), 64)
        self.assertNotIn('__', values['JWT_SECRET'])
        self.assertTrue(values['UPLOAD_DIR'].startswith(str(self.work / 'data')))
        self.assertTrue(values['PRIVATE_HOMEWORK_DIR'].startswith(str(self.work / 'data')))
        mode = (self.root / 'etc/zg-homework-server/env').stat().st_mode & 0o777
        self.assertEqual(mode, 0o640)

    def test_data_directories_are_created(self):
        self.run_install()
        self.assertTrue((self.work / 'data/uploads').is_dir())
        self.assertTrue((self.work / 'data/private_homework').is_dir())

    def test_invalid_arguments_are_rejected_without_writing_files(self):
        cases = [
            (['--api-port', '0'], '端口'),
            (['--api-port', '70000'], '端口'),
            (['--database-url', 'postgresql://x/y'], 'mysql+pymysql'),
            (['--data-dir', str(self.server / 'uploads')], '检出目录'),
        ]
        for extra, expected in cases:
            with self.subTest(extra=extra):
                result = self.run_install(*extra, expect=1)
                self.assertIn(expected, result.stderr)
        self.assertFalse((self.root / 'etc/systemd/system/zg-homework-server.service').exists())

    def test_missing_database_url_is_rejected(self):
        command = ['sh', str(self.server / 'scripts/install.sh'), '--root', str(self.root),
                   '--server-dir', str(self.server), '--skip-venv']
        result = subprocess.run(command, env=self.env, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 2)
        self.assertIn('database-url', result.stderr)

    def test_rerun_keeps_existing_jwt_secret(self):
        self.run_install()
        original = dict(line.split('=', 1) for line in self.env_text().splitlines() if '=' in line)
        self.run_install()
        updated = dict(line.split('=', 1) for line in self.env_text().splitlines() if '=' in line)
        self.assertEqual(updated['JWT_SECRET'], original['JWT_SECRET'])

    def test_secret_is_not_echoed_to_stdout(self):
        result = self.run_install('--jwt-secret', 'topsecretvalue0123456789')
        self.assertNotIn('topsecretvalue0123456789', result.stdout)
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd /Users/zg/PycharmProjects/zg-homework && python3 -m unittest discover -s zg-homework-tests -p test_install_scripts.py -v`

Expected: FAIL —— `ServerInstallTests` 全部失败（`install.sh` 仍是 Task 1 的空壳，退出码 1，stdout 含「尚未实现」）。

- [ ] **Step 3: 实现 `install.sh`**

整体替换 `zg-homework-server/scripts/install.sh`：

```sh
#!/bin/sh
'''exec' python3 "$0" "$@"
' '''
"""安装服务端：渲染 systemd 单元、生成生产配置、建立数据目录。"""
import argparse
import os
from pathlib import Path
import pwd
import grp
import re
import secrets
import shutil
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
        'show this help message and exit': '显示此帮助信息并退出',
        '%(prog)s: error: %(message)s\n': '%(prog)s：错误：%(message)s\n',
    }.get(message, message)


argparse._ = translate
parser = argparse.ArgumentParser(description='安装 zg-homework 服务端：渲染 systemd 单元、生成生产配置、建立数据目录。')
parser.add_argument('--server-dir', default='/data/apps/zg-homework-server', help='服务端代码检出目录')
parser.add_argument('--api-port', default='8000', help='后端监听端口（仅 127.0.0.1）')
parser.add_argument('--service-user', default='www-data', help='systemd 运行用户')
parser.add_argument('--service-group', default='www-data', help='systemd 运行组')
parser.add_argument('--env-owner', default=None, help='env 文件属主 user:group（默认 root:<service-group>）')
parser.add_argument('--database-url', help='mysql+pymysql://…?charset=utf8mb4')
parser.add_argument('--jwt-secret', help='JWT 密钥；不给则随机生成 32 字节 hex')
parser.add_argument('--cors-origins', default='', help='允许的来源，逗号分隔；同域反代通常留空')
parser.add_argument('--data-dir', default='/var/lib/zg-homework', help='上传数据根目录')
parser.add_argument('--env-file', default='/etc/zg-homework-server/env', help='生产配置路径')
parser.add_argument('--unit-file', default='/etc/systemd/system/' + UNIT_NAME, help='systemd 单元路径')
parser.add_argument('--root', default='/', help='根前缀；用于沙箱测试，默认 /')
parser.add_argument('--skip-venv', action='store_true', help='跳过虚拟环境创建')
parser.add_argument('--no-start', action='store_true', help='安装后不启动服务')
parser.add_argument('--force-env', action='store_true', help='覆盖已存在的生产配置')
parser.add_argument('--help', action='store_true')
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


def build_env(server_dir, data_dir, jwt_secret):
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
        'CORS_ORIGINS': args.cors_origins,
    })
    for key in ('DATABASE_URL', 'JWT_SECRET', 'UPLOAD_DIR', 'PRIVATE_HOMEWORK_DIR', 'CORS_ORIGINS'):
        check_value(key, values[key])
    return ''.join(f'{key}={values[key]}\n' for key in sorted(values))


def random_secret():
    return secrets.token_hex(32)


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

    unit_path.parent.mkdir(parents=True, exist_ok=True)
    unit_path.write_text(render_unit(server_dir, python, args.service_user,
                                     args.service_group, args.api_port), encoding='utf-8')
    unit_path.chmod(0o644)

    existing = {}
    if env_path.is_file() and not args.force_env:
        for line in env_path.read_text(encoding='utf-8').splitlines():
            if line and not line.startswith('#') and '=' in line:
                key, _, value = line.partition('=')
                existing[key] = value
    jwt = args.jwt_secret or existing.get('JWT_SECRET') or random_secret()
    env_path.parent.mkdir(parents=True, exist_ok=True)
    env_path.write_text(build_env(server_dir, data_dir, jwt), encoding='utf-8')
    env_path.chmod(0o640)
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

    subprocess.run(['systemctl', 'daemon-reload'], check=True)
    if not args.no_start:
        subprocess.run(['systemctl', 'enable', '--now', UNIT_NAME], check=True)

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
except subprocess.CalledProcessError as exc:
    print(f'错误：命令执行失败（{exc.cmd}）', file=sys.stderr)
    sys.exit(1)
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd /Users/zg/PycharmProjects/zg-homework && python3 -m unittest discover -s zg-homework-tests -p test_install_scripts.py -v`

Expected: PASS —— `TemplateTests` 2 项 + `ServerInstallTests` 7 项，共 9 tests OK。

若 `test_invalid_arguments_are_rejected_without_writing_files` 失败，检查错误信息里是否含关键字 `端口` / `mysql+pymysql` / `检出目录`——措辞可调整，但关键字必须出现。

- [ ] **Step 5: 手工验证渲染出的单元与 env**

```bash
cd /Users/zg/PycharmProjects/zg-homework
rm -rf /tmp/inst && mkdir -p /tmp/inst/root
python3 - <<'PY'
import subprocess, pathlib
work = pathlib.Path('/tmp/inst')
result = subprocess.run(['sh', 'zg-homework-server/scripts/install.sh',
    '--root', str(work / 'root'), '--server-dir', str(pathlib.Path('zg-homework-server').resolve()),
    '--data-dir', str(work / 'data'), '--skip-venv', '--no-start',
    '--database-url', 'mysql+pymysql://u:p@127.0.0.1:3306/db?charset=utf8mb4'],
    capture_output=True, text=True)
print(result.returncode, result.stdout, result.stderr)
PY
cat /tmp/inst/root/etc/systemd/system/zg-homework-server.service
cat /tmp/inst/root/etc/zg-homework-server/env
```

Expected: 单元与 env 打印如设计；env 中无 `__…__`、无引号。

- [ ] **Step 6: 提交**

```bash
cd /Users/zg/PycharmProjects/zg-homework
git add zg-homework-server/scripts/install.sh zg-homework-tests/test_install_scripts.py
git commit -m "feat(server): 新增 install.sh，渲染 systemd 单元与生产配置并建立数据目录"
```

---

## Task 3: 前端 `install.sh`（共享 nginx 片段）

**Files:**
- Create: `zg-homework-web/scripts/install.sh`
- Modify: `zg-homework-tests/test_install_scripts.py`（追加 `WebInstallTests`）
- Read-only 参考: `zg-homework-web/scripts/web_run.sh`（`expected_config()` 的片段形态）、`zg-homework-web/nginx.conf`

**Interfaces:**
- Consumes: 无
- Produces: 命令行接口
  ```
  install.sh [--web-prefix P] [--api-prefix P] [--api-upstream 127.0.0.1:PORT]
             [--deploy-dir DIR] [--snippet-file PATH] [--nginx-bin PATH]
             [--nginx-main-conf PATH] [--root PREFIX] [--no-reload] [--print-only] [--help]
  ```
  退出码：0 成功；2 参数错误；1 其它失败。片段路径默认 `/etc/nginx/conf.d/zg-homework.conf`。

- [ ] **Step 1: 写失败的测试**

在 `zg-homework-tests/test_install_scripts.py` 追加：

```python
class WebInstallTests(unittest.TestCase):
    def setUp(self):
        DOCS.mkdir(exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(prefix='install-web-', dir=DOCS)
        self.addCleanup(self.tmp.cleanup)
        self.work = Path(self.tmp.name)
        self.root = self.work / 'root'
        self.root.mkdir()
        self.snippet = self.root / 'etc/nginx/conf.d/zg-homework.conf'
        self.main_conf = self.root / 'etc/nginx/nginx.conf'
        self.main_conf.parent.mkdir(parents=True)
        self.main_conf.write_text('http { include /etc/nginx/conf.d/*.conf; }\n')
        self.bin = self.work / 'bin'
        self.bin.mkdir()
        self.log = self.work / 'calls.log'
        self.fake('nginx', '#!/bin/sh\necho "nginx $*" >> "$TEST_LOG"\nexit "${TEST_NGINX_EXIT:-0}"\n')
        self.fake('systemctl', '#!/bin/sh\necho "systemctl $*" >> "$TEST_LOG"\nexit 0\n')
        self.env = {**os.environ, 'PATH': str(self.bin) + os.pathsep + os.environ.get('PATH', ''),
                    'TEST_LOG': str(self.log)}

    def fake(self, name, body):
        path = self.bin / name
        path.write_text(body)
        path.chmod(0o755)

    def run_install(self, *args, expect=0):
        command = ['sh', str(WEB / 'scripts/install.sh'),
                   '--root', str(self.root),
                   '--deploy-dir', str(self.work / 'deploy'),
                   '--snippet-file', str(self.snippet),
                   '--nginx-main-conf', str(self.main_conf)] + list(args)
        result = subprocess.run(command, env=self.env, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, expect, result.stderr or result.stdout)
        return result

    def test_snippet_contains_only_location_blocks(self):
        self.run_install()
        text = self.snippet.read_text()
        self.assertNotIn('server {', text)
        self.assertNotIn('events {', text)
        self.assertIn('location /homework/ {', text)
        self.assertIn('location /homework_api/ {', text)
        self.assertIn('alias /var/lib/zg-homework-web/current/;', text)
        self.assertIn('proxy_pass http://127.0.0.1:8000;', text)
        self.assertNotIn('proxy_pass http://127.0.0.1:8000/;', text)
        self.assertIn('try_files $uri $uri/ /homework/index.html;', text)

    def test_deploy_directory_is_created(self):
        self.run_install()
        self.assertTrue((self.root / 'var/lib/zg-homework-web/releases').is_dir())

    def test_print_only_writes_nothing(self):
        result = self.run_install('--print-only')
        self.assertIn('location /homework/ {', result.stdout)
        self.assertFalse(self.snippet.exists())

    def test_invalid_prefix_is_rejected(self):
        for prefix in ('homework', '/homework'):
            with self.subTest(prefix=prefix):
                result = self.run_install('--web-prefix', prefix, expect=1)
                self.assertIn('前缀', result.stderr)

    def test_invalid_upstream_is_rejected(self):
        result = self.run_install('--api-upstream', 'example.com:8000', expect=1)
        self.assertIn('上游', result.stderr)

    def test_nginx_syntax_failure_keeps_previous_snippet(self):
        self.run_install()
        original = self.snippet.read_text()
        result = self.run_install('--web-prefix', '/other', expect=1,
                                  env={'TEST_NGINX_EXIT': '1'})
        self.assertIn('nginx', result.stderr)
        self.assertEqual(self.snippet.read_text(), original)

    def test_rerun_is_idempotent(self):
        self.run_install()
        first = self.snippet.read_text()
        self.run_install()
        self.assertEqual(self.snippet.read_text(), first)
```

> `run_install` 需要支持传入环境变量覆盖：把签名改为 `def run_install(self, *args, expect=0, env=None)`，并把 `env` 合并进 `self.env`：

```python
    def run_install(self, *args, expect=0, env=None):
        command = ['sh', str(WEB / 'scripts/install.sh'),
                   '--root', str(self.root),
                   '--deploy-dir', '/var/lib/zg-homework-web',
                   '--snippet-file', '/etc/nginx/conf.d/zg-homework.conf',
                   '--nginx-main-conf', '/etc/nginx/nginx.conf'] + list(args)
        merged = {**self.env, **(env or {})}
        result = subprocess.run(command, env=merged, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, expect, result.stderr or result.stdout)
        return result
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd /Users/zg/PycharmProjects/zg-homework && python3 -m unittest discover -s zg-homework-tests -p test_install_scripts.py -v`

Expected: FAIL —— `WebInstallTests` 全部失败（`zg-homework-web/scripts/install.sh` 不存在，`sh` 报 `No such file or directory`，退出码 127 ≠ 0）。

- [ ] **Step 3: 实现前端 `install.sh`**

创建 `zg-homework-web/scripts/install.sh`：

```sh
#!/bin/sh
# 在共享 nginx 下安装本项目的前端片段与发布目录。
set -eu

ROOT_PREFIX=/
WEB_PREFIX=/homework
API_PREFIX=/homework_api
API_UPSTREAM=127.0.0.1:8000
DEPLOY_DIR=/var/lib/zg-homework-web
SNIPPET_FILE=/etc/nginx/conf.d/zg-homework.conf
NGINX_BIN=nginx
NGINX_MAIN_CONF=/etc/nginx/nginx.conf
NO_RELOAD=0
PRINT_ONLY=0

usage() {
    printf '%s\n' \
        '用法：sh scripts/install.sh [选项]' \
        '  --web-prefix PREFIX      前端路径前缀（默认 /homework）' \
        '  --api-prefix PREFIX      后端路径前缀（默认 /homework_api）' \
        '  --api-upstream HOST:PORT 后端上游（默认 127.0.0.1:8000）' \
        '  --deploy-dir DIR         前端产物根目录（默认 /var/lib/zg-homework-web）' \
        '  --snippet-file PATH      nginx 片段路径（默认 /etc/nginx/conf.d/zg-homework.conf）' \
        '  --nginx-bin PATH         nginx 可执行文件（默认 nginx）' \
        '  --nginx-main-conf PATH   主配置路径（默认 /etc/nginx/nginx.conf）' \
        '  --root PREFIX            根前缀，用于沙箱测试（默认 /）' \
        '  --no-reload              不 reload nginx' \
        '  --print-only             只打印片段内容，不写文件' \
        '  --help                   显示帮助'
}

fail() {
    printf '错误：%s\n' "$1" >&2
    exit 1
}

while [ "$#" -gt 0 ]; do
    case "$1" in
        --web-prefix) WEB_PREFIX=${2:?缺少 --web-prefix 的值}; shift 2 ;;
        --api-prefix) API_PREFIX=${2:?缺少 --api-prefix 的值}; shift 2 ;;
        --api-upstream) API_UPSTREAM=${2:?缺少 --api-upstream 的值}; shift 2 ;;
        --deploy-dir) DEPLOY_DIR=${2:?缺少 --deploy-dir 的值}; shift 2 ;;
        --snippet-file) SNIPPET_FILE=${2:?缺少 --snippet-file 的值}; shift 2 ;;
        --nginx-bin) NGINX_BIN=${2:?缺少 --nginx-bin 的值}; shift 2 ;;
        --nginx-main-conf) NGINX_MAIN_CONF=${2:?缺少 --nginx-main-conf 的值}; shift 2 ;;
        --root) ROOT_PREFIX=${2:?缺少 --root 的值}; shift 2 ;;
        --no-reload) NO_RELOAD=1; shift ;;
        --print-only) PRINT_ONLY=1; shift ;;
        --help|-h) usage; exit 0 ;;
        *) printf '错误：不支持的参数：%s\n' "$1" >&2; usage >&2; exit 2 ;;
    esac
done

case "$WEB_PREFIX" in
    /*/) ;;
    *) fail "--web-prefix 必须以 / 开头并以 / 结尾" ;;
esac
case "$API_PREFIX" in
    /*/) ;;
    *) fail "--api-prefix 必须以 / 开头并以 / 结尾" ;;
esac
case "$API_UPSTREAM" in
    127.0.0.1:*)
        PORT=${API_UPSTREAM#127.0.0.1:}
        case "$PORT" in
            ''|*[!0-9]*) fail "--api-upstream 的端口无效" ;;
        esac
        [ "$PORT" -ge 1 ] && [ "$PORT" -le 65535 ] || fail "--api-upstream 的端口无效"
        ;;
    *) fail "--api-upstream 必须是 127.0.0.1:PORT" ;;
esac

TARGET_SNIPPET=$ROOT_PREFIX/${SNIPPET_FILE#/}
TARGET_MAIN_CONF=$ROOT_PREFIX/${NGINX_MAIN_CONF#/}
TARGET_DEPLOY=$ROOT_PREFIX/${DEPLOY_DIR#/}

SNIPPET=$(cat <<EOF
# 由 zg-homework-web/scripts/install.sh 生成，请勿手工编辑。
# 同域名多项目共存：本项目独占 ${WEB_PREFIX} 与 ${API_PREFIX} 两个前缀。
# 本片段只含 location 块；server 块与 TLS 证书由运维统一维护。

location ${WEB_PREFIX} {
    alias ${DEPLOY_DIR}/current/;
    index index.html;
    try_files \$uri \$uri/ ${WEB_PREFIX}index.html;
}

location ${API_PREFIX} {
    proxy_pass http://${API_UPSTREAM};
    proxy_http_version 1.1;
    proxy_set_header Host \$host;
    proxy_set_header X-Real-IP \$remote_addr;
    proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto \$scheme;
    client_max_body_size 12m;
    proxy_read_timeout 60s;
}
EOF
)

if [ "$PRINT_ONLY" -eq 1 ]; then
    printf '%s\n' "$SNIPPET"
    exit 0
fi

mkdir -p "$(dirname "$TARGET_SNIPPET")"
mkdir -p "$TARGET_DEPLOY/releases"

if [ -f "$TARGET_SNIPPET" ] && [ "$(cat "$TARGET_SNIPPET")" = "$SNIPPET" ]; then
    printf '%s\n' "片段未变化，跳过写入：$TARGET_SNIPPET"
    exit 0
fi

BACKUP=''
if [ -f "$TARGET_SNIPPET" ]; then
    BACKUP=$TARGET_SNIPPET.bak
    cp "$TARGET_SNIPPET" "$BACKUP"
fi

printf '%s\n' "$SNIPPET" > "$TARGET_SNIPPET"
chmod 644 "$TARGET_SNIPPET"

if ! "$NGINX_BIN" -t -c "$TARGET_MAIN_CONF"; then
    if [ -n "$BACKUP" ] && [ -f "$BACKUP" ]; then
        mv "$BACKUP" "$TARGET_SNIPPET"
    else
        rm -f "$TARGET_SNIPPET"
    fi
    fail "nginx 配置校验失败，已恢复原片段"
fi
rm -f "$BACKUP"

if ! grep -q 'include[^;]*conf\.d' "$TARGET_MAIN_CONF"; then
    printf '%s\n' "警告：主配置未 include conf.d 目录，片段不会生效" >&2
fi

if [ "$NO_RELOAD" -eq 0 ]; then
    if command -v systemctl >/dev/null 2>&1; then
        systemctl reload nginx
    else
        "$NGINX_BIN" -s reload
    fi
fi

printf '%s\n' "前端片段已安装：$TARGET_SNIPPET" "发布目录：$TARGET_DEPLOY/releases"
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd /Users/zg/PycharmProjects/zg-homework && python3 -m unittest discover -s zg-homework-tests -p test_install_scripts.py -v`

Expected: PASS —— 共 16 tests OK（2 模板 + 7 服务端 + 7 前端）。

若 `test_nginx_syntax_failure_keeps_previous_snippet` 失败，检查失败分支是否先 `mv` 回备份再 `fail`。

- [ ] **Step 5: 提交**

```bash
cd /Users/zg/PycharmProjects/zg-homework
git add zg-homework-web/scripts/install.sh zg-homework-tests/test_install_scripts.py
git commit -m "feat(web): 新增 install.sh，生成共享 nginx 片段与发布目录"
```

---

## Task 4: `web_deploy.sh`（前端发布）

**Files:**
- Create: `zg-homework-web/scripts/web_deploy.sh`
- Modify: `zg-homework-tests/test_package_scripts.py`（**不改逻辑**，仅当需要登记新脚本时——默认不改）
- Test: `zg-homework-tests/test_web_deploy.py`（新建）

**Interfaces:**
- Consumes: `web_package.sh` 产出的静态包（顶层目录 `zg-homework-web-static/`，内含 `index.html` 与 `assets/`）
- Produces: 命令行接口
  ```
  web_deploy.sh (--package FILE | --build) [--deploy-dir DIR] [--nginx-bin PATH]
               [--nginx-main-conf PATH] [--no-reload] [--source-dir DIR] [--help]
  ```
  发布后 `<deploy-dir>/current` 指向 `<deploy-dir>/releases/web-<时间戳>-<hash>`，目录内含 `index.html` 与 `.web-run-owner`。

- [ ] **Step 1: 写失败的测试**

新建 `zg-homework-tests/test_web_deploy.py`：

```python
"""web_deploy.sh 的契约测试；不触碰真实 nginx、/var 或 systemd。"""
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
WEB = REPO / 'zg-homework-web'
SCRIPT = WEB / 'scripts/web_deploy.sh'
DOCS = REPO / 'docs'


def make_package(path, entries):
    with tarfile.open(path, 'w:gz') as archive:
        for name, payload in entries.items():
            data = payload.encode()
            info = tarfile.TarInfo('zg-homework-web-static/' + name)
            info.size = len(data)
            info.mtime = 1700000000
            archive.addfile(info, io.BytesIO(data))


class WebDeployTests(unittest.TestCase):
    def setUp(self):
        DOCS.mkdir(exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(prefix='web-deploy-', dir=DOCS)
        self.addCleanup(self.tmp.cleanup)
        self.work = Path(self.tmp.name)
        self.deploy = self.work / 'deploy'
        (self.deploy / 'releases').mkdir(parents=True)
        self.package = self.work / 'static.tar.gz'
        make_package(self.package, {'index.html': '<html>ok</html>',
                                    'assets/app.js': 'console.log(1)'})
        self.bin = self.work / 'bin'
        self.bin.mkdir()
        self.log = self.work / 'calls.log'
        self.write_fake('nginx', '#!/bin/sh\necho "nginx $*" >> "$TEST_LOG"\nexit "${TEST_NGINX_EXIT:-0}"\n')
        self.write_fake('systemctl', '#!/bin/sh\necho "systemctl $*" >> "$TEST_LOG"\nexit 0\n')
        self.write_fake('node', '#!/bin/sh\nprintf "v20.11.0\\n"\n')
        self.write_fake('tsc', '#!/bin/sh\necho "tsc $*" >> "$TEST_LOG"\nexit "${TEST_TSC_EXIT:-0}"\n',
                        self.work / 'node_modules/.bin')
        self.write_fake('vite', '#!/bin/sh\necho "vite $*" >> "$TEST_LOG"\n'
                               'while [ "$1" != "--outDir" ]; do shift; done\n'
                               'mkdir -p "$2/assets"; printf "<html>built</html>" > "$2/index.html"\n',
                        self.work / 'node_modules/.bin')
        self.source = self.work / 'source'
        (self.source / 'scripts').mkdir(parents=True)
        (self.source / 'node_modules/.bin').mkdir(parents=True)
        self.env = {**os.environ, 'PATH': str(self.bin) + os.pathsep + os.environ.get('PATH', ''),
                    'TEST_LOG': str(self.log)}

    def write_fake(self, name, body, directory=None):
        path = (directory or self.bin) / name
        path.write_text(body)
        path.chmod(0o755)

    def run_deploy(self, *args, expect=0, env=None):
        command = ['sh', str(SCRIPT), '--deploy-dir', str(self.deploy),
                   '--nginx-main-conf', str(self.work / 'nginx.conf')] + list(args)
        merged = {**self.env, **(env or {})}
        result = subprocess.run(command, env=merged, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, expect, result.stderr or result.stdout)
        return result

    def calls(self):
        return self.log.read_text() if self.log.exists() else ''

    def test_package_release_switches_current_and_reloads(self):
        self.run_deploy('--package', str(self.package))
        current = (self.deploy / 'current').resolve()
        self.assertTrue((current / 'index.html').is_file())
        self.assertTrue((current / '.web-run-owner').is_file())
        self.assertIn('systemctl reload nginx', self.calls())

    def test_invalid_package_is_rejected(self):
        bad = self.work / 'bad.tar.gz'
        with tarfile.open(bad, 'w:gz') as archive:
            info = tarfile.TarInfo('index.html')
            info.size = 0
            archive.addfile(info, io.BytesIO(b''))
        self.run_deploy('--package', str(bad), expect=1)
        self.assertFalse((self.deploy / 'current').exists())
        self.assertNotIn('systemctl reload nginx', self.calls())

    def test_nginx_test_failure_keeps_current(self):
        self.run_deploy('--package', str(self.package))
        before = (self.deploy / 'current').resolve()
        self.run_deploy('--package', str(self.package), expect=1,
                        env={'TEST_NGINX_EXIT': '1'})
        self.assertEqual((self.deploy / 'current').resolve(), before)

    def test_package_release_needs_no_node(self):
        self.run_deploy('--package', str(self.package))
        self.assertNotIn('tsc ', self.calls())
        self.assertNotIn('vite ', self.calls())

    def test_old_releases_are_kept(self):
        self.run_deploy('--package', str(self.package))
        first = (self.deploy / 'current').resolve()
        self.run_deploy('--package', str(self.package))
        self.assertTrue(first.is_dir())
        self.assertNotEqual((self.deploy / 'current').resolve(), first)


if __name__ == '__main__':
    unittest.main()
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd /Users/zg/PycharmProjects/zg-homework && python3 -m unittest discover -s zg-homework-tests -p test_web_deploy.py -v`

Expected: FAIL —— `SCRIPT` 不存在，`sh` 退出码 127，测试全部失败。

- [ ] **Step 3: 实现 `web_deploy.sh`**

创建 `zg-homework-web/scripts/web_deploy.sh`：

```sh
#!/bin/sh
'''exec' python3 "$0" "$@"
' '''
"""发布前端产物到共享 nginx 的发布目录，并原子切换 current。"""
import argparse
import hashlib
import os
from pathlib import Path
import re
import secrets
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time

DEFAULTS = {
    'deploy_dir': '/var/lib/zg-homework-web',
    'nginx_bin': 'nginx',
    'nginx_main_conf': '/etc/nginx/nginx.conf',
}
MARKER = '.web-run-owner'


def fail(message):
    raise RuntimeError(message)


argparse._ = lambda message: {
    'usage: ': '用法：',
    'options': '选项',
    'show this help message and exit': '显示此帮助信息并退出',
    '%(prog)s: error: %(message)s\n': '%(prog)s：错误：%(message)s\n',
}.get(message, message)
parser = argparse.ArgumentParser(description='发布前端产物：解包静态包或本机构建，原子切换 current 后 reload nginx。')
group = parser.add_mutually_exclusive_group()
group.add_argument('--package', help='web_package.sh 产出的静态包路径')
group.add_argument('--build', action='store_true', help='在服务器本机构建（需要 Node 20+ 与 node_modules）')
parser.add_argument('--deploy-dir', default=DEFAULTS['deploy_dir'])
parser.add_argument('--source-dir', default=None, help='源码检出目录（--build 模式使用，默认脚本所在模块目录）')
parser.add_argument('--nginx-bin', default=DEFAULTS['nginx_bin'])
parser.add_argument('--nginx-main-conf', default=DEFAULTS['nginx_main_conf'])
parser.add_argument('--no-reload', action='store_true')
parser.add_argument('--help', action='store_true')
args = parser.parse_args()
if args.help:
    print(parser.format_help())
    sys.exit(0)
if not args.package and not args.build:
    parser.error('必须指定 --package 或 --build')


def run(command, **kwargs):
    return subprocess.run(command, text=True, **kwargs)


def version_name(digest):
    """版本目录名：web-<UTC 时间戳>-<内容哈希前 8 位>-<随机后缀>。
    随机后缀保证同一秒内两次发布不会撞名。"""
    stamp = time.strftime('%Y%m%d-%H%M%S', time.gmtime())
    return f'web-{stamp}-{digest[:8]}-{secrets.token_hex(2)}'


def safe_extract(archive, destination):
    """解包到 destination，拒绝符号链接、特殊文件与路径穿越条目。"""
    members = archive.getmembers()
    if not members:
        fail('静态包为空')
    tops = {member.name.split('/')[0] for member in members if member.name}
    if len(tops) != 1:
        fail('静态包必须只含一个顶层目录')
    top = tops.pop()
    if not top or top.startswith('/') or '..' in Path(top).parts:
        fail('静态包的顶层目录非法')
    if not any(member.name.startswith(top + '/') for member in members):
        fail('静态包的内容必须全部位于顶层目录之下')
    for member in members:
        name = member.name
        if name.startswith('/') or '..' in Path(name).parts:
            fail(f'静态包含有路径穿越条目：{name}')
        if member.issym() or member.islnk():
            fail(f'静态包含有链接条目：{name}')
        if not (member.isfile() or member.isdir()):
            fail(f'静态包含有特殊文件：{name}')
        if member.isfile():
            target = destination / Path(name).relative_to(top)
            target.parent.mkdir(parents=True, exist_ok=True)
            source = archive.extractfile(member)
            with open(target, 'wb') as output:
                shutil.copyfileobj(source, output)
        else:
            (destination / Path(name).relative_to(top)).mkdir(parents=True, exist_ok=True)


def release_from_package(package_path, releases):
    path = Path(package_path)
    if not path.is_file():
        fail(f'静态包不存在：{path}')
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    release = releases / version_name(digest)
    release.mkdir(parents=True)
    try:
        with tarfile.open(path, 'r:gz') as archive:
            safe_extract(archive, release)
    except tarfile.TarError as exc:
        shutil.rmtree(release, ignore_errors=True)
        fail(f'静态包无法解包：{exc}')
    if not (release / 'index.html').is_file():
        shutil.rmtree(release, ignore_errors=True)
        fail('静态包缺少 index.html')
    return release


def release_from_build(source, releases):
    tsc = source / 'node_modules/.bin/tsc'
    vite = source / 'node_modules/.bin/vite'
    for tool in (tsc, vite):
        if not os.access(tool, os.X_OK):
            fail(f'请先安装 Web 依赖：{tool}')
    result = run(['node', '--version'], capture_output=True)
    match = re.match(r'v(\d+)', result.stdout.strip())
    if not match or int(match.group(1)) < 20:
        fail('需要 Node.js 20 或更高版本')
    release = releases / version_name(hashlib.sha256(str(release_dir_seed(releases)).encode()).hexdigest())
    release.mkdir(parents=True)
    environment = {**os.environ, 'VITE_API_BASE_URL': '/homework_api'}
    for command in ([str(tsc), '--noEmit', '--incremental', 'false'],
                    [str(vite), 'build', '--mode', 'production', '--base', '/homework/',
                     '--outDir', str(release), '--emptyOutDir']):
        outcome = run(command, cwd=str(source), env=environment)
        if outcome.returncode:
            shutil.rmtree(release, ignore_errors=True)
            fail(f'构建失败：{command[0]}')
    if not (release / 'index.html').is_file():
        shutil.rmtree(release, ignore_errors=True)
        fail('构建未生成 index.html')
    return release


def release_dir_seed(releases):
    entries = sorted(p.name for p in releases.iterdir() if p.is_dir())
    return '|'.join(entries) + f'|{len(entries)}'


def publish(base, target):
    temporary = Path(tempfile.mkdtemp(prefix='.current-', dir=str(base)))
    try:
        link = temporary / 'current'
        link.symlink_to(target)
        os.replace(link, base / 'current')
    finally:
        shutil.rmtree(temporary, ignore_errors=True)


def main():
    base = Path(args.deploy_dir)
    releases = base / 'releases'
    if not releases.is_dir():
        fail(f'缺少发布目录，请先运行 install.sh：{releases}')
    source = Path(args.source_dir).resolve() if args.source_dir else None
    if args.build:
        source = source or Path(__file__).resolve().parent.parent
        release = release_from_build(source, releases)
    else:
        release = release_from_package(args.package, releases)
    (release / MARKER).write_text(str(source or release) + '\n', encoding='utf-8')
    test = run([args.nginx_bin, '-t', '-c', args.nginx_main_conf])
    if test.returncode:
        shutil.rmtree(release, ignore_errors=True)
        fail('nginx 配置校验失败，未切换版本')
    previous = None
    current = base / 'current'
    if current.exists() and not current.is_symlink():
        shutil.rmtree(release, ignore_errors=True)
        fail(f'{current} 已存在但不是受管理的符号链接')
    if current.is_symlink():
        previous = current.resolve()
    publish(base, release)
    if not args.no_reload:
        if shutil.which('systemctl'):
            result = run(['systemctl', 'reload', 'nginx'])
        else:
            result = run([args.nginx_bin, '-s', 'reload'])
        if result.returncode:
            if previous is not None:
                publish(base, previous)
                run(['systemctl', 'reload', 'nginx']) if shutil.which('systemctl') else None
            fail('nginx reload 失败，已恢复上一版本')
    print(f'已发布：{release}')
    print(f'current → {release}')
    kept = sorted(p.name for p in releases.iterdir() if p.is_dir() and p.name != release.name)
    if kept:
        print('保留的历史版本（需人工确认后清理）：' + ', '.join(kept))


try:
    main()
except RuntimeError as exc:
    print(f'错误：{exc}', file=sys.stderr)
    sys.exit(1)
except subprocess.SubprocessError as exc:
    print(f'错误：命令执行失败：{exc}', file=sys.stderr)
    sys.exit(1)
```

> 实现注记：`release_from_build` 的版本名种子用「已有版本目录列表 + 数量」而非构建产物内容哈希，避免为构建产物做全量读盘。版本名末尾的随机后缀保证同一秒内连续两次发布不会撞名。

- [ ] **Step 4: 跑测试确认通过**

Run: `cd /Users/zg/PycharmProjects/zg-homework && python3 -m unittest discover -s zg-homework-tests -p test_web_deploy.py -v`

Expected: PASS —— 5 tests OK。

若 `test_nginx_test_failure_keeps_current` 失败：检查 `nginx -t` 失败分支是否在 `publish()` **之前**执行（先校验再切换）。

- [ ] **Step 5: 跑全量回归**

Run: `cd /Users/zg/PycharmProjects/zg-homework && python3 -m unittest discover -s zg-homework-tests -p 'test_*.py' -v`

Expected: 既有 `test_run_scripts.py`、`test_production_contract.py`、`test_package_scripts.py` 全部 PASS，新测试全部 PASS。

- [ ] **Step 6: 提交**

```bash
cd /Users/zg/PycharmProjects/zg-homework
git add zg-homework-web/scripts/web_deploy.sh zg-homework-tests/test_web_deploy.py
git commit -m "feat(web): 新增 web_deploy.sh，支持静态包发布与原子切换"
```

---

## Task 5: 重写《生产部署打包方案.md》

**Files:**
- Modify: `zg-homework-docs/sys_doc/生产部署打包方案.md`（整体重写）
- Read-only 参考: `zg-homework-docs/superpowers/specs/2026-11-13-multi-project-deploy-design.md`

**Interfaces:**
- Consumes: Task 2/3/4 产出的三个脚本的真实命令行接口（参数名必须与脚本一致）
- Produces: 无代码接口

- [ ] **Step 1: 核对三个脚本的实际用法**

```bash
cd /Users/zg/PycharmProjects/zg-homework
sh zg-homework-server/scripts/install.sh --help
sh zg-homework-web/scripts/install.sh --help
sh zg-homework-web/scripts/web_deploy.sh --help
```

Expected: 三段用法文本，参数名与 Task 2/3/4 的 Interfaces 完全一致。**若不一致，先改脚本再写文档。**

- [ ] **Step 2: 重写文档**

整体替换 `zg-homework-docs/sys_doc/生产部署打包方案.md`，章节如下（每节都要有实际可复制的命令，参数与上一步核对过的一致）：

1. **一、多项目共存拓扑** —— 同域名 + 路径前缀模型图；资源归属清单；写入纪律（不碰 `nginx.conf` / `sites-available` / `sites-enabled`）。
2. **二、路径前缀与端口分配** —— 本项目固定 `/homework/`、`/homework_api/`、`127.0.0.1:8000`；新增项目时的分配约定。
3. **三、目录与数据规划** —— `/data/apps/zg-homework-server`、`/var/lib/zg-homework/{uploads,private_homework}`、`/var/lib/zg-homework-web/{releases,current}`、`/etc/zg-homework-server/env`、`/etc/nginx/conf.d/zg-homework.conf`；上传数据为何必须外置。
4. **四、服务端部署** —— `install.sh` 一键安装的完整命令；等价手工步骤（渲染 unit / 生成 env / 建目录 / 建 venv / `daemon-reload`）；`server_run.sh` 的 check/status/start/stop/restart；`server_package.sh` 打包与上传。
5. **五、前端部署** —— web `install.sh` 生成片段；`web_package.sh` 打包静态包；`web_deploy.sh --package` 发布；`web_deploy.sh --build` 服务器构建模式。
6. **六、共享 nginx 片段规范** —— 片段全文；主配置的 `include` 示例；reload 纪律；本项目不得写主配置的说明。
7. **七、数据库初始化** —— `python -m app.seed.initial_data`（幂等、含 admin、**不覆盖已有 admin 密码**）；`create_all()` 不加列的警告；迁移脚本 `app/seed/migrate_*.py` 与迁移前备份。
8. **八、TLS 与证书** —— 同域名共用一张证书，运维统一管理；本项目不申请、不续期。
9. **九、升级、回滚与备份** —— 服务端升级流程（备份 → 停服 → 覆盖 → venv → 配置 → `server_run.sh restart` → 验证）；前端回滚（`web_deploy.sh` 失败自动回滚，或手动把 `current` 指回旧版本目录）；备份项清单。
10. **十、日常更新流程**（补完原 `-- TODO`）—— 开发 → 本地验证 → `main` 分支打包 → 上传 → 安装 → 验证 → 回滚预案。
11. **十一、验证清单与故障对照表** —— curl 验证命令（注意健康检查是 **POST** `/homework_api/health`）+ 故障对照表。
12. **十二、脚本职责对照表** —— 四个脚本的用途、是否可重跑、写入范围。

文档中出现的所有端口、路径、命令必须与脚本实际行为一致；旧的 8001、gunicorn、`/etc/zg-homework/env`、`sites-available` 全部不得出现。

- [ ] **Step 3: 自检文档一致性**

```bash
cd /Users/zg/PycharmProjects/zg-homework
grep -n '8001\|gunicorn\|sites-available\|/etc/zg-homework/env' zg-homework-docs/sys_doc/生产部署打包方案.md
```

Expected: 无输出（无匹配）。

```bash
grep -n 'TODO\|TBD' zg-homework-docs/sys_doc/生产部署打包方案.md
```

Expected: 无输出。

- [ ] **Step 4: 提交**

```bash
cd /Users/zg/PycharmProjects/zg-homework
git add zg-homework-docs/sys_doc/生产部署打包方案.md
git commit -m "docs(deploy): 重写生产部署打包方案为多项目共存版"
```

---

## Task 6: 同步 `CLAUDE.md`

**Files:**
- Modify: `CLAUDE.md`（顶部声明块 + 「云服务器部署（裸机 systemd + nginx）」一节）

**Interfaces:**
- Consumes: Task 2/3/4 产出的脚本名与参数
- Produces: 无代码接口

- [ ] **Step 1: 核对 CLAUDE.md 中失效的引用**

```bash
cd /Users/zg/PycharmProjects/zg-homework
grep -n 'Makefile\|scripts/dev.sh\|scripts/init.sh\|deploy/README-DEPLOY.md\|acceptance_check.py\|independence_check.py\|install.sh' CLAUDE.md
```

Expected: 列出所有需要修正的行。

- [ ] **Step 2: 修正顶部声明块**

把

```markdown
> 当前仓库已移除根 Makefile、开发/初始化脚本、部署/打包脚本和文档验收脚本。下文提及这些文件的内容属于历史说明，不可执行；请直接使用模块源码和依赖清单。
```

改为

```markdown
> 根目录没有 Makefile，也没有 `scripts/dev.sh`、`scripts/init.sh`、`deploy/README-DEPLOY.md` 与 `zg-homework-docs/scripts/` 下的验收脚本——这些是历史说明，不可执行。可执行的脚本都在各模块的 `scripts/` 下，详见「云服务器部署」一节。
```

- [ ] **Step 3: 重写「云服务器部署」一节**

替换为：

```markdown
### 云服务器部署（裸机 systemd + 共享 nginx，多项目共存）

生产机多项目共存，**同一域名 + 路径前缀**区分：本项目占 `/homework/`（前端）与 `/homework_api/`（API）。共享 nginx 的主配置、`server` 块与 TLS 证书由运维统一维护，本项目只写自己的片段 `/etc/nginx/conf.d/zg-homework.conf`。

打包（开发机或 CI，产物不含任何凭据）：

```bash
cd zg-homework-server && ./scripts/server_package.sh    # → zg-homework-tests/tar/zg-homework-server-<ts>.tar.gz
cd zg-homework-web    && ./scripts/web_package.sh        # → zg-homework-tests/tar/zg-homework-web-static-<ts>.tar.gz
```

目标机安装（需 root）：

```bash
# 服务端：解压 → 安装 → 校验
tar -xzf zg-homework-server-<ts>.tar.gz && cd zg-homework-server-<ts>
sudo ./scripts/install.sh --server-dir /data/apps/zg-homework-server \
     --api-port 8000 --database-url 'mysql+pymysql://user:pass@127.0.0.1:3306/zg_homework?charset=utf8mb4'
sudo sh ./scripts/server_run.sh check
python -m app.seed.initial_data        # 数据库初始化（幂等，不覆盖已有 admin 密码）

# Web 端：生成片段 → 发布静态包
sudo zg-homework-web/scripts/install.sh --api-upstream 127.0.0.1:8000
zg-homework-web/scripts/web_deploy.sh --package zg-homework-web-static-<ts>.tar.gz
```

关键约束：

- **systemd 固定单 worker**（`--workers 1`）。成语接龙会话在进程内存（`app/routers/games.py` 的 `SessionStore`），多 worker 会丢会话。
- **上传数据必须在代码目录之外**（默认 `/var/lib/zg-homework/`），否则升级覆盖代码时会丢文件。
- **`proxy_pass` 不带末尾 `/`**：服务端路由自带 `/homework_api` 前缀，剥了会 404。
- **`alias` 必须带末尾 `/`**：`alias /var/lib/zg-homework-web/current/;`。
- **任何脚本都不得写** `/etc/nginx/nginx.conf`、`sites-available/`、`sites-enabled/`；只写自己的 `conf.d` 片段，且 reload 前必须 `nginx -t` 通过。
- **生产配置由 `scripts/install.sh` 生成**（`/etc/zg-homework-server/env`，`0640 root:www-data`）：值中不得含 `'"\$` 或未替换的 `__…__` 占位符，`server_run.sh` 会直接拒绝。重复执行默认保留已有 `JWT_SECRET`（避免轮换密钥导致已签发 token 失效），需强制覆盖时用 `--force-env`。
- **数据库初始化用 `python -m app.seed.initial_data`**：幂等，重复执行不重复插入，也不覆盖已存在的 admin 密码。它依赖项目自带的 PyMySQL，不需要 mysql 客户端。
- **无迁移框架**：`create_all()` 只建缺失的表，不给已有表加列。涉及表结构的升级需按 `app/seed/migrate_*.py` 单独执行迁移，迁移前备份数据库。
```

- [ ] **Step 4: 补充脚本清单说明**

在「常用命令」一节后追加一段：

```markdown
### 部署脚本清单

| 脚本 | 用途 | 可重跑 | 写入范围 |
|---|---|---|---|
| `zg-homework-server/scripts/install.sh` | 渲染 systemd 单元、生成生产配置、建数据目录、建 venv | 是（`--force-env` 除外） | `/etc/systemd/system/`、`/etc/zg-homework-server/`、`/var/lib/zg-homework/` |
| `zg-homework-server/scripts/server_run.sh` | 单元的 check/status/start/stop/restart | — | 不写文件 |
| `zg-homework-server/scripts/server_package.sh` | 服务端源码归档 | — | `zg-homework-tests/tar/` |
| `zg-homework-server/scripts/init_check.sh` | 创建 `.venv` | 否（拒绝覆盖） | 模块内 `.venv/` |
| `zg-homework-web/scripts/install.sh` | 生成共享 nginx 片段、建发布目录 | 是 | `/etc/nginx/conf.d/zg-homework.conf`、`/var/lib/zg-homework-web/` |
| `zg-homework-web/scripts/web_deploy.sh` | 解包静态包或本机构建 → 原子切换 `current` → reload | 是 | `/var/lib/zg-homework-web/` |
| `zg-homework-web/scripts/web_package.sh` | 前端静态包 / 源码包 | — | `zg-homework-tests/tar/` |
| `zg-homework-web/scripts/web_run.sh` | 独占 nginx 模式（本方案不使用） | — | `/var/lib/zg-homework-web/` |
```

- [ ] **Step 5: 自检**

```bash
cd /Users/zg/PycharmProjects/zg-homework
grep -n 'Makefile\|scripts/dev.sh\|scripts/init.sh\|deploy/README-DEPLOY.md\|acceptance_check.py\|independence_check.py\|render_env.sh\|db_bootstrap' CLAUDE.md
```

Expected: 无输出。

- [ ] **Step 6: 提交**

```bash
cd /Users/zg/PycharmProjects/zg-homework
git add CLAUDE.md
git commit -m "docs: 同步 CLAUDE.md 的脚本清单与生产部署说明"
```

---

## 最终验收

- [ ] **Step 1: 全量测试通过**

```bash
cd /Users/zg/PycharmProjects/zg-homework
python3 -m unittest discover -s zg-homework-tests -p 'test_*.py' -v
```

Expected: 全部 PASS。

- [ ] **Step 2: 三个脚本的 --help 正常**

```bash
sh zg-homework-server/scripts/install.sh --help
sh zg-homework-web/scripts/install.sh --help
sh zg-homework-web/scripts/web_deploy.sh --help
```

Expected: 均为退出码 0 并打印中文用法。

- [ ] **Step 3: 端到端演练（沙箱）**

```bash
cd /Users/zg/PycharmProjects/zg-homework
rm -rf /tmp/e2e && mkdir -p /tmp/e2e/root
sh zg-homework-server/scripts/install.sh --root /tmp/e2e/root \
   --server-dir "$PWD/zg-homework-server" --data-dir /tmp/e2e/data --skip-venv --no-start \
   --database-url 'mysql+pymysql://u:p@127.0.0.1:3306/db?charset=utf8mb4'
sh zg-homework-web/scripts/install.sh --root /tmp/e2e/root --deploy-dir /tmp/e2e/web \
   --nginx-main-conf /tmp/e2e/root/etc/nginx/nginx.conf --no-reload
cat /tmp/e2e/root/etc/nginx/conf.d/zg-homework.conf
```

Expected: 单元、env、nginx 片段三份文件均生成且内容符合设计；`env` 中无 `__…__`、无引号。

- [ ] **Step 4: 确认工作区干净**

```bash
cd /Users/zg/PycharmProjects/zg-homework && git status --short
```

Expected: 无输出（`生产部署打包方案.md` 的历史未提交改动已在 Task 5 提交）。
