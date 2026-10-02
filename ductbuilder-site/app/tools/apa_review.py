"""Create a review-only AIRKAN APA round-branch model.

APA contains the AP symmetric case. Use S to place the D2 branch on D1's
centre plane; use A to align D2's right tangent with D1's right tangent; or
enter a right-side partial offset. Consequently, APA S supersedes the
standalone AP review construction without changing the approved AP script.

Example:
    "C:\Program Files\FreeCAD 1.1\bin\python.exe" ^
        app\tools\apa_review.py --out C:\temp\apa-review ^
        --d1-mm 200 --d2-mm 90 --asymmetry S --e-mm 20

When run in a FreeCAD GUI with no arguments, the script opens the
dialog-free 200-90 S review fixture in four tiled native 3D views. Use
command-line arguments or the companion macro environment variables to
select another fixture without prompts.
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


TRANSITION_HEIGHT_MM = 60.0
WALL_THICKNESS_MM = 1.0
SADDLE_LENGTH_ALLOWANCE_MM = 120.0
CONTACT_WIDTH_ALLOWANCE_MM = 100.0
DEFAULT_GUI_D1_MM = 200.0
DEFAULT_GUI_D2_MM = 90.0
DEFAULT_GUI_ASYMMETRY = "S"
DEFAULT_GUI_E_MM = 20.0


def _positive_number(value):
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise argparse.ArgumentTypeError("Enter a positive finite number.")
    return number


def _nonnegative_number(value):
    number = float(value)
    if not math.isfinite(number) or number < 0:
        raise argparse.ArgumentTypeError("Enter a non-negative finite number.")
    return number


def _validate_diameters(d1_mm, d2_mm):
    if d1_mm <= d2_mm:
        raise ValueError("D1 must be greater than D2.")
    if d2_mm <= 2 * WALL_THICKNESS_MM:
        raise ValueError(
            f"D2 must exceed {2 * WALL_THICKNESS_MM:g} mm to create the hollow tube."
        )


def _resolve_asymmetry(value, d1_mm, d2_mm):
    text = str(value).strip()
    maximum_asymmetry_mm = (d1_mm - d2_mm) / 2
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
            "Numeric asymmetry must be less than the fully asymmetric "
            f"position ({maximum_asymmetry_mm:g} mm). Use A when D2's right "
            "tangent must align with D1's right tangent."
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


def _rectangle_wire(width_mm, depth_mm, z_mm, center_x_mm):
    half_width = width_mm / 2
    half_depth = depth_mm / 2
    points = [
        App.Vector(center_x_mm - half_width, -half_depth, z_mm),
        App.Vector(center_x_mm + half_width, -half_depth, z_mm),
        App.Vector(center_x_mm + half_width, half_depth, z_mm),
        App.Vector(center_x_mm - half_width, half_depth, z_mm),
        App.Vector(center_x_mm - half_width, -half_depth, z_mm),
    ]
    return Part.makePolygon(points)


def _circle_wire(radius_mm, z_mm, center_x_mm):
    return Part.Wire([Part.makeCircle(radius_mm, App.Vector(center_x_mm, 0, z_mm))])


def _fuse(shapes):
    result = shapes[0]
    for shape in shapes[1:]:
        result = result.fuse(shape)
    return result.removeSplitter()


def _add_length_property(feature, name, value, description):
    feature.addProperty("App::PropertyLength", name, "Dimensions", description)
    setattr(feature, name, value)


def build_apa(d1_mm, d2_mm, asymmetry_mm, e_mm):
    """Return the hollow APA fitting and review dimensions in millimetres."""
    _validate_diameters(d1_mm, d2_mm)
    maximum_asymmetry_mm = (d1_mm - d2_mm) / 2
    if not math.isfinite(asymmetry_mm) or not 0 <= asymmetry_mm <= maximum_asymmetry_mm:
        raise ValueError(
            "Asymmetry must be from 0 through the fully asymmetric "
            f"position ({maximum_asymmetry_mm:g} mm)."
        )
    if not math.isfinite(e_mm) or e_mm < 0:
        raise ValueError("e must be a non-negative finite number.")

    d1_radius = d1_mm / 2
    d2_radius = d2_mm / 2
    saddle_length_mm = d2_mm + SADDLE_LENGTH_ALLOWANCE_MM
    requested_contact_width_mm = d2_mm + CONTACT_WIDTH_ALLOWANCE_MM
    contact_width_mm = min(requested_contact_width_mm, d1_mm)
    contact_half_width_mm = contact_width_mm / 2
    saddle_edge_z_mm = math.sqrt(d1_radius**2 - contact_half_width_mm**2)
    shoulder_z_mm = d1_radius
    spigot_start_z_mm = shoulder_z_mm + TRANSITION_HEIGHT_MM
    spigot_end_z_mm = spigot_start_z_mm + e_mm

    # D1 remains on its own centre plane. APA moves D2 right: A puts D2's
    # right tangent at D1's right tangent; S makes this the AP construction.
    d2_center_x_mm = asymmetry_mm

    outer_base = _rectangle_wire(contact_width_mm, saddle_length_mm, saddle_edge_z_mm, 0)
    outer_shoulder = _rectangle_wire(d2_mm, d2_mm, shoulder_z_mm, d2_center_x_mm)
    outer_circle = _circle_wire(d2_radius, spigot_start_z_mm, d2_center_x_mm)
    outer_pyramid = Part.makeLoft([outer_base, outer_shoulder], True, True)
    outer_loft = Part.makeLoft([outer_shoulder, outer_circle], True, False)
    outer_spigot = Part.makeCylinder(
        d2_radius,
        e_mm,
        App.Vector(d2_center_x_mm, 0, spigot_start_z_mm),
    )
    outer = _fuse([outer_pyramid, outer_loft, outer_spigot])

    inner_base = _rectangle_wire(
        contact_width_mm - 2 * WALL_THICKNESS_MM,
        saddle_length_mm - 2 * WALL_THICKNESS_MM,
        saddle_edge_z_mm - WALL_THICKNESS_MM,
        0,
    )
    inner_shoulder = _rectangle_wire(
        d2_mm - 2 * WALL_THICKNESS_MM,
        d2_mm - 2 * WALL_THICKNESS_MM,
        shoulder_z_mm,
        d2_center_x_mm,
    )
    inner_circle = _circle_wire(
        d2_radius - WALL_THICKNESS_MM,
        spigot_start_z_mm,
        d2_center_x_mm,
    )
    inner_pyramid = Part.makeLoft([inner_base, inner_shoulder], True, True)
    inner_loft = Part.makeLoft([inner_shoulder, inner_circle], True, False)
    inner_spigot = Part.makeCylinder(
        d2_radius - WALL_THICKNESS_MM,
        e_mm + WALL_THICKNESS_MM,
        App.Vector(d2_center_x_mm, 0, spigot_start_z_mm),
    )
    inner = _fuse([inner_pyramid, inner_loft, inner_spigot])

    host_cutter = Part.makeCylinder(
        d1_radius,
        saddle_length_mm + 20,
        App.Vector(0, -(saddle_length_mm + 20) / 2, 0),
        App.Vector(0, 1, 0),
    )
    fitting = outer.cut(inner).cut(host_cutter).removeSplitter()
    if not fitting.isValid() or len(fitting.Solids) != 1:
        raise RuntimeError("APA review geometry must produce one valid solid.")

    dimensions = {
        "d1_mm": d1_mm,
        "d2_mm": d2_mm,
        "d1_radius_mm": d1_radius,
        "d2_radius_mm": d2_radius,
        "asymmetry_mm": asymmetry_mm,
        "maximum_asymmetry_mm": maximum_asymmetry_mm,
        "d2_center_x_mm": d2_center_x_mm,
        "transition_height_mm": TRANSITION_HEIGHT_MM,
        "e_mm": e_mm,
        "straight_spigot_end_z_mm": spigot_end_z_mm,
        "saddle_length_mm": saddle_length_mm,
        "requested_contact_width_mm": requested_contact_width_mm,
        "contact_width_mm": contact_width_mm,
        "saddle_edge_z_mm": saddle_edge_z_mm,
        "wall_thickness_mm": WALL_THICKNESS_MM,
    }
    return fitting, dimensions


def write_review(out_dir, d1_mm, d2_mm, asymmetry_mm, asymmetry_mode, e_mm, keep_document_open=False):
    out_dir.mkdir(parents=True, exist_ok=True)
    fitting, dimensions = build_apa(d1_mm, d2_mm, asymmetry_mm, e_mm)
    d1_label = _dimension_label(d1_mm)
    d2_label = _dimension_label(d2_mm)
    asymmetry_label = _asymmetry_label(asymmetry_mm, asymmetry_mode)
    model_name = f"APA_{d1_label}_{d2_label}_{asymmetry_label}_review"

    document = App.newDocument(model_name)
    try:
        feature = document.addObject("Part::Feature", "APA_Fitting")
        feature.Label = f"APA {d1_label}-{d2_label} {asymmetry_label} review fitting"
        feature.Shape = fitting
        feature.addProperty(
            "App::PropertyString",
            "ReviewScope",
            "Review",
            "What this standalone review model represents.",
        )
        feature.ReviewScope = (
            "APA fitting only. The D1 host duct is a Boolean cutter and is not exported."
        )
        for name, value in dimensions.items():
            _add_length_property(feature, name.title().replace("_", ""), value, name)
        if feature.ViewObject is not None:
            feature.ViewObject.ShapeColor = (0.12, 0.12, 0.12)
            feature.ViewObject.LineColor = (0.0, 0.0, 0.0)

        data = document.addObject("App::FeaturePython", "Review_Data")
        data.Label = f"APA {d1_label}-{d2_label} review assumptions"
        data.addProperty("App::PropertyString", "AsymmetryInput", "Review")
        data.AsymmetryInput = (
            f"{asymmetry_mode}: D2 centre X = {asymmetry_mm:g} mm; "
            f"A maximum = (D1 - D2) / 2 = {dimensions['maximum_asymmetry_mm']:g} mm."
        )
        data.addProperty("App::PropertyString", "Construction", "Review")
        data.Construction = (
            "D1 is used only as a cutter. The D2 shoulder moves right while the "
            "D1 contact footprint remains centred; A aligns D2's right tangent "
            "with D1's right tangent. S is the symmetric AP construction."
        )
        data.addProperty("App::PropertyString", "ContactWidth", "Review")
        data.ContactWidth = (
            "Requested contact width = D2 + 100 mm. It is limited to D1 so "
            "the review saddle remains on the D1 host surface."
        )

        document.recompute()
        if not feature.Shape.isValid() or len(feature.Shape.Solids) != 1:
            raise RuntimeError("Saved APA review fitting is not one valid solid.")

        fcstd_path = out_dir / f"{model_name}.FCStd"
        step_path = out_dir / f"{model_name}.step"
        metadata_path = out_dir / f"{model_name}.json"
        document.saveAs(str(fcstd_path))
        Part.export([feature], str(step_path))
        metadata_path.write_text(
            json.dumps(
                {
                    "schema": "apa-review-v1",
                    "dimensions_mm": dimensions,
                    "asymmetry_mode": asymmetry_mode,
                    "assumptions": [
                        "D1 is a Boolean cutter and is not exported.",
                        "S is the symmetric AP construction.",
                        "A places D2's right tangent on D1's right tangent.",
                        "A partial numeric value moves D2 right by that direct offset.",
                        "Transition height = 60 mm.",
                        "The model is a geometry review, not fabrication-certified sheet metal.",
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


def _prompt_for_number(widgets, label, prompt, validator):
    while True:
        value, accepted = widgets.QInputDialog.getText(None, label, prompt)
        if not accepted:
            return None
        try:
            return validator(value)
        except argparse.ArgumentTypeError as error:
            widgets.QMessageBox.warning(None, label, str(error))


def _prompt_for_inputs(widgets):
    label = "APA round branch review"
    while True:
        d1_mm = _prompt_for_number(widgets, label, "Enter D1 host diameter (mm):", _positive_number)
        if d1_mm is None:
            return None
        d2_mm = _prompt_for_number(widgets, label, "Enter D2 branch diameter (mm):", _positive_number)
        if d2_mm is None:
            return None
        try:
            _validate_diameters(d1_mm, d2_mm)
        except ValueError as error:
            widgets.QMessageBox.warning(None, label, str(error))
            continue
        maximum_asymmetry_mm = (d1_mm - d2_mm) / 2
        while True:
            value, accepted = widgets.QInputDialog.getText(
                None,
                label,
                "Enter asymmetry: A = D2 right tangent on D1 right tangent, "
                "S = symmetric/AP, or a number from 0 up to (but excluding) "
                f"the fully asymmetric position ({maximum_asymmetry_mm:g} mm):",
            )
            if not accepted:
                return None
            try:
                asymmetry_mm, asymmetry_mode = _resolve_asymmetry(value, d1_mm, d2_mm)
                break
            except ValueError as error:
                widgets.QMessageBox.warning(None, label, str(error))
        e_mm = _prompt_for_number(
            widgets,
            label,
            "Enter e (mm), the straight D2 spigot length in the AIRKAN drawing:",
            _nonnegative_number,
        )
        if e_mm is not None:
            return d1_mm, d2_mm, asymmetry_mm, asymmetry_mode, e_mm


def _default_gui_output_dir(core):
    desktop = core.QStandardPaths.writableLocation(core.QStandardPaths.StandardLocation.DesktopLocation)
    return Path(desktop) if desktop else Path.home()


def run_interactive():
    core, widgets = _gui_modules()
    inputs = _prompt_for_inputs(widgets)
    if inputs is None:
        return 0
    d1_mm, d2_mm, asymmetry_mm, asymmetry_mode, e_mm = inputs
    selected = widgets.QFileDialog.getExistingDirectory(
        None,
        "Choose APA review output folder",
        str(_default_gui_output_dir(core)),
    )
    if not selected:
        return 0
    try:
        result = write_review(
            Path(selected),
            d1_mm,
            d2_mm,
            asymmetry_mm,
            asymmetry_mode,
            e_mm,
            keep_document_open=True,
        )
    except (OSError, RuntimeError, ValueError) as error:
        widgets.QMessageBox.critical(None, "APA review failed", str(error))
        return 1
    import FreeCADGui as Gui

    Gui.activeDocument().activeView().viewAxonometric()
    Gui.activeDocument().activeView().fitAll()
    widgets.QMessageBox.information(
        None,
        "APA review exported",
        "Review document is open in FreeCAD.\n\n"
        "FCStd:\n" + result["fcstd"] + "\n\n"
        "STEP:\n" + result["step"] + "\n\n"
        "Review JSON:\n" + result["metadata"],
    )
    return 0


def _wait_for_gui_frames(frame_count=50, frame_delay_seconds=0.1):
    """Let FreeCAD finish painting the tiled 3D views."""
    _, widgets = _gui_modules()
    application = widgets.QApplication.instance()
    for _ in range(frame_count):
        application.processEvents()
        time.sleep(frame_delay_seconds)


def _close_start_page(main_window):
    """Remove FreeCAD's Start page so it cannot become a fifth tiled window."""
    _, widgets = _gui_modules()
    for subwindow in main_window.findChildren(widgets.QMdiSubWindow):
        if subwindow.windowTitle() == "Start":
            subwindow.close()


