import json
import re

import pytest

from tests.nestjs_support import analyze as nest_analyze
from tests.nestjs_support import framework_nodes, write_project
from tests.rename_delta_support import make_repo
from tests.delta_support import ref_delta, wire
from tests.symbol_changes_support import analyze, arch, candidates_of, nest, rel, sym_payload

KIND = 'unprovided_injection'
S_PATH, A_PATH, B_PATH, C_PATH, G_PATH, CTL_PATH = ('src/s.ts', 'src/a.module.ts', 'src/b.module.ts', 'src/c.module.ts',
                                                    'src/g.module.ts', 'src/b.controller.ts')


def api():
    import bottlenecks.nestjs_visibility as module
    return module


def run(nodes, edges):
    return api().unprovided_candidates(arch(nodes, edges))


def edge(a, b, relation, line=1):
    return rel(a.id, b.id, relation, path=a.span.file_path, line=line)


def scene(a_provides=True, a_exports=False, imports_a=True, controller_in_b=True, b_unsupported=(), a_global=False, g=False,
          c_chain=None):
    """S is provided by A. B declares the controller that injects S and imports A (unless imports_a is False).
    g adds a global module G that provides and exports S. c_chain: None, 'exported' or 'private' adds C (providing S)
    between A and B: A exports C, and C exports S when 'exported'."""
    s = nest('provider', 'S', S_PATH)
    a = nest('module', 'AModule', A_PATH, global_=a_global)
    b = nest('module', 'BModule', B_PATH, unsupported=b_unsupported)
    ctl = nest('controller', 'BController', CTL_PATH, line=3)
    nodes, edges = [s, a, b, ctl], [edge(ctl, s, 'DEPENDS_ON', line=7)]
    if controller_in_b:
        edges.append(edge(b, ctl, 'DECLARES'))
    if a_provides:
        edges.append(edge(a, s, 'PROVIDES'))
    if a_exports:
        edges.append(edge(a, s, 'EXPORTS'))
    if imports_a:
        edges.append(edge(b, a, 'INCLUDES'))
    if g:
        gm = nest('module', 'GModule', G_PATH, global_=True)
        nodes.append(gm)
        edges += [edge(gm, s, 'PROVIDES'), edge(gm, s, 'EXPORTS')]
    if c_chain:
        c = nest('module', 'CModule', C_PATH)
        nodes.append(c)
        edges += [edge(c, s, 'PROVIDES'), edge(a, c, 'EXPORTS')]
        if c_chain == 'exported':
            edges.append(edge(c, s, 'EXPORTS'))
    return nodes, edges, {'s': s, 'a': a, 'b': b, 'ctl': ctl}


def assert_candidate(result, certain, uncertain, certainty):
    assert len(result) == 1, result
    [item] = result
    assert {'kind', 'target', 'metrics', 'evidence'} <= set(item)
    assert re.fullmatch(r'b:[0-9a-f]{16}', item['id']) and item['coverage'] == 'static_analyzer_relation'
    assert item['status'] == 'static_candidate'
    assert item['kind'] == KIND and item['target'] == f'file:{CTL_PATH}'
    assert item['metrics'] == {'unprovided_count': certain, 'uncertain_count': uncertain}
    assert [e['certainty'] for e in item['evidence']] == [certainty] * len(item['evidence'])
    return item


def test_V08_cause_own_providers_means_no_candidate():
    nodes, edges, n = scene(a_provides=False, imports_a=False)
    edges.append(edge(n['b'], n['s'], 'PROVIDES'))
    assert run(nodes, edges) == []


def test_V08_effect_certain_when_the_provider_is_not_visible_from_the_only_module():
    nodes, edges, n = scene()
    item = assert_candidate(run(nodes, edges), 1, 0, 'certain')
    [evidence] = item['evidence']
    assert set(evidence) == {'consumer_id', 'provider_id', 'module_ids', 'certainty', 'line'}
    assert evidence['consumer_id'] == n['ctl'].id and evidence['provider_id'] == n['s'].id
    assert evidence['module_ids'] == [n['b'].id] and evidence['line'] == 7


def test_V08_cause_direct_import_export_means_no_candidate():
    nodes, edges, _ = scene(a_exports=True)
    assert run(nodes, edges) == []


