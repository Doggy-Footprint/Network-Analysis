"""
Unit tests for FastAPI Visualizer static analysis, graph builder, and renderer.
"""

import ast
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from agent_view import RepositorySnapshot
from fixtures.registry import fixture_root
from framework_analyzers.fastapi.analyzer import FastAPIAnalyzer
import framework_analyzers.fastapi.graph as fastapi_graph
from framework_analyzers.fastapi.graph import ArchitectureGraphBuilder
from framework_analyzers.fastapi.models import EndpointInfo, ProjectArchitecture, SchemaFieldInfo, SchemaInfo
from language_analyzers.core.graph_models import Confidence, RelationKind, Resolution, SourceSpan
from renderers.html import HTMLRenderer


class TestFastAPIVisualizer(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.project_path = Path(self.test_dir)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def _create_sample_fastapi_app(self):
        models_dir = self.project_path / "app" / "models"
        models_dir.mkdir(parents=True, exist_ok=True)
        (models_dir / "__init__.py").write_text("")
        (models_dir / "user.py").write_text("""
from pydantic import BaseModel, EmailStr
from typing import Optional

class UserBase(BaseModel):
    email: EmailStr
    is_active: bool = True

class UserCreate(UserBase):
    password: str

class UserResponse(UserBase):
    id: int
""")

        core_dir = self.project_path / "app" / "core"
        core_dir.mkdir(parents=True, exist_ok=True)
        (core_dir / "__init__.py").write_text("")
        (core_dir / "deps.py").write_text("""
from typing import Annotated, Generator
from fastapi import Depends, HTTPException
from app.models.user import UserResponse

def get_db() -> Generator:
    db = {"session": True}
    try:
        yield db
    finally:
        pass

SessionDep = Annotated[dict, Depends(get_db)]

def get_current_user(session: SessionDep) -> UserResponse:
    return UserResponse(id=1, email="test@example.com")

CurrentUser = Annotated[UserResponse, Depends(get_current_user)]
""")

        routes_dir = self.project_path / "app" / "api" / "routes"
        routes_dir.mkdir(parents=True, exist_ok=True)
        (routes_dir / "__init__.py").write_text("")
        (routes_dir / "users.py").write_text("""
from fastapi import APIRouter, Depends, status
from app.models.user import UserCreate, UserResponse
from app.core.deps import CurrentUser, get_db

router = APIRouter(prefix="/users", tags=["users"])

@router.get("/me", response_model=UserResponse, summary="Get current user")
def read_user_me(current_user: CurrentUser):
    \"\"\"Return current authenticated user profile.\"\"\"
    return current_user

@router.post("/", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def create_user(user_in: UserCreate, db=Depends(get_db)):
    \"\"\"Register a new user.\"\"\"
    return UserResponse(id=2, email=user_in.email)
""")

        app_dir = self.project_path / "app"
        (app_dir / "main.py").write_text("""
from fastapi import FastAPI
from app.api.routes.users import router as users_router

app = FastAPI(title="Sample API", version="2.0.0")
app.include_router(users_router, prefix="/api/v1")
""")

    def test_analyzer_extraction(self):
        self._create_sample_fastapi_app()
        analyzer = FastAPIAnalyzer(str(self.project_path))
        arch = analyzer.analyze()

        self.assertEqual(len(arch.apps), 1)
        self.assertEqual(arch.apps[0].title, "Sample API")
        self.assertEqual(arch.apps[0].version, "2.0.0")

        self.assertGreaterEqual(len(arch.routers), 1)
        users_router = next((r for r in arch.routers if "users" in r.var_name or "router" in r.var_name), None)
        self.assertIsNotNone(users_router)

        self.assertEqual(len(arch.endpoints), 2)
        me_ep = next((ep for ep in arch.endpoints if "read_user_me" in ep.function_name), None)
        self.assertIsNotNone(me_ep)
        self.assertEqual(me_ep.http_method, "GET")
        self.assertEqual(me_ep.response_model, "UserResponse")
        self.assertEqual(me_ep.summary, "Get current user")
        self.assertIn("Return current authenticated user profile.", me_ep.docstring)
        self.assertEqual(me_ep.full_path, "/api/v1/users/me")

        schema_names = [s.name for s in arch.schemas]
        self.assertIn("UserCreate", schema_names)
        self.assertIn("UserResponse", schema_names)

        dep_names = [d.name for d in arch.dependencies]
        self.assertIn("get_db", dep_names)
        self.assertIn("get_current_user", dep_names)

    def test_C_2_snapshot_preserves_fastapi_analysis_language_graph_and_enrichment(self):
        source = (
            "from fastapi import FastAPI\n"
            "app = FastAPI(title='Captured API')\n"
            "@app.get('/captured')\n"
            "def captured_route():\n"
            "    return 'FEATURE_KEY'\n"
        )
        snapshot = RepositorySnapshot(
            str(self.project_path.resolve()),
            "agent_view.v3",
            (("main.py", source), (".env", "FEATURE_KEY=enabled\n")),
            (),
            "0" * 64,
        )
        (self.project_path / "main.py").write_text("raise RuntimeError('new filesystem state')\n", encoding="utf-8")

        with mock.patch.object(Path, "rglob", side_effect=AssertionError("repository traversal")), \
                mock.patch.object(Path, "read_text", side_effect=AssertionError("repository read")), \
                mock.patch.object(Path, "read_bytes", side_effect=AssertionError("repository read")), \
                mock.patch.object(os, "walk", side_effect=AssertionError("repository traversal")):
            framework = FastAPIAnalyzer(str(self.project_path.resolve()), snapshot=snapshot).analyze()
            architecture = ArchitectureGraphBuilder(snapshot=snapshot).build_graph(framework)

        self.assertEqual([endpoint.function_name for endpoint in framework.endpoints], ["captured_route"])
        self.assertTrue(any(node.label == "captured_route" for node in architecture.nodes))
        self.assertTrue(any(node.provenance == "python-core" for node in architecture.nodes))
        self.assertTrue(all(node.cost is not None for node in architecture.nodes))
        nodes = {node.id: node for node in architecture.nodes}
        config_edges = [edge for edge in architecture.edges if edge.relation == RelationKind.CONFIGURES]
        self.assertTrue(config_edges)
        self.assertTrue(any(nodes[edge.to_id].label == "captured_route" for edge in config_edges))

    def test_C_3_fastapi_snapshot_root_must_match_an_absolute_project_path(self):
        (self.project_path / "main.py").write_text("from fastapi import FastAPI\napp = FastAPI()\n", encoding="utf-8")
        snapshot = RepositorySnapshot(
            str(self.project_path.resolve()), "agent_view.v3", (("main.py", "from fastapi import FastAPI\n"),), (), "0" * 64,
        )

        with self.assertRaises(ValueError):
            FastAPIAnalyzer(str(self.project_path.parent.resolve()), snapshot=snapshot).analyze()
        with self.assertRaises(ValueError):
            FastAPIAnalyzer("relative-project", snapshot=snapshot).analyze()
        framework = FastAPIAnalyzer(str(self.project_path.resolve())).analyze()
        different_root = RepositorySnapshot(
            str(self.project_path.parent.resolve()), "agent_view.v3", (), (), "0" * 64,
        )
        with self.assertRaises(ValueError):
            ArchitectureGraphBuilder(snapshot=different_root).build_graph(framework)

    def test_C_4_fastapi_without_snapshot_discovers_the_current_filesystem(self):
        (self.project_path / "main.py").write_text(
            "from fastapi import FastAPI\napp = FastAPI()\n@app.get('/')\ndef filesystem_route():\n    return 1\n",
            encoding="utf-8",
        )

        architecture = FastAPIAnalyzer(str(self.project_path.resolve())).analyze()

        self.assertEqual([endpoint.function_name for endpoint in architecture.endpoints], ["filesystem_route"])

    def test_graph_building_and_rendering(self):
        self._create_sample_fastapi_app()
        analyzer = FastAPIAnalyzer(str(self.project_path))
        arch = analyzer.analyze()

        builder = ArchitectureGraphBuilder(include_models=True, include_dependencies=True)
        arch = builder.build_graph(arch)

        self.assertGreater(len(arch.nodes), 0)
        self.assertGreater(len(arch.edges), 0)

        self.assertEqual(arch.stats["total_endpoints"], 2)
        self.assertEqual(arch.stats["methods_breakdown"]["GET"], 1)
        self.assertEqual(arch.stats["methods_breakdown"]["POST"], 1)
        self.assertIn("analysis", arch.stats)
        self.assertEqual(len(arch.stats["analysis"]["node_metrics"]), len(arch.nodes))
        self.assertTrue(all("analysis" in node.metadata for node in arch.nodes))

        out_html = self.project_path / "output.html"
        renderer = HTMLRenderer(title="Test Visualizer")
        rendered_file = renderer.render(arch, str(out_html))

        self.assertTrue(rendered_file.exists())
        content = rendered_file.read_text(encoding="utf-8")
        self.assertIn("Sample API", content)
        self.assertIn("/api/v1/users/me", content)
        self.assertIn("UserResponse", content)
        self.assertIn("vis-network", content)
        asset_dir = self.project_path / "output_assets"
        self.assertTrue((asset_dir / "styles.css").exists())
        self.assertTrue((asset_dir / "tailwind-config.js").exists())
        self.assertTrue((asset_dir / "app.js").exists())
        self.assertNotIn("<style>", content)

    def test_built_framework_edges_carry_their_declared_rule(self):
        self._create_sample_fastapi_app()
        arch = ArchitectureGraphBuilder().build_graph(FastAPIAnalyzer(str(self.project_path)).analyze())

        framework_edges = [
            edge for edge in arch.edges
            if str(edge.confidence) == "framework_inferred"
        ]
        undeclared = [
            edge.relation for edge in framework_edges
            if "framework_rule" not in (edge.metadata or {})
        ]
        implemented_by = [edge for edge in framework_edges if edge.relation == "IMPLEMENTED_BY"]

        self.assertGreater(len(framework_edges), 0)
        self.assertEqual(undeclared, [])
        self.assertGreater(len(implemented_by), 0)
        self.assertEqual(
            implemented_by[0].metadata["framework_rule"],
            {"id": "fastapi.implemented_by", "specificity": "unique"},
        )
        routes = [edge for edge in framework_edges if edge.relation == "ROUTES"]
        self.assertGreater(len(routes), 0)
        self.assertEqual(
            routes[0].metadata["framework_rule"],
            {"id": "fastapi.routes", "specificity": "unique"},
        )

    def test_every_framework_edge_carries_repository_relative_evidence(self):
        self._create_sample_fastapi_app()
        arch = ArchitectureGraphBuilder().build_graph(FastAPIAnalyzer(str(self.project_path)).analyze())

        framework_edges = [
            edge for edge in arch.edges
            if str(edge.confidence) == "framework_inferred"
        ]
        absolute = [
            edge.evidence.file_path for edge in framework_edges
            if edge.evidence is not None and Path(edge.evidence.file_path).is_absolute()
        ]

        self.assertGreater(len(framework_edges), 0)
        self.assertEqual(absolute, [])

    def test_mermaid_generation(self):
        self._create_sample_fastapi_app()
        analyzer = FastAPIAnalyzer(str(self.project_path))
        arch = analyzer.analyze()
        builder = ArchitectureGraphBuilder()
        arch = builder.build_graph(arch)

        mermaid = builder.generate_mermaid(arch)
        self.assertTrue(mermaid.startswith("graph TD"))
        self.assertIn("Sample API", mermaid)


    def test_node_labels_are_bare_identifiers_and_decoration_reaches_the_rendered_html(self):
        self._create_sample_fastapi_app()
        builder = ArchitectureGraphBuilder(include_models=True, include_dependencies=True)
        arch = builder.build_graph(FastAPIAnalyzer(str(self.project_path)).analyze())

        decorated = [
            node.label for node in arch.nodes
            if "\n" in node.label or any(ord(char) > 0x2000 for char in node.label)
        ]
        app_node = next(node for node in arch.nodes if node.category == "app")

        self.assertEqual(decorated, [])
        self.assertEqual(app_node.label, "app")
        self.assertIn("\U0001f680", app_node.display_label)

        out_html = self.project_path / "labels.html"
        HTMLRenderer().render(arch, str(out_html))
        content = out_html.read_text(encoding="utf-8")

        self.assertIn("\U0001f680", content)


class FastAPIFrameworkRuleDeclarationTests(unittest.TestCase):
    def test_every_emitted_framework_relation_declares_a_rule(self):
        source = Path(fastapi_graph.__file__).read_text(encoding="utf-8")
        emitted = {
            keyword.value.value
            for node in ast.walk(ast.parse(source))
            if isinstance(node, ast.Call)
            for keyword in node.keywords
            if keyword.arg == "relation"
            and isinstance(keyword.value, ast.Constant)
            and isinstance(keyword.value.value, str)
        }

        undeclared = emitted - set(ArchitectureGraphBuilder.FRAMEWORK_RULE_SPECIFICITY)

        self.assertEqual(undeclared, set())

    def test_declared_specificities_are_within_the_contract(self):
        self.assertEqual(
            set(ArchitectureGraphBuilder.FRAMEWORK_RULE_SPECIFICITY.values()) - {"unique", "narrowing"},
            set(),
        )


class FastAPISchemaFieldTypeUsesTests(unittest.TestCase):
    def _build(self, schemas):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "api.py").write_text("x = 1\n", encoding="utf-8")
            architecture = ProjectArchitecture(
                project_name="sample",
                project_path=str(root),
                schemas=schemas,
            )
            return ArchitectureGraphBuilder(include_language_graph=False).build_graph(architecture)

    def test_fa_1_field_typed_as_another_model_produces_type_uses_edge(self):
        owner = SchemaInfo(id="schema-owner", name="Owner", module="api",
                            file_path="owner.py", line_number=1, end_line_number=1)
        model = SchemaInfo(
            id="schema-model", name="Model", module="api",
            file_path="model.py", line_number=5, end_line_number=5,
            fields=[SchemaFieldInfo(name="owner", type_annotation="Owner")],
        )

        result = self._build([owner, model])

        edge = next(e for e in result.edges if e.relation == RelationKind.TYPE_USES)
        self.assertEqual((edge.from_id, edge.to_id), ("schema-model", "schema-owner"))
        self.assertEqual(str(edge.confidence), str(Confidence.STATIC_CERTAIN))
        self.assertEqual(str(edge.resolution), str(Resolution.UNIQUE_NAME))
        self.assertEqual(edge.evidence, SourceSpan("model.py", 5, 5))
        self.assertEqual(
            edge.metadata["framework_rule"],
            {"id": "fastapi.model_field_type_uses", "specificity": "unique"},
        )

    def test_fa_2_wrapped_field_types_are_stripped_before_matching(self):
        owner = SchemaInfo(id="schema-owner", name="Owner", module="api",
                            file_path="owner.py", line_number=1, end_line_number=1)
        model = SchemaInfo(
            id="schema-model", name="Model", module="api",
            file_path="model.py", line_number=5, end_line_number=5,
            fields=[
                SchemaFieldInfo(name="owner", type_annotation="Optional[Owner]"),
                SchemaFieldInfo(name="owners", type_annotation="List[Owner]"),
            ],
        )

        result = self._build([owner, model])

        edges = [e for e in result.edges if e.relation == RelationKind.TYPE_USES]
        self.assertEqual(len(edges), 2)
        self.assertTrue(all(e.to_id == "schema-owner" for e in edges))

    def test_fa_3_primitive_field_type_produces_no_type_uses_edge(self):
        model = SchemaInfo(
            id="schema-model", name="Model", module="api",
            file_path="model.py", line_number=5, end_line_number=5,
            fields=[SchemaFieldInfo(name="name", type_annotation="str")],
        )

        result = self._build([model])

        self.assertFalse(any(e.relation == RelationKind.TYPE_USES for e in result.edges))

    def test_fa_4_two_models_sharing_a_class_name_produce_ambiguous_type_uses(self):
        owner_a = SchemaInfo(id="schema-owner-a", name="Owner", module="api.v1",
                              file_path="a.py", line_number=1, end_line_number=1)
        owner_b = SchemaInfo(id="schema-owner-b", name="Owner", module="api.v2",
                              file_path="b.py", line_number=1, end_line_number=1)
        model = SchemaInfo(
            id="schema-model", name="Model", module="api",
            file_path="model.py", line_number=5, end_line_number=5,
            fields=[SchemaFieldInfo(name="owner", type_annotation="Owner")],
        )

        result = self._build([owner_a, owner_b, model])

        edge = next(e for e in result.edges if e.relation == RelationKind.TYPE_USES)
        self.assertEqual(str(edge.resolution), str(Resolution.AMBIGUOUS))
        self.assertEqual(set(edge.candidates) | {edge.to_id}, {"schema-owner-a", "schema-owner-b"})


