"""Coverage for the tree-sitter TypeScript extraction: the typed node/edge fields and the
constructs the previous regex implementation could not see."""

import shutil
import tempfile
import unittest
from pathlib import Path

from language_analyzers.core import flags as flag_names
from language_analyzers.core.graph_models import Confidence, NodeKind, RelationKind, Resolution

try:
    import tree_sitter_language_pack  # noqa: F401
    _HAS_TREE_SITTER = True
except ImportError:
    _HAS_TREE_SITTER = False


@unittest.skipUnless(_HAS_TREE_SITTER, "tree-sitter and tree-sitter-language-pack are not installed")
class TypeScriptFixture(unittest.TestCase):
    def setUp(self):
        self.directory = Path(tempfile.mkdtemp()).resolve()

    def tearDown(self):
        shutil.rmtree(self.directory, ignore_errors=True)

    def write(self, relative_path, source):
        path = self.directory / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source, encoding="utf-8")

    def graph(self):
        from language_analyzers.typescript import TypeScriptAnalyzer

        architecture = TypeScriptAnalyzer(self.directory).analyze()
        return (
            {node.id: node for node in architecture.nodes},
            {(edge.from_id, edge.to_id, edge.relation): edge for edge in architecture.edges},
            architecture,
        )


class TestSyntaxAwareExtraction(TypeScriptFixture):
    def test_calls_inside_comments_and_strings_are_not_edges(self):
        self.write("lib.ts", "export function helper(): number {\n  return 1;\n}\n")
        self.write(
            "main.ts",
            'import { helper } from "./lib";\n'
            "\n"
            "export function run(): string {\n"
            "  // helper() must not count as a call\n"
            '  const text = "helper()";\n'
            "  /* helper() */\n"
            "  return text;\n"
            "}\n",
        )

        _, edges, _ = self.graph()

        self.assertNotIn(("ts:main.ts#run", "ts:lib.ts#helper", RelationKind.CALLS), edges)

    def test_a_real_call_is_still_found(self):
        self.write("lib.ts", "export function helper(): number {\n  return 1;\n}\n")
        self.write(
            "main.ts",
            'import { helper } from "./lib";\n\nexport function run(): number {\n  return helper();\n}\n',
        )

        _, edges, _ = self.graph()
        edge = edges[("ts:main.ts#run", "ts:lib.ts#helper", RelationKind.CALLS)]

        self.assertEqual(edge.resolution, Resolution.EXACT)
        self.assertEqual(edge.confidence, Confidence.STATIC_CERTAIN)
        self.assertEqual(edge.evidence.start_line, 4)

    def test_interfaces_type_aliases_and_enums_become_symbols(self):
        self.write(
            "types.ts",
            "export interface Shape {\n  area(): number;\n}\n"
            "\nexport type Id = string | number;\n"
            "\nexport enum Color {\n  Red,\n  Green,\n}\n",
        )

        nodes, _, _ = self.graph()

        self.assertEqual(nodes["ts:types.ts#Shape"].kind, NodeKind.INTERFACE)
        self.assertEqual(nodes["ts:types.ts#Id"].kind, NodeKind.TYPE_ALIAS)
        self.assertEqual(nodes["ts:types.ts#Color"].kind, NodeKind.ENUM)

    def test_class_fields_and_methods_are_contained_by_their_class(self):
        self.write(
            "widget.ts",
            "export class Widget {\n  label: string = 'x';\n\n  render(): string {\n    return this.label;\n  }\n}\n",
        )

        nodes, edges, _ = self.graph()

        self.assertEqual(nodes["ts:widget.ts#Widget.label"].kind, NodeKind.FIELD)
        self.assertEqual(nodes["ts:widget.ts#Widget.render"].kind, NodeKind.METHOD)
        self.assertIn(("ts:widget.ts#Widget", "ts:widget.ts#Widget.render", RelationKind.CONTAINS), edges)

    def test_implements_is_distinct_from_extends(self):
        self.write("base.ts", "export class Base {}\nexport interface Thing {\n  go(): void;\n}\n")
        self.write(
            "child.ts",
            'import { Base, Thing } from "./base";\n\nexport class Child extends Base implements Thing {\n  go(): void {}\n}\n',
        )

        _, edges, _ = self.graph()

        self.assertIn(("ts:child.ts#Child", "ts:base.ts#Base", RelationKind.INHERITS), edges)
        self.assertIn(("ts:child.ts#Child", "ts:base.ts#Thing", RelationKind.IMPLEMENTS), edges)

    def test_this_calls_resolve_within_the_class_and_its_base(self):
        self.write(
            "mod.ts",
            "export class Base {\n  inherited(): number {\n    return 1;\n  }\n}\n"
            "\nexport class Child extends Base {\n  own(): number {\n    return 2;\n  }\n"
            "\n  run(): number {\n    return this.own() + this.inherited();\n  }\n}\n",
        )

        _, edges, _ = self.graph()

        self.assertIn(("ts:mod.ts#Child.run", "ts:mod.ts#Child.own", RelationKind.CALLS), edges)
        self.assertIn(("ts:mod.ts#Child.run", "ts:mod.ts#Base.inherited", RelationKind.CALLS), edges)

    def test_new_expression_is_instantiates(self):
        self.write("models.ts", "export class User {}\n")
        self.write(
            "main.ts",
            'import { User } from "./models";\n\nexport function make(): User {\n  return new User();\n}\n',
        )

        _, edges, _ = self.graph()

        self.assertIn(("ts:main.ts#make", "ts:models.ts#User", RelationKind.INSTANTIATES), edges)

    def test_namespace_import_resolves_the_member(self):
        self.write("lib.ts", "export function helper(): number {\n  return 1;\n}\n")
        self.write(
            "main.ts",
            'import * as lib from "./lib";\n\nexport function run(): number {\n  return lib.helper();\n}\n',
        )

        _, edges, _ = self.graph()
        edge = edges[("ts:main.ts#run", "ts:lib.ts#helper", RelationKind.CALLS)]

        self.assertEqual(edge.resolution, Resolution.EXACT)

    def test_aliased_named_import_resolves_to_the_original_symbol(self):
        self.write("lib.ts", "export function helper(): number {\n  return 1;\n}\n")
        self.write(
            "main.ts",
            'import { helper as aliased } from "./lib";\n\nexport function run(): number {\n  return aliased();\n}\n',
        )

        _, edges, _ = self.graph()

        self.assertIn(("ts:main.ts#run", "ts:lib.ts#helper", RelationKind.CALLS), edges)

    def test_local_declaration_shadowing_an_import_creates_no_edge(self):
        self.write("lib.ts", "export function helper(): number {\n  return 1;\n}\n")
        self.write(
            "main.ts",
            'import { helper } from "./lib";\n\nexport function run(): number {\n'
            "  const helper = () => 2;\n  return helper();\n}\n",
        )

        _, edges, _ = self.graph()

        self.assertNotIn(("ts:main.ts#run", "ts:lib.ts#helper", RelationKind.CALLS), edges)

    def test_type_annotations_produce_type_uses_edges(self):
        self.write("models.ts", "export interface User {\n  id: string;\n}\n")
        self.write(
            "svc.ts",
            'import { User } from "./models";\n\nexport function find(user: User): User {\n  return user;\n}\n',
        )

        _, edges, _ = self.graph()

        self.assertIn(("ts:svc.ts#find", "ts:models.ts#User", RelationKind.TYPE_USES), edges)

    def test_ts1_class_type_parameter_constraint_produces_type_uses_edge(self):
        self.write("base.ts", "export class Base {}\n")
        self.write(
            "repo.ts",
            'import { Base } from "./base";\n\nexport class Repo<T extends Base> {}\n',
        )

        _, edges, _ = self.graph()

        self.assertIn(("ts:repo.ts#Repo", "ts:base.ts#Base", RelationKind.TYPE_USES), edges)

    def test_ts2_multiple_type_parameter_constraints_produce_one_edge_each(self):
        self.write("widget.ts", "export class Widget {}\nexport class Other {}\n")
        self.write(
            "main.ts",
            'import { Widget, Other } from "./widget";\n\n'
            "export function make<T extends Widget, U extends Other>() {}\n",
        )

        _, edges, _ = self.graph()

        self.assertIn(("ts:main.ts#make", "ts:widget.ts#Widget", RelationKind.TYPE_USES), edges)
        self.assertIn(("ts:main.ts#make", "ts:widget.ts#Other", RelationKind.TYPE_USES), edges)

    def test_ts3_unconstrained_type_parameter_produces_no_edge_and_no_error(self):
        self.write("foo.ts", "export class Foo<T> {}\n")

        nodes, edges, _ = self.graph()

        constraint_edges = [
            key for key in edges if key[0] == "ts:foo.ts#Foo" and key[2] == RelationKind.TYPE_USES
        ]
        self.assertEqual(constraint_edges, [])
        self.assertIn("ts:foo.ts#Foo", nodes)

    def test_ts4_unresolvable_call_type_argument_does_not_affect_the_call_edge(self):
        self.write("container.ts", "export class Container {}\n")
        self.write(
            "main.ts",
            'import { Container } from "./container";\n\n'
            "export function make() {\n  return new Container<Item>();\n}\n",
        )

        nodes, edges, _ = self.graph()

        self.assertIn(("ts:main.ts#make", "ts:container.ts#Container", RelationKind.INSTANTIATES), edges)
        type_use_edges = [
            key for key in edges if key[0] == "ts:main.ts#make" and key[2] == RelationKind.TYPE_USES
        ]
        self.assertEqual(type_use_edges, [])
        self.assertNotIn("Item", nodes["ts:main.ts#make"].metadata.get("unresolved_calls", {}))

    def test_ts5_call_type_argument_resolves_even_when_call_itself_is_unresolved(self):
        self.write("baz.ts", "export class Baz {}\n")
        self.write(
            "main.ts",
            'import { Baz } from "./baz";\n\n'
            "export function run() {\n  return foo.bar<Baz>();\n}\n",
        )

        _, edges, _ = self.graph()

        self.assertIn(("ts:main.ts#run", "ts:baz.ts#Baz", RelationKind.TYPE_USES), edges)
        self.assertNotIn(("ts:main.ts#run", "ts:baz.ts#Baz", RelationKind.CALLS), edges)


