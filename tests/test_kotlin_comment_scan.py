from pathlib import Path

import pytest

from language_analyzers.kotlin import KotlinAnalyzer

LINE_RELATIONS = {'READS', 'WRITES', 'TYPE_USES', 'CALLS', 'INHERITS', 'IMPLEMENTS', 'INSTANTIATES'}
SOURCE_DIR = 'src/main/kotlin/demo'

PARAM = ['package demo', '', 'open class Base', '', 'class ProjectSymbol', '', 'class Param(val value: String)', '', 'class Result']
COUNTER = [
    'package demo',
    '',
    'class Counter {',
    '    var count: Int = 0',
    '    fun bump() {',
    '        count = count + 1',
    '    }',
    '    fun peek(): Int {',
    '        return count',
    '    }',
    '    fun load(p: Param): Result {',
    '        return Result()',
    '    }',
    '}',
    '',
    'class Holder : Base()',
]
# (from label, to label, relation, 1-based line of the reference in COUNTER)
READS_EDGE = ('peek', 'count', 'READS', 9)
WRITES_EDGE = ('bump', 'count', 'WRITES', 6)
TYPE_USES_EDGE = ('load', 'Param', 'TYPE_USES', 11)


def analyze(root, files):
    root = Path(root)
    for relative, text in files.items():
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding='utf-8')
    nodes, edges = KotlinAnalyzer(root).build()
    by_id = {node.id: node for node in nodes}
    found = []
    for edge in edges:
        if edge.from_id in by_id and edge.to_id in by_id:
            line = edge.evidence.start_line if edge.evidence is not None else None
            found.append((by_id[edge.from_id].label, by_id[edge.to_id].label, str(edge.relation), str(edge.resolution), line))
    return found


def has(edges, source, target, relation, line=None):
    return any(e[:3] == (source, target, relation) and (line is None or e[4] == line) for e in edges)


def linked(edges, source, target):
    return [e for e in edges if e[0] == source and e[1] == target]


def project_files(counter_lines, param_lines=PARAM):
    return {f'{SOURCE_DIR}/Param.kt': '\n'.join(param_lines) + '\n', f'{SOURCE_DIR}/Counter.kt': '\n'.join(counter_lines) + '\n'}


def inject(lines, inserts=(), replacements=()):
    """Comment lines go before the given 1-based line; replacements swap one line for one line. Returns (lines, line map)."""
    inserts, replacements = dict(inserts), dict(replacements)
    out = []
    for number, text in enumerate(lines, start=1):
        out.extend(inserts.get(number, []))
        out.append(replacements.get(number, text))
    assert all('\n' not in text for text in replacements.values())
    return out, lambda old: old + sum(len(c) for k, c in inserts.items() if k <= old)


STYLES = {
    'EP1-line-comment': (
        {5: ['    // bump the value and count of Param, see ProjectSymbol'], 6: ['        // value count Param Result ProjectSymbol'],
         8: ['    // peek returns count, value'], 16: ['// Holder extends Base, value ProjectSymbol']},
        {9: '        return count // value Param ProjectSymbol'}),
    'EP2-block-comment': (
        {5: ['    /* bump value count Param */'], 6: ['        /* value', '           count ProjectSymbol Result */'],
         16: ['/* Holder value Base ProjectSymbol */']},
        {11: '    fun load(p: Param /* ProjectSymbol value */): Result {', 8: '    fun peek(): Int /* count value Param */ {'}),
    'EP3-kdoc-sentence-word': (
        {5: ['    /**', '     * Bumps the count and returns the value of the Param.', '     */'],
         6: ['        /** the value and the count */'],
         8: ['    /**', '     * Reads the count; the value is not touched.', '     */'], 16: ['/** The value holder. */']},
        {}),
    'EP4-kdoc-link': (
        {5: ['    /**', '     * See [ProjectSymbol], [Param.value] and [Counter.count].', '     */'],
         6: ['        /** [value] [Param] */'],
         11: ['    /** Loads a [Param] into a [Result] using [value]. */'], 16: ['/** [Holder] is a [ProjectSymbol]. */']},
        {}),
}


@pytest.fixture(scope='module')
def plain_edges(tmp_path_factory):
    return analyze(tmp_path_factory.mktemp('plain'), project_files(COUNTER))


@pytest.mark.parametrize('edge, ep', [(READS_EDGE, 'EP5'), (WRITES_EDGE, 'EP6'), (TYPE_USES_EDGE, 'EP7')])
def test_V11_reference_edges_exist_outside_comments(plain_edges, edge, ep):
    source, target, relation, line = edge
    assert has(plain_edges, source, target, relation, line), (ep, plain_edges)