def run_gui_review(out_dir, d1_mm, d2_mm, asymmetry_mm, asymmetry_mode, e_mm):
    """Build a dialog-free tiled FreeCAD GUI review."""
    if not App.GuiUp:
        raise RuntimeError("The tiled review requires a FreeCAD GUI session.")

    import FreeCADGui as Gui

    result = write_review(
        out_dir,
        d1_mm,
        d2_mm,
        asymmetry_mm,
        asymmetry_mode,
        e_mm,
        keep_document_open=True,
    )
    main_window = Gui.getMainWindow()
    main_window.showMaximized()
    _close_start_page(main_window)

    views = (
        "viewAxonometric",
        "viewFront",
        "viewRight",
        "viewTop",
    )
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
    required_arguments = {"--out", "--d1-mm", "--d2-mm", "--asymmetry", "--e-mm"}
    if App.GuiUp and not argv:
        default_out_dir = Path.home() / "Documents" / "ductbuild-apa-review"
        asymmetry_mm, asymmetry_mode = _resolve_asymmetry(
            DEFAULT_GUI_ASYMMETRY,
            DEFAULT_GUI_D1_MM,
            DEFAULT_GUI_D2_MM,
        )
        result = run_gui_review(
            default_out_dir,
            DEFAULT_GUI_D1_MM,
            DEFAULT_GUI_D2_MM,
            asymmetry_mm,
            asymmetry_mode,
            DEFAULT_GUI_E_MM,
        )
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    parser = argparse.ArgumentParser(description="Create a standalone APA round-branch review model.")
    parser.add_argument("--out", required=True, type=Path, help="Output folder for FCStd, STEP, and review JSON.")
    parser.add_argument("--d1-mm", required=True, type=_positive_number, help="D1 host diameter in millimetres.")
    parser.add_argument("--d2-mm", required=True, type=_positive_number, help="D2 branch diameter in millimetres.")
    parser.add_argument(
        "--asymmetry",
        required=True,
        help="A for right-tangent alignment, S for symmetric/AP, or a partial right-side offset.",
    )
    parser.add_argument(
        "--e-mm",
        required=True,
        type=_nonnegative_number,
        help="Straight D2 spigot length marked e in the supplier drawing.",
    )
    arguments = parser.parse_args(argv)
    try:
        _validate_diameters(arguments.d1_mm, arguments.d2_mm)
        asymmetry_mm, asymmetry_mode = _resolve_asymmetry(
            arguments.asymmetry,
            arguments.d1_mm,
            arguments.d2_mm,
        )
    except ValueError as error:
        parser.error(str(error))
    result = write_review(
        arguments.out.expanduser().resolve(),
        arguments.d1_mm,
        arguments.d2_mm,
        asymmetry_mm,
        asymmetry_mode,
        arguments.e_mm,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
