import base64
import bisect
import gzip
import hashlib
import json
import re
import string
from pathlib import Path
from typing import Dict, List, Mapping, Sequence, Tuple

from dataclasses import asdict

from .models import Occurrence, OccurrenceBlock, OccurrenceRange, ReadableNode


class OccurrenceStoreError(ValueError):
    pass

_WORD_RE = re.compile(r"[A-Za-z0-9_]+")
_WORD_CHARS = frozenset(string.ascii_letters + string.digits + "_")

DOC_SUFFIXES = {".md", ".rst", ".txt"}
CONFIG_SUFFIXES = {".json", ".yaml", ".yml", ".toml", ".properties", ".env", ".gradle"}
_TRIPLE_QUOTE_SUFFIXES = {".py", ".pyi"}


def file_context_kind(path: str) -> str:
    name = Path(path).name.lower()
    suffix = Path(path).suffix.lower()
    if suffix in DOC_SUFFIXES:
        return "doc"
    if name.endswith(".gradle.kts") or suffix in CONFIG_SUFFIXES or name == ".env":
        return "config"
    return "code"


def _line_starts(text: str) -> List[int]:
    starts = [0]
    for index, character in enumerate(text):
        if character == "\n":
            starts.append(index + 1)
    return starts


def _classify_regions(text: str, path: str) -> List[Tuple[int, int, str]]:
    triple = Path(path).suffix.lower() in _TRIPLE_QUOTE_SUFFIXES
    regions: List[Tuple[int, int, str]] = []
    index = 0
    length = len(text)
    while index < length:
        character = text[index]
        if triple and text.startswith(('"""', "'''"), index):
            delimiter = text[index:index + 3]
            end = text.find(delimiter, index + 3)
            end = length if end == -1 else end + 3
            regions.append((index, end, "docstring"))
            index = end
            continue
        if character == "#" or text.startswith("//", index):
            end = text.find("\n", index)
            end = length if end == -1 else end
            regions.append((index, end, "comment"))
            index = end
            continue
        if text.startswith("/*", index):
            end = text.find("*/", index + 2)
            end = length if end == -1 else end + 2
            regions.append((index, end, "comment"))
            index = end
            continue
        if character in ("'", '"'):
            index += 1
            while index < length and text[index] != character and text[index] != "\n":
                index += 2 if text[index] == "\\" else 1
            index += 1
            continue
        index += 1
    return regions


class OccurrenceIndex:
    def __init__(self, contents: Mapping[str, str], nodes_by_file: Mapping[str, List[ReadableNode]]):
        self._contents = dict(contents)
        self._nodes_by_file = {path: list(nodes) for path, nodes in nodes_by_file.items()}
        self._line_starts = {path: _line_starts(text) for path, text in self._contents.items()}
        self._regions: Dict[str, List[Tuple[int, int, str]]] = {}
        self._region_starts: Dict[str, List[int]] = {}
        self._base_context = {path: file_context_kind(path) for path in self._contents}
        self._enclosing_cache: Dict[Tuple[str, int], str] = {}
        self._postings = self._build_postings()

    def _build_postings(self) -> Dict[str, List[Tuple[str, int]]]:
        postings: Dict[str, List[Tuple[str, int]]] = {}
        for path in sorted(self._contents):
            for match in _WORD_RE.finditer(self._contents[path]):
                postings.setdefault(match.group(0), []).append((path, match.start()))
        return postings

    def _context(self, path: str, offset: int) -> str:
        base = self._base_context[path]
        if base != "code":
            return base
        if path not in self._regions:
            regions = _classify_regions(self._contents[path], path)
            self._regions[path] = regions
            self._region_starts[path] = [region[0] for region in regions]
        regions = self._regions[path]
        starts = self._region_starts[path]
        position = bisect.bisect_right(starts, offset) - 1
        if position >= 0 and regions[position][0] <= offset < regions[position][1]:
            return regions[position][2]
        return "code"

    def _enclosing(self, path: str, line: int) -> str:
        key = (path, line)
        cached = self._enclosing_cache.get(key)
        if cached is None:
            cached = enclosing_node_id(self._nodes_by_file.get(path, []), path, line)
            self._enclosing_cache[key] = cached
        return cached

    def _at(self, path: str, offset: int, term: str) -> Occurrence:
        starts = self._line_starts[path]
        line_index = bisect.bisect_right(starts, offset) - 1
        return Occurrence(
            file_path=path,
            line=line_index + 1,
            col=offset - starts[line_index],
            matched_text=term,
            context=self._context(path, offset),
            enclosing_node_id=self._enclosing(path, line_index + 1),
        )

    def find(self, term: str) -> List[Occurrence]:
        if not term:
            return []
        anchors = list(_WORD_RE.finditer(term))
        if not anchors:
            return self._scan(term)

        # 후보 위치는 가장 희소한 토큰의 posting에서만 나온다. term 내부 토큰은 term 안의
        # 비영숫자 구분자에 둘러싸여 텍스트에서도 같은 토큰으로 잘리고, 가장자리 토큰이 텍스트에서
        # 더 긴 토큰으로 이어지는 경우는 아래 경계 검사가 그대로 걸러낸다.
        anchor = min(anchors, key=lambda match: len(self._postings.get(match.group(0), ())))
        lead = anchor.start()
        width = len(term)

        results: List[Occurrence] = []
        consumed_path = ""
        consumed_until = 0
        # posting은 파일 경로 순, 파일 안에서는 오프셋 순으로 쌓여 있으므로 왼쪽부터 훑으면서
        # 직전 매치가 덮은 구간을 건너뛰면 re.finditer의 비중첩 매치와 같은 집합이 된다.
        # `0.0.0.0` 안의 `0.0.0`처럼 겹치는 후보는 검색 도구도 한 번만 보고한다.
        for path, offset in self._postings.get(anchor.group(0), ()):
            start = offset - lead
            if start < 0:
                continue
            if path == consumed_path and start < consumed_until:
                continue
            text = self._contents[path]
            end = start + width
            if text[start:end] != term:
                continue
            if start > 0 and text[start - 1] in _WORD_CHARS:
                continue
            if end < len(text) and text[end] in _WORD_CHARS:
                continue
            consumed_path = path
            consumed_until = end
            results.append(self._at(path, start, term))
        results.sort(key=lambda item: (item.file_path, item.line, item.col))
        return results

    def _scan(self, term: str) -> List[Occurrence]:
        pattern = re.compile(rf"(?<![A-Za-z0-9_]){re.escape(term)}(?![A-Za-z0-9_])")
        results: List[Occurrence] = []
        for path in sorted(self._contents):
            for match in pattern.finditer(self._contents[path]):
                results.append(self._at(path, match.start(), match.group(0)))
        results.sort(key=lambda item: (item.file_path, item.line, item.col))
        return results

    def find_path(self, term: str) -> List[Occurrence]:
        results = []
        for path in sorted(self._contents):
            start = 0
            while True:
                offset = path.find(term, start)
                if offset < 0:
                    break
                results.append(
                    Occurrence(path, 1, offset, term, "path", self._enclosing(path, 1), "path")
                )
                start = offset + max(1, len(term))
        return results

    def list_paths(self, paths: Sequence[str]) -> List[Occurrence]:
        return [
            Occurrence(path, 1, 0, path, "path", self._enclosing(path, 1), "path")
            for path in sorted(paths)
        ]


