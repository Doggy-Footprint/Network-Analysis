import hashlib
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import yaml

import repository
import repository.models
import repository.scan
from repository import (
    ScanPolicy,
    ScanPolicyError,
    ScanPolicyRef,
    build_snapshot,
    default_scan_policy_path,
    list_repository_files,
    load_scan_policy,
)

ROOT = Path(__file__).resolve().parents[1]
REF = ScanPolicyRef("test-policy", 1, "0" * 64)

VALID_POLICY = {
    "id": "temp-policy",
    "version": 1,
    "max_file_bytes": 100,
    "exclusions": {
        "vendor_globs": ["v/**"],
        "generated_globs": ["g/**"],
        "generated_markers": ["auto"],
        "lockfile_names": ["a.lock"],
    },
}
EXCLUSION_KEYS = ("vendor_globs", "generated_globs", "generated_markers", "lockfile_names")


def policy(**overrides):
    values = dict(
        ref=REF,
        max_file_bytes=1000,
        generated_marker_lines=2,
        include_agent_docs=False,
        tracked_files_only=True,
        vendor_globs=["vendor/**"],
        generated_globs=["gen/**"],
        generated_markers=["generated file"],
        lockfile_names=["my.lock"],
    )
    values.update(overrides)
    return ScanPolicy(**values)


AGENT_VIEW_SHAPED = json.dumps({"schema_version": "3", "query_nodes": [], "occurrence_store": []})


def snapshot_of(files, *, root, scan_policy=None, unreadable=(), raising=None, **kwargs):
    def reader(path):
        relative = path.relative_to(root).as_posix()
        if relative in unreadable:
            return None
        if raising and relative in raising:
            raise raising[relative]
        return files[relative]

    return build_snapshot(
        root, list(files), policy=scan_policy or policy(), reader=reader, ignore_source="test", **kwargs
    )


def reasons_of(snapshot):
    return {item.file_path: item.reason for item in snapshot.excluded_files}


def expected_digest(contents):
    body = "".join(
        f"{path}\0{hashlib.sha256(text.encode('utf-8')).hexdigest()}\n" for path, text in sorted(contents.items())
    )
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


class TempRootCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name).resolve()

    def write_policy(self, data, name="policy.yaml"):
        path = self.root / name
        path.write_text(yaml.safe_dump(data), encoding="utf-8")
        return path


def valid(**changes):
    data = json.loads(json.dumps(VALID_POLICY))
    data.update(changes)
    return data


