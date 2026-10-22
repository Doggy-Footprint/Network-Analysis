import pytest

from analysis.structure import analyze_structure, package_assignments
from tests.structure_support import (AMBIGUOUS, EXACT, SC, SI, UNIQUE, architecture, cycle_id, cycle_target, cycles_by_key, dedge,
                                     default_weights, dnode, fedge, fid, of_kind, python_modules, unstable_id)


def run(paths, edges, **kwargs):
    return analyze_structure(architecture(paths, edges, **kwargs), default_weights())


def language(arch):
    return package_assignments(arch)['language']


def test_V04_python_packages_C08():
    modules = {'pkg/__init__.py': 'pkg', 'pkg/a.py': 'pkg.a', 'top.py': 'top', 'pkg/sub/deep.py': 'pkg.sub.deep',
               'pkg/sub/__init__.py': 'pkg.sub'}
    dnodes, files = python_modules(modules)
    paths = list(modules) + ['pkg/nomod.py', 'docs/README.md', 'LICENSE']
    assigned = language(architecture(paths, dnodes=dnodes, node_files=files))
    assert assigned == {
        fid('pkg/__init__.py'): ['pkg:python:pkg'],        # __init__.py: the module name itself
        fid('pkg/a.py'): ['pkg:python:pkg'],               # pkg.a minus last element
        fid('top.py'): ['pkg:python:(root)'],              # no dot
        fid('pkg/sub/deep.py'): ['pkg:python:pkg.sub'],
        fid('pkg/sub/__init__.py'): ['pkg:python:pkg.sub'],
        fid('pkg/nomod.py'): ['pkg:dir:pkg'],              # python file without module node falls back to the directory
        fid('docs/README.md'): ['pkg:dir:docs'],           # non-code file
        fid('LICENSE'): ['pkg:dir:.'],                     # root file
    }


@pytest.mark.parametrize('variant', ['empty-string', 'none', 'missing-key'])
def test_V04_python_module_without_symbol_path_uses_id_without_prefix(variant):
    module = dnode('py:app.web.views', 'module', 'python-core', symbol_path='')
    if variant == 'none':
        module['symbol_path'] = None
    elif variant == 'missing-key':
        del module['symbol_path']
    arch = architecture(['app/web/views.py'], dnodes=[module], node_files={'py:app.web.views': 'app/web/views.py'})
    assert language(arch) == {fid('app/web/views.py'): ['pkg:python:app.web']}


def test_V04_python_symbol_path_wins_over_id():
    module = dnode('py:wrong.name', 'module', 'python-core', symbol_path='right.name')
    arch = architecture(['right/name.py'], dnodes=[module], node_files={'py:wrong.name': 'right/name.py'})
    assert language(arch) == {fid('right/name.py'): ['pkg:python:right']}


def test_V04_python_class_nodes_do_not_define_packages():
    clazz = dnode('py:pkg.a#X', 'class', 'python-core', symbol_path='pkg.a.X')
    arch = architecture(['pkg/a.py'], dnodes=[clazz], node_files={'py:pkg.a#X': 'pkg/a.py'})
    assert language(arch) == {fid('pkg/a.py'): ['pkg:dir:pkg']}


def kotlin_arch():
    paths = ['x/Y.kt', 'com/a/b/Q.kt', 'Z.kt', 'k/NoEdge.kt']
    dnodes, dedges, files = [], [], {}
    for path, package in (('x/Y.kt', 'com.a.b'), ('com/a/b/Q.kt', 'other.pkg'), ('Z.kt', '<default>')):
        file_id = 'kotlin:' + path
        dnodes += [dnode(file_id, 'file', 'kotlin-core'), dnode('kotlin-package:' + package, 'module', 'kotlin-core')]
        dedges.append(dedge('kotlin-package:' + package, file_id, 'CONTAINS'))
        files[file_id] = path
    dnodes.append(dnode('kotlin:k/NoEdge.kt', 'file', 'kotlin-core'))
    files['kotlin:k/NoEdge.kt'] = 'k/NoEdge.kt'
    dnodes.append(dnode('kotlin:x/Y.kt#Y', 'class', 'kotlin-core'))
    files['kotlin:x/Y.kt#Y'] = 'x/Y.kt'
    dedges.append(dedge('kotlin:x/Y.kt', 'kotlin:x/Y.kt#Y', 'DECLARES'))
    return architecture(paths, dnodes=dnodes, dedges=dedges, node_files=files)


