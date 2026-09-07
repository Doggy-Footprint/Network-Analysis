import unittest

from language_analyzers.core.cost import (
    CHARACTERS_PER_TOKEN,
    DIGIT_GROUP_SIZE,
    TOKENIZER_VERSION,
    cost_for_text,
    estimate_tokens,
)


class TokenizerContractTests(unittest.TestCase):
    def test_documented_defaults_and_version(self):
        self.assertEqual(CHARACTERS_PER_TOKEN, 4.0)
        self.assertEqual(DIGIT_GROUP_SIZE, 3)
        self.assertEqual(TOKENIZER_VERSION, "chars-div4-digit-group3-v1")

    def test_edge_cases(self):
        cases = {
            "": 1,
            "a": 1,
            "abcd": 1,
            "abcde": 2,
            "1": 1,
            "12": 1,
            "123": 1,
            "1234": 2,
            "1234567": 3,
            "v2": 2,
            "a1234b": 3,
            "abcd1234": 3,
            "a1b22c333": 4,
            "x = 1\n": 3,
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(estimate_tokens(text), expected)

    def test_only_ascii_digits_are_grouped(self):
        self.assertEqual(estimate_tokens("２３４"), 1)

    def test_both_tokenizer_parameters_are_injectable(self):
        self.assertEqual(estimate_tokens("abcdefgh1234", 8, 2), 3)

    def test_cost_for_text_reports_chars_and_lines_next_to_the_token_estimate(self):
        cost = cost_for_text("a1b22c333")

        self.assertEqual(cost.token_estimate, 4)
        self.assertEqual(cost.char_count, 9)
        self.assertEqual(cost.line_count, 1)


if __name__ == "__main__":
    unittest.main()
