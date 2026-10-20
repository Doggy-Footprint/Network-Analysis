"""Oracle (d) disables the feature by replacing bottlenecks.reach.reach_candidates with a function returning []
(analyze_bottlenecks imports it at call time) and compares the remaining candidates."""
import json, random, sys, tempfile, time
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from tests.reach_support import Graph, E, graph_model, ref_untested_hubs, ref_isolated, weights_with, pagerank_of
from bottlenecks import analyze_bottlenecks, bottlenecks_to_json, BottleneckInputError
import bottlenecks.reach as reach_mod

SEED, N = 20261019, int(sys.argv[2])
rnd = random.Random(SEED)
CATS = ['production'] * 5 + ['test', 'generated', 'vendored']
EXTS = ['py', 'ts', 'tsx', 'js', 'kt', 'yaml', 'md']
RELS = ['IMPORTS', 'CALLS', 'TESTS', 'TYPE_USES', 'INHERITS']
CONF = ['static_certain', 'static_inferred', 'framework_inferred', 'dynamic_required']
RES = ['exact', 'unique_name', 'ambiguous', 'unresolved']
tmp = Path(tempfile.mkdtemp())
[(tmp / str(n)).mkdir() for n in range(1, 21)]
weights = {n: weights_with(tmp / str(n), untested_hub_top_n=n) for n in range(1, 21)}
violations, crashes, execs = [], 0, 0
start = time.time()
for i in range(N):
    nf = rnd.randint(1, 60)
    files = {}
    for k in range(nf):
        cat = rnd.choice(CATS)
        d = {'test': 'tests/', 'generated': 'generated/', 'vendored': 'vendor/'}.get(cat, 'src/')
        name = ('test_f%d' % k) if cat == 'test' else 'f%d' % k
        files[d + name + '.' + rnd.choice(EXTS)] = (cat, rnd.choice([0, 1, 2, 5, 40]))
    boundary = tuple('ext:m%d' % k for k in range(rnd.randint(0, 3)))
    names = list(files) + list(boundary)
    edges = []
    for _ in range(rnd.randint(0, nf * 3)):
        res = rnd.choice(RES)
        cands = tuple(rnd.sample(names, min(len(names), rnd.randint(1, 3)))) if res == 'ambiguous' or rnd.random() < 0.2 else ()
        edges.append(E(rnd.choice(names), rnd.choice(names), rnd.choice(RELS), rnd.choice(CONF), res, cands))
    g = Graph(files, edges, boundary)
    top_n = rnd.randint(1, 20)
    execs += 1
    try:
        report = json.loads(bottlenecks_to_json(analyze_bottlenecks(*g.snapshot_and_architecture(), weights[top_n])))
    except BottleneckInputError:
        continue
    except Exception as exc:
        crashes += 1
        violations.append((i, 'a', repr(exc)[:200])); continue
    cands = report['candidates']
    hubs = [c for c in cands if c['kind'] == 'untested_hub']
    iso = {c['target'] for c in cands if c['kind'] == 'isolated_node'}
    model = graph_model(g)
    if len(hubs) > top_n: violations.append((i, 'b', len(hubs)))
    ref_iso = set(ref_isolated(model))
    if not iso <= ref_iso or iso != ref_iso: violations.append((i, 'c', sorted(iso ^ ref_iso)[:3]))
    ref_h = set(ref_untested_hubs(model, pagerank_of(report), top_n))
    if {c['target'] for c in hubs} != ref_h: violations.append((i, 'c-hub', sorted({c['target'] for c in hubs} ^ ref_h)[:3]))
    orig = reach_mod.reach_candidates
    reach_mod.reach_candidates = lambda *a, **k: []
    try:
        import bottlenecks.core as core
        saved = getattr(core, 'reach_candidates', None)
        if saved is not None: core.reach_candidates = reach_mod.reach_candidates
        base = json.loads(bottlenecks_to_json(analyze_bottlenecks(*g.snapshot_and_architecture(), weights[top_n])))['candidates']
    finally:
        reach_mod.reach_candidates = orig
        if saved is not None: core.reach_candidates = saved
    if [c for c in cands if c['kind'] not in ('untested_hub', 'isolated_node')] != base:
        violations.append((i, 'd', 'base candidates differ'))
print(json.dumps({'seed': SEED, 'execs': execs, 'crashes': crashes, 'violations': len(violations), 'first': violations[:5], 'seconds': round(time.time() - start, 1)}))
