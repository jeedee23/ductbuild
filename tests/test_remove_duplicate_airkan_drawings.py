from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = (
    Path(__file__).parents[1]
    / "scripts"
    / "remove_duplicate_airkan_drawings.py"
)
SPEC = importlib.util.spec_from_file_location(
    "remove_duplicate_airkan_drawings",
    SCRIPT,
)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class RemoveDuplicateAirkanDrawingsTests(unittest.TestCase):
    def test_finds_exact_duplicates_and_keeps_first_path(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            first = root / "a" / "drawing.png"
            duplicate = root / "b" / "drawing.png"
            different = root / "c" / "drawing.png"
            for path in (first, duplicate, different):
                path.parent.mkdir()
            first.write_bytes(b"same")
            duplicate.write_bytes(b"same")
            different.write_bytes(b"different")

            duplicates = MODULE.find_duplicates(root)

            self.assertEqual(len(duplicates), 1)
            self.assertEqual(duplicates[0].kept, first)
            self.assertEqual(duplicates[0].removed, duplicate)


if __name__ == "__main__":
    unittest.main()
