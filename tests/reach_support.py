"""Reference functions for untested_hub / isolated_node use different algorithms from the product on purpose
(brute-force per-file edge scans for isolation, a full sort for hubs), and categories are declared by the test
builder, not derived from path rules. Expected values come from spec 74b78d6823637a21 v1 only."""
import copy
import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path

from analysis.file_graph import FileArchitecture
from language_analyzers.core.graph_models import GraphEdge, GraphNode, NodeCost, SourceSpan
from tests.edge_weights_support import load_weights, weights_data
from tests.file_analysis_support import snapshot

REPO = Path(__file__).resolve().parents[1]
EVIDENCE = Path(__file__).parent / 'reach_evidence'
MANIFEST_PATH = EVIDENCE / 'base_manifest.json'
BASE_COMMIT = '6444895451a89f4450b9123b7beb17b11506e534'
FIXTURES = ('futuramaapi', 'fastapi-realworld', 'android-nowinandroid', 'typescript-nestjs-realworld')
NEW_KINDS = ('untested_hub', 'isolated_node')
SC, SI, FI, DR = 'static_certain', 'static_inferred', 'framework_inferred', 'dynamic_required'
EXACT, UNIQUE, AMBIGUOUS, UNRESOLVED = 'exact', 'unique_name', 'ambiguous', 'unresolved'
CONFIDENCES = (SC, SI, FI, DR)
STATIC = (SC, SI)
CERTAIN_RESOLUTIONS = (EXACT, UNIQUE)
ISOLATION_EXTENSIONS = ('py', 'ts', 'tsx', 'js', 'jsx', 'mjs', 'cjs', 'kt')

# Paths whose category is declared here; the product's own path rules are cross-checked in test_reach_candidates.
CATEGORY_DIRS = {'production': 'src', 'test': 'tests', 'generated': 'migrations', 'vendored': 'vendor'}


def load_manifest():
    return json.loads(MANIFEST_PATH.read_text(encoding='utf-8'))


