"""Spec 485e71fc64c8a984 v1, VO2 (FR6): TypeScript HTTP client call-site collection.

Technique: equivalence partitioning. One partition per coverage item (fetch literal, fetch template,
fetch init method, axios.<7 methods>, axios(config), axios.request, same-file instance, imported
instance, non-literal url, non-literal method, top-level call, nested function). Observation is the
(source_id, http_method, path) tuple of TypeScriptAnalyzer(...).analyze().http_calls. Where a path is
resolvable it is compared after normalize_route_path so raw formatting is not constrained.
"""
import shutil
import tempfile
import unittest
from pathlib import Path

from framework_analyzers.route_matching import normalize_route_path
from language_analyzers.core.graph_models import RelationKind

try:
    import tree_sitter_language_pack  # noqa: F401
    _HAS_TREE_SITTER = True
except ImportError:
    _HAS_TREE_SITTER = False


@unittest.skipUnless(_HAS_TREE_SITTER, "tree-sitter and tree-sitter-language-pack are not installed")
class HttpCallFixture(unittest.TestCase):
    def setUp(self):
        self.directory = Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(shutil.rmtree, self.directory, ignore_errors=True)

    def write(self, relative_path, source):
        path = self.directory / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source, encoding="utf-8")

    def analyze(self):
        from language_analyzers.typescript import TypeScriptAnalyzer

        return TypeScriptAnalyzer(self.directory).analyze()

    def calls(self):
        """Sorted (source_id, method, normalized path or None) tuples."""
        result = []
        for item in self.analyze().http_calls:
            path = None if item.path is None else normalize_route_path(item.path)
            result.append((item.source_id, item.http_method, path))
        return sorted(result, key=lambda row: (row[0], row[1] or "", row[2] or ""))

    def assert_calls(self, expected):
        self.assertEqual(self.calls(), sorted(expected, key=lambda row: (row[0], row[1] or "", row[2] or "")))


class TestFetch(HttpCallFixture):
    def test_fetch_string_literal_defaults_to_get(self):
        self.write("m.ts", 'export function load() {\n  return fetch("/api/users");\n}\n')
        self.assert_calls([("ts:m.ts#load", "GET", "/api/users")])

    def test_C1_fetch_template_string_interpolation_becomes_a_parameter_segment(self):
        self.write("m.ts", "export function load(id: string) {\n  return fetch(`/api/users/${id}`);\n}\n")
        self.assert_calls([("ts:m.ts#load", "GET", "/api/users/{}")])

    def test_fetch_init_method_string_literal(self):
        self.write(
            "m.ts",
            'export function save() {\n  return fetch("/api/users", { method: "POST", body: "x" });\n}\n',
        )
        self.assert_calls([("ts:m.ts#save", "POST", "/api/users")])

    def test_fetch_init_without_method_defaults_to_get(self):
        self.write("m.ts", 'export function load() {\n  return fetch("/api/users", { headers: {} });\n}\n')
        self.assert_calls([("ts:m.ts#load", "GET", "/api/users")])

    def test_C9_fetch_variable_url_is_unresolvable(self):
        self.write("m.ts", "export function load(url: string) {\n  return fetch(url);\n}\n")
        calls = self.analyze().http_calls
        self.assertEqual([(c.source_id, c.path) for c in calls], [("ts:m.ts#load", None)])

    def test_C9_fetch_non_literal_method_gives_method_none_and_keeps_path(self):
        self.write("m.ts", 'export function go(m: string) {\n  return fetch("/x", { method: m });\n}\n')
        self.assert_calls([("ts:m.ts#go", None, "/x")])

    def test_C9_fetch_call_result_url_is_unresolvable(self):
        self.write("m.ts", "export function go() {\n  return fetch(buildUrl());\n}\n")
        calls = self.analyze().http_calls
        self.assertEqual([c.path for c in calls], [None])

    def test_fetch_evidence_is_the_call_site_span(self):
        self.write("m.ts", 'export function load() {\n  return fetch("/api/users");\n}\n')
        (call,) = self.analyze().http_calls
        self.assertEqual(call.evidence.file_path, "m.ts")
        self.assertEqual(call.evidence.start_line, 2)


