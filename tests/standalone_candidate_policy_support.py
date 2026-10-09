import copy
import hashlib
import json
import math
import re
from collections import Counter, defaultdict

from tests.candidate_policy_metadata_support import without_candidate_policy_metadata
from tests.candidate_policy_transition_support import assert_candidate_policy_transition
from tests.candidate_group_storage_support import recovered_candidate_evidence

NETWORK_METRICS = {'pagerank', 'hub_score', 'authority_score', 'degree_centrality', 'betweenness_centrality', 'weighted_centrality_cost', 'fan_in', 'fan_out', 'weighted_fan_in', 'weighted_fan_out', 'hop_2_node_count', 'hop_3_node_count', 'hop_2_token_cost', 'hop_3_token_cost'}
TOP_METRICS = {'top_pagerank': 'pagerank', 'top_hubs': 'hub_score', 'top_betweenness': 'betweenness_centrality', 'top_weighted_cost': 'weighted_centrality_cost', 'top_hop_2_cost': 'hop_2_token_cost', 'top_hop_3_cost': 'hop_3_token_cost'}


def _raw(architecture):
    result = {key: copy.deepcopy(architecture[key]) for key in ('nodes', 'edges')}
    for node in result['nodes']:
        node.get('metadata', {}).pop('analysis', None)
    return result


def _pairs(edges, weights):
    pairs = {}
    for edge in edges:
        targets = {edge['to_id'], *edge.get('candidates', [])} if edge['resolution'] == 'ambiguous' else {edge['to_id']}
        contribution = min(weights['confidence'][edge['confidence']], weights['resolution'][edge['resolution']]) / len(targets)
        for target in targets:
            if edge['from_id'] != target:
                pair = (edge['from_id'], target)
                pairs[pair] = max(pairs.get(pair, 0), contribution)
    return pairs


def _metric_rows(old_rows, rows, pairs):
    assert old_rows.keys() == rows.keys()
    incoming, outgoing = defaultdict(dict), defaultdict(dict)
    for (source, target), value in pairs.items():
        incoming[target][source] = value
        outgoing[source][target] = value
    for ident, row in rows.items():
        assert row.keys() == old_rows[ident].keys()
        assert {k: v for k, v in row.items() if k not in NETWORK_METRICS} == {k: v for k, v in old_rows[ident].items() if k not in NETWORK_METRICS}, ('unrelated metric changed', ident)
        assert row['fan_in'] == len(incoming[ident])
        assert row['fan_out'] == len(outgoing[ident])
        assert abs(row['weighted_fan_in'] - math.fsum(incoming[ident].values())) <= 1e-9
        assert abs(row['weighted_fan_out'] - math.fsum(outgoing[ident].values())) <= 1e-9
        for key in NETWORK_METRICS:
            assert type(row[key]) in {int, float} and math.isfinite(row[key]) and row[key] >= 0


def _fallback_costs(architecture, old_rows):
    adjusted = copy.deepcopy(old_rows)
    cached = architecture['stats'].get('analysis', {}).get('node_metrics', {})
    for node in architecture['nodes']:
        cost = node.get('cost') or {}
        metadata = node.get('metadata', {})
        if node.get('span') is not None or cost.get('token_estimate', 0) > 0 or metadata.get('file_path'):
            continue
        ident = node['id']
        assert ident in cached, ('fallback description lacks cached pre-final metric input', ident)
        description_metadata = copy.deepcopy(metadata)
        description_metadata['analysis'] = copy.deepcopy(cached[ident])
        text = json.dumps({'label': node.get('display_label') or node['label'], 'title': node.get('title'), 'metadata': description_metadata}, ensure_ascii=False, default=str)
        digits = re.findall('[0-9]+', text)
        remaining = re.sub('[0-9]+', '', text)
        estimate = max(1, math.ceil(len(remaining) / 4) + sum(math.ceil(len(run) / 3) for run in digits))
        original = old_rows[ident]
        multiplier = original['effective_token_cost'] / original['token_cost']
        adjusted[ident]['token_cost'] = estimate
        adjusted[ident]['effective_token_cost'] = estimate * multiplier
    return adjusted