class FastAPIRealFixtureSmokeTests(unittest.TestCase):
    """Acceptance-level coverage against real, network-fetched FastAPI apps
    (fixtures.registry), in addition to (not replacing) TestFastAPIVisualizer's
    precise synthetic-app assertions above.

    Expected values below were hand-derived by reading the fixture sources at
    their pinned commits (see fixtures/registry.py), not by reading the
    analyzer's own output.
    """

    def _assert_pipeline_smoke(self, project_path):
        analyzer = FastAPIAnalyzer(str(project_path))
        arch = analyzer.analyze()

        builder = ArchitectureGraphBuilder(include_models=True, include_dependencies=True)
        arch = builder.build_graph(arch)
        self.assertGreater(len(arch.nodes), 0)
        self.assertGreater(len(arch.edges), 0)

        framework_edges = [edge for edge in arch.edges if str(edge.confidence) == "framework_inferred"]
        self.assertGreater(len(framework_edges), 0)
        undeclared = [edge.relation for edge in framework_edges if "framework_rule" not in (edge.metadata or {})]
        self.assertEqual(undeclared, [])
        absolute_evidence = [
            edge.evidence.file_path for edge in framework_edges
            if edge.evidence is not None and Path(edge.evidence.file_path).is_absolute()
        ]
        self.assertEqual(absolute_evidence, [])

        with tempfile.TemporaryDirectory() as directory:
            out_html = Path(directory) / "output.html"
            rendered_file = HTMLRenderer(title="Fixture Smoke Test").render(arch, str(out_html))
            self.assertTrue(rendered_file.exists())

    def test_fastapi_realworld_fixture_analyzes_without_crashing(self):
        root = fixture_root("fastapi-realworld")
        project_path = root / "app"
        analyzer = FastAPIAnalyzer(str(project_path))
        arch = analyzer.analyze()

        self.assertEqual(len(arch.apps), 1)
        self.assertEqual(arch.apps[0].title, "FastAPI App")
        self.assertEqual(arch.apps[0].version, "0.1.0")
        self.assertEqual(arch.apps[0].title_source, "unresolved")
        self.assertEqual(arch.apps[0].title_expr, "get_application()")
        self.assertEqual(arch.apps[0].version_source, "unresolved")
        self.assertEqual(arch.apps[0].version_expr, "get_application()")

        # app/api/routes/api.py wires: authentication(+/users), users(+/user),
        # profiles(+/profiles), articles(articles_common: 3 + articles_resource: 5),
        # comments(+3), tags(+1) = 2+2+3+3+5+3+1 = 19, hand-counted from the
        # @router.<method> decorators across every routes/*.py file.
        self.assertEqual(len(arch.endpoints), 19)
        self.assertEqual(
            {ep.http_method for ep in arch.endpoints if ep.http_method not in ("GET", "POST", "PUT", "DELETE")},
            set(),
        )

        login_ep = next(ep for ep in arch.endpoints if ep.function_name == "login")
        self.assertEqual(login_ep.http_method, "POST")
        self.assertEqual(login_ep.response_model, "UserInResponse")
        self.assertIn("UserInLogin", login_ep.request_schemas)
        self.assertEqual(login_ep.full_path, "/users/login")

        favorite_ep = next(ep for ep in arch.endpoints if ep.function_name == "mark_article_as_favorite")
        self.assertEqual(favorite_ep.http_method, "POST")
        self.assertEqual(favorite_ep.response_model, "ArticleInResponse")
        self.assertEqual(favorite_ep.full_path, "/articles/{slug}/favorite")

        schema_names = [s.name for s in arch.schemas]
        # 19 classes under app/models/schemas/ (any class there counts, per
        # in_model_file) + Article, Comment, Profile, RWModel, User, UserInDB
        # under app/models/domain/ + DateTimeModelMixin, IDModelMixin in
        # app/models/common.py = 19 + 6 + 2 = 27.
        self.assertEqual(len(schema_names), 27)
        self.assertIn("UserInResponse", schema_names)
        self.assertIn("UserWithToken", schema_names)

        dep_names = [d.name for d in arch.dependencies]
        self.assertIn("get_current_user_authorizer", dep_names)
        self.assertIn("get_repository", dep_names)

        builder = ArchitectureGraphBuilder(include_models=True, include_dependencies=True)
        built = builder.build_graph(arch)
        self.assertEqual(built.stats["total_endpoints"], 19)
        self.assertEqual(
            built.stats["methods_breakdown"],
            {"GET": 7, "POST": 6, "PUT": 2, "DELETE": 4},
        )

        # app/models/schemas/users.py: UserInResponse.user is typed UserWithToken,
        # a class name unique across the whole fixture, so the field-type-uses
        # rule must resolve it as a STATIC_CERTAIN/UNIQUE_NAME edge.
        node_by_id = {node.id: node for node in built.nodes}
        type_uses_pairs = {
            (node_by_id[edge.from_id].label, node_by_id[edge.to_id].label)
            for edge in built.edges
            if str(edge.relation) == "TYPE_USES"
            and edge.from_id in node_by_id and edge.to_id in node_by_id
        }
        self.assertIn(("UserInResponse", "UserWithToken"), type_uses_pairs)

        self._assert_pipeline_smoke(project_path)

    def test_fastapi_official_template_fixture_analyzes_without_crashing(self):
        root = fixture_root("fastapi-official-template")
        project_path = root / "backend" / "app"
        analyzer = FastAPIAnalyzer(str(project_path))
        arch = analyzer.analyze()

        self.assertEqual(len(arch.apps), 1)
        self.assertEqual(arch.apps[0].title, "FastAPI App")
        self.assertEqual(arch.apps[0].version, "0.1.0")
        self.assertEqual(arch.apps[0].title_source, "unresolved")
        self.assertEqual(arch.apps[0].title_expr, "settings.PROJECT_NAME")
        self.assertEqual(arch.apps[0].version_source, "default")
        self.assertIsNone(arch.apps[0].version_expr)

        # utils.py(2) + items.py(5) + users.py(10) + login.py(5) + private.py(1)
        # = 23, hand-counted from @router.<method> decorators.
        self.assertEqual(len(arch.endpoints), 23)

        read_user_me = next(ep for ep in arch.endpoints if ep.function_name == "read_user_me")
        self.assertEqual(read_user_me.http_method, "GET")
        self.assertEqual(read_user_me.response_model, "UserPublic")
        self.assertEqual(read_user_me.full_path, "/users/me")

        delete_user = next(ep for ep in arch.endpoints if ep.function_name == "delete_user")
        self.assertEqual(delete_user.http_method, "DELETE")
        self.assertIsNone(delete_user.response_model)
        self.assertEqual(delete_user.full_path, "/users/{user_id}")

        schema_names = {s.name for s in arch.schemas}
        # Every class in models.py directly subclassing SQLModel (is_schema's
        # "Model" substring check), plus PrivateUserCreate(BaseModel) in
        # api/routes/private.py. Classes that subclass a *sibling* base class
        # (UserBase, ItemBase -- e.g. UserPublic, User, ItemPublic, Item,
        # UserCreate, ItemCreate) do NOT match, since is_schema only inspects
        # each class's own direct base names and models.py isn't inside a
        # models/schemas/entities *directory*.
        self.assertEqual(
            schema_names,
            {
                "UserBase", "UserRegister", "UserUpdate", "UserUpdateMe", "UpdatePassword",
                "UsersPublic", "ItemBase", "ItemUpdate", "ItemsPublic", "Message", "Token",
                "TokenPayload", "NewPassword", "PrivateUserCreate",
            },
        )
        self.assertNotIn("UserPublic", schema_names)
        self.assertNotIn("Item", schema_names)

        builder = ArchitectureGraphBuilder(include_models=True, include_dependencies=True)
        built = builder.build_graph(arch)
        self.assertEqual(built.stats["total_endpoints"], 23)
        self.assertEqual(
            built.stats["methods_breakdown"],
            {"GET": 6, "POST": 10, "PATCH": 3, "DELETE": 3, "PUT": 1},
        )

        # UsersPublic.data/ItemsPublic.data are typed list[UserPublic]/list[ItemPublic],
        # but UserPublic/ItemPublic aren't registered schemas (see above), so the
        # FastAPI-specific field-type-uses rule (metadata id
        # "fastapi.model_field_type_uses") never fires for this fixture -- unlike
        # the generic Python-source-level TYPE_USES edges from include_language_graph,
        # which resolve class attribute annotations independently of schema registration.
        schema_type_uses = [
            edge for edge in built.edges
            if str(edge.relation) == "TYPE_USES"
            and (edge.metadata or {}).get("framework_rule", {}).get("id") == "fastapi.model_field_type_uses"
        ]
        self.assertEqual(schema_type_uses, [])

        self._assert_pipeline_smoke(project_path)


