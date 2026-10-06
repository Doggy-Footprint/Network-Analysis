import bisect
import re
from typing import Dict, List, Tuple


class NamePositions:
    def __init__(self, text: str):
        self.text = text
        self.names: Dict[str, List[Tuple[int, int]]] = {}
        self.tokens = []
        self.token_starts = []
        self._orders = {}
        self._range_names = {}
        for match in re.finditer(r"\w+", text):
            self.names.setdefault(match.group(), []).append((match.start(), match.end()))
            self.tokens.append((match.start(), match.end(), match.group()))
            self.token_starts.append(match.start())
        self.fallback: Dict[str, List[Tuple[int, int]]] = {}
        self.line_starts = [0, *(match.end() for match in re.finditer("\n", text))]

    def candidate_names(self, order, start=0, end=None):
        if end is None:
            end = len(self.text)
        order_id = id(order)
        if order_id not in self._orders:
            fallback = tuple(name for name in order if not re.fullmatch(r"\w+", name))
            self._orders[order_id] = (order, fallback)
        key = (order_id, start, end)
        if key in self._range_names:
            return self._range_names[key]
        found = set()
        left = max(0, bisect.bisect_right(self.token_starts, start) - 1)
        right = bisect.bisect_left(self.token_starts, end)
        for lo, hi, name in self.tokens[left:right]:
            if hi <= start:
                continue
            clipped = self.text[max(lo, start):min(hi, end)] if lo < start or hi > end else name
            if clipped in order:
                found.add(clipped)
        for name in self._orders[order_id][1]:
            if self.matches(name, start, end):
                found.add(name)
        result = tuple(sorted(found, key=order.__getitem__))
        self._range_names[key] = result
        return result

    def matches(self, name: str, start: int = 0, end: int = None) -> List[Tuple[int, int]]:
        if end is None:
            end = len(self.text)
        if re.fullmatch(r"\w+", name):
            positions = self.names.get(name, [])
        else:
            if name not in self.fallback:
                self.fallback[name] = [(match.start(), match.end()) for match in re.finditer(rf"\b{re.escape(name)}\b", self.text)]
            positions = self.fallback[name]
        left = bisect.bisect_left(positions, (start, -1))
        right = bisect.bisect_right(positions, (end, -1))
        results = [pair for pair in positions[left:right] if pair[1] <= end]
        # Regex boundaries at a sliced declaration/header may differ from the complete file.
        if (start and re.match(r"\w", self.text[start - 1:start]) or end < len(self.text) and re.match(r"\w", self.text[end:end + 1])):
            pattern = re.compile(rf"\b{re.escape(name)}\b")
            sliced = self.text[start:end]
            for position in (0, len(sliced) - len(name)):
                if position < 0:
                    continue
                match = pattern.match(sliced, position)
                if match:
                    pair = (start + match.start(), start + match.end())
                    if pair not in results:
                        results.append(pair)
            results.sort()
        return results

    def line(self, offset: int) -> int:
        return bisect.bisect_right(self.line_starts, offset)
