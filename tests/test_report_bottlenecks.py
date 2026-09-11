import copy
import json
import re
from dataclasses import asdict
from pathlib import Path

import pytest

from agent_view import build_agent_view, load_profile
from agent_view.models import RepositorySnapshot
from bottlenecks import analyze_bottlenecks, bottlenecks_to_json, parse_harness_profile, parse_observation_trace
from language_analyzers.python.graph import PythonGraphAnalyzer
from report.bottlenecks.generate import generate, main, render_report
from report.shared.document import ReportInputError, ReportOutputError


@pytest.fixture
def payload() -> dict:
    return {
        "schema": "bottlenecks.v1",
        "snapshot": {"digest": "abc", "file_count": 2},
        "profile": {"id": "fixed", "settings": {"limit": 30}},
        "versions": {"analysis": "1"},
        "coverage": {"mode": "tracked"},
        "probes": [
            {
                "probe": {
                    "id": "p:1",
                    "kind": "exact",
                    "scope": "repository",
                    "surface": "content",
                    "term": "needle",
                },
                "output": {
                    "probe_id": "p:1",
                    "rows": [
                        {
                            "path": "src/a.py",
                            "line": 7,
                            "end_line": 9,
                            "text": "needle",
                            "occurrences": 1,
                        }
                    ],
                    "total_count": 1,
                    "visible_count": 1,
                    "omitted_count": 0,
                    "truncated": False,
                },
                "visible_arrival_ids": ["py:src.a#thing"],
                "hidden_arrival_ids": [],
            }
        ],
        "candidates": [
            {
                "id": "b:1",
                "target": "py:src.a#thing",
                "kind": "multiple_results",
                "metrics": {"visible_rows": 1},
                "evidence": {
                    "visible": [
                        {"path": "src/a.py", "line": 7, "text": "needle", "occurrences": 1}
                    ],
                    "hidden": [
                        {"path": "src/full/path.py", "line": 12, "text": "needle", "occurrences": 1}
                    ],
                    "visible_arrival_ids": ["py:src.a#thing"],
                    "hidden_arrival_ids": ["py:src.full#thing"],
                },
                "status": "static_candidate",
                "probe_ids": ["p:1"],
                "reasons": ["multiple_results"],
                "coverage": "generated_probe",
            },
            {
                "id": "b:2",
                "target": "py:missing",
                "kind": "unresolved_boundary",
                "metrics": {},
                "evidence": [
                    {
                        "file_path": "src/a.py",
                        "start_line": 7,
                        "start_column": 1,
                        "end_line": 9,
                        "end_column": 2,
                    }
                ],
                "status": "static_candidate",
                "probe_ids": [],
                "reasons": ["unresolved_or_dynamic_relation"],
                "coverage": "original_python_relations",
            },
        ],
        "observations": [{"before": "one", "after": "two"}],
        "limitations": ["Static evidence only."],
    }


def embedded_payload(document: str) -> dict:
    match = re.search(
        r"<script id='bottlenecks-data' type='application/json'>(.*?)</script>",
        document,
        re.DOTALL,
    )
    assert match
    return json.loads(match.group(1))


def test_render_displays_contract_fields_without_changing_payload(payload: dict) -> None:
    original = copy.deepcopy(payload)
    document = render_report(payload)
    assert payload == original
    assert embedded_payload(document) == payload
    for text in (
        "py:src.a#thing",
        "multiple_results",
        "visible_rows",
        "src/full/path.py",
        "src/a.py",
        "end_line",
        "needle",
        "static_candidate",
        "Profile and settings",
        "Versions",
        "Coverage",
        "Limitations",
        "Probes",
        "Observation comparison",
    ):
        assert text in document


def test_m3_ec_03_renderer_accepts_legacy_candidates_without_additive_fields(payload: dict) -> None:
    original = copy.deepcopy(payload)
    document = render_report(payload)
    assert embedded_payload(document) == original


def test_renderer_validates_additive_candidate_fields_when_present(payload: dict) -> None:
    candidate = payload["candidates"][0]
    candidate.update({
        "validation_status": "unverified",
        "affected_profile_ids": ["fixed"],
        "obstacle": {"axis": "result_dilution", "explanation": "Static result rows require refinement."},
    })
    document = render_report(payload)
    assert embedded_payload(document) == payload
    for text in ("result_dilution", "Static result rows require refinement.", "unverified"):
        assert text in document


@pytest.mark.parametrize(
    ("mutate", "path"),
    [
        (lambda candidate: candidate.update(validation_status="observed"), "validation_status"),
        (lambda candidate: candidate.update(affected_profile_ids=[1]), "affected_profile_ids[0]"),
        (lambda candidate: candidate.update(obstacle={"explanation": "Static barrier."}), "missing required field 'axis'"),
        (lambda candidate: candidate.update(obstacle={"axis": "result_dilution"}), "missing required field 'explanation'"),
        (lambda candidate: candidate.update(obstacle={"axis": 1, "explanation": "Static barrier."}), "obstacle.axis"),
        (lambda candidate: candidate.update(obstacle={"axis": "result_dilution", "explanation": 1}), "obstacle.explanation"),
    ],
)
def test_renderer_rejects_malformed_present_additive_candidate_fields(payload: dict, mutate, path: str) -> None:
    mutate(payload["candidates"][0])
    with pytest.raises(ReportInputError, match=re.escape(path)):
        render_report(payload)