class FastAPIRouterPrefixResolutionTests(unittest.TestCase):
    def _write(self, root: Path, relative: str, source: str):
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(source, encoding="utf-8")

    def _build_project(self, root: Path, package: str):
        self._write(root, f"{package}/__init__.py", "")
        self._write(root, f"{package}/api/__init__.py", "")
        self._write(root, f"{package}/api/routes/__init__.py", "")
        self._write(root, f"{package}/api/routes/authentication.py", """
from fastapi import APIRouter

router = APIRouter()


@router.post("/login")
def login():
    return {}
""")
        self._write(root, f"{package}/api/routes/api.py", """
from fastapi import APIRouter

from app.api.routes import authentication

router = APIRouter()
router.include_router(authentication.router, prefix="/users")
""")

    def test_rp_1_absolute_app_rooted_import_resolves_to_stripped_module_key(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "app"
            root.mkdir()
            self._build_project(root, ".")
            analyzer = FastAPIAnalyzer(str(root))
            arch = analyzer.analyze()
            resolved = analyzer._resolve_target_router_module(
                "authentication.router", analyzer.file_asts["api.routes.api"]
            )

        self.assertEqual(resolved, "api.routes.authentication")
        login = next(ep for ep in arch.endpoints if ep.function_name == "login")
        self.assertEqual(login.full_path, "/users/login")

    def test_rp_2_module_keys_carrying_app_prefix_are_not_stripped(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "project"
            root.mkdir()
            self._build_project(root, "app")
            analyzer = FastAPIAnalyzer(str(root))
            arch = analyzer.analyze()
            resolved = analyzer._resolve_target_router_module(
                "authentication.router", analyzer.file_asts["app.api.routes.api"]
            )

        self.assertEqual(resolved, "app.api.routes.authentication")
        login = next(ep for ep in arch.endpoints if ep.function_name == "login")
        self.assertEqual(login.full_path, "/users/login")

    def test_rp_3_unknown_module_falls_back_to_imported_module_string(self):
        """@characterization: pins the pre-existing legacy fallback to the module part only."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "app"
            root.mkdir()
            self._write(root, "api.py", """
from fastapi import APIRouter

from vendor.pkg import elsewhere

router = APIRouter()
router.include_router(elsewhere.router, prefix="/users")
""")
            analyzer = FastAPIAnalyzer(str(root))
            analyzer.analyze()
            resolved = analyzer._resolve_target_router_module(
                "elsewhere.router", analyzer.file_asts["api"]
            )

        self.assertEqual(resolved, "vendor.pkg")

    def test_rp_4_plain_import_is_normalized_against_module_keys(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "app"
            root.mkdir()
            self._write(root, "__init__.py", "")
            self._write(root, "api/__init__.py", "")
            self._write(root, "api/routes/__init__.py", "")
            self._write(root, "api/routes/users.py", """
from fastapi import APIRouter

router = APIRouter()


@router.get("/me")
def read_user_me():
    return {}
""")
            self._write(root, "api/main.py", """
from fastapi import APIRouter

import app.api.routes.users as users_module

router = APIRouter()
router.include_router(users_module.router, prefix="/users")
""")
            analyzer = FastAPIAnalyzer(str(root))
            arch = analyzer.analyze()
            resolved = analyzer._resolve_target_router_module(
                "users_module.router", analyzer.file_asts["api.main"]
            )

        self.assertEqual(resolved, "api.routes.users")
        me = next(ep for ep in arch.endpoints if ep.function_name == "read_user_me")
        self.assertEqual(me.full_path, "/users/me")


    def test_rp_5_stripped_segment_follows_the_actual_root_basename(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "svc"
            root.mkdir()
            self._write(root, "__init__.py", "")
            self._write(root, "api/__init__.py", "")
            self._write(root, "api/routes/__init__.py", "")
            self._write(root, "api/routes/authentication.py", """
from fastapi import APIRouter

router = APIRouter()


@router.post("/login")
def login():
    return {}
""")
            self._write(root, "api/routes/api.py", """
from fastapi import APIRouter

from svc.api.routes import authentication

router = APIRouter()
router.include_router(authentication.router, prefix="/users")
""")
            analyzer = FastAPIAnalyzer(str(root))
            arch = analyzer.analyze()
            resolved = analyzer._resolve_target_router_module(
                "authentication.router", analyzer.file_asts["api.routes.api"]
            )

        self.assertEqual(resolved, "api.routes.authentication")
        login = next(ep for ep in arch.endpoints if ep.function_name == "login")
        self.assertEqual(login.full_path, "/users/login")

    def test_rp_6_exact_key_match_wins_over_the_stripped_candidate(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "app"
            root.mkdir()
            self._write(root, "__init__.py", "")
            self._write(root, "api/__init__.py", "")
            self._write(root, "api/routes/__init__.py", "")
            self._write(root, "api/routes/authentication.py", """
from fastapi import APIRouter

router = APIRouter()


@router.post("/login")
def login_stripped():
    return {}
""")
            self._write(root, "app/__init__.py", "")
            self._write(root, "app/api/__init__.py", "")
            self._write(root, "app/api/routes/__init__.py", "")
            self._write(root, "app/api/routes/authentication.py", """
from fastapi import APIRouter

router = APIRouter()


@router.post("/login")
def login_raw():
    return {}
""")
            self._write(root, "api/routes/api.py", """
from fastapi import APIRouter

from app.api.routes import authentication

router = APIRouter()
router.include_router(authentication.router, prefix="/users")
""")
            analyzer = FastAPIAnalyzer(str(root))
            arch = analyzer.analyze()
            resolved = analyzer._resolve_target_router_module(
                "authentication.router", analyzer.file_asts["api.routes.api"]
            )

        self.assertEqual(resolved, "app.api.routes.authentication")
        raw_ep = next(ep for ep in arch.endpoints if ep.function_name == "login_raw")
        stripped_ep = next(ep for ep in arch.endpoints if ep.function_name == "login_stripped")
        self.assertEqual(raw_ep.full_path, "/users/login")
        self.assertEqual(stripped_ep.full_path, "/login")


class FastAPIAppTitleVersionSourceTests(unittest.TestCase):
    def _analyze_main(self, source: str):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "main.py").write_text(source, encoding="utf-8")
            arch = FastAPIAnalyzer(str(root)).analyze()
        return arch.apps[0]

    def test_tv_1_literal_title_and_version(self):
        app = self._analyze_main("""
from fastapi import FastAPI

app = FastAPI(title="X", version="1.0")
""")
        self.assertEqual(app.title, "X")
        self.assertEqual(app.title_source, "literal")
        self.assertIsNone(app.title_expr)
        self.assertEqual(app.version, "1.0")
        self.assertEqual(app.version_source, "literal")
        self.assertIsNone(app.version_expr)

    def test_tv_2_no_relevant_keyword_keeps_defaults(self):
        app = self._analyze_main("""
from fastapi import FastAPI

app = FastAPI(openapi_url="/o.json")
""")
        self.assertEqual(app.title, "FastAPI App")
        self.assertEqual(app.title_source, "default")
        self.assertIsNone(app.title_expr)
        self.assertEqual(app.version, "0.1.0")
        self.assertEqual(app.version_source, "default")
        self.assertIsNone(app.version_expr)

    def test_tv_3_non_literal_title_is_unresolved_with_expression(self):
        app = self._analyze_main("""
from fastapi import FastAPI

from app.core.config import settings

app = FastAPI(title=settings.PROJECT_NAME)
""")
        self.assertEqual(app.title, "FastAPI App")
        self.assertEqual(app.title_source, "unresolved")
        self.assertEqual(app.title_expr, "settings.PROJECT_NAME")
        self.assertEqual(app.version_source, "default")
        self.assertIsNone(app.version_expr)

    def test_tv_4_kwargs_expansion_marks_both_fields_unresolved(self):
        app = self._analyze_main("""
from fastapi import FastAPI

from app.core.config import settings

app = FastAPI(**settings.fastapi_kwargs)
""")
        self.assertEqual(app.title, "FastAPI App")
        self.assertEqual(app.version, "0.1.0")
        self.assertEqual(app.title_source, "unresolved")
        self.assertEqual(app.version_source, "unresolved")
        self.assertEqual(app.title_expr, "**settings.fastapi_kwargs")
        self.assertEqual(app.version_expr, "**settings.fastapi_kwargs")

    def test_tv_5_factory_call_marks_both_fields_unresolved(self):
        app = self._analyze_main("""
from app.main import get_application

app = get_application()
""")
        self.assertEqual(app.title, "FastAPI App")
        self.assertEqual(app.version, "0.1.0")
        self.assertEqual(app.title_source, "unresolved")
        self.assertEqual(app.version_source, "unresolved")
        self.assertEqual(app.title_expr, "get_application()")
        self.assertEqual(app.version_expr, "get_application()")

    def test_tv_6_explicit_literal_wins_over_kwargs_expansion(self):
        app = self._analyze_main("""
from fastapi import FastAPI

from app.core.config import kw

app = FastAPI(title="X", **kw)
""")
        self.assertEqual(app.title, "X")
        self.assertEqual(app.title_source, "literal")
        self.assertIsNone(app.title_expr)
        self.assertEqual(app.version, "0.1.0")
        self.assertEqual(app.version_source, "unresolved")
        self.assertEqual(app.version_expr, "**kw")


    def test_tv_7_non_literal_version_is_unresolved_with_expression(self):
        app = self._analyze_main("""
from fastapi import FastAPI

from app.core.config import settings

app = FastAPI(version=settings.VERSION)
""")
        self.assertEqual(app.version, "0.1.0")
        self.assertEqual(app.version_source, "unresolved")
        self.assertEqual(app.version_expr, "settings.VERSION")
        self.assertEqual(app.title, "FastAPI App")
        self.assertEqual(app.title_source, "default")
        self.assertIsNone(app.title_expr)


class FastAPINameCollisionTests(unittest.TestCase):
    def test_two_schemas_sharing_a_name_are_recorded_as_candidates(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "api.py").write_text("x = 1\n", encoding="utf-8")
            architecture = ProjectArchitecture(
                project_name="sample",
                project_path=str(root),
                endpoints=[EndpointInfo(
                    id="endpoint", http_method="POST", path="/users", function_name="create",
                    module="api", file_path=str(root / "api.py"), line_number=1, end_line_number=1,
                    request_schemas=["User"],
                )],
                schemas=[
                    SchemaInfo(id="schema-a", name="User", module="api.v1",
                               file_path=str(root / "api.py"), line_number=1, end_line_number=1),
                    SchemaInfo(id="schema-b", name="User", module="api.v2",
                               file_path=str(root / "api.py"), line_number=1, end_line_number=1),
                ],
            )

            result = ArchitectureGraphBuilder(include_language_graph=False).build_graph(architecture)

        body = next(edge for edge in result.edges if edge.relation == "REQUEST_BODY")
        self.assertEqual(body.to_id, "schema-a")
        self.assertEqual(body.candidates, ["schema-b"])
        self.assertEqual(str(body.resolution), str(Resolution.AMBIGUOUS))


if __name__ == "__main__":
    unittest.main()
