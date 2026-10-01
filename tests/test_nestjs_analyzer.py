"""Spec 7a2c91e6d80f4b35 v2: independent O1–O5 and O10 source oracles."""
import tempfile
import unittest
from pathlib import Path

from tests.nestjs_support import (
    analyze, diagnostics, edge_names, endpoint_data, fixture, framework_nodes,
    node_name, oracle, write_project,
)


COMMON = "import { Module, Controller, Injectable, Get, Post, Put, Delete, Patch, Options, Head } from '@nestjs/common';\n"
CORE = "import { NestFactory } from '@nestjs/core';\n"


class NestProject(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()

    def graph(self, files, **kwargs):
        write_project(self.root, files)
        return analyze(self.root, **kwargs)

    def names(self, arch, kind):
        return {node_name(n) for n in framework_nodes(arch, kind)}

    def codes(self, arch):
        return {d["code"] for d in diagnostics(arch)}


class TestDeclarations(NestProject):
    def test_O1_export_wrappers_siblings_alias_namespace_and_unrelated_decorator(self):
        arch = self.graph({"src/a.ts": """
import { Module as NestModule, Controller as NestController, Injectable as Service } from '@nestjs/common';
import * as Nest from '@nestjs/common';
import { Controller } from './other';
@NestModule({controllers:[Listed], providers:[Plain]})
export class Root {}
@NestController('listed')
export class Listed {}
@Service()
class ServiceClass {}
@Nest.Injectable()
export class NamespaceService {}
class Plain {}
@Controller('false')
class Wrong {}
""", "src/other.ts": "export const Controller = () => () => {};"})
        self.assertEqual(self.names(arch, "module"), {"Root"})
        self.assertEqual(self.names(arch, "controller"), {"Listed"})
        self.assertEqual(self.names(arch, "provider"), {"Plain", "ServiceClass", "NamespaceService"})
        self.assertNotIn("Wrong", {node_name(n) for n in framework_nodes(arch)})
        self.assertIn(("Root", "Plain"), edge_names(arch, "PROVIDES"))

    def test_O1_plain_and_exported_classes_attached_to_preceding_decorators(self):
        arch = self.graph({"main.ts": COMMON + "@Controller()\nclass Plain {}\n@Module({controllers:[Plain]})\nexport class Root {}\n"})
        self.assertEqual(self.names(arch, "controller"), {"Plain"})
        self.assertEqual(self.names(arch, "module"), {"Root"})


class TestReferences(NestProject):
    def test_O2_all_module_relations_duplicate_and_cycle(self):
        arch = self.graph({"src/main.ts": COMMON + """
@Injectable() export class S {}
@Controller() export class C {}
@Module({imports:[B,B], controllers:[C,C], providers:[S,S], exports:[S,B]}) export class A {}
@Module({imports:[A]}) export class B {}
"""})
        for relation, expected in {
            "INCLUDES": {("A", "B"), ("B", "A")},
            "DECLARES": {("A", "C")},
            "PROVIDES": {("A", "S")},
            "EXPORTS": {("A", "S"), ("A", "B")},
        }.items():
            self.assertEqual(edge_names(arch, relation), expected, relation)
            actual_edges = [e for e in arch.edges if e.relation == relation and e.from_id.startswith("nestjs:")]
            self.assertEqual(len(actual_edges), len(expected), relation)
            self.assertEqual(len({(e.from_id, e.to_id) for e in actual_edges}), len(expected), relation)

    def test_O2_relative_named_default_namespace_suffixless_and_index(self):
        arch = self.graph({
            "src/a.ts": COMMON + "import { Named as Renamed } from './named';\nimport Default from './default';\nimport * as Ns from './nested';\n@Module({imports:[Renamed,Default,Ns.IndexModule]}) export class Root {}",
            "src/named.ts": COMMON + "@Module({}) export class Named {}",
            "src/default.ts": COMMON + "@Module({}) export default class Default {}",
            "src/nested/index.ts": COMMON + "@Module({}) export class IndexModule {}",
        })
        self.assertEqual(edge_names(arch, "INCLUDES"), {("Root", "Named"), ("Root", "Default"), ("Root", "IndexModule")})

    def test_O2_mixed_dynamic_barrel_paths_external_and_shadowed_refs_do_not_guess(self):
        arch = self.graph({
            "src/root.ts": COMMON + "import { Good } from './good';\nimport { Lost } from './barrel';\nimport { Alias } from '@app/alias';\nimport { External } from 'external';\n@Module({imports:[Good,Lost,Alias,External,makeModule()]}) export class Root {}",
            "src/good.ts": COMMON + "@Module({}) export class Good {}",
            "src/barrel.ts": "export { Lost } from './lost';",
            "src/lost.ts": COMMON + "@Module({}) export class Lost {}",
            "src/alias.ts": COMMON + "@Module({}) export class Alias {}",
            "src/external.ts": COMMON + "@Module({}) export class External {}",
        })
        self.assertEqual(edge_names(arch, "INCLUDES"), {("Root", "Good")})
        self.assertTrue({"unsupported_expression", "unresolved_reference"} <= self.codes(arch))

    def test_O2_shadowed_and_ambiguous_reference(self):
        arch = self.graph({"main.ts": COMMON + "@Module({imports:[Shared]}) class A {}\n@Module({}) class Shared {}\n@Module({}) class Shared {}"})
        self.assertEqual(edge_names(arch, "INCLUDES"), set())
        self.assertIn("ambiguous_reference", self.codes(arch))

    def test_O2_local_shadow_prevents_import_name_fallback(self):
        arch = self.graph({
            "src/main.ts": COMMON + "import {Target} from './target'; const Target = unknownValue; @Module({imports:[Target]}) class Local {}",
            "src/target.ts": COMMON + "@Module({}) export class Target {}",
        })
        self.assertIn("Local", self.names(arch, "module"))
        self.assertNotIn(("Local", "Target"), edge_names(arch, "INCLUDES"))
        self.assertIn("unresolved_reference", self.codes(arch))


class TestDI(NestProject):
    def test_O3_three_consumer_kinds_alias_and_unregistered_injectable(self):
        arch = self.graph({
            "src/s.ts": COMMON + "@Injectable() export class Service {}",
            "src/main.ts": COMMON + "import { Service as Renamed } from './s';\n@Controller() class C { constructor(s: Renamed) {} }\n@Injectable() class P { constructor(s: Renamed) {} }\n@Module({controllers:[C],providers:[P]}) class M { constructor(s: Renamed) {} }",
        })
        self.assertEqual(edge_names(arch, "DEPENDS_ON"), {("C", "Service"), ("P", "Service"), ("M", "Service")})
        self.assertNotIn(("M", "Service"), edge_names(arch, "PROVIDES"))

    def test_O3_same_name_external_interface_alias_generic_union_explicit_injection(self):
        arch = self.graph({
            "src/local.ts": COMMON + "@Injectable() export class Shared {}",
            "src/other.ts": COMMON + "@Injectable() export class Shared {}",
            "src/main.ts": COMMON + "import { Shared as Local } from './local';\nimport { Shared as Other } from './other';\nimport { External } from 'pkg';\ninterface Contract {}\ntype Alias = Local;\nclass Ordinary {}\n@Controller() class C { constructor(a: Local, b: Other, c: External, d: Contract, e: Alias, f: Promise<Local>, g: Local | Other, @Inject('x') h: Local, i: Ordinary) {} }",
        })
        pairs = edge_names(arch, "DEPENDS_ON")
        targets = {e.to_id for e in arch.edges if e.relation == "DEPENDS_ON" and e.from_id == "nestjs:controller:src/main.ts#C"}
        self.assertEqual(targets, {"nestjs:provider:src/local.ts#Shared", "nestjs:provider:src/other.ts#Shared"})
        self.assertEqual({target for source, target in pairs if source == "C"}, {"Shared"})
        self.assertIn("unsupported_expression", self.codes(arch))


class TestPaths(NestProject):
    def test_O4_http_grammar_literals_and_unsupported_expressions(self):
        source = COMMON + """
@Controller('//items//') class C {
 @Get() a() {}
 @Post('') b() {}
 @Put("/:id//") c() {}
 @Delete(`tail`) d() {}
 @Patch('/patch') e() {}
 @Options('/options') f() {}
 @Head('/head') g() {}
 @Get(['x']) h() {}
 @Get({path:'x'}) i() {}
 @Get(prefix + 'x') j() {}
 @Get(`x/${value}`) k() {}
 @Get('*') l() {}
}
"""
        arch = self.graph({"main.ts": source})
        endpoints = framework_nodes(arch, "endpoint")
        self.assertEqual(len(endpoints), 12)
        self.assertTrue(all({"http_method", "path", "controller_path", "relative_path", "full_path"} <= n.metadata.keys() for n in endpoints))
        self.assertTrue(all(n.metadata["controller_path"] == "/items" for n in endpoints))
        self.assertTrue(all(n.metadata["full_path"] is None for n in endpoints))
        observed = {(n.metadata["http_method"], n.metadata["relative_path"]) for n in endpoints}
        expected = {("GET", "/items"): "/", ("POST", "/items"): "/", ("PUT", "/items/:id"): "/:id",
                    ("DELETE", "/items/tail"): "/tail", ("PATCH", "/items/patch"): "/patch",
                    ("OPTIONS", "/items/options"): "/options", ("HEAD", "/items/head"): "/head"}
        for key, path in expected.items():
            self.assertIn(key, observed)
            matching = [n for n in endpoints if (n.metadata["http_method"], n.metadata["relative_path"]) == key]
            self.assertEqual(len(matching), 1)
            self.assertEqual(matching[0].metadata["path"], path)
        unsupported = [n for n in endpoints if n.metadata["relative_path"] is None]
        self.assertEqual(len(unsupported), 5)
        self.assertTrue(all(n.metadata["path"] is None and n.metadata["full_path"] is None for n in unsupported))
        self.assertIn("unsupported_expression", self.codes(arch))


class TestBootstrap(NestProject):
    def project(self, bootstrap, *, import_root=True, controller=True):
        app = COMMON + ("@Module({controllers:[C]}) class Root {}\n" if controller else "@Module({}) class Root {}\n") + "@Controller('x') class C { @Get('y') handler() {} }\n" + bootstrap
        return self.graph({"main.ts": app})

    def test_O5_single_literal_prefix_and_missing_prefix(self):
        for prefix, expected in [("app.setGlobalPrefix('api');", "/api/x/y"), ("", "/x/y")]:
            with self.subTest(prefix=prefix):
                arch = self.project(CORE + "async function start(){const app=await NestFactory.create(Root);" + prefix + "}")
                self.assertIn(("GET", expected), endpoint_data(arch))

    def test_O5_unreachable_absent_multiple_unresolved_bootstraps(self):
        cases = {
            "unreachable": (CORE + "const app=NestFactory.create(Root);", False),
            "absent": ("", True),
            "multiple": (CORE + "const a=NestFactory.create(Root); const b=NestFactory.create(Root);", True),
            "unresolved": (CORE + "const a=NestFactory.create(Missing);", True),
        }
        for label, (bootstrap, registered) in cases.items():
            with self.subTest(label=label):
                arch = self.project(bootstrap, controller=registered)
                self.assertIn(("GET", None), endpoint_data(arch))

    def test_O5_dynamic_multiple_options_and_other_function_prefix(self):
        cases = ["app.setGlobalPrefix(prefix);", "app.setGlobalPrefix('a');app.setGlobalPrefix('b');", "app.setGlobalPrefix('a', {});"]
        for prefix in cases:
            with self.subTest(prefix=prefix):
                arch = self.project(CORE + "async function start(){const app=await NestFactory.create(Root);" + prefix + "}")
                self.assertIn(("GET", None), endpoint_data(arch))

    def test_O5_other_function_prefix_does_not_attach(self):
        arch = self.project(CORE + "async function start(){const app=await NestFactory.create(Root); function other(){app.setGlobalPrefix('a');}}")
        self.assertIn(("GET", "/x/y"), endpoint_data(arch))

    def test_O5_factory_named_alias_and_namespace(self):
        for factory in ["import {NestFactory as Factory} from '@nestjs/core';\nFactory.create(Root)", "import * as Nest from '@nestjs/core';\nNest.NestFactory.create(Root)"]:
            with self.subTest(factory=factory):
                imported, call = factory.split("\n")
                arch = self.project(imported + "\nasync function start(){const app=await " + call + ";}")
                self.assertIn(("GET", "/x/y"), endpoint_data(arch))

    def test_O5_shadowed_factory_and_root_parameters_cannot_confirm_bootstrap(self):
        cases = [
            "async function start(NestFactory: any){const app=await NestFactory.create(Root);}",
            "async function start(Root: any){const app=await NestFactory.create(Root);}",
        ]
        for source in cases:
            with self.subTest(source=source):
                arch = self.project(CORE + source)
                self.assertIn(("GET", None), endpoint_data(arch))
                self.assertTrue(any(n.metadata["relative_path"] == "/x/y" for n in framework_nodes(arch, "endpoint")))

    def test_O5_inner_app_variable_cannot_set_outer_app_prefix(self):
        arch = self.project(CORE + "async function start(){const app=await NestFactory.create(Root); {const app=other; app.setGlobalPrefix('wrong');}}")
        self.assertIn(("GET", "/x/y"), endpoint_data(arch))


class TestPinnedFixture(unittest.TestCase):
    def test_O10_source_authored_counts_edges_and_routes(self):
        expected = oracle()
        arch = analyze(fixture(), language=False)
        self.assertEqual({node_name(n) for n in framework_nodes(arch, "module")}, set(expected["modules"]))
        self.assertEqual({node_name(n) for n in framework_nodes(arch, "controller")}, set(expected["controllers"]))
        self.assertEqual(len(framework_nodes(arch, "endpoint")), 21)
        for relation, key in [("INCLUDES", "module_imports"), ("DECLARES", "registrations"), ("PROVIDES", "providers"), ("EXPORTS", "exports"), ("DEPENDS_ON", "di")]:
            observed = edge_names(arch, relation)
            if relation == "INCLUDES":
                observed = {pair for pair in observed if pair[0] in expected["modules"]}
            self.assertEqual(observed, set(map(tuple, expected[key])), relation)
        self.assertEqual(endpoint_data(arch), set(map(tuple, expected["routes"])))
        expressions = " ".join(str(d.get("expression", "")) for d in diagnostics(arch))
        for item in expected["unsupported"]:
            self.assertIn(item, expressions)