class TestReexportAndDynamicImports(TypeScriptFixture):
    def test_star_reexport_marks_a_barrel_and_links_every_exported_symbol(self):
        self.write("impl.ts", "export function alpha(): number {\n  return 1;\n}\nexport class Beta {}\n")
        self.write("index.ts", 'export * from "./impl";\n')

        nodes, edges, _ = self.graph()

        self.assertIn(flag_names.REEXPORT, nodes["ts:index.ts"].flags)
        self.assertIn(("ts:index.ts", "ts:impl.ts#alpha", RelationKind.RE_EXPORTS), edges)
        self.assertIn(("ts:index.ts", "ts:impl.ts#Beta", RelationKind.RE_EXPORTS), edges)

    def test_named_reexport_links_only_the_named_symbol(self):
        self.write("impl.ts", "export function alpha(): number {\n  return 1;\n}\nexport class Beta {}\n")
        self.write("index.ts", 'export { alpha } from "./impl";\n')

        _, edges, _ = self.graph()

        self.assertIn(("ts:index.ts", "ts:impl.ts#alpha", RelationKind.RE_EXPORTS), edges)
        self.assertNotIn(("ts:index.ts", "ts:impl.ts#Beta", RelationKind.RE_EXPORTS), edges)

    def test_a_module_with_real_code_is_not_a_barrel(self):
        self.write("impl.ts", "export function alpha(): number {\n  return 1;\n}\n")
        self.write("index.ts", 'export * from "./impl";\n\nexport const extra = 1;\n')

        nodes, _, _ = self.graph()

        self.assertNotIn(flag_names.REEXPORT, nodes["ts:index.ts"].flags)

    def test_dynamic_import_is_flagged_and_edged_with_lower_confidence(self):
        self.write("lazy.ts", "export function later(): number {\n  return 1;\n}\n")
        self.write("main.ts", 'export async function load() {\n  return await import("./lazy");\n}\n')

        nodes, edges, _ = self.graph()
        edge = edges[("ts:main.ts", "ts:lazy.ts", RelationKind.IMPORTS)]

        self.assertIn(flag_names.DYNAMIC_IMPORT, nodes["ts:main.ts"].flags)
        self.assertEqual(edge.confidence, Confidence.DYNAMIC_REQUIRED)

    def test_require_is_treated_as_a_dynamic_import(self):
        self.write("cjs.js", "function thing() {\n  return 1;\n}\n")
        self.write("main.js", 'const cjs = require("./cjs");\n')

        nodes, edges, _ = self.graph()

        self.assertIn(flag_names.DYNAMIC_IMPORT, nodes["ts:main.js"].flags)
        self.assertEqual(
            edges[("ts:main.js", "ts:cjs.js", RelationKind.IMPORTS)].confidence,
            Confidence.DYNAMIC_REQUIRED,
        )


