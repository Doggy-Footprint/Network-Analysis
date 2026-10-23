from __future__ import annotations

import json
import re
from typing import Dict, List, Mapping, Optional, Set, Tuple

from .graph_models import Confidence, GraphEdge, GraphNode, NodeCost, RelationKind, Resolution, SourceSpan

_INCLUDE_RE = re.compile(r"(?<![\w.])include\s*\(?\s*(?P<args>(?:[\"'][^\"'\r\n]*[\"']\s*,?\s*)+)")
_STRING_ARG_RE = re.compile(r"[\"']([^\"'\r\n]*)[\"']")
_PROJECT_RE = re.compile(r"(?<![\w.])project\s*\(\s*(?:path\s*[:=]\s*)?[\"']([^\"'\r\n]*)[\"']")
_ACCESSOR_RE = re.compile(r"(?<![\w.])projects((?:\.[A-Za-z_]\w*)+)")
_TRAILING_IDENT_RE = re.compile(r"([A-Za-z_]\w*)\s*\(?\s*$")
_NPM_DEP_FIELDS = ("dependencies", "devDependencies", "peerDependencies", "optionalDependencies")
_DEPENDENCY_WRAPPERS = {"platform", "enforcedPlatform", "testFixtures"}
_ZERO_COST = NodeCost(0, 0, 0)


def _blank_comments(text: str) -> str:
    out, i, n = [], 0, len(text)
    while i < n:
        c = text[i]
        if c in "\"'":
            j = i + 1
            while j < n and text[j] != c and text[j] != "\n":
                j += 2 if text[j] == "\\" else 1
            out.append(text[i:j + 1]); i = j + 1
        elif text.startswith("//", i):
            j = text.find("\n", i)
            j = n if j < 0 else j
            out.append(" " * (j - i)); i = j
        elif text.startswith("/*", i):
            j = text.find("*/", i + 2)
            j = n if j < 0 else j + 2
            out.append(re.sub(r"[^\n]", " ", text[i:j])); i = j
        else:
            out.append(c); i += 1
    return "".join(out)