class PolicyLoadingTests(TempRootCase):
    def test_VO2_V1_default_policy_matches_snapshot_v1_yaml(self):
        path = default_scan_policy_path()
        self.assertEqual(path, ROOT / "profiles" / "snapshot.v1.yaml")
        loaded = load_scan_policy(path)
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        self.assertEqual(loaded.max_file_bytes, raw["max_file_bytes"])
        self.assertEqual(loaded.generated_marker_lines, raw["generated_marker_lines"])
        self.assertEqual(loaded.include_agent_docs, raw["include_agent_docs"])
        self.assertEqual(loaded.tracked_files_only, raw["tracked_files_only"])
        for key in EXCLUSION_KEYS:
            self.assertEqual(getattr(loaded, key), raw["exclusions"][key], key)
        self.assertEqual(loaded.ref.id, "snapshot")
        self.assertEqual(loaded.ref.version, 1)
        self.assertEqual(loaded.ref.content_hash, hashlib.sha256(path.read_bytes()).hexdigest())

    def test_VO2_V2_optional_keys_default(self):
        path = self.write_policy(valid())
        loaded = load_scan_policy(path)
        self.assertEqual(loaded.generated_marker_lines, 8)
        self.assertIs(loaded.include_agent_docs, True)
        self.assertIs(loaded.tracked_files_only, True)
        self.assertEqual(loaded.ref, ScanPolicyRef("temp-policy", 1, hashlib.sha256(path.read_bytes()).hexdigest()))
        self.assertEqual(loaded.max_file_bytes, 100)
        self.assertEqual(loaded.vendor_globs, ["v/**"])
        self.assertEqual(loaded.generated_globs, ["g/**"])
        self.assertEqual(loaded.generated_markers, ["auto"])
        self.assertEqual(loaded.lockfile_names, ["a.lock"])

    def test_VO2_V3_explicit_optional_keys_are_reflected(self):
        path = self.write_policy(
            valid(generated_marker_lines=3, include_agent_docs=False, tracked_files_only=False)
        )
        loaded = load_scan_policy(str(path))
        self.assertEqual(loaded.generated_marker_lines, 3)
        self.assertIs(loaded.include_agent_docs, False)
        self.assertIs(loaded.tracked_files_only, False)

    def assert_rejected(self, label, data=None, raw=None):
        path = self.root / "bad.yaml"
        if raw is not None:
            path.write_bytes(raw)
        else:
            path.write_text(yaml.safe_dump(data), encoding="utf-8")
        with self.subTest(label), self.assertRaises(ScanPolicyError):
            load_scan_policy(path)

    def test_VO3_E1_missing_file_names_path(self):
        missing = self.root / "absent.yaml"
        with self.assertRaises(ScanPolicyError) as caught:
            load_scan_policy(missing)
        self.assertIn(str(missing), str(caught.exception))
        self.assertIsInstance(caught.exception, ValueError)

    def test_VO3_E2_yaml_and_decode_errors(self):
        self.assert_rejected("E2-yaml", raw=b"a: [unterminated\n")
        self.assert_rejected("E2-decode", raw=b"\xff\xfe\x80\x81: 1\n")

    def test_VO3_E3_root_is_not_mapping(self):
        self.assert_rejected("E3-list", data=[1, 2])
        self.assert_rejected("E3-scalar", data="text")

    def test_VO3_E4_required_keys_missing(self):
        for key in ("id", "version", "max_file_bytes", "exclusions"):
            data = valid()
            del data[key]
            self.assert_rejected(f"E4-{key}", data=data)
        for key in EXCLUSION_KEYS:
            data = valid()
            del data["exclusions"][key]
            self.assert_rejected(f"E4-exclusions.{key}", data=data)

    def test_VO3_E5_id_empty_or_not_string(self):
        self.assert_rejected("E5-empty", data=valid(id=""))
        self.assert_rejected("E5-int", data=valid(id=5))

    def test_VO3_E6_version_not_one(self):
        self.assert_rejected("E6-2", data=valid(version=2))
        self.assert_rejected("E6-0", data=valid(version=0))

    def test_VO3_E7_numeric_bounds(self):
        for value in (0, -1, 1.5, "10"):
            self.assert_rejected(f"E7-max_file_bytes-{value!r}", data=valid(max_file_bytes=value))
            self.assert_rejected(f"E7-marker_lines-{value!r}", data=valid(generated_marker_lines=value))

    def test_VO3_E8_bool_is_not_int(self):
        self.assert_rejected("E8-max_file_bytes", data=valid(max_file_bytes=True))
        self.assert_rejected("E8-marker_lines", data=valid(generated_marker_lines=True))

    def test_VO3_E9_bool_fields_reject_non_bool(self):
        for key in ("include_agent_docs", "tracked_files_only"):
            for value in ("yes", 1, None):
                self.assert_rejected(f"E9-{key}-{value!r}", data=valid(**{key: value}))

    def test_VO3_E10_exclusions_not_mapping(self):
        self.assert_rejected("E10-list", data=valid(exclusions=["a"]))
        self.assert_rejected("E10-string", data=valid(exclusions="a"))

    def test_VO3_E11_exclusion_lists_must_be_string_arrays(self):
        for key in EXCLUSION_KEYS:
            for label, value in (("int-element", ["ok", 1]), ("scalar", "text"), ("mapping", {"a": "b"})):
                data = valid()
                data["exclusions"][key] = value
                self.assert_rejected(f"E11-{key}-{label}", data=data)