def test_V08_cause_direct_import_without_export_is_still_not_visible():
    nodes, edges, _ = scene(a_exports=False)
    assert_candidate(run(nodes, edges), 1, 0, 'certain')


def test_V08_cause_provider_exported_by_a_module_that_is_not_imported_is_not_visible():
    nodes, edges, _ = scene(a_exports=True, imports_a=False)
    assert_candidate(run(nodes, edges), 1, 0, 'certain')


def test_V08_cause_re_export_chain_means_no_candidate():
    nodes, edges, _ = scene(c_chain='exported', a_provides=False)
    assert run(nodes, edges) == []


def test_V08_cause_re_export_chain_whose_inner_module_does_not_export_the_provider_is_not_visible():
    nodes, edges, _ = scene(c_chain='private', a_provides=False)
    assert_candidate(run(nodes, edges), 1, 0, 'certain')


def test_V08_cause_re_export_cycle_terminates_and_stays_invisible():
    nodes, edges, n = scene(c_chain='private', a_provides=False)
    c = next(x for x in nodes if x.label == 'CModule')
    edges.append(edge(c, n['a'], 'EXPORTS'))
    assert_candidate(run(nodes, edges), 1, 0, 'certain')


def test_V08_cause_global_module_export_means_no_candidate_even_without_an_import():
    nodes, edges, _ = scene(a_provides=False, imports_a=False, g=True)
    assert run(nodes, edges) == []


def test_V08_cause_module_that_exports_but_is_not_global_does_not_leak_to_unimported_modules():
    nodes, edges, _ = scene(a_provides=False, imports_a=False, g=True)
    next(x for x in nodes if x.label == 'GModule').metadata['global'] = False
    assert_candidate(run(nodes, edges), 1, 0, 'certain')


@pytest.mark.parametrize('fields', [['imports'], ['providers'], ['imports', 'providers']], ids=['imports', 'providers', 'both'])
def test_V08_cause_unsupported_module_fields_make_the_verdict_uncertain(fields):
    nodes, edges, n = scene(b_unsupported=fields)
    item = assert_candidate(run(nodes, edges), 0, 1, 'uncertain')
    assert item['evidence'][0]['module_ids'] == [n['b'].id]


def test_V08_cause_unsupported_fields_do_not_hide_a_provider_that_is_visible():
    nodes, edges, _ = scene(a_exports=True, b_unsupported=['imports'])
    assert run(nodes, edges) == []


def test_V08_cause_consumer_without_any_module_is_uncertain():
    nodes, edges, _ = scene(controller_in_b=False)
    assert_candidate(run(nodes, edges), 0, 1, 'uncertain')


def test_V08_consumer_kinds_module_provider_and_controller_are_all_checked():
    nodes, edges, n = scene(controller_in_b=True)
    other = nest('provider', 'Other', CTL_PATH, line=20)
    nodes.append(other)
    edges += [edge(n['b'], other, 'PROVIDES'), edge(other, n['s'], 'DEPENDS_ON', line=21), edge(n['b'], n['s'], 'DEPENDS_ON', line=22)]
    result = {c['target']: c for c in run(nodes, edges)}
    controller_file = result[f'file:{CTL_PATH}']
    assert controller_file['metrics'] == {'unprovided_count': 2, 'uncertain_count': 0}
    assert sorted(e['consumer_id'] for e in controller_file['evidence']) == sorted([n['ctl'].id, other.id])
    assert result[f'file:{B_PATH}']['metrics'] == {'unprovided_count': 1, 'uncertain_count': 0}


def test_V08_counts_follow_certainty_per_evidence_and_one_candidate_covers_the_file():
    nodes, edges, n = scene()
    other_provider = nest('provider', 'T', S_PATH, line=9)
    lone_ctl = nest('controller', 'Lone', CTL_PATH, line=30)
    nodes += [other_provider, lone_ctl]
    edges += [edge(n['ctl'], other_provider, 'DEPENDS_ON', line=8), edge(lone_ctl, n['s'], 'DEPENDS_ON', line=31)]
    [item] = run(nodes, edges)
    assert item['metrics'] == {'unprovided_count': 2, 'uncertain_count': 1}
    assert sorted((e['consumer_id'].split('#')[-1], e['certainty']) for e in item['evidence']) == [
        ('BController', 'certain'), ('BController', 'certain'), ('Lone', 'uncertain')]