def canonical_sha(value):
    text = json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False)
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def sha16(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()[:16]


def candidate_id(file_id, kind):
    return 'b:' + sha16(f'{file_id}|{kind}')


def fid(path):
    return 'file:' + path


@dataclass
class E:
    """File-level edge between 'file' paths, boundary ids, or the same path (self edge)."""
    source: str
    target: str
    relation: str = 'IMPORTS'
    confidence: str = SC
    resolution: str = EXACT
    candidates: tuple = ()


@dataclass
class Graph:
    """files: {path: (category, line_count)}; boundary: ids of external nodes (no 'file:' prefix)."""
    files: dict
    edges: list = field(default_factory=list)
    boundary: tuple = ()

    def ident(self, name):
        return name if name in self.boundary else fid(name)

    def category(self, name):
        return 'boundary' if name in self.boundary else self.files[name][0]

    def snapshot_and_architecture(self):
        contents = {path: 'x\n' * lines for path, (_, lines) in self.files.items()}
        snap = snapshot(contents)
        flags_of = {'production': [], 'test': ['test'], 'generated': ['generated'], 'vendored': ['vendored']}
        nodes = []
        for path, (category, lines) in self.files.items():
            meta = {'file_path': path, 'granularity': 'file'}
            nodes.append(GraphNode(fid(path), path, 'file', 'file', kind='file', language=path.rsplit('.', 1)[-1],
                                   span=SourceSpan(path, 1, lines) if lines else None, symbol_path=path,
                                   cost=NodeCost(lines, 2 * lines, lines),
                                   flags=list(flags_of[category]), provenance='file-aggregation', metadata=meta))
        for name in self.boundary:
            nodes.append(GraphNode(name, name, 'module', 'module', kind='module', provenance='python-core', cost=NodeCost(0, 0, 0),
                                   metadata={'file_path': name, 'granularity': 'file', 'boundary': True}))
        edges = []
        for index, e in enumerate(self.edges):
            edges.append(GraphEdge(self.ident(e.source), self.ident(e.target), e.relation, confidence=e.confidence,
                                   resolution=e.resolution, candidates=[self.ident(c) for c in e.candidates],
                                   metadata={'detail_edge_indices': [index], 'evidence_count': 1}))
        detail = {'nodes': [], 'edges': [], 'node_files': {}, 'node_owners': {}, 'file_nodes': {}}
        return snap, FileArchitecture('oracle', snap.root, nodes, edges, {}, [], detail, 'file')


def weights_with(tmp_path, **top_level):
    return load_weights(tmp_path, weights_data(**top_level))


def run_report(graph, weights):
    from bottlenecks import analyze_bottlenecks, bottlenecks_to_json
    snap, arch = graph.snapshot_and_architecture()
    return json.loads(bottlenecks_to_json(analyze_bottlenecks(snap, arch, weights)))


def of_kind(candidates, kind):
    return [c for c in candidates if c['kind'] == kind]


def pagerank_of(report):
    metrics = report['dependency_network']['node_metrics']
    return {name: row['pagerank'] for name, row in metrics.items()}


# ---------------------------------------------------------------- neutral model for the references

@dataclass
class Model:
    """files: {file id: (category, line_count)}; edges: [(source id, target id, relation, confidence, resolution,
    candidate ids)]. Any edge endpoint that is not a key of files is a boundary (external) node."""
    files: dict
    edges: list


def graph_model(graph):
    files = {fid(path): (category, lines) for path, (category, lines) in graph.files.items()}
    edges = [(graph.ident(e.source), graph.ident(e.target), e.relation, e.confidence, e.resolution,
              tuple(graph.ident(c) for c in e.candidates)) for e in graph.edges]
    return Model(files, edges)


def _value(item):
    return getattr(item, 'value', item)


def architecture_model(arch):
    """Model of a real FileArchitecture; the category comes from the node flags the file converter assigned."""
    files = {}
    for node in arch.nodes:
        if node.kind != 'file' or (node.metadata or {}).get('boundary'):
            continue
        flags = set(node.flags or ())
        category = 'test' if 'test' in flags else 'vendored' if 'vendored' in flags else 'generated' if flags & {'generated', 'migration'} else 'production'
        files[node.id] = (category, node.cost.line_count)
    edges = [(e.from_id, e.to_id, e.relation, _value(e.confidence), _value(e.resolution), tuple(e.candidates or ()))
             for e in arch.edges]
    return Model(files, edges)


def record_key(edge):
    """Identity of an edge record (dict from JSON) comparable with Model edge tuples."""
    return (edge['from_id'], edge['to_id'], edge['relation'], edge['confidence'], edge['resolution'])


def model_key(edge):
    return edge[:5]


# ---------------------------------------------------------------- reference: hubs (full sort)

def ref_hub_pool(model):
    return [ident for ident, (category, _) in model.files.items() if category == 'production']


def ref_hubs(model, pagerank, top_n):
    """Full sort of the whole pool by (-pagerank, id); returns [(file id, 1-based rank)] for the first top_n."""
    ordered = sorted(ref_hub_pool(model), key=lambda ident: (-pagerank[ident], ident))
    return [(ident, position + 1) for position, ident in enumerate(ordered)][:top_n]


def ref_global_ranks(model, pagerank, file_id):
    """{rank among file nodes, rank among every scored node incl. boundary} by (-pagerank, id); the spec does not say
    which population pagerank_rank counts, so callers assert rank only where all readings agree."""
    def rank(population):
        return sorted(population, key=lambda ident: (-pagerank[ident], ident)).index(file_id) + 1
    return {rank(list(model.files)), rank(list(pagerank))}


def ref_incoming_tests(model, file_id, any_origin=False):
    """(confirmed count, indices of uncertain TESTS edges). Confirmed edges must come from test-category files; R3 does
    not say whether uncertain edges from other categories count, so any_origin exposes the other reading."""
    confirmed, uncertain = 0, []
    for index, (source, target, relation, _conf, resolution, candidates) in enumerate(model.edges):
        from_test = model.files.get(source, ('', 0))[0] == 'test'
        if relation != 'TESTS':
            continue
        if from_test and target == file_id and resolution in CERTAIN_RESOLUTIONS:
            confirmed += 1
        elif (from_test or any_origin) and resolution in (AMBIGUOUS, UNRESOLVED) and (target == file_id or (resolution == AMBIGUOUS and file_id in candidates)):
            uncertain.append(index)
    return confirmed, uncertain


def ref_untested_hubs(model, pagerank, top_n):
    """{file id: (pool rank, uncertain TESTS edge indices)}"""
    found = {}
    for ident, rank in ref_hubs(model, pagerank, top_n):
        confirmed, uncertain = ref_incoming_tests(model, ident)
        if confirmed == 0:
            found[ident] = (rank, uncertain)
    return found


# ---------------------------------------------------------------- reference: isolation (per-file scan)

def isolation_eligible(file_id, category, lines):
    name = file_id.rsplit('/', 1)[-1]
    return category == 'production' and lines >= 1 and '.' in name and name.rsplit('.', 1)[-1] in ISOLATION_EXTENSIONS


def ref_isolated(model):
    """{file id: (framework, dynamic, uncertain_static, evidence edge indices)}; one full edge scan per file."""
    found = {}
    for me, (category, lines) in model.files.items():
        if not isolation_eligible(me, category, lines):
            continue
        connections, framework, dynamic, uncertain, indices = 0, 0, 0, 0, []
        for index, (source, target, _rel, confidence, resolution, _cands) in enumerate(model.edges):
            if me not in (source, target) or source == target:
                continue
            other = target if source == me else source
            if other not in model.files or model.files[other][0] != 'production':
                continue
            if confidence in STATIC and resolution in CERTAIN_RESOLUTIONS:
                connections += 1
            elif confidence == FI:
                framework += 1
                indices.append(index)
            elif confidence == DR:
                dynamic += 1
                indices.append(index)
            elif confidence in STATIC and resolution in (AMBIGUOUS, UNRESOLVED):
                uncertain += 1
                indices.append(index)
        if connections == 0:
            found[me] = (framework, dynamic, uncertain, indices)
    return found


def ref_base_candidates(candidates):
    return [c for c in candidates if c['kind'] not in NEW_KINDS]


def without_reach(payload):
    """Drops what the feature adds so legacy comparisons keep their original meaning."""
    result = copy.deepcopy(payload)
    result['candidates'] = ref_base_candidates(result.get('candidates', []))
    network = result.get('dependency_network')
    if isinstance(network, dict) and isinstance(network.get('edge_weights'), dict):
        network['edge_weights'].pop('untested_hub_top_n', None)
    if isinstance(result.get('edge_weights'), dict):
        result['edge_weights'].pop('untested_hub_top_n', None)
    return result
