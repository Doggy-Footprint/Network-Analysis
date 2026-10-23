"""Expected values come from base-commit goldens in tests/report_size_evidence (see its README), from
tests.structure_support's independent reference functions, or are written out by hand. Nothing here
reads product output to derive an expectation."""
import copy
import functools
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

from analysis.edge_weights import default_edge_weights_path, load_edge_weights
from analysis.file_graph import to_file_architecture
from bottlenecks import analyze_bottlenecks, bottlenecks_to_json
from language_analyzers.core.serialization import architecture_to_dict
from language_analyzers.python.graph import PythonGraphAnalyzer
from tests.doc_references_support import without_doc_references
from repository import build_snapshot, default_scan_policy_path, load_scan_policy

REPO = Path(__file__).resolve().parents[1]
EVIDENCE = Path(__file__).parent / 'report_size_evidence'
PROJECT = EVIDENCE / 'project'
MAIN = 'from code_analyzer.cli import main; main()'
CYCLE_KINDS = ('dependency_cycle', 'package_cycle')
CHANGED_KINDS = ('evidence_spread', 'dependency_cycle', 'package_cycle', 'unstable_dependency')
FILE_PAIR_COLUMNS = ['from', 'to', 'relations', 'max_weight', 'evidence_count', 'tier']
PACKAGE_PAIR_COLUMNS = ['from_id', 'to_id', 'relations', 'max_weight', 'evidence_count', 'tier', 'file_pairs']
EVIDENCE_COLUMNS = {'file_pair': FILE_PAIR_COLUMNS, 'package_pair': PACKAGE_PAIR_COLUMNS}


def golden(name):
    return json.loads((EVIDENCE / name).read_text(encoding='utf-8'))


def weights():
    return load_edge_weights(default_edge_weights_path())


def project_files():
    return {path.relative_to(PROJECT).as_posix(): path.read_text(encoding='utf-8') for path in sorted(PROJECT.rglob('*.py'))}


def snapshot_of(files):
    root = Path('/repo')
    return build_snapshot(root, sorted(files), policy=load_scan_policy(default_scan_policy_path()),
                          reader=lambda path: files[path.relative_to(root).as_posix()], ignore_source='test')


@functools.lru_cache(maxsize=None)
def fixture_pipeline():
    """(snapshot, FileArchitecture) of the fixture project, built through public analyzers."""
    files = project_files()
    snap = snapshot_of(files)
    root = Path('/repo')
    return snap, to_file_architecture(PythonGraphAnalyzer(root, snap).analyze(), snap)


def to_payload(snap, arch):
    return json.loads(bottlenecks_to_json(analyze_bottlenecks(snap, arch, weights())))


@functools.lru_cache(maxsize=None)
def _fixture_payload_text():
    snap, arch = fixture_pipeline()
    return bottlenecks_to_json(analyze_bottlenecks(snap, arch, weights()))


def fixture_payload():
    return json.loads(_fixture_payload_text())


def fixture_architecture_dict():
    return json.loads(json.dumps(architecture_to_dict(fixture_pipeline()[1])))


def of_kind(candidates, kind):
    return [item for item in candidates if item['kind'] == kind]


def decode_file_row(row, file_ids):
    """F04: [from, to, relations, max_weight, evidence_count, tier] -> the v8 record fields (no detail_edge_indices)."""
    assert isinstance(row, list) and len(row) == len(FILE_PAIR_COLUMNS), row
    return {'from_id': file_ids[row[0]], 'to_id': file_ids[row[1]], 'relations': row[2], 'max_weight': row[3],
            'evidence_count': row[4], 'tier': row[5]}


def decode_package_row(row, file_ids):
    """F05: [from_id, to_id, relations, max_weight, evidence_count, tier, file_pairs] -> v8 record fields."""
    assert isinstance(row, list) and len(row) == len(PACKAGE_PAIR_COLUMNS), row
    return {'from_id': row[0], 'to_id': row[1], 'relations': row[2], 'max_weight': row[3], 'evidence_count': row[4],
            'tier': row[5], 'file_pairs': [[file_ids[a], file_ids[b]] for a, b in row[6]]}


def decode_evidence(candidate, file_ids):
    kind = candidate['kind']
    if kind in ('dependency_cycle', 'unstable_dependency'):
        return [decode_file_row(row, file_ids) for row in candidate['evidence']]
    if kind == 'package_cycle':
        return [decode_package_row(row, file_ids) for row in candidate['evidence']]
    return candidate['evidence']


def encode_candidates_v9(candidates, file_ids):
    """v8-shaped hand-made candidates -> v9 evidence (used to re-express legacy test inputs and baselines in v9)."""
    index = {file_id: i for i, file_id in enumerate(file_ids)}
    result = copy.deepcopy(candidates)
    for item in result:
        kind = item['kind']
        if kind in ('dependency_cycle', 'unstable_dependency'):
            item['evidence'] = [[index[r['from_id']], index[r['to_id']], r['relations'], r['max_weight'], r['evidence_count'], r['tier']]
                                for r in item['evidence']]
        elif kind == 'package_cycle':
            item['evidence'] = [[r['from_id'], r['to_id'], r['relations'], r['max_weight'], r['evidence_count'], r['tier'],
                                 [[index[a], index[b]] for a, b in r['file_pairs']]] for r in item['evidence']]
        elif kind == 'evidence_spread':
            item['evidence'] = sorted({r['detail_edge_index'] for r in item['evidence']})
    return result


