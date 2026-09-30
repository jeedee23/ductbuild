from __future__ import annotations

import argparse
import csv
import re
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
import pymupdf


INVALID_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
CODE_PREFIX = re.compile(r"^Code\s*:\s*(.+)$", re.IGNORECASE)
DIMENSION_DEFINITION = re.compile(
    r"^([A-Z][A-Z0-9. αΑ-]{0,18}?)\s+-\s+(?:Ø|[A-Z]|\d)",
)
SHORT_CODE = re.compile(r"^[A-Z][A-Z0-9.]{0,12}$")


@dataclass(frozen=True)
class TextLine:
    text: str
    bbox: pymupdf.Rect
    is_code_label: bool


@dataclass(frozen=True)
class ImageMetrics:
    nonwhite_ratio: float
    dark_ratio: float
    entropy: float
    ink_entropy: float
    edge_ratio: float


@dataclass(frozen=True)
class DrawingCandidate:
    page_number: int
    image_number: int
    bbox: pymupdf.Rect
    intrinsic_width: int
    intrinsic_height: int
    code: str
    metrics: ImageMetrics


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Move each direct AIRKAN PDF into a same-named folder and extract "
            "technical drawing images as code-named PNG files."
        ),
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path("shared") / "sources" / "pdf" / "airkan",
        help="Folder whose direct child PDFs are processed.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Analyze PDFs and print planned outputs without moving or writing files.",
    )
    return parser.parse_args()


def sanitize_filename(value: str) -> str:
    value = value.replace("\u00d8", "Ø").strip()
    value = re.sub(r"\s*\.\s*", ".", value)
    value = re.sub(r"\s+", " ", value)
    value = value.rstrip(" .&-")
    value = INVALID_FILENAME_CHARS.sub("_", value)
    return value or "drawing"


def extract_code(text: str) -> tuple[str, bool] | None:
    text = text.strip()
    code_match = CODE_PREFIX.match(text)
    if code_match:
        value = code_match.group(1).strip()
        value = re.split(r"\s+-\s+(?:Ø|[A-Z]\b|\d)", value, maxsplit=1)[0]
        return sanitize_filename(value), True

    definition_match = DIMENSION_DEFINITION.match(text)
    if definition_match:
        return sanitize_filename(definition_match.group(1)), False

    return None


def page_text_lines(page: pymupdf.Page) -> list[TextLine]:
    lines: list[TextLine] = []
    for block in page.get_text("dict")["blocks"]:
        for line in block.get("lines", []):
            text = "".join(span["text"] for span in line["spans"]).strip()
            if not text:
                continue
            parsed = extract_code(text)
            if parsed is not None:
                code, is_code_label = parsed
                lines.append(TextLine(code, pymupdf.Rect(line["bbox"]), is_code_label))
                continue

            bbox = pymupdf.Rect(line["bbox"])
            if (
                88 <= bbox.y0 <= 180
                and bbox.x0 < 180
                and SHORT_CODE.fullmatch(text)
            ):
                lines.append(TextLine(sanitize_filename(text), bbox, False))
    return lines


def fallback_page_name(page: pymupdf.Page, pdf_stem: str) -> str:
    header_lines: list[tuple[float, str]] = []
    title_lines: list[tuple[float, str]] = []
    for block in page.get_text("dict")["blocks"]:
        for line in block.get("lines", []):
            text = "".join(span["text"] for span in line["spans"]).strip()
            if not text:
                continue
            bbox = pymupdf.Rect(line["bbox"])
            if 55 <= bbox.y0 <= 84:
                if (
                    bbox.x0 > 420
                    and len(text) <= 45
                    and "Hoofdstuk" not in text
                ):
                    header_lines.append((bbox.y0, text))
                elif bbox.x0 > 230 and "Hoofdstuk" not in text:
                    title_lines.append((bbox.y0, text))

    if header_lines:
        return sanitize_filename(
            " ".join(text for _, text in sorted(header_lines)),
        )
    if title_lines:
        return sanitize_filename(
            " ".join(text for _, text in sorted(title_lines)),
        )
    return sanitize_filename(pdf_stem)


