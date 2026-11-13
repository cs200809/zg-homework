#!/bin/sh
'''exec' python3 "$0" "$@"
' '''
"""发布前端产物到共享 nginx 的发布目录，并原子切换 current。

两种输入模式：--package 解包 web_package.sh 产出的静态包（生产机无需 Node），
--build 在服务器本机构建。流程固定为：产出版本目录 → nginx -t → 原子切换 current → reload；
任何一步失败都不留下半成品，reload 失败会把 current 指回上一版本。

整个发布过程持发布目录的独占锁（与 web_run.sh 同一把锁），并发发布会被拒绝。

本脚本只写自己的发布目录（默认 /var/lib/zg-homework-web），不写 /etc/nginx/ 下的任何文件。
"""
import argparse
import fcntl
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

# 写死的发布目录：与 web install.sh 生成的 nginx 片段里的 alias 指向同一处。
ALLOWED_DEPLOY_DIR = '/var/lib/zg-homework-web'
DEFAULTS = {
    'deploy_dir': ALLOWED_DEPLOY_DIR,
    'nginx_bin': 'nginx',
    'nginx_main_conf': '/etc/nginx/nginx.conf',
    'root': '/',
}
# 归属标记：与 web_run.sh 的 .web-run-owner 格式一致（路径 + 换行）。
MARKER = '.web-run-owner'
UNKNOWN_OWNER = '<unknown>'
# 静态包唯一顶层目录名（web_package.sh 的静态包形态）。
STATIC_TOP = 'zg-homework-web-static'
# 解包上限：防止解压炸弹（web_package.sh 的真实产物远低于这些上限）。
MAX_MEMBERS = 20000
MAX_EXTRACT_BYTES = 512 * 1024 * 1024


def fail(message):
    raise RuntimeError(message)


def resolve_path(root, path):
    """把生产路径拼到 --root 前缀下落地（--root / 即生产行为）。"""
    if root == '/':
        return path
    return root.rstrip('/') + '/' + path.lstrip('/')


def nginx_available(binary):
    """名字走 PATH，含斜杠的按路径判断是否可执行。"""
    if '/' in binary:
        return os.path.isfile(binary) and os.access(binary, os.X_OK)
    return shutil.which(binary) is not None


def run(command, **kwargs):
    return subprocess.run(command, text=True, **kwargs)


def version_name(digest):
    """版本目录名：web-<UTC 时间戳>-<哈希前 8 位>-<随机后缀>。
    随机后缀保证同一秒内连续两次发布不会撞名。"""
    stamp = time.strftime('%Y%m%d-%H%M%S', time.gmtime())
    return 'web-%s-%s-%s' % (stamp, digest[:8], secrets.token_hex(2))


def entry_parts(name):
    """把归档条目名拆成路径分量。
    目录条目以 / 结尾；web_package.sh 的根目录条目形如 <top>/. ，两者都表示目录本身。"""
    parts = name.split('/')
    if parts and parts[-1] == '':
        parts = parts[:-1]
    if parts and parts[-1] == '.':
        parts = parts[:-1]
    return parts


def is_inside(base, target):
    try:
        target.relative_to(base)
        return True
    except ValueError:
        return False


