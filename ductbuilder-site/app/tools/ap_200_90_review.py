"""Create a review-only AP 200-90 FreeCAD model.

This is intentionally outside the AAVDS application rules and GUI. It is a
standalone geometry review for the AIRKAN AP saddle fitting only: the Ø200
host duct is used only as a Boolean cutter and is never included in the
exported STEP.

Example:
    "C:\Program Files\FreeCAD 1.1\bin\python.exe" ^
        app\tools\ap_200_90_review.py --out C:\temp\ap-review --e-mm 20

When run with FreeCAD's GUI macro command, the script prompts for e and the
output folder, then keeps the review document open for inspection.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import FreeCAD as App
import Part


HOST_DIAMETER_MM = 200.0
BRANCH_DIAMETER_MM = 90.0
TRANSITION_HEIGHT_MM = 60.0
WALL_THICKNESS_MM = 1.0


def _nonnegative_number(value):
    number = float(value)
    if not math.isfinite(number) or number < 0:
        raise argparse.ArgumentTypeError("Enter a non-negative finite number.")
    return number


def _rectangle_wire(width_mm, depth_mm, z_mm):
    half_width = width_mm / 2
    half_depth = depth_mm / 2
    points = [
        App.Vector(-half_width, -half_depth, z_mm),
        App.Vector(half_width, -half_depth, z_mm),
        App.Vector(half_width, half_depth, z_mm),
        App.Vector(-half_width, half_depth, z_mm),
        App.Vector(-half_width, -half_depth, z_mm),
    ]
    return Part.makePolygon(points)


def _circle_wire(radius_mm, z_mm):
    return Part.Wire([Part.makeCircle(radius_mm, App.Vector(0, 0, z_mm))])


def _fuse(shapes):
    result = shapes[0]
    for shape in shapes[1:]:
        result = result.fuse(shape)
    return result.removeSplitter()


def _add_number_property(feature, name, value, group, description):
    feature.addProperty("App::PropertyLength", name, group, description)
    setattr(feature, name, value)


def build_ap_200_90(e_mm):
    """Return the AP saddle shell and review dimensions in millimetres."""
    host_radius = HOST_DIAMETER_MM / 2
    branch_radius = BRANCH_DIAMETER_MM / 2
    saddle_length = BRANCH_DIAMETER_MM + 120
    installation_opening_width = BRANCH_DIAMETER_MM + 100
    installation_opening_length = saddle_length - 20
    overlap_each_end = (saddle_length - installation_opening_length) / 2

    # The lower exposed edge follows the Ø200 duct. The opening width is
    # transverse to the host axis; the longer 210 mm saddle footprint runs
    # along that axis and overhangs the 190 mm installer opening by 10 mm
    # at each end.
    chord_half_width = installation_opening_width / 2
    saddle_edge_z = math.sqrt(host_radius**2 - chord_half_width**2)
    saddle_depth_below_crown = host_radius - saddle_edge_z
    shoulder_z = host_radius
    spigot_start_z = shoulder_z + TRANSITION_HEIGHT_MM
    spigot_end_z = spigot_start_z + e_mm

    outer_base = _rectangle_wire(
        installation_opening_width,
        saddle_length,
        saddle_edge_z,
    )
    outer_shoulder = _rectangle_wire(BRANCH_DIAMETER_MM, BRANCH_DIAMETER_MM, shoulder_z)
    outer_circle = _circle_wire(branch_radius, spigot_start_z)
    outer_pyramid = Part.makeLoft([outer_base, outer_shoulder], True, True)
    outer_loft = Part.makeLoft([outer_shoulder, outer_circle], True, False)
    outer_spigot = Part.makeCylinder(
        branch_radius,
        e_mm,
        App.Vector(0, 0, spigot_start_z),
    )
    outer = _fuse([outer_pyramid, outer_loft, outer_spigot])

    inner_base = _rectangle_wire(
        installation_opening_width - 2 * WALL_THICKNESS_MM,
        saddle_length - 2 * WALL_THICKNESS_MM,
        saddle_edge_z - WALL_THICKNESS_MM,
    )
    inner_shoulder = _rectangle_wire(
        BRANCH_DIAMETER_MM - 2 * WALL_THICKNESS_MM,
        BRANCH_DIAMETER_MM - 2 * WALL_THICKNESS_MM,
        shoulder_z,
    )
    inner_circle = _circle_wire(branch_radius - WALL_THICKNESS_MM, spigot_start_z)
    inner_pyramid = Part.makeLoft([inner_base, inner_shoulder], True, True)
    inner_loft = Part.makeLoft([inner_shoulder, inner_circle], True, False)
    inner_spigot = Part.makeCylinder(
        branch_radius - WALL_THICKNESS_MM,
        e_mm + WALL_THICKNESS_MM,
        App.Vector(0, 0, spigot_start_z),
    )
    inner = _fuse([inner_pyramid, inner_loft, inner_spigot])

    # This cutter establishes the concave saddle surface only. It is not kept
    # as a document object and is not part of the resulting STEP.
    cutter_length = saddle_length + 20
    host_cutter = Part.makeCylinder(
        host_radius,
        cutter_length,
        App.Vector(0, -cutter_length / 2, 0),
        App.Vector(0, 1, 0),
    )
    fitting = outer.cut(inner).cut(host_cutter).removeSplitter()
    if not fitting.isValid() or len(fitting.Solids) != 1:
        raise RuntimeError("AP review geometry must produce one valid solid.")

    dimensions = {
        "host_diameter_mm": HOST_DIAMETER_MM,
        "branch_diameter_mm": BRANCH_DIAMETER_MM,
        "transition_height_mm": TRANSITION_HEIGHT_MM,
        "e_mm": e_mm,
        "straight_spigot_end_z_mm": spigot_end_z,
        "projection_above_host_crown_mm": TRANSITION_HEIGHT_MM + e_mm,
        "saddle_length_mm": saddle_length,
        "installation_opening_width_mm": installation_opening_width,
        "installation_opening_length_mm": installation_opening_length,
        "overlap_each_end_mm": overlap_each_end,
        "host_crown_z_mm": shoulder_z,
        "saddle_edge_z_mm": saddle_edge_z,
        "saddle_depth_below_host_crown_mm": saddle_depth_below_crown,
        "wall_thickness_mm": WALL_THICKNESS_MM,
    }
    return fitting, dimensions


def write_review(out_dir, e_mm, keep_document_open=False):
    out_dir.mkdir(parents=True, exist_ok=True)
    fitting, dimensions = build_ap_200_90(e_mm)

    document = App.newDocument("AP_200_90_review")
    try:
        feature = document.addObject("Part::Feature", "AP_200_90")
        feature.Label = "AP 200-90 review fitting"
        feature.Shape = fitting
        feature.addProperty(
            "App::PropertyString",
            "ReviewScope",
            "Review",
            "What this standalone review model represents.",
        )
        feature.ReviewScope = (
            "Saddle fitting only. The Ø200 host duct is a Boolean cutter and is not included."
        )
        for name, value in dimensions.items():
            _add_number_property(feature, name.title().replace("_", ""), value, "Dimensions", name)
        if feature.ViewObject is not None:
            feature.ViewObject.ShapeColor = (0.12, 0.12, 0.12)
            feature.ViewObject.LineColor = (0.0, 0.0, 0.0)

        data = document.addObject("App::FeaturePython", "Review_Data")
        data.Label = "AP 200-90 review assumptions"
        data.addProperty("App::PropertyString", "Summary", "Review")
        data.Summary = (
            "Standalone review only: no AIRKAN catalogue pricing, no host duct, "
            "and no fabrication certification."
        )
        data.addProperty("App::PropertyString", "SourceRelations", "Review")
        data.SourceRelations = (
            "Saddle length = Ø2 + 120; opening width = Ø2 + 100; "
            "opening length = saddle length - 20; overlap = 10 mm per end; "
            "straight transition = 60 mm; "
            "e is supplied at runtime."
        )
        data.addProperty("App::PropertyString", "CatalogueStatus", "Review")
        data.CatalogueStatus = "CUSTOM: Ø2 90 mm is not listed in the AP source table."

        document.recompute()
        if not feature.Shape.isValid() or len(feature.Shape.Solids) != 1:
            raise RuntimeError("Saved AP review fitting is not one valid solid.")

        fcstd_path = out_dir / "AP_200_90_review.FCStd"
        step_path = out_dir / "AP_200_90_review.step"
        metadata_path = out_dir / "AP_200_90_review.json"
        document.saveAs(str(fcstd_path))
        Part.export([feature], str(step_path))
        metadata_path.write_text(
            json.dumps(
                {
                    "schema": "ap-200-90-review-v1",
                    "dimensions_mm": dimensions,
                    "assumptions": [
                        "The exported fitting contains no Ø200 host duct.",
                        "The lower saddle is cut from a Ø200 cylindrical host reference.",
                        "The 190 mm by 190 mm installation opening is not exported as separate geometry.",
                        "The model is a geometry review, not a fabrication-certified sheet-metal model.",
                    ],
                    "outputs": {
                        "fcstd": fcstd_path.name,
                        "step": step_path.name,
                    },
                },
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        return {
            "fcstd": str(fcstd_path),
            "step": str(step_path),
            "metadata": str(metadata_path),
            "dimensions": dimensions,
        }
    finally:
        if not keep_document_open:
            App.closeDocument(document.Name)


def _gui_modules():
    try:
        from PySide6 import QtCore, QtWidgets
    except ImportError:
        from PySide import QtCore, QtGui as QtWidgets
    return QtCore, QtWidgets


def _prompt_for_e_mm(widgets):
    while True:
        value, accepted = widgets.QInputDialog.getText(
            None,
            "AP 200-90 review",
            "Enter e (mm), the straight spigot length in the AIRKAN drawing:",
        )
        if not accepted:
            return None
        try:
            return _nonnegative_number(value)
        except argparse.ArgumentTypeError as error:
            widgets.QMessageBox.warning(None, "AP 200-90 review", str(error))


def _default_gui_output_dir(core):
    desktop = core.QStandardPaths.writableLocation(core.QStandardPaths.StandardLocation.DesktopLocation)
    return Path(desktop) if desktop else Path.home()


def run_interactive():
    core, widgets = _gui_modules()
    e_mm = _prompt_for_e_mm(widgets)
    if e_mm is None:
        return 0
    selected = widgets.QFileDialog.getExistingDirectory(
        None,
        "Choose AP 200-90 review output folder",
        str(_default_gui_output_dir(core)),
    )
    if not selected:
        return 0
    try:
        result = write_review(Path(selected), e_mm, keep_document_open=True)
    except (OSError, RuntimeError, ValueError) as error:
        widgets.QMessageBox.critical(None, "AP 200-90 review failed", str(error))
        return 1
    import FreeCADGui as Gui

    Gui.activeDocument().activeView().viewAxonometric()
    Gui.activeDocument().activeView().fitAll()
    widgets.QMessageBox.information(
        None,
        "AP 200-90 review exported",
        "Review document is open in FreeCAD.\n\n"
        "FCStd:\n" + result["fcstd"] + "\n\n"
        "STEP:\n" + result["step"] + "\n\n"
        "Review JSON:\n" + result["metadata"],
    )
    return 0


def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]
    if App.GuiUp and not {"--out", "--e-mm"}.intersection(argv):
        return run_interactive()
    parser = argparse.ArgumentParser(description="Create a standalone AP 200-90 FreeCAD review model.")
    parser.add_argument("--out", required=True, type=Path, help="Output folder for FCStd, STEP, and review JSON.")
    parser.add_argument(
        "--e-mm",
        required=True,
        type=_nonnegative_number,
        help="Straight spigot length marked e in the supplier drawing, in millimetres.",
    )
    arguments = parser.parse_args(argv)
    result = write_review(arguments.out.expanduser().resolve(), arguments.e_mm)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