class TestTypedFields(TypeScriptFixture):
    def test_symbols_carry_span_cost_and_signature(self):
        self.write("mod.ts", "export function compute(value: number): number {\n  return value * 2;\n}\n")

        nodes, _, _ = self.graph()
        node = nodes["ts:mod.ts#compute"]

        self.assertEqual(node.span.file_path, "mod.ts")
        self.assertEqual((node.span.start_line, node.span.end_line), (1, 3))
        self.assertEqual(node.language, "typescript")
        self.assertEqual(node.provenance, "typescript-core")
        self.assertTrue(node.exported)
        self.assertGreater(node.cost.token_estimate, 0)
        self.assertIn("value: number", node.signature)

    def test_file_node_span_covers_the_whole_file(self):
        self.write("mod.ts", "export const a = 1;\nexport const b = 2;\n")

        nodes, _, _ = self.graph()

        self.assertEqual(nodes["ts:mod.ts"].span.start_line, 1)
        self.assertEqual(nodes["ts:mod.ts"].span.end_line, 3)

    def test_ambiguous_call_records_candidates_and_flags_the_symbols(self):
        self.write("a.ts", "export function shared(): number {\n  return 1;\n}\n")
        self.write("b.ts", "export function shared(): number {\n  return 2;\n}\n")
        self.write("main.ts", "export function run(): number {\n  return shared();\n}\n")

        nodes, edges, _ = self.graph()
        ambiguous = [
            edge for key, edge in edges.items()
            if key[0] == "ts:main.ts#run" and key[2] == RelationKind.CALLS
        ]

        self.assertEqual(len(ambiguous), 1)
        self.assertEqual(ambiguous[0].resolution, Resolution.AMBIGUOUS)
        self.assertEqual(ambiguous[0].candidates, ["ts:b.ts#shared"])
        self.assertIn(flag_names.AMBIGUOUS_NAME, nodes["ts:a.ts#shared"].flags)

    def test_unimported_unique_name_is_inferred_not_certain(self):
        self.write("lib.ts", "export function onlyHere(): number {\n  return 1;\n}\n")
        self.write("main.ts", "export function run(): number {\n  return onlyHere();\n}\n")

        _, edges, _ = self.graph()
        edge = edges[("ts:main.ts#run", "ts:lib.ts#onlyHere", RelationKind.CALLS)]

        self.assertEqual(edge.resolution, Resolution.UNIQUE_NAME)
        self.assertEqual(edge.confidence, Confidence.STATIC_INFERRED)

    def test_calls_leaving_the_project_are_counted(self):
        self.write("main.ts", "export function run(text: string): number {\n  return parseInt(text, 10);\n}\n")

        nodes, _, _ = self.graph()

        self.assertEqual(nodes["ts:main.ts#run"].metadata["unresolved_calls"], {"parseInt": 1})

    def test_repeated_calls_accumulate_weight(self):
        self.write("lib.ts", "export function helper(): number {\n  return 1;\n}\n")
        self.write(
            "main.ts",
            'import { helper } from "./lib";\n\nexport function run(): number {\n'
            "  helper();\n  return helper();\n}\n",
        )

        _, edges, _ = self.graph()

        self.assertEqual(edges[("ts:main.ts#run", "ts:lib.ts#helper", RelationKind.CALLS)].weight, 2.0)

    def test_stats_expose_the_confidence_breakdown(self):
        self.write("lib.ts", "export function helper(): number {\n  return 1;\n}\n")
        self.write(
            "main.ts",
            'import { helper } from "./lib";\n\nexport function run(): number {\n  return helper();\n}\n',
        )

        _, _, architecture = self.graph()

        self.assertIn("static_certain", architecture.stats["edges_by_confidence"])
        self.assertEqual(architecture.stats["total_files"], 2)
        self.assertEqual([c.key for c in architecture.report_collections], ["symbols"])

    def test_tsx_files_are_parsed_with_the_tsx_grammar(self):
        self.write("button.tsx", "export function Button() {\n  return <div>hi</div>;\n}\n")

        nodes, _, _ = self.graph()

        self.assertEqual(nodes["ts:button.tsx#Button"].kind, NodeKind.FUNCTION)

    def test_empty_project_produces_an_empty_graph(self):
        _, _, architecture = self.graph()

        self.assertEqual(architecture.nodes, [])
        self.assertEqual(architecture.edges, [])


if __name__ == "__main__":
    unittest.main()