def safe_extract(archive, destination):
    """解包到 destination；拒绝符号链接、特殊文件、绝对路径与路径穿越条目。"""
    members = archive.getmembers()
    if not members:
        fail('静态包为空')
    if len(members) > MAX_MEMBERS:
        fail('静态包的条目过多（%d 条，上限 %d 条）' % (len(members), MAX_MEMBERS))
    total = sum(member.size for member in members if member.isfile())
    if total > MAX_EXTRACT_BYTES:
        fail('静态包解压后的体积超过上限（%d MiB，上限 %d MiB）'
             % (total // (1024 * 1024), MAX_EXTRACT_BYTES // (1024 * 1024)))
    for member in members:
        name = member.name
        if not name:
            fail('静态包含有非法条目名')
        if name.startswith('/'):
            fail('静态包含有绝对路径条目：%s' % name)
        parts = entry_parts(name)
        if not parts:
            fail('静态包含有非法条目名：%s' % name)
        if '..' in parts:
            fail('静态包含有路径穿越条目：%s' % name)
        if any(part in ('', '.') for part in parts):
            fail('静态包含有非法路径条目：%s' % name)
    tops = {entry_parts(member.name)[0] for member in members}
    if len(tops) != 1:
        fail('静态包必须只含一个顶层目录')
    top = tops.pop()
    if top != STATIC_TOP:
        fail('静态包的顶层目录必须是 %s/（当前是 %s/）' % (STATIC_TOP, top))
    for member in members:
        name = member.name
        if member.issym() or member.islnk():
            fail('静态包含有链接条目：%s' % name)
        if not (member.isfile() or member.isdir()):
            fail('静态包含有特殊文件：%s' % name)
        target = destination / Path(*entry_parts(name)[1:])
        if not is_inside(destination, target):
            fail('静态包含有越界条目：%s' % name)
        if member.isdir():
            target.mkdir(parents=True, exist_ok=True)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        with open(target, 'wb') as output:
            shutil.copyfileobj(archive.extractfile(member), output)
        os.chmod(target, 0o644)


def create_release(releases, name):
    release = releases / name
    try:
        release.mkdir(parents=True, exist_ok=False)
    except FileExistsError:
        fail('版本目录已存在：%s' % release)
    os.chmod(release, 0o755)
    return release


def file_digest(path):
    """分块计算摘要：静态包可能很大，不整体读进内存。"""
    digest = hashlib.sha256()
    with open(path, 'rb') as source:
        for block in iter(lambda: source.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def release_from_package(package_path, releases):
    path = Path(package_path)
    if not path.is_file():
        fail('静态包不存在：%s' % path)
    digest = file_digest(path)
    release = create_release(releases, version_name(digest))
    try:
        with tarfile.open(path, 'r:gz') as archive:
            safe_extract(archive, release)
        if not (release / 'index.html').is_file():
            fail('静态包缺少 index.html')
    except tarfile.TarError as exc:
        shutil.rmtree(release, ignore_errors=True)
        fail('静态包无法解包：%s' % exc)
    except Exception:
        shutil.rmtree(release, ignore_errors=True)
        raise
    return release


def release_seed(releases):
    """构建模式的版本名种子：已有版本目录列表 + 数量（不为构建产物做全量读盘）。"""
    entries = sorted(p.name for p in releases.iterdir() if p.is_dir())
    return '|'.join(entries) + '|%d' % len(entries)


def release_from_build(source, releases):
    tsc = source / 'node_modules/.bin/tsc'
    vite = source / 'node_modules/.bin/vite'
    for tool in (tsc, vite):
        if not os.access(tool, os.X_OK):
            fail('请先安装 Web 依赖：%s' % tool)
    if not shutil.which('node'):
        fail('缺少依赖：node')
    result = run(['node', '--version'], capture_output=True)
    match = re.match(r'v(\d+)', result.stdout.strip())
    if not match or int(match.group(1)) < 20:
        fail('需要 Node.js 20 或更高版本')
    seed = hashlib.sha256(release_seed(releases).encode()).hexdigest()
    release = create_release(releases, version_name(seed))
    environment = {**os.environ, 'VITE_API_BASE_URL': '/homework_api'}
    try:
        for command in ([str(tsc), '--noEmit', '--incremental', 'false'],
                        [str(vite), 'build', '--mode', 'production', '--base', '/homework/',
                         '--outDir', str(release), '--emptyOutDir']):
            outcome = run(command, cwd=str(source), env=environment)
            if outcome.returncode:
                fail('构建失败：%s' % command[0])
        if not (release / 'index.html').is_file():
            fail('构建未生成 index.html')
    except Exception:
        shutil.rmtree(release, ignore_errors=True)
        raise
    return release


def publish(base, target):
    """同文件系统内的临时符号链接 + os.replace：切换是原子的，绝不先删后建。"""
    temporary = Path(tempfile.mkdtemp(prefix='.current-', dir=str(base)))
    try:
        link = temporary / 'current'
        link.symlink_to(target)
        os.replace(link, base / 'current')
    finally:
        shutil.rmtree(temporary, ignore_errors=True)


def acquire_lock(base):
    """独占锁住发布目录：与 web_run.sh 同样的做法，避免两次发布交错。"""
    fd = os.open(str(base), os.O_RDONLY | os.O_DIRECTORY)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        os.close(fd)
        fail('发布目录已被锁定（另一个发布或服务控制操作正在进行）：%s；请稍后重试' % base)
    return fd


def release_lock(fd):
    if fd is None:
        return
    try:
        fcntl.flock(fd, fcntl.LOCK_UN)
    except OSError:
        pass
    try:
        os.close(fd)
    except OSError:
        pass


def managed_release(target, releases):
    """目标是否是受管理的发布版本：必须直接位于 releases/ 之下。

    与 web_run.sh 的 current_target() 同一约束：手工造的 current → /etc 之类的
    符号链接不是受管理版本，绝不能被当作回滚目标写回去。
    """
    try:
        parent = target.parent.resolve()
    except OSError:
        return False
    return parent == releases.resolve() and target.is_dir()


def reload_nginx(nginx_bin):
    if shutil.which('systemctl'):
        return run(['systemctl', 'reload', 'nginx']).returncode == 0
    return run([nginx_bin, '-s', 'reload']).returncode == 0


# Translate argparse's standard labels and common argument errors without changing parsing.
# 这张表与同一模块下的 web_package.sh 逐字重复（两处都要同步维护）。
_argparse_messages = {
    'usage: ': '用法：',
    'options': '选项',
    'optional arguments': '可选参数',
    'show this help message and exit': '显示此帮助信息并退出',
    '%(prog)s: error: %(message)s\n': '%(prog)s：错误：%(message)s\n',
    'unrecognized arguments: %s': '无法识别的参数：%s',
    'expected one argument': '需要一个参数',
    'argument %(argument_name)s: %(message)s': '参数 %(argument_name)s：%(message)s',
    'not allowed with argument %s': '不能与参数 %s 同时使用',
}
_original_argparse_gettext = argparse._
argparse._ = lambda message: _argparse_messages.get(message, _original_argparse_gettext(message))

parser = argparse.ArgumentParser(
    description='发布前端产物：解包静态包（--package）或本机构建（--build），'
                '校验 nginx 配置后原子切换 current 并 reload。'
                '只写自己的发布目录，不写 /etc/nginx/ 下的任何文件。')
group = parser.add_mutually_exclusive_group()
group.add_argument('--package', help='web_package.sh 产出的静态包路径（推荐：生产机无需 Node）')
group.add_argument('--build', action='store_true', help='在服务器本机构建（需要 Node 20+ 与 node_modules）')
parser.add_argument('--deploy-dir', default=DEFAULTS['deploy_dir'],
                    help='前端产物根目录（固定 %s）' % ALLOWED_DEPLOY_DIR)
parser.add_argument('--source-dir', default=None,
                    help='源码检出目录（--build 用它构建；--package 用它记录归属来源，'
                         '缺省时归属记为 <unknown>）')
parser.add_argument('--nginx-bin', default=DEFAULTS['nginx_bin'], help='nginx 可执行文件（默认 nginx）')
parser.add_argument('--nginx-main-conf', default=DEFAULTS['nginx_main_conf'],
                    help='nginx 主配置路径（默认 /etc/nginx/nginx.conf）')
parser.add_argument('--root', default=DEFAULTS['root'],
                    help='沙箱前缀：把落地位置映射到该目录下（默认 /）')
parser.add_argument('--no-reload', action='store_true', help='切换 current 后不 reload nginx')
args = parser.parse_args()
if not args.package and not args.build:
    parser.error('必须指定 --package 或 --build')


def validate_args():
    if not args.root.startswith('/'):
        fail('--root 无效：必须是绝对路径（当前值 %s）' % args.root)
    if args.deploy_dir != ALLOWED_DEPLOY_DIR:
        fail('--deploy-dir 无效：只能是 %s；本项目只写自己的发布目录，'
             '不得写其它项目的目录（当前值 %s）' % (ALLOWED_DEPLOY_DIR, args.deploy_dir))
    if not args.nginx_main_conf.startswith('/'):
        fail('--nginx-main-conf 无效：必须是绝对路径（当前值 %s）' % args.nginx_main_conf)
    if args.source_dir is not None and not args.source_dir.startswith('/'):
        fail('--source-dir 无效：必须是绝对路径（当前值 %s）' % args.source_dir)


def main():
    validate_args()
    base = Path(resolve_path(args.root, args.deploy_dir))
    releases = base / 'releases'
    if not releases.is_dir() or releases.is_symlink():
        fail('缺少发布目录，请先运行 web install.sh：%s' % releases)
    current = base / 'current'
    # current 只允许是受管理的符号链接：真实目录绝不能被覆盖。
    if os.path.lexists(current) and not current.is_symlink():
        fail('%s 已存在但不是受管理的符号链接；请人工确认后再发布' % current)
    # 缺件必须先报清楚：否则会被误报成“配置非法”，并误删刚产出的版本目录。
    if not nginx_available(args.nginx_bin):
        fail('找不到 nginx 可执行文件（%s）；请用 --nginx-bin 指定 nginx 的绝对路径，'
             '或先安装 nginx 后重试；未写入任何文件' % args.nginx_bin)
    # 整个发布过程持独占锁：并发发布会交错 reload 与历史版本清单。
    lock = acquire_lock(base)
    try:
        publish_locked(base, releases, current)
    finally:
        release_lock(lock)


def publish_locked(base, releases, current):
    source = Path(args.source_dir).resolve() if args.source_dir else None
    if args.build:
        source = source or Path(__file__).resolve().parent.parent
        if not source.is_dir():
            fail('源码检出目录不存在：%s' % source)
        release = release_from_build(source, releases)
        owner = str(source)
    else:
        release = release_from_package(args.package, releases)
        # 模式 A：源码目录已知就记录来源（保留真实归属），未知才写 <unknown>。
        owner = str(source) if source is not None else UNKNOWN_OWNER
    (release / MARKER).write_text(owner + '\n', encoding='utf-8')
    # 必须先 nginx -t 通过才允许切换；失败只删本次版本目录，不动 current。
    test = run([args.nginx_bin, '-t', '-c', resolve_path(args.root, args.nginx_main_conf)],
               capture_output=True)
    if test.returncode:
        shutil.rmtree(release, ignore_errors=True)
        detail = (test.stderr or test.stdout or '').strip().splitlines()
        fail('nginx 配置校验失败，未切换版本' + ('：' + detail[-1] if detail else ''))
    previous = None
    unmanaged = None
    if current.is_symlink():
        target = current.resolve()
        if managed_release(target, releases):
            previous = target
        else:
            # 手工造的符号链接不是受管理版本，不能作为回滚目标写回去。
            unmanaged = target
    publish(base, release)
    if not args.no_reload:
        if not reload_nginx(args.nginx_bin):
            if previous is not None:
                publish(base, previous)
                if reload_nginx(args.nginx_bin):
                    fail('nginx reload 失败，已恢复上一版本：%s' % previous)
                fail('符号链接已恢复，但回滚 reload 同样失败；current 已指回 %s，'
                     '但 nginx 可能仍在服务新版本，请人工检查' % previous)
            if unmanaged is not None:
                fail('nginx reload 失败；原 current 指向 %s，不是受管理的发布目录，'
                     '不作为回滚目标；current 仍指向新版本，请人工检查' % unmanaged)
            fail('nginx reload 失败；不存在上一版本可恢复，current 仍指向新版本，请人工检查')
    print('已发布：%s' % release)
    print('current → %s' % release)
    kept = sorted(p.name for p in releases.iterdir() if p.is_dir() and p.name != release.name)
    if kept:
        print('保留的历史版本（需人工确认后清理）：' + ', '.join(kept))


try:
    main()
except RuntimeError as exc:
    print('错误：%s' % exc, file=sys.stderr)
    sys.exit(1)
except subprocess.SubprocessError as exc:
    print('错误：命令执行失败：%s' % exc, file=sys.stderr)
    sys.exit(1)
except OSError as exc:
    print('错误：%s' % exc, file=sys.stderr)
    sys.exit(1)
except Exception as exc:
    # 兜底：生产脚本不应抛裸 traceback。
    print('错误：发布失败：%s' % exc, file=sys.stderr)
    sys.exit(1)