class SnapshotReasonTests(TempRootCase):
    def test_VO4_R0_to_R10_one_file_per_reason(self):
        files = {
            "ok.py": "value = 1\n",
            "out.txt": "x",
            "my.lock": "x",
            "vendor/a.py": "x",
            "gen/a.py": "x",
            "unread.txt": "x",
            "art.data": AGENT_VIEW_SHAPED,
            "big.txt": "x" * 1001,
            "bin.dat": "a\0b",
            "marked.txt": "Generated File\nx",
            "AGENTS.md": "guide",
        }
        snap = snapshot_of(files, root=self.root, unreadable=("unread.txt",), excluded_paths=["out.txt"])
        self.assertEqual(
            reasons_of(snap),
            {
                "out.txt": "explicit_output",
                "my.lock": "lockfile",
                "vendor/a.py": "vendored",
                "gen/a.py": "generated_path",
                "unread.txt": "unreadable",
                "big.txt": "too_large",
                "bin.dat": "binary",
                "marked.txt": "generated_marker",
                "AGENTS.md": "agent_document_disabled",
            },
        )
        self.assertEqual(snap.content_map(), {"ok.py": "value = 1\n", "art.data": AGENT_VIEW_SHAPED})
        self.assertEqual([item.file_path for item in snap.excluded_files], sorted(reasons_of(snap)))

    def test_VO4_R10_agent_documents_included_when_enabled(self):
        files = {"AGENTS.md": "a", "CLAUDE.md": "b", "README.md": "c", "docs/README.md": "d"}
        enabled = snapshot_of(files, root=self.root, scan_policy=policy(include_agent_docs=True))
        self.assertEqual(enabled.content_map(), files)
        disabled = snapshot_of(files, root=self.root)
        self.assertEqual(
            reasons_of(disabled),
            {name: "agent_document_disabled" for name in files},
        )

    def test_VO4_adjacent_priority_pairs(self):
        cases = [
            ("R1>R2", {"my.lock": "x"}, {}, {"excluded_paths": ["my.lock"]}, None, "explicit_output"),
            ("R2>R3", {"vendor/my.lock": "x"}, {}, {}, None, "lockfile"),
            ("R3>R4", {"vendor/a.py": "x"}, {}, {}, policy(generated_globs=["vendor/**"]), "vendored"),
            ("R4>R5", {"gen/a.py": "x"}, {"unreadable": ("gen/a.py",)}, {}, None, "generated_path"),
            ("R7>R8", {"a.dat": "\0" + "x" * 20}, {}, {}, policy(max_file_bytes=10), "too_large"),
            ("R8>R9", {"a.dat": "generated file\0"}, {}, {}, None, "binary"),
            ("R9>R10", {"AGENTS.md": "generated file"}, {}, {}, None, "generated_marker"),
        ]
        for label, files, reader_options, kwargs, scan_policy, expected in cases:
            with self.subTest(label):
                snap = snapshot_of(files, root=self.root, scan_policy=scan_policy, **reader_options, **kwargs)
                self.assertEqual(list(reasons_of(snap).values()), [expected])
                self.assertEqual(snap.content_map(), {})


class FormerArtifactMarkerTests(TempRootCase):
    """F16: files shaped like the retired agent_view outputs are ordinary files."""

    def test_F16_each_former_artifact_marker_is_included_as_a_regular_file(self):
        markers = {
            "json-v3-space-store.json": '{"schema_version": "3", "occurrence_store": []}',
            "json-v2-compact-nodes.json": '{"schema_version":"2","query_nodes":[]}',
            "html-payload.html": "<html><script id=\"agent-view-v3-payload\"></script></html>",
            "html-data.html": '<html><script id="agent-view-data"></script></html>',
        }
        snap = snapshot_of(dict(markers), root=self.root, scan_policy=policy(max_file_bytes=100000))
        self.assertEqual(snap.excluded_files, ())
        self.assertEqual(snap.content_map(), markers)


class BoundaryTests(TempRootCase):
    def test_VO5_B1_max_file_bytes_boundary(self):
        scan_policy = policy(max_file_bytes=10)
        snap = snapshot_of({"eq.txt": "x" * 10, "over.txt": "x" * 11}, root=self.root, scan_policy=scan_policy)
        self.assertEqual(snap.content_map(), {"eq.txt": "x" * 10})
        self.assertEqual(reasons_of(snap), {"over.txt": "too_large"})

    def test_VO5_B1_limit_counts_utf8_bytes(self):
        scan_policy = policy(max_file_bytes=10)
        snap = snapshot_of({"eq.txt": "é" * 5, "over.txt": "é" * 6}, root=self.root, scan_policy=scan_policy)
        self.assertEqual(set(snap.content_map()), {"eq.txt"})
        self.assertEqual(reasons_of(snap), {"over.txt": "too_large"})

    def test_VO5_B2_marker_line_boundary(self):
        for lines in (1, 3):
            with self.subTest(marker_lines=lines):
                inside = "x\n" * (lines - 1) + "Do Not Edit\n" + "tail\n"
                outside = "x\n" * lines + "Do Not Edit\n"
                snap = snapshot_of(
                    {"inside.txt": inside, "outside.txt": outside},
                    root=self.root,
                    scan_policy=policy(generated_marker_lines=lines, generated_markers=["do not edit"]),
                )
                self.assertEqual(reasons_of(snap), {"inside.txt": "generated_marker"})
                self.assertEqual(snap.content_map(), {"outside.txt": outside})

    def test_VO5_B3_nul_position_boundary(self):
        scan_policy = policy(max_file_bytes=100000)
        inside = "a" * 8191 + "\0" + "b"
        outside = "a" * 8192 + "\0"
        snap = snapshot_of({"in.dat": inside, "out.dat": outside}, root=self.root, scan_policy=scan_policy)
        self.assertEqual(reasons_of(snap), {"in.dat": "binary"})
        self.assertEqual(snap.content_map(), {"out.dat": outside})


