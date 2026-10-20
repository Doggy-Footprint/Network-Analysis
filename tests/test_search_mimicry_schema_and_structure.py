"""V5 and V7 for spec f7564b09cf80bdd9 v1.

V5 (equivalence partitioning): A1/A2 accepted schemas, J1..J5 rejected schema/granularity combinations,
O1..O3 analyze_bottlenecks output identity. Rejections are checked on render_report and on generate, whose
write_text spy must stay uncalled (E1, E2).
V7 (structure checks over the repository tree): T1..T8.
"""
import ast
import copy
import importlib.util
import json
import re
from pathlib import Path

import pytest

from analysis import GraphAnalyzer
from bottlenecks import analyze_bottlenecks, bottlenecks_to_json
from report.bottlenecks import render_report
from report.bottlenecks.generate import generate
from report.shared.document import ReportInputError
from tests.file_analysis_support import converted, node as file_node
from tests.edge_weights_support import edge, load_weights, weights_data
from tests.test_bottlenecks_v3 import network_subject
from tests.test_file_analysis_core import payload as file_payload
from tests.test_report_bottlenecks_v3 import v3_payload

REPO = Path(__file__).resolve().parents[1]


def symbol_payload(tmp_path):
    payload = v3_payload(tmp_path)
    assert "granularity" not in payload
    return payload


def file_mode_payload(tmp_path):
    files = {"a.py": "abcd", "b.py": "abcde"}
    snap, result = converted(files, [file_node("a", "a.py"), file_node("b", "b.py")], [edge("a", "b")])
    payload = file_payload(snap, result, tmp_path)
    assert payload["granularity"] == "file"
    return payload


def v6(tmp_path):
    payload = copy.deepcopy(symbol_payload(tmp_path))
    payload["schema"] = "bottlenecks.v6"
    return payload


def v7(tmp_path):
    payload = copy.deepcopy(file_mode_payload(tmp_path))
    payload["schema"] = "bottlenecks.v7"
    payload["granularity"] = "file"
    return payload


def rejected_by_generate(payload, tmp_path):
    writes = []
    with pytest.raises(ReportInputError) as raised:
        generate(tmp_path / "in.json", tmp_path / "out.html",
                 read_text=lambda path: json.dumps(payload),
                 write_text=lambda path, text: writes.append((path, text)))
    assert writes == []
    assert not (tmp_path / "out.html").exists()
    return str(raised.value)


def rejected_by_render(payload):
    with pytest.raises(ReportInputError) as raised:
        render_report(payload)
    return str(raised.value)


# ---- V5 -------------------------------------------------------------------------------------------------------------


def test_V5_A1_v6_payload_is_accepted(tmp_path):
    payload = v6(tmp_path)
    document = render_report(payload)
    assert isinstance(document, str) and "<html" in document.lower()
    writes = []
    generate(tmp_path / "in.json", tmp_path / "out.html", read_text=lambda path: json.dumps(payload),
             write_text=lambda path, text: writes.append((path, text)))
    assert len(writes) == 1 and "<html" in writes[0][1].lower()


def test_V5_A2_v7_payload_with_granularity_file_is_accepted(tmp_path):
    payload = v7(tmp_path)
    document = render_report(payload)
    assert isinstance(document, str) and "<html" in document.lower()
    writes = []
    generate(tmp_path / "in.json", tmp_path / "out.html", read_text=lambda path: json.dumps(payload),
             write_text=lambda path, text: writes.append((path, text)))
    assert len(writes) == 1


def test_V5_J1_v4_schema_is_rejected_naming_schema_path(tmp_path):
    payload = v6(tmp_path)
    payload["schema"] = "bottlenecks.v4"
    assert "$.schema" in rejected_by_render(payload)
    assert "$.schema" in rejected_by_generate(payload, tmp_path)


def test_V5_J2_v5_schema_with_file_granularity_is_rejected_naming_schema_path(tmp_path):
    payload = v7(tmp_path)
    payload["schema"] = "bottlenecks.v5"
    assert payload["granularity"] == "file"
    assert "$.schema" in rejected_by_render(payload)
    assert "$.schema" in rejected_by_generate(payload, tmp_path)


def test_V5_J3_v7_without_granularity_is_rejected(tmp_path):
    payload = v7(tmp_path)
    del payload["granularity"]
    for message in (rejected_by_render(payload), rejected_by_generate(payload, tmp_path)):
        assert "$.granularity" in message or "$" in message


@pytest.mark.parametrize("granularity", ["symbol", "", None, "FILE"])
def test_V5_J4_v7_with_granularity_other_than_file_is_rejected(tmp_path, granularity):
    payload = v7(tmp_path)
    payload["granularity"] = granularity
    for message in (rejected_by_render(payload), rejected_by_generate(payload, tmp_path)):
        assert "$.granularity" in message or "$" in message


def test_V5_J5_v6_with_granularity_added_is_rejected(tmp_path):
    payload = v6(tmp_path)
    payload["granularity"] = "file"
    for message in (rejected_by_render(payload), rejected_by_generate(payload, tmp_path)):
        assert "$" in message


def test_V5_O1_symbol_output_is_v6_without_granularity(tmp_path):
    snapshot, architecture = network_subject(["a", "b"], [edge("a", "b")])
    payload = json.loads(bottlenecks_to_json(analyze_bottlenecks(snapshot, architecture, load_weights(tmp_path, weights_data()))))
    assert payload["schema"] == "bottlenecks.v6"
    assert "granularity" not in payload