def render_image_region(
    page: pymupdf.Page,
    bbox: pymupdf.Rect,
    intrinsic_width: int,
    intrinsic_height: int,
) -> tuple[pymupdf.Pixmap, np.ndarray]:
    horizontal_scale = intrinsic_width / max(bbox.width, 1)
    vertical_scale = intrinsic_height / max(bbox.height, 1)
    scale = max(1.0, min(4.0, horizontal_scale, vertical_scale))
    pixmap = page.get_pixmap(
        matrix=pymupdf.Matrix(scale, scale),
        clip=bbox,
        alpha=False,
        colorspace=pymupdf.csRGB,
    )
    rgb = np.frombuffer(pixmap.samples, dtype=np.uint8).reshape(
        pixmap.height,
        pixmap.width,
        3,
    )
    return pixmap, rgb


def calculate_metrics(rgb: np.ndarray) -> ImageMetrics:
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    histogram = np.bincount(gray.ravel(), minlength=256)
    probabilities = histogram[histogram > 0] / gray.size
    entropy = float(-(probabilities * np.log2(probabilities)).sum())
    ink = gray[gray < 245]
    ink_histogram = np.bincount(ink, minlength=256)
    ink_probabilities = ink_histogram[ink_histogram > 0] / max(ink.size, 1)
    ink_entropy = float(
        -(ink_probabilities * np.log2(ink_probabilities)).sum(),
    )
    edges = cv2.Canny(gray, 80, 180)
    return ImageMetrics(
        nonwhite_ratio=float(np.mean(gray < 245)),
        dark_ratio=float(np.mean(gray < 180)),
        entropy=entropy,
        ink_entropy=ink_entropy,
        edge_ratio=float(np.mean(edges > 0)),
    )


def is_technical_line_art(
    metrics: ImageMetrics,
    intrinsic_width: int,
) -> bool:
    if metrics.nonwhite_ratio >= 0.8 or metrics.entropy >= 4.2:
        return False
    if metrics.edge_ratio < 0.012:
        return False
    if intrinsic_width < 300:
        edge_to_dark = metrics.edge_ratio / max(metrics.dark_ratio, 0.001)
        if edge_to_dark < 0.65:
            return False
        if metrics.nonwhite_ratio > 0.2 and metrics.ink_entropy < 5.5:
            return False
    return True


def horizontal_distance(first: pymupdf.Rect, second: pymupdf.Rect) -> float:
    if first.x1 < second.x0:
        return second.x0 - first.x1
    if second.x1 < first.x0:
        return first.x0 - second.x1
    return 0.0


def match_code(
    image_bbox: pymupdf.Rect,
    labels: list[TextLine],
    fallback: str,
) -> str:
    matches: list[tuple[float, TextLine]] = []
    for label in labels:
        if label.is_code_label:
            distance_below = label.bbox.y0 - image_bbox.y1
            distance_above = image_bbox.y0 - label.bbox.y1
            if -5 <= distance_below <= 32 or -5 <= distance_above <= 48:
                score = min(
                    abs(distance_below),
                    abs(distance_above),
                ) + horizontal_distance(
                    image_bbox,
                    label.bbox,
                )
                matches.append((score, label))
        else:
            vertical_distance = image_bbox.y0 - label.bbox.y1
            if -5 <= vertical_distance <= 48:
                score = abs(vertical_distance) + horizontal_distance(
                    image_bbox,
                    label.bbox,
                )
                matches.append((score, label))

    if not matches:
        return fallback
    return min(matches, key=lambda item: item[0])[1].text


def find_candidates(
    document: pymupdf.Document,
    pdf_stem: str,
) -> list[DrawingCandidate]:
    candidates: list[DrawingCandidate] = []
    for page_index, page in enumerate(document):
        labels = page_text_lines(page)
        fallback = fallback_page_name(page, pdf_stem)
        for image_number, image in enumerate(page.get_image_info(), start=1):
            bbox = pymupdf.Rect(image["bbox"])
            if bbox.y0 <= 94 or bbox.width < 60 or bbox.height < 35:
                continue

            _, rgb = render_image_region(
                page,
                bbox,
                image["width"],
                image["height"],
            )
            metrics = calculate_metrics(rgb)
            if not is_technical_line_art(metrics, image["width"]):
                continue

            code = match_code(bbox, labels, fallback)
            candidates.append(
                DrawingCandidate(
                    page_number=page_index + 1,
                    image_number=image_number,
                    bbox=bbox,
                    intrinsic_width=image["width"],
                    intrinsic_height=image["height"],
                    code=code,
                    metrics=metrics,
                ),
            )
    return candidates