def second_module(nodes, edges, n, name, path, provides=False, unsupported=()):
    module = nest('module', name, path, unsupported=unsupported)
    nodes.append(module)
    edges.append(edge(module, n['ctl'], 'DECLARES'))
    if provides:
        edges.append(edge(module, n['s'], 'PROVIDES'))
    return module


def test_V08_cause_visible_in_one_of_two_modules_is_recorded_for_the_invisible_one_only():
    nodes, edges, n = scene()
    second_module(nodes, edges, n, 'B2Module', 'src/b2.module.ts', provides=True)
    item = assert_candidate(run(nodes, edges), 1, 0, 'certain')
    assert item['evidence'][0]['module_ids'] == [n['b'].id] and item['evidence'][0]['line'] == 7


def test_V08_cause_certainty_comes_only_from_the_modules_where_the_provider_is_invisible():
    nodes, edges, n = scene()
    second_module(nodes, edges, n, 'B2Module', 'src/b2.module.ts', provides=True, unsupported=['imports', 'providers'])
    assert_candidate(run(nodes, edges), 1, 0, 'certain')


def test_V08_cause_two_invisible_modules_with_mixed_unsupported_fields_are_uncertain_with_both_ids_sorted():
    nodes, edges, n = scene()
    other = second_module(nodes, edges, n, 'AaModule', 'src/aa.module.ts', unsupported=['imports'])
    item = assert_candidate(run(nodes, edges), 0, 1, 'uncertain')
    assert item['evidence'][0]['module_ids'] == sorted([n['b'].id, other.id]) == [other.id, n['b'].id]


def test_V08_a_graph_without_nestjs_nodes_has_no_candidates():
    from tests.symbol_changes_support import sym
    assert run([sym('py:a#f', 'a.py'), sym('py:b#g', 'b.py')], [rel('py:b#g', 'py:a#f')]) == []


SERVICE = "import { Injectable } from '@nestjs/common';\n@Injectable()\nexport class S {}\n"
CONTROLLER = ("import { Controller } from '@nestjs/common';\nimport { S } from './s.service';\n@Controller('b')\n"
              "export class BController {\n  constructor(private readonly s: S) {}\n}\n")


def a_module(exports='', providers='S'):
    return ("import { Module } from '@nestjs/common';\nimport { S } from './s.service';\n"
            f"@Module({{ imports: [], providers: [{providers}]{exports} }})\nexport class AModule {{}}\n")


def b_module(imports='AModule', head=''):
    return ("import { Module } from '@nestjs/common';\nimport { AModule } from './a.module';\nimport { BController } from './b.controller';\n"
            f"{head}@Module({{ imports: [{imports}], controllers: [BController] }})\nexport class BModule {{}}\n")


def nest_project(tmp_path, **files):
    root = tmp_path / 'repo'
    make_repo(root, {'src/s.service.ts': SERVICE, 'src/b.controller.ts': CONTROLLER, **files})
    return analyze(root, tmp_path / 'o', ['-f', 'nestjs', '-l', 'typescript']), root


def injection(data):
    found = [c for c in candidates_of(data, KIND) if c['target'] == 'file:src/b.controller.ts']
    assert len(found) <= 1
    return found


def test_C08_provider_not_exported_by_the_imported_module_is_reported_as_certain(tmp_path):
    data, _ = nest_project(tmp_path, **{'src/a.module.ts': a_module(), 'src/b.module.ts': b_module()})
    [item] = injection(data)
    assert item['metrics'] == {'unprovided_count': 1, 'uncertain_count': 0}
    [evidence] = item['evidence']
    assert evidence['certainty'] == 'certain' and evidence['consumer_id'].endswith('#BController') and evidence['provider_id'].endswith('#S')
    assert [m.endswith('#BModule') for m in evidence['module_ids']] == [True]


def test_C08_control_exported_provider_is_visible(tmp_path):
    data, _ = nest_project(tmp_path, **{'src/a.module.ts': a_module(exports=', exports: [S]'), 'src/b.module.ts': b_module()})
    assert injection(data) == []