def test_V5_O2_file_output_is_v7_with_granularity_file(tmp_path):
    payload = file_mode_payload(tmp_path)
    assert payload["schema"] == "bottlenecks.v8"
    assert payload["granularity"] == "file"


def test_V5_O3_versions_analysis_is_5_in_both_modes(tmp_path):
    snapshot, architecture = network_subject(["a"], [])
    symbol = json.loads(bottlenecks_to_json(analyze_bottlenecks(snapshot, architecture, load_weights(tmp_path, weights_data()))))
    assert symbol["versions"]["analysis"] == "5"
    assert file_mode_payload(tmp_path)["versions"]["analysis"] == "5"


# ---- V7 -------------------------------------------------------------------------------------------------------------

Q5_PATTERN = re.compile(
    r"identifier_file_count|hub_score|authority_score|degree_centrality|hop_3|_source_for_line|_tree_cache|"
    r"_source_cache|top_hubs|identifier_occurrence"
)
Q5_DIRECTORIES = (
    "analysis", "bottlenecks", "report", "renderers", "language_analyzers", "code_analyzer",
    "framework_analyzers", "repository",
)
ADR_NAME = "31d2dee6912427d5-consolidate-overlapping-metrics.md"


def matching_lines(pattern, roots, only=None):
    hits = []
    for root in roots:
        base = REPO / root
        for path in sorted(base.rglob("*") if base.is_dir() else [base]):
            if not path.is_file() or "__pycache__" in path.parts or (only and path.name != only):
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            hits.extend(f"{path.relative_to(REPO)}:{number}" for number, line in enumerate(text.splitlines(), 1) if pattern.search(line))
    return hits


def test_V7_T1_removed_symbols_have_zero_matching_lines_in_active_packages():
    assert matching_lines(Q5_PATTERN, Q5_DIRECTORIES) == []
    assert matching_lines(re.compile(r"NamePositions"), ["language_analyzers/core"], only="enrichment.py") == []


def test_V7_T2_identifier_occurrence_module_is_gone():
    assert not (REPO / "bottlenecks" / "identifier_occurrence.py").exists()
    assert importlib.util.find_spec("bottlenecks.identifier_occurrence") is None


def test_V7_T3_archived_fallback_module_keeps_source_for_line():
    path = REPO / "archive" / "token_cost_disk_fallback" / "graph_metrics_fallback.py"
    assert path.is_file()
    assert "_source_for_line" in path.read_text(encoding="utf-8")


def test_V7_T4_archived_fallback_tests_exist():
    path = REPO / "archive" / "tests" / "test_graph_metrics_disk_fallback.py"
    assert path.is_file()
    ast.parse(path.read_text(encoding="utf-8"))
    assert not list((REPO / "tests").glob("test_graph_metrics_disk_fallback.py"))


def test_V7_T5_archive_readme_mentions_the_fallback_directory():
    text = (REPO / "archive" / "README.md").read_text(encoding="utf-8")
    assert "token_cost_disk_fallback" in text
    assert sum("token_cost_disk_fallback" in line for line in text.splitlines()) == 1


def test_V7_T6_adr_file_has_required_sections():
    path = REPO / "agent-docs" / "adr" / ADR_NAME
    assert path.is_file()
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    assert any(re.match(r"# \S", line) for line in lines)
    assert any(re.match(r"\**Status\**\s*:", line) or line.startswith("Status:") for line in lines)
    for heading in ("## Context", "## Decision", "## Alternatives", "## Consequences"):
        assert any(line.strip() == heading for line in lines), heading
    assert re.search(r"(?<!\d)10(?!\d)", text)


def test_V7_T7_adr_index_block_has_the_four_fields():
    text = (REPO / "agent-docs" / "adr" / "index.md").read_text(encoding="utf-8")
    blocks = [block for block in re.split(r"^---\s*$", text, flags=re.M) if f"File: {ADR_NAME}" in block]
    assert len(blocks) == 1
    fields = [line.split(":", 1)[0] for line in blocks[0].strip().splitlines() if ":" in line]
    assert fields[:4] == ["File", "Summary", "Related Files", "Related Symbols"]
    for line in blocks[0].strip().splitlines():
        if line.split(":", 1)[0] in {"Summary", "Related Files", "Related Symbols"}:
            assert line.split(":", 1)[1].strip(), line


def imported_modules(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names = []
    for item in ast.walk(tree):
        if isinstance(item, ast.Import):
            names.extend(alias.name for alias in item.names)
        elif isinstance(item, ast.ImportFrom):
            names.append(item.module or "")
    return names


def test_V7_T8_graph_metrics_imports_no_ast():
    names = imported_modules(REPO / "analysis" / "graph_metrics.py")
    assert not [name for name in names if name == "ast" or name.startswith("ast.")]


def test_V7_F11_graph_analyzer_has_no_disk_fallback_state():
    analyzer = GraphAnalyzer()
    for name in ("_source_for_line", "_source_cache", "_tree_cache"):
        assert not hasattr(GraphAnalyzer, name), name
        assert not hasattr(analyzer, name), name


def test_V7_F12_active_packages_do_not_import_archive():
    offenders = []
    for root in (*Q5_DIRECTORIES, "contracts", "profiles", "scripts"):
        base = REPO / root
        for path in sorted(base.rglob("*.py")) if base.is_dir() else []:
            if "__pycache__" in path.parts:
                continue
            for name in imported_modules(path):
                if name.split(".")[0] in {"archive", "token_cost_disk_fallback", "graph_metrics_fallback"}:
                    offenders.append(f"{path.relative_to(REPO)}:{name}")
    assert offenders == []
