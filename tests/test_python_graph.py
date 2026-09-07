import shutil
import tempfile
import unittest
from pathlib import Path

from language_analyzers.core import flags as flag_names
from language_analyzers.core.graph_models import Confidence, NodeKind, RelationKind, Resolution
from language_analyzers.python.graph import PythonGraphAnalyzer
from language_analyzers.python.source import PythonSourceAnalyzer
from language_analyzers.python.symbols import build_symbol_table, resolve_relative_module


class PythonProjectFixture(unittest.TestCase):
    def setUp(self):
        self.directory = Path(tempfile.mkdtemp()).resolve()

    def tearDown(self):
        shutil.rmtree(self.directory, ignore_errors=True)

    def write(self, relative_path, source):
        path = self.directory / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source, encoding="utf-8")

    def table(self):
        return build_symbol_table(PythonSourceAnalyzer(self.directory).analyze(), self.directory)

    def graph(self):
        architecture = PythonGraphAnalyzer(self.directory).analyze()
        return (
            {node.id: node for node in architecture.nodes},
            {(edge.from_id, edge.to_id, edge.relation): edge for edge in architecture.edges},
            architecture,
        )

    @staticmethod
    def relations(edges, relation):
        return {key for key in edges if key[2] == relation}


class TestResolveRelativeModule(unittest.TestCase):
    def test_absolute_import_is_returned_unchanged(self):
        self.assertEqual(resolve_relative_module("app.api", "app.models", 0), "app.models")

    def test_single_level_resolves_against_the_containing_package(self):
        self.assertEqual(resolve_relative_module("app.api", "deps", 1), "app.api.deps")

    def test_two_levels_climb_one_further(self):
        self.assertEqual(resolve_relative_module("app.api", "models", 2), "app.models")

    def test_bare_relative_import_yields_the_package(self):
        self.assertEqual(resolve_relative_module("app.api", None, 1), "app.api")

    def test_package_init_importing_a_sibling_stays_inside_the_package(self):
        # In pkg/__init__.py, __name__ and __package__ are both "pkg", so `from .impl import x`
        # must resolve to pkg.impl rather than climbing out of the package.
        self.assertEqual(resolve_relative_module("pkg", "impl", 1), "pkg.impl")


class TestSymbolTable(PythonProjectFixture):
    def test_qualnames_cover_nested_classes_methods_and_closures(self):
        self.write("mod.py", (
            "class Outer:\n"
            "    class Inner:\n"
            "        def method(self):\n"
            "            def closure():\n"
            "                return 1\n"
            "            return closure\n"
        ))

        ids = set(self.table().by_id)

        self.assertIn("py:mod#Outer", ids)
        self.assertIn("py:mod#Outer.Inner", ids)
        self.assertIn("py:mod#Outer.Inner.method", ids)
        self.assertIn("py:mod#Outer.Inner.method.<locals>.closure", ids)

    def test_import_alias_binds_the_local_name(self):
        self.write("target.py", "def helper():\n    return 1\n")
        self.write("caller.py", "from target import helper as aliased\n")

        table = self.table()

        self.assertEqual(table.resolve_in_module("caller", "aliased"), "py:target#helper")
        self.assertIsNone(table.resolve_in_module("caller", "helper"))

    def test_relative_import_binding_resolves_across_packages(self):
        self.write("app/__init__.py", "")
        self.write("app/core.py", "def setting():\n    return 1\n")
        self.write("app/api.py", "from .core import setting\n")

        self.assertEqual(self.table().resolve_in_module("app.api", "setting"), "py:app.core#setting")

    def test_collisions_count_distinct_defining_modules(self):
        self.write("a.py", "def shared():\n    return 1\n")
        self.write("b.py", "def shared():\n    return 2\n")
        self.write("c.py", "def unique():\n    return 3\n")

        table = self.table()

        self.assertEqual(table.collisions("shared"), 2)
        self.assertEqual(table.collisions("unique"), 1)
        self.assertEqual(table.collisions("absent"), 0)

    def test_dunder_all_defines_which_names_are_exported(self):
        self.write("mod.py", "__all__ = ['public']\n\ndef public():\n    pass\n\ndef also_public():\n    pass\n")

        table = self.table()

        self.assertTrue(table.by_id["py:mod#public"].exported)
        self.assertFalse(table.by_id["py:mod#also_public"].exported)

    def test_underscore_prefixed_names_are_not_exported_without_dunder_all(self):
        self.write("mod.py", "def _private():\n    pass\n\ndef public():\n    pass\n")

        table = self.table()

        self.assertFalse(table.by_id["py:mod#_private"].exported)
        self.assertTrue(table.by_id["py:mod#public"].exported)

    def test_import_only_package_init_is_marked_as_a_reexport(self):
        self.write("pkg/__init__.py", "from .impl import thing\n\n__all__ = ['thing']\n")
        self.write("pkg/impl.py", "def thing():\n    return 1\n")

        self.assertIn(flag_names.REEXPORT, self.table().modules["pkg"].flags)

    def test_package_init_with_real_code_is_not_a_reexport(self):
        self.write("pkg/__init__.py", "from .impl import thing\n\ndef extra():\n    return thing()\n")
        self.write("pkg/impl.py", "def thing():\n    return 1\n")

        self.assertNotIn(flag_names.REEXPORT, self.table().modules["pkg"].flags)

    def test_a_plain_module_is_never_a_reexport(self):
        self.write("mod.py", "from os import path\n")

        self.assertNotIn(flag_names.REEXPORT, self.table().modules["mod"].flags)


