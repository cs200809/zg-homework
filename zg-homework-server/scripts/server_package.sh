#!/bin/sh
# Package the current module working tree; no Git operations are performed.
exec python3 - "$0" "$@" <<'PY'
import argparse
from datetime import datetime
import os
from pathlib import Path
import stat
import sys
import tarfile
import tempfile

MODULE = 'zg-homework-server'
TREE = 'app'
FILES = ('requirements.txt', '.env.example', 'Dockerfile', '.dockerignore',
         'README.md', 'scripts/server_run.sh', 'scripts/server_package.sh', 'scripts/install.sh',
         'scripts/init_check.sh', 'scripts/production.env.example',
         'scripts/zg-homework-server.service.example')
SERVER = True

# Translate argparse's standard labels and common argument errors without changing parsing.
_argparse_messages = {
    'usage: ': '用法：',
    'options': '选项',
    'optional arguments': '可选参数',
    'show this help message and exit': '显示此帮助信息并退出',
    '%(prog)s: error: %(message)s\n': '%(prog)s：错误：%(message)s\n',
    'unrecognized arguments: %s': '无法识别的参数：%s',
    'expected one argument': '需要一个参数',
    'argument %(argument_name)s: %(message)s': '参数 %(argument_name)s：%(message)s',
}
_original_argparse_gettext = argparse._
argparse._ = lambda message: _argparse_messages.get(message, _original_argparse_gettext(message))
parser = argparse.ArgumentParser(description='将当前工作树打包为部署源码归档。'
    '分发前请检查源码和示例文件中是否包含敏感信息。'
    '无法保证并发修改源码时生成的快照一致。')
parser.add_argument('-o', '--output', help='两个模块目录之外的新 .tar.gz 文件路径（默认：zg-homework-tests/tar）')
args = parser.parse_args(sys.argv[2:])
root = Path(os.path.abspath(sys.argv[1])).resolve().parent.parent

# Only application sources/resources are traversed. Hidden, generated, test,
# local configuration and runtime data are never part of the source package.
def excluded(name, is_dir):
    lower = name.lower()
    if name.startswith('.') or lower in {
        '__pycache__', 'node_modules', 'dist', 'build', 'coverage', 'uploads',
        'data', 'logs', 'log', 'tmp', 'temp', 'venv', 'env', 'tests', 'test',
        '__tests__', 'fixtures', 'offline_tests', 'htmlcov', 'cache',
    }:
        return True
    if is_dir:
        return lower.endswith(('.egg-info', '.dist-info'))
    return (lower.startswith(('test_', 'test-')) or
            lower.endswith(('.pyc', '.pyo', '.log', '.tmp', '.temp', '.bak',
                            '.swp', '.swo', '~', '.test.js', '.test.jsx',
                            '.test.ts', '.test.tsx', '.spec.js', '.spec.jsx',
                            '.spec.ts', '.spec.tsx')))

def signature(st):
    return (st.st_dev, st.st_ino, st.st_mode, st.st_size, st.st_mtime_ns, st.st_ctime_ns)

def require_regular(path):
    st = path.lstat()
    if not stat.S_ISREG(st.st_mode):
        raise ValueError('不是普通文件（禁止使用符号链接）：' + str(path))
    return st

def collect_tree(path, relative, entries):
    before = path.lstat()
    if not stat.S_ISDIR(before.st_mode):
        raise ValueError('不是目录（禁止使用符号链接）：' + str(path))
    entries.append((path, relative, before))
    with os.scandir(path) as scan:
        children = sorted(scan, key=lambda item: item.name)
    for child in children:
        st = child.stat(follow_symlinks=False)
        is_dir = stat.S_ISDIR(st.st_mode)
        if excluded(child.name, is_dir):
            continue
        child_path = path / child.name
        child_rel = relative / child.name
        if is_dir:
            collect_tree(child_path, child_rel, entries)
        elif stat.S_ISREG(st.st_mode):
            if not SERVER or child.name.endswith('.py'):
                entries.append((child_path, child_rel, st))
        else:
            raise ValueError('输入中存在符号链接或特殊文件：' + str(child_path))
    if signature(path.lstat()) != signature(before):
        raise ValueError('收集时输入目录发生变化：' + str(path))

def main():
    if args.output:
        output = Path(args.output).absolute()
    else:
        directory = root.parent / 'zg-homework-tests' / 'tar'
        directory.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime('%Y%m%d-%H%M%S-%f')
        output = directory / f'{MODULE}-{timestamp}.tar.gz'
    if output.name in ('', '.', '..') or not output.name.endswith('.tar.gz'):
        raise ValueError('输出必须指定新的 .tar.gz 文件')
    parent = output.parent.resolve(strict=True)
    if not parent.is_dir():
        raise ValueError('输出文件的父目录必须已存在')
    modules = (root, (root.parent / 'zg-homework-web').resolve())
    if any(parent == module or module in parent.parents for module in modules):
        raise ValueError('输出文件必须位于两个模块目录之外')
    output = parent / output.name
    if os.path.lexists(output):
        raise FileExistsError('输出文件已存在：' + str(output))

    entries = []
    collect_tree(root / TREE, Path(TREE), entries)
    for name in FILES:
        path = root / name
        # The fixed scripts directory must not redirect outside the module.
        if '/' in name and not stat.S_ISDIR((root / 'scripts').lstat().st_mode):
            raise ValueError('scripts 必须是真实目录')
        entries.append((path, Path(name), require_regular(path)))

    fd, temporary = tempfile.mkstemp(prefix='.package-', suffix='.tmp', dir=parent)
    try:
        with os.fdopen(fd, 'wb') as raw:
            with tarfile.open(fileobj=raw, mode='w:gz', format=tarfile.PAX_FORMAT) as archive:
                for path, relative, original in entries:
                    if signature(path.lstat()) != signature(original):
                        raise ValueError('打包时输入发生变化：' + str(path))
                    info = tarfile.TarInfo(MODULE + '/' + relative.as_posix())
                    info.mode = stat.S_IMODE(original.st_mode) & 0o777
                    info.mtime = int(original.st_mtime)
                    if stat.S_ISDIR(original.st_mode):
                        info.type = tarfile.DIRTYPE
                        archive.addfile(info)
                    else:
                        flags = os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_NONBLOCK', 0)
                        file_fd = os.open(path, flags)
                        with os.fdopen(file_fd, 'rb') as source:
                            if signature(os.fstat(source.fileno())) != signature(original):
                                raise ValueError('打开时输入发生变化：' + str(path))
                            info.size = original.st_size
                            archive.addfile(info, source)
                            if signature(os.fstat(source.fileno())) != signature(original):
                                raise ValueError('读取时输入发生变化：' + str(path))
            raw.flush()
            os.fsync(raw.fileno())
        # Hard-link publication is atomic and fails if the destination exists.
        os.link(temporary, output)
    finally:
        os.unlink(temporary)
    print('已创建：', output)
    print('警告：请检查文件中是否包含敏感信息；并发修改时无法保证快照一致。', file=sys.stderr)

try:
    main()
except (OSError, ValueError, tarfile.TarError) as exc:
    print('打包失败：', exc, file=sys.stderr)
    sys.exit(1)
PY
