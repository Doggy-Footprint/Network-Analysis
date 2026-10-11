import copy
import json
import re

import pytest
from playwright.sync_api import expect

from report.shared.document import ReportInputError
from bottlenecks import BottleneckInputError
from tests.candidate_policy_metadata_support import DEFAULT_TABLES
from tests.unified_support import architecture, bottleneck_fixture, document, edge, node
from tests.file_analysis_browser_support import file_arch, file_node, symbol
from tests.report_redesign_support import dialog, goto_list, has_number


def ambiguous(source='s', target='a', others=('b',), line=5):
    e = edge(source, target, resolution='ambiguous', line=line)
    e['candidates'] = list(others)
    e['weight'] = 87
    return e


@pytest.mark.parametrize('mode', ['architecture-only', 'report-only', 'combined'])
def test_VO6_supported_payload_shapes(tmp_path, mode):
    arch = architecture([node('a')])
    report = bottleneck_fixture(tmp_path, arch['nodes'], candidate_count=0)
    html = document(None if mode == 'report-only' else arch, None if mode == 'architecture-only' else report)
    decoded = json.loads(re.search(r'<script[^>]*id="report-data"[^>]*>(.*?)</script>', html, re.S).group(1))
    assert decoded['architecture'] == (None if mode == 'report-only' else arch)
    assert decoded['bottlenecks'] == (None if mode == 'architecture-only' else report)


@pytest.mark.parametrize('component,policy,combined', [
    ('architecture', None, False), ('architecture', 'old', False),
    ('report', None, False), ('report', 'old', False),
    ('architecture', None, True), ('architecture', 'old', True),
    ('report', None, True), ('report', 'old', True),
])
def test_VO6_generation_policy_rejections(tmp_path, component, policy, combined):
    arch = architecture([node('a')])
    report = bottleneck_fixture(tmp_path, arch['nodes'], candidate_count=0)
    section = arch['stats']['analysis'] if component == 'architecture' else report['dependency_network']
    if policy is None:
        section.pop('ambiguity_policy')
    else:
        section['ambiguity_policy'] = policy
    with pytest.raises(ReportInputError):
        document(arch if combined or component == 'architecture' else None, report if combined or component == 'report' else None)


def test_VO6_unknown_candidate_generation_rejected():
    arch = architecture([node('s'), node('a')], [ambiguous(others=('ghost',))])
    with pytest.raises(BottleneckInputError):
        document(arch)


@pytest.mark.parametrize('component,policy', [('architecture', None), ('architecture', 'old'), ('bottlenecks', None), ('bottlenecks', 'old')])
def test_VO6_injected_policy_loader_error(open_report, tmp_path, component, policy):
    arch = architecture([node('a')])
    report = bottleneck_fixture(tmp_path, arch['nodes'], candidate_count=0)
    html = document(arch, report)
    match = re.search(r'(<script[^>]*id="report-data"[^>]*>)(.*?)(</script>)', html, re.S)
    data = json.loads(match.group(2))
    section = data[component]['stats']['analysis'] if component == 'architecture' else data[component]['dependency_network']
    if policy is None:
        section.pop('ambiguity_policy')
    else:
        section['ambiguity_policy'] = policy
    html = html[:match.start(2)] + json.dumps(data) + html[match.end(2):]
    page = open_report(None, html=html)
    expect(page.locator('#report-status')).to_be_visible()
    assert page.locator('#report-status').inner_text().strip()
    assert page.locator('[data-node-row]').count() == 0
    assert page.evaluate('window.ReportGraph == null')


def test_VO5_modal_top_ten_ranks_ambiguous_file_share_at_cutoff(open_report):
    """Rewritten for the modal (A06): allocation text is gone, but the share-weighted effective weight still decides the top-10 cut."""
    letters = 'ABCDEFGHI'
    paths = ['src/Src.py', 'src/Bee.py', 'src/Cee.py'] + [f'src/Fil{c}.py' for c in letters]
    originals = [symbol('s', 'src/Src.py'), symbol('a', 'src/Bee.py'), symbol('b', 'src/Bee.py'), symbol('c', 'src/Cee.py')]
    originals += [symbol(f'f{c}', f'src/Fil{c}.py') for c in letters]
    relations = [ambiguous(others=('b', 'c'))] + [edge('s', f'f{c}', confidence='framework_inferred') for c in letters]
    arch = file_arch([file_node(p) for p in paths], originals, relations)
    shares = {e['to_id']: e['metadata']['candidate_share'] for e in arch['edges'] if e['resolution'] == 'ambiguous'}
    assert shares == {'file:src/Bee.py': pytest.approx(2 / 3), 'file:src/Cee.py': pytest.approx(1 / 3)}
    arch['stats']['analysis']['edge_weights'] = copy.deepcopy(DEFAULT_TABLES)
    arch['stats']['analysis']['edge_weights']['confidence']['framework_inferred'] = .15
    page = open_report(arch)
    goto_list(page)
    page.locator('#node-list [data-node-row="file:src/Src.py"] [data-node-id]').first.click()
    expect(dialog(page)).to_be_visible()
    text = dialog(page).inner_text()
    # effective weights: Bee 0.3*2/3=0.2, nine fillers 0.15, Cee 0.3*1/3=0.1 -> eleven neighbours, Cee is cut
    assert 'Bee' in text and 'Cee' not in text and all(f'Fil{c}' in text for c in letters)
    assert has_number(text, 11)
    assert page.unhandled_errors == []
