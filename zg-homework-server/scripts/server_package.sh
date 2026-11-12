#!/bin/sh
# Package the current module working tree; no Git operations are performed.
exec python3 - "$0" "$@" <<'PY'
import argparse
import os
from pathlib import Path
import stat
import sys
import tarfile
import tempfile

MODULE = 'zg-homework-server'
TREE = 'app'
FILES = ('requirements.txt', '.env.example', 'Dockerfile', '.dockerignore',
         'README.md', 'scripts/server_run.sh', 'scripts/server_package.sh')
SERVER = True

parser = argparse.ArgumentParser(description='Package the current working tree as a deployment source archive. '
    'Inspect source and example files for secrets before distribution. '
    'Concurrent source changes cannot be guaranteed to produce a consistent snapshot.')
parser.add_argument('-o', '--output', required=True, help='new .tar.gz path in an existing directory outside both modules')
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
        raise ValueError('not a regular file (symlinks are forbidden): ' + str(path))
    return st

def collect_tree(path, relative, entries):
    before = path.lstat()
    if not stat.S_ISDIR(before.st_mode):
        raise ValueError('not a directory (symlinks are forbidden): ' + str(path))
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
            raise ValueError('symlink or special file in input: ' + str(child_path))
    if signature(path.lstat()) != signature(before):
        raise ValueError('input directory changed while collecting: ' + str(path))

def main():
    output = Path(args.output).absolute()
    if output.name in ('', '.', '..') or not output.name.endswith('.tar.gz'):
        raise ValueError('output must name a new .tar.gz file')
    parent = output.parent.resolve(strict=True)
    if not parent.is_dir():
        raise ValueError('output parent must be an existing directory')
    modules = (root, (root.parent / 'zg-homework-web').resolve())
    if any(parent == module or module in parent.parents for module in modules):
        raise ValueError('output must be outside both module directories')
    output = parent / output.name
    if os.path.lexists(output):
        raise FileExistsError('output already exists: ' + str(output))

    entries = []
    collect_tree(root / TREE, Path(TREE), entries)
    for name in FILES:
        path = root / name
        # The fixed scripts directory must not redirect outside the module.
        if '/' in name and not stat.S_ISDIR((root / 'scripts').lstat().st_mode):
            raise ValueError('scripts must be a real directory')
        entries.append((path, Path(name), require_regular(path)))

    fd, temporary = tempfile.mkstemp(prefix='.package-', suffix='.tmp', dir=parent)
    try:
        with os.fdopen(fd, 'wb') as raw:
            with tarfile.open(fileobj=raw, mode='w:gz', format=tarfile.PAX_FORMAT) as archive:
                for path, relative, original in entries:
                    if signature(path.lstat()) != signature(original):
                        raise ValueError('input changed while packaging: ' + str(path))
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
                                raise ValueError('input changed while opening: ' + str(path))
                            info.size = original.st_size
                            archive.addfile(info, source)
                            if signature(os.fstat(source.fileno())) != signature(original):
                                raise ValueError('input changed while reading: ' + str(path))
            raw.flush()
            os.fsync(raw.fileno())
        # Hard-link publication is atomic and fails if the destination exists.
        os.link(temporary, output)
    finally:
        os.unlink(temporary)
    print('Created:', output)
    print('Warning: inspect files for secrets; concurrent changes are not a consistent snapshot.', file=sys.stderr)

try:
    main()
except (OSError, ValueError, tarfile.TarError) as exc:
    print('Package failed:', exc, file=sys.stderr)
    sys.exit(1)
PY
