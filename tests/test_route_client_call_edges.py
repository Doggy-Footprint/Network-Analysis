"""Spec 485e71fc64c8a984 v1, unit surfaces.

VO3: normalize_route_path (boundary value analysis + equivalence partitioning), hand-derived from FR7.
VO4: match_routes decision table over hand-built nodes and call sites (FR8, FR9).
VO8: CALLS_ROUTE edge weight under the loaded edge-weight profile (FR10).
"""
import pytest

from analysis import GraphAnalyzer
from analysis.edge_weights import default_edge_weights_path, load_edge_weights
from analysis.graph_metrics import GraphAnalysisConfig
from framework_analyzers.route_matching import match_routes, normalize_route_path
from language_analyzers.core.graph_models import (
    Confidence, GraphNode, RelationKind, Resolution, SourceSpan,
)
from language_analyzers.typescript.http_calls import HttpCallSite
from tests.edge_weights_support import edge, load_weights, symbol_nodes, weights_data

# ---------------------------------------------------------------- VO3

NORMALIZE_CASES = [
    # id, input, expected
    ("scheme_host", "https://example.com/api/users", "/api/users"),
    ("scheme_http_port", "http://localhost:8000/api/users", "/api/users"),
    ("host_port_https", "https://h:8443/x", "/x"),
    ("host_only_is_root", "https://h", "/"),
    ("host_only_with_port_is_root", "http://localhost:8000", "/"),
    ("leading_interpolation", "${API_URL}/api/users", "/api/users"),
    ("leading_interpolation_then_param", "${base}/users/${id}", "/users/{}"),
    ("query", "/api/users?q=1", "/api/users"),
    ("query_containing_slash_and_interpolation", "/a?next=/b&id=${id}", "/a"),
    ("fragment", "/api/users#top", "/api/users"),
    ("query_and_fragment", "/api/users?q=1#top", "/api/users"),
    ("trailing_slash", "/api/users/", "/api/users"),
    ("no_trailing_slash", "/api/users", "/api/users"),
    ("root", "/", "/"),
    ("double_slash_inside", "/api//users", "/api/users"),
    ("double_slash_only", "//", "/"),
    ("brace_param", "/users/{id}", "/users/{}"),
    ("colon_param", "/users/:id", "/users/{}"),
    ("template_param", "/users/${id}", "/users/{}"),
    ("partial_template_segment", "/files/a-${x}", "/files/{}"),
    ("path_converter", "/files/{p:path}", "/files/{}"),
    ("missing_leading_slash", "api/users", "/api/users"),
    ("missing_leading_slash_param", "api/users/{userId}", "/api/users/{}"),
    ("several_params", "/a/{x}/b/:y/c/${z}", "/a/{}/b/{}/c/{}"),
    ("interpolation_after_first_slash_is_a_segment", "/${x}/y", "/{}/y"),
    ("full_url_with_query_and_trailing_slash", "https://h/api/users/?q=1", "/api/users"),
]


@pytest.mark.parametrize("raw,expected", [case[1:] for case in NORMALIZE_CASES], ids=[case[0] for case in NORMALIZE_CASES])
def test_VO3_normalize_route_path(raw, expected):
    assert normalize_route_path(raw) == expected


@pytest.mark.parametrize("raw", ["", None, 5], ids=["empty", "none", "non_str"])
def test_VO3_empty_or_non_string_input_is_none(raw):
    assert normalize_route_path(raw) is None


# ---------------------------------------------------------------- VO4

SPAN = SourceSpan("client.ts", 3, 3, 2, 30)
RETROFIT_SPAN = SourceSpan("Api.kt", 7, 8, 0, 1)
STATS_KEYS = {"matched", "ambiguous", "unmatched", "unresolvable"}


def server(node_id, method, full_path):
    return GraphNode(node_id, node_id, "endpoint", "endpoint", metadata={"full_path": full_path, "http_method": method})