@pytest.mark.parametrize('style', list(STYLES))
def test_V11_adding_comments_leaves_the_edge_set_unchanged(tmp_path, plain_edges, style):
    inserts, replacements = STYLES[style]
    lines, remap = inject(COUNTER, inserts, replacements)
    assert len(lines) > len(COUNTER) or replacements
    commented = analyze(tmp_path, project_files(lines))
    strip = lambda edges: sorted((e[:4] for e in edges), key=str)
    assert strip(commented) == strip(plain_edges)
    shifted = sorted((e[:4] + (remap(e[4]),) for e in plain_edges if e[2] in LINE_RELATIONS and e[4] is not None and e[0] in
                      {'bump', 'peek', 'load', 'Holder', 'Counter'}), key=str)
    kept = sorted((e for e in commented if e[2] in LINE_RELATIONS and e[0] in {'bump', 'peek', 'load', 'Holder', 'Counter'}), key=str)
    assert kept == shifted


@pytest.mark.parametrize('style', list(STYLES))
def test_V11_EP5_EP6_EP7_reference_edges_keep_their_relation_and_shifted_line_under_comments(tmp_path, style):
    inserts, replacements = STYLES[style]
    lines, remap = inject(COUNTER, inserts, replacements)
    commented = analyze(tmp_path, project_files(lines))
    for source, target, relation, line in (READS_EDGE, WRITES_EDGE, TYPE_USES_EDGE):
        assert has(commented, source, target, relation, remap(line)), (style, source, target, remap(line), commented)


# ------------------------------------------------------------------ V12 comment boundaries

HEAD = ['package g', 'class Param(val value: String)']
K_OPEN = ['class K {', '    var total: Int = 0']


def scan(tmp_path, lines, trailing_newline=True):
    text = '\n'.join(lines) + ('\n' if trailing_newline else '')
    return analyze(tmp_path, {'src/main/kotlin/g/G.kt': text})


def test_V12_G1_double_slash_inside_a_string_is_not_a_comment(tmp_path):
    edges = scan(tmp_path, [*HEAD, *K_OPEN, '    fun a(): Int {', '        val n = "// not a comment value" + total',
                            '        return n.length', '    }', '}'])
    assert has(edges, 'a', 'total', 'READS', 6)
    assert has(edges, 'a', 'value', 'READS')


def test_V12_G2_block_comment_opener_inside_a_string_does_not_hide_later_code(tmp_path):
    edges = scan(tmp_path, [*HEAD, *K_OPEN, '    fun a(): Int {', '        val s = "/* open"', '        return total', '    }',
                            '    fun b(): Int = total', '}'])
    assert has(edges, 'a', 'total', 'READS', 7)
    assert has(edges, 'b', 'total', 'READS', 9)


def test_V12_G3_nested_block_comment_is_one_comment(tmp_path):
    edges = scan(tmp_path, [*HEAD, *K_OPEN, '    fun f() {', '        /* a /* value */ total */', '        val x = 1', '    }',
                            '    fun g(): Int {', '        return total', '    }', '}'])
    assert linked(edges, 'f', 'value') == [] and linked(edges, 'f', 'total') == []
    assert has(edges, 'g', 'total', 'READS', 10)


def test_V12_G4_trailing_comment_keeps_the_call_and_hides_the_name(tmp_path):
    edges = scan(tmp_path, ['package g', 'class Param(val value: String)', 'fun foo() {}', 'fun a() {', '    foo() // value', '}'])
    assert has(edges, 'a', 'foo', 'CALLS', 5)
    assert linked(edges, 'a', 'value') == []


def test_V12_G5_block_comment_inside_a_class_header_hides_the_name_and_keeps_the_supertype(tmp_path):
    edges = scan(tmp_path, ['package g', 'open class C', 'class B', 'class A /* B */ : C()'])
    assert any(e[0] == 'A' and e[1] == 'C' and e[2] in ('INHERITS', 'IMPLEMENTS') for e in edges)
    assert linked(edges, 'A', 'B') == []


def test_V12_G6_comments_on_first_and_last_line_without_final_newline(tmp_path):
    edges = scan(tmp_path, ['// first Param value', 'package g', 'class Param(val value: String)', 'class K {',
                            '    var total: Int = 0', '    fun a(): Int = total // Param value', '}// Param value'],
                 trailing_newline=False)
    assert has(edges, 'a', 'total', 'READS', 6)
    assert linked(edges, 'a', 'value') == [] and linked(edges, 'a', 'Param') == []


def test_V12_G7_multi_byte_characters_inside_comments_do_not_shift_later_offsets(tmp_path):
    edges = scan(tmp_path, [*HEAD, *K_OPEN, '    /* \ud55c\uae00 \u65e5\u672c\u8a9e \u00e9 \U0001F600 value Param */',
                            '    fun a(): Int = total', '    fun b(): Int {',
                            '        /* \ud55c\uae00 \U0001F600 value */ return total', '    }', '}'])
    assert has(edges, 'a', 'total', 'READS', 6)
    assert has(edges, 'b', 'total', 'READS', 8)
    for name in ('a', 'b'):
        assert linked(edges, name, 'value') == [] and linked(edges, name, 'Param') == []