def test_V04_kotlin_packages_C09():
    assert language(kotlin_arch()) == {
        fid('x/Y.kt'): ['pkg:kotlin:com.a.b'],            # directory x is irrelevant
        fid('com/a/b/Q.kt'): ['pkg:kotlin:other.pkg'],    # directory com/a/b does not decide it either
        fid('Z.kt'): ['pkg:kotlin:<default>'],            # F07 takes <name> from the kotlin-package id verbatim
        fid('k/NoEdge.kt'): ['pkg:dir:k'],                # kotlin file without kotlin-package CONTAINS edge
    }


def test_V04_typescript_packages_use_directories_C10():
    paths = ['src/a/b.ts', 'main.ts', 'src/a/c.tsx']
    modules = [dnode('ts:' + p, 'module', 'typescript-core') for p in paths]
    arch = architecture(paths, dnodes=modules, node_files={m['id']: p for m, p in zip(modules, paths)})
    assert language(arch) == {fid('src/a/b.ts'): ['pkg:dir:src/a'], fid('main.ts'): ['pkg:dir:.'], fid('src/a/c.tsx'): ['pkg:dir:src/a']}


def test_V04_every_file_has_exactly_one_language_package():
    arch = kotlin_arch()
    assigned = language(arch)
    assert set(assigned) == {n.id for n in arch.nodes}
    assert all(len(v) == 1 for v in assigned.values())


def test_V04_framework_key_exists_only_with_nestjs_modules():
    arch = architecture(['a.py'])
    assert set(package_assignments(arch)) == {'language'}


def nest_node(kind, path, name):
    return dnode(f'nestjs:{kind}:{path}#{name}', kind, 'nestjs')


def nest_arch(paths, modules, members, edges=(), extra_dnodes=(), extra_dedges=(), extra_files=None, unmapped=()):
    dnodes, dedges, files = list(extra_dnodes), list(extra_dedges), dict(extra_files or {})
    mod_ids = {}
    for name, path in modules.items():
        node = nest_node('module', path, name)
        mod_ids[name] = node['id']
        dnodes.append(node)
        if name not in unmapped:
            files[node['id']] = path
    seen = {}
    for owner, relation, kind, path, name in members:
        node = nest_node(kind, path, name)
        if node['id'] not in seen:
            seen[node['id']] = node
            dnodes.append(node)
            files[node['id']] = path
        dedges.append(dedge(mod_ids[owner], node['id'], relation))
    return architecture(paths, edges, dnodes=dnodes, dedges=dedges, node_files=files)


def single_module_arch():
    ts_e = dnode('ts:src/e.ts', 'module', 'typescript-core')
    exported = nest_node('provider', 'src/t.ts', 'T')
    arch = nest_arch(
        ['src/m.ts', 'src/c.ts', 'src/s.ts', 'src/e.ts', 'src/t.ts'], {'M': 'src/m.ts'},
        [('M', 'DECLARES', 'controller', 'src/c.ts', 'C'), ('M', 'PROVIDES', 'provider', 'src/s.ts', 'S')],
        extra_dnodes=[ts_e, exported], extra_dedges=[dedge('nestjs:module:src/m.ts#M', exported['id'], 'EXPORTS')],
        extra_files={'ts:src/e.ts': 'src/e.ts', exported['id']: 'src/t.ts'})
    return arch


def test_V05_C11_module_controller_provider_membership():
    assigned = package_assignments(single_module_arch())['framework']
    pkg = 'pkg:nestjs:src/m.ts#M'
    assert {f: v for f, v in assigned.items() if v} == {fid('src/m.ts'): [pkg], fid('src/c.ts'): [pkg], fid('src/s.ts'): [pkg]}
    assert assigned.get(fid('src/e.ts'), []) == [] and assigned.get(fid('src/t.ts'), []) == []  # nest-unassigned; EXPORTS is not membership


def test_V05_C11_framework_coverage_and_metrics():
    result = analyze_structure(single_module_arch(), default_weights())
    schemes = result.coverage['structure']['schemes']
    assert result.coverage['structure']['policy'] == 'structure.v2'
    assert set(result.coverage) == {'structure'} and set(result.coverage['structure']) == {'policy', 'schemes'}
    assert list(result.candidates) == sorted(result.candidates, key=lambda c: (c['kind'], c['id']))
    assert schemes['framework'] == {'assigned_file_count': 3, 'unassigned_file_count': 2,
                                    'unassigned_files': [fid('src/e.ts'), fid('src/t.ts')], 'shared_file_count': 0, 'shared_files': []}
    assert schemes['language'] == {'assigned_file_count': 5, 'unassigned_file_count': 0, 'unassigned_files': [],
                                   'shared_file_count': 0, 'shared_files': []}
    assert set(result.package_metrics) == {'language', 'framework'}
    assert set(result.package_metrics['framework']) == {'pkg:nestjs:src/m.ts#M'}
    assert result.package_metrics['framework']['pkg:nestjs:src/m.ts#M']['file_count'] == 3