class TestAxiosModuleCalls(HttpCallFixture):
    def test_each_axios_method_maps_to_its_upper_case_http_method(self):
        for name in ("get", "post", "put", "patch", "delete", "head", "options"):
            with self.subTest(method=name):
                self.write("m.ts", f'import axios from "axios";\nexport function f() {{\n  return axios.{name}("/api/x");\n}}\n')
                self.assert_calls([("ts:m.ts#f", name.upper(), "/api/x")])

    def test_axios_config_call_with_url_and_method(self):
        self.write(
            "m.ts",
            'import axios from "axios";\nexport function f() {\n  return axios({ url: "/api/users", method: "post" });\n}\n',
        )
        self.assert_calls([("ts:m.ts#f", "POST", "/api/users")])

    def test_C15_axios_config_method_is_normalized_to_upper_case(self):
        self.write(
            "m.ts",
            'import axios from "axios";\nexport function f() {\n  return axios({ url: "/api/users", method: "delete" });\n}\n',
        )
        self.assert_calls([("ts:m.ts#f", "DELETE", "/api/users")])

    def test_axios_config_without_method_defaults_to_get(self):
        self.write("m.ts", 'import axios from "axios";\nexport function f() {\n  return axios({ url: "/api/users" });\n}\n')
        self.assert_calls([("ts:m.ts#f", "GET", "/api/users")])

    def test_C15_axios_request_config(self):
        self.write(
            "m.ts",
            'import axios from "axios";\nexport function f() {\n  return axios.request({ url: "/api/users", method: "delete" });\n}\n',
        )
        self.assert_calls([("ts:m.ts#f", "DELETE", "/api/users")])

    def test_axios_request_config_without_method_defaults_to_get(self):
        self.write("m.ts", 'import axios from "axios";\nexport function f() {\n  return axios.request({ url: "/a" });\n}\n')
        self.assert_calls([("ts:m.ts#f", "GET", "/a")])

    def test_axios_template_url(self):
        self.write("m.ts", "import axios from 'axios';\nexport function f(id: string) {\n  return axios.get(`/api/users/${id}`);\n}\n")
        self.assert_calls([("ts:m.ts#f", "GET", "/api/users/{}")])

    def test_axios_variable_url_is_unresolvable(self):
        self.write("m.ts", 'import axios from "axios";\nexport function f(u: string) {\n  return axios.get(u);\n}\n')
        self.assertEqual([(c.source_id, c.path) for c in self.analyze().http_calls], [("ts:m.ts#f", None)])

    def test_axios_config_non_literal_method_gives_method_none(self):
        self.write(
            "m.ts",
            'import axios from "axios";\nexport function f(m: string) {\n  return axios({ url: "/x", method: m });\n}\n',
        )
        self.assert_calls([("ts:m.ts#f", None, "/x")])


class TestAxiosInstances(HttpCallFixture):
    def test_same_file_instance_prefixes_base_url_path(self):
        self.write(
            "m.ts",
            'import axios from "axios";\nconst api = axios.create({ baseURL: "https://h/api" });\n'
            'export function f() {\n  return api.get("/users");\n}\n',
        )
        self.assert_calls([("ts:m.ts#f", "GET", "/api/users")])

    def test_same_file_instance_config_and_request_forms(self):
        self.write(
            "m.ts",
            'import axios from "axios";\nconst api = axios.create({ baseURL: "/api" });\n'
            'export function a() {\n  return api({ url: "/x", method: "put" });\n}\n'
            'export function b() {\n  return api.request({ url: "/y" });\n}\n'
            'export function c() {\n  return api.delete("/z");\n}\n',
        )
        self.assert_calls([
            ("ts:m.ts#a", "PUT", "/api/x"),
            ("ts:m.ts#b", "GET", "/api/y"),
            ("ts:m.ts#c", "DELETE", "/api/z"),
        ])

    def test_C3_named_import_of_exported_instance_through_relative_import(self):
        self.write(
            "client.ts",
            'import axios from "axios";\nexport const api = axios.create({ baseURL: "https://h/api" });\n',
        )
        self.write(
            "main.ts",
            'import { api } from "./client";\nexport function createUser() {\n  return api.post("/users");\n}\n',
        )
        self.assert_calls([("ts:main.ts#createUser", "POST", "/api/users")])

    def test_default_import_of_exported_instance_through_relative_import(self):
        self.write(
            "client.ts",
            'import axios from "axios";\nconst http = axios.create({ baseURL: "/v1" });\nexport default http;\n',
        )
        self.write(
            "main.ts",
            'import client from "./client";\nexport function list() {\n  return client.get("/items");\n}\n',
        )
        self.assert_calls([("ts:main.ts#list", "GET", "/v1/items")])

    def test_import_from_subdirectory_relative_path(self):
        self.write(
            "lib/http.ts",
            'import axios from "axios";\nexport const api = axios.create({ baseURL: "/api" });\n',
        )
        self.write(
            "pages/main.ts",
            'import { api } from "../lib/http";\nexport function f() {\n  return api.get("/u");\n}\n',
        )
        self.assert_calls([("ts:pages/main.ts#f", "GET", "/api/u")])

    def test_object_named_like_an_instance_but_not_created_by_axios_is_ignored(self):
        self.write(
            "m.ts",
            'const api = makeClient({ baseURL: "/api" });\nexport function f() {\n  return api.get("/users");\n}\n',
        )
        self.assert_calls([])

    def test_unrelated_get_calls_are_not_http_calls(self):
        self.write(
            "m.ts",
            'const cache = new Map<string, string>();\nexport function f() {\n  cache.get("/a");\n  return fetchData("/b");\n}\n',
        )
        self.assert_calls([])


