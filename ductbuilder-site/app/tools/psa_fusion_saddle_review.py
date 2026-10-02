"""Create a review-only PSA model using the supplied Fusion-style Boolean order.

The existing psa_review.py is intentionally untouched. This standalone review
builds a hollow Ø1 tube, cuts the Ø2 opening, joins a hollow vertical Ø2 tube,
then retains a 10 mm band around the actual Ø1/Ø2 seam. Ø1 is never exported
as a complete host tube; only the retained saddle patch remains.

Example:
    "C:\Program Files\FreeCAD 1.1\bin\python.exe" ^
        app\tools\psa_fusion_saddle_review.py --out C:\temp\psa-review ^
        --d1-mm 200 --d2-mm 100 --asymmetry A

When run as a FreeCAD GUI macro without arguments, the script opens a
dialog-free 200-100 A review fixture and creates four tiled native 3D views.
Use command-line arguments to select another fixture without prompts.
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


SADDLE_WIDTH_MM = 10.0
WALL_THICKNESS_MM = 1.0
DEFAULT_GUI_D1_MM = 200.0
DEFAULT_GUI_D2_MM = 100.0
DEFAULT_GUI_ASYMMETRY = "A"


def _positive_number(value):
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise argparse.ArgumentTypeError("Enter a positive finite number.")
    return number


def _validate_diameters(d1_mm, d2_mm):
    if d1_mm <= d2_mm:
        raise ValueError("D1 must be greater than D2.")
    if d2_mm <= 2 * WALL_THICKNESS_MM:
        raise ValueError(
            f"D2 must exceed {2 * WALL_THICKNESS_MM:g} mm to create the hollow tube."
        )


def _validate_asymmetry(asymmetry_mm, d2_mm):
    if not math.isfinite(asymmetry_mm) or asymmetry_mm < 0:
        raise ValueError("Asymmetry must be a non-negative finite number.")
    if asymmetry_mm > d2_mm / 2:
        raise ValueError(f"Asymmetry cannot exceed D2 / 2 ({d2_mm / 2:g} mm).")


def _resolve_asymmetry(value, d2_mm):
    text = str(value).strip()
    maximum_asymmetry_mm = d2_mm / 2
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
            f"Numeric asymmetry must be less than D2 / 2 ({maximum_asymmetry_mm:g} mm). "
            "Use A for the fully asymmetric tangential position."
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


def _closed_loop_area(points):
    return sum(
        point[0] * points[(index + 1) % len(points)][1]
        - points[(index + 1) % len(points)][0] * point[1]
        for index, point in enumerate(points)
    ) / 2


def _resample_closed_loop(points, count):
    if len(points) < 3:
        raise RuntimeError("A developed seam loop requires at least three points.")

    cumulative_lengths = []
    total_length = 0.0
    for index, point in enumerate(points):
        next_point = points[(index + 1) % len(points)]
        total_length += math.hypot(next_point[0] - point[0], next_point[1] - point[1])
        cumulative_lengths.append(total_length)
    if total_length <= 0:
        raise RuntimeError("A developed seam loop must have a positive length.")

    samples = []
    for sample_index in range(count):
        target_length = total_length * sample_index / count
        previous_length = 0.0
        for edge_index, end_length in enumerate(cumulative_lengths):
            if target_length <= end_length:
                start = points[edge_index]
                end = points[(edge_index + 1) % len(points)]
                fraction = (target_length - previous_length) / (end_length - previous_length)
                samples.append(
                    (
                        start[0] + (end[0] - start[0]) * fraction,
                        start[1] + (end[1] - start[1]) * fraction,
                    )
                )
                break
            previous_length = end_length
    return samples


def _wire_xy_points(wire):
    points = []
    for edge in wire.Edges:
        points.extend((point.x, point.y) for point in edge.discretize(12)[:-1])
    if len(points) < 3:
        raise RuntimeError("The 10 mm seam offset did not produce a closed wire.")
    return points


def _periodic_curve(points):
    curve = Part.BSplineCurve()
    curve.interpolate([App.Vector(*point) for point in points], True)
    return curve.toShape()


def _map_developed_loop(points, radius, d1_center_x, d1_outer_radius):
    return [
        (
            d1_center_x + radius * math.cos(developed_x / d1_outer_radius),
            developed_y,
            -d1_outer_radius + radius * math.sin(developed_x / d1_outer_radius),
        )
        for developed_x, developed_y in points
    ]


def _build_joined_developed_saddle(
    d1_radius,
    d2_radius,
    d1_center_x,
    wall_thickness,
    saddle_width,
    d2_spigot_height,
):
    """Create the joined D1 saddle band and D2 shell as one closed BRep shell."""
    seam_sample_count = 128
    ruled_sample_count = 96
    start_angle = math.acos((d2_radius - d1_center_x) / d1_radius)
    end_angle = math.acos((-d2_radius - d1_center_x) / d1_radius)

    seam_loop = []
    for index in range(seam_sample_count + 1):
        angle = start_angle + (end_angle - start_angle) * index / seam_sample_count
        x = d1_center_x + d1_radius * math.cos(angle)
        seam_loop.append(
            (
                d1_radius * angle,
                math.sqrt(max(0.0, d2_radius * d2_radius - x * x)),
            )
        )
    for index in range(seam_sample_count - 1, 0, -1):
        angle = start_angle + (end_angle - start_angle) * index / seam_sample_count
        x = d1_center_x + d1_radius * math.cos(angle)
        seam_loop.append(
            (
                d1_radius * angle,
                -math.sqrt(max(0.0, d2_radius * d2_radius - x * x)),
            )
        )
    if _closed_loop_area(seam_loop) < 0:
        seam_loop.reverse()

    developed_seam = Part.makePolygon(
        [App.Vector(seam_x, seam_y, 0) for seam_x, seam_y in seam_loop + [seam_loop[0]]]
    )
    developed_offset = developed_seam.makeOffset2D(
        saddle_width,
        join=0,
        fill=False,
        openResult=False,
        intersection=False,
    )
    offset_loop = _wire_xy_points(developed_offset)
    if _closed_loop_area(offset_loop) < 0:
        offset_loop.reverse()

    seam_loop = _resample_closed_loop(seam_loop, ruled_sample_count)
    offset_loop = _resample_closed_loop(offset_loop, ruled_sample_count)
    seam_start = seam_loop[0]
    offset_start_index = min(
        range(ruled_sample_count),
        key=lambda index: (
            (offset_loop[index][0] - seam_start[0]) ** 2
            + (offset_loop[index][1] - seam_start[1]) ** 2
        ),
    )
    offset_loop = offset_loop[offset_start_index:] + offset_loop[:offset_start_index]

    d1_inner_radius = d1_radius - wall_thickness
    outer_seam = _periodic_curve(
        _map_developed_loop(seam_loop, d1_radius, d1_center_x, d1_radius)
    )
    outer_offset = _periodic_curve(
        _map_developed_loop(offset_loop, d1_radius, d1_center_x, d1_radius)
    )
    inner_offset = _periodic_curve(
        _map_developed_loop(offset_loop, d1_inner_radius, d1_center_x, d1_radius)
    )

    outer_seam_points = _map_developed_loop(
        seam_loop,
        d1_radius,
        d1_center_x,
        d1_radius,
    )
    inner_seam_points = []
    outer_top_points = []
    inner_top_points = []
    d2_bore_radius = d2_radius - wall_thickness
    for outer_x, outer_y, _ in outer_seam_points:
        angle = math.atan2(outer_y, outer_x)
        inner_x = d2_bore_radius * math.cos(angle)
        inner_y = d2_bore_radius * math.sin(angle)
        inner_z = -d1_radius + math.sqrt(
            max(
                0.0,
                d1_inner_radius * d1_inner_radius
                - (inner_x - d1_center_x) * (inner_x - d1_center_x),
            )
        )
        inner_seam_points.append((inner_x, inner_y, inner_z))
        outer_top_points.append((outer_x, outer_y, d2_spigot_height))
        inner_top_points.append((inner_x, inner_y, d2_spigot_height))

    outer_seam = _periodic_curve(outer_seam_points)
    inner_seam = _periodic_curve(inner_seam_points)
    outer_top = _periodic_curve(outer_top_points)
    inner_top = _periodic_curve(inner_top_points)
    faces = [
        Part.makeRuledSurface(outer_seam, outer_offset),
        Part.makeRuledSurface(inner_offset, inner_seam),
        Part.makeRuledSurface(outer_offset, inner_offset),
        Part.makeRuledSurface(outer_seam, outer_top),
        Part.makeRuledSurface(inner_top, inner_seam),
        Part.makeRuledSurface(outer_top, inner_top),
    ]
    return Part.makeSolid(Part.makeShell(faces))


def build_psa_fusion_saddle(d1_mm, d2_mm, asymmetry_mm):
    """Return the hollow PSA saddle fitting and dimensions in millimetres."""
    _validate_diameters(d1_mm, d2_mm)
    _validate_asymmetry(asymmetry_mm, d2_mm)

    d1_radius = d1_mm / 2
    d2_radius = d2_mm / 2
    d2_spigot_height = 2 * d2_mm
    d1_front_y = -d1_mm
    d1_end_y = d1_mm

    # A is the direct right-side X coordinate of D1's centre. At A, D1's
    # centre lies on D2's right tangent plane X = +D2/2.
    d1_center_x = asymmetry_mm

    # D2's base plane is Z=0. D1 therefore occupies the space below it, with
    # its crown tangent to that plane. Centreing D1 on Z=0 incorrectly
    # retained two unrelated side fragments instead of its crown saddle.
    d1_center_z = -d1_radius
    # Develop the D1 surface around the true D1/D2 intersection, apply the
    # 10 mm Offset A there, then map the band back to D1's hollow curvature.
    # D2 is trimmed to that same seam rather than ending at a flat Z=0 rim.
    fitting = _build_joined_developed_saddle(
        d1_radius,
        d2_radius,
        d1_center_x,
        WALL_THICKNESS_MM,
        SADDLE_WIDTH_MM,
        d2_spigot_height,
    )
    if not fitting.isValid() or len(fitting.Solids) != 1:
        raise RuntimeError("Fusion-style PSA review geometry must produce one valid solid.")

    dimensions = {
        "d1_mm": d1_mm,
        "d2_mm": d2_mm,
        "d1_radius_mm": d1_radius,
        "d2_radius_mm": d2_radius,
        "asymmetry_mm": asymmetry_mm,
        "maximum_asymmetry_mm": d2_radius,
        "d1_center_x_mm": d1_center_x,
        "d1_center_z_mm": d1_center_z,
        "d1_front_y_mm": d1_front_y,
        "d1_end_y_mm": d1_end_y,
        "d2_spigot_height_mm": d2_spigot_height,
        "saddle_width_mm": SADDLE_WIDTH_MM,
        "wall_thickness_mm": WALL_THICKNESS_MM,
    }
    return fitting, dimensions


def write_review(out_dir, d1_mm, d2_mm, asymmetry_mm, asymmetry_mode, keep_document_open=False):
    out_dir.mkdir(parents=True, exist_ok=True)
    fitting, dimensions = build_psa_fusion_saddle(d1_mm, d2_mm, asymmetry_mm)
    d1_label = _dimension_label(d1_mm)
    d2_label = _dimension_label(d2_mm)
    asymmetry_label = _asymmetry_label(asymmetry_mm, asymmetry_mode)
    model_name = f"PSA_Fusion_{d1_label}_{d2_label}_{asymmetry_label}_review"

    document = App.newDocument(model_name)
    try:
        feature = document.addObject("Part::Feature", "PSA_Fusion_Saddle")
        feature.Label = f"PSA Fusion saddle {d1_label}-{d2_label} {asymmetry_label}"
        feature.Shape = fitting
        feature.addProperty(
            "App::PropertyString",
            "ReviewScope",
            "Review",
            "What this standalone review model represents.",
        )
        feature.ReviewScope = (
            "PSA fitting only. The full D1 host tube is a construction blank and is not exported."
        )
        for name, value in dimensions.items():
            _add_length_property(feature, name.title().replace("_", ""), value, name)
        if feature.ViewObject is not None:
            feature.ViewObject.ShapeColor = (0.12, 0.12, 0.12)
            feature.ViewObject.LineColor = (0.0, 0.0, 0.0)

        data = document.addObject("App::FeaturePython", "Review_Data")
        data.Label = f"PSA Fusion saddle assumptions {d1_label}-{d2_label}"
        data.addProperty("App::PropertyString", "AsymmetryInput", "Review")
        data.AsymmetryInput = (
            f"{asymmetry_mode}: {asymmetry_mm:g} mm; "
            f"maximum = D2 / 2 = {d2_mm / 2:g} mm."
        )
        data.addProperty("App::PropertyString", "Construction", "Review")
        data.Construction = (
            "Hollow D1 tube from Y=-D1 to Y=+D1 below D2's Z=0 base plane; "
            "retain D1 material within the 10 mm Offset A around D2; cut the "
            "D2 outer opening; bore D2 after joining it to the saddle."
        )
        data.addProperty("App::PropertyString", "SourceDrawingCorrection", "Review")
        data.SourceDrawingCorrection = (
            "The lower-right large-circle label in the supplied PSA drawing reads D2; it is D1."
        )

        document.recompute()
        if not feature.Shape.isValid() or len(feature.Shape.Solids) != 1:
            raise RuntimeError("Saved Fusion-style PSA fitting is not one valid solid.")

        fcstd_path = out_dir / f"{model_name}.FCStd"
        step_path = out_dir / f"{model_name}.step"
        metadata_path = out_dir / f"{model_name}.json"
        document.saveAs(str(fcstd_path))
        Part.export([feature], str(step_path))
        metadata_path.write_text(
            json.dumps(
                {
                    "schema": "psa-fusion-saddle-review-v1",
                    "dimensions_mm": dimensions,
                    "asymmetry_mode": asymmetry_mode,
                    "assumptions": [
                        "D1 is created as a hollow tube from Y=-D1 to Y=+D1 below Z=0.",
                        "The D2 outer opening cuts the retained D1 saddle.",
                        "The D2 bore creates a hollow D2 tube without removing its wall.",
                        "The retained D1 saddle is the material within Offset A = 10 mm around D2.",
                        "Offset B = 3 × D1 is represented by removing all material outside Offset A.",
                        "The full D1 host tube is not exported.",
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


def _wait_for_gui_frames(frame_count=50, frame_delay_seconds=0.1):
    """Let FreeCAD finish painting the tiled 3D views."""
    try:
        from PySide6 import QtWidgets
    except ImportError:
        from PySide import QtGui as QtWidgets
    application = QtWidgets.QApplication.instance()
    for _ in range(frame_count):
        application.processEvents()
        time.sleep(frame_delay_seconds)


def _close_start_page(main_window):
    """Remove FreeCAD's Start page so it cannot become a fifth tiled window."""
    try:
        from PySide6 import QtWidgets
    except ImportError:
        from PySide import QtGui as QtWidgets
    for subwindow in main_window.findChildren(QtWidgets.QMdiSubWindow):
        if subwindow.windowTitle() == "Start":
            subwindow.close()


