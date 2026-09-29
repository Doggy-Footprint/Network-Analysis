"""VO-7 of the archived report-readability-finish spec (renderers/html/static/app.js
`buildOverview` category label rule). The remaining obligations of that spec
target report/m1 and live in archive/tests/test_readability_finish.py.

VO-7 (FR-6, C-9): equivalence partitioning over {category in
file/module/package (label != file_path) x1 each, category=function
(label != file_path)}, checked on `buildOverview`'s `focus` array.
"""
import json
import unittest

from tests.test_readability_dashboard import run_overview_js


def _overview_node(node_id, label, file_path, category, **metrics):
    return {
        "id": node_id, "label": label, "category": category,
        "span": {"file_path": file_path},
        "metadata": {"analysis": metrics},
    }


class TestVO7BuildOverviewCategoryLabelRule(unittest.TestCase):
    """VO-7 (FR-6, C-9): equivalence partitioning over the 2 declared
    coverage items (category in {file, module, package} x1 each, and
    category=function, all with label != file_path). Expected short/full
    labels reuse file_path pairs already independently established by
    tests.test_readability_dashboard's VO-18 (FR-1's short_labels
    algorithm), not re-derived here."""

    def test_file_category_with_custom_label_shows_the_short_file_label_and_full_label_is_the_file_path(self):
        nodes = [
            _overview_node("py:app/src/pkg/mod.py", "Foo", "app/src/pkg/mod.py", "file", weighted_centrality_cost=30),
            _overview_node("py:app/src/other/util.py", "app/src/other/util.py", "app/src/other/util.py", "file", weighted_centrality_cost=20),
        ]
        result = run_overview_js(json.dumps(nodes))
        by_id = {item["id"]: item for item in result["focus"]}
        item = by_id["py:app/src/pkg/mod.py"]
        self.assertEqual(item["label"], "mod.py")
        self.assertEqual(item["full_label"], "app/src/pkg/mod.py")

    def test_module_category_with_custom_label_shows_the_short_file_label_and_full_label_is_the_file_path(self):
        nodes = [
            _overview_node("py:pkg/graph.py", "Foo", "pkg/graph.py", "module", weighted_centrality_cost=50),
            _overview_node("py:pkg/other.py", "pkg/other.py", "pkg/other.py", "module", weighted_centrality_cost=40),
        ]
        result = run_overview_js(json.dumps(nodes))
        by_id = {item["id"]: item for item in result["focus"]}
        item = by_id["py:pkg/graph.py"]
        self.assertEqual(item["label"], "graph.py")
        self.assertEqual(item["full_label"], "pkg/graph.py")

    def test_package_category_with_custom_label_and_colliding_basenames_shows_the_full_path_label(self):
        # FR-1: "a/x/m.py" vs "b/x/m.py" collide on both basename ("m.py")
        # and one-level-up dir ("x/m.py"), so the full path is the required
        # short label (same pair as VO-18's third coverage item).
        nodes = [
            _overview_node("py:a/x/m.py", "Foo", "a/x/m.py", "package", weighted_centrality_cost=50),
            _overview_node("py:b/x/m.py", "Bar", "b/x/m.py", "package", weighted_centrality_cost=40),
        ]
        result = run_overview_js(json.dumps(nodes))
        by_id = {item["id"]: item for item in result["focus"]}
        item = by_id["py:a/x/m.py"]
        self.assertEqual(item["label"], "a/x/m.py")
        self.assertEqual(item["full_label"], "a/x/m.py")

    def test_non_file_module_package_category_with_custom_label_shows_file_label_colon_label(self):
        nodes = [
            _overview_node("py:pkg/graph.py#resolve", "resolve", "pkg/graph.py", "function", weighted_centrality_cost=50),
            _overview_node("py:pkg/other.py", "pkg/other.py", "pkg/other.py", "module", weighted_centrality_cost=1),
        ]
        result = run_overview_js(json.dumps(nodes))
        by_id = {item["id"]: item for item in result["focus"]}
        item = by_id["py:pkg/graph.py#resolve"]
        self.assertEqual(item["label"], "graph.py:resolve")


if __name__ == "__main__":
    unittest.main()