def to_v9_payload(payload, details_file=None):
    """A v8 bottlenecks payload (as the base commit wrote it) -> the equivalent v9 payload, by the F02-F05 encoding."""
    result = copy.deepcopy(payload)
    network = result['dependency_network']
    file_ids = sorted(network['node_metrics'])
    result['schema'] = 'bottlenecks.v9'
    network['file_ids'] = file_ids
    network['evidence_columns'] = copy.deepcopy(EVIDENCE_COLUMNS)
    result['candidates'] = encode_candidates_v9(result['candidates'], file_ids)
    if details_file is not None:
        result['details_file'] = details_file
    return result


def to_v8_payload(payload, details):
    """Inverse of to_v9_payload given the details: decodes v9 evidence back to base-commit records."""
    result = without_doc_references(payload)
    network = result['dependency_network']
    file_ids = network.pop('file_ids')
    network.pop('evidence_columns')
    result.pop('details_file', None)
    result['schema'] = 'bottlenecks.v8'
    groups = {}
    for item in result['candidates']:
        if item['kind'] in ('dependency_cycle', 'unstable_dependency', 'package_cycle'):
            decoded = decode_evidence(item, file_ids)
            item['evidence'] = decoded
        elif item['kind'] == 'evidence_spread':
            item['evidence'] = [spread_record(details['edges'][i], i, groups) for i in item['evidence']]
    if groups:
        network['candidate_groups'] = {**network.get('candidate_groups', {}), **groups}
    return result


def spread_record(edge, index, groups=None):
    """v8 evidence_spread record: the detail edge plus its evidence location and its index. An edge with candidates is
    interned into `groups` ({id: {"candidates", "to_id"}}) as the base commit did (id = "cg:" + sha256 of the compact,
    key-sorted JSON of the group)."""
    evidence = edge['evidence']
    record = dict(edge, path=evidence['file_path'], start_line=evidence['start_line'], end_line=evidence['end_line'], detail_edge_index=index)
    if groups is not None and edge.get('candidates'):
        group = {'candidates': edge['candidates'], 'to_id': edge['to_id']}
        ident = 'cg:' + hashlib.sha256(json.dumps(group, sort_keys=True, separators=(',', ':')).encode('utf-8')).hexdigest()
        groups[ident] = group
        del record['candidates']
        record['candidate_group_id'] = ident
    return record


def run_cli(*args, cwd=REPO, seed='0'):
    command = [sys.executable, '-c', MAIN, *map(str, args)]
    return subprocess.run(command, cwd=cwd, env=dict(os.environ, PYTHONHASHSEED=seed), capture_output=True, text=True)


def run_cli_ok(*args, **kwargs):
    done = run_cli(*args, **kwargs)
    assert done.returncode == 0, done.stderr[-2000:]
    return done


def cli_fixture_run(directory, *, json_flag=True, bottlenecks='bn/b.json', granularity='file', html='report.html', seed='0'):
    """Runs the CLI on the fixture project; returns the output directory."""
    directory = Path(directory)
    (directory / 'bn').mkdir(parents=True, exist_ok=True)
    args = [PROJECT, '-l', 'python', '-o', directory / html]
    if granularity != 'file':
        args += ['--granularity', granularity]
    if json_flag:
        args.append('--json')
    if bottlenecks:
        args += ['--bottlenecks', directory / bottlenecks]
    run_cli_ok(*args, seed=seed)
    return directory


def is_compact(text):
    """F07/F08: json.dumps(..., separators=(',', ':')) layout (key order is whatever the file holds)."""
    value = json.loads(text)
    return text.rstrip('\n') == json.dumps(value, separators=(',', ':'), ensure_ascii=False)


def inline_data(html_path):
    found = re.search(r'<script[^>]*id="report-data"[^>]*>(.*?)</script>', Path(html_path).read_text(encoding='utf-8'), re.S)
    assert found
    return json.loads(found.group(1))


def legacy_v8(payload, arch=None):
    """The standalone report.bottlenecks renderer only reads bottlenecks.v6-v8; tests of its validator/labels feed it the
    v8 form of a pipeline payload (decoded by the F02-F05 inverse)."""
    details = json.loads(json.dumps(architecture_to_dict(arch)['details'])) if arch is not None else {'edges': []}
    return to_v8_payload(payload, details)


def with_v8_spread(payload, arch):
    """Copy of a v9 payload whose evidence_spread evidence is expanded back to base-commit records (F03 inverse),
    so legacy assertions about the located evidence keep their meaning."""
    details = json.loads(json.dumps(architecture_to_dict(arch)['details']))
    result = copy.deepcopy(payload)
    for item in result['candidates']:
        if item['kind'] == 'evidence_spread':
            item['evidence'] = [spread_record(details['edges'][i], i) for i in item['evidence']]
    return result