def test_V05_C12_no_nest_nodes_means_no_framework_key_anywhere():
    result = run(['a/x.py', 'b/y.py'], [fedge('a/x.py', 'b/y.py')])
    assert set(result.package_metrics) == {'language'}
    assert set(result.coverage['structure']['schemes']) == {'language'}
    assert set(package_assignments(architecture(['a.py']))) == {'language'}


def test_V05_non_nestjs_module_nodes_do_not_enable_framework():
    ts = dnode('nestjs:module:src/m.ts#M', 'module', 'typescript-core')   # same id shape, wrong provenance
    arch = architecture(['src/m.ts'], dnodes=[ts], node_files={ts['id']: 'src/m.ts'})
    assert 'framework' not in package_assignments(arch)
    other_kind = dnode('nestjs:controller:src/m.ts#C', 'controller', 'nestjs')  # nestjs provenance, but not a module
    arch = architecture(['src/m.ts'], dnodes=[other_kind], node_files={other_kind['id']: 'src/m.ts'})
    assert 'framework' not in package_assignments(arch)


def test_V05_nest_module_unmapped_keeps_other_members():
    arch = nest_arch(['src/c.ts', 'src/s.ts'], {'M': 'src/m.ts'},
                     [('M', 'DECLARES', 'controller', 'src/c.ts', 'C'), ('M', 'PROVIDES', 'provider', 'src/s.ts', 'S')], unmapped=('M',))
    assigned = package_assignments(arch)['framework']
    assert {f: v for f, v in assigned.items() if v} == {fid('src/c.ts'): ['pkg:nestjs:src/m.ts#M'], fid('src/s.ts'): ['pkg:nestjs:src/m.ts#M']}
    result = analyze_structure(arch, default_weights())
    assert result.coverage['structure']['schemes']['framework']['unassigned_file_count'] == 0


def test_V05_module_without_any_mapped_member_file_yields_no_package():
    arch = nest_arch(['src/a.ts'], {'M': 'src/m.ts'}, [], unmapped=('M',))
    assigned = package_assignments(arch).get('framework', {})
    assert not any(assigned.values())
    result = analyze_structure(arch, default_weights())
    assert result.package_metrics.get('framework', {}) == {}
    assert result.coverage['structure']['schemes']['framework']['assigned_file_count'] == 0


def test_V05_member_without_file_mapping_is_skipped_without_error():
    arch = nest_arch(['src/m.ts', 'src/c.ts'], {'M': 'src/m.ts'},
                     [('M', 'DECLARES', 'controller', 'src/c.ts', 'C'), ('M', 'PROVIDES', 'provider', 'src/ghost.ts', 'G')])
    arch.details['node_files']['nestjs:provider:src/ghost.ts#G'] = None
    assigned = package_assignments(arch)['framework']
    assert {f for f, v in assigned.items() if v} == {fid('src/m.ts'), fid('src/c.ts')}


def multi_arch(extra_edges=()):
    paths = ['src/m1.ts', 'src/m2.ts', 'src/m3.ts', 'src/s.ts', 'src/x.ts']
    edges = [fedge('src/x.ts', 'src/s.ts', indices=[0])] + list(extra_edges)
    return nest_arch(paths, {'M1': 'src/m1.ts', 'M2': 'src/m2.ts', 'M3': 'src/m3.ts'},
                     [('M1', 'PROVIDES', 'provider', 'src/s.ts', 'S'), ('M2', 'PROVIDES', 'provider', 'src/s.ts', 'S'),
                      ('M3', 'DECLARES', 'controller', 'src/x.ts', 'X')], edges)


def test_V05_C25_file_in_two_modules_is_member_of_both():
    arch = multi_arch()
    assigned = package_assignments(arch)['framework']
    assert sorted(assigned[fid('src/s.ts')]) == ['pkg:nestjs:src/m1.ts#M1', 'pkg:nestjs:src/m2.ts#M2']
    assert assigned[fid('src/x.ts')] == ['pkg:nestjs:src/m3.ts#M3']
    result = analyze_structure(arch, default_weights())
    framework = result.coverage['structure']['schemes']['framework']
    assert framework['shared_file_count'] == 1 and framework['shared_files'] == [fid('src/s.ts')]
    assert framework['assigned_file_count'] == 5 and framework['unassigned_file_count'] == 0
    assert result.coverage['structure']['schemes']['language']['shared_file_count'] == 0