def test_C09_a_dynamic_import_makes_the_same_verdict_uncertain(tmp_path):
    head = "import { ConfigModule } from '@nestjs/config';\n"
    data, _ = nest_project(tmp_path, **{'src/a.module.ts': a_module(), 'src/b.module.ts': b_module('AModule, ConfigModule.forRoot()', head)})
    [item] = injection(data)
    assert item['metrics'] == {'unprovided_count': 0, 'uncertain_count': 1}
    assert [e['certainty'] for e in item['evidence']] == ['uncertain']


def test_C10_a_global_module_that_exports_the_provider_makes_it_visible(tmp_path):
    glob = ("import { Module, Global } from '@nestjs/common';\nimport { S } from './s.service';\n@Global()\n"
            "@Module({ providers: [S], exports: [S] })\nexport class GlobalModule {}\n")
    data, _ = nest_project(tmp_path, **{'src/a.module.ts': a_module(providers=''), 'src/g.module.ts': glob, 'src/b.module.ts': b_module()})
    assert injection(data) == []


def test_C11_a_provider_re_exported_through_another_module_is_visible(tmp_path):
    inner = ("import { Module } from '@nestjs/common';\nimport { S } from './s.service';\n"
             "@Module({ providers: [S], exports: [S] })\nexport class CModule {}\n")
    outer = ("import { Module } from '@nestjs/common';\nimport { CModule } from './c.module';\n"
             "@Module({ imports: [CModule], exports: [CModule] })\nexport class AModule {}\n")
    data, _ = nest_project(tmp_path, **{'src/a.module.ts': outer, 'src/c.module.ts': inner, 'src/b.module.ts': b_module()})
    assert injection(data) == []


def test_V08_repository_without_nestjs_has_no_candidates_and_no_error(tmp_path):
    root = tmp_path / 'repo'
    make_repo(root, {'app/__init__.py': '', 'app/a.py': 'def f():\n    return 1\n'})
    assert candidates_of(analyze(root, tmp_path / 'o', ['-l', 'python']), KIND) == []


def test_V08_module_node_metadata_records_global_and_unsupported_fields(tmp_path):
    root = tmp_path / 'p'
    write_project(root, {
        'src/g.ts': "import { Module, Global } from '@nestjs/common';\n@Global()\n@Module({})\nexport class GlobalOne {}\n",
        'src/p.ts': "import { Module } from '@nestjs/common';\n@Module({})\nexport class Plain {}\n",
        'src/d.ts': ("import { Module } from '@nestjs/common';\nimport { ConfigModule } from '@nestjs/config';\n"
                     "@Module({ imports: [ConfigModule.forRoot()] })\nexport class Dynamic {}\n"),
        'src/r.ts': ("import { Module } from '@nestjs/common';\nclass Y {}\n"
                     "@Module({ providers: [{ provide: 'X', useClass: Y }] })\nexport class Recorded {}\n")})
    modules = {n.label: n.metadata for n in framework_nodes(nest_analyze(root, language=False), 'module')}
    assert {k: (v['global'], v['unsupported_fields']) for k, v in modules.items()} == {
        'GlobalOne': (True, []), 'Plain': (False, []), 'Dynamic': (False, ['imports']), 'Recorded': (False, ['providers'])}


def pair_candidate(pairs, ident, certain=None, uncertain=0, target='file:src/b.controller.ts', consumer_path='src/b.controller.ts'):
    evidence = [{'consumer_id': f'nestjs:controller:{consumer_path}#BController', 'provider_id': p, 'module_ids': [], 'certainty': 'certain',
                 'line': 1} for p in pairs]
    return {'id': ident, 'kind': KIND, 'target': target, 'coverage': 'static_analyzer_relation', 'status': 'static_candidate',
            'metrics': {'unprovided_count': len(pairs) if certain is None else certain, 'uncertain_count': uncertain}, 'evidence': evidence}


S1, S2 = 'nestjs:provider:src/s.service.ts#S', 'nestjs:provider:src/t.service.ts#T'


def delta_compare(cur, base, renames=None):
    import bottlenecks.delta as delta
    current, baseline = sym_payload(None, candidates=cur), sym_payload(None, candidates=base)
    result = wire(delta.compute_delta(current, baseline, renames))
    assert result == wire(ref_delta(current, baseline, renames))
    return result


