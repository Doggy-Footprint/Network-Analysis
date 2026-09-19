"""
Unit tests for the Android/Kotlin static analysis, graph builder, and renderer.
Requires tree-sitter + tree-sitter-language-pack; skips cleanly when unavailable
(the repo's main Python environment intentionally does not install them).
"""

import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from agent_view import RepositorySnapshot
from fixtures.registry import fixture_root

try:
    import tree_sitter_language_pack  # noqa: F401
    _HAS_TREE_SITTER = True
except ImportError:
    _HAS_TREE_SITTER = False

if _HAS_TREE_SITTER:
    from framework_analyzers.android.analyzer import AndroidAnalyzer
    from framework_analyzers.android.graph import AndroidArchitectureGraphBuilder
    from language_analyzers.kotlin import KotlinAnalyzer
    from renderers.html import HTMLRenderer


@unittest.skipUnless(_HAS_TREE_SITTER, "tree-sitter-language-pack not installed")
class TestAndroidVisualizer(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.project_path = Path(self.test_dir)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def _create_sample_android_app(self):
        feature_topic = self.project_path / "feature_topic" / "src" / "main" / "kotlin" / "com" / "example" / "feature" / "topic"
        feature_topic.mkdir(parents=True, exist_ok=True)
        (feature_topic / "TopicScreen.kt").write_text("""
package com.example.feature.topic

import androidx.compose.runtime.Composable
import androidx.hilt.navigation.compose.hiltViewModel

@Composable
fun TopicRoute(
    onBackClick: () -> Unit,
    viewModel: TopicViewModel = hiltViewModel(),
) {
    TopicScreen(onBackClick = onBackClick)
}

@Composable
fun TopicScreen(onBackClick: () -> Unit) {
    TopicDetail()
}

@Composable
fun TopicDetail() {
}
""")
        (feature_topic / "TopicViewModel.kt").write_text("""
package com.example.feature.topic

import androidx.lifecycle.ViewModel
import com.example.core.data.repository.TopicsRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import javax.inject.Inject

@HiltViewModel
class TopicViewModel @Inject constructor(
    private val topicsRepository: TopicsRepository,
) : ViewModel() {
    fun loadTopics() {
        topicsRepository.getTopics()
    }
}
""")
        (feature_topic / "SyncViewModel.kt").write_text("""
package com.example.feature.topic

import androidx.lifecycle.ViewModel
import com.example.core.network.RetrofitNiaNetworkApi
import dagger.hilt.android.lifecycle.HiltViewModel
import javax.inject.Inject

@HiltViewModel
class SyncViewModel @Inject constructor(
    private val networkApi: RetrofitNiaNetworkApi,
) : ViewModel() {
    fun sync() {
        networkApi.getTopics()
    }
}
""")

        core_data_repo = self.project_path / "core_data" / "src" / "main" / "kotlin" / "com" / "example" / "core" / "data" / "repository"
        core_data_repo.mkdir(parents=True, exist_ok=True)
        (core_data_repo / "TopicsRepository.kt").write_text("""
package com.example.core.data.repository

interface TopicsRepository {
    fun getTopics(): List<String>
}
""")
        (core_data_repo / "OfflineFirstTopicsRepository.kt").write_text("""
package com.example.core.data.repository

import com.example.core.database.dao.TopicDao
import com.example.core.network.RetrofitNiaNetworkApi
import javax.inject.Inject

class OfflineFirstTopicsRepository @Inject constructor(
    private val topicDao: TopicDao,
    private val network: RetrofitNiaNetworkApi,
) : TopicsRepository {
    override fun getTopics(): List<String> {
        return topicDao.getTopicEntities().map { it.name }
    }
}
""")

        core_data_di = self.project_path / "core_data" / "src" / "main" / "kotlin" / "com" / "example" / "core" / "data" / "di"
        core_data_di.mkdir(parents=True, exist_ok=True)
        (core_data_di / "DataModule.kt").write_text("""
package com.example.core.data.di

import com.example.core.data.repository.OfflineFirstTopicsRepository
import com.example.core.data.repository.TopicsRepository
import dagger.Binds
import dagger.Module
import dagger.hilt.InstallIn
import dagger.hilt.components.SingletonComponent

@Module
@InstallIn(SingletonComponent::class)
abstract class DataModule {
    @Binds
    abstract fun bindsTopicsRepository(impl: OfflineFirstTopicsRepository): TopicsRepository
}
""")
        (core_data_di / "NetworkModule.kt").write_text("""
package com.example.core.data.di

import com.example.core.network.RetrofitNiaNetworkApi
import dagger.Module
import dagger.Provides
import dagger.hilt.InstallIn
import dagger.hilt.components.SingletonComponent
import retrofit2.Retrofit

@Module
@InstallIn(SingletonComponent::class)
object NetworkModule {
    @Provides
    fun providesNetworkApi(retrofit: Retrofit): RetrofitNiaNetworkApi {
        return retrofit.create(RetrofitNiaNetworkApi::class.java)
    }
}
""")

        core_network = self.project_path / "core_network" / "src" / "main" / "kotlin" / "com" / "example" / "core" / "network"
        core_network.mkdir(parents=True, exist_ok=True)
        (core_network / "RetrofitNiaNetworkApi.kt").write_text("""
package com.example.core.network

import retrofit2.http.GET
import retrofit2.http.POST
import retrofit2.http.Body

interface RetrofitNiaNetworkApi {
    @GET("topics")
    suspend fun getTopics(): List<String>

    @POST("topics/sync")
    suspend fun syncTopics(@Body request: String): String
}
""")

        core_db_model = self.project_path / "core_database" / "src" / "main" / "kotlin" / "com" / "example" / "core" / "database" / "model"
        core_db_model.mkdir(parents=True, exist_ok=True)
        (core_db_model / "TopicEntity.kt").write_text("""
package com.example.core.database.model

import androidx.room.Entity
import androidx.room.PrimaryKey

@Entity(tableName = "topics")
data class TopicEntity(
    @PrimaryKey
    val id: String,
    val name: String,
)
""")

        core_db_dao = self.project_path / "core_database" / "src" / "main" / "kotlin" / "com" / "example" / "core" / "database" / "dao"
        core_db_dao.mkdir(parents=True, exist_ok=True)
        (core_db_dao / "TopicDao.kt").write_text("""
package com.example.core.database.dao

import androidx.room.Dao
import androidx.room.Delete
import androidx.room.Insert
import androidx.room.Query
import androidx.room.Update
import com.example.core.database.model.TopicEntity

@Dao
interface TopicDao {
    @Query("SELECT * FROM topics")
    fun getTopicEntities(): List<TopicEntity>

    @Insert
    suspend fun insertTopics(topics: List<TopicEntity>)

    @Update
    suspend fun updateTopics(topics: List<TopicEntity>)

    @Delete
    suspend fun deleteTopics(topics: List<TopicEntity>)
}
""")

        core_db = self.project_path / "core_database" / "src" / "main" / "kotlin" / "com" / "example" / "core" / "database"
        (core_db / "NiaDatabase.kt").write_text("""
package com.example.core.database

import androidx.room.Database
import androidx.room.RoomDatabase
import com.example.core.database.dao.TopicDao
import com.example.core.database.model.TopicEntity

@Database(
    entities = [TopicEntity::class],
    version = 1,
)
abstract class NiaDatabase : RoomDatabase() {
    abstract fun topicDao(): TopicDao
}
""")

        app_dir = self.project_path / "app" / "src" / "main" / "kotlin" / "com" / "example" / "app"
        app_dir.mkdir(parents=True, exist_ok=True)
        (app_dir / "MainActivity.kt").write_text("""
package com.example.app

import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import com.example.feature.topic.TopicRoute
import dagger.hilt.android.AndroidEntryPoint
import javax.inject.Inject

@AndroidEntryPoint
class MainActivity : ComponentActivity() {
    @Inject
    lateinit var analyticsHelper: AnalyticsHelper

    override fun onCreate() {
        setContent {
            TopicRoute(onBackClick = {})
        }
    }
}
""")

    def test_analyzer_extraction(self):
        self._create_sample_android_app()
        analyzer = AndroidAnalyzer(str(self.project_path))
        arch = analyzer.analyze()

        composable_names = {c.name for c in arch.composables}
        self.assertEqual(composable_names, {"TopicRoute", "TopicScreen", "TopicDetail"})
        topic_route = next(c for c in arch.composables if c.name == "TopicRoute")
        self.assertEqual(topic_route.uses_viewmodel, "TopicViewModel")
        self.assertIn("TopicScreen", topic_route.calls)
        topic_screen = next(c for c in arch.composables if c.name == "TopicScreen")
        self.assertIn("TopicDetail", topic_screen.calls)

        vm_names = {v.name for v in arch.viewmodels}
        self.assertEqual(vm_names, {"TopicViewModel", "SyncViewModel"})
        topic_vm = next(v for v in arch.viewmodels if v.name == "TopicViewModel")
        self.assertTrue(topic_vm.is_hilt)
        self.assertEqual(topic_vm.injected_types, ["TopicsRepository"])
        self.assertIn("getTopics", topic_vm.calls)
        sync_vm = next(v for v in arch.viewmodels if v.name == "SyncViewModel")
        self.assertEqual(sync_vm.injected_types, ["RetrofitNiaNetworkApi"])

        module_names = {m.name for m in arch.di_modules}
        self.assertEqual(module_names, {"DataModule", "NetworkModule"})
        for m in arch.di_modules:
            self.assertEqual(m.install_in, ["SingletonComponent"])

        binding_kinds = {(b.name, b.kind) for b in arch.di_bindings}
        self.assertIn(("bindsTopicsRepository", "binds"), binding_kinds)
        self.assertIn(("providesNetworkApi", "provides"), binding_kinds)
        self.assertIn(("OfflineFirstTopicsRepository", "inject_constructor"), binding_kinds)
        self.assertIn(("analyticsHelper", "inject_field"), binding_kinds)

        binds_binding = next(b for b in arch.di_bindings if b.name == "bindsTopicsRepository")
        self.assertEqual(binds_binding.provided_type, "TopicsRepository")
        inject_ctor_binding = next(b for b in arch.di_bindings if b.name == "OfflineFirstTopicsRepository")
        self.assertEqual(inject_ctor_binding.injected_type, "OfflineFirstTopicsRepository")
        inject_field_binding = next(b for b in arch.di_bindings if b.name == "analyticsHelper")
        self.assertEqual(inject_field_binding.injected_type, "AnalyticsHelper")

        self.assertEqual(len(arch.dagger_components), 1)
        component = arch.dagger_components[0]
        self.assertEqual(component.name, "SingletonComponent")
        self.assertTrue(component.synthesized)

        self.assertEqual(len(arch.room_entities), 1)
        entity = arch.room_entities[0]
        self.assertEqual(entity.name, "TopicEntity")
        field_by_name = {f.name: f for f in entity.fields}
        self.assertTrue(field_by_name["id"].is_primary_key)
        self.assertFalse(field_by_name["name"].is_primary_key)
        self.assertEqual(field_by_name["id"].type_annotation, "String")

        self.assertEqual(len(arch.room_daos), 1)
        dao = arch.room_daos[0]
        self.assertEqual(dao.name, "TopicDao")
        method_kinds = {m.name: m.kind for m in dao.methods}
        self.assertEqual(
            method_kinds,
            {
                "getTopicEntities": "query",
                "insertTopics": "insert",
                "updateTopics": "update",
                "deleteTopics": "delete",
            },
        )
        query_method = next(m for m in dao.methods if m.name == "getTopicEntities")
        self.assertEqual(query_method.query_text, "SELECT * FROM topics")
        self.assertEqual(query_method.return_type, "TopicEntity")

        self.assertEqual(len(arch.room_databases), 1)
        database = arch.room_databases[0]
        self.assertEqual(database.name, "NiaDatabase")
        self.assertEqual(database.entity_names, ["TopicEntity"])
        self.assertEqual(database.dao_accessors, ["TopicDao"])

        self.assertEqual(len(arch.retrofit_apis), 1)
        api = arch.retrofit_apis[0]
        self.assertEqual(api.name, "RetrofitNiaNetworkApi")
        endpoint_by_name = {e.name: e for e in api.endpoints}
        self.assertEqual(endpoint_by_name["getTopics"].http_method, "GET")
        self.assertEqual(endpoint_by_name["getTopics"].path, "topics")
        self.assertEqual(endpoint_by_name["syncTopics"].http_method, "POST")
        self.assertEqual(endpoint_by_name["syncTopics"].path, "topics/sync")

        self.assertEqual(len(arch.activities_fragments), 1)
        activity = arch.activities_fragments[0]
        self.assertEqual(activity.name, "MainActivity")
        self.assertEqual(activity.kind, "activity")
        self.assertTrue(activity.is_hilt_entry_point)
        self.assertIn("TopicRoute", activity.hosted_composables)

    def test_C_2_snapshot_preserves_android_and_kotlin_graph_after_source_is_deleted(self):
        source = (
            "import androidx.compose.runtime.Composable\n"
            "@Composable\n"
            "fun CapturedScreen() { val key = \"ANDROID_KEY\" }\n"
        )
        snapshot = RepositorySnapshot(
            str(self.project_path.resolve()),
            "agent_view.v3",
            (("CapturedScreen.kt", source), (".env", "ANDROID_KEY=value\n")),
            (),
            "0" * 64,
        )
        (self.project_path / "CapturedScreen.kt").write_text("class Changed\n", encoding="utf-8")

        with mock.patch.object(Path, "rglob", side_effect=AssertionError("repository traversal")), \
                mock.patch.object(Path, "read_text", side_effect=AssertionError("repository read")), \
                mock.patch.object(Path, "read_bytes", side_effect=AssertionError("repository read")), \
                mock.patch.object(os, "walk", side_effect=AssertionError("repository traversal")):
            framework = AndroidAnalyzer(self.project_path.resolve(), snapshot=snapshot).analyze()
            architecture = AndroidArchitectureGraphBuilder(snapshot=snapshot).build_graph(framework)

        self.assertEqual([item.name for item in framework.composables], ["CapturedScreen"])
        self.assertTrue(any(node.provenance == "kotlin-core" for node in architecture.nodes))
        self.assertTrue(all(node.cost is not None for node in architecture.nodes))
        self.assertTrue(any(edge.relation == "CONFIGURES" for edge in architecture.edges))

    def test_graph_building_and_rendering(self):
        self._create_sample_android_app()
        analyzer = AndroidAnalyzer(str(self.project_path))
        arch = analyzer.analyze()

        builder = AndroidArchitectureGraphBuilder(include_models=True, include_dependencies=True)
        arch = builder.build_graph(arch)

        node_ids = {n.id for n in arch.nodes}
        self.assertGreater(len(arch.nodes), 0)
        self.assertGreater(len(arch.edges), 0)
        for edge in arch.edges:
            self.assertIn(edge.from_id, node_ids)
            self.assertIn(edge.to_id, node_ids)

        relation_names = {e.relation for e in arch.edges}
        self.assertTrue({"CALLS", "USES_VIEWMODEL", "BINDS", "PROVIDES", "INSTALLS_IN", "INJECTS",
                         "CALLS_API", "ROUTES", "QUERIES", "CONTAINS", "DEFINES_ENTITY", "HOSTS",
                         "IMPLEMENTED_BY"}.issubset(relation_names))
        self.assertTrue(any(node.provenance == "kotlin-core" for node in arch.nodes))

        def find_edge(relation, from_fragment, to_fragment):
            return next(
                (e for e in arch.edges
                 if e.relation == relation and from_fragment in e.from_id and to_fragment in e.to_id),
                None,
            )

        self.assertIsNotNone(find_edge("USES_VIEWMODEL", "_TopicRoute", "_TopicViewModel"))
        self.assertIsNotNone(find_edge("CALLS", "_TopicRoute", "_TopicScreen"))
        self.assertIsNotNone(find_edge("CALLS", "_TopicScreen", "_TopicDetail"))
        self.assertIsNotNone(find_edge("INJECTS", "_TopicViewModel", "_bindsTopicsRepository"))
        self.assertIsNotNone(find_edge("INJECTS", "_SyncViewModel", "_providesNetworkApi"))
        self.assertIsNotNone(find_edge("CALLS_API", "_SyncViewModel", "_RetrofitNiaNetworkApi"))
        self.assertIsNotNone(find_edge("BINDS", "_DataModule", "_bindsTopicsRepository"))
        self.assertIsNotNone(find_edge("PROVIDES", "_NetworkModule", "_providesNetworkApi"))
        installs_in_edges = [e for e in arch.edges if e.relation == "INSTALLS_IN"]
        self.assertEqual(len(installs_in_edges), 2)
        for e in installs_in_edges:
            self.assertTrue(e.to_id.startswith("component_synth_"))
        self.assertIsNotNone(find_edge("CONTAINS", "_NiaDatabase", "_TopicDao"))
        self.assertIsNotNone(find_edge("DEFINES_ENTITY", "_NiaDatabase", "_TopicEntity"))
        self.assertIsNotNone(find_edge("HOSTS", "_MainActivity", "_TopicRoute"))
        queries_edges = [e for e in arch.edges if e.relation == "QUERIES"]
        self.assertEqual(len(queries_edges), 1)
        self.assertTrue(queries_edges[0].to_id.endswith("_TopicEntity"))

        self.assertEqual(arch.stats["total_composables"], 3)
        self.assertEqual(arch.stats["total_viewmodels"], 2)
        self.assertEqual(arch.stats["total_room_entities"], 1)
        self.assertEqual(arch.stats["total_retrofit_apis"], 1)
        self.assertIn("analysis", arch.stats)
        self.assertEqual(len(arch.stats["analysis"]["node_metrics"]), len(arch.nodes))
        self.assertTrue(all("analysis" in node.metadata for node in arch.nodes))

        collection_keys = {c.key for c in arch.report_collections}
        self.assertEqual(collection_keys, {"composables", "viewmodels", "di_bindings", "room_entities", "retrofit_apis"})
        composables_collection = next(c for c in arch.report_collections if c.key == "composables")
        self.assertEqual(len(composables_collection.rows), 3)

        out_html = self.project_path / "output.html"
        renderer = HTMLRenderer(title="Android Test", framework_label="Android")
        rendered_file = renderer.render(arch, str(out_html))

        self.assertTrue(rendered_file.exists())
        content = rendered_file.read_text(encoding="utf-8")
        self.assertIn("TopicViewModel", content)
        self.assertIn("vis-network", content)
        asset_dir = self.project_path / "output_assets"
        self.assertTrue((asset_dir / "styles.css").exists())
        self.assertTrue((asset_dir / "app.js").exists())

    def test_graph_builder_exclude_flags(self):
        self._create_sample_android_app()
        analyzer = AndroidAnalyzer(str(self.project_path))
        arch = analyzer.analyze()

        no_models_builder = AndroidArchitectureGraphBuilder(include_models=False, include_dependencies=True)
        no_models_arch = no_models_builder.build_graph(arch)
        self.assertNotIn("room_entity", {n.category for n in no_models_arch.nodes})
        self.assertFalse(any(e.relation == "DEFINES_ENTITY" for e in no_models_arch.edges))
        self.assertFalse(any(e.relation == "QUERIES" for e in no_models_arch.edges))
        self.assertIn("di_module", {n.category for n in no_models_arch.nodes})

        arch2 = analyzer.analyze()
        no_deps_builder = AndroidArchitectureGraphBuilder(include_models=True, include_dependencies=False)
        no_deps_arch = no_deps_builder.build_graph(arch2)
        categories = {n.category for n in no_deps_arch.nodes}
        self.assertNotIn("di_module", categories)
        self.assertNotIn("di_binding", categories)
        self.assertNotIn("dagger_component", categories)
        self.assertIn("room_entity", categories)
        self.assertFalse(any(e.relation in ("PROVIDES", "BINDS", "INSTALLS_IN", "INJECTS") for e in no_deps_arch.edges))

    def test_mermaid_generation(self):
        self._create_sample_android_app()
        analyzer = AndroidAnalyzer(str(self.project_path))
        arch = analyzer.analyze()
        builder = AndroidArchitectureGraphBuilder()
        arch = builder.build_graph(arch)

        mermaid = builder.generate_mermaid(arch)
        self.assertTrue(mermaid.startswith("graph TD"))
        self.assertIn("-->", mermaid)

    def test_language_graph_is_merged_without_mutating_kotlin_edges(self):
        self._create_sample_android_app()
        core_nodes, core_edges = KotlinAnalyzer(self.project_path).build()
        arch = AndroidArchitectureGraphBuilder().build_graph(AndroidAnalyzer(self.project_path).analyze())
        merged_nodes = {node.id for node in arch.nodes}
        merged_edges = {(edge.from_id, edge.to_id, edge.relation): edge for edge in arch.edges}
        self.assertTrue({node.id for node in core_nodes}.issubset(merged_nodes))
        for edge in core_edges:
            actual = merged_edges[(edge.from_id, edge.to_id, edge.relation)]
            self.assertEqual(actual.confidence, edge.confidence)
            self.assertEqual(actual.resolution, edge.resolution)
            self.assertEqual(actual.candidates, edge.candidates)
            self.assertEqual(actual.evidence, edge.evidence)
        no_language = AndroidArchitectureGraphBuilder(include_language_graph=False).build_graph(
            AndroidAnalyzer(self.project_path).analyze()
        )
        self.assertFalse(any(node.provenance == "kotlin-core" for node in no_language.nodes))


@unittest.skipUnless(_HAS_TREE_SITTER, "tree-sitter-language-pack not installed")
class TestAndroidRealSampleSmoke(unittest.TestCase):
    def test_full_pipeline_against_real_sample(self):
        nowinandroid_sample = fixture_root("android-nowinandroid")
        analyzer = AndroidAnalyzer(str(nowinandroid_sample))
        arch = analyzer.analyze()

        builder = AndroidArchitectureGraphBuilder()
        arch = builder.build_graph(arch)

        self.assertGreater(len(arch.nodes), 10)
        self.assertGreater(len(arch.edges), 5)
        node_ids = {n.id for n in arch.nodes}
        for edge in arch.edges:
            self.assertIn(edge.from_id, node_ids)
            self.assertIn(edge.to_id, node_ids)
        self.assertIn("analysis", arch.stats)

        with tempfile.TemporaryDirectory() as directory:
            out_html = Path(directory) / "output.html"
            renderer = HTMLRenderer(title="NowInAndroid Sample", framework_label="Android")
            rendered_file = renderer.render(arch, str(out_html))
            self.assertTrue(rendered_file.exists())


if __name__ == "__main__":
    unittest.main()