class NormalizationDigestTests(TempRootCase):
    def test_VO6_N1_leading_dot_slash_and_duplicates_collapse(self):
        seen = []
        snap = build_snapshot(
            self.root,
            ["./a.py", "a.py", "./a.py"],
            policy=policy(),
            reader=lambda path: seen.append(path) or "x = 1\n",
        )
        self.assertEqual(snap.contents, (("a.py", "x = 1\n"),))
        self.assertEqual(seen, [self.root / "a.py"])

    def test_VO6_N2_output_order_is_sorted_regardless_of_input_order(self):
        files = {"z.py": "z", "b/y.py": "y", "a.py": "a", "vendor/q.py": "q", "my.lock": "l", "gen/r": "r"}
        forward = snapshot_of(files, root=self.root)
        backward = snapshot_of(dict(reversed(list(files.items()))), root=self.root)
        self.assertEqual([path for path, _ in forward.contents], ["a.py", "b/y.py", "z.py"])
        self.assertEqual([item.file_path for item in forward.excluded_files], ["gen/r", "my.lock", "vendor/q.py"])
        self.assertEqual(forward, backward)

    def explicit(self, excluded, files):
        return snapshot_of(files, root=self.root, excluded_paths=excluded)

    def test_VO6_O1_relative_path_and_descendants(self):
        files = {"out/a.txt": "x", "out/sub/b.txt": "x", "keep.txt": "x"}
        snap = self.explicit(["out"], files)
        self.assertEqual(reasons_of(snap), {"out/a.txt": "explicit_output", "out/sub/b.txt": "explicit_output"})
        self.assertEqual(set(snap.content_map()), {"keep.txt"})
        self.assertEqual(reasons_of(self.explicit(["out"], {"out": "x"})), {"out": "explicit_output"})

    def test_VO6_O2_absolute_path_under_root(self):
        files = {"out/a.txt": "x", "keep.txt": "x", "one.json": "x"}
        snap = self.explicit([self.root / "out", str(self.root / "one.json")], files)
        self.assertEqual(reasons_of(snap), {"out/a.txt": "explicit_output", "one.json": "explicit_output"})
        self.assertEqual(set(snap.content_map()), {"keep.txt"})

    def test_VO6_O3_absolute_path_outside_root_is_ignored(self):
        with tempfile.TemporaryDirectory() as other:
            outside = Path(other).resolve()
            snap = self.explicit([outside, outside / "a.py"], {"a.py": "x", "out/b.py": "x"})
        self.assertEqual(set(snap.content_map()), {"a.py", "out/b.py"})
        self.assertEqual(snap.excluded_files, ())

    def test_VO6_O4_prefix_lookalike_is_not_excluded(self):
        snap = self.explicit(["out"], {"outside/x": "x", "out/y": "x", "out.txt": "x"})
        self.assertEqual(reasons_of(snap), {"out/y": "explicit_output"})
        self.assertEqual(set(snap.content_map()), {"outside/x", "out.txt"})

    def test_VO6_D1_digest_matches_independent_computation(self):
        files = {"b/two.py": "two é\n", "a.py": "one\n", "vendor/skip.py": "skip"}
        snap = snapshot_of(files, root=self.root)
        included = {"a.py": "one\n", "b/two.py": "two é\n"}
        self.assertEqual(snap.digest, expected_digest(included))
        self.assertEqual(snap.digest, snapshot_of(files, root=self.root).digest)

    def test_VO6_D1_empty_inclusion_digest(self):
        snap = snapshot_of({"vendor/a.py": "x"}, root=self.root)
        self.assertEqual(snap.digest, hashlib.sha256(b"").hexdigest())

    def test_VO6_D2_one_byte_change_changes_digest(self):
        before = snapshot_of({"a.py": "abc"}, root=self.root)
        after = snapshot_of({"a.py": "abd"}, root=self.root)
        self.assertNotEqual(before.digest, after.digest)
        self.assertEqual(after.digest, expected_digest({"a.py": "abd"}))

    def test_VO6_U1_reader_errors_mark_only_that_file_unreadable(self):
        snap = snapshot_of(
            {"ok.py": "x", "os.py": "x", "uni.py": "x"},
            root=self.root,
            raising={
                "os.py": OSError("denied"),
                "uni.py": UnicodeDecodeError("utf-8", b"\xff", 0, 1, "bad"),
            },
        )
        self.assertEqual(reasons_of(snap), {"os.py": "unreadable", "uni.py": "unreadable"})
        self.assertEqual(snap.content_map(), {"ok.py": "x"})

    def test_VO6_U2_reader_none_marks_unreadable_and_continues(self):
        snap = snapshot_of({"a.py": "x", "none.py": "x", "z.py": "z"}, root=self.root, unreadable=("none.py",))
        self.assertEqual(reasons_of(snap), {"none.py": "unreadable"})
        self.assertEqual(snap.content_map(), {"a.py": "x", "z.py": "z"})


