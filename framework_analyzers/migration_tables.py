from __future__ import annotations

import re
from typing import Dict, List, Optional, Sequence, Tuple

from language_analyzers.core.graph_models import (Confidence, GraphEdge, RelationKind,
                                                  Resolution, SourceSpan)

RULE_ID = "orm.migration_touches_table"

_NAME_PART = r'"[^"]*"|`[^`]*`|\[[^\]]*\]|[^\s.]+'
_QUOTED_PART = re.compile(_NAME_PART)
_IDENT = r'(?:"[^"]*"|`[^`]*`|\[[^\]]*\]|[A-Za-z_][\w$]*)(?:\s*\.\s*(?:"[^"]*"|`[^`]*`|\[[^\]]*\]|[A-Za-z_][\w$]*))*'
_FLAGS = re.IGNORECASE

_CREATE_TABLE = re.compile(
    rf"^\s*CREATE\s+(?:(?:TEMP|TEMPORARY)\s+)?TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?({_IDENT})", _FLAGS)
_ALTER_TABLE = re.compile(
    rf"^\s*ALTER\s+TABLE\s+(?:IF\s+EXISTS\s+)?(?:ONLY\s+)?({_IDENT})", _FLAGS)
_RENAME_TO = re.compile(rf"\bRENAME\s+TO\s+({_IDENT})", _FLAGS)
_DROP_TABLE = re.compile(rf"^\s*DROP\s+TABLE\s+(?:IF\s+EXISTS\s+)?({_IDENT})", _FLAGS)
_CREATE_INDEX = re.compile(
    rf"^\s*CREATE\s+(?:UNIQUE\s+)?INDEX\s+(?:IF\s+NOT\s+EXISTS\s+)?{_IDENT}\s+ON\s+(?:ONLY\s+)?({_IDENT})", _FLAGS)
_REFERENCES = re.compile(rf"\bREFERENCES\s+({_IDENT})", _FLAGS)
_COMMENTS = re.compile(r"--[^\n]*|/\*.*?\*/", re.DOTALL)


def normalize_table_name(name: str) -> Optional[str]:
    if not isinstance(name, str):
        return None
    parts = _QUOTED_PART.findall(name.strip())
    if not parts:
        return None
    last = parts[-1]
    if len(last) >= 2 and (last[0], last[-1]) in {('"', '"'), ("`", "`"), ("[", "]")}:
        last = last[1:-1]
    last = last.strip().lower()
    return last or None


def _statements(sql: str) -> List[str]:
    statements: List[str] = []
    current: List[str] = []
    quote = ""
    for char in sql:
        if quote:
            if char == quote:
                quote = ""
        elif char in "'\"`":
            quote = char
        elif char == ";":
            statements.append("".join(current))
            current = []
            continue
        current.append(char)
    statements.append("".join(current))
    return statements


def sql_table_refs(sql: str) -> List[str]:
    if not isinstance(sql, str) or not sql.strip():
        return []
    refs: List[str] = []

    def add(raw: str) -> None:
        name = normalize_table_name(raw)
        if name is not None and name not in refs:
            refs.append(name)

    for statement in _statements(_COMMENTS.sub(" ", sql)):
        match = _CREATE_TABLE.match(statement)
        if match:
            add(match.group(1))
            for reference in _REFERENCES.finditer(statement, match.end()):
                add(reference.group(1))
            continue
        match = _ALTER_TABLE.match(statement)
        if match:
            add(match.group(1))
            rename = _RENAME_TO.search(statement, match.end())
            if rename:
                add(rename.group(1))
            for reference in _REFERENCES.finditer(statement, match.end()):
                add(reference.group(1))
            continue
        match = _DROP_TABLE.match(statement) or _CREATE_INDEX.match(statement)
        if match:
            add(match.group(1))
    return refs


def match_migration_tables(
    models: Dict[str, List[str]],
    migrations: Sequence[Tuple[str, Sequence[Optional[str]], SourceSpan]],
) -> Tuple[List[GraphEdge], Dict[str, int]]:
    stats = {"matched": 0, "ambiguous": 0, "unmatched": 0, "unresolvable": 0}
    edges: Dict[Tuple[str, str], GraphEdge] = {}
    for migration_id, refs, evidence in migrations:
        seen = set()
        for ref in refs:
            if ref is None:
                stats["unresolvable"] += 1
                continue
            if ref in seen:
                continue
            seen.add(ref)
            candidates = sorted(set(models.get(ref, [])))
            if not candidates:
                stats["unmatched"] += 1
                continue
            ambiguous = len(candidates) > 1
            stats["ambiguous" if ambiguous else "matched"] += 1
            target = candidates[0]
            if (migration_id, target) in edges:
                continue
            edges[(migration_id, target)] = GraphEdge(
                from_id=migration_id,
                to_id=target,
                relation=RelationKind.MIGRATES,
                confidence=Confidence.FRAMEWORK_INFERRED,
                resolution=Resolution.AMBIGUOUS if ambiguous else Resolution.UNIQUE_NAME,
                evidence=evidence,
                candidates=candidates[1:],
                metadata={
                    "framework_rule": {"id": RULE_ID, "specificity": "ambiguous" if ambiguous else "unique"},
                    "table": ref,
                },
            )
    return [edges[pair] for pair in sorted(edges)], stats