def retrofit(node_id, method, path):
    return GraphNode(
        node_id, node_id, "retrofit_endpoint", "retrofit_endpoint",
        metadata={"http_method": method, "path": path}, span=RETROFIT_SPAN,
    )


def call(source_id, method, path, span=SPAN):
    return HttpCallSite(source_id, method, path, span)


def pairs(edges):
    return sorted((item.from_id, item.to_id) for item in edges)


def test_VO4_C1_single_candidate_edge_has_the_specified_fields():
    nodes = [server("api:get_user", "GET", "/api/users/{id}")]
    edges, stats = match_routes(nodes, [call("ts:client.ts#load", "GET", "/api/users/${id}")])
    assert len(edges) == 1
    item = edges[0]
    assert (item.from_id, item.to_id, item.relation) == ("ts:client.ts#load", "api:get_user", "CALLS_ROUTE")
    assert item.relation == RelationKind.CALLS_ROUTE
    assert item.confidence == "framework_inferred"
    assert item.resolution == "unique_name"
    assert item.candidates == []
    assert item.evidence == SPAN
    assert item.metadata["framework_rule"] == {"id": "http.client_calls_route", "specificity": "unique"}
    assert stats == {"matched": 1, "ambiguous": 0, "unmatched": 0, "unresolvable": 0}


def test_VO4_C4_method_mismatch_gives_no_edge_and_counts_unmatched():
    nodes = [server("api:get_users", "GET", "/api/users")]
    edges, stats = match_routes(nodes, [call("ts:client.ts#make", "POST", "/api/users")])
    assert edges == []
    assert stats == {"matched": 0, "ambiguous": 0, "unmatched": 1, "unresolvable": 0}


def test_VO4_path_mismatch_gives_no_edge_and_counts_unmatched():
    nodes = [server("api:get_users", "GET", "/api/users")]
    edges, stats = match_routes(nodes, [call("ts:client.ts#f", "GET", "/api/other")])
    assert edges == []
    assert stats["unmatched"] == 1 and stats["matched"] == 0


def test_VO4_zero_servers_and_no_calls():
    edges, stats = match_routes([], [call("ts:client.ts#f", "GET", "/x")])
    assert edges == [] and stats == {"matched": 0, "ambiguous": 0, "unmatched": 1, "unresolvable": 0}
    edges, stats = match_routes([server("a", "GET", "/x")], [])
    assert edges == [] and stats == {"matched": 0, "ambiguous": 0, "unmatched": 0, "unresolvable": 0}


def test_VO4_C8_two_candidates_pick_lowest_id_and_list_the_rest():
    nodes = [server("b:health", "GET", "/health"), server("a:health", "GET", "/health")]
    edges, stats = match_routes(nodes, [call("ts:client.ts#ping", "GET", "/health")])
    assert len(edges) == 1
    item = edges[0]
    assert (item.from_id, item.to_id, item.relation) == ("ts:client.ts#ping", "a:health", "CALLS_ROUTE")
    assert item.resolution == "ambiguous"
    assert item.confidence == "framework_inferred"
    assert item.candidates == ["b:health"]
    assert item.evidence == SPAN
    assert item.metadata["framework_rule"] == {"id": "http.client_calls_route", "specificity": "ambiguous"}
    assert stats["ambiguous"] == 1 and stats["unmatched"] == 0 and stats["unresolvable"] == 0


def test_VO4_three_candidates_are_sorted_regardless_of_input_order():
    nodes = [server("c:h", "GET", "/h"), server("a:h", "GET", "/h"), server("b:h", "GET", "/h")]
    edges, _ = match_routes(nodes, [call("s", "GET", "/h")])
    assert [(item.to_id, item.candidates) for item in edges] == [("a:h", ["b:h", "c:h"])]


def test_VO4_only_same_method_servers_are_candidates():
    nodes = [server("a:get", "GET", "/x"), server("b:post", "POST", "/x")]
    edges, _ = match_routes(nodes, [call("s", "POST", "/x")])
    assert [(item.to_id, item.resolution, item.candidates) for item in edges] == [("b:post", "unique_name", [])]