class InventoryTests(TempRootCase):
    def test_VO7_L1_git_entries_present(self):
        with mock.patch("repository.scan._git_tracked_files", return_value=["b.py", "a.py"]) as tracked, \
                mock.patch("repository.scan._walk_files") as walk:
            result = list_repository_files(self.root)
        self.assertEqual(result, ("git-tracked", ["a.py", "b.py"]))
        tracked.assert_called_once_with(self.root)
        walk.assert_not_called()

    def test_VO7_L1_real_git_repository_omits_untracked(self):
        if shutil.which("git") is None:
            self.skipTest("git unavailable")
        (self.root / "tracked.py").write_text("x", encoding="utf-8")
        (self.root / "untracked.py").write_text("x", encoding="utf-8")
        subprocess.run(["git", "init", "-q"], cwd=self.root, check=True)
        subprocess.run(["git", "add", "tracked.py"], cwd=self.root, check=True)
        self.assertEqual(list_repository_files(self.root), ("git-tracked", ["tracked.py"]))

    def build_tree(self):
        for name in (
            "a.py", "sub/b.py", ".hidden/c.py", ".git/x", "__pycache__/x", "build/x", "dist/x",
            "env/x", "node_modules/x", "venv/x",
        ):
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("x", encoding="utf-8")

    def test_VO7_L2_git_none_and_empty_fall_back_to_walk(self):
        self.build_tree()
        with mock.patch("repository.scan._git_tracked_files", return_value=None):
            self.assertEqual(list_repository_files(self.root), ("static_fallback", ["a.py", "sub/b.py"]))

    def test_VO7_L2_real_git_repository_without_tracked_files_falls_back(self):
        if shutil.which("git") is None:
            self.skipTest("git unavailable")
        self.build_tree()
        subprocess.run(["git", "init", "-q"], cwd=self.root, check=True)
        self.assertEqual(list_repository_files(self.root), ("static_fallback", ["a.py", "sub/b.py"]))

    def test_VO7_L2_real_git_failure_falls_back(self):
        self.build_tree()
        with mock.patch("subprocess.run", side_effect=OSError("git missing")):
            self.assertEqual(list_repository_files(self.root), ("static_fallback", ["a.py", "sub/b.py"]))

    def test_VO7_L2a_nonzero_git_exit_ignores_stdout(self):
        self.build_tree()
        failed = SimpleNamespace(returncode=128, stdout=b"x.py\0", stderr=b"")
        with mock.patch("subprocess.run", return_value=failed):
            self.assertEqual(list_repository_files(self.root), ("static_fallback", ["a.py", "sub/b.py"]))

    def test_VO7_L3_tracked_files_only_false_skips_git(self):
        self.build_tree()
        with mock.patch("repository.scan._git_tracked_files", return_value=["git.py"]) as tracked:
            result = list_repository_files(self.root, tracked_files_only=False)
        self.assertEqual(result, ("static_fallback", ["a.py", "sub/b.py"]))
        tracked.assert_not_called()

    def test_VO7_L4_walk_skips_hidden_and_static_excluded_directories(self):
        self.build_tree()
        with mock.patch("repository.scan._git_tracked_files", return_value=None):
            source, paths = list_repository_files(self.root)
        self.assertEqual(source, "static_fallback")
        self.assertEqual(paths, ["a.py", "sub/b.py"])


