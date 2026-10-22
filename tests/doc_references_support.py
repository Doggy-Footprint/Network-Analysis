"""Support for spec 64deae051d59caac v1 (doc code references).
Expected rows in the tests are written out by hand from the spec rules; nothing here derives an expectation from the product."""
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

from repository.models import ExcludedFile, RepositorySnapshot

REPO = Path(__file__).resolve().parents[1]
EVIDENCE = Path(__file__).parent / 'doc_references_evidence'
FIXTURES = REPO / '.fixtures'
MAIN = 'from code_analyzer.cli import main; main()'
BASE_COMMIT = '7d169832420840158671369992f392d025284ff4'
COLUMNS = ['doc', 'line', 'notation', 'text', 'status', 'target', 'target_kind', 'candidates', 'candidate_total']
OLD_ANALYSIS = '6'
NEW_ANALYSIS = '7'
NEW_KIND = 'dangling_doc_reference'

K_CONFIGS = {
    'K1': ('fastapi-realworld', ['-f', 'fastapi'], 'file'),
    'K2': ('typescript-nestjs-realworld', ['-f', 'nestjs'], 'file'),
    'K3': ('android-nowinandroid', ['-f', 'android'], 'file'),
    'K4': ('futuramaapi', ['-f', 'fastapi'], 'file'),
    'K5': ('fastapi-realworld', ['-f', 'fastapi'], 'symbol'),
}


def snap(files, excluded=(), root='/dr-oracle'):
    return RepositorySnapshot(root=root, ignore_source='provided', contents=tuple(files.items()),
                              excluded_files=tuple(ExcludedFile(p, 'binary') for p in excluded))


def sym(ident, kind, label, symbol_path=None, metadata=None):
    return {'id': ident, 'kind': kind, 'label': label, 'symbol_path': symbol_path, 'metadata': metadata if metadata is not None else {}}


def gradle(path, module_dir='<default>'):
    metadata = {'build_system': 'gradle', 'module_path': path}
    if module_dir != '<default>':
        if module_dir is not None:
            metadata['module_dir'] = module_dir
    else:
        metadata['module_dir'] = path.strip(':').replace(':', '/')
    return sym('build-module:gradle:' + path, 'module', path, None, metadata)


def details_of(nodes=(), file_paths=()):
    file_nodes = {f'file:{p}': {'id': f'file:{p}', 'kind': 'file', 'label': p, 'symbol_path': None, 'metadata': {}} for p in file_paths}
    return {'nodes': list(nodes) + list(file_nodes.values()), 'file_nodes': file_nodes}


def row(doc, line, notation, text, status, target=None, target_kind=None, candidates=None, total=None):
    return [doc, line, notation, text, status, target, target_kind, candidates, total]


def analyze(files, nodes=(), file_paths=(), excluded=()):
    from analysis.doc_references import analyze_doc_references
    return analyze_doc_references(snap(files, excluded), details_of(nodes, file_paths))


def rows_of(files, nodes=(), file_paths=(), excluded=()):
    table, _candidates, _summary = analyze(files, nodes, file_paths, excluded)
    assert table['columns'] == COLUMNS
    return table['rows']


def candidate_id(doc):
    return 'b:' + hashlib.sha256((doc + '|dangling_doc').encode('utf-8')).hexdigest()[:16]


def canonical_sha(value):
    text = json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False)
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def run_cli(root, out_dir, flags, granularity, name='a', env_extra=None, cwd=REPO):
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    command = [sys.executable, '-c', MAIN, str(root), *flags, '--granularity', granularity, '--json',
               '-o', str(out / f'{name}.html'), '--bottlenecks', str(out / f'{name}_b.json')]
    done = subprocess.run(command, cwd=cwd, env=dict(os.environ, PYTHONHASHSEED='0', **(env_extra or {})),
                          capture_output=True, text=True)
    assert done.returncode == 0, done.stderr[-2000:]
    load = lambda p: json.loads(Path(p).read_text(encoding='utf-8'))
    details = out / f'{name}.details.json'
    return load(out / f'{name}_b.json'), (load(details) if details.exists() else None), load(out / f'{name}.json')


def comparable(bottlenecks, details, report):
    """Hash views of the parts F14 keeps equal: every bottleneck top-level key, every dependency_network key, every details key,
    and the architecture report (graph) JSON."""
    network = bottlenecks['dependency_network']
    return {
        'bottlenecks': {key: canonical_sha(value) for key, value in bottlenecks.items() if key != 'dependency_network'},
        'network': {key: canonical_sha(value) for key, value in network.items()},
        'candidate_count': len(bottlenecks['candidates']),
        'details': None if details is None else {key: canonical_sha(value) for key, value in details.items()},
        'report': canonical_sha(report),
    }


def strip_new(bottlenecks, details):
    """Removes only what the spec adds and sets versions.analysis back to the base value."""
    bottlenecks = json.loads(json.dumps(bottlenecks))
    details = json.loads(json.dumps(details))
    assert bottlenecks['versions']['analysis'] == NEW_ANALYSIS
    bottlenecks['versions']['analysis'] = OLD_ANALYSIS
    bottlenecks['coverage'].pop('doc_references', None)
    bottlenecks['candidates'] = [c for c in bottlenecks['candidates'] if c['kind'] != NEW_KIND]
    details.pop('doc_references', None)
    return bottlenecks, details


def without_doc_references(payload):
    """Copy of a bottleneck payload (or details dict) with what spec 64deae051d59caac adds removed and versions.analysis set
    back to the base value, so legacy comparisons against base-commit evidence keep their original meaning."""
    result = json.loads(json.dumps(payload))
    if 'candidates' in result:
        result['candidates'] = [c for c in result['candidates'] if c.get('kind') != NEW_KIND]
    if isinstance(result.get('coverage'), dict):
        result['coverage'].pop('doc_references', None)
    if isinstance(result.get('versions'), dict) and result['versions'].get('analysis') == NEW_ANALYSIS:
        result['versions']['analysis'] = OLD_ANALYSIS
    result.pop('doc_references', None)
    return result


def base_symbol_bytes(data):
    """Symbol-mode output differs from the base commit only in versions.analysis (F12); restores that one value in the bytes."""
    for new, old in ((b'"analysis":"7"', b'"analysis":"6"'), (b'"analysis": "7"', b'"analysis": "6"')):
        if data.count(new) == 1:
            return data.replace(new, old)
    raise AssertionError('versions.analysis "7" not found exactly once')