def legacy_architecture_text(report_text, details_text):
    """report.json (schema 7, compact) + details file -> the base-commit report.json text (schema 6, indent=2)."""
    report = json.loads(report_text)
    report.pop('details_file')
    report['schema_version'] = '6'
    report['details'] = without_doc_references(json.loads(details_text))
    return json.dumps(report, indent=2, ensure_ascii=False)


TIER_RANK = {'certain': 0, 'resolved': 1, 'all': 2}


def edge_tier(edge):
    """Structure tier of a file-level edge dict (F04 tier rule: certain = static_certain+exact; resolved = exact/unique_name; else all)."""
    if edge['confidence'] == 'static_certain' and edge['resolution'] == 'exact':
        return 'certain'
    return 'resolved' if edge['resolution'] in ('exact', 'unique_name') else 'all'


def restore_detail_edge_indices(v8_payload, file_edges):
    """D02: v8 `detail_edge_indices` of a cycle/unstable row = union of the detail indices of the file edges of that pair
    whose tier is not looser than the cycle's tier (unstable_dependency pairs aggregate every tier)."""
    for item in v8_payload['candidates']:
        if item['kind'] not in ('dependency_cycle', 'unstable_dependency'):
            continue
        limit = TIER_RANK['all' if item['kind'] == 'unstable_dependency' else item['structure']['tier']]
        for record in item['evidence']:
            found = set()
            for edge in file_edges:
                if (edge['from_id'], edge['to_id']) == (record['from_id'], record['to_id']) and edge['relation'] != 'TESTS' \
                        and TIER_RANK[edge_tier(edge)] <= limit:
                    found.update(edge['metadata']['detail_edge_indices'])
            record['detail_edge_indices'] = sorted(found)
    return v8_payload


def legacy_bottlenecks_canonical(bn_path, report_path):
    """Canonical bytes (sorted keys, compact, trailing newline) of the v8 form, the layout base_form_bytes expects."""
    return (json.dumps(json.loads(legacy_bottlenecks_text(bn_path, report_path)), sort_keys=True, separators=(',', ':'), ensure_ascii=False,
                       allow_nan=False) + '\n').encode('utf-8')


def legacy_bottlenecks_text(bn_path, report_path):
    """A v9 bottlenecks.json with its details file and report.json -> compact JSON of the full v8 form."""
    bn_path = Path(bn_path)
    payload = json.loads(bn_path.read_text(encoding='utf-8'))
    details = json.loads((bn_path.parent / payload['details_file']).read_text(encoding='utf-8'))
    restored = restore_detail_edge_indices(to_v8_payload(payload, details), json.loads(Path(report_path).read_text(encoding='utf-8'))['edges'])
    return json.dumps(restored, ensure_ascii=False)


def legacy_v8_full(payload, architecture):
    """v9 payload + the architecture_to_dict result (details and file edges) -> the complete base-commit v8 payload."""
    return restore_detail_edge_indices(to_v8_payload(payload, architecture['details']), architecture['edges'])


def as_v9(bottlenecks):
    """Hand-built v8-layout file payloads (browser fixtures) -> bottlenecks.v9 by the F02-F05 encoding; anything else unchanged.
    File ids that the fixture references but node_metrics lacks are appended so every row index resolves."""
    if not isinstance(bottlenecks, dict) or bottlenecks.get('schema') != 'bottlenecks.v8' or bottlenecks.get('granularity') != 'file':
        return bottlenecks
    result = copy.deepcopy(bottlenecks)
    network = result['dependency_network']
    file_ids = sorted(network.get('node_metrics', {}))
    known = set(file_ids)
    extra = set()
    for item in result['candidates']:
        evidence = item.get('evidence')
        if item['kind'] in ('dependency_cycle', 'unstable_dependency'):
            extra.update(r[key] for r in evidence for key in ('from_id', 'to_id'))
        elif item['kind'] == 'package_cycle':
            for r in evidence:
                r.setdefault('file_pairs', [])
            extra.update(f for r in evidence for pair in r['file_pairs'] for f in pair)
    file_ids += sorted(extra - known)
    result['schema'] = 'bottlenecks.v9'
    network['file_ids'] = file_ids
    network['evidence_columns'] = copy.deepcopy(EVIDENCE_COLUMNS)
    for item in result['candidates']:
        if item['kind'] == 'evidence_spread':
            item['evidence'] = [r['detail_edge_index'] if isinstance(r, dict) and 'detail_edge_index' in r else i for i, r in enumerate(item['evidence'])]
    others = copy.deepcopy(result['candidates'])
    result['candidates'] = [item for item in encode_candidates_v9([c for c in others if c['kind'] != 'evidence_spread'], file_ids)] + \
        [c for c in others if c['kind'] == 'evidence_spread']
    result['candidates'].sort(key=lambda c: [x['id'] for x in bottlenecks['candidates']].index(c['id']))
    return result