class NestedWalkExclusionTests(TempRootCase):
    def make_files(self, names):
        for name in names:
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("x", encoding="utf-8")

    def walk(self):
        return list_repository_files(self.root, tracked_files_only=False)

    def assert_nested_excluded(self, directory):
        self.make_files(
            [
                "pkg/keep.py",
                f"pkg/sub/{directory}/x.py",
                f"pkg/sub/{directory}/inner/y.py",
                f"deep/1/2/{directory}/z.py",
            ]
        )
        self.assertEqual(self.walk(), ("static_fallback", ["pkg/keep.py"]))

    def test_VO1_D1_dot_prefixed_directory_nested(self):
        self.assert_nested_excluded(".cache")

    def test_VO1_D2_git_directory_nested(self):
        self.assert_nested_excluded(".git")

    def test_VO1_D3_pycache_directory_nested(self):
        self.assert_nested_excluded("__pycache__")

    def test_VO1_D4_build_directory_nested(self):
        self.assert_nested_excluded("build")

    def test_VO1_D5_dist_directory_nested(self):
        self.assert_nested_excluded("dist")

    def test_VO1_D6_env_directory_nested(self):
        self.assert_nested_excluded("env")

    def test_VO1_D7_node_modules_directory_nested(self):
        self.assert_nested_excluded("node_modules")

    def test_VO1_D8_venv_directory_nested(self):
        self.assert_nested_excluded("venv")

    def test_VO1_same_name_at_depth_1_and_depth_3_or_more(self):
        self.make_files(
            [
                "keep.py",
                "build/top.py",
                "a/b/c/keep.py",
                "a/b/c/build/deep.py",
                "a/b/c/build/inner/deeper.py",
            ]
        )
        self.assertEqual(self.walk(), ("static_fallback", ["a/b/c/keep.py", "keep.py"]))

    def test_VO2_K1_file_named_like_excluded_directory_is_kept(self):
        self.make_files(["sub/build"])
        self.assertEqual(self.walk(), ("static_fallback", ["sub/build"]))

    def test_VO2_K2_suffix_lookalike_directory_is_kept(self):
        self.make_files(["sub/builds/b.py"])
        self.assertEqual(self.walk(), ("static_fallback", ["sub/builds/b.py"]))

    def test_VO2_K3_prefix_lookalike_directory_is_kept(self):
        self.make_files(["sub/my_env/c.py"])
        self.assertEqual(self.walk(), ("static_fallback", ["sub/my_env/c.py"]))

    def test_VO2_K4_dot_prefixed_file_is_kept(self):
        self.make_files(["sub/.hidden_file"])
        self.assertEqual(self.walk(), ("static_fallback", ["sub/.hidden_file"]))


class ReexportTests(unittest.TestCase):
    def test_VO9_repository_exports(self):
        expected = {
            "ExcludedFile", "RepositorySnapshot", "ScanPolicy", "ScanPolicyRef", "ScanPolicyError",
            "build_snapshot", "default_scan_policy_path", "list_repository_files", "load_scan_policy", "read_file",
        }
        for name in expected:
            with self.subTest(name):
                self.assertTrue(hasattr(repository, name))


class SnapshotMetadataTests(TempRootCase):
    def test_VO11_T1_T2_root_and_ignore_source(self):
        snap = build_snapshot(self.root, ["a.py"], policy=policy(), reader=lambda p: "x", ignore_source="custom-src")
        self.assertEqual(snap.root, str(self.root))
        self.assertEqual(snap.ignore_source, "custom-src")

    def test_VO11_T3_ignore_source_defaults_to_provided(self):
        snap = build_snapshot(self.root, ["a.py"], policy=policy(), reader=lambda p: "x")
        self.assertEqual(snap.ignore_source, "provided")

    def test_VO11_F1_read_file_utf8(self):
        (self.root / "u.txt").write_bytes("h\u00e9llo \u4e2d\n".encode("utf-8"))
        self.assertEqual(repository.read_file(self.root / "u.txt"), "h\u00e9llo \u4e2d\n")

    def test_VO11_F2_invalid_utf8_is_replaced(self):
        (self.root / "bad.txt").write_bytes(b"a\xffb")
        self.assertEqual(repository.read_file(self.root / "bad.txt"), "a\ufffdb")

    def test_VO11_F3_missing_path_returns_none(self):
        self.assertIsNone(repository.read_file(self.root / "absent.txt"))


if __name__ == "__main__":
    unittest.main()
