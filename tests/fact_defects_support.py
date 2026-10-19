"""Spec 7ab6320d2eb56ccf v1 support. Every oracle here is written from the spec text and uses a different algorithm
from the product (character scan instead of split, explicit candidate list instead of suffix handling); none of it
reads product output to derive an expected value."""
import json
import posixpath
import sys
from pathlib import Path

import pytest

from language_analyzers.core.serialization import architecture_to_dict
from tests.edge_weights_support import weights_data, write_weights

REPO = Path(__file__).resolve().parents[1]

# Spec R5: existing SOURCE_EXTENSIONS order, restated so a changed order in the product is caught.
TS_EXTENSIONS = ('.ts', '.mts', '.cts', '.tsx', '.js', '.jsx', '.mjs', '.cjs')
CONTROL_CHARS = ('\x0b', '\x0c', '\x1c', '\x1d', '\x1e', '\x85', '\u2028', '\u2029')


def ref_line_count(text):
    """R1: number of LF, plus one when the text is non-empty and does not end with LF."""
    count = sum(1 for ch in text if ch == '\n')
    if text and not text.endswith('\n'):
        count += 1
    return count


def ref_lines(text):
    """R2: LF-separated pieces; a CR directly before an LF is dropped from that piece only."""
    lines, current, index = [], [], 0
    while index < len(text):
        ch = text[index]
        if ch == '\n':
            if current and current[-1] == '\r':
                current.pop()
            lines.append(''.join(current))
            current = []
        else:
            current.append(ch)
        index += 1
    if current:
        lines.append(''.join(current))
    return tuple(lines)


def write_tree(root, files):
    root = Path(root)
    for name, content in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content.encode('utf-8') if isinstance(content, str) else content)
    return root


def ref_resolve_relative(importer, specifier, project_files):
    """R5 (v3, four candidate groups in order). project_files: posix paths of analysed modules. Returns the first match or None."""
    base = posixpath.normpath(posixpath.join(posixpath.dirname(importer), specifier))
    if base == '..' or base.startswith('../'):
        return None
    candidates = []
    if posixpath.splitext(base)[1] in TS_EXTENSIONS:
        candidates.append(base)
    candidates.extend(base + ext for ext in TS_EXTENSIONS)
    suffix = posixpath.splitext(base)[1]
    if suffix in TS_EXTENSIONS:
        candidates.extend(base[:-len(suffix)] + ext for ext in TS_EXTENSIONS)
    candidates.extend(f'{base}/index{ext}' for ext in TS_EXTENSIONS)
    for candidate in candidates:
        if candidate in project_files:
            return candidate
    return None


def edge_rows(architecture):
    """(from, relation, to, confidence, resolution, candidates) per edge of a language-level architecture."""
    data = architecture_to_dict(architecture)
    return [(e['from_id'], e['relation'], e['to_id'], e['confidence'], e['resolution'], tuple(e['candidates']))
            for e in data['edges']]


def node_rows(architecture):
    return {n['id']: n for n in architecture_to_dict(architecture)['nodes']}


def ts_analyze(root):
    from language_analyzers.typescript import TypeScriptAnalyzer
    return TypeScriptAnalyzer(str(root)).analyze()


def kotlin_analyze(root):
    from language_analyzers.kotlin import KotlinAnalyzer
    return KotlinAnalyzer(str(root)).analyze()


def python_analyze(root):
    from language_analyzers.python.graph import PythonGraphAnalyzer
    return PythonGraphAnalyzer(str(root)).analyze()


def ts_file_of(node_id):
    """'ts:a/b.ts#X' -> 'a/b.ts'."""
    return node_id[len('ts:'):].split('#', 1)[0]


def kt_file_of(node_id):
    return node_id[len('kotlin:'):].split('#', 1)[0]


def run_pipeline(root, tmp_path, granularity, *language_args, threshold=None, name='run'):
    """Run the CLI in-process and return (bottlenecks payload, snapshot, architecture handed to analyze_bottlenecks)."""
    import code_analyzer.cli as cli
    out = Path(tmp_path) / name
    out.mkdir(parents=True, exist_ok=True)
    argv = ['code-analyzer', str(Path(root).resolve()), *language_args, '--granularity', granularity,
            '-o', str(out / 'report.html'), '--bottlenecks', str(out / 'b.json')]
    if threshold is not None:
        weights = write_weights(out, weights_data(large_node_line_threshold=threshold))
        argv += ['--edge-weights', str(weights)]
    seen = {}
    original = cli.analyze_bottlenecks

    def spy(snapshot, arch, weights, *args, **kwargs):
        seen.update(snapshot=snapshot, arch=arch)
        return original(snapshot, arch, weights, *args, **kwargs)

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(cli, 'analyze_bottlenecks', spy)
        patch.setattr(sys, 'argv', argv)
        cli.main()
    assert seen, 'the CLI must reach analyze_bottlenecks'
    return json.loads((out / 'b.json').read_text(encoding='utf-8')), seen['snapshot'], seen['arch']


def candidates_of(payload, kind):
    return [c for c in payload['candidates'] if c['kind'] == kind]


def arch_edges(arch):
    return [(e.from_id, str(e.relation), e.to_id, str(e.confidence), str(e.resolution), tuple(e.candidates))
            for e in arch.edges]


def arch_node(arch, node_id):
    for node in arch.nodes:
        if node.id == node_id:
            return node
    raise AssertionError(f'node {node_id} missing')
