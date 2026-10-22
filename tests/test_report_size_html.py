"""Spec ee17484a52af182c v1: V06 scenarios S1-S5 for the HTML embed (F09). The inputs are bottlenecks.v9 payloads (the
F02-F05 encoding of the hand-built browser fixtures); expectations are the ones the pre-change browser tests derive by hand."""
import copy
import json
import re

import pytest

from report.unified import render_unified_report
from tests.report_size_support import as_v9, inline_data, cli_fixture_run
from tests.test_report_layers import CASES, GENERIC
from tests.report_redesign_support import build_report, file_id, make_file
from tests.test_structure_panel_browser import (PANEL, area_text, button, clicked, ids, report, standard_candidates, standard_delta)


def embed(arch, bn):
    html = render_unified_report(arch, bn)
    return json.loads(re.search(r'<script[^>]*id="report-data"[^>]*>(.*?)</script>', html, re.S).group(1))


@pytest.fixture
def v9_standard(open_report):
    arch, bn = report(standard_candidates(), standard_delta())
    bn = as_v9(bn)
    assert bn['schema'] == 'bottlenecks.v9'
    package = next(c for c in bn['candidates'] if c['kind'] == 'package_cycle')
    assert all(type(a) is int and type(b) is int for row in package['evidence'] for a, b in row[6])
    return open_report(arch, bn)


def test_V06_S1_embedded_architecture_has_no_details_and_the_input_keeps_them():
    arch, bn = report(standard_candidates(), standard_delta())
    assert 'details' in arch
    before = copy.deepcopy(arch)
    data = embed(arch, as_v9(bn))
    assert 'details' not in data['architecture']
    assert arch == before


def test_V06_S1_cli_html_embeds_no_details_while_the_details_file_has_them(tmp_path):
    directory = cli_fixture_run(tmp_path)
    assert 'details' not in inline_data(directory / 'report.html')['architecture']
    assert json.loads((directory / 'report.details.json').read_text(encoding='utf-8'))['nodes']


@pytest.mark.parametrize('case', CASES, ids=str)
def test_V06_S2_embedded_layers_equal_the_hand_derived_layers(case):
    framework, roles, expected, details = CASES[case]
    files = [make_file(path) for path in roles]
    arch, bn = build_report(files, roles=roles, framework=framework, details=details, generic=GENERIC.get(case))
    layers = embed(arch, as_v9(bn))['layers']
    assert {k: v for k, v in layers.items() if k in {file_id(p) for p in expected}} == {
        file_id(path): {'layer': layer, 'source': source} for path, (layer, source) in expected.items()}


def test_V06_S3_package_cycle_click_selects_the_files_of_its_v9_file_pairs(v9_standard):
    assert clicked(v9_standard, button(v9_standard, 'cycles', 'package_cycle')) == [(ids('a', 'b', 'e'), '3개 파일 강조')]


def test_V06_S4_dependency_cycle_click_selects_its_members(v9_standard):
    results = clicked(v9_standard, button(v9_standard, 'cycles', 'dependency_cycle'))
    assert {tuple(r[0]): r[1] for r in results}[tuple(ids('a', 'b', 'c', 'd'))] == '4개 파일 강조'


def test_V06_S5_rule_violation_wording_and_destination_use_to_id(v9_standard):
    page = v9_standard
    assert 'db → api · 금지 규칙' in area_text(page, 'violations')
    internal = page.locator(f'{PANEL["violations"]} button[data-structure-kind]:has-text("db → api")')
    assert clicked(page, internal) == [(ids('a', 'b'), '2개 파일 강조')]
