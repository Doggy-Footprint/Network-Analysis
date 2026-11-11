"""argv: source fixture, destination. Copies it and blanks every tree-sitter Kotlin comment in .kt/.kts files (bytes -> spaces, newlines kept)."""
import shutil, sys
from pathlib import Path
from tree_sitter_language_pack import get_parser
src, dst = Path(sys.argv[1]), Path(sys.argv[2])
shutil.rmtree(dst, ignore_errors=True); shutil.copytree(src, dst, symlinks=True)
parser = get_parser('kotlin'); changed = 0
for f in sorted([*dst.rglob('*.kt'), *dst.rglob('*.kts')]):
    if '.git' in f.parts: continue
    data = bytearray(f.read_bytes()); stack = [parser.parse(bytes(data)).root_node]; spans = []
    while stack:
        n = stack.pop()
        if n.type in ('line_comment', 'multiline_comment'): spans.append((n.start_byte, n.end_byte)); continue
        stack.extend(n.children)
    for a, b in spans:
        data[a:b] = bytes(c if c == 0x0A else 0x20 for c in data[a:b])
    if spans: f.write_bytes(bytes(data)); changed += 1
print('files masked', changed)
