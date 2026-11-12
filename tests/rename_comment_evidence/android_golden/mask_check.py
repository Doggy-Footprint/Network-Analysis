"""argv: worktree root, fixture root, out json, mask(0/1). Runs KotlinAnalyzer of that worktree; mask=1 analyzes a copy with comments blanked."""
import sys, json, shutil, tempfile
from pathlib import Path
root, fixture, out, mask = sys.argv[1], Path(sys.argv[2]), sys.argv[3], sys.argv[4] == '1'
sys.path.insert(0, root)
from language_analyzers.kotlin import KotlinAnalyzer
target = fixture
if mask:
    from tree_sitter_language_pack import get_parser
    parser = get_parser('kotlin')
    tmp = Path(tempfile.mkdtemp()) / 'fx'; shutil.copytree(fixture, tmp, symlinks=True); target = tmp
    for f in list(tmp.rglob('*.kt')) + list(tmp.rglob('*.kts')):
        data = bytearray(f.read_bytes()); tree = parser.parse(bytes(data)); stack = [tree.root_node]
        while stack:
            n = stack.pop()
            if n.type in ('line_comment', 'multiline_comment', 'comment', 'block_comment'):
                seg = data[n.start_byte:n.end_byte].decode('utf-8')
                blank = ''.join(c if c == '\n' else ' ' * len(c.encode('utf-8')) for c in seg).encode()
                data[n.start_byte:n.end_byte] = blank
                continue
            stack.extend(n.children)
        f.write_bytes(bytes(data))
nodes, edges = KotlinAnalyzer(target).build()
by = {n.id: n for n in nodes}
rows = sorted({(e.from_id, e.to_id, str(e.relation), str(e.resolution), e.evidence.start_line if e.evidence else None) for e in edges})
json.dump(rows, open(out, 'w'))
print(len(rows))