def applied(*pairs):
    return {'status': 'applied', 'reason': None, 'pairs': [{'from': a, 'to': b, 'similarity': 100} for a, b in pairs]}


def test_V03_EP6_consumer_file_rename_keeps_the_same_pair_quiet():
    base = [pair_candidate([S1], 'b:0000000000000001')]
    cur = [pair_candidate([S1], 'b:0000000000000002', target='file:src/b2.controller.ts', consumer_path='src/b2.controller.ts')]
    result = delta_compare(cur, base, applied(('src/b.controller.ts', 'src/b2.controller.ts')))
    assert result['new_candidates'] == [] and result['strengthened_candidates'] == [] and result['resolved']['candidates'] == 0
    control = delta_compare(cur, base)
    assert len(control['new_candidates']) == 1 and control['resolved']['candidates'] == 1


def test_V03_EP6_provider_file_rename_keeps_the_same_pair_quiet():
    base = [pair_candidate([S1], 'b:0000000000000001')]
    cur = [pair_candidate(['nestjs:provider:src/s2.service.ts#S'], 'b:0000000000000002')]
    result = delta_compare(cur, base, applied(('src/s.service.ts', 'src/s2.service.ts')))
    assert result['new_candidates'] == [] and result['strengthened_candidates'] == [] and result['resolved']['candidates'] == 0
    control = delta_compare(cur, base)
    assert [i['kind'] for i in control['strengthened_candidates']] == [KIND]


def test_V08_delta_unprovided_count_increase_is_strengthened_with_no_added_evidence():
    base = [pair_candidate([S1], 'b:0000000000000001')]
    cur = [pair_candidate([S1], 'b:0000000000000002', certain=2)]
    [item] = delta_compare(cur, base)['strengthened_candidates']
    assert item['increased'] == {'unprovided_count': {'baseline': 1, 'current': 2}} and item['added_evidence'] == []


def test_V08_delta_uncertain_count_increase_is_strengthened_with_no_added_evidence():
    base = [pair_candidate([S1], 'b:0000000000000001')]
    cur = [pair_candidate([S1], 'b:0000000000000002', certain=1, uncertain=1)]
    [item] = delta_compare(cur, base)['strengthened_candidates']
    assert item['increased'] == {'uncertain_count': {'baseline': 0, 'current': 1}} and item['added_evidence'] == []


def test_V08_delta_certainty_flip_on_the_same_pair_reports_only_the_uncertain_increase():
    base = [pair_candidate([S1], 'b:0000000000000001')]
    cur = [pair_candidate([S1], 'b:0000000000000002', certain=0, uncertain=1)]
    [item] = delta_compare(cur, base)['strengthened_candidates']
    assert item['increased'] == {'uncertain_count': {'baseline': 0, 'current': 1}} and item['added_evidence'] == []


def test_V08_delta_count_decrease_is_not_reported():
    base = [pair_candidate([S1, S2], 'b:0000000000000001')]
    cur = [pair_candidate([S1], 'b:0000000000000002')]
    result = delta_compare(cur, base)
    assert result['strengthened_candidates'] == [] and result['new_candidates'] == []


def test_V08_delta_new_consumer_file_is_a_new_candidate():
    base = [pair_candidate([S1], 'b:0000000000000001')]
    other = pair_candidate([S2], 'b:0000000000000003', target='file:src/c.controller.ts', consumer_path='src/c.controller.ts')
    result = delta_compare([base[0], other], base)
    assert [(i['kind'], i['target'], i['metrics']) for i in result['new_candidates']] == [
        (KIND, 'file:src/c.controller.ts', {'unprovided_count': 1, 'uncertain_count': 0})]
    assert result['strengthened_candidates'] == []


def test_V08_delta_strengthening_adds_the_injection_row_for_a_new_consumer_provider_pair():
    base = [pair_candidate([S1], 'b:0000000000000001')]
    cur = [pair_candidate([S2], 'b:0000000000000002')]
    [item] = delta_compare(cur, base)['strengthened_candidates']
    assert item['increased'] == {} and item['added_evidence'] == [['injection', 'nestjs:controller:src/b.controller.ts#BController', S2]]