def unique_output_path(
    output_folder: Path,
    code: str,
    used_names: set[str],
) -> Path:
    base = sanitize_filename(code)
    candidate = base
    suffix = 2
    while candidate.casefold() in used_names or (output_folder / f"{candidate}.png").exists():
        candidate = f"{base}_{suffix}"
        suffix += 1
    used_names.add(candidate.casefold())
    return output_folder / f"{candidate}.png"


def write_candidate(
    document: pymupdf.Document,
    candidate: DrawingCandidate,
    output_path: Path,
) -> None:
    page = document[candidate.page_number - 1]
    pixmap, _ = render_image_region(
        page,
        candidate.bbox,
        candidate.intrinsic_width,
        candidate.intrinsic_height,
    )
    pixmap.save(output_path)


def organize_and_extract(
    source_pdf: Path,
    dry_run: bool,
) -> list[dict[str, str]]:
    output_folder = source_pdf.parent / source_pdf.stem
    destination_pdf = output_folder / source_pdf.name

    with pymupdf.open(source_pdf) as document:
        candidates = find_candidates(document, source_pdf.stem)

    used_names: set[str] = set()
    rows: list[dict[str, str]] = []
    for candidate in candidates:
        output_path = unique_output_path(
            output_folder,
            candidate.code,
            used_names,
        )
        rows.append(
            {
                "source_pdf": source_pdf.name,
                "page": str(candidate.page_number),
                "code": candidate.code,
                "png": output_path.name,
                "status": "planned" if dry_run else "extracted",
            },
        )

    if dry_run:
        for row in rows:
            print(
                f"PLAN {row['source_pdf']} page {row['page']} "
                f"-> {output_folder.name}\\{row['png']}",
            )
        if not rows:
            print(f"PLAN {source_pdf.name}: no technical drawings detected")
        return rows

    output_folder.mkdir(exist_ok=False)
    shutil.move(str(source_pdf), destination_pdf)
    try:
        with pymupdf.open(destination_pdf) as moved_document:
            used_names.clear()
            for candidate, row in zip(candidates, rows, strict=True):
                output_path = unique_output_path(
                    output_folder,
                    candidate.code,
                    used_names,
                )
                write_candidate(moved_document, candidate, output_path)
                row["png"] = output_path.name
    except Exception:
        if destination_pdf.exists() and not source_pdf.exists():
            shutil.move(str(destination_pdf), source_pdf)
        if output_folder.exists() and not any(output_folder.iterdir()):
            output_folder.rmdir()
        raise

    print(
        f"DONE {source_pdf.name}: moved PDF and extracted "
        f"{len(rows)} drawing(s)",
    )
    return rows


def write_manifest(root: Path, rows: list[dict[str, str]]) -> None:
    manifest = root / "_airkan_extraction_manifest.csv"
    with manifest.open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=("source_pdf", "page", "code", "png", "status"),
        )
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    if sys.stdout.encoding:
        sys.stdout.reconfigure(errors="backslashreplace")
        sys.stderr.reconfigure(errors="backslashreplace")

    arguments = parse_arguments()
    root = arguments.root.resolve()
    if not root.is_dir():
        raise FileNotFoundError(f"AIRKAN folder does not exist: {root}")

    source_pdfs = sorted(root.glob("*.pdf"), key=lambda path: path.name.casefold())
    if not source_pdfs:
        print(f"No direct child PDFs found in {root}")
        return 0

    all_rows: list[dict[str, str]] = []
    for source_pdf in source_pdfs:
        output_folder = source_pdf.parent / source_pdf.stem
        if output_folder.exists():
            raise FileExistsError(
                f"Refusing to merge with existing output folder: {output_folder}",
            )
        all_rows.extend(organize_and_extract(source_pdf, arguments.dry_run))

    if not arguments.dry_run:
        write_manifest(root, all_rows)
    print(
        f"{'Planned' if arguments.dry_run else 'Extracted'} "
        f"{len(all_rows)} drawing(s) from {len(source_pdfs)} PDF(s)",
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"ERROR: {error}", file=sys.stderr)
        raise
