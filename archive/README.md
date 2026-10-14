Code moved here is archived and not run by the analysis pipeline or pytest.
agent_view, report_m1, bottlenecks_v2 (harness/probe replay), and profiles/ were removed from the active tree by spec 8fd668e309160b58.
They may not import or run against the current code.
token_cost_disk_fallback was moved here because it bypassed the repository snapshot to read files from disk (spec f7564b09cf80bdd9); its tests live in archive/tests/test_graph_metrics_disk_fallback.py.
