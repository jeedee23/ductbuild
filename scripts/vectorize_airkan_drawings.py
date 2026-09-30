from __future__ import annotations

import argparse
import csv
import html
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
from PIL import Image


SVG_NAMESPACE = "http://www.w3.org/2000/svg"
ET.register_namespace("", SVG_NAMESPACE)


@dataclass(frozen=True)
class TextCorrection:
    clear_box: tuple[int, int, int, int]
    text: str
    x: float
    y: float
    rotation: float
    font_size: float


CORRECTIONS: dict[str, tuple[TextCorrection, ...]] = {
    "dakdoorvoeren/KRS.png": (
        TextCorrection((25, 31, 32, 39), "50", 29.5, 37.5, -90, 5.0),
        TextCorrection((25, 39, 32, 47), "50", 29.5, 45.5, -90, 5.0),
        TextCorrection((25, 132, 32, 141), "50", 29.5, 139.5, -90, 5.0),
    ),
}

TRACE_LAYERS = (
    (245, "#b8b8b8"),
    (210, "#888888"),
    (160, "#555555"),
    (100, "#222222"),
    (60, "#000000"),
)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Convert curated AIRKAN drawing PNGs into path-based SVGs.",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path("shared") / "sources" / "pdf" / "airkan",
    )
    parser.add_argument(
        "--files",
        type=Path,
        nargs="*",
        help="Optional PNG files to vectorize instead of every PNG below root.",
    )
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def load_grayscale(path: Path) -> np.ndarray:
    with Image.open(path) as image:
        rgb = np.asarray(image.convert("RGB"))
    return cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)


def apply_corrections(
    gray: np.ndarray,
    corrections: tuple[TextCorrection, ...],
) -> None:
    for correction in corrections:
        x0, y0, x1, y1 = correction.clear_box
        gray[y0:y1, x0:x1] = 255


def contour_to_path(contour: np.ndarray) -> str:
    points = contour.reshape(-1, 2)
    if len(points) < 3:
        return ""
    commands = [f"M{points[0, 0]} {points[0, 1]}"]
    commands.extend(f"L{x} {y}" for x, y in points[1:])
    commands.append("Z")
    return "".join(commands)


def mask_to_path(mask: np.ndarray) -> str:
    contours, _ = cv2.findContours(
        mask,
        cv2.RETR_TREE,
        cv2.CHAIN_APPROX_SIMPLE,
    )
    path_parts = []
    for contour in contours:
        if cv2.contourArea(contour) < 0.25:
            continue
        path = contour_to_path(contour)
        if path:
            path_parts.append(path)
    return "".join(path_parts)


def correction_elements(
    corrections: tuple[TextCorrection, ...],
) -> str:
    elements = []
    for correction in corrections:
        escaped_text = html.escape(correction.text)
        transform = (
            f' transform="rotate({correction.rotation:g} '
            f'{correction.x:g} {correction.y:g})"'
            if correction.rotation
            else ""
        )
        elements.append(
            f'<text x="{correction.x:g}" y="{correction.y:g}"'
            f'{transform} font-family="Arial, sans-serif" '
            f'font-size="{correction.font_size:g}" '
            f'text-anchor="middle" fill="#000000">{escaped_text}</text>',
        )
    if not elements:
        return ""
    return '<g id="confirmed-values">' + "".join(elements) + "</g>"


def vectorize_png(
    png_path: Path,
    svg_path: Path,
    root: Path,
) -> None:
    gray = load_grayscale(png_path)
    relative_key = png_path.relative_to(root).as_posix()
    corrections = CORRECTIONS.get(relative_key, ())
    apply_corrections(gray, corrections)
    vector_layers = []
    for threshold, color in TRACE_LAYERS:
        mask = np.where(gray < threshold, 255, 0).astype(np.uint8)
        path_data = mask_to_path(mask)
        if path_data:
            vector_layers.append(
                f'<path fill="{color}" d="{path_data}"/>',
            )
    if not vector_layers:
        raise ValueError(f"No vector paths found in {png_path}")

    height, width = gray.shape
    description = html.escape(
        f"Vectorized from {relative_key}; no raster image is embedded.",
    )
    correction_markup = correction_elements(corrections)
    svg = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<svg xmlns="{SVG_NAMESPACE}" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}">'
        f"<desc>{description}</desc>"
        '<g id="drawing" fill-rule="evenodd">'
        f'{"".join(vector_layers)}'
        "</g>"
        f"{correction_markup}"
        "</svg>\n"
    )
    svg_path.write_text(svg, encoding="utf-8")


def parse_svg(path: Path) -> ET.Element:
    return ET.parse(path).getroot()


def write_manifest(
    root: Path,
    rows: list[dict[str, str]],
) -> None:
    path = root / "_airkan_vectorization_manifest.csv"
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=("png", "svg", "corrections", "status"),
        )
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    arguments = parse_arguments()
    root = arguments.root.resolve()
    if arguments.files:
        png_paths = [path.resolve() for path in arguments.files]
    else:
        png_paths = sorted(
            root.glob("*/*.png"),
            key=lambda path: str(path.relative_to(root)).casefold(),
        )

    rows = []
    for png_path in png_paths:
        svg_path = png_path.with_suffix(".svg")
        if svg_path.exists() and not arguments.overwrite:
            raise FileExistsError(
                f"SVG already exists; use --overwrite: {svg_path}",
            )
        vectorize_png(png_path, svg_path, root)
        relative_png = png_path.relative_to(root).as_posix()
        corrections = CORRECTIONS.get(relative_png, ())
        rows.append(
            {
                "png": relative_png,
                "svg": svg_path.relative_to(root).as_posix(),
                "corrections": str(len(corrections)),
                "status": "vectorized",
            },
        )
        print(f"VECTORIZED {relative_png}")

    if not arguments.files:
        write_manifest(root, rows)
    print(f"Vectorized {len(rows)} PNG file(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
