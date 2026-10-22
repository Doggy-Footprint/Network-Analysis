"""Archive subagent transcripts of an evaluation session and tabulate token usage per agent role."""
import argparse
import json
import re
import shutil
from pathlib import Path

EVAL = Path(__file__).resolve().parents[2] / 'eval'
ROLE = [(re.compile(r'results/([\w-]+)/finder-prompt\.md'), 'finder'),
        (re.compile(r'results/([\w-]+)/refactor-(p\d)-prompt\.md'), 'refactor'),
        (re.compile(r'results/([\w-]+)/test-baseline\.json'), 'test_baseline')]


def classify(prompt):
    for pattern, role in ROLE:
        match = pattern.search(prompt)
        if match:
            groups = match.groups()
            return {'role': role, 'repo': groups[0], 'pid': groups[1] if len(groups) > 1 else None}
    return {'role': 'other', 'repo': None, 'pid': None}


def summarize(path):
    usage, seen, first, model, tools, start, end = {}, set(), None, None, 0, None, None
    for line in path.read_text().splitlines():
        record = json.loads(line)
        start = start or record.get('timestamp')
        end = record.get('timestamp') or end
        message = record.get('message') or {}
        if first is None and record.get('type') == 'user' and isinstance(message.get('content'), str):
            first = message['content']
        if record.get('type') != 'assistant':
            continue
        model = message.get('model', model)
        tools += sum(1 for c in message.get('content', []) if isinstance(c, dict) and c.get('type') == 'tool_use')
        # one API response is split across several transcript lines that repeat the same usage block
        key = message.get('id') or record.get('requestId')
        if key in seen:
            continue
        seen.add(key)
        for name, value in (message.get('usage') or {}).items():
            if isinstance(value, int):
                usage[name] = usage.get(name, 0) + value
    return first or '', model, tools, usage, start, end


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('subagent_dir', help='~/.claude/projects/<project>/<session>/subagents')
    parser.add_argument('--experiment', default='report-informed')
    args = parser.parse_args()
    raw = EVAL / 'results' / 'raw' / args.experiment / 'agents'
    raw.mkdir(parents=True, exist_ok=True)
    rows = []
    for path in sorted(Path(args.subagent_dir).expanduser().glob('agent-*.jsonl')):
        shutil.copy2(path, raw / path.name)
        meta = path.with_suffix('.meta.json')
        if meta.exists():
            shutil.copy2(meta, raw / meta.name)
        prompt, model, tools, usage, start, end = summarize(path)
        role = classify(prompt)
        if role['role'] == 'other' and 'test-baseline' in prompt:
            role['role'] = 'test_baseline'
        rows.append({'agent': path.stem.removeprefix('agent-'), **role, 'model': model, 'tool_uses': tools, 'start': start, 'end': end,
                     'input_tokens': usage.get('input_tokens', 0), 'cache_creation_input_tokens': usage.get('cache_creation_input_tokens', 0),
                     'cache_read_input_tokens': usage.get('cache_read_input_tokens', 0), 'output_tokens': usage.get('output_tokens', 0),
                     'prompt_head': prompt[:160]})
    (EVAL / 'results' / f'agents-{args.experiment}.json').write_text(json.dumps(rows, indent=1))
    for row in rows:
        total = row['input_tokens'] + row['cache_creation_input_tokens'] + row['cache_read_input_tokens'] + row['output_tokens']
        print(f"{row['role']:13} {row['repo'] or '-':13} {row['pid'] or '-':3} out={row['output_tokens']:>7} total={total:>9} tools={row['tool_uses']}")


if __name__ == '__main__':
    main()
