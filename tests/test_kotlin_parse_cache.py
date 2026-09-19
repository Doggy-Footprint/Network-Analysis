"""
Unit tests for KotlinParseCache (contracts/kotlin-parse-cache.md).
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
try:
    import tree_sitter_language_pack  # noqa: F401
    _HAS_TREE_SITTER = True
except ImportError:
    _HAS_TREE_SITTER = False

if _HAS_TREE_SITTER:
    from framework_analyzers.android.analyzer import AndroidAnalyzer
    from framework_analyzers.android.graph import AndroidArchitectureGraphBuilder
    from language_analyzers.kotlin import KotlinAnalyzer, KotlinParseCache
    from language_analyzers.kotlin import ast as ka

SAMPLE_KT = """
package com.example.sample

class Sample {
    fun greet(): String {
        return "hi"
    }
}
"""

OTHER_KT = """
package com.example.sample

class Other {
    fun bye(): String {
        return "bye"
    }
}
"""


@unittest.skipUnless(_HAS_TREE_SITTER, "tree-sitter-language-pack not installed")
class TestKotlinParseCache(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.project_path = Path(self.test_dir)
        self.kt_file = self.project_path / "Sample.kt"
        self.kt_file.write_text(SAMPLE_KT)
        self.kt_file2 = self.project_path / "Other.kt"
        self.kt_file2.write_text(OTHER_KT)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_EC_01_second_call_same_path_returns_identical_tuple_without_reparsing(self):
        cache = KotlinParseCache()
        real_read_bytes = Path.read_bytes
        read_calls = []

        def counting_read_bytes(self):
            read_calls.append(self)
            return real_read_bytes(self)

        real_parser = ka.get_kotlin_parser()
        parse_calls = []

        class CountingParserProxy:
            def parse(self, *args, **kwargs):
                parse_calls.append((args, kwargs))
                return real_parser.parse(*args, **kwargs)

        proxy = CountingParserProxy()
        with mock.patch.object(Path, "read_bytes", counting_read_bytes), \
                mock.patch.object(ka, "get_kotlin_parser", return_value=proxy):
            source1, root1 = cache.read_and_parse(self.kt_file)
            source2, root2 = cache.read_and_parse(self.kt_file)

        self.assertIs(source1, source2)
        self.assertIs(root1, root2)
        self.assertEqual(len(read_calls), 1)
        self.assertEqual(len(parse_calls), 1)

    def test_EC_02_single_call_returns_bytes_and_parsed_root_and_caches(self):
        cache = KotlinParseCache()
        source, root = cache.read_and_parse(self.kt_file)

        self.assertEqual(source, self.kt_file.read_bytes())
        declarations = ka.top_level_declarations(root)
        self.assertEqual(len(declarations), 1)
        self.assertEqual(ka.declared_name(declarations[0], source), "Sample")
        # entry is now cached under path
        cached_source, cached_root = cache._cache[self.kt_file]
        self.assertIs(cached_source, source)
        self.assertIs(cached_root, root)

    def test_EC_03_oserror_propagates_and_is_not_cached_and_retries(self):
        cache = KotlinParseCache()
        missing = self.project_path / "does_not_exist.kt"

        with self.assertRaises(OSError):
            cache.read_and_parse(missing)

        self.assertNotIn(missing, cache._cache)

        # Subsequent call, after the file becomes readable, re-attempts the read
        # (rather than replaying a cached failure).
        with self.assertRaises(OSError):
            cache.read_and_parse(missing)
        self.assertNotIn(missing, cache._cache)

        missing.write_text(SAMPLE_KT)
        source, root = cache.read_and_parse(missing)
        self.assertEqual(source, missing.read_bytes())
        self.assertIn(missing, cache._cache)

    def test_EC_04_no_parse_cache_argument_creates_private_cache_and_output_unchanged(self):
        analyzer_a = AndroidAnalyzer(str(self.project_path))
        analyzer_b = AndroidAnalyzer(str(self.project_path))
        self.assertIsNot(analyzer_a._parse_cache, analyzer_b._parse_cache)
        self.assertIsInstance(analyzer_a._parse_cache, KotlinParseCache)

        arch_a = analyzer_a.analyze()
        arch_b = analyzer_b.analyze()
        self.assertEqual({c.name for c in arch_a.composables}, {c.name for c in arch_b.composables})
        self.assertEqual(len(arch_a.viewmodels), len(arch_b.viewmodels))

        kotlin_a = KotlinAnalyzer(self.project_path)
        kotlin_b = KotlinAnalyzer(self.project_path)
        self.assertIsNot(kotlin_a._parse_cache, kotlin_b._parse_cache)
        nodes_a, edges_a = kotlin_a.build()
        nodes_b, edges_b = kotlin_b.build()
        self.assertEqual({n.id for n in nodes_a}, {n.id for n in nodes_b})
        self.assertEqual(len(edges_a), len(edges_b))

    def test_EC_05_shared_cache_reads_and_parses_overlapping_files_once(self):
        android_files = set(AndroidAnalyzer(str(self.project_path))._discover_files())
        kotlin_files = set(KotlinAnalyzer(self.project_path)._discover_files())
        overlap = {p.resolve() for p in android_files & kotlin_files}
        # Both Sample.kt and Other.kt must be seen by both analyzers, or this test
        # cannot distinguish "read once per file" from "read once total".
        self.assertEqual(overlap, {self.kt_file.resolve(), self.kt_file2.resolve()})

        real_read_bytes = Path.read_bytes

        def make_counting_read_bytes(calls):
            def counting_read_bytes(self):
                calls.append(self)
                return real_read_bytes(self)
            return counting_read_bytes

        # Negative control: two independent (unshared) caches read each overlapping
        # file twice — establishes that the assertion below is actually exercising
        # the sharing, not something true unconditionally.
        unshared_calls = []
        with mock.patch.object(Path, "read_bytes", make_counting_read_bytes(unshared_calls)):
            AndroidAnalyzer(str(self.project_path)).analyze()
            KotlinAnalyzer(self.project_path).build()
        unshared_paths = [p.resolve() for p in unshared_calls]
        for path in overlap:
            self.assertEqual(unshared_paths.count(path), 2)

        cache = KotlinParseCache()
        shared_calls = []
        with mock.patch.object(Path, "read_bytes", make_counting_read_bytes(shared_calls)):
            analyzer = AndroidAnalyzer(str(self.project_path), parse_cache=cache)
            arch = analyzer.analyze()
            builder = AndroidArchitectureGraphBuilder(parse_cache=cache)
            builder.build_graph(arch)

        shared_paths = [p.resolve() for p in shared_calls]
        for path in overlap:
            self.assertEqual(shared_paths.count(path), 1)

    def test_C_2_parse_snapshot_caches_by_source_bytes_without_reading_its_path(self):
        cache = KotlinParseCache()
        virtual_path = self.project_path / "removed.kt"

        with mock.patch.object(Path, "read_bytes", side_effect=AssertionError("repository read")):
            first_source, first_root = cache.parse_snapshot(virtual_path, SAMPLE_KT.encode("utf-8"))
            second_source, second_root = cache.parse_snapshot(virtual_path, SAMPLE_KT.encode("utf-8"))
            changed_source, changed_root = cache.parse_snapshot(virtual_path, OTHER_KT.encode("utf-8"))

        self.assertIs(first_source, second_source)
        self.assertIs(first_root, second_root)
        self.assertEqual(changed_source, OTHER_KT.encode("utf-8"))
        self.assertIsNot(changed_root, first_root)

    def test_C_2_kotlin_analyzer_uses_snapshot_after_the_captured_file_is_deleted(self):
        snapshot = RepositorySnapshot(
            str(self.project_path.resolve()), "agent_view.v3", (("Sample.kt", SAMPLE_KT),), (), "0" * 64,
        )
        self.kt_file.unlink()

        with mock.patch.object(Path, "rglob", side_effect=AssertionError("repository traversal")), \
                mock.patch.object(Path, "read_bytes", side_effect=AssertionError("repository read")), \
                mock.patch.object(os, "walk", side_effect=AssertionError("repository traversal")):
            nodes, _ = KotlinAnalyzer(self.project_path.resolve(), snapshot=snapshot).build()

        self.assertIn("Sample", {node.label for node in nodes})


@unittest.skipUnless(_HAS_TREE_SITTER, "tree-sitter-language-pack not installed")
class TestCliAndroidWiring(unittest.TestCase):
    """Guards the actual wiring the contract exists to deliver: `code_analyzer.cli`'s
    `--framework android` branch must pass ONE KotlinParseCache instance to both
    AndroidAnalyzer and AndroidArchitectureGraphBuilder, not one each."""

    def test_EC_wiring_cli_android_branch_shares_a_single_parse_cache_instance(self):
        import contextlib
        import io
        import sys
        from unittest.mock import patch

        import code_analyzer.cli as cli_module

        test_dir = tempfile.mkdtemp()
        try:
            project_path = Path(test_dir)
            (project_path / "Sample.kt").write_text(SAMPLE_KT)

            created_instances = []
            real_cls = cli_module.KotlinParseCache

            class SpyKotlinParseCache(real_cls):
                def __init__(self):
                    super().__init__()
                    created_instances.append(self)

            argv = [
                "code-analyzer", str(project_path), "-f", "android",
                "-o", str(project_path / "architecture.html"),
            ]
            with patch.object(cli_module, "KotlinParseCache", SpyKotlinParseCache), \
                    patch.object(sys, "argv", argv):
                with contextlib.redirect_stdout(io.StringIO()):
                    cli_module.main()

            self.assertEqual(len(created_instances), 1)
        finally:
            shutil.rmtree(test_dir, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
