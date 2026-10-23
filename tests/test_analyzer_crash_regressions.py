"""Spec 3974b0fa12e686e6 v1: regressions for the three analyzer crashes.

Expected values are computed from fixture text and the spec, never from analyzer output.
"""

import json
import re
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent

OLD_RETROFIT_ID = re.compile(r'"retrofit_[A-Za-z0-9]+_[A-Za-z0-9]+"')
NEW_RETROFIT_ID = re.compile(r'"retrofit_[^"]*\.kt_[A-Za-z0-9]+_[A-Za-z0-9]+_[0-9]+"')


def write_files(root, files):
    for name, source in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source, encoding="utf-8")


def git_init(root, files):
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "add", *files], cwd=root, check=True)


# ---------------------------------------------------------------- V1

def python_nodes(tmp_path):
    from language_analyzers.python.graph import PythonGraphAnalyzer
    architecture = PythonGraphAnalyzer(tmp_path).analyze()
    return {node.id: node for node in architecture.nodes}


V1_CASES = {
    "P1_function_general": (
        'def f():\n    """Load users.\n\n    Details.\n    """\n    return 1\n', "py:mod#f", "Load users."),
    "P2_function_newline_indent": (
        'def f():\n    """\n    """\n    return 1\n', "py:mod#f", None),
    "P3_class_newline_indent": (
        'class K:\n    """\n    """\n    x = 1\n', "py:mod#K", None),
    "P4_module_whitespace": (
        '"""\n   """\nX = 1\n', "py:mod", None),
    "P5_blank_line_then_text": (
        'def f():\n    """\n\n    Text\n    """\n    return 1\n', "py:mod#f", "Text"),
    "P6_no_docstring": (
        'def f():\n    return 1\n', "py:mod#f", None),
}


@pytest.mark.parametrize("case", list(V1_CASES))
def test_V1_docstring_partitions(tmp_path, case):
    source, node_id, expected = V1_CASES[case]
    (tmp_path / "mod.py").write_text(source, encoding="utf-8")

    nodes = python_nodes(tmp_path)

    assert node_id in nodes
    assert nodes[node_id].docstring == expected


# ---------------------------------------------------------------- V2

def test_V2_E1_cli_fastapi_with_whitespace_docstring(tmp_path):
    files = {
        "main.py": (
            "from fastapi import FastAPI\n\napp = FastAPI()\n\n\n"
            "def helper():\n    \"\"\"\n    \"\"\"\n    return 1\n\n\n"
            "@app.get('/users')\ndef users():\n    return helper()\n"
        ),
    }
    write_files(tmp_path, files)
    git_init(tmp_path, files)
    html, bottlenecks = tmp_path / "a.html", tmp_path / "b.json"

    result = subprocess.run(
        [sys.executable, "-m", "code_analyzer.cli", str(tmp_path), "-f", "fastapi",
         "-o", str(html), "--bottlenecks", str(bottlenecks)],
        cwd=REPO, capture_output=True, text=True, timeout=300)

    assert result.returncode == 0, result.stderr
    assert html.exists() and bottlenecks.exists()


# ---------------------------------------------------------------- V3

NEST_RUNNER = textwrap.dedent('''
    import json, sys
    from framework_analyzers.nestjs import NestJSAnalyzer
    arch = NestJSAnalyzer(sys.argv[1]).analyze()
    span = lambda s: [s.file_path, s.start_line, s.end_line, s.start_col, s.end_col]
    print(json.dumps({
        "diagnostics": [[d.code, d.expression, span(d.span)] for d in arch.diagnostics],
        "declarations": [[d.kind, d.name, span(d.span)] for d in arch.declarations],
    }))
''')

DIAGNOSTIC_COLUMNS = {"B1": 255, "B2": 256, "B3": 257, "B4": 1000}


def padded_reference_file(token, column):
    prefix = f"export class S{token} {{ constructor("
    tail = "private a: "
    pad = column - len(prefix) - len(tail)
    assert pad >= 0
    line = prefix + " " * pad + tail + f"{token}) {{}} }}"
    assert line.index(token, len(prefix)) == column
    source = (
        "import { Injectable } from '@nestjs/common';\n"
        f"import {{ {token} }} from './missing';\n"
        "@Injectable()\n"
        f"{line}\n"
    )
    return source, 4, line


def nest_fixture():
    files, expected = {}, {}
    for item, column in DIAGNOSTIC_COLUMNS.items():
        token = f"Ref{item}"
        source, line_number, line = padded_reference_file(token, column)
        files[f"diag_{item}.ts"] = source
        expected[f"diag_{item}.ts"] = (item, token, line_number, column)

    ctl_decorator_col = 257
    ctl_prefix = " " * ctl_decorator_col
    ctl_lines = [
        "import { Controller, Get, Module } from '@nestjs/common';",
        "@Controller()",
        "export class Ctl {",
        ctl_prefix + "@Get() m() {}",
        "}",
    ]
    ctl_line_number = 4
    assert ctl_lines[ctl_line_number - 1].index("@Get") == ctl_decorator_col
    files["ctl.ts"] = "\n".join(ctl_lines) + "\n"

    app_prefix = "async function boot() { const app = await "
    app_pad = " " * (300 - len(app_prefix))
    app_line = app_prefix + app_pad + "NestFactory.create(AppModule); }"
    app_col = app_line.index("NestFactory.create")
    assert app_col == 300
    files["main.ts"] = (
        "import { NestFactory } from '@nestjs/core';\n"
        "import { Module } from '@nestjs/common';\n"
        "@Module({})\nexport class AppModule {}\n"
        + app_line + "\n"
    )
    app_line_number = 5
    return files, expected, (ctl_line_number, ctl_decorator_col), (app_line_number, app_col)


