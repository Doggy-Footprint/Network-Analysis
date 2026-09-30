"""VO-1: short_labels (Python) against independent, hand-computed expected
values from spec Cases C-1..C-4 (FR-1). The JS counterpart lived in report/m1
and is archived with it.

Technique: equivalence partitioning + boundary value (2-value).
Coverage items (7): 무충돌, 1단계 충돌, 다단계 충돌, 단일, 빈, 중복, 순서 반전.

Expected values are computed by hand from FR-1's algorithm description, not by
invoking report/shared/labels.py.
"""
import unittest

from report.shared.labels import short_labels


# Independently hand-computed expected results for each labelled Case.
CASES = {
    "C-1_no_conflict": (
        ["app/src/main/a/Foo.kt", "app/src/main/b/Bar.kt"],
        {"app/src/main/a/Foo.kt": "Foo.kt", "app/src/main/b/Bar.kt": "Bar.kt"},
    ),
    "C-2_one_level_conflict": (
        ["app/src/ui/Button.kt", "app/src/data/Button.kt", "app/src/X.kt"],
        {
            "app/src/ui/Button.kt": "ui/Button.kt",
            "app/src/data/Button.kt": "data/Button.kt",
            "app/src/X.kt": "X.kt",
        },
    ),
    "C-4_multi_level_conflict": (
        ["x/a/m/f.py", "y/a/m/f.py"],
        {"x/a/m/f.py": "x/a/m/f.py", "y/a/m/f.py": "y/a/m/f.py"},
    ),
    "C-4_multi_level_conflict_reversed": (
        ["y/a/m/f.py", "x/a/m/f.py"],
        {"x/a/m/f.py": "x/a/m/f.py", "y/a/m/f.py": "y/a/m/f.py"},
    ),
    "C-3_single": (
        ["a/b/c.py"],
        {"a/b/c.py": "c.py"},
    ),
    "C-3_empty": (
        [],
        {},
    ),
    "C-3_duplicate": (
        ["a/b/c.py", "a/b/c.py"],
        {"a/b/c.py": "c.py"},
    ),
}


class TestShortLabelsPython(unittest.TestCase):
    """VO-1: `short_labels` unit tests, one per coverage item."""

    def test_C1_no_conflict(self):
        paths, expected = CASES["C-1_no_conflict"]
        self.assertEqual(short_labels(paths), expected)

    def test_C2_one_level_conflict(self):
        paths, expected = CASES["C-2_one_level_conflict"]
        self.assertEqual(short_labels(paths), expected)

    def test_C4_multi_level_conflict(self):
        paths, expected = CASES["C-4_multi_level_conflict"]
        self.assertEqual(short_labels(paths), expected)

    def test_C4_multi_level_conflict_order_reversed_is_deterministic(self):
        paths, expected = CASES["C-4_multi_level_conflict_reversed"]
        self.assertEqual(short_labels(paths), expected)
        forward_paths, _ = CASES["C-4_multi_level_conflict"]
        self.assertEqual(short_labels(paths), short_labels(forward_paths))

    def test_C3_single_path_is_basename(self):
        paths, expected = CASES["C-3_single"]
        self.assertEqual(short_labels(paths), expected)

    def test_C3_empty_input_is_empty_dict(self):
        paths, expected = CASES["C-3_empty"]
        self.assertEqual(short_labels(paths), expected)

    def test_C3_duplicate_input_collapses_to_one_key(self):
        paths, expected = CASES["C-3_duplicate"]
        result = short_labels(paths)
        self.assertEqual(result, expected)
        self.assertEqual(len(result), 1)


if __name__ == "__main__":
    unittest.main()
