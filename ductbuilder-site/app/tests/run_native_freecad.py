"""Native FreeCAD document/export/reopen regression runner.

Run in a fresh process:
    FreeCADCmd.exe tests/run_native_freecad.py --out <new-empty-folder>
"""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path


PACKAGE_DIR = Path(__file__).resolve().parents[1]
if str(PACKAGE_DIR) not in sys.path:
    sys.path.insert(0, str(PACKAGE_DIR))
if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

import FreeCAD as App

import airkan_builder
from airkan_builder.document import bom_from_document, create_document, export_document
from airkan_builder.geometry import cached_frame
from airkan_builder.kernel import Kernel, frame_api
from airkan_builder.rules import VERSION
from allshield_project import port_specs
from test_geometry import cases, check_result


def _write_report(path, report):
    path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False),
        encoding="utf-8",
    )


def _sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _physical_objects(doc):
    return [obj for obj in doc.Objects if "GeometryRole" in obj.PropertiesList]


def _check_document(doc, root, objects, result):
    doc.recompute()
    bodies = [obj for obj in doc.Objects if obj.TypeId == "PartDesign::Body"]
    expected_bodies = result["validation"]["partdesign_body_count"]
    if len(bodies) != expected_bodies:
        raise RuntimeError("Onjuist aantal PartDesign::Body-objecten.")
    if result["detail"] == "BOM_SIMPLIFIED" and len(bodies) != 1:
        raise RuntimeError("Vereenvoudigd model is niet precies een Body.")
    for obj in objects:
        if not obj.Shape.isValid() or len(obj.Shape.Solids) != 1:
            raise RuntimeError("Document bevat geen geldig fysiek een-solid-object: " + obj.Name)
    bom = bom_from_document(doc)
    if len(bom) != 1 or bom[0]["quantity"] != 1:
        raise RuntimeError("BOM telt intern detail dubbel.")
    if json.loads(root.ParametersJSON) != result["parameters"]:
        raise RuntimeError("Rootparameters verschillen van het bouwresultaat.")
    refs = doc.getObject("Aansluitreferenties")
    if refs is None or len(refs.Group) != len(result["join_datums"]):
        raise RuntimeError("Aansluitreferenties ontbreken of zijn onvolledig.")
    logical_ports = {port["name"]: port for port in port_specs(result["parameters"])}
    for datum in result["join_datums"]:
        logical = logical_ports.get(datum["name"])
        if logical is None:
            raise RuntimeError("Projectpoort ontbreekt voor geometrisch aansluitdatum: " + datum["name"])
        for key in ("width_mm", "height_mm", "diameter_mm", "kind"):
            if logical[key] != datum[key]:
                raise RuntimeError("Projectpoort wijkt af van geometrie: " + datum["name"] + "/" + key)
    if not any(port["direction"] == "in" for port in logical_ports.values()) or not any(port["direction"] == "out" for port in logical_ports.values()):
        raise RuntimeError("Projectstuk mist voorganger- of opvolgerpoort.")
    return len(bodies), len(objects)


def _check_reopened(path, result, expected_body_count, expected_object_count):
    reopened = App.openDocument(path)
    try:
        reopened.recompute()
        roots = [
            obj
            for obj in reopened.Objects
            if getattr(obj, "BuilderSchema", "") == "airkan-component-v3"
        ]
        if len(roots) != 1:
            raise RuntimeError("FCStd-heropening mist de unieke onderdeelroot.")
        if json.loads(roots[0].ParametersJSON) != result["parameters"]:
            raise RuntimeError("Parameters gewijzigd na FCStd-heropening.")
        bodies = [obj for obj in reopened.Objects if obj.TypeId == "PartDesign::Body"]
        if len(bodies) != expected_body_count:
            raise RuntimeError("Body-aantal gewijzigd na FCStd-heropening.")
        physical = _physical_objects(reopened)
        if len(physical) != expected_object_count:
            raise RuntimeError("Aantal fysieke objecten gewijzigd na FCStd-heropening.")
        for obj in physical:
            if not obj.Shape.isValid() or len(obj.Shape.Solids) != 1:
                raise RuntimeError("Ongeldige fysieke Shape na FCStd-heropening: " + obj.Name)
        refs = reopened.getObject("Aansluitreferenties")
        if refs is None or len(refs.Group) != len(result["join_datums"]):
            raise RuntimeError("Aansluitreferenties gewijzigd na FCStd-heropening.")
    finally:
        App.closeDocument(reopened.Name)