class TestPythonGraphEdges(PythonProjectFixture):
    def test_containment_runs_from_package_to_module_to_symbol(self):
        self.write("pkg/__init__.py", "")
        self.write("pkg/mod.py", "class Thing:\n    def method(self):\n        return 1\n")

        nodes, edges, _ = self.graph()

        self.assertEqual(nodes["py:pkg.mod"].kind, NodeKind.MODULE)
        self.assertEqual(nodes["py:pkg.mod#Thing"].kind, NodeKind.CLASS)
        self.assertEqual(nodes["py:pkg.mod#Thing.method"].kind, NodeKind.METHOD)
        self.assertIn(("py:pkg", "py:pkg.mod", RelationKind.CONTAINS), edges)
        self.assertIn(("py:pkg.mod", "py:pkg.mod#Thing", RelationKind.CONTAINS), edges)
        self.assertIn(("py:pkg.mod#Thing", "py:pkg.mod#Thing.method", RelationKind.CONTAINS), edges)

    def test_import_edges_carry_the_import_statement_as_evidence(self):
        self.write("target.py", "def helper():\n    return 1\n")
        self.write("caller.py", "import os\n\nfrom target import helper\n")

        _, edges, _ = self.graph()
        module_edge = edges[("py:caller", "py:target", RelationKind.IMPORTS)]
        symbol_edge = edges[("py:caller", "py:target#helper", RelationKind.IMPORTS_SYMBOL)]

        self.assertEqual(module_edge.evidence.start_line, 3)
        self.assertEqual(symbol_edge.evidence.start_line, 3)
        self.assertEqual(module_edge.confidence, Confidence.STATIC_CERTAIN)

    def test_third_party_imports_do_not_create_nodes_or_edges(self):
        self.write("caller.py", "import os\nfrom collections import Counter\n")

        nodes, edges, _ = self.graph()

        self.assertNotIn("py:os", nodes)
        self.assertEqual(self.relations(edges, RelationKind.IMPORTS), set())

    def test_reexporting_init_uses_a_distinct_relation(self):
        self.write("pkg/__init__.py", "from .impl import thing\n")
        self.write("pkg/impl.py", "def thing():\n    return 1\n")

        _, edges, _ = self.graph()

        self.assertIn(("py:pkg", "py:pkg.impl#thing", RelationKind.RE_EXPORTS), edges)
        self.assertNotIn(("py:pkg", "py:pkg.impl#thing", RelationKind.IMPORTS_SYMBOL), edges)

    def test_call_to_an_imported_function_is_exact(self):
        self.write("target.py", "def helper():\n    return 1\n")
        self.write("caller.py", "from target import helper\n\ndef run():\n    return helper()\n")

        _, edges, _ = self.graph()
        edge = edges[("py:caller#run", "py:target#helper", RelationKind.CALLS)]

        self.assertEqual(edge.resolution, Resolution.EXACT)
        self.assertEqual(edge.confidence, Confidence.STATIC_CERTAIN)
        self.assertEqual(edge.evidence.start_line, 4)
        self.assertEqual(edge.weight, 1.0)

    def test_repeated_calls_accumulate_weight_and_keep_the_first_evidence(self):
        self.write("target.py", "def helper():\n    return 1\n")
        self.write(
            "caller.py",
            "from target import helper\n\ndef run():\n    helper()\n    helper()\n    return helper()\n",
        )

        _, edges, _ = self.graph()
        edge = edges[("py:caller#run", "py:target#helper", RelationKind.CALLS)]

        self.assertEqual(edge.weight, 3.0)
        self.assertEqual(edge.evidence.start_line, 4)

    def test_unimported_but_project_unique_name_is_inferred(self):
        self.write("target.py", "def only_here():\n    return 1\n")
        self.write("caller.py", "def run():\n    return only_here()\n")

        _, edges, _ = self.graph()
        edge = edges[("py:caller#run", "py:target#only_here", RelationKind.CALLS)]

        self.assertEqual(edge.resolution, Resolution.UNIQUE_NAME)
        self.assertEqual(edge.confidence, Confidence.STATIC_INFERRED)

    def test_ambiguous_name_records_the_rejected_candidates(self):
        self.write("a.py", "def shared():\n    return 1\n")
        self.write("b.py", "def shared():\n    return 2\n")
        self.write("caller.py", "def run():\n    return shared()\n")

        _, edges, _ = self.graph()
        ambiguous = [
            edge for key, edge in edges.items()
            if key[0] == "py:caller#run" and key[2] == RelationKind.CALLS
        ]

        self.assertEqual(len(ambiguous), 1)
        self.assertEqual(ambiguous[0].resolution, Resolution.AMBIGUOUS)
        self.assertEqual(ambiguous[0].confidence, Confidence.STATIC_INFERRED)
        self.assertEqual(ambiguous[0].candidates, ["py:b#shared"])

    def test_colliding_names_flag_every_involved_symbol(self):
        self.write("a.py", "def shared():\n    return 1\n")
        self.write("b.py", "def shared():\n    return 2\n")

        nodes, _, _ = self.graph()

        self.assertIn(flag_names.AMBIGUOUS_NAME, nodes["py:a#shared"].flags)
        self.assertEqual(nodes["py:a#shared"].metadata["name_collision_count"], 2)

    def test_local_variable_shadowing_a_symbol_creates_no_edge(self):
        self.write("target.py", "def helper():\n    return 1\n")
        self.write("caller.py", "def run():\n    helper = lambda: 2\n    return helper()\n")

        _, edges, _ = self.graph()

        self.assertNotIn(("py:caller#run", "py:target#helper", RelationKind.CALLS), edges)

    def test_parameter_shadowing_a_symbol_creates_no_edge(self):
        self.write("target.py", "def helper():\n    return 1\n")
        self.write("caller.py", "from target import helper\n\ndef run(helper):\n    return helper()\n")

        _, edges, _ = self.graph()

        self.assertNotIn(("py:caller#run", "py:target#helper", RelationKind.CALLS), edges)

    def test_class_construction_is_instantiates_not_calls(self):
        self.write("models.py", "class User:\n    pass\n")
        self.write("caller.py", "from models import User\n\ndef run():\n    return User()\n")

        _, edges, _ = self.graph()

        self.assertIn(("py:caller#run", "py:models#User", RelationKind.INSTANTIATES), edges)
        self.assertNotIn(("py:caller#run", "py:models#User", RelationKind.CALLS), edges)

    def test_self_calls_resolve_within_the_class_and_its_bases(self):
        self.write("mod.py", (
            "class Base:\n"
            "    def inherited(self):\n"
            "        return 1\n"
            "\n"
            "class Child(Base):\n"
            "    def own(self):\n"
            "        return 2\n"
            "\n"
            "    def run(self):\n"
            "        return self.own() + self.inherited()\n"
        ))

        _, edges, _ = self.graph()

        self.assertIn(("py:mod#Child.run", "py:mod#Child.own", RelationKind.CALLS), edges)
        inherited = edges[("py:mod#Child.run", "py:mod#Base.inherited", RelationKind.CALLS)]
        self.assertEqual(inherited.resolution, Resolution.EXACT)

    def test_inheritance_edge_points_from_child_to_base(self):
        self.write("base.py", "class Base:\n    pass\n")
        self.write("child.py", "from base import Base\n\nclass Child(Base):\n    pass\n")

        _, edges, _ = self.graph()
        edge = edges[("py:child#Child", "py:base#Base", RelationKind.INHERITS)]

        self.assertEqual(edge.confidence, Confidence.STATIC_CERTAIN)
        self.assertEqual(edge.evidence.start_line, 3)

    def test_decorator_edge_points_from_decorator_to_decorated_symbol(self):
        self.write("deco.py", "def wrap(fn):\n    return fn\n")
        self.write("mod.py", "from deco import wrap\n\n@wrap\ndef target():\n    pass\n")

        _, edges, _ = self.graph()
        edge = edges[("py:deco#wrap", "py:mod#target", RelationKind.DECORATES)]

        self.assertEqual(edge.evidence.start_line, 3)

    def test_type_annotations_produce_type_uses_edges_including_generics(self):
        self.write("models.py", "class User:\n    pass\n")
        self.write(
            "svc.py",
            "from typing import List, Optional\nfrom models import User\n\n"
            "def find(user: User) -> Optional[List[User]]:\n    return None\n",
        )

        _, edges, _ = self.graph()

        self.assertIn(("py:svc#find", "py:models#User", RelationKind.TYPE_USES), edges)

    def test_module_level_constant_reads_and_writes(self):
        self.write("conf.py", "TIMEOUT = 30\n")
        self.write(
            "mod.py",
            "LOCAL = 1\n\ndef read_it():\n    return LOCAL\n\ndef write_it():\n    global LOCAL\n    LOCAL = 2\n",
        )

        _, edges, _ = self.graph()

        self.assertIn(("py:mod#read_it", "py:mod#LOCAL", RelationKind.READS), edges)
        self.assertIn(("py:mod#write_it", "py:mod#LOCAL", RelationKind.WRITES), edges)

    def test_nodes_carry_span_cost_signature_and_symbol_path(self):
        self.write("mod.py", "def compute(value: int) -> int:\n    return value * 2\n")

        nodes, _, _ = self.graph()
        node = nodes["py:mod#compute"]

        self.assertEqual(node.span.file_path, "mod.py")
        self.assertEqual((node.span.start_line, node.span.end_line), (1, 2))
        # "def compute(value: int) -> int:" (31) + newline + "    return value * 2" (20) = 52
        # 51 non-digit chars -> ceil(51/4) = 13, plus the digit run "2" -> 1 = 14.
        self.assertEqual(node.cost.char_count, 52)
        self.assertEqual(node.cost.token_estimate, 14)
        self.assertEqual(node.signature, "def compute(value: int) -> int")
        self.assertEqual(node.symbol_path, "mod.compute")
        self.assertEqual(node.language, "python")
        self.assertEqual(node.provenance, "python-core")

    def test_docstring_first_line_is_captured(self):
        self.write("mod.py", 'def thing():\n    """Does a thing.\n\n    More text.\n    """\n    return 1\n')

        nodes, _, _ = self.graph()

        self.assertEqual(nodes["py:mod#thing"].docstring, "Does a thing.")


