"""Complements the Bash sandbox (which has no network and denyRead on these roots) with rules the sandbox cannot express:
file-tool paths, upstream-lookup commands, and points.json being write-once.
"""
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUNS = Path.home() / 'toy-projects' / 'network-analysis-eval' / 'runs'
RUN = Path(sys.argv[1]).resolve()
POINTS = RUN / 'points.json'
# the gate executes interpreters and node tooling from these; everything else under ROOT is the analyzer and pilot data
ROOT_ALLOWED = [ROOT / 'eval' / 'envs', ROOT / 'eval' / 'node', ROOT / 'eval' / '.venv']
FORBIDDEN = [ROOT, RUNS, Path.home() / '.claude', Path('/private/tmp/claude-501'), Path('/tmp/claude-501')]
UPSTREAM = re.compile(r'\bgit\b[^|;&]*\b(remote|fetch|pull|push|ls-remote|clone|submodule|request-pull|archive\s+--remote)\b'
                      r'|\bgh\b|github\.com|githubusercontent|gitlab\.com|bitbucket\.org')


def deny(reason):
    print(json.dumps({'hookSpecificOutput': {'hookEventName': 'PreToolUse', 'permissionDecision': 'deny',
                                             'permissionDecisionReason': reason}}))
    sys.exit(0)


def inside(path, root):
    return path == root or root in path.parents


def check_path(raw, cwd):
    path = Path(os.path.expanduser(raw))
    path = (path if path.is_absolute() else Path(cwd) / path).resolve()
    if inside(path, RUN) or any(inside(path, a) for a in ROOT_ALLOWED):
        return path
    if any(inside(path, f) for f in FORBIDDEN):
        deny(f'{path} is outside this evaluation run')
    return path


def main():
    event = json.load(sys.stdin)
    tool, args, cwd = event.get('tool_name'), event.get('tool_input') or {}, event.get('cwd') or str(RUN)
    if tool == 'Bash':
        command = args.get('command', '')
        if UPSTREAM.search(command):
            deny('upstream repository lookups are not allowed in this evaluation')
        if '../..' in command or '.claude' in command:
            deny('paths outside this evaluation run are not allowed')
        for match in re.finditer(r'(?:~|/Users/[^/\s\'"]+)/[^\s\'";|&)]*', command):
            check_path(match.group(0), cwd)
        return
    for key in ('file_path', 'path', 'notebook_path'):
        if args.get(key):
            path = check_path(args[key], cwd)
            if tool in ('Write', 'Edit', 'MultiEdit', 'NotebookEdit') and path == POINTS and (tool != 'Write' or POINTS.exists()):
                deny('points.json is write-once: the declared points and predictions cannot be changed')
    if tool == 'Glob' and str(args.get('pattern', '')).startswith(('/', '~')):
        check_path(args['pattern'].split('*')[0] or '/', cwd)


if __name__ == '__main__':
    main()