@pytest.mark.parametrize(
    "method,path",
    [(None, "/x"), ("GET", None), (None, None)],
    ids=["method_none", "path_none", "both_none"],
)
def test_VO4_C9_unresolvable_calls_give_no_edge(method, path):
    edges, stats = match_routes([server("a:x", "GET", "/x")], [call("s", method, path)])
    assert edges == []
    assert stats == {"matched": 0, "ambiguous": 0, "unmatched": 0, "unresolvable": 1}


def test_VO4_C9_two_unresolvable_calls_count_two():
    calls = [call("s1", "GET", None), call("s2", None, "/x")]
    edges, stats = match_routes([server("a:x", "GET", "/x")], calls)
    assert edges == [] and stats["unresolvable"] == 2


def test_VO4_C2_retrofit_endpoint_is_a_client_with_its_own_span_as_evidence():
    nodes = [server("api:get_user", "GET", "/api/users/{user_id}"), retrofit("kt:UserApi.getUser", "GET", "api/users/{userId}")]
    edges, stats = match_routes(nodes, [])
    assert len(edges) == 1
    item = edges[0]
    assert (item.from_id, item.to_id, item.relation) == ("kt:UserApi.getUser", "api:get_user", "CALLS_ROUTE")
    assert item.evidence == RETROFIT_SPAN
    assert item.resolution == "unique_name" and item.confidence == "framework_inferred"
    assert item.metadata["framework_rule"] == {"id": "http.client_calls_route", "specificity": "unique"}
    assert stats == {"matched": 1, "ambiguous": 0, "unmatched": 0, "unresolvable": 0}


def test_VO4_retrofit_method_mismatch_is_unmatched():
    nodes = [server("api:x", "GET", "/x"), retrofit("kt:Api.post", "POST", "x")]
    edges, stats = match_routes(nodes, [])
    assert edges == [] and stats["unmatched"] == 1


def test_VO4_retrofit_ambiguous_target():
    nodes = [server("b:x", "GET", "/x"), server("a:x", "GET", "/x"), retrofit("kt:Api.get", "GET", "/x")]
    edges, _ = match_routes(nodes, [])
    assert [(item.from_id, item.to_id, item.resolution, item.candidates) for item in edges] == [
        ("kt:Api.get", "a:x", "ambiguous", ["b:x"])
    ]


def test_VO4_ts_and_retrofit_clients_of_one_route_yield_two_edges():
    nodes = [server("api:x", "GET", "/api/x"), retrofit("kt:Api.get", "GET", "api/x")]
    edges, _ = match_routes(nodes, [call("ts:c.ts#f", "GET", "/api/x")])
    assert pairs(edges) == [("kt:Api.get", "api:x"), ("ts:c.ts#f", "api:x")]


def test_VO4_duplicate_pair_from_one_function_is_kept_once():
    nodes = [server("api:x", "GET", "/api/x")]
    calls = [
        call("ts:c.ts#f", "GET", "/api/x", SourceSpan("c.ts", 2, 2)),
        call("ts:c.ts#f", "GET", "/api/x/", SourceSpan("c.ts", 5, 5)),
    ]
    edges, _ = match_routes(nodes, calls)
    assert pairs(edges) == [("ts:c.ts#f", "api:x")]


def test_VO4_distinct_callers_of_one_route_are_not_deduped():
    nodes = [server("api:x", "GET", "/api/x")]
    edges, _ = match_routes(nodes, [call("ts:c.ts#f", "GET", "/api/x"), call("ts:c.ts#g", "GET", "/api/x")])
    assert pairs(edges) == [("ts:c.ts#f", "api:x"), ("ts:c.ts#g", "api:x")]


def test_VO4_same_caller_two_routes_gives_two_edges():
    nodes = [server("api:x", "GET", "/x"), server("api:y", "GET", "/y")]
    edges, _ = match_routes(nodes, [call("s", "GET", "/x"), call("s", "GET", "/y")])
    assert pairs(edges) == [("s", "api:x"), ("s", "api:y")]