def run(outdir):
    out = Path(outdir).expanduser().resolve()
    out.mkdir(parents=True, exist_ok=False)
    report_path = out / "validation_native_freecad.json"
    package_file = Path(airkan_builder.__file__).resolve()
    if PACKAGE_DIR not in package_file.parents:
        raise RuntimeError("Verkeerde airkan_builder geïmporteerd: " + str(package_file))

    frame_api.cache_clear()
    cached_frame.cache_clear()
    report = {
        "schema": "airkan-native-validation-v3",
        "version": VERSION,
        "started_utc": datetime.now(timezone.utc).isoformat(),
        "runtime": {
            "os": platform.platform(),
            "python": platform.python_version(),
            "freecad": App.Version(),
            "gui_up": bool(App.GuiUp),
            "package": str(package_file),
        },
        "native_freecad_tested": True,
        "native_freecad_gui_tested": False,
        "native_fcstd_tested": True,
        "native_fusion_tested": False,
        "cases": [],
    }
    old_active = App.ActiveDocument.Name if App.ActiveDocument else None
    kernel = Kernel("freecad")
    try:
        for case in cases():
            print("START", case["name"], flush=True)
            started = time.monotonic()
            row = {**case, "passed": False}
            doc = None
            try:
                try:
                    doc, root, objects, result = create_document(
                        case["parameters"], show_references=False
                    )
                except Exception as exc:
                    if case["expected_error"] and case["expected_error"] in str(exc):
                        row.update(passed=True, rejection=str(exc))
                        result = None
                    else:
                        raise
                if result is not None:
                    if case["expected_error"]:
                        raise RuntimeError("Ongeldige invoer werd niet geweigerd.")
                    check_result(result, kernel)
                    expected_threshold_profiles = {
                        "frame_threshold_E30": "E30",
                        "frame_threshold_A_A40": "A40",
                        "frame_threshold_B_A40": "A40",
                    }
                    expected_profile = expected_threshold_profiles.get(case["name"])
                    if expected_profile and result["frames"][0]["profile"] != expected_profile:
                        raise RuntimeError("Onjuist profiel op de maatgrens.")
                    if case["name"] == "mixed_end_profiles":
                        if [frame["profile"] for frame in result["frames"]] != ["E30", "A40"]:
                            raise RuntimeError("Gemengde profielkeuze E30/A40 is onjuist.")
                    body_count, object_count = _check_document(
                        doc, root, objects, result
                    )
                    should_export = case["step"] or case["name"].startswith("base_")
                    if should_export:
                        paths = export_document(doc, root, objects, result, str(out))
                        repeat_paths = None
                        if case["name"] == "base_REG":
                            original_hashes = {
                                key: _sha256(path) for key, path in paths.items()
                            }
                            repeat_paths = export_document(
                                doc, root, objects, result, str(out)
                            )
                            if any(paths[key] == repeat_paths[key] for key in paths):
                                raise RuntimeError("Herhaalde export gebruikte dezelfde bestandsnaam.")
                            if any(
                                _sha256(path) != original_hashes[key]
                                for key, path in paths.items()
                            ):
                                raise RuntimeError("Herhaalde export overschreef de eerste uitvoer.")
                        App.closeDocument(doc.Name)
                        doc = None
                        _check_reopened(
                            paths["freecad"], result, body_count, object_count
                        )
                        if repeat_paths is not None:
                            _check_reopened(
                                repeat_paths["freecad"],
                                result,
                                body_count,
                                object_count,
                            )
                            row.update(
                                repeat_export="PASS",
                                repeat_files=repeat_paths,
                                original_files_unchanged=True,
                            )
                        row.update(
                            files=paths,
                            step_reread="PASS",
                            fcstd_reopen="PASS",
                        )
                    row.update(
                        passed=True,
                        body_count=body_count,
                        physical_object_count=object_count,
                        solid_count=result["validation"]["valid_solids"],
                    )
            except Exception as exc:
                row.update(error=str(exc), traceback=traceback.format_exc())
            finally:
                if doc is not None:
                    try:
                        App.closeDocument(doc.Name)
                    except Exception:
                        pass
            row["seconds"] = round(time.monotonic() - started, 3)
            report["cases"].append(row)
            _write_report(report_path, report)
            print(
                "PASS" if row["passed"] else "FAIL",
                case["name"],
                row["seconds"],
                row.get("error", ""),
                flush=True,
            )
    finally:
        if old_active and old_active in App.listDocuments():
            App.setActiveDocument(old_active)

    report["summary"] = {
        "total_cases": len(report["cases"]),
        "passed": sum(row["passed"] for row in report["cases"]),
        "step_roundtrips_passed": sum(
            row.get("step_reread") == "PASS" for row in report["cases"]
        ),
        "fcstd_reopens_passed": sum(
            row.get("fcstd_reopen") == "PASS" for row in report["cases"]
        ),
        "negative_cases_passed": sum(
            row["passed"] and bool(row.get("expected_error"))
            for row in report["cases"]
        ),
        "repeat_exports_passed": sum(
            row.get("repeat_export") == "PASS" for row in report["cases"]
        ),
    }
    report["completed_utc"] = datetime.now(timezone.utc).isoformat()
    _write_report(report_path, report)
    print(report["summary"], flush=True)
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    report = run(args.out)
    return 0 if report["summary"]["total_cases"] == report["summary"]["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())