def test_V05_C25_package_pairs_reach_both_modules():
    metrics = analyze_structure(multi_arch(), default_weights()).package_metrics['framework']
    m1, m2, m3 = (metrics[f'pkg:nestjs:src/{n.lower()}.ts#{n}'] for n in ('M1', 'M2', 'M3'))
    assert (m3['ce'], m3['ca'], m3['instability'], m3['weighted_ce']) == (2, 0, 1.0, pytest.approx(2.0))
    for member in (m1, m2):
        assert (member['ca'], member['ce'], member['instability'], member['file_count']) == (1, 0, 0.0, 2)
        assert member['weighted_ca'] == pytest.approx(1.0)
    assert m3['file_count'] == 2


def test_V05_C25_framework_package_cycle_with_file_pairs():
    result = analyze_structure(multi_arch([fedge('src/s.ts', 'src/x.ts', indices=[1])]), default_weights())
    pkgs = ['pkg:nestjs:src/m1.ts#M1', 'pkg:nestjs:src/m2.ts#M2', 'pkg:nestjs:src/m3.ts#M3']
    found = cycles_by_key(result.candidates, 'package_cycle')
    assert {k[:2] for k in found} == {('framework', t) for t in ('certain', 'resolved', 'all')}
    top = found[('framework', 'all', tuple(pkgs))]
    assert top['id'] == cycle_id('framework', 'all', pkgs) and top['target'] == cycle_target('framework', 'all', pkgs)
    pairs = {(r['from_id'], r['to_id']): r['file_pairs'] for r in top['evidence']}
    assert pairs == {(pkgs[2], pkgs[0]): [[fid('src/x.ts'), fid('src/s.ts')]], (pkgs[2], pkgs[1]): [[fid('src/x.ts'), fid('src/s.ts')]],
                     (pkgs[0], pkgs[2]): [[fid('src/s.ts'), fid('src/x.ts')]], (pkgs[1], pkgs[2]): [[fid('src/s.ts'), fid('src/x.ts')]]}
    assert top['metrics']['member_count'] == 3 and top['metrics']['internal_pair_count'] == 4


def by_package(result, scheme='language'):
    return result.package_metrics[scheme]


def test_V06_C13_boundary_values_of_instability():
    result = run(['p/a.py', 'q/b.py', 'r/c.py'], [fedge('p/a.py', 'q/b.py', indices=[0])])
    metrics = by_package(result)
    assert set(metrics['pkg:dir:p']) == {'file_count', 'ca', 'ce', 'instability', 'weighted_ca', 'weighted_ce', 'weighted_instability'}
    assert metrics['pkg:dir:p'] == {'file_count': 1, 'ca': 0, 'ce': 1, 'instability': 1.0, 'weighted_ca': 0, 'weighted_ce': pytest.approx(1.0), 'weighted_instability': 1.0}
    assert metrics['pkg:dir:q'] == {'file_count': 1, 'ca': 1, 'ce': 0, 'instability': 0.0, 'weighted_ca': pytest.approx(1.0), 'weighted_ce': 0, 'weighted_instability': 0.0}
    assert metrics['pkg:dir:r'] == {'file_count': 1, 'ca': 0, 'ce': 0, 'instability': None, 'weighted_ca': 0, 'weighted_ce': 0, 'weighted_instability': None}
    assert of_kind(result.candidates, 'unstable_dependency') == []  # delta-negative: I(Q)=0 < I(P)=1


def c14_result():
    edges = [
        fedge('z/z.py', 'p/a.py', 'CALLS', SI, AMBIGUOUS, indices=[0]),
        fedge('p/a.py', 'q/b.py', 'IMPORTS', SC, EXACT, indices=[1]),
        fedge('p/a2.py', 'q/b2.py', 'CALLS', SI, AMBIGUOUS, indices=[2, 3], evidence=2),
        fedge('q/b.py', 's/s.py', 'IMPORTS', SC, EXACT, indices=[4]),
        fedge('q/b2.py', 't/t.py', 'IMPORTS', SC, EXACT, share=.5, indices=[5]),
    ]
    return run(['z/z.py', 'p/a.py', 'p/a2.py', 'q/b.py', 'q/b2.py', 's/s.py', 't/t.py'], edges)


