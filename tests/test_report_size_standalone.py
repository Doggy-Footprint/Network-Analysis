"""Spec ee17484a52af182c v3: V11 (F15, C19) the standalone `python -m report.bottlenecks.generate` / `render_report` accept
bottlenecks.v9 and still accept v8. Inputs: the v8 golden written by the base commit, and the v9 file the CLI wrote."""
import json
import re
import subprocess
import sys

import pytest

from report.bottlenecks import render_report
from tests.report_size_support import REPO, cli_fixture_run, golden, to_v9_payload

V8 = golden('v8_bottlenecks.json')


@pytest.fixture(scope='module')
def cli_v9(tmp_path_factory):
    directory = cli_fixture_run(tmp_path_factory.mktemp('v11'))
    return directory / 'bn' / 'b.json'


def generate(source, output):
    return subprocess.run([sys.executable, '-m', 'report.bottlenecks.generate', str(source), '-o', str(output)], cwd=REPO,
                          capture_output=True, text=True)


def embedded(html):
    found = re.search(r'<script[^>]*id="report-data"[^>]*>(.*?)</script>', html, re.S)
    assert found
    return json.loads(found.group(1))


def test_V11_C19_cli_accepts_the_v9_file_the_main_cli_wrote(cli_v9, tmp_path):
    assert json.loads(cli_v9.read_text(encoding='utf-8'))['schema'] == 'bottlenecks.v9'
    done = generate(cli_v9, tmp_path / 'v9.html')
    assert done.returncode == 0, done.stderr[-1500:]
    html = (tmp_path / 'v9.html').read_text(encoding='utf-8')
    assert '<html' in html.lower()
    assert {c['kind'] for c in embedded(html)['bottlenecks']['candidates']} >= {'dependency_cycle', 'package_cycle', 'unstable_dependency', 'evidence_spread'}


def test_V11_C19_cli_still_accepts_the_v8_golden(tmp_path):
    source = tmp_path / 'v8.json'
    source.write_text(json.dumps(V8), encoding='utf-8')
    done = generate(source, tmp_path / 'v8.html')
    assert done.returncode == 0, done.stderr[-1500:]
    assert '<html' in (tmp_path / 'v8.html').read_text(encoding='utf-8').lower()


@pytest.mark.parametrize('schema', ['v8', 'v9'])
def test_V11_render_report_accepts_both_schemas_without_validation_errors(schema):
    payload = V8 if schema == 'v8' else to_v9_payload(V8)
    assert payload['schema'] == f'bottlenecks.{schema}'
    html = render_report(payload)
    assert '<html' in html.lower()
    assert len(embedded(html)['bottlenecks']['candidates']) == len(V8['candidates'])


def test_V11_v9_package_cycle_file_list_decodes_through_file_ids():
    payload = to_v9_payload(V8)
    package = next(c for c in payload['candidates'] if c['kind'] == 'package_cycle')
    assert all(type(a) is int for row in package['evidence'] for pair in row[6] for a in pair)
    data = embedded(render_report(payload))
    shown = next(c for c in data['bottlenecks']['candidates'] if c['id'] == package['id'])
    assert shown['evidence'] == package['evidence']
    assert data['bottlenecks']['dependency_network']['file_ids'] == payload['dependency_network']['file_ids']


def open_page(chromium, path):
    context = chromium.new_context(viewport={'width': 1440, 'height': 900})
    context.set_default_timeout(5000)
    context.route('http://**/*', lambda route: route.abort())
    context.route('https://**/*', lambda route: route.abort())
    errors = []
    page = context.new_page()
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.goto(path.as_uri())
    return context, page, errors


# file_ids of the golden project, sorted (hand-written): index -> path
HAND_FILE_IDS = ['file:app/__init__.py', 'file:app/main.py', 'file:core/__init__.py', 'file:core/engine.py', 'file:core/registry.py',
                 'file:util/__init__.py', 'file:util/helpers.py', 'file:web/__init__.py', 'file:web/extra.py', 'file:web/views.py']


def test_V11_F05_standalone_v9_page_package_cycle_item_opens_the_file_its_pairs_name(chromium, tmp_path):
    """Hand-derived: index 8 is web/extra.py and 9 is web/views.py in the sorted file_ids, so a package_cycle whose file_pairs are
    [[8, 9]] must open web/extra.py (first of its files) and none of the golden package files."""
    payload = to_v9_payload(V8)
    assert payload['dependency_network']['file_ids'] == HAND_FILE_IDS
    for item in payload['candidates']:
        if item['kind'] == 'package_cycle':
            for row in item['evidence']:
                row[6] = [[8, 9]]
    source = tmp_path / 'v9.json'
    source.write_text(json.dumps(payload), encoding='utf-8')
    done = generate(source, tmp_path / 'v9.html')
    assert done.returncode == 0, done.stderr[-1500:]
    context, page, errors = open_page(chromium, tmp_path / 'v9.html')
    try:
        buttons = page.locator('#structure-section button[data-structure-kind="package_cycle"]')
        assert buttons.count() == len([c for c in V8['candidates'] if c['kind'] == 'package_cycle' and c['structure']['tier'] == 'all'])
        buttons.first.click()
        dialog = page.locator('[role=dialog]')
        dialog.wait_for(state='visible')
        text = dialog.inner_text()
        assert 'web/extra.py' in text
        assert 'web/views.py' not in text and 'core/engine.py' not in text and 'util/helpers.py' not in text
        assert errors == []
    finally:
        context.close()


def test_V11_F05_standalone_v9_page_from_the_cli_file_opens_a_package_cycle_file_and_has_no_page_errors(chromium, cli_v9, tmp_path):
    assert generate(cli_v9, tmp_path / 'cli.html').returncode == 0
    context, page, errors = open_page(chromium, tmp_path / 'cli.html')
    try:
        buttons = page.locator('#structure-section button[data-structure-kind="package_cycle"]')
        assert buttons.count() == len([c for c in V8['candidates'] if c['kind'] == 'package_cycle' and c['structure']['tier'] == 'all'])
        buttons.first.click()
        page.locator('[role=dialog]').wait_for(state='visible')
        text = page.locator('[role=dialog]').inner_text()
        # the package_cycle of the fixture is core <-> util: its first file (sorted) is core/engine.py
        assert 'core/engine.py' in text and 'web/' not in text and 'app/' not in text
        assert errors == []
    finally:
        context.close()


def test_V11_F05_standalone_v8_golden_page_renders_without_errors_and_opens_the_same_first_file(chromium, tmp_path):
    source = tmp_path / 'v8.json'
    source.write_text(json.dumps(V8), encoding='utf-8')
    assert generate(source, tmp_path / 'v8.html').returncode == 0
    context, page, errors = open_page(chromium, tmp_path / 'v8.html')
    try:
        kinds = [b.get_attribute('data-structure-kind') for b in page.locator('#structure-section button[data-structure-kind]').all()]
        assert kinds.count('package_cycle') == len([c for c in V8['candidates'] if c['kind'] == 'package_cycle' and c['structure']['tier'] == 'all'])
        assert kinds.count('dependency_cycle') == len([c for c in V8['candidates'] if c['kind'] == 'dependency_cycle' and c['structure']['tier'] == 'all'])
        page.locator('#structure-section button[data-structure-kind="package_cycle"]').first.click()
        page.locator('[role=dialog]').wait_for(state='visible')
        assert 'core/engine.py' in page.locator('[role=dialog]').inner_text()
        assert errors == []
    finally:
        context.close()