class TestFrictionSignals(PythonProjectFixture):
    def test_dynamic_import_flags_the_symbol_and_creates_a_dynamic_edge(self):
        self.write("plugins/__init__.py", "")
        self.write("plugins/alpha.py", "def run():\n    return 1\n")
        self.write("loader.py", "import importlib\n\ndef load():\n    return importlib.import_module('plugins.alpha')\n")

        nodes, edges, _ = self.graph()
        edge = edges[("py:loader#load", "py:plugins.alpha", RelationKind.IMPORTS)]

        self.assertIn(flag_names.DYNAMIC_IMPORT, nodes["py:loader#load"].flags)
        self.assertEqual(edge.confidence, Confidence.DYNAMIC_REQUIRED)
        self.assertEqual(edge.evidence.start_line, 4)

    def test_getattr_with_a_computed_name_is_flagged(self):
        self.write("mod.py", "def pick(obj, name):\n    return getattr(obj, name)\n")

        nodes, _, _ = self.graph()

        self.assertIn(flag_names.DYNAMIC_ATTR, nodes["py:mod#pick"].flags)

    def test_getattr_with_a_constant_name_is_not_flagged(self):
        self.write("mod.py", "def pick(obj):\n    return getattr(obj, 'value')\n")

        nodes, _, _ = self.graph()

        self.assertNotIn(flag_names.DYNAMIC_ATTR, nodes["py:mod#pick"].flags)

    def test_eval_is_flagged(self):
        self.write("mod.py", "def run(expression):\n    return eval(expression)\n")

        nodes, _, _ = self.graph()

        self.assertIn(flag_names.DYNAMIC_EVAL, nodes["py:mod#run"].flags)

    def test_generated_and_test_paths_flag_their_symbols(self):
        self.write("alembic/versions/abc_init.py", "def upgrade():\n    pass\n")
        self.write("tests/test_thing.py", "def test_thing():\n    pass\n")

        nodes, _, _ = self.graph()

        self.assertIn(flag_names.GENERATED, nodes["py:alembic.versions.abc_init#upgrade"].flags)
        self.assertIn(flag_names.TEST, nodes["py:tests.test_thing#test_thing"].flags)

    def test_calls_leaving_the_project_are_counted_not_dropped_silently(self):
        self.write("mod.py", "import json\n\ndef run(payload):\n    return json.dumps(payload) + str(len(payload))\n")

        nodes, _, _ = self.graph()

        self.assertEqual(
            nodes["py:mod#run"].metadata["unresolved_calls"],
            {"dumps": 1, "len": 1, "str": 1},
        )