@pytest.fixture(scope="module")
def nest_run(tmp_path_factory):
    root = tmp_path_factory.mktemp("nest_columns")
    files, expected, endpoint, application = nest_fixture()
    write_files(root, files)
    result = subprocess.run([sys.executable, "-c", NEST_RUNNER, str(root)],
                            cwd=REPO, capture_output=True, text=True, timeout=300)
    return result, expected, endpoint, application


def nest_output(nest_run):
    result = nest_run[0]
    assert result.returncode == 0, (result.returncode, result.stderr[-2000:])
    return json.loads(result.stdout)


def test_V3_subprocess_exits_zero(nest_run):
    assert nest_run[0].returncode == 0, (nest_run[0].returncode, nest_run[0].stderr[-2000:])


@pytest.mark.parametrize("item", list(DIAGNOSTIC_COLUMNS))
def test_V3_diagnostic_start_column_boundary(nest_run, item):
    output = nest_output(nest_run)
    expected = nest_run[1][f"diag_{item}.ts"]
    token, line_number, column = expected[1], expected[2], expected[3]
    assert column == DIAGNOSTIC_COLUMNS[item]

    found = [d for d in output["diagnostics"]
             if d[0] == "unresolved_reference" and d[2][0] == f"diag_{item}.ts" and d[1] == token]

    assert len(found) == 1
    _, _, (_, start_line, end_line, start_col, _end_col) = found[0]
    assert (start_line, end_line, start_col) == (line_number, line_number, column)


@pytest.mark.parametrize("item", list(DIAGNOSTIC_COLUMNS))
def test_V3_B5_diagnostic_end_column_above_256(nest_run, item):
    output = nest_output(nest_run)
    token, column = f"Ref{item}", DIAGNOSTIC_COLUMNS[item]
    found = [d for d in output["diagnostics"]
             if d[0] == "unresolved_reference" and d[2][0] == f"diag_{item}.ts" and d[1] == token]

    assert len(found) == 1
    end_col = found[0][2][4]
    assert end_col == column + len(token)
    assert end_col > 256


def test_V3_B6_endpoint_identifier_column(nest_run):
    output = nest_output(nest_run)
    line_number, column = nest_run[2]

    names = [d[1] for d in output["declarations"] if d[0] == "endpoint"]

    assert names == [f"Ctl.m@{line_number}:{column}"]


def test_V3_B7_application_identifier_column(nest_run):
    output = nest_output(nest_run)
    line_number, column = nest_run[3]

    names = [d[1] for d in output["declarations"] if d[0] == "application"]

    assert names == [f"NestFactory.create@{line_number}:{column}"]


def declaration_spans(nest_run, kind):
    output = nest_output(nest_run)
    spans = [d[2] for d in output["declarations"] if d[0] == kind]
    assert len(spans) == 1
    return spans[0]


def test_V3_B8_endpoint_declaration_span_is_the_decorator(nest_run):
    line_number, column = nest_run[2]
    decorator = "@Get()"
    end_col = column + len(decorator)

    span = declaration_spans(nest_run, "endpoint")

    assert span[1:] == [line_number, line_number, column, end_col]
    assert end_col > 256 and end_col != column


def test_V3_B9_application_declaration_span_is_the_create_call(nest_run):
    line_number, column = nest_run[3]
    call = "NestFactory.create(AppModule)"
    end_col = column + len(call)

    span = declaration_spans(nest_run, "application")

    assert span[1:] == [line_number, line_number, column, end_col]
    assert end_col > 256 and end_col != column


# ---------------------------------------------------------------- V4

def retrofit_ids(project):
    from framework_analyzers.android.analyzer import AndroidAnalyzer
    architecture = AndroidAnalyzer(str(project)).analyze()
    return {(api.name, e.name, e.line_number): e.id for api in architecture.retrofit_apis for e in api.endpoints}, \
        [e.id for api in architecture.retrofit_apis for e in api.endpoints]


def kotlin_api(interface, methods):
    lines = ["package sample", "import retrofit2.http.GET", "import retrofit2.Call", f"interface {interface} {{"]
    for name, parameter in methods:
        lines.append(f'    @GET("x") fun {name}({parameter}): Call<String>')
    lines.append("}")
    return "\n".join(lines) + "\n"


def test_V4_R1_single_interface_two_methods(tmp_path):
    path = "app/src/Api.kt"
    write_files(tmp_path, {path: kotlin_api("Api", [("first", ""), ("second", "")])})

    _, ids = retrofit_ids(tmp_path)

    assert sorted(ids) == sorted([f"retrofit_{path}_Api_first_5", f"retrofit_{path}_Api_second_6"])


