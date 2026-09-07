import unittest
from pathlib import Path


class M0DocumentationContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).resolve().parents[1]
        cls.readme = (root / "README.md").read_text(encoding="utf-8")
        cls.roadmap = (root / "ROADMAP.md").read_text(encoding="utf-8")

    def test_roadmap_records_m0_as_complete_and_classifies_existing_features(self):
        self.assertIn("### M0. 문서 및 계약 재정렬 — 완료", self.roadmap)
        self.assertIn(
            "| Keep | language and framework analyzers, static relations and evidence, "
            "graph metrics including effective and weighted measures, renderers |",
            self.roadmap,
        )
        self.assertIn(
            "| Replace or extend | the existing symbol graph becomes M1 readable and query "
            "nodes; serialization and CLI output extend per milestone contract. Current "
            "graph metrics are M5 input and do not constitute M5 completion. |",
            self.roadmap,
        )
        self.assertIn(
            "| Remove | previous exploration cost, task difficulty, repository cost diff, "
            "git diff impact analysis, structural friction diagnostics, Android "
            "inject-field arbitrary costs and warnings |",
            self.roadmap,
        )

    def test_roadmap_records_m1_as_complete(self):
        self.assertIn("### M1. 에이전트 관점 그래프 — 완료", self.roadmap)

    def test_readme_states_its_blankness_is_intentional_and_only_points_at_documents(self):
        self.assertIn("Left blank for intent.", self.readme)
        self.assertIn("[ROADMAP.md](ROADMAP.md)", self.readme)
        self.assertNotIn("## Graph model", self.readme)
        self.assertNotIn("## Cost contract", self.readme)
        self.assertLess(len(self.readme), len(self.roadmap))


if __name__ == "__main__":
    unittest.main()
