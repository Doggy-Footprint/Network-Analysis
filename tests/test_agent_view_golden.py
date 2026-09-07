import unittest

from agent_view import SCHEMA_VERSION

class DeterminismGoldenTests(unittest.TestCase):
    def test_golden_contract_tracks_current_schema(self):
        self.assertEqual(SCHEMA_VERSION,"3")