def _line_of(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def _gradle_path(raw: str) -> str:
    return ":" + raw.strip().strip(":")


def _gradle_dir(path: str) -> str:
    return path.strip(":").replace(":", "/")


def _camel(segment: str) -> str:
    head, *rest = re.split(r"[-_]", segment)
    return head + "".join(part[:1].upper() + part[1:] for part in rest)


def _gradle_modules(contents: Mapping[str, str]) -> Dict[str, str]:
    settings = next((contents[name] for name in ("settings.gradle.kts", "settings.gradle") if name in contents), None)
    if settings is not None:
        paths = {":"}
        for match in _INCLUDE_RE.finditer(_blank_comments(settings)):
            for raw in _STRING_ARG_RE.findall(match.group("args")):
                if raw.strip().strip(":"):
                    paths.add(_gradle_path(raw))
        return {path: _gradle_dir(path) for path in paths}
    dirs = {name.rpartition("/")[0] for name in contents if name.rpartition("/")[2] in ("build.gradle", "build.gradle.kts")}
    return {(":" + directory.replace("/", ":")) if directory else ":": directory for directory in dirs}


def _build_file(contents: Mapping[str, str], directory: str, names: Tuple[str, ...]) -> Optional[str]:
    return next((candidate for candidate in (f"{directory}/{name}" if directory else name for name in names) if candidate in contents), None)


def _module_node(node_id: str, label: str, provenance: str, metadata: Dict[str, str], build_file: Optional[str], contents: Mapping[str, str]) -> GraphNode:
    # A build file without lines cannot carry a 1:1 span; the file graph rejects spans past the file end.
    spanned = build_file is not None and bool(contents[build_file])
    return GraphNode(
        id=node_id, label=label, group="configuration", category="configuration", kind="module",
        language="configuration", provenance=provenance, symbol_path=label, cost=_ZERO_COST,
        span=SourceSpan(build_file, 1, 1) if spanned else None,
        metadata=dict(metadata, file_path=build_file) if spanned else metadata,
    )


def _enclosing_call(text: str, offset: int) -> Optional[str]:
    depth, index = 0, offset - 1
    while index >= 0:
        char = text[index]
        if char in ")}":
            depth += 1
        elif char in "({":
            if depth:
                depth -= 1
            elif char == "(":
                found = re.search(r"([A-Za-z_]\w*)\s*$", text[:index])
                if not found:
                    return None
                if found.group(1) not in _DEPENDENCY_WRAPPERS:
                    return found.group(1)
                offset, index = found.start(1), found.start(1)
            else:
                break
        index -= 1
    found = _TRAILING_IDENT_RE.search(text[text.rfind("\n", 0, offset) + 1:offset])
    return found.group(1) if found and found.group(1) not in _DEPENDENCY_WRAPPERS else None


def _gradle_graph(contents: Mapping[str, str]) -> Tuple[List[GraphNode], List[GraphEdge]]:
    modules = _gradle_modules(contents)
    if not modules:
        return [], []
    accessors = {tuple(_camel(part) for part in path.strip(":").split(":")): path for path in modules if path != ":"}
    nodes: Dict[str, GraphNode] = {}
    build_files: Dict[str, Optional[str]] = {}
    for path in sorted(modules):
        directory = modules[path]
        build_file = _build_file(contents, directory, ("build.gradle.kts", "build.gradle"))
        build_files[path] = build_file
        node_id = f"build-module:gradle:{path}"
        nodes[node_id] = _module_node(node_id, path, "gradle", {"build_system": "gradle", "module_path": path, "module_dir": directory}, build_file, contents)
    edges: Dict[Tuple[str, str, str], GraphEdge] = {}
    extra: Dict[str, GraphNode] = {}
    for path in sorted(modules):
        build_file = build_files[path]
        if build_file is None:
            continue
        text = _blank_comments(contents[build_file])
        references = [(m.start(), _gradle_path(m.group(1))) for m in _PROJECT_RE.finditer(text) if m.group(1).strip().strip(":")]
        for match in _ACCESSOR_RE.finditer(text):
            segments = tuple(match.group(1)[1:].split("."))
            references.append((match.start(), accessors.get(segments) or "projects" + match.group(1)))
        for offset, target_path in sorted(references):
            configuration = _enclosing_call(text, offset)
            target_id = f"build-module:gradle:{target_path}"
            source_id = f"build-module:gradle:{path}"
            if configuration is None or target_id == source_id:
                continue
            exact = target_path in modules
            if not exact and target_id not in extra:
                extra[target_id] = GraphNode(
                    id=target_id, label=target_path, group="configuration", category="configuration", kind="module",
                    language="configuration", provenance="gradle", symbol_path=target_path, cost=_ZERO_COST,
                    metadata={"build_system": "gradle", "module_path": target_path},
                )
            key = (source_id, target_id, configuration)
            if key not in edges:
                line = _line_of(text, offset)
                edges[key] = GraphEdge(
                    from_id=source_id, to_id=target_id, relation=RelationKind.DECLARES_DEPENDENCY,
                    confidence=Confidence.STATIC_CERTAIN, resolution=Resolution.EXACT if exact else Resolution.UNRESOLVED,
                    evidence=SourceSpan(build_file, line, line), metadata={"configuration": configuration},
                )
    return list(nodes.values()) + list(extra.values()), list(edges.values())


def _glob_match(pattern: List[str], parts: List[str]) -> bool:
    if not pattern:
        return not parts
    if pattern[0] == "**":
        return any(_glob_match(pattern[1:], parts[skip:]) for skip in range(len(parts) + 1))
    if not parts:
        return False
    segment = re.escape(pattern[0]).replace(r"\*", "[^/]*")
    return re.fullmatch(segment, parts[0]) is not None and _glob_match(pattern[1:], parts[1:])


def _load_json_object(text: str) -> Optional[dict]:
    try:
        data = json.loads(text)
    except (ValueError, RecursionError):
        return None
    return data if isinstance(data, dict) else None


def _workspace_patterns(root: dict) -> Optional[List[str]]:
    workspaces = root.get("workspaces")
    if isinstance(workspaces, dict):
        workspaces = workspaces.get("packages")
    if not isinstance(workspaces, list) or not all(isinstance(item, str) for item in workspaces):
        return None
    return [item.strip().removeprefix("./").rstrip("/") for item in workspaces]


def _key_line(text: str, field: str, key: str) -> int:
    start = text.find(json.dumps(field))
    found = text.find(json.dumps(key), max(start, 0))
    return _line_of(text, found if found >= 0 else 0)


def _npm_graph(contents: Mapping[str, str]) -> Tuple[List[GraphNode], List[GraphEdge]]:
    root = _load_json_object(contents["package.json"]) if "package.json" in contents else None
    patterns = _workspace_patterns(root) if root is not None else None
    if patterns is None:
        return [], []
    positive = [p.split("/") for p in patterns if p and not p.startswith("!")]
    negative = [p[1:].lstrip("/").removeprefix("./").split("/") for p in patterns if p.startswith("!") and p[1:]]
    dirs = [""] + sorted(
        directory for directory in {name.rpartition("/")[0] for name in contents if name.rpartition("/")[2] == "package.json"} if directory
        and any(_glob_match(g, directory.split("/")) for g in positive) and not any(_glob_match(g, directory.split("/")) for g in negative)
    )
    parsed = {directory: _load_json_object(contents[f"{directory}/package.json" if directory else "package.json"]) for directory in dirs}
    names = {directory: (data["name"] if data is not None and isinstance(data.get("name"), str) and data["name"] else None) for directory, data in parsed.items()}
    claimed: Set[str] = set()
    ids: Dict[str, str] = {}
    for directory in dirs:
        name = names[directory]
        if name is not None and name not in claimed:
            claimed.add(name); ids[directory] = name
        else:
            ids[directory] = directory or "(root)"
    nodes: Dict[str, GraphNode] = {}
    for directory in dirs:
        file_path = f"{directory}/package.json" if directory else "package.json"
        node_id = f"build-module:npm:{ids[directory]}"
        if node_id not in nodes:
            nodes[node_id] = _module_node(node_id, ids[directory], "npm-workspace", {"build_system": "npm", "module_path": ids[directory], "module_dir": directory}, file_path, contents)
    edges: Dict[Tuple[str, str, str], GraphEdge] = {}
    for directory in dirs:
        data = parsed[directory]
        if data is None:
            continue
        file_path = f"{directory}/package.json" if directory else "package.json"
        for field in _NPM_DEP_FIELDS:
            declared = data.get(field)
            for key in declared if isinstance(declared, dict) else ():
                if key not in claimed or key == ids[directory]:
                    continue
                source_id, target_id = f"build-module:npm:{ids[directory]}", f"build-module:npm:{key}"
                if (source_id, target_id, field) not in edges:
                    line = _key_line(contents[file_path], field, key)
                    edges[(source_id, target_id, field)] = GraphEdge(
                        from_id=source_id, to_id=target_id, relation=RelationKind.DECLARES_DEPENDENCY,
                        confidence=Confidence.STATIC_CERTAIN, resolution=Resolution.EXACT,
                        evidence=SourceSpan(file_path, line, line), metadata={"configuration": field},
                    )
    return list(nodes.values()), list(edges.values())


def build_module_graph(contents: Mapping[str, str]) -> Tuple[List[GraphNode], List[GraphEdge]]:
    gradle_nodes, gradle_edges = _gradle_graph(contents)
    npm_nodes, npm_edges = _npm_graph(contents)
    return gradle_nodes + npm_nodes, gradle_edges + npm_edges