def test_VO4_normalization_is_applied_on_both_sides():
    nodes = [server("api:file", "GET", "/files/{p:path}"), server("api:user", "GET", "/api/users/{user_id}/")]
    calls = [
        call("s1", "GET", "/files/${x}"),
        call("s2", "GET", "http://localhost:8000/api/users/:id?q=1"),
        call("s3", "GET", "${API_URL}/api/users/${id}"),
    ]
    edges, stats = match_routes(nodes, calls)
    assert pairs(edges) == [("s1", "api:file"), ("s2", "api:user"), ("s3", "api:user")]
    assert stats["unmatched"] == 0


def test_VO4_C7_root_path_matches():
    edges, _ = match_routes([server("api:root", "GET", "/")], [call("s", "GET", "/")])
    assert pairs(edges) == [("s", "api:root")]


def test_VO4_nodes_without_both_full_path_and_http_method_are_not_servers():
    nodes = [
        GraphNode("only_path", "n", "endpoint", "endpoint", metadata={"full_path": "/x"}),
        GraphNode("only_method", "n", "endpoint", "endpoint", metadata={"http_method": "GET"}),
    ]
    edges, stats = match_routes(nodes, [call("s", "GET", "/x")])
    assert edges == [] and stats["unmatched"] == 1


def test_VO4_non_retrofit_nodes_with_method_and_path_are_not_clients():
    nodes = [
        server("api:x", "GET", "/x"),
        GraphNode("other", "n", "endpoint", "endpoint", metadata={"http_method": "GET", "path": "/x"}),
    ]
    edges, stats = match_routes(nodes, [])
    assert edges == []
    assert stats == {"matched": 0, "ambiguous": 0, "unmatched": 0, "unresolvable": 0}


def test_VO4_stats_have_exactly_the_four_documented_keys():
    _, stats = match_routes([], [])
    assert set(stats) == STATS_KEYS


def test_VO4_mixed_outcomes_are_counted_per_class():
    nodes = [server("a:one", "GET", "/one"), server("a:dup", "GET", "/dup"), server("b:dup", "GET", "/dup")]
    calls = [call("s1", "GET", "/one"), call("s2", "GET", "/dup"), call("s3", "GET", "/none"), call("s4", "GET", None)]
    edges, stats = match_routes(nodes, calls)
    assert pairs(edges) == [("s1", "a:one"), ("s2", "a:dup")]
    assert stats["unmatched"] == 1 and stats["unresolvable"] == 1 and stats["ambiguous"] == 1


# ---------------------------------------------------------------- VO8

def route_edge(source, target, resolution):
    return edge(
        source, target, Confidence.FRAMEWORK_INFERRED, resolution, relation=RelationKind.CALLS_ROUTE,
    )


def fan_in_metrics(profile):
    nodes = symbol_nodes("caller_u", "server_u", "caller_a", "server_a")
    edges = [
        route_edge("caller_u", "server_u", Resolution.UNIQUE_NAME),
        route_edge("caller_a", "server_a", Resolution.AMBIGUOUS),
    ]
    return GraphAnalyzer(GraphAnalysisConfig(edge_weights=profile)).analyze(nodes, edges, None)["node_metrics"]


def test_VO8_default_profile_weights_both_route_edges_at_point_three():
    metrics = fan_in_metrics(load_edge_weights(default_edge_weights_path()))
    assert metrics["server_u"]["weighted_fan_in"] == pytest.approx(0.3, abs=1e-12)
    assert metrics["server_a"]["weighted_fan_in"] == pytest.approx(0.3, abs=1e-12)
    assert metrics["caller_u"]["weighted_fan_out"] == pytest.approx(0.3, abs=1e-12)
    assert metrics["server_u"]["fan_in"] == 1 and metrics["server_a"]["fan_in"] == 1


