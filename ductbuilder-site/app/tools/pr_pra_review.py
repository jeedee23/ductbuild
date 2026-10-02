"""Create a review-only PR/PRA rectangular branch on a round host.

The source drawing specifies a B × L rectangular branch, a 100 mm projection
above the D1 host crown, and a concave D1 contact surface. This script keeps
the branch classification deliberately neutral until the catalogue's B/D1
variant mapping is released.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import time
from pathlib import Path

import FreeCAD as App
import Part


WALL_THICKNESS_MM = 1.0
HEIGHT_ABOVE_HOST_CROWN_MM = 100.0
DEFAULT_GUI_D1_MM = 200.0
DEFAULT_GUI_B_MM = 100.0
DEFAULT_GUI_L_MM = 200.0
DEFAULT_GUI_ASYMMETRY = "S"


def _positive_number(value):
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise argparse.ArgumentTypeError("Enter a positive finite number.")
    return number


def _validate_dimensions(d1_mm, b_mm, l_mm):
    if b_mm <= 2 * WALL_THICKNESS_MM:
        raise ValueError(
            f"B must exceed {2 * WALL_THICKNESS_MM:g} mm to create a hollow branch."
        )
    if d1_mm < b_mm:
        raise ValueError("D1 must be at least as large as B.")
    if l_mm <= 2 * WALL_THICKNESS_MM:
        raise ValueError(
            f"L must exceed {2 * WALL_THICKNESS_MM:g} mm to create a hollow branch."
        )


def _resolve_asymmetry(value, d1_mm, b_mm):
    text = str(value).strip()
    maximum_asymmetry_mm = (d1_mm - b_mm) / 2
    if text.upper() == "S":
        return 0.0, "S"
    if text.upper() == "A":
        if maximum_asymmetry_mm == 0:
            raise ValueError("A requires D1 to be greater than B.")
        return maximum_asymmetry_mm, "A"
    numeric_text = text[1:] if text.upper().startswith("P") else text
    try:
        asymmetry_mm = float(numeric_text)
    except ValueError as error:
        raise ValueError(
            "Enter A, S, P followed by a non-negative number, or a non-negative number."
        ) from error
    if not math.isfinite(asymmetry_mm) or asymmetry_mm < 0:
        raise ValueError("Asymmetry must be a non-negative finite number.")
    if asymmetry_mm >= maximum_asymmetry_mm:
        raise ValueError(
            f"Numeric asymmetry must be less than {maximum_asymmetry_mm:g} mm. "
            "Use A for the right-tangent position."
        )
    return asymmetry_mm, "PARTIAL"


def _dimension_label(value):
    if value.is_integer():
        return str(int(value))
    return f"{value:g}".replace(".", "_")


def _asymmetry_label(asymmetry_mm, asymmetry_mode):
    if asymmetry_mode in {"A", "S"}:
        return asymmetry_mode
    return f"P{_dimension_label(asymmetry_mm)}"


def _add_length_property(feature, name, value, description):
    feature.addProperty("App::PropertyLength", name, "Dimensions", description)
    setattr(feature, name, value)


def build_pr_pra(d1_mm, b_mm, l_mm, asymmetry_mm):
    """Return a hollow rectangular PR/PRA review branch and its dimensions."""
    _validate_dimensions(d1_mm, b_mm, l_mm)
    maximum_asymmetry_mm = (d1_mm - b_mm) / 2
    if not math.isfinite(asymmetry_mm) or not 0 <= asymmetry_mm <= maximum_asymmetry_mm:
        raise ValueError(
            "Asymmetry must be from 0 through the right-tangent position "
            f"({maximum_asymmetry_mm:g} mm)."
        )

    d1_radius = d1_mm / 2
    branch_height_mm = d1_radius + HEIGHT_ABOVE_HOST_CROWN_MM
    branch_x_min_mm = asymmetry_mm - b_mm / 2
    branch_y_min_mm = -l_mm / 2
    outer = Part.makeBox(
        b_mm,
        l_mm,
        branch_height_mm,
        App.Vector(branch_x_min_mm, branch_y_min_mm, 0),
    )
    inner = Part.makeBox(
        b_mm - 2 * WALL_THICKNESS_MM,
        l_mm - 2 * WALL_THICKNESS_MM,
        branch_height_mm + 2 * WALL_THICKNESS_MM,
        App.Vector(
            branch_x_min_mm + WALL_THICKNESS_MM,
            branch_y_min_mm + WALL_THICKNESS_MM,
            -WALL_THICKNESS_MM,
        ),
    )
    host_cutter = Part.makeCylinder(
        d1_radius,
        l_mm + 2 * WALL_THICKNESS_MM,
        App.Vector(0, branch_y_min_mm - WALL_THICKNESS_MM, 0),
        App.Vector(0, 1, 0),
    )
    fitting = outer.cut(inner).cut(host_cutter)
    if not fitting.isValid() or len(fitting.Solids) != 1:
        raise RuntimeError("PR/PRA review geometry must produce one valid solid.")

    dimensions = {
        "d1_mm": d1_mm,
        "d1_radius_mm": d1_radius,
        "b_mm": b_mm,
        "l_mm": l_mm,
        "asymmetry_mm": asymmetry_mm,
        "maximum_asymmetry_mm": maximum_asymmetry_mm,
        "branch_x_min_mm": branch_x_min_mm,
        "height_above_host_crown_mm": HEIGHT_ABOVE_HOST_CROWN_MM,
        "branch_height_mm": branch_height_mm,
        "wall_thickness_mm": WALL_THICKNESS_MM,
    }
    return fitting, dimensions


def write_review(out_dir, d1_mm, b_mm, l_mm, asymmetry_mm, asymmetry_mode, keep_document_open=False):
    out_dir.mkdir(parents=True, exist_ok=True)
    fitting, dimensions = build_pr_pra(d1_mm, b_mm, l_mm, asymmetry_mm)
    d1_label = _dimension_label(d1_mm)
    b_label = _dimension_label(b_mm)
    l_label = _dimension_label(l_mm)
    asymmetry_label = _asymmetry_label(asymmetry_mm, asymmetry_mode)
    model_name = f"PR_PRA_{d1_label}_{b_label}x{l_label}_{asymmetry_label}_review"

    document = App.newDocument(model_name)
    try:
        feature = document.addObject("Part::Feature", "PR_PRA_Fitting")
        feature.Label = f"PR/PRA {d1_label} B{b_label}x{l_label} {asymmetry_label} review"
        feature.Shape = fitting
        feature.addProperty("App::PropertyString", "ReviewScope", "Review")
        feature.ReviewScope = (
            "Rectangular branch only. D1 is a Boolean cutter and is not exported."
        )
        for name, value in dimensions.items():
            _add_length_property(feature, name.title().replace("_", ""), value, name)
        if feature.ViewObject is not None:
            feature.ViewObject.ShapeColor = (0.35, 0.65, 1.0)
            feature.ViewObject.LineColor = (0.05, 0.15, 0.45)

        data = document.addObject("App::FeaturePython", "Review_Data")
        data.Label = f"PR/PRA {d1_label} B{b_label}x{l_label} review assumptions"
        data.addProperty("App::PropertyString", "AsymmetryInput", "Review")
        data.AsymmetryInput = (
            f"{asymmetry_mode}: rectangular branch centre X = {asymmetry_mm:g} mm; "
            f"A maximum = (D1 - B) / 2 = {dimensions['maximum_asymmetry_mm']:g} mm."
        )
        data.addProperty("App::PropertyString", "Construction", "Review")
        data.Construction = (
            "A hollow B x L rectangular branch extends 100 mm above D1's crown. "
            "D1 forms the concave lower contact and is not exported."
        )
        data.addProperty("App::PropertyString", "CatalogueStatus", "Review")
        data.CatalogueStatus = (
            "PR/PRA B-versus-D1 catalogue variant mapping is not yet released."
        )

        document.recompute()
        if not feature.Shape.isValid() or len(feature.Shape.Solids) != 1:
            raise RuntimeError("Saved PR/PRA review fitting is not one valid solid.")

        fcstd_path = out_dir / f"{model_name}.FCStd"
        step_path = out_dir / f"{model_name}.step"
        metadata_path = out_dir / f"{model_name}.json"
        document.saveAs(str(fcstd_path))
        Part.export([feature], str(step_path))
        metadata_path.write_text(
            json.dumps(
                {
                    "schema": "pr-pra-review-v1",
                    "dimensions_mm": dimensions,
                    "asymmetry_mode": asymmetry_mode,
                    "assumptions": [
                        "D1 is a Boolean cutter and is not exported.",
                        "The rectangular B x L branch projects 100 mm above the D1 crown.",
                        "S is centred and A places the branch's right side at D1's right tangent.",
                        "The PR/PRA catalogue variant mapping is not yet declared.",
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
        from PySide6 import QtWidgets
    except ImportError:
        from PySide import QtGui as QtWidgets
    return QtWidgets


def _wait_for_gui_frames(frame_count=50, frame_delay_seconds=0.1):
    application = _gui_modules().QApplication.instance()
    for _ in range(frame_count):
        application.processEvents()
        time.sleep(frame_delay_seconds)


def _close_start_page(main_window):
    widgets = _gui_modules()
    for subwindow in main_window.findChildren(widgets.QMdiSubWindow):
        if subwindow.windowTitle() == "Start":
            subwindow.close()


def run_gui_review(out_dir, d1_mm, b_mm, l_mm, asymmetry_mm, asymmetry_mode):
    """Build a dialog-free tiled FreeCAD GUI review."""
    if not App.GuiUp:
        raise RuntimeError("The tiled review requires a FreeCAD GUI session.")

    import FreeCADGui as Gui

    result = write_review(
        out_dir,
        d1_mm,
        b_mm,
        l_mm,
        asymmetry_mm,
        asymmetry_mode,
        keep_document_open=True,
    )
    main_window = Gui.getMainWindow()
    main_window.showMaximized()
    _close_start_page(main_window)

    views = ("viewAxonometric", "viewFront", "viewRight", "viewTop")
    gui_document = Gui.activeDocument()
    view = gui_document.activeView()
    review_views = []
    for index, view_method in enumerate(views):
        getattr(view, view_method)()
        view.fitAll()
        review_views.append(view)
        if index < len(views) - 1:
            Gui.runCommand("Std_ViewCreate", 0)
            view = gui_document.activeView()

    Gui.runCommand("Std_TileWindows", 0)
    for review_view in review_views:
        review_view.fitAll()
        review_view.redraw()
    _wait_for_gui_frames()
    result["view_count"] = len(review_views)
    return result


def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]
    if App.GuiUp and not argv:
        default_out_dir = Path.home() / "Documents" / "ductbuild-pr-pra-review"
        asymmetry_mm, asymmetry_mode = _resolve_asymmetry(
            DEFAULT_GUI_ASYMMETRY,
            DEFAULT_GUI_D1_MM,
            DEFAULT_GUI_B_MM,
        )
        result = run_gui_review(
            default_out_dir,
            DEFAULT_GUI_D1_MM,
            DEFAULT_GUI_B_MM,
            DEFAULT_GUI_L_MM,
            asymmetry_mm,
            asymmetry_mode,
        )
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0

    parser = argparse.ArgumentParser(
        description="Create a standalone PR/PRA rectangular-branch review model."
    )
    parser.add_argument("--out", required=True, type=Path, help="Output folder for FCStd, STEP, and review JSON.")
    parser.add_argument("--d1-mm", required=True, type=_positive_number, help="D1 round-host diameter in millimetres.")
    parser.add_argument("--b-mm", required=True, type=_positive_number, help="Rectangular branch B width in millimetres.")
    parser.add_argument("--l-mm", required=True, type=_positive_number, help="Rectangular branch L length in millimetres.")
    parser.add_argument(
        "--asymmetry",
        required=True,
        help="S for centred, A for right tangent, or a number less than (D1 - B) / 2.",
    )
    arguments = parser.parse_args(argv)
    try:
        _validate_dimensions(arguments.d1_mm, arguments.b_mm, arguments.l_mm)
        asymmetry_mm, asymmetry_mode = _resolve_asymmetry(
            arguments.asymmetry,
            arguments.d1_mm,
            arguments.b_mm,
        )
    except ValueError as error:
        parser.error(str(error))
    result = write_review(
        arguments.out.expanduser().resolve(),
        arguments.d1_mm,
        arguments.b_mm,
        arguments.l_mm,
        asymmetry_mm,
        asymmetry_mode,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
