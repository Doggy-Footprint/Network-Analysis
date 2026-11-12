"""Support for the test-change-signal evidence. Expected values are written by hand from the spec tables; payloads and
architectures are built by hand in the shapes the product reads, so no expectation comes from product output."""
import copy
import json
import shutil
from pathlib import Path

from tests.delta_support import COUNT_KEYS, SYMBOL_COLUMNS, TEST_CASE_COLUMNS, payload, ref_delta, wire
from tests.delta_support import REPO
from tests.rename_delta_support import git, make_repo
from tests.symbol_changes_support import (AMBIGUOUS, DR, EXACT, FI, SC, SI, UNIQUE, UNRESOLVED, analyze, arch, cli_args, entry, rel,
                                          row_of, run_cli, sym)

BASE_COMMIT = '0f17dd29afc6a0d916529c10562e72a1692f8eab'
TEST_FILE = 'file:tests/a.test.ts'


def signals_api():
    import bottlenecks.test_signals as module
    return module


def delta_api():
    import bottlenecks.delta as module
    return module


def symbols_api():
    import bottlenecks.symbols as module
    return module


def branch_count(path, source, line, name):
    return signals_api().branch_count(path, source, line, name)


def cases_of(path, source):
    return signals_api().test_case_table({path: source}, [path])


def case_row(path, source, name):
    rows = [r for r in cases_of(path, source) if r['name'] == name]
    assert len(rows) == 1, (name, [r['id'] for r in cases_of(path, source)])
    return rows[0]


def counts_of(path, source, name):
    row = case_row(path, source, name)
    return row['strong_assertions'], row['weak_assertions'], row['mocks'], row['skipped']


def indent(text, spaces):
    pad = ' ' * spaces
    return ''.join(pad + line if line.strip() else line for line in text.splitlines(True))


def reach_of(nodes, edges=()):
    return signals_api().test_reach(arch(nodes, edges))


def case(ident, file=TEST_FILE, name=None, strong=1, weak=0, mocks=0, skipped=False):
    return {'id': ident, 'file': file, 'name': name or ident.split('#', 1)[-1], 'strong_assertions': strong, 'weak_assertions': weak,
            'mocks': mocks, 'skipped': skipped}


def symbol(ident, file='file:a.py', kind='function', name=None, branches=0, reach='untested', signature=None):
    value = entry(ident, file, kind=kind, name=name or ident.split('#')[-1].split('.')[-1], signature=signature)
    value['branches'] = branches
    value['test_reach'] = reach
    return value


def signal_payload(symbols=None, cases=None, extra_files=(), **kwargs):
    """symbols None omits the symbol table; cases None omits the test case table."""
    data = payload(**kwargs)
    data['candidates'] = copy.deepcopy(data['candidates'])
    network = data['dependency_network']
    files = set(extra_files)
    files |= {s['file'] for s in symbols or []} | {c['file'] for c in cases or []}
    for item in data['candidates']:
        if item['kind'] == 'dependency_cycle':
            files |= set(item['structure']['members'])
    file_ids = sorted(files)
    network['file_ids'] = file_ids
    for item in data['candidates']:
        if item['kind'] == 'dependency_cycle':
            item['evidence'] = [[file_ids.index(e['from_id']), file_ids.index(e['to_id']), ['IMPORTS'], 1.0, 1, e['tier']] for e in item['evidence']]
    if symbols is not None:
        network['symbol_columns'] = list(SYMBOL_COLUMNS)
        network['symbols'] = [row_of(s, file_ids) for s in symbols]
    if cases is not None:
        network['test_case_columns'] = list(TEST_CASE_COLUMNS)
        network['test_cases'] = [[c['id'], file_ids.index(c['file']), c['name'], c['strong_assertions'], c['weak_assertions'],
                                  c['mocks'], c['skipped']] for c in cases]
    return data


def compute(current, baseline, renames=None):
    result = wire(delta_api().compute_delta(current, baseline, renames))
    assert result == wire(ref_delta(current, baseline, renames))
    return result


def applied(*pairs):
    return {'status': 'applied', 'reason': None, 'pairs': [{'from': a, 'to': b, 'similarity': 100} for a, b in pairs]}


def counts(case_item):
    return {key: case_item[key] for key in COUNT_KEYS}


def base_worktree(tmp_dir):
    target = Path(tmp_dir) / 'base-worktree'
    git(REPO, 'worktree', 'add', '--detach', target, BASE_COMMIT)
    return target


def remove_worktree(path):
    git(REPO, 'worktree', 'remove', '--force', path, check=False)
    shutil.rmtree(path, ignore_errors=True)
    git(REPO, 'worktree', 'prune', check=False)


def run_file_granularity(root, directory, cwd, lang, *extra):
    directory.mkdir(parents=True, exist_ok=True)
    args = [root, *lang, '--granularity', 'file', '--json', '-o', directory / 'r.html', '--bottlenecks', directory / 'b.json', *extra]
    done = run_cli(args, cwd=cwd)
    assert done.returncode == 0, done.stderr[-1500:]
    text = (directory / 'b.json').read_text(encoding='utf-8').replace(str(directory), '<out>')
    return json.loads(text)


def decode_symbols(data):
    network = data['dependency_network']
    return [dict(zip(network['symbol_columns'], row)) for row in network['symbols']]


def summary_lines(done):
    out = [line for line in done.stdout.splitlines() if line.startswith('[Δ] Test changes')]
    err = [line for line in done.stderr.splitlines() if 'test changes not compared' in line]
    return out, err

