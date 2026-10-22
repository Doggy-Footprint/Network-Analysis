from __future__ import annotations

import hashlib
import posixpath
import re
from typing import Any, Mapping
from urllib.parse import unquote

COLUMNS = ["doc", "line", "notation", "text", "status", "target", "target_kind", "candidates", "candidate_total"]
_DOC_SUFFIXES = (".md", ".mdx", ".markdown")
_FENCE_OPEN = re.compile(r"^ {0,3}(`{3,}|~{3,})(.*)$")
_FENCE_CLOSE = re.compile(r"^ {0,3}(`{3,}|~{3,})[ \t]*$")
_INLINE_LINK = re.compile(r"!?\[[^\[\]]*\]\([ \t]*(<[^<>]*>|[^\s)]+)")
_REF_DEF = re.compile(r"^ {0,3}\[([^\]\[]+)\]:[ \t]*(<[^<>]*>|\S+)")
_SCHEME = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")
_BACKTICKS = re.compile(r"`+")
_FORBIDDEN = re.compile(r"[\s*?<>{}\[\]$|]")
_EXTENSION = re.compile(r"\.[A-Za-z0-9]{1,5}$")
_GRADLE = re.compile(r"^:[A-Za-z0-9_.-]+(:[A-Za-z0-9_.-]+)*$")
_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)*$")
_SYMBOL_KINDS = frozenset({"class", "interface", "enum", "type_alias", "function", "method"})
_FALLBACKS = ("", ".md", ".mdx", "/README.md", "/index.md", "/index.mdx")
_CANDIDATE_LIMIT = 10


class _Inventory:
    def __init__(self, snapshot: Any) -> None:
        paths = {path for path, _ in snapshot.contents}
        paths.update(item.file_path for item in snapshot.excluded_files if isinstance(getattr(item, "file_path", None), str))
        self.files = paths
        dirs = {""} if paths else set()
        for path in paths:
            parent = posixpath.dirname(path)
            while parent and parent not in dirs:
                dirs.add(parent)
                parent = posixpath.dirname(parent)
        self.dirs = dirs

    def exists(self, path: str) -> bool:
        return path in self.files or path in self.dirs

    def first(self, path: str) -> str | None:
        if not path:
            return "" if "" in self.dirs else None
        for suffix in _FALLBACKS:
            if self.exists(path + suffix):
                return path + suffix
        return None


def _normalize(base: str, rel: str) -> str | None:
    joined = posixpath.normpath(posixpath.join(base, rel)) if rel else base
    if joined == ".":
        return ""
    return None if joined == ".." or joined.startswith("../") else joined


def _symbol_index(nodes: Any) -> tuple[dict, dict, list]:
    by_label: dict[str, list[str]] = {}
    by_path: dict[str, list[str]] = {}
    gradle = []
    for node in nodes if isinstance(nodes, list) else ():
        if not isinstance(node, Mapping) or not isinstance(node.get("id"), str):
            continue
        metadata = node.get("metadata")
        if isinstance(metadata, Mapping) and metadata.get("build_system") == "gradle" and isinstance(metadata.get("module_path"), str):
            gradle.append((node["id"], metadata["module_path"], metadata.get("module_dir") is not None))
        if node.get("kind") not in _SYMBOL_KINDS:
            continue
        label, symbol_path = node.get("label"), node.get("symbol_path")
        if isinstance(label, str):
            by_label.setdefault(label, []).append(node["id"])
        if isinstance(symbol_path, str):
            parts = symbol_path.split(".")
            for index in range(len(parts)):
                by_path.setdefault(".".join(parts[index:]), []).append(node["id"])
    return by_label, by_path, gradle


def _doc_lines(text: str):
    in_fence = None
    for number, line in enumerate(text.split("\n"), 1):
        if line.endswith("\r"):
            line = line[:-1]
        if in_fence is not None:
            match = _FENCE_CLOSE.match(line)
            if match and match.group(1)[0] == in_fence[0] and len(match.group(1)) >= in_fence[1]:
                in_fence = None
            continue
        match = _FENCE_OPEN.match(line)
        if match and not (match.group(1)[0] == "`" and "`" in match.group(2)):
            in_fence = (match.group(1)[0], len(match.group(1)))
            continue
        yield number, line


def _spans(line: str) -> tuple[list[tuple[int, str]], str]:
    runs = [(m.start(), m.end()) for m in _BACKTICKS.finditer(line)]
    if len(runs) < 2:
        return [], line
    nxt: dict[int, int] = {}
    closer = [-1] * len(runs)
    for index in range(len(runs) - 1, -1, -1):
        length = runs[index][1] - runs[index][0]
        closer[index] = nxt.get(length, -1)
        nxt[length] = index
    spans, masked, cursor, index = [], [], 0, 0
    while index < len(runs):
        other = closer[index]
        if other < 0:
            index += 1
            continue
        start, end = runs[index][0], runs[other][1]
        if runs[index][1] - start == 1:
            spans.append((start, line[runs[index][1]:runs[other][0]]))
        masked += [line[cursor:start], " " * (end - start)]
        cursor, index = end, other + 1
    masked.append(line[cursor:])
    return spans, "".join(masked)


