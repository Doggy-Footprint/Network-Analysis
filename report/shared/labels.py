from typing import Dict, Iterable, List


def _segments(path: str) -> List[str]:
    parts = [segment for segment in path.split("/") if segment != ""]
    return parts if parts else [path]


def _suffix(segments: List[str], depth: int) -> str:
    return "/".join(segments[max(0, len(segments) - depth):])


def short_labels(paths: Iterable[str]) -> Dict[str, str]:
    unique_paths = list(dict.fromkeys(paths))
    if not unique_paths:
        return {}

    segments_by_path = {path: _segments(path) for path in unique_paths}
    groups: Dict[str, List[str]] = {}
    for path in unique_paths:
        basename = segments_by_path[path][-1]
        groups.setdefault(basename, []).append(path)

    labels: Dict[str, str] = {}
    for basename, group_paths in groups.items():
        if len(group_paths) == 1:
            labels[group_paths[0]] = basename
            continue
        max_depth = max(len(segments_by_path[path]) for path in group_paths)
        depth = 2
        while True:
            candidates = {path: _suffix(segments_by_path[path], depth) for path in group_paths}
            counts: Dict[str, int] = {}
            for label in candidates.values():
                counts[label] = counts.get(label, 0) + 1
            if all(counts[label] == 1 for label in candidates.values()) or depth >= max_depth:
                labels.update(candidates)
                break
            depth += 1
    return labels
