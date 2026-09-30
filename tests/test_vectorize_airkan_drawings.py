from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw


SCRIPT = Path(__file__).parents[1] / "scripts" / "vectorize_airkan_drawings.py"
SPEC = importlib.util.spec_from_file_location("vectorize_airkan_drawings", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class VectorizeAirkanDrawingsTests(unittest.TestCase):
    def test_svg_contains_paths_and_no_embedded_image(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            folder = root / "sample"
            folder.mkdir()
            png_path = folder / "drawing.png"
            svg_path = folder / "drawing.svg"
            image = Image.new("RGB", (80, 60), "white")
            draw = ImageDraw.Draw(image)
            draw.rectangle((10, 10, 70, 50), outline="black", width=2)
            draw.line((15, 30, 65, 30), fill="black", width=1)
            image.save(png_path)

            MODULE.vectorize_png(png_path, svg_path, root)

            svg_text = svg_path.read_text(encoding="utf-8")
            root_element = ET.fromstring(svg_text)
            paths = root_element.findall(f".//{{{MODULE.SVG_NAMESPACE}}}path")
            images = root_element.findall(f".//{{{MODULE.SVG_NAMESPACE}}}image")
            self.assertTrue(paths)
            self.assertFalse(images)

    def test_krs_corrections_are_declared(self) -> None:
        corrections = MODULE.CORRECTIONS["dakdoorvoeren/KRS.png"]
        self.assertEqual([item.text for item in corrections], ["50", "50", "50"])

    def test_mask_to_path_preserves_binary_shape(self) -> None:
        mask = np.zeros((30, 40), dtype=np.uint8)
        cv2.rectangle(mask, (5, 5), (35, 25), 255, thickness=2)
        path = MODULE.mask_to_path(mask)
        self.assertIn("M", path)
        self.assertIn("L", path)
        self.assertIn("Z", path)


if __name__ == "__main__":
    unittest.main()