def analyze_doc_references(snapshot: Any, details: Mapping[str, Any]) -> tuple[dict, list[dict], dict]:
    inventory = _Inventory(snapshot)
    file_nodes = details.get("file_nodes") if isinstance(details, Mapping) else None
    file_nodes = file_nodes if isinstance(file_nodes, Mapping) else {}
    by_label, by_path, gradle = _symbol_index(details.get("nodes") if isinstance(details, Mapping) else None)
    gradle_enabled = any(has_dir for _, _, has_dir in gradle)
    gradle_ids: dict[str, str] = {}
    for node_id, module_path, has_dir in sorted(gradle, reverse=True):
        if has_dir:
            gradle_ids[module_path] = node_id

    def path_target(path: str) -> tuple[str, str]:
        node_id = "file:" + path
        if node_id in file_nodes:
            return node_id, "file"
        return path or ".", ("directory" if path in inventory.dirs and path not in inventory.files else "path")

    def resolve_link(doc_dir: str, raw: str) -> tuple[str, str | None, str | None]:
        target = raw.strip()
        if target.startswith("<") and target.endswith(">"):
            target = target[1:-1].strip()
        if not target or _SCHEME.match(target) or target.startswith("#"):
            return "", None, None
        target = unquote(target.split("#", 1)[0].split("?", 1)[0])
        if not target:
            return "", None, None
        absolute = target.startswith("/")
        path = _normalize("", target.lstrip("/")) if absolute else _normalize(doc_dir, target)
        found = None if path is None or (absolute and not path) else inventory.first(path)
        if found is None:
            return ("site_route" if absolute else "dangling"), None, None
        return ("resolved", *path_target(found))

    def resolve_span(doc_dir: str, content: str):
        if _FORBIDDEN.search(content) or _SCHEME.match(content):
            return None
        slash = "/" in content
        if content.startswith("/"):
            bases, rel = [""], content.lstrip("/")
        else:
            bases, rel = ([doc_dir, ""] if doc_dir else [""]), (content[2:] if content.startswith("./") else content)
        rel = rel.rstrip("/")
        hit = None
        for base in bases:
            full = _normalize(base, rel) if rel else None
            if full is not None and inventory.exists(full):
                hit = full
                break
        if slash:
            first = rel.split("/", 1)[0]
            firsts = [_normalize(base, first) if first else None for base in bases]
            if not any(item and inventory.exists(item) for item in firsts) and not _EXTENSION.search(content):
                return None
        elif hit is None:
            return None
        if hit is not None:
            return ("resolved", *path_target(hit))
        return ("dangling", None, None)

    rows = []
    candidates = []
    for doc, text in sorted(snapshot.contents):
        if not doc.lower().endswith(_DOC_SUFFIXES) or not isinstance(text, str):
            continue
        doc_dir = posixpath.dirname(doc)
        found = []

        def add(number, column, notation, raw, status, target=None, kind=None, cands=None, total=None):
            found.append((number, column, [doc, number, notation, raw, status, target, kind, cands, total]))

        for number, line in _doc_lines(text):
            if "`" not in line and "[" not in line:
                continue
            spans, masked = _spans(line) if "`" in line else ([], line)
            if "[" in masked:
                match = _REF_DEF.match(masked)
                if match and not match.group(1).startswith("^"):
                    raw = match.group(2)
                    status, target, kind = resolve_link(doc_dir, raw)
                    if status:
                        add(number, match.start(2), "link", raw[1:-1].strip() if raw.startswith("<") and raw.endswith(">") else raw, status, target, kind)
                for match in _INLINE_LINK.finditer(masked):
                    raw = match.group(1)
                    status, target, kind = resolve_link(doc_dir, raw)
                    if status:
                        add(number, match.start(), "link", raw[1:-1].strip() if raw.startswith("<") and raw.endswith(">") else raw, status, target, kind)
            for column, content in spans:
                if not content:
                    continue
                if _GRADLE.match(content):
                    if not gradle_enabled:
                        continue
                    node_id = gradle_ids.get(content)
                    add(number, column, "gradle_module", content, *(("resolved", node_id, "build_module") if node_id else ("dangling", None, None)))
                    continue
                result = resolve_span(doc_dir, content)
                if result is not None:
                    add(number, column, "code_path", content, *result)
                    continue
                name = content[:-2] if content.endswith("()") else content
                if not _IDENT.match(name):
                    continue
                ids = by_path.get(name, ()) if "." in name else by_label.get(name, ())
                ids = sorted(set(ids))
                if len(ids) == 1:
                    add(number, column, "identifier", content, "resolved", ids[0], "symbol")
                elif ids:
                    add(number, column, "identifier", content, "ambiguous", None, None, ids[:_CANDIDATE_LIMIT], len(ids))
        found.sort(key=lambda item: item[:2])
        doc_rows = [item[2] for item in found]
        rows += doc_rows
        dangling = [row for row in doc_rows if row[4] == "dangling"]
        if dangling:
            candidates.append({"id": "b:" + hashlib.sha256((doc + "|dangling_doc").encode()).hexdigest()[:16], "kind": "dangling_doc_reference", "target": "file:" + doc,
                               "metrics": {"dangling_count": len(dangling)}, "evidence": [{"line": row[1], "notation": row[2], "text": row[3]} for row in dangling],
                               "coverage": "doc_reference", "status": "static_candidate"})
    doc_count = sum(1 for path, _ in snapshot.contents if path.lower().endswith(_DOC_SUFFIXES))
    by_status: dict[str, int] = {}
    by_notation: dict[str, int] = {}
    for row in rows:
        by_status[row[4]] = by_status.get(row[4], 0) + 1
        by_notation[row[2]] = by_notation.get(row[2], 0) + 1
    summary = {"document_count": doc_count, "reference_count": len(rows), "by_status": dict(sorted(by_status.items())), "by_notation": dict(sorted(by_notation.items()))}
    return {"columns": list(COLUMNS), "rows": rows}, candidates, summary