def encode_occurrence_blocks(
    groups: Sequence[Sequence[Occurrence]],
    rows_per_block: int,
) -> Tuple[List[OccurrenceBlock], List[List[OccurrenceRange]]]:
    if rows_per_block < 1:
        raise OccurrenceStoreError("rows_per_block must be >= 1")
    blocks: List[OccurrenceBlock] = []
    ranges: List[List[OccurrenceRange]] = []
    absolute = 0
    for group in groups:
        group_ranges = []
        position = 0
        while position < len(group):
            chunk = list(group[position:position + rows_per_block])
            raw = json.dumps(
                [asdict(item) for item in chunk],
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
            ).encode("utf-8")
            compressed = gzip.compress(raw, compresslevel=9, mtime=0)
            block_id = f"o:{len(blocks):08d}"
            blocks.append(
                OccurrenceBlock(
                    id=block_id,
                    start=absolute,
                    end=absolute + len(chunk),
                    count=len(chunk),
                    sha256=hashlib.sha256(raw).hexdigest(),
                    encoding="gzip+base64",
                    data=base64.b64encode(compressed).decode("ascii"),
                )
            )
            group_ranges.append(OccurrenceRange(block_id, 0, len(chunk)))
            absolute += len(chunk)
            position += len(chunk)
        ranges.append(group_ranges)
    return blocks, ranges


def decode_occurrence_block(block: OccurrenceBlock) -> List[Occurrence]:
    try:
        if block.encoding != "gzip+base64":
            raise ValueError(f"unsupported encoding {block.encoding!r}")
        if block.count < 0 or block.end - block.start != block.count:
            raise ValueError("invalid block range/count")
        raw = gzip.decompress(base64.b64decode(block.data, validate=True))
        if hashlib.sha256(raw).hexdigest() != block.sha256:
            raise ValueError("digest mismatch")
        values = json.loads(raw)
        if not isinstance(values, list) or len(values) != block.count:
            raise ValueError("row count mismatch")
        return [Occurrence(**value) for value in values]
    except Exception as error:
        raise OccurrenceStoreError(f"corrupt occurrence block {block.id}: {error}") from error


def decode_occurrence_ranges(
    ranges: Sequence[OccurrenceRange],
    blocks: Sequence[OccurrenceBlock],
) -> List[Occurrence]:
    by_id = {block.id: block for block in blocks}
    result = []
    for occurrence_range in ranges:
        block = by_id.get(occurrence_range.block_id)
        if block is None:
            raise OccurrenceStoreError(
                f"unknown occurrence block {occurrence_range.block_id}"
            )
        if (
            occurrence_range.start < 0
            or occurrence_range.count < 0
            or occurrence_range.start + occurrence_range.count > block.count
        ):
            raise OccurrenceStoreError(
                f"invalid occurrence range for block {occurrence_range.block_id}"
            )
        rows = decode_occurrence_block(block)
        start = occurrence_range.start
        result.extend(rows[start:start + occurrence_range.count])
    return result


def enclosing_node_id(nodes: Sequence[ReadableNode], path: str, line: int) -> str:
    containing = [
        node for node in nodes
        if node.start_line is not None and node.end_line is not None
        and node.start_line <= line <= node.end_line
    ]
    if containing:
        return min(containing, key=lambda node: (node.end_line - node.start_line, node.id)).id
    file_id = f"file:{path}"
    if any(node.id == file_id for node in nodes):
        return file_id
    return min((node.id for node in nodes), default=file_id)