class TestArchitectureShape(PythonProjectFixture):
    def test_analyze_reports_stats_and_a_symbol_collection(self):
        self.write("mod.py", "def helper():\n    return 1\n\ndef run():\n    return helper()\n")

        _, _, architecture = self.graph()

        self.assertEqual(architecture.project_path, str(self.directory))
        self.assertEqual(architecture.stats["total_modules"], 1)
        self.assertEqual(architecture.stats["nodes_by_kind"][NodeKind.FUNCTION], 2)
        self.assertEqual(architecture.stats["edges_by_confidence"]["static_certain"], 3)
        self.assertEqual([c.key for c in architecture.report_collections], ["symbols"])
        self.assertTrue(all("symbol_path" in row for row in architecture.report_collections[0].rows))

    def test_empty_project_produces_an_empty_graph(self):
        _, _, architecture = self.graph()

        self.assertEqual(architecture.nodes, [])
        self.assertEqual(architecture.edges, [])
        self.assertEqual(architecture.stats["total_modules"], 0)

    def test_a_file_that_does_not_parse_is_skipped_rather_than_raising(self):
        self.write("broken.py", "def (:\n")
        self.write("fine.py", "def ok():\n    return 1\n")

        nodes, _, _ = self.graph()

        self.assertIn("py:fine#ok", nodes)
        self.assertNotIn("py:broken", nodes)


if __name__ == "__main__":
    unittest.main()