def test_V06_C14_metrics_hand_calculated():
    metrics = by_package(c14_result())
    # P: ca={Z}=1, ce={Q}=1 -> 0.5; weighted_ce = max(1.0, 0.3) (max per pair, not sum) = 1.0, weighted_ca = 0.3 -> 1/1.3
    assert metrics['pkg:dir:p'] == {'file_count': 2, 'ca': 1, 'ce': 1, 'instability': 0.5, 'weighted_ca': pytest.approx(0.3),
                                    'weighted_ce': pytest.approx(1.0), 'weighted_instability': pytest.approx(1 / 1.3)}
    # Q: ca={P}=1, ce={S,T}=2 -> 2/3; weighted_ce = 1.0 + 0.5, weighted_ca = 1.0 -> 1.5/2.5
    assert metrics['pkg:dir:q'] == {'file_count': 2, 'ca': 1, 'ce': 2, 'instability': pytest.approx(2 / 3), 'weighted_ca': pytest.approx(1.0),
                                    'weighted_ce': pytest.approx(1.5), 'weighted_instability': pytest.approx(0.6)}
    assert metrics['pkg:dir:z']['instability'] == 1.0 and metrics['pkg:dir:z']['weighted_ce'] == pytest.approx(0.3)
    assert metrics['pkg:dir:s']['instability'] == 0.0 and metrics['pkg:dir:s']['weighted_ca'] == pytest.approx(1.0)
    assert metrics['pkg:dir:t']['instability'] == 0.0 and metrics['pkg:dir:t']['weighted_ca'] == pytest.approx(0.5)


def test_V07_candidates_are_sorted_by_kind_then_id():
    for result in (c14_result(), cross_cycle(), analyze_structure(multi_arch([fedge('src/s.ts', 'src/x.ts', indices=[1])]), default_weights())):
        keys = [(c['kind'], c['id']) for c in result.candidates]
        assert keys and keys == sorted(keys)


def test_V07_C14_unstable_dependency_fields():
    found = of_kind(c14_result().candidates, 'unstable_dependency')
    assert len(found) == 1   # Z->P, Q->S, Q->T go to lower instability
    item = found[0]
    assert item['kind'] == 'unstable_dependency'
    assert item['id'] == unstable_id('language', 'pkg:dir:p', 'pkg:dir:q')
    assert item['target'] == 'pkg:dir:p'
    assert item['coverage'] == 'static_analyzer_relation' and item['status'] == 'static_candidate'
    metrics = item['metrics']
    assert set(metrics) == {'instability_from', 'instability_to', 'instability_delta', 'evidence_count', 'file_pair_count',
                            'weighted_instability_from', 'weighted_instability_to'}   # unstable-weighted-present
    assert metrics['instability_from'] == 0.5 and metrics['instability_to'] == pytest.approx(2 / 3)
    assert metrics['instability_delta'] == pytest.approx(1 / 6, abs=1e-4)   # 0.1667
    assert metrics['evidence_count'] == 3 and metrics['file_pair_count'] == 2
    assert metrics['weighted_instability_from'] == pytest.approx(1 / 1.3) and metrics['weighted_instability_to'] == pytest.approx(0.6)
    assert item['structure'] == {'scheme': 'language', 'tier': 'certain', 'from_package': 'pkg:dir:p', 'to_package': 'pkg:dir:q'}
    records = {(r['from_id'], r['to_id']): r for r in item['evidence']}
    assert set(records) == {(fid('p/a.py'), fid('q/b.py')), (fid('p/a2.py'), fid('q/b2.py'))}
    assert records[(fid('p/a.py'), fid('q/b.py'))]['relations'] == ['IMPORTS'] and records[(fid('p/a.py'), fid('q/b.py'))]['max_weight'] == pytest.approx(1.0)
    assert records[(fid('p/a2.py'), fid('q/b2.py'))]['evidence_count'] == 2 and records[(fid('p/a2.py'), fid('q/b2.py'))]['max_weight'] == pytest.approx(0.3)


def test_V06_C15_equal_instability_makes_no_candidate():
    edges = [fedge('z/z.py', 'p/a.py'), fedge('p/a.py', 'q/b.py'), fedge('q/b.py', 's/s.py')]
    result = run(['z/z.py', 'p/a.py', 'q/b.py', 's/s.py'], edges)
    metrics = by_package(result)
    assert metrics['pkg:dir:p']['instability'] == 0.5 == metrics['pkg:dir:q']['instability']
    assert of_kind(result.candidates, 'unstable_dependency') == []


def test_V06_delta_positive_just_above_zero():
    # P: ca=2 (Z1,Z2), ce=1 -> 1/3; Q: ca=1, ce=1 -> 1/2; Z1,Z2 -> I=1; S -> 0. Only P->Q ascends.
    edges = [fedge('z1/a.py', 'p/a.py'), fedge('z2/a.py', 'p/a.py'), fedge('p/a.py', 'q/b.py'), fedge('q/b.py', 's/s.py')]
    result = run(['z1/a.py', 'z2/a.py', 'p/a.py', 'q/b.py', 's/s.py'], edges)
    found = of_kind(result.candidates, 'unstable_dependency')
    assert [(c['structure']['from_package'], c['structure']['to_package']) for c in found] == [('pkg:dir:p', 'pkg:dir:q')]
    assert found[0]['metrics']['instability_delta'] == pytest.approx(1 / 6)


