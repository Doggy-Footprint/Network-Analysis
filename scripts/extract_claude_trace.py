import argparse
import hashlib
import json
import re
import shlex
import sys
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Sequence, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from discovery.trace import TraceError, validate_trace  # noqa: E402

READ_COMMANDS = ("cat", "sed", "head", "tail", "less", "more")
SEARCH_COMMANDS = ("grep", "rg", "egrep", "fgrep", "ack")
LIST_COMMANDS = ("ls", "find", "tree", "fd")
_SEGMENT = re.compile(r"&&|\|\||;|\|")
_PATH_LIKE = re.compile(r"^[A-Za-z0-9_./~$-][A-Za-z0-9_./*-]*$")
_HEREDOC = re.compile(r"<<-?\s*['\"]?\w+")
SEARCH_VALUE_FLAGS = ("-e", "-m", "-A", "-B", "-C", "--include", "--exclude", "-g", "-t")
LIST_VALUE_FLAGS = ("-type", "-name", "-path", "-iname", "-maxdepth", "-mindepth")
READ_VALUE_FLAGS = ("-n",)


def _tool_uses(record: Dict[str, Any]) -> Iterator[Tuple[str, Dict[str, Any]]]:
    message = record.get("message") or {}
    content = message.get("content")
    if not isinstance(content, list):
        return
    for block in content:
        if isinstance(block, dict) and block.get("type") == "tool_use":
            yield str(block.get("name", "")), block.get("input") or {}


def _repo_relative(token: str, root_names: Sequence[str]) -> Optional[str]:
    value = token.strip("'\"")
    if not value or value.startswith("-") or not _PATH_LIKE.match(value):
        return None
    for name in root_names:
        if value.startswith(name + "/"):
            value = value[len(name) + 1:]
            break
    if value.startswith("/") or value.startswith("~"):
        return None
    return value


def _segments(command: str) -> List[str]:
    if _HEREDOC.search(command):
        return []
    return [part.strip() for part in _SEGMENT.split(command) if part.strip()]


def _tokens(segment: str) -> List[str]:
    try:
        return shlex.split(segment)
    except ValueError:
        return segment.split()


def _value_flags(name: str) -> Tuple[str, ...]:
    if name in SEARCH_COMMANDS:
        return SEARCH_VALUE_FLAGS
    if name in LIST_COMMANDS:
        return LIST_VALUE_FLAGS
    if name in READ_COMMANDS:
        return READ_VALUE_FLAGS
    return ()


def _drop_flag_values(arguments: Sequence[str], value_flags: Sequence[str]) -> List[str]:
    kept = []
    skip = False
    for token in arguments:
        if skip:
            skip = False
            continue
        if token in value_flags:
            skip = True
            continue
        kept.append(token)
    return kept


def _bash_events(command: str, root_names: Sequence[str]) -> List[Dict[str, Any]]:
    events = []
    for segment in _segments(command):
        tokens = _tokens(segment)
        if not tokens:
            continue
        name = Path(tokens[0]).name
        arguments = _drop_flag_values(tokens[1:], _value_flags(name))
        paths = [
            resolved
            for resolved in (_repo_relative(token, root_names) for token in arguments)
            if resolved is not None
        ]
        if name in SEARCH_COMMANDS:
            term = next((token for token in arguments if not token.startswith("-")), "")
            events.append({
                "kind": "search",
                "term": term.strip("'\""),
                "surface": "content",
                "paths": [item for item in paths if item != term],
                "raw_tool": f"Bash:{name}",
            })
        elif name in READ_COMMANDS and paths:
            events.append({
                "kind": "read", "term": "", "surface": "content",
                "paths": paths, "raw_tool": f"Bash:{name}",
            })
        elif name in LIST_COMMANDS:
            events.append({
                "kind": "list", "term": "", "surface": "path",
                "paths": paths, "raw_tool": f"Bash:{name}",
            })
        else:
            events.append({
                "kind": "other", "term": "", "surface": "content",
                "paths": paths, "raw_tool": f"Bash:{name}",
            })
    return events


def _tool_events(name: str, value: Dict[str, Any], root_names: Sequence[str]) -> List[Dict[str, Any]]:
    if name == "Bash":
        return _bash_events(str(value.get("command", "")), root_names)
    if name == "Grep":
        path = _repo_relative(str(value.get("path", "")), root_names)
        return [{
            "kind": "search", "term": str(value.get("pattern", "")),
            "surface": "path" if value.get("glob") and not value.get("pattern") else "content",
            "paths": [path] if path else [], "raw_tool": "Grep",
        }]
    if name == "Glob":
        return [{
            "kind": "list", "term": str(value.get("pattern", "")), "surface": "path",
            "paths": [], "raw_tool": "Glob",
        }]
    if name in ("Read", "Edit", "Write", "NotebookEdit"):
        path = _repo_relative(str(value.get("file_path", "")), root_names)
        return [{
            "kind": "read" if name == "Read" else "other", "term": "", "surface": "content",
            "paths": [path] if path else [], "raw_tool": name,
        }]
    return [{"kind": "other", "term": "", "surface": "content", "paths": [], "raw_tool": name}]


def extract(
    transcript: Path,
    repository_name: str,
    root_names: Sequence[str],
    targets: Sequence[str],
    commit: str,
    task: Optional[str] = None,
) -> Dict[str, Any]:
    raw = transcript.read_bytes()
    events: List[Dict[str, Any]] = []
    first_prompt = None
    model = ""
    session_id = ""
    recorded_at = ""
    for line in raw.decode("utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        session_id = session_id or str(record.get("sessionId", ""))
        recorded_at = recorded_at or str(record.get("timestamp", ""))
        message = record.get("message") or {}
        if record.get("type") == "user" and first_prompt is None:
            content = message.get("content")
            if isinstance(content, str) and content.strip():
                first_prompt = content
        if record.get("type") == "assistant":
            model = model or str(message.get("model", ""))
        for name, value in _tool_uses(record):
            events.extend(_tool_events(name, value, root_names))

    for index, event in enumerate(events):
        event["index"] = index

    trace = {
        "schema": "agent_trace.v1",
        "trace_id": hashlib.sha256(raw).hexdigest()[:16],
        "recorded_at": recorded_at,
        "source": {
            "tool": "claude-code",
            "transcript_sha256": hashlib.sha256(raw).hexdigest(),
            "session_id": session_id,
        },
        "repository": {"name": repository_name, "commit": commit},
        "agent": {"name": "claude-code", "model": model, "settings": {"mode": "auto"}},
        "task": task if task is not None else (first_prompt or ""),
        "targets": list(targets),
        "events": events,
    }
    validate_trace(trace)
    return trace


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Claude Code 세션 트랜스크립트를 agent_trace.v1 스키마로 변환합니다."
    )
    parser.add_argument("transcript")
    parser.add_argument("-o", "--output", required=True)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--commit", default="")
    parser.add_argument("--root-name", action="append", default=[])
    parser.add_argument("--target", action="append", default=[])
    parser.add_argument("--task", default=None)
    args = parser.parse_args(argv)
    try:
        trace = extract(
            Path(args.transcript), args.repository, args.root_name,
            args.target, args.commit, args.task,
        )
    except (OSError, TraceError) as error:
        print(f"{type(error).__name__}: {error}", file=sys.stderr)
        return 1
    Path(args.output).write_text(
        json.dumps(trace, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