def run_gui_review(out_dir, d1_mm, d2_mm, asymmetry_mm, asymmetry_mode):
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
    for view in review_views:
        view.fitAll()
        view.redraw()
    _wait_for_gui_frames()
    result["view_count"] = len(review_views)
    return result


def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]
    if App.GuiUp and not argv:
        default_out_dir = Path.home() / "Documents" / "ductbuild-psa-review"
        asymmetry_mm, asymmetry_mode = _resolve_asymmetry(
            DEFAULT_GUI_ASYMMETRY,
            DEFAULT_GUI_D2_MM,
        )
        result = run_gui_review(
            default_out_dir,
            DEFAULT_GUI_D1_MM,
            DEFAULT_GUI_D2_MM,
            asymmetry_mm,
            asymmetry_mode,
        )
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    parser = argparse.ArgumentParser(
        description="Create a standalone Fusion-style PSA saddle review model."
    )
    parser.add_argument("--out", required=True, type=Path, help="Output folder for FCStd, STEP, and review JSON.")
    parser.add_argument("--d1-mm", required=True, type=_positive_number, help="D1 big tube diameter in millimetres.")
    parser.add_argument("--d2-mm", required=True, type=_positive_number, help="D2 vertical tube diameter in millimetres.")
    parser.add_argument(
        "--asymmetry",
        required=True,
        help="A for fully asymmetric/right tangent, S for symmetric, or a number less than D2 / 2.",
    )
    parser.add_argument(
        "--gui-review",
        action="store_true",
        help="Open four tiled native 3D views without prompts or dialogs.",
    )
    arguments = parser.parse_args(argv)
    try:
        _validate_diameters(arguments.d1_mm, arguments.d2_mm)
        asymmetry_mm, asymmetry_mode = _resolve_asymmetry(arguments.asymmetry, arguments.d2_mm)
    except ValueError as error:
        parser.error(str(error))
    out_dir = arguments.out.expanduser().resolve()
    if arguments.gui_review:
        if not App.GuiUp:
            parser.error("--gui-review requires the FreeCAD GUI executable.")
        result = run_gui_review(
            out_dir,
            arguments.d1_mm,
            arguments.d2_mm,
            asymmetry_mm,
            asymmetry_mode,
        )
    else:
        result = write_review(
            out_dir,
            arguments.d1_mm,
            arguments.d2_mm,
            asymmetry_mm,
            asymmetry_mode,
        )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