class TestSourceIdAndGraphIsolation(HttpCallFixture):
    def test_C16_top_level_fetch_belongs_to_the_module_node(self):
        self.write("m.ts", 'const p = fetch("/api/boot");\nexport function other() {\n  return 1;\n}\n')
        self.assert_calls([("ts:m.ts", "GET", "/api/boot")])

    def test_nested_class_method_is_the_innermost_enclosing_symbol(self):
        self.write(
            "m.ts",
            'export class Service {\n  load() {\n    return fetch("/api/users");\n  }\n}\n',
        )
        self.assert_calls([("ts:m.ts#Service.load", "GET", "/api/users")])

    def test_anonymous_callback_is_skipped_outward_to_the_named_function(self):
        self.write(
            "m.ts",
            'export function f(items: string[]) {\n  return items.map(() => fetch("/x"));\n}\n',
        )
        self.assert_calls([("ts:m.ts#f", "GET", "/x")])

    def test_anonymous_callback_at_module_scope_belongs_to_the_module_node(self):
        self.write("m.ts", 'const items: string[] = [];\nitems.map(() => fetch("/x"));\n')
        self.assert_calls([("ts:m.ts", "GET", "/x")])

    def test_calls_in_two_functions_and_module_scope_keep_their_own_sources(self):
        self.write(
            "m.ts",
            'fetch("/top");\nexport function a() {\n  return fetch("/a");\n}\nexport function b() {\n  return fetch("/b");\n}\n',
        )
        self.assert_calls([
            ("ts:m.ts", "GET", "/top"),
            ("ts:m.ts#a", "GET", "/a"),
            ("ts:m.ts#b", "GET", "/b"),
        ])

    def test_every_source_id_is_a_node_of_the_typescript_graph(self):
        self.write(
            "m.ts",
            'fetch("/top");\nexport function a() {\n  return fetch("/a");\n}\n'
            'export class S {\n  m() {\n    return fetch("/m");\n  }\n}\n',
        )
        architecture = self.analyze()
        ids = {node.id for node in architecture.nodes}
        self.assertEqual(len(architecture.http_calls), 3)
        for call in architecture.http_calls:
            self.assertIn(call.source_id, ids)

    def test_http_calls_are_not_added_to_nodes_or_edges(self):
        self.write("m.ts", 'export function a() {\n  return fetch("/a");\n}\n')
        architecture = self.analyze()
        self.assertEqual([node.id for node in architecture.nodes if "/a" in node.id], [])
        self.assertNotIn("CALLS_ROUTE", {edge.relation for edge in architecture.edges})
        self.assertEqual(RelationKind.CALLS_ROUTE, "CALLS_ROUTE")

    def test_file_without_http_calls_gives_empty_list(self):
        self.write("m.ts", "export function a() {\n  return 1;\n}\n")
        self.assertEqual(self.analyze().http_calls, [])


if __name__ == "__main__":
    unittest.main()
