"""Native regression for the CM user-supplied STEP worker route."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path


PACKAGE_DIR = Path(__file__).resolve().parents[1]
if str(PACKAGE_DIR) not in sys.path:
    sys.path.insert(0, str(PACKAGE_DIR))

import FreeCAD as App
import Part

from Allshield_FreeCAD_Worker import run_job
from airkan_builder.rules import defaults


def run(outdir):
    out = Path(outdir).expanduser().resolve()
    out.mkdir(parents=True, exist_ok=False)
    source_path = out / "user_plenum.step"
    source_document = App.newDocument("CM_Test_Source")
    try:
        source_object = source_document.addObject("Part::Feature", "KnownBox")
        source_object.Shape = Part.makeBox(100, 200, 300)
        Part.export([source_object], str(source_path))
    finally:
        App.closeDocument(source_document.Name)

    parameters = dict(
        defaults("CM"),
        prefix="TEST",
        description="Test plenum",
        source_step=str(source_path),
        material="GALVA",
        thickness_mm=1.2,
        area_rate_eur_per_m2=33.8,
    )
    buy_parameters = dict(
        defaults("BUY"),
        prefix="TEST",
        supplier="Renson",
        article_code="411/900",
        description="Buitenrooster",
        source_step=str(source_path),
        a_mm=900,
        b_mm=700,
        airflow_role="AANZUIG",
        price_status="ON_REQUEST",
        unit_price_eur=0,
        price_source="Leverancierspagina",
    )
    job_directory = out / "job"
    job_directory.mkdir()
    job_path = job_directory / "job.json"
    job_path.write_text(json.dumps({
        "schema": "allshield-freecad-job-v1",
        "items": [
            {
                "id": "A-10",
                "parameters": parameters,
                "connections": [],
                "connection_fingerprint": "",
                "from": "",
                "to": "",
                "connection_errors": "",
            },
            {
                "id": "A-20",
                "parameters": buy_parameters,
                "connections": [],
                "connection_fingerprint": "",
                "from": "",
                "to": "",
                "connection_errors": "",
            },
        ],
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    report = run_job(job_path)
    if not report["passed"]:
        raise RuntimeError(report["items"][0].get("error", "CM-worker mislukt."))
    row = report["items"][0]
    payload = json.loads(Path(row["paths"]["parameters"]).read_text(encoding="utf-8"))
    exported_shape = Part.read(row["paths"]["step"])
    buy_row = report["items"][1]
    buy_payload = json.loads(Path(buy_row["paths"]["parameters"]).read_text(encoding="utf-8"))
    buy_exported_shape = Part.read(buy_row["paths"]["step"])
    expected_hash = hashlib.sha256(source_path.read_bytes()).hexdigest()
    checks = {
        "worker_passed": row["passed"],
        "source_hash": payload["derived"]["source_step_sha256"] == expected_hash,
        "solid_count": len(exported_shape.Solids) == 1 == payload["validation"]["valid_solids"],
        "surface_area_mm2": payload["derived"]["surface_area_mm2"] == 220000.0,
        "one_sided_price_area_m2": payload["derived"]["one_sided_price_area_m2"] == 0.11,
        "total_not_persisted": "unit_price_eur" not in payload["order"] and "unit_price_eur" not in payload["derived"],
        "price_status": payload["order"]["pricing_status"] == "AREA_MEASURED",
        "step_reread": payload["validation"]["step_reread"] == "PASS",
        "project_item": payload["project_item"]["id"] == "A-10" and bool(payload["project_item"]["build_fingerprint"]),
        "buy_worker_passed": buy_row["passed"],
        "buy_identity": buy_payload["parameters"]["family"] == "BUY" and buy_payload["order"]["supplier"] == "Renson" and buy_payload["order"]["article_code"] == "411/900",
        "buy_source_hash": buy_payload["derived"]["source_step_sha256"] == expected_hash,
        "buy_solid_count": len(buy_exported_shape.Solids) == 1 == buy_payload["validation"]["valid_solids"],
        "buy_on_request": buy_payload["order"]["pricing_status"] == "ON_REQUEST" and "unit_price_eur" not in buy_payload["order"],
    }
    validation = {"schema": "allshield-imported-step-validation-v1", "checks": checks, "passed": all(checks.values()), "worker_result": report}
    (out / "validation_cm_import.json").write_text(json.dumps(validation, ensure_ascii=False, indent=2), encoding="utf-8")
    if not validation["passed"]:
        raise RuntimeError("CM-importvalidatie faalde: " + json.dumps(checks, sort_keys=True))
    return validation


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=os.environ.get("AIRKAN_IMPORTED_STEP_TEST_OUT"))
    arguments = parser.parse_args()
    if not arguments.out:
        parser.error("--out of AIRKAN_IMPORTED_STEP_TEST_OUT is verplicht")
    report = run(arguments.out)
    print(json.dumps(report["checks"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())