def test_V06_unstable_weighted_keys_absent_when_weighted_denominator_is_zero():
    """Contrived: candidate_share 0 gives weight 0, so the weighted denominator of Q is 0 while its count denominator is not."""
    edges = [fedge('z1/a.py', 'p/a.py', indices=[0]), fedge('z2/a.py', 'p/a.py', indices=[1]),
             fedge('p/a.py', 'q/b.py', share=0, indices=[2]), fedge('q/b.py', 's/s.py', share=0, indices=[3])]
    result = run(['z1/a.py', 'z2/a.py', 'p/a.py', 'q/b.py', 's/s.py'], edges)
    metrics = by_package(result)
    assert metrics['pkg:dir:q'] == {'file_count': 1, 'ca': 1, 'ce': 1, 'instability': 0.5, 'weighted_ca': 0, 'weighted_ce': 0, 'weighted_instability': None}
    assert metrics['pkg:dir:p']['weighted_instability'] == 0.0   # 0 / (2 + 0): denominator is not zero
    (item,) = of_kind(result.candidates, 'unstable_dependency')
    assert 'weighted_instability_to' not in item['metrics']
    assert set(item['metrics']) == {'instability_from', 'instability_to', 'instability_delta', 'evidence_count', 'file_pair_count', 'weighted_instability_from'}
    assert item['metrics']['weighted_instability_from'] == 0.0


def test_V07_unstable_weighted_from_key_absent_when_from_side_denominator_is_zero():
    """Contrived (candidate_share 0): every pair of P has weight 0, Q's weighted side is non-zero."""
    edges = [fedge('z1/a.py', 'p/a.py', share=0, indices=[0]), fedge('z2/a.py', 'p/a.py', share=0, indices=[1]),
             fedge('p/a.py', 'q/b.py', share=0, indices=[2]), fedge('q/b.py', 's/s.py', indices=[3])]
    result = run(['z1/a.py', 'z2/a.py', 'p/a.py', 'q/b.py', 's/s.py'], edges)
    row = by_package(result)['pkg:dir:p']
    assert (row['ca'], row['ce'], row['weighted_ca'], row['weighted_ce'], row['weighted_instability']) == (2, 1, 0, 0, None)
    (item,) = of_kind(result.candidates, 'unstable_dependency')
    assert set(item['metrics']) == {'instability_from', 'instability_to', 'instability_delta', 'evidence_count', 'file_pair_count', 'weighted_instability_to'}
    assert 'weighted_instability_from' not in item['metrics']
    assert item['metrics']['weighted_instability_to'] == pytest.approx(1.0)   # Q: wce 1.0 / (wca 0 + wce 1.0)
    assert item['metrics']['instability_from'] == pytest.approx(1 / 3) and item['metrics']['instability_to'] == 0.5


def test_V06_tests_and_boundary_edges_between_packages_do_not_count():
    edges = [fedge('r/c.py', 'p/a.py', indices=[0]), fedge('p/a.py', 'q/b.py', 'TESTS', indices=[1]),
             fedge('p/a.py', 'ext:lib', indices=[2]), fedge('ext:lib', 'q/b.py', indices=[3])]
    result = run(['r/c.py', 'p/a.py', 'q/b.py'], edges, boundary=['ext:lib'])
    metrics = by_package(result)
    assert (metrics['pkg:dir:p']['ca'], metrics['pkg:dir:p']['ce']) == (1, 0)
    assert (metrics['pkg:dir:q']['ca'], metrics['pkg:dir:q']['ce'], metrics['pkg:dir:q']['instability']) == (0, 0, None)
    assert (metrics['pkg:dir:r']['ca'], metrics['pkg:dir:r']['ce']) == (0, 1)
    assert of_kind(result.candidates, 'package_cycle') == []


RING_SHARES = [1, 1, .5, .5, .5, 1, .25, 1, .5, 1, .25]
RING_EVIDENCE = [3, 1, 2, 2, 1, 1, 5, 2, 1, 1, 1]
RING_ORDER = [10, 6, 4, 8, 2, 3, 1, 5, 9, 7, 0]   # (max_weight, evidence_count, from, to), worked out by hand


