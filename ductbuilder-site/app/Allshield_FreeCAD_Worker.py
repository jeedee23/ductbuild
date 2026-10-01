"""Background FreeCAD worker for the standalone Allshield project GUI."""
from __future__ import annotations

import argparse
import json
import os
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path


sys.dont_write_bytecode = True
PACKAGE_DIR = Path(__file__).resolve().parent
if str(PACKAGE_DIR) not in sys.path:
    sys.path.insert(0, str(PACKAGE_DIR))

from airkan_builder.document import create_document, create_imported_step_document, export_step_json
from airkan_builder.rules import resolve
from allshield_project import build_fingerprint, output_basename, validate_item_id


JOB_SCHEMA = "allshield-freecad-job-v1"
RESULT_SCHEMA = "allshield-freecad-job-result-v1"


def _utc_now():
    return datetime.now(timezone.utc).isoformat()


def load_job(path):
    path = Path(path).resolve()
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema") != JOB_SCHEMA or not isinstance(payload.get("items"), list):
        raise ValueError("Invalid AAVDS FreeCAD job.")
    if not payload["items"]:
        raise ValueError("The FreeCAD job contains no components.")
    return path, payload


def run_job(job_path):
    import FreeCAD as App

    job_path, job = load_job(job_path)
    output_root = job_path.parent / "output"
    output_root.mkdir(parents=True, exist_ok=True)
    report = {
        "schema": RESULT_SCHEMA,
        "started_utc": _utc_now(),
        "freecad": App.Version(),
        "worker": str(Path(__file__).resolve()),
        "items": [],
    }
    for source_item in job["items"]:
        item_id = str(source_item.get("id", ""))
        row = {"id": item_id, "passed": False}
        document = None
        try:
            item_id = validate_item_id(item_id)
            parameters = dict(source_item["parameters"])
            resolved = resolve(parameters)
            item = {
                "id": item_id,
                "connection_fingerprint": str(source_item.get("connection_fingerprint", "")),
                "parameters": resolved["params"],
            }
            destination = output_root / item_id
            destination.mkdir(parents=True, exist_ok=True)
            if item["parameters"]["family"] in ("CM", "BUY"):
                document, root, objects, result = create_imported_step_document(item["parameters"])
            else:
                document, root, objects, result = create_document(item["parameters"], show_references=False)
            paths = export_step_json(
                document,
                root,
                objects,
                result,
                destination,
                basename=output_basename(item, result),
                project_item={
                    "id": item_id,
                    "from": str(source_item.get("from", "")).strip(),
                    "to": str(source_item.get("to", "")).strip(),
                    "connections": source_item.get("connections", []),
                    "connection_errors": str(source_item.get("connection_errors", "")).strip(),
                    "project_prefix": item["parameters"]["prefix"],
                    "build_fingerprint": build_fingerprint(item),
                },
            )
            row.update({
                "id": item_id,
                "passed": True,
                "paths": paths,
                "filename_stem": result["filename_stem"],
                "valid_solids": result["validation"]["valid_solids"],
                "warnings": result.get("warnings", []),
            })
        except Exception as error:
            row.update({
                "id": item_id,
                "error": str(error),
                "traceback": traceback.format_exc(),
            })
        finally:
            if document is not None:
                try:
                    App.closeDocument(document.Name)
                except Exception:
                    pass
        report["items"].append(row)
    report["completed_utc"] = _utc_now()
    report["passed"] = all(item["passed"] for item in report["items"])
    result_path = job_path.parent / "result.json"
    temporary = result_path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    os.replace(temporary, result_path)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description="Build Allshield project items with FreeCAD.")
    parser.add_argument("job", help="Path to an allshield-freecad-job-v1 JSON file")
    arguments = parser.parse_args(argv)
    report = run_job(arguments.job)
    print(json.dumps({
        "passed": report["passed"],
        "result": str(Path(arguments.job).resolve().parent / "result.json"),
        "items": len(report["items"]),
    }))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())