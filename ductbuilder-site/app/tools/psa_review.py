"""Create a review-only PSA FreeCAD model.

This is intentionally outside the AAVDS application rules and GUI. It models
the reviewed PSA concept: a hollow vertical Ø2 spigot with an asymmetric
10 mm saddle cut by a Ø1 reference cylinder. The Ø1 host duct is used only
to form the contact surface and is never included in the exported STEP.

Example:
    "C:\Program Files\FreeCAD 1.1\bin\python.exe" ^
        app\tools\psa_review.py --out C:\temp\psa-review ^
        --host-diameter-mm 200 --branch-diameter-mm 100 --asymmetry A

When run with FreeCAD's GUI macro command, the script prompts for Ø1, Ø2,
asymmetry, and the output folder, then keeps the review document open for
inspection.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import FreeCAD as App
import Part


SADDLE_WIDTH_MM = 10.0
WALL_THICKNESS_MM = 1.0


def _positive_number(value):
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise argparse.ArgumentTypeError("Enter a positive finite number.")
    return number


def _validate_diameters(host_diameter_mm, branch_diameter_mm):
    if host_diameter_mm <= branch_diameter_mm:
        raise ValueError("Ø1 host diameter must be greater than Ø2 branch diameter.")
    if branch_diameter_mm <= 2 * WALL_THICKNESS_MM:
        raise ValueError(
            f"Ø2 branch diameter must exceed {2 * WALL_THICKNESS_MM:g} mm "
            "to create the hollow review spigot."
        )


def _validate_asymmetry(asymmetry_mm, branch_diameter_mm):
    if not math.isfinite(asymmetry_mm) or asymmetry_mm < 0:
        raise ValueError("Asymmetry must be a non-negative finite number.")
    maximum_asymmetry_mm = branch_diameter_mm / 2
    if asymmetry_mm > maximum_asymmetry_mm:
        raise ValueError(
            f"Asymmetry cannot exceed Ø2 / 2 ({maximum_asymmetry_mm:g} mm)."
        )


def _resolve_asymmetry(value, branch_diameter_mm):
    text = str(value).strip()
    maximum_asymmetry_mm = branch_diameter_mm / 2
    if text.upper() == "A":
        return maximum_asymmetry_mm, "A"
    if text.upper() == "S":
        return 0.0, "S"
    try:
        asymmetry_mm = float(text)
    except ValueError as error:
        raise ValueError("Enter A, S, or a non-negative number.") from error
    if not math.isfinite(asymmetry_mm) or asymmetry_mm < 0:
        raise ValueError("Asymmetry must be a non-negative finite number.")
    if asymmetry_mm >= maximum_asymmetry_mm:
        raise ValueError(
            f"Numeric asymmetry must be less than Ø2 / 2 ({maximum_asymmetry_mm:g} mm). "
            "Use A for the fully asymmetric tangential position."
        )
    return asymmetry_mm, "PARTIAL"


def _fuse(shapes):
    result = shapes[0]
    for shape in shapes[1:]:
        result = result.fuse(shape)
    return result


def _add_number_property(feature, name, value, group, description):
    feature.addProperty("App::PropertyLength", name, group, description)
    setattr(feature, name, value)


def _dimension_label(value):
    if value.is_integer():
        return str(int(value))
    return f"{value:g}".replace(".", "_")


def _asymmetry_label(asymmetry_mm, asymmetry_mode):
    if asymmetry_mode in {"A", "S"}:
        return asymmetry_mode
    return f"P{_dimension_label(asymmetry_mm)}"


def build_psa(host_diameter_mm, branch_diameter_mm, asymmetry_mm):
    """Return the PSA saddle fitting and reviewed dimensions in millimetres."""
    _validate_diameters(host_diameter_mm, branch_diameter_mm)
    _validate_asymmetry(asymmetry_mm, branch_diameter_mm)

    host_radius = host_diameter_mm / 2
    branch_radius = branch_diameter_mm / 2
    spigot_height_mm = 2 * branch_diameter_mm
    front_tangent_plane_y = -branch_radius
    host_cutter_end_y = host_diameter_mm
    host_cutter_length = host_cutter_end_y - front_tangent_plane_y

    # The asymmetry value is the direct right-side X coordinate of the Ø1
    # centre. It ranges from the Ø2 centre plane (S) to Ø2's right tangent
    # plane (A).
    host_cutter_center_x = asymmetry_mm

    host_cutter = Part.makeCylinder(
        host_radius,
        host_cutter_length,
        App.Vector(host_cutter_center_x, front_tangent_plane_y, 0),
        App.Vector(0, 1, 0),
    )
    host_skin = Part.makeCylinder(
        host_radius + WALL_THICKNESS_MM,
        host_cutter_length,
        App.Vector(host_cutter_center_x, front_tangent_plane_y, 0),
        App.Vector(0, 1, 0),
    ).cut(host_cutter)
    branch_outer = Part.makeCylinder(
        branch_radius,
        spigot_height_mm,
        App.Vector(0, 0, 0),
    )
    branch_inner = Part.makeCylinder(
        branch_radius - WALL_THICKNESS_MM,
        spigot_height_mm + WALL_THICKNESS_MM,
        App.Vector(0, 0, -WALL_THICKNESS_MM),
    )
    branch_shell = branch_outer.cut(branch_inner).cut(host_cutter)

    saddle_outer_envelope = Part.makeCylinder(
        branch_radius + SADDLE_WIDTH_MM,
        host_radius + SADDLE_WIDTH_MM,
        App.Vector(0, 0, 0),
    )
    saddle_inner_envelope = Part.makeCylinder(
        branch_radius,
        host_radius + SADDLE_WIDTH_MM,
        App.Vector(0, 0, 0),
    )
    saddle_band = host_skin.common(saddle_outer_envelope.cut(saddle_inner_envelope))

    fitting = _fuse([branch_shell, saddle_band])
    if not fitting.isValid() or len(fitting.Solids) != 1:
        raise RuntimeError("PSA review geometry must produce one valid solid.")

    dimensions = {
        "host_diameter_mm": host_diameter_mm,
        "branch_diameter_mm": branch_diameter_mm,
        "host_radius_mm": host_radius,
        "branch_radius_mm": branch_radius,
        "asymmetry_mm": asymmetry_mm,
        "maximum_asymmetry_mm": branch_radius,
        "host_cutter_center_x_mm": host_cutter_center_x,
        "right_tangent_plane_x_mm": branch_radius,
        "front_tangent_plane_y_mm": front_tangent_plane_y,
        "host_cutter_end_y_mm": host_cutter_end_y,
        "spigot_height_mm": spigot_height_mm,
        "saddle_band_width_mm": SADDLE_WIDTH_MM,
        "wall_thickness_mm": WALL_THICKNESS_MM,
    }
    return fitting, dimensions


def write_review(
    out_dir,
    host_diameter_mm,
    branch_diameter_mm,
    asymmetry_mm,
    asymmetry_mode,
    keep_document_open=False,
):
    out_dir.mkdir(parents=True, exist_ok=True)
    fitting, dimensions = build_psa(
        host_diameter_mm,
        branch_diameter_mm,
        asymmetry_mm,
    )
    host_label = _dimension_label(host_diameter_mm)
    branch_label = _dimension_label(branch_diameter_mm)
    asymmetry_label = _asymmetry_label(asymmetry_mm, asymmetry_mode)
    model_name = f"PSA_{host_label}_{branch_label}_{asymmetry_label}_review"

    document = App.newDocument(model_name)
    try:
        feature = document.addObject("Part::Feature", "PSA_Fitting")
        feature.Label = f"PSA {host_label}-{branch_label} {asymmetry_label} review fitting"
        feature.Shape = fitting
        feature.addProperty(
            "App::PropertyString",
            "ReviewScope",
            "Review",
            "What this standalone review model represents.",
        )
        feature.ReviewScope = (
            "PSA fitting only. The Ø1 host duct is a Boolean reference and is not included."
        )
        for name, value in dimensions.items():
            _add_number_property(feature, name.title().replace("_", ""), value, "Dimensions", name)
        if feature.ViewObject is not None:
            feature.ViewObject.ShapeColor = (0.12, 0.12, 0.12)
            feature.ViewObject.LineColor = (0.0, 0.0, 0.0)

        data = document.addObject("App::FeaturePython", "Review_Data")
        data.Label = f"PSA {host_label}-{branch_label} review assumptions"
        data.addProperty("App::PropertyString", "Summary", "Review")
        data.Summary = (
            "Standalone geometry review only: no catalogue pricing and no fabrication certification."
        )
        data.addProperty("App::PropertyString", "PlacementRule", "Review")
        data.PlacementRule = (
            "The vertical Ø2 tube is centred at X=0, Y=0, Z=0. The Ø1 cutter "
            "centre is X=asymmetry, from 0 at S to +Ø2/2 at A."
        )
        data.addProperty("App::PropertyString", "AsymmetryInput", "Review")
        data.AsymmetryInput = (
            f"{asymmetry_mode}: {asymmetry_mm:g} mm; "
            f"maximum = Ø2 / 2 = {branch_diameter_mm / 2:g} mm."
        )
        data.addProperty("App::PropertyString", "SaddleRule", "Review")
        data.SaddleRule = (
            "The saddle is a nominal 10 mm band around the Ø2 contact profile, "
            "with its contact face concave to Ø1."
        )
        data.addProperty("App::PropertyString", "SourceDrawingCorrection", "Review")
        data.SourceDrawingCorrection = (
            "The lower-right host-circle label in the supplied PSA drawing reads Ø2; it is Ø1."
        )

        document.recompute()
        if not feature.Shape.isValid() or len(feature.Shape.Solids) != 1:
            raise RuntimeError("Saved PSA review fitting is not one valid solid.")

        fcstd_path = out_dir / f"{model_name}.FCStd"
        step_path = out_dir / f"{model_name}.step"
        metadata_path = out_dir / f"{model_name}.json"
        document.saveAs(str(fcstd_path))
        Part.export([feature], str(step_path))
        metadata_path.write_text(
            json.dumps(
                {
                    "schema": "psa-review-v2",
                    "dimensions_mm": dimensions,
                    "asymmetry_mode": asymmetry_mode,
                    "assumptions": [
                        "The exported fitting contains no Ø1 host duct.",
                        "The Ø2 spigot is vertical at X=0, Y=0, Z=0 and has height 2 × Ø2.",
                        "The Ø1 cutter begins at Y=-Ø2/2 and ends at Y=Ø1.",
                        "The Ø1 cutter centre is X=asymmetry; S is 0 mm and A is +Ø2 / 2.",
                        "A numeric asymmetry is non-negative and strictly less than Ø2 / 2.",
                        "The supplied drawing's lower-right host-circle label is Ø1, not the printed Ø2.",
                        "A nominal 10 mm saddle skirt extends below the spigot and contacts Ø1.",
                        "Projection above the Ø1 crown is 100 mm, or 125 mm when Ø1 exceeds 500 mm.",
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


def _prompt_for_positive_number(widgets, label, prompt):
    while True:
        value, accepted = widgets.QInputDialog.getText(None, label, prompt)
        if not accepted:
            return None
        try:
            return _positive_number(value)
        except argparse.ArgumentTypeError as error:
            widgets.QMessageBox.warning(None, label, str(error))


def _prompt_for_dimensions(widgets):
    label = "PSA review"
    while True:
        host_diameter_mm = _prompt_for_positive_number(
            widgets,
            label,
            "Enter Ø1 host diameter (mm):",
        )
        if host_diameter_mm is None:
            return None
        branch_diameter_mm = _prompt_for_positive_number(
            widgets,
            label,
            "Enter Ø2 branch diameter (mm):",
        )
        if branch_diameter_mm is None:
            return None
        try:
            _validate_diameters(host_diameter_mm, branch_diameter_mm)
        except ValueError as error:
            widgets.QMessageBox.warning(None, label, str(error))
            continue

        maximum_asymmetry_mm = branch_diameter_mm / 2
        while True:
            value, accepted = widgets.QInputDialog.getText(
                None,
                label,
                "Enter asymmetry: A = fully asymmetric/tangent, "
                "S = symmetric, or a number from 0 up to (but excluding) "
                f"Ø2 / 2 ({maximum_asymmetry_mm:g} mm):",
            )
            if not accepted:
                return None
            try:
                asymmetry_mm, asymmetry_mode = _resolve_asymmetry(
                    value,
                    branch_diameter_mm,
                )
                return (
                    host_diameter_mm,
                    branch_diameter_mm,
                    asymmetry_mm,
                    asymmetry_mode,
                )
            except ValueError as error:
                widgets.QMessageBox.warning(None, label, str(error))


def _default_gui_output_dir(core):
    desktop = core.QStandardPaths.writableLocation(core.QStandardPaths.StandardLocation.DesktopLocation)
    return Path(desktop) if desktop else Path.home()


def run_interactive():
    core, widgets = _gui_modules()
    dimensions = _prompt_for_dimensions(widgets)
    if dimensions is None:
        return 0
    (
        host_diameter_mm,
        branch_diameter_mm,
        asymmetry_mm,
        asymmetry_mode,
    ) = dimensions
    selected = widgets.QFileDialog.getExistingDirectory(
        None,
        "Choose PSA review output folder",
        str(_default_gui_output_dir(core)),
    )
    if not selected:
        return 0
    try:
        result = write_review(
            Path(selected),
            host_diameter_mm,
            branch_diameter_mm,
            asymmetry_mm,
            asymmetry_mode,
            keep_document_open=True,
        )
    except (OSError, RuntimeError, ValueError) as error:
        widgets.QMessageBox.critical(None, "PSA review failed", str(error))
        return 1
    import FreeCADGui as Gui

    Gui.activeDocument().activeView().viewAxonometric()
    Gui.activeDocument().activeView().fitAll()
    widgets.QMessageBox.information(
        None,
        "PSA review exported",
        "Review document is open in FreeCAD.\n\n"
        "FCStd:\n" + result["fcstd"] + "\n\n"
        "STEP:\n" + result["step"] + "\n\n"
        "Review JSON:\n" + result["metadata"],
    )
    return 0


def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]
    required_arguments = {
        "--out",
        "--host-diameter-mm",
        "--branch-diameter-mm",
        "--asymmetry",
    }
    if App.GuiUp and not required_arguments.intersection(argv):
        return run_interactive()
    parser = argparse.ArgumentParser(description="Create a standalone PSA FreeCAD review model.")
    parser.add_argument("--out", required=True, type=Path, help="Output folder for FCStd, STEP, and review JSON.")
    parser.add_argument(
        "--host-diameter-mm",
        required=True,
        type=_positive_number,
        help="Ø1 host diameter in millimetres.",
    )
    parser.add_argument(
        "--branch-diameter-mm",
        required=True,
        type=_positive_number,
        help="Ø2 branch diameter in millimetres.",
    )
    parser.add_argument(
        "--asymmetry",
        required=True,
        help="A for fully asymmetric/tangent, S for symmetric, or a number less than Ø2 / 2.",
    )
    arguments = parser.parse_args(argv)
    try:
        asymmetry_mm, asymmetry_mode = _resolve_asymmetry(
            arguments.asymmetry,
            arguments.branch_diameter_mm,
        )
    except ValueError as error:
        parser.error(str(error))
    result = write_review(
        arguments.out.expanduser().resolve(),
        arguments.host_diameter_mm,
        arguments.branch_diameter_mm,
        asymmetry_mm,
        asymmetry_mode,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