def test_V07_package_cycle_with_eleven_pairs_caps_cut_candidates_at_ten():
    paths = [f'd{i:02}/f.py' for i in range(11)]
    edges = [fedge(paths[i], paths[(i + 1) % 11], share=RING_SHARES[i], indices=[i], evidence=RING_EVIDENCE[i]) for i in range(11)]
    found = cycles_by_key(run(paths, edges).candidates, 'package_cycle')
    members = [f'pkg:dir:d{i:02}' for i in range(11)]
    top = found[('language', 'all', tuple(members))]
    cuts = top['structure']['cut_candidates']
    assert [(c['from_id'], c['to_id']) for c in cuts] == [(members[i], members[(i + 1) % 11]) for i in RING_ORDER[:10]]
    assert all(set(c) == {'from_id', 'to_id', 'relations', 'max_weight', 'evidence_count'} for c in cuts)
    assert len(top['evidence']) == 11 and top['metrics']['internal_pair_count'] == 11


def test_V06_same_package_edges_do_not_count():
    result = run(['p/a.py', 'p/b.py', 'q/c.py'], [fedge('p/a.py', 'p/b.py'), fedge('p/a.py', 'q/c.py'), fedge('p/b.py', 'q/c.py')])
    row = by_package(result)['pkg:dir:p']
    assert (row['ce'], row['ca'], row['file_count']) == (1, 0, 2)    # ce counts distinct packages, not file pairs
    assert row['weighted_ce'] == pytest.approx(1.0)                  # max per package pair, not 2.0


def test_V06_metrics_use_all_tier_even_for_ambiguous_edges():
    result = run(['p/a.py', 'q/b.py'], [fedge('p/a.py', 'q/b.py', 'CALLS', SI, AMBIGUOUS, share=.5)])
    row = by_package(result)['pkg:dir:p']
    assert (row['ce'], row['instability']) == (1, 1.0) and row['weighted_ce'] == pytest.approx(0.15)


PACKAGE_PAIR_KEYS = {'from_id', 'to_id', 'relations', 'max_weight', 'evidence_count', 'tier', 'file_pairs'}


def certain_relations(found):
    return found[('language', 'certain', ('pkg:dir:p', 'pkg:dir:q'))]['evidence'][0]['relations']


def cross_cycle(ab=(SC, EXACT), ba=(SC, EXACT), ba_share=None):
    edges = [fedge('p/a.py', 'q/b.py', 'IMPORTS', *ab, indices=[0], evidence=2), fedge('q/b.py', 'p/a.py', 'CALLS', *ba, share=ba_share, indices=[1])]
    return run(['p/a.py', 'q/b.py'], edges)


def test_V07_C16_cross_package_cycle_all_tiers():
    result = cross_cycle(ba_share=.5)
    members = ['pkg:dir:p', 'pkg:dir:q']
    found = cycles_by_key(result.candidates, 'package_cycle')
    assert set(found) == {('language', t, tuple(members)) for t in ('certain', 'resolved', 'all')}
    top = found[('language', 'all', tuple(members))]
    assert set(top) >= {'id', 'kind', 'target', 'metrics', 'evidence', 'coverage', 'status', 'structure'}
    assert top['id'] == cycle_id('language', 'all', members) and top['target'] == cycle_target('language', 'all', members)
    assert top['coverage'] == 'static_analyzer_relation' and top['status'] == 'static_candidate'
    assert set(top['structure']) == {'scheme', 'tier', 'members', 'parent_id', 'cut_candidates'}
    assert top['structure']['scheme'] == 'language' and top['structure']['members'] == members
    assert top['metrics'] == {'member_count': 2, 'internal_pair_count': 2, 'internal_evidence_count': 3, 'min_pair_weight': pytest.approx(0.5)}
    assert [(r['from_id'], r['to_id']) for r in top['evidence']] == [(members[0], members[1]), (members[1], members[0])]
    assert all(set(r) == PACKAGE_PAIR_KEYS for r in top['evidence'])
    assert [r['relations'] for r in top['evidence']] == [['IMPORTS'], ['CALLS']]
    assert [c['relations'] for c in top['structure']['cut_candidates']] == [['CALLS'], ['IMPORTS']]
    assert top['evidence'][0]['file_pairs'] == [[fid('p/a.py'), fid('q/b.py')]]
    assert top['evidence'][1]['file_pairs'] == [[fid('q/b.py'), fid('p/a.py')]]
    assert [(r['max_weight'], r['evidence_count']) for r in top['evidence']] == [(pytest.approx(1.0), 2), (pytest.approx(0.5), 1)]
    cuts = top['structure']['cut_candidates']
    assert [(c['from_id'], c['to_id'], c['evidence_count']) for c in cuts] == [(members[1], members[0], 1), (members[0], members[1], 2)]
    assert all(set(c) == {'from_id', 'to_id', 'relations', 'max_weight', 'evidence_count'} for c in cuts)
    assert found[('language', 'certain', tuple(members))]['structure']['parent_id'] == cycle_id('language', 'resolved', members)
    assert found[('language', 'resolved', tuple(members))]['structure']['parent_id'] == cycle_id('language', 'all', members)
    assert top['structure']['parent_id'] is None
    assert len(of_kind(result.candidates, 'dependency_cycle')) == 3   # the same files also form file cycles