def _rankings(rankings, metrics, members):
    for metric, entries in rankings.items():
        expected = [{'node_id': ident, 'value': metrics[ident][metric]} for ident in sorted(members, key=lambda ident: (-metrics[ident][metric], ident))[:10]]
        assert entries == expected, ('ranking inconsistent', metric)


def _spread(edges, threshold):
    evidence = defaultdict(list)
    for edge in edges:
        span = edge.get('evidence')
        if not span or not span.get('file_path'):
            continue
        row = {'path': span['file_path'], 'start_line': span['start_line'], 'end_line': span['end_line']}
        if edge['resolution'] == 'ambiguous':
            row.update(copy.deepcopy(edge))
        targets = {edge['to_id'], *edge.get('candidates', [])} if edge['resolution'] == 'ambiguous' else {edge['to_id']}
        for target in targets:
            evidence[target].append(row)
    expected = {}
    for target, records in evidence.items():
        paths = {e['path'] for e in records}
        extent = max(e['end_line'] for e in records) - min(e['start_line'] for e in records) + 1 if len(paths) == 1 else 0
        if len(paths) > 1 or extent > threshold:
            expected[target] = ({'file_count': len(paths), 'line_span': extent, 'line_threshold': threshold}, records)
    return expected


def assert_standalone_candidate_policy_transition(old_arch, old_report, arch, report, contents, category_members):
    assert_candidate_policy_transition(_raw(old_arch), _raw(arch), contents)
    clean_arch = without_candidate_policy_metadata(arch, 'architecture')
    clean_report = without_candidate_policy_metadata(recovered_candidate_evidence(report), 'bottlenecks')
    pairs = _pairs(arch['edges'], old_report['edge_weights'])
    old_network = old_report['dependency_network']
    network = clean_report['dependency_network']
    assert network['node_count'] == len(arch['nodes']) == old_network['node_count']
    assert network['edge_count'] == len(pairs)
    adjusted_costs = _fallback_costs(arch, old_network['node_metrics'])
    _metric_rows(adjusted_costs, network['node_metrics'], pairs)
    nodes = {n['id']: n for n in arch['nodes']}
    assert network['rankings'].keys() == old_network['rankings'].keys()
    _rankings(network['rankings'], network['node_metrics'], nodes)
    assert network['rankings_by_category'].keys() == old_network['rankings_by_category'].keys()
    assert category_members.keys() == old_network['rankings_by_category'].keys()
    membership = [ident for members in category_members.values() for ident in members]
    assert len(membership) == len(set(membership)) and set(membership) == nodes.keys(), 'frozen categories must partition preserved original nodes'
    for category, ranks in network['rankings_by_category'].items():
        assert ranks.keys() == old_network['rankings_by_category'][category].keys()
        _rankings(old_network['rankings_by_category'][category], old_network['node_metrics'], category_members[category])
        _rankings(ranks, network['node_metrics'], category_members[category])
    assert {k: v for k, v in network.items() if k not in {'node_metrics', 'node_count', 'edge_count', 'rankings', 'rankings_by_category'}} == {k: v for k, v in old_network.items() if k not in {'node_metrics', 'node_count', 'edge_count', 'rankings', 'rankings_by_category'}}
    stats, old_stats = clean_arch['stats'], old_arch['stats']
    for key, field in [('edges_by_relation', 'relation'), ('edges_by_confidence', 'confidence'), ('edges_by_resolution', 'resolution')]:
        if key in stats:
            original_all = dict(Counter(e[field] for e in old_arch['edges']))
            if old_stats[key] == original_all:
                scoped_edges = arch['edges']
            else:
                original_scope = dict(Counter(e[field] for e in old_arch['edges'] if e['relation'] not in {'TESTS', 'CONFIGURES'}))
                assert old_stats[key] == original_scope, ('unsupported original histogram scope', key)
                scoped_edges = [e for e in arch['edges'] if e['relation'] not in {'TESTS', 'CONFIGURES'}]
            assert stats[key] == dict(Counter(e[field] for e in scoped_edges)), ('histogram scope', key)
    analysis = stats.get('analysis')
    old_analysis = old_stats.get('analysis')
    if analysis is not None:
        if old_analysis is not None:
            _metric_rows(old_analysis['node_metrics'], analysis['node_metrics'], pairs)
            for value in (old_analysis['neighborhood_strategy'], analysis['neighborhood_strategy']):
                assert value in {'single_bfs_to_3_hops', 'exact_bitset', 'exact_hybrid'}
            assert {k: v for k, v in analysis.items() if k not in {'node_metrics', 'neighborhood_strategy'} and k not in TOP_METRICS} == {k: v for k, v in old_analysis.items() if k not in {'node_metrics', 'neighborhood_strategy'} and k not in TOP_METRICS}
        else:
            assert analysis == {}, 'previously absent analysis gained undeclared non-marker fields'
        if old_analysis is not None:
            for key, metric in TOP_METRICS.items():
                assert analysis[key] == [{'id': ident, 'label': nodes[ident].get('display_label') or nodes[ident]['label'], 'value': analysis['node_metrics'][ident][metric]} for ident in sorted(nodes, key=lambda ident: -analysis['node_metrics'][ident][metric])[:10]]
    histograms = {'edges_by_relation', 'edges_by_confidence', 'edges_by_resolution'}
    assert {k: v for k, v in stats.items() if k != 'analysis' and k not in histograms} == {k: v for k, v in old_stats.items() if k != 'analysis' and k not in histograms}
    assert set(stats) - {'analysis'} == set(old_stats) - {'analysis'}
    assert {k: v for k, v in clean_arch.items() if k not in {'nodes', 'edges', 'stats'}} == {k: v for k, v in old_arch.items() if k not in {'nodes', 'edges', 'stats'}}
    old_by_id = {n['id']: n for n in old_arch['nodes']}
    for ident, node in nodes.items():
        old_metrics = old_by_id[ident].get('metadata', {}).get('analysis')
        metrics = node.get('metadata', {}).get('analysis')
        if old_metrics is not None:
            expected = copy.deepcopy(old_metrics)
            for field in ('token_cost', 'effective_token_cost'):
                expected[field] = adjusted_costs[ident][field]
            _metric_rows({ident: expected}, {ident: metrics}, pairs)
        else:
            assert metrics is None
    unchanged = lambda candidates: [c for c in candidates if c['kind'] != 'evidence_spread']
    assert unchanged(clean_report['candidates']) == unchanged(old_report['candidates']), 'large/unresolved/unrelated candidate rules changed'
    expected_spread = _spread(arch['edges'], old_report['edge_weights']['large_node_line_threshold'])
    spread = {c['target']: c for c in clean_report['candidates'] if c['kind'] == 'evidence_spread'}
    assert len(spread) == sum(c['kind'] == 'evidence_spread' for c in clean_report['candidates'])
    assert spread.keys() == expected_spread.keys()
    for target, candidate in spread.items():
        metrics, evidence = expected_spread[target]
        assert candidate['metrics'] == metrics
        actual_records = Counter(json.dumps(e, sort_keys=True) for e in candidate['evidence'])
        expected_records = Counter(json.dumps(e, sort_keys=True) for e in evidence)
        assert actual_records == expected_records, ('spread evidence', target, list((actual_records - expected_records).items())[:1], list((expected_records - actual_records).items())[:1])
        assert candidate['coverage'] == 'static_analyzer_relation' and candidate['status'] == 'static_candidate'
        assert candidate['id'] == 'b:' + hashlib.sha256((target + '|spread').encode()).hexdigest()[:16]
        assert set(candidate) == {'id', 'kind', 'target', 'metrics', 'evidence', 'coverage', 'status'}
    assert {k: v for k, v in clean_report.items() if k not in {'dependency_network', 'candidates'}} == {k: v for k, v in old_report.items() if k not in {'dependency_network', 'candidates'}}
