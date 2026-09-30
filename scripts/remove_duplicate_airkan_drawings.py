from __future__ import annotations

import argparse
import csv
import hashlib
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Duplicate:
    removed: Path
    kept: Path
    sha256: str


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Remove byte-identical AIRKAN drawing PNGs.",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path("shared") / "sources" / "pdf" / "airkan",
    )
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def find_duplicates(root: Path) -> list[Duplicate]:
    groups: dict[str, list[Path]] = defaultdict(list)
    for path in root.glob("*/*.png"):
        groups[sha256(path)].append(path)

    duplicates: list[Duplicate] = []
    for digest, paths in groups.items():
        if len(paths) < 2:
            continue
        ordered = sorted(
            paths,
            key=lambda path: str(path.relative_to(root)).casefold(),
        )
        kept = ordered[0]
        duplicates.extend(
            Duplicate(removed=removed, kept=kept, sha256=digest)
            for removed in ordered[1:]
        )
    return sorted(
        duplicates,
        key=lambda item: str(item.removed.relative_to(root)).casefold(),
    )


def update_manifest(root: Path, removed_paths: set[Path]) -> int:
    manifest = root / "_airkan_extraction_manifest.csv"
    with manifest.open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))

    retained = []
    for row in rows:
        folder = Path(row["source_pdf"]).stem
        png_path = (root / folder / row["png"]).resolve()
        if png_path not in removed_paths:
            retained.append(row)

    with manifest.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(retained)
    return len(retained)


def write_log(root: Path, duplicates: list[Duplicate]) -> None:
    log_path = root / "_airkan_duplicates_removed.csv"
    with log_path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=("removed_png", "kept_png", "sha256"),
        )
        writer.writeheader()
        for duplicate in duplicates:
            writer.writerow(
                {
                    "removed_png": str(duplicate.removed.relative_to(root)),
                    "kept_png": str(duplicate.kept.relative_to(root)),
                    "sha256": duplicate.sha256,
                },
            )


def main() -> int:
    arguments = parse_arguments()
    root = arguments.root.resolve()
    duplicates = find_duplicates(root)
    for duplicate in duplicates:
        verb = "WOULD REMOVE" if arguments.dry_run else "REMOVED"
        print(
            f"{verb} {duplicate.removed.relative_to(root)} "
            f"(kept {duplicate.kept.relative_to(root)})",
        )

    if arguments.dry_run:
        print(f"Would remove {len(duplicates)} exact duplicate PNG(s)")
        return 0

    removed_paths = {duplicate.removed.resolve() for duplicate in duplicates}
    for duplicate in duplicates:
        duplicate.removed.unlink()
    remaining = update_manifest(root, removed_paths)
    write_log(root, duplicates)
    print(
        f"Removed {len(duplicates)} exact duplicate PNG(s); "
        f"{remaining} manifest entries remain",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