def test_render_accepts_actual_core_output() -> None:
    root = Path(__file__).resolve().parents[1]
    contents = (
        ("a.py", "def shared():\n    return 1\n"),
        ("b.py", "from a import shared\nfrom unknown_package import missing\nshared()\n"),
        ("large.py", "def large():\n" + "    value = 1\n" * 2001),
        ("loader.py", "import importlib\ndef load():\n    return importlib.import_module('a')\n"),
    )
    import hashlib

    digest = hashlib.sha256(
        "".join(f"{path}\0{hashlib.sha256(text.encode()).hexdigest()}\n" for path, text in contents).encode()
    ).hexdigest()
    snapshot = RepositorySnapshot("/repo", "test", contents, (), digest)
    architecture = PythonGraphAnalyzer("/repo", snapshot).analyze()
    graph = build_agent_view(
        architecture,
        profile=load_profile(root / "profiles/agent_view.v3.yaml"),
        snapshot=snapshot,
    )
    profile = parse_harness_profile(
        json.loads((root / "profiles/harness.fixed-baseline.v1.json").read_text())
    )
    initial = analyze_bottlenecks(snapshot, architecture, graph, profile)
    probe = initial.probes[0]
    profile_hash = hashlib.sha256(json.dumps(asdict(profile), sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    trace = parse_observation_trace({"schema": "harness_observation.v1", "id": "actual", "snapshot_digest": snapshot.digest, "profile": {"id": profile.id, "version": profile.version, "content_hash": profile_hash}, "events": [{"id": "actual-search", "kind": "search", "status": "completed", "inputs": {"probe_id": probe["probe"]["id"]}, "returned": json.loads(json.dumps(probe["output"]))}]})
    actual = json.loads(bottlenecks_to_json(analyze_bottlenecks(snapshot, architecture, graph, profile, traces=(trace,))))
    assert {"connection_constraint", "evidence_spread", "read_limit", "unresolved_boundary"} <= {
        candidate["kind"] for candidate in actual["candidates"]
    }
    document = render_report(actual)
    assert embedded_payload(document) == actual
    visible = re.sub(r"<script id='bottlenecks-data'.*?</script>", "", document, flags=re.DOTALL)
    for value in (actual["profile"]["id"], actual["profile"]["content_hash"], str(actual["profile"]["read"]["max_lines"]), str(actual["coverage"]["source_file_count"]), str(actual["coverage"]["python_file_count"])):
        assert value in visible
    assert "returned_visible_count" in visible


def test_visible_text_and_embedded_json_are_xss_safe(payload: dict) -> None:
    attack = '</script><img src=x onerror=alert(1)>& "雪"'
    payload["candidates"][0]["target"] = attack
    document = render_report(payload)
    assert attack not in document
    assert "&lt;/script&gt;&lt;img src=x onerror=alert(1)&gt;&amp; &quot;雪&quot;" in document
    assert "\\u003c/script\\u003e" in document
    assert embedded_payload(document) == payload


@pytest.mark.parametrize(
    ("mutate", "path"),
    [
        (lambda value: value.update(schema="other"), "$.schema"),
        (lambda value: value.pop("coverage"), "$"),
        (lambda value: value.update(snapshot=[]), "$.snapshot"),
        (lambda value: value.update(limitations=[1]), "$.limitations[0]"),
        (lambda value: value.update(probes=[None]), "$.probes[0]"),
        (lambda value: value["probes"][0].update(output=[]), "$.probes[0].output"),
        (lambda value: value["probes"][0]["output"].update(rows=[{"path": 2}]), "$.probes[0].output.rows[0].path"),
        (lambda value: value.update(candidates=[None]), "$.candidates[0]"),
        (lambda value: value["candidates"][0].update(metrics=[]), "$.candidates[0].metrics"),
        (lambda value: value["candidates"][0].update(evidence=3), "$.candidates[0].evidence"),
        (lambda value: value["candidates"][0].update(probe_ids=["p:missing"]), "$.candidates[0].probe_ids[0]"),
        (lambda value: value.update(observations=[None]), "$.observations[0]"),
    ],
)
def test_malformed_shapes_raise_typed_input_error(payload: dict, mutate, path: str) -> None:
    mutate(payload)
    with pytest.raises(ReportInputError, match=re.escape(path)):
        render_report(payload)


def test_generate_uses_only_injected_io(payload: dict) -> None:
    source = Path("/does/not/exist/input.json")
    output = Path("/does/not/exist/output.html")
    calls = []

    def read_text(path: Path) -> str:
        calls.append(("read", path))
        return json.dumps(payload)

    def write_text(path: Path, document: str) -> None:
        calls.append(("write", path, embedded_payload(document)))

    assert generate(source, output, read_text=read_text, write_text=write_text) == output
    assert calls == [("read", source), ("write", output, payload)]


def test_generate_reports_invalid_json_as_input_error() -> None:
    with pytest.raises(ReportInputError):
        generate(Path("in"), Path("out"), read_text=lambda _: "{", write_text=lambda *_: None)


def test_generate_reports_write_failure_as_output_error(payload: dict) -> None:
    def fail_write(_path: Path, _document: str) -> None:
        raise OSError("disk full")

    with pytest.raises(ReportOutputError, match="disk full"):
        generate(
            Path("in"),
            Path("out"),
            read_text=lambda _: json.dumps(payload),
            write_text=fail_write,
        )


def test_main_returns_one_for_report_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("report.bottlenecks.generate.generate", lambda *_: (_ for _ in ()).throw(ReportInputError("bad")))
    assert main(["input", "-o", "output"]) == 1


def test_main_invalid_arguments_exit_two() -> None:
    with pytest.raises(SystemExit) as error:
        main([])
    assert error.value.code == 2