def test_V07_pkg_cycle_tiers_only_all_when_one_direction_is_ambiguous():
    result = cross_cycle(ba=(SC, AMBIGUOUS))
    found = cycles_by_key(result.candidates, 'package_cycle')
    assert set(found) == {('language', 'all', ('pkg:dir:p', 'pkg:dir:q'))}
    assert found[('language', 'all', ('pkg:dir:p', 'pkg:dir:q'))]['structure']['parent_id'] is None


def test_V07_pkg_cycle_resolved_tier_evidence_uses_only_resolved_edges():
    result = cross_cycle(ba=(SC, UNIQUE))
    found = cycles_by_key(result.candidates, 'package_cycle')
    assert {k[1] for k in found} == {'resolved', 'all'}
    resolved = found[('language', 'resolved', ('pkg:dir:p', 'pkg:dir:q'))]
    assert resolved['structure']['parent_id'] == cycle_id('language', 'all', ['pkg:dir:p', 'pkg:dir:q'])
    assert {r['tier'] for r in resolved['evidence']} == {'certain', 'resolved'}


def test_V07_C17_cycle_inside_one_package_is_a_file_cycle_only():
    result = run(['p/a.py', 'p/b.py'], [fedge('p/a.py', 'p/b.py'), fedge('p/b.py', 'p/a.py')])
    assert len(of_kind(result.candidates, 'dependency_cycle')) == 3
    assert of_kind(result.candidates, 'package_cycle') == []
    assert of_kind(result.candidates, 'unstable_dependency') == []


def test_V07_package_cycle_parent_chain_with_widening_members():
    edges = [fedge('p/a.py', 'q/b.py'), fedge('q/b.py', 'p/a.py'), fedge('p/a.py', 'r/c.py', resolution=UNIQUE), fedge('r/c.py', 'p/a.py', resolution=UNIQUE)]
    found = cycles_by_key(run(['p/a.py', 'q/b.py', 'r/c.py'], edges).candidates, 'package_cycle')
    pq, pqr = ['pkg:dir:p', 'pkg:dir:q'], ['pkg:dir:p', 'pkg:dir:q', 'pkg:dir:r']
    assert set(found) == {('language', 'certain', tuple(pq)), ('language', 'resolved', tuple(pqr)), ('language', 'all', tuple(pqr))}
    assert found[('language', 'certain', tuple(pq))]['structure']['parent_id'] == cycle_id('language', 'resolved', pqr)


def test_V07_file_pairs_listing_aggregates_and_sorts():
    edges = [fedge('p/b.py', 'q/y.py', indices=[0], evidence=2), fedge('p/a.py', 'q/x.py', 'CALLS', SI, AMBIGUOUS, share=.5, indices=[1]),
             fedge('q/x.py', 'p/a.py', indices=[2])]
    found = cycles_by_key(run(['p/a.py', 'p/b.py', 'q/x.py', 'q/y.py'], edges).candidates, 'package_cycle')
    top = found[('language', 'all', ('pkg:dir:p', 'pkg:dir:q'))]
    forward = top['evidence'][0]
    assert forward['file_pairs'] == [[fid('p/a.py'), fid('q/x.py')], [fid('p/b.py'), fid('q/y.py')]]
    assert forward['max_weight'] == pytest.approx(1.0)       # max(0.15, 1.0), not the sum
    assert forward['evidence_count'] == 3                    # 1 + 2
    assert set(forward) == PACKAGE_PAIR_KEYS and forward['relations'] == ['CALLS', 'IMPORTS']
    assert certain_relations(found) == ['IMPORTS']
    assert forward['tier'] == 'certain'
    certain = found[('language', 'certain', ('pkg:dir:p', 'pkg:dir:q'))]
    assert certain['evidence'][0]['file_pairs'] == [[fid('p/b.py'), fid('q/y.py')]]
    assert certain['evidence'][0]['evidence_count'] == 2


def test_V07_shared_file_contributes_to_every_module_pair_in_dependency_direction():
    result = analyze_structure(multi_arch(), default_weights())
    assert of_kind(result.candidates, 'package_cycle') == []
    assert of_kind(result.candidates, 'dependency_cycle') == []
