import json
import unittest
from pathlib import Path

from manifest_json import dump_json


class FakeArray:
    def tolist(self):
        return [1, 2, 3]


class ManifestJsonTest(unittest.TestCase):
    def test_serializes_paths_and_array_like_values(self):
        encoded = dump_json({"path": Path("/tmp/example"), "array": FakeArray()})
        self.assertEqual(
            json.loads(encoded),
            {"path": "/tmp/example", "array": [1, 2, 3]},
        )


if __name__ == "__main__":
    unittest.main()