@pytest.mark.parametrize(
    "confidence,unique,ambiguous,expected_unique,expected_ambiguous",
    [
        (0.6, 0.8, 0.5, 0.6, 0.5),   # unique: min(0.6, 0.8); ambiguous: min(0.6, 0.5)
        (0.9, 0.4, 0.7, 0.4, 0.7),   # resolution is the smaller side for unique; confidence for none
        (0.5, 0.5, 0.2, 0.5, 0.2),   # equal values
    ],
    ids=["confidence_smaller_for_unique", "resolution_smaller_for_unique", "equal_and_low_ambiguous"],
)
def test_VO8_weight_is_min_of_confidence_and_resolution_of_the_loaded_profile(
    tmp_path, confidence, unique, ambiguous, expected_unique, expected_ambiguous
):
    profile = load_weights(
        tmp_path,
        weights_data(
            confidence={"framework_inferred": confidence},
            resolution={"unique_name": unique, "ambiguous": ambiguous},
        ),
    )
    metrics = fan_in_metrics(profile)
    assert metrics["server_u"]["weighted_fan_in"] == pytest.approx(expected_unique, abs=1e-12)
    assert metrics["server_a"]["weighted_fan_in"] == pytest.approx(expected_ambiguous, abs=1e-12)


# ---------------------------------------------------------------- VO4 stats (spec v2)

def total(stats):
    return sum(stats[key] for key in STATS_KEYS)


def test_VO4_v2_empty_path_client_is_unresolvable():
    edges, stats = match_routes([server("a:x", "GET", "/x")], [call("s", "GET", "")])
    assert edges == []
    assert stats == {"matched": 0, "ambiguous": 0, "unmatched": 0, "unresolvable": 1}


def test_VO4_v2_ambiguous_client_is_not_counted_as_matched():
    nodes = [server("a:h", "GET", "/h"), server("b:h", "GET", "/h")]
    _, stats = match_routes(nodes, [call("s", "GET", "/h")])
    assert stats == {"matched": 0, "ambiguous": 1, "unmatched": 0, "unresolvable": 0}


def test_VO4_v2_deduped_call_sites_are_each_counted():
    nodes = [server("api:x", "GET", "/api/x")]
    calls = [call("ts:c.ts#f", "GET", "/api/x"), call("ts:c.ts#f", "GET", "/api/x/"), call("ts:c.ts#f", "GET", "/api/x?q=1")]
    edges, stats = match_routes(nodes, calls)
    assert pairs(edges) == [("ts:c.ts#f", "api:x")]
    assert stats == {"matched": 3, "ambiguous": 0, "unmatched": 0, "unresolvable": 0}


def test_VO4_v2_stats_are_exclusive_and_sum_to_the_number_of_clients():
    nodes = [
        server("a:one", "GET", "/one"), server("a:dup", "GET", "/dup"), server("b:dup", "GET", "/dup"),
        retrofit("kt:Api.one", "GET", "one"), retrofit("kt:Api.miss", "GET", "miss"),
    ]
    calls = [
        call("s1", "GET", "/one"), call("s1", "GET", "/one"), call("s2", "GET", "/dup"),
        call("s3", "GET", "/none"), call("s4", "GET", None), call("s5", None, "/one"), call("s6", "GET", ""),
    ]
    edges, stats = match_routes(nodes, calls)
    assert stats == {"matched": 3, "ambiguous": 1, "unmatched": 2, "unresolvable": 3}
    assert total(stats) == len(calls) + 2


@pytest.mark.parametrize(
    "metadata",
    [{"path": "x"}, {"http_method": "GET"}, {}],
    ids=["missing_http_method", "missing_path", "missing_both"],
)
def test_VO4_retrofit_endpoint_lacking_method_or_path_is_unresolvable(metadata):
    endpoint = GraphNode("kt:Api.f", "f", "retrofit_endpoint", "retrofit_endpoint", metadata=metadata, span=RETROFIT_SPAN)
    edges, stats = match_routes([server("api:x", "GET", "/x"), endpoint], [])
    assert edges == []
    assert stats == {"matched": 0, "ambiguous": 0, "unmatched": 0, "unresolvable": 1}
