"""V10 / Q03: existing architecture (schema 5, 6) and bottleneck (v4, v5) inputs still render without page errors."""
import pytest

from tests.report_redesign_support import SEL, build_report, make_file, row_ids, tab, tab_active, goto_list
from tests.unified_support import architecture, bottleneck_fixture, edge, node

PATHS = ['app/ui/Home.py', 'app/data/Dao.py']


def symbol_inputs(tmp_path):
    nodes = [node('a', value=3), node('b', value=2)]
    edges = [edge('a', 'b')]
    return architecture(nodes, edges), bottleneck_fixture(tmp_path, nodes, edges, candidate_count=1)


def file_inputs():
    files = [make_file(p, {'pagerank': i + 2}) for i, p in enumerate(PATHS)]
    return build_report(files, [(PATHS[0], PATHS[1], 'CALLS', 'static_certain', 'exact', 5)])


@pytest.mark.parametrize('case', ['arch5+bn4', 'arch5-only', 'bn4-only', 'arch6+bn5', 'arch6-only', 'bn5-only'])
def test_V10_existing_inputs_render_without_page_errors(open_report, tmp_path, case):
    arch5, bn4 = symbol_inputs(tmp_path)
    arch6, bn5 = file_inputs()
    arch, bn = {'arch5+bn4': (arch5, bn4), 'arch5-only': (arch5, None), 'bn4-only': (None, bn4),
                'arch6+bn5': (arch6, bn5), 'arch6-only': (arch6, None), 'bn5-only': (None, bn5)}[case]
    page = open_report(arch, bn)
    if not tab(page, '목록').is_disabled() and not tab_active(page, '목록'):
        goto_list(page)
    assert page.locator(SEL['card_group']).count() == 6
    expected = {'arch5': {'a', 'b'}, 'arch6': {'file:' + p for p in PATHS}, 'bn4': {'a', 'b'}, 'bn5': {'file:' + p for p in PATHS}}[case.split('+')[0].split('-')[0]]
    assert set(row_ids(page)) == expected
    assert page.unhandled_errors == []