def test_V4_R2_same_interface_and_method_in_two_files(tmp_path):
    path_a, path_b = "moda/Api.kt", "modb/Api.kt"
    source = kotlin_api("Api", [("get", "")])
    write_files(tmp_path, {path_a: source, path_b: source})

    _, ids = retrofit_ids(tmp_path)

    assert sorted(ids) == sorted([f"retrofit_{path_a}_Api_get_5", f"retrofit_{path_b}_Api_get_5"])
    assert len(set(ids)) == len(ids) == 2


def test_V4_R3_cli_android_bottlenecks_with_duplicate_interfaces(tmp_path):
    source = kotlin_api("Api", [("get", "")])
    files = {"moda/Api.kt": source, "modb/Api.kt": source}
    write_files(tmp_path, files)
    git_init(tmp_path, files)

    result = subprocess.run(
        [sys.executable, "-m", "code_analyzer.cli", str(tmp_path), "-f", "android",
         "-o", str(tmp_path / "a.html"), "--bottlenecks", str(tmp_path / "b.json")],
        cwd=REPO, capture_output=True, text=True, timeout=300)

    assert result.returncode == 0, result.stderr
    assert "architecture node ids are invalid" not in result.stderr + result.stdout
    assert (tmp_path / "b.json").exists()


def test_V4_R4_overloaded_methods_differ_by_line(tmp_path):
    path = "Api.kt"
    write_files(tmp_path, {path: kotlin_api("Api", [("get", "a: Int"), ("get", "a: String")])})

    _, ids = retrofit_ids(tmp_path)

    assert sorted(ids) == sorted([f"retrofit_{path}_Api_get_5", f"retrofit_{path}_Api_get_6"])


def test_V4_R5_annotation_on_line_above_fun_uses_annotation_line(tmp_path):
    path = "Api.kt"
    source = (
        "package sample\n"
        "import retrofit2.http.GET\n"
        "import retrofit2.Call\n"
        "interface Api {\n"
        '    @GET("x")\n'
        "    fun get(): Call<String>\n"
        "}\n"
    )
    assert source.splitlines()[4].lstrip().startswith("@GET")
    write_files(tmp_path, {path: source})

    _, ids = retrofit_ids(tmp_path)

    assert ids == [f"retrofit_{path}_Api_get_5"]


# ---------------------------------------------------------------- V5

POINT_ATTRIBUTE = re.compile(r"(start|end)_point\s*\.\s*(row|column)\b")
POINT_PATTERN_EXAMPLES = {
    "G1": "node.start_point.column", "G2": "node.end_point.column",
    "G3": "node.start_point.row", "G4": "node.end_point.row",
}


@pytest.mark.parametrize("item", list(POINT_PATTERN_EXAMPLES))
def test_V5_pattern_detects_each_attribute_form(item):
    assert POINT_ATTRIBUTE.search(POINT_PATTERN_EXAMPLES[item])
    spaced = POINT_PATTERN_EXAMPLES[item].replace(".", " . ")
    assert POINT_ATTRIBUTE.search(spaced)


def test_V5_pattern_allows_index_access():
    assert not POINT_ATTRIBUTE.search("node.start_point[1]")


def test_V5_no_point_attribute_access_outside_tests():
    tracked = subprocess.run(["git", "ls-files", "*.py"], cwd=REPO, capture_output=True, text=True, check=True).stdout.split()
    violations = []
    for name in tracked:
        if name.startswith("tests/"):
            continue
        path = REPO / name
        if not path.is_file():
            continue
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if POINT_ATTRIBUTE.search(line):
                violations.append(f"{name}:{number}: {line.strip()}")

    assert not violations, "\n".join(violations)


# ---------------------------------------------------------------- V6

GOLDENS = {
    "tests/coverage_reporting_evidence/characterization-baseline.json":
        ("retrofit_src/Screen.kt_Api_users_9", "Api_users"),
    "tests/file_analysis_evidence/direct-api-original.json":
        ("retrofit_core_network/src/main/kotlin/com/example/core/network/UserApi.kt_UserApi_getUser_7",
         "UserApi_getUser"),
}


@pytest.mark.parametrize("golden", list(GOLDENS))
def test_V6_J1_no_old_format_retrofit_ids(golden):
    text = (REPO / golden).read_text(encoding="utf-8")

    assert not OLD_RETROFIT_ID.findall(text.replace('"retrofit_api"', "").replace('"retrofit_apis"', "")
                                       .replace('"retrofit_endpoint"', "").replace('"total_retrofit_apis"', ""))
    assert f'"retrofit_{GOLDENS[golden][1]}"' not in text


@pytest.mark.parametrize("golden", list(GOLDENS))
def test_V6_J2_new_format_retrofit_ids_present(golden):
    text = (REPO / golden).read_text(encoding="utf-8")
    new_id = GOLDENS[golden][0]

    assert f'"id": "{new_id}"' in text
    assert NEW_RETROFIT_ID.search(text)
