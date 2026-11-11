"""Helpers for the rename and comment evidence. Expected rename pairs come from git itself, run on a throwaway copy of
the repository, never from the product."""
import os
import shutil
import subprocess
import sys
from pathlib import Path

from tests.delta_support import MAIN, REPO

IDENTITY = {'GIT_AUTHOR_NAME': 't', 'GIT_AUTHOR_EMAIL': 't@example.invalid', 'GIT_COMMITTER_NAME': 't',
            'GIT_COMMITTER_EMAIL': 't@example.invalid', 'GIT_CONFIG_GLOBAL': os.devnull, 'GIT_CONFIG_NOSYSTEM': '1',
            'GIT_TERMINAL_PROMPT': '0'}
MISSING_COMMIT = '0123456789abcdef0123456789abcdef01234567'
RENAMES_WARNING = '[!] Warning: renames not detected ({})'


def git(root, *args, check=True, binary=False, extra_env=None):
    done = subprocess.run(['git', *map(str, args)], cwd=root, env={**os.environ, **IDENTITY, **(extra_env or {})},
                          capture_output=True, text=not binary)
    if check:
        assert done.returncode == 0, (args, done.stderr)
    return done.stdout


def write_files(root, files):
    for relative, text in files.items():
        target = Path(root) / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding='utf-8')


def make_repo(root, files):
    """Creates a git repository with every file committed; returns the HEAD commit."""
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    git(root, 'init', '-q')
    write_files(root, files)
    git(root, 'add', '-A')
    git(root, 'commit', '-q', '-m', 'base')
    return git(root, 'rev-parse', 'HEAD').strip()


def block(tag, count=30, width=20):
    """count lines of exactly `width` bytes each; lines of different tags never coincide."""
    lines = []
    for index in range(count):
        head = f'{tag}_{index:04d}_'
        lines.append(head + 'x' * (width - 1 - len(head)) + '\n')
    assert all(len(line) == width for line in lines)
    return ''.join(lines)


def oracle_pairs(root, commit, scratch, threshold=None):
    """git's own rename report for commit -> working tree including untracked files, computed on a copy of the repository."""
    copy = Path(scratch) / 'oracle-copy'
    if copy.exists():
        shutil.rmtree(copy)
    shutil.copytree(root, copy, symlinks=True)
    git(copy, 'add', '-A')
    flag = '-M' if threshold is None else f'-M{threshold}%'
    out = git(copy, 'diff', '--cached', flag, '--name-status', '--no-ext-diff', '--no-textconv', commit)
    pairs = []
    for line in out.splitlines():
        status, *names = line.split('\t')
        if status.startswith('R'):
            pairs.append({'from': names[0], 'to': names[1], 'similarity': int(status[1:])})
    return sorted(pairs, key=lambda pair: pair['from']), out


def observations(root):
    """The five repository observations that a rename detection must leave unchanged."""
    root = Path(root)
    index = (root / '.git' / 'index').read_bytes()
    quiet = {'GIT_OPTIONAL_LOCKS': '0'}
    return {
        'status': git(root, 'status', '--porcelain=v2', '--untracked-files=all', extra_env=quiet),
        'index': index,
        'objects': git(root, 'count-objects', '-v'),
        'refs': git(root, 'for-each-ref'),
        'config': (root / '.git' / 'config').read_bytes(),
    }


def run_cli(args, env=None, cwd=REPO):
    environment = dict(os.environ, PYTHONHASHSEED='0')
    environment.update(env or {})
    return subprocess.run([sys.executable, '-c', MAIN, *map(str, args)], cwd=cwd, env=environment, capture_output=True, text=True)


def empty_path_env(directory):
    """PATH that holds no executable at all, so git cannot be found; the interpreter is invoked by absolute path."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    return {'PATH': str(directory)}


APP_FILES = {
    'app/__init__.py': '"""app"""\n',
    'app/a.py': 'from app.b import fb\n\n\ndef fa(x):\n    return fb(x) + 1\n',
    'app/b.py': 'from app.a import fa\n\n\ndef fb(x):\n    if x > 100:\n        return x\n    return fa(x + 1)\n',
    'app/c.py': 'from app.a import fa\n\n\ndef fc():\n    return fa(2)\n',
    'app/d.py': 'def fd(y):\n    return y * 4\n',
}


def analysis_args(root, out, *extra, bottlenecks='b.json'):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    return [root, '-l', 'python', '--granularity', 'file', '--json', '-o', out / 'r.html', '--bottlenecks', out / bottlenecks, *extra]


def move_a_to_a_impl(root, use_git_mv=True):
    root = Path(root)
    if use_git_mv:
        git(root, 'mv', 'app/a.py', 'app/a_impl.py')
    else:
        (root / 'app' / 'a.py').rename(root / 'app' / 'a_impl.py')
    for name in ('b.py', 'c.py'):
        path = root / 'app' / name
        path.write_text(path.read_text(encoding='utf-8').replace('app.a import', 'app.a_impl import'), encoding='utf-8')
