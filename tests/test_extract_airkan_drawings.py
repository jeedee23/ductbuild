from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts" / "extract_airkan_drawings.py"
SPEC = importlib.util.spec_from_file_location("extract_airkan_drawings", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class ExtractAirkanDrawingsTests(unittest.TestCase):
    def test_extracts_short_code_from_dimension_definition(self) -> None:
        self.assertEqual(MODULE.extract_code("PSA - Ø1 - Ø2"), ("PSA", False))
        self.assertEqual(MODULE.extract_code("GE60XL - H - B"), ("GE60XL", False))

    def test_extracts_and_normalizes_code_label(self) -> None:
        self.assertEqual(MODULE.extract_code("Code: P .BI"), ("P.BI", True))
        self.assertEqual(MODULE.extract_code("Code: SL.E20 &"), ("SL.E20", True))

    def test_sanitizes_windows_filename_characters(self) -> None:
        self.assertEqual(MODULE.sanitize_filename("DD:15 / Ø"), "DD_15 _ Ø")

    def test_line_art_classifier_rejects_photos(self) -> None:
        drawing = MODULE.ImageMetrics(0.15, 0.06, 2.1, 7.0, 0.09)
        photo = MODULE.ImageMetrics(0.93, 0.18, 5.8, 7.0, 0.07)
        dark_photo = MODULE.ImageMetrics(0.20, 0.15, 3.0, 6.0, 0.03)
        isolated_photo = MODULE.ImageMetrics(0.25, 0.02, 2.2, 5.3, 0.03)
        self.assertTrue(MODULE.is_technical_line_art(drawing, 193))
        self.assertFalse(MODULE.is_technical_line_art(photo, 193))
        self.assertFalse(MODULE.is_technical_line_art(dark_photo, 193))
        self.assertFalse(MODULE.is_technical_line_art(isolated_photo, 193))


if __name__ == "__main__":
    unittest.main()
