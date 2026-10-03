"""Create review-only rectangular T, asymmetric-T, and Talpha fittings.

The supplier drawings define three rectangular ports with a shared B depth:
left A x B, branch C x B, and right D x B.  This review model keeps the
special family separate from the production-only constant-section T generator.
"""
from __future__ import annotations

import argparse
from functools import lru_cache
import json
import math
import runpy
import sys
import time
from pathlib import Path

import FreeCAD as App
import Part


WALL_THICKNESS_MM = 1.0
SHOULDER_RADIUS_MM = 150.0
DEFAULT_GUI_VARIANT = "T"
DEFAULT_GUI_A_MM = 300.0
DEFAULT_GUI_B_MM = 200.0
DEFAULT_GUI_C_MM = 400.0
DEFAULT_GUI_D_MM = 300.0
DEFAULT_GUI_MAIN_LENGTH_MM = 1000.0
DEFAULT_GUI_BRANCH_LENGTH_MM = 300.0
DEFAULT_GUI_ALPHA_DEG = 45.0
DEFAULT_GUI_FRAME_PROFILE = "E20"
DEFAULT_GUI_TALPHA_E_MM = 300.0
DEFAULT_GUI_TALPHA_G_MM = 250.0
TALPHA_DIMENSION_TOLERANCE_MM = 1.0
TALPHA_MIN_K2_VERTICAL_CLEARANCE_MM = 100.0


def _positive_number(value):
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise argparse.ArgumentTypeError("Enter a positive finite number.")
    return number


def _variant(value):
    variant = str(value).strip().upper()
    if variant not in {"T", "TASYMM", "TALPHA"}:
        raise ValueError("Variant must be T, TASYMM, or TALPHA.")
    return variant


@lru_cache(maxsize=1)
def _frame_api():
    library_path = Path(__file__).resolve().parents[1] / "vendor" / "makeframe_v2.FCMacro"
    return runpy.run_path(
        str(library_path),
        init_globals={"MAKEFRAME_LIBRARY_ONLY": True},
    )


def _frame_profile(value):
    profile = str(value).strip().upper()
    supported = _frame_api()["PROFILE_SPECS"]
    if profile not in supported:
        raise ValueError(
            f"Frame profile must be one of {', '.join(sorted(supported))}."
        )
    return profile


def _validate_dimensions(
    variant,
    a_mm,
    b_mm,
    c_mm,
    d_mm,
    main_length_mm,
    branch_length_mm,
    alpha_deg,
    frame_profile,
):
    _frame_profile(frame_profile)
    dimensions = (a_mm, b_mm, c_mm, d_mm, main_length_mm, branch_length_mm)
    if any(value <= 2 * WALL_THICKNESS_MM for value in dimensions):
        raise ValueError(
            f"All section and length dimensions must exceed {2 * WALL_THICKNESS_MM:g} mm."
        )
    if c_mm >= main_length_mm:
        raise ValueError("C must be smaller than the main length.")
    if variant in {"T", "TASYMM"} and c_mm <= 2 * (SHOULDER_RADIUS_MM + WALL_THICKNESS_MM):
        raise ValueError(
            f"T and TASYMM require C to exceed {2 * (SHOULDER_RADIUS_MM + WALL_THICKNESS_MM):g} mm "
            f"for two R={SHOULDER_RADIUS_MM:g} mm throat rounds."
        )
    if variant == "T" and not math.isclose(a_mm, d_mm, abs_tol=1e-9):
        raise ValueError("T requires A and D to be equal; use TASYMM for unequal main ports.")
    if variant == "TALPHA" and not 5.0 <= alpha_deg <= 85.0:
        raise ValueError("TALPHA alpha must be between 5 and 85 degrees.")


def _profile_prism(points, depth_mm, y_origin_mm):
    vectors = [App.Vector(x_mm, y_origin_mm, z_mm) for x_mm, z_mm in points]
    wire = Part.makePolygon(vectors + [vectors[0]])
    return Part.Face(wire).extrude(App.Vector(0, depth_mm, 0))


def _main_prism(
    a_mm,
    d_mm,
    main_length_mm,
    depth_mm,
    y_origin_mm,
    bottom_z_mm,
    x_origin_mm=0,
):
    return _profile_prism(
        [
            (x_origin_mm, bottom_z_mm),
            (x_origin_mm + main_length_mm, bottom_z_mm),
            (x_origin_mm + main_length_mm, d_mm - bottom_z_mm),
            (x_origin_mm, a_mm - bottom_z_mm),
        ],
        depth_mm,
        y_origin_mm,
    )


def _dot(left, right):
    return sum(left[index] * right[index] for index in range(3))


def _length(vector):
    return math.sqrt(_dot(vector, vector))


def _validate_axes(local_x, local_y, local_z):
    axes = (local_x, local_y, local_z)
    if any(not math.isclose(_length(axis), 1.0, abs_tol=1e-9) for axis in axes):
        raise ValueError("Frame axes must be unit vectors.")
    if any(
        not math.isclose(_dot(axes[index], axes[other]), 0.0, abs_tol=1e-9)
        for index in range(3)
        for other in range(index + 1, 3)
    ):
        raise ValueError("Frame axes must be orthogonal.")


def _place_frame_shape(shape, origin, local_x, local_y, local_z):
    _validate_axes(local_x, local_y, local_z)
    matrix = App.Matrix()
    matrix.A11, matrix.A12, matrix.A13, matrix.A14 = (
        local_x[0],
        local_y[0],
        local_z[0],
        origin[0],
    )
    matrix.A21, matrix.A22, matrix.A23, matrix.A24 = (
        local_x[1],
        local_y[1],
        local_z[1],
        origin[1],
    )
    matrix.A31, matrix.A32, matrix.A33, matrix.A34 = (
        local_x[2],
        local_y[2],
        local_z[2],
        origin[2],
    )
    matrix.A41, matrix.A42, matrix.A43, matrix.A44 = 0, 0, 0, 1
    return shape.transformGeometry(matrix)


def _build_port_frame(
    name,
    profile,
    opening_length_mm,
    opening_width_mm,
    origin,
    local_x,
    local_y,
    local_z,
):
    frame = _frame_api()["build_frame_geometry"](
        profile=profile,
        length=opening_length_mm,
        width=opening_width_mm,
        backend="freecad",
    )
    parts = []
    for frame_part in frame["parts"]:
        shape = _place_frame_shape(
            frame_part["shape"],
            origin,
            local_x,
            local_y,
            local_z,
        )
        if not shape.isValid() or len(shape.Solids) != 1:
            raise RuntimeError(f"Invalid {name} frame component: {frame_part['name']}.")
        parts.append(
            {
                "name": f"{name}_{frame_part['name']}",
                "code": frame_part["code"],
                "role": frame_part["role"],
                "shape": shape,
            }
        )
    return parts, frame["config"]


def _inner_main_top_z_at_origin(
    a_mm,
    d_mm,
    main_length_mm,
    x_mm,
    x_origin_mm,
):
    return a_mm - WALL_THICKNESS_MM + (d_mm - a_mm) * (
        (x_mm - x_origin_mm + WALL_THICKNESS_MM)
        / (main_length_mm + 2 * WALL_THICKNESS_MM)
    )


def _outer_main_top_z(a_mm, d_mm, main_length_mm, x_mm, x_origin_mm=0.0):
    return a_mm + (d_mm - a_mm) * (
        (x_mm - x_origin_mm) / main_length_mm
    )


def _round_outer_t_throats(
    outer,
    a_mm,
    d_mm,
    main_length_mm,
    main_x_origin_mm,
    root_x_mm,
    c_mm,
):
    shoulder_positions = (
        (
            root_x_mm - c_mm / 2,
            _outer_main_top_z(
                a_mm,
                d_mm,
                main_length_mm,
                root_x_mm - c_mm / 2,
                main_x_origin_mm,
            ),
        ),
        (
            root_x_mm + c_mm / 2,
            _outer_main_top_z(
                a_mm,
                d_mm,
                main_length_mm,
                root_x_mm + c_mm / 2,
                main_x_origin_mm,
            ),
        ),
    )
    shoulders = []
    for edge in outer.Edges:
        vertices = edge.Vertexes
        if len(vertices) != 2:
            continue
        first, second = (vertex.Point for vertex in vertices)
        is_y_edge = (
            abs(first.x - second.x) < 1e-7
            and abs(first.z - second.z) < 1e-7
        )
        is_throat = any(
            abs(first.x - shoulder_x_mm) < 1e-7
            and abs(first.z - shoulder_z_mm) < 1e-7
            for shoulder_x_mm, shoulder_z_mm in shoulder_positions
        )
        if is_y_edge and is_throat:
            shoulders.append(edge)
    if len(shoulders) != 2:
        raise RuntimeError("Could not identify both special-tee outer throat edges.")
    return outer.makeFillet(SHOULDER_RADIUS_MM, shoulders)


def _round_t_throats(
    inner,
    a_mm,
    d_mm,
    main_length_mm,
    main_x_origin_mm,
    root_x_mm,
    c_mm,
):
    shoulder_x_offset_mm = c_mm / 2 - WALL_THICKNESS_MM
    shoulder_positions = (
        (
            root_x_mm - shoulder_x_offset_mm,
            _inner_main_top_z_at_origin(
                a_mm,
                d_mm,
                main_length_mm,
                root_x_mm - shoulder_x_offset_mm,
                main_x_origin_mm,
            ),
        ),
        (
            root_x_mm + shoulder_x_offset_mm,
            _inner_main_top_z_at_origin(
                a_mm,
                d_mm,
                main_length_mm,
                root_x_mm + shoulder_x_offset_mm,
                main_x_origin_mm,
            ),
        ),
    )
    shoulders = []
    for edge in inner.Edges:
        vertices = edge.Vertexes
        if len(vertices) != 2:
            continue
        first, second = (vertex.Point for vertex in vertices)
        is_y_edge = (
            abs(first.x - second.x) < 1e-7
            and abs(first.z - second.z) < 1e-7
        )
        is_throat = any(
            abs(first.x - shoulder_x_mm) < 1e-7
            and abs(first.z - shoulder_z_mm) < 1e-7
            for shoulder_x_mm, shoulder_z_mm in shoulder_positions
        )
        if is_y_edge and is_throat:
            shoulders.append(edge)
    if len(shoulders) != 2:
        raise RuntimeError("Could not identify both special-tee throat edges.")
    return inner.makeFillet(SHOULDER_RADIUS_MM, shoulders)


def derive_talpha_source_dimensions(
    a_mm,
    c_mm,
    d_mm,
    main_length_mm,
    g_mm,
    alpha_deg,
    frame_profile=DEFAULT_GUI_FRAME_PROFILE,
):
    """Derive E and the minimum F for an oblique K2 and actual G."""
    frame_profile = _frame_profile(frame_profile)
    frame_config = _frame_api()["frame_config"](
        profile=frame_profile,
        length=c_mm,
        width=max(a_mm, c_mm, d_mm),
    )
    frame_depth_mm = frame_config["profile_depth"]
    sheet_main_length_mm = main_length_mm - 2 * frame_depth_mm
    if sheet_main_length_mm <= 0:
        raise ValueError("TALPHA main length is too short for both main-port frames.")

    main_x_origin_mm = frame_depth_mm
    right_entry_x_mm = main_length_mm - frame_depth_mm
    frame_return_x_mm = right_entry_x_mm - g_mm
    if not main_x_origin_mm < frame_return_x_mm < right_entry_x_mm:
        raise ValueError("TALPHA G must leave room between the two main-port frames.")

    alpha_rad = math.radians(alpha_deg)
    branch_cos = math.cos(alpha_rad)
    branch_sin = math.sin(alpha_rad)
    main_top_slope = (d_mm - a_mm) / sheet_main_length_mm
    denominator = branch_sin - main_top_slope * branch_cos
    if denominator <= 1e-9:
        raise ValueError(
            "TALPHA alpha and the main-height taper cannot form a source profile."
        )

    target_z_mm = _outer_main_top_z(
        a_mm,
        d_mm,
        sheet_main_length_mm,
        frame_return_x_mm,
        main_x_origin_mm,
    )
    x_term_mm = (
        frame_return_x_mm
        - c_mm * branch_sin
    )
    z_term_mm = (
        target_z_mm
        - a_mm
        + main_top_slope * main_x_origin_mm
        + c_mm * branch_cos
    )
    alignment_length_mm = (
        z_term_mm - main_top_slope * x_term_mm
    ) / denominator
    e_mm = x_term_mm - branch_cos * alignment_length_mm
    if not main_x_origin_mm < e_mm < right_entry_x_mm:
        raise ValueError(
            "TALPHA E derived from L, G, C, and alpha leaves no usable main-port section."
        )
    minimum_return_length_mm = (
        TALPHA_MIN_K2_VERTICAL_CLEARANCE_MM / branch_sin
    )
    f_mm = alignment_length_mm + minimum_return_length_mm
    return {
        "e_mm": e_mm,
        "f_mm": f_mm,
        "alignment_length_mm": alignment_length_mm,
        "minimum_return_length_mm": minimum_return_length_mm,
        "minimum_vertical_clearance_mm": TALPHA_MIN_K2_VERTICAL_CLEARANCE_MM,
        "frame_depth_mm": frame_depth_mm,
        "right_entry_x_mm": right_entry_x_mm,
    }


def _build_talpha_sheet(
    a_mm,
    b_mm,
    c_mm,
    d_mm,
    main_length_mm,
    e_mm,
    f_mm,
    g_mm,
    alpha_deg,
    frame_depth_mm,
    wall_mm,
    frame_profile,
):
    """Build the source-profile Talpha sheet and return its port geometry."""
    sheet_main_length_mm = main_length_mm - 2 * frame_depth_mm
    main_x_origin_mm = frame_depth_mm
    derived_dimensions = derive_talpha_source_dimensions(
        a_mm,
        c_mm,
        d_mm,
        main_length_mm,
        g_mm,
        alpha_deg,
        frame_profile=frame_profile,
    )
    if not math.isclose(
        e_mm,
        derived_dimensions["e_mm"],
        abs_tol=TALPHA_DIMENSION_TOLERANCE_MM,
    ):
        raise ValueError(
            "TALPHA E must satisfy the source L/G/C/alpha closure; use "
            f"{derived_dimensions['e_mm']:.3f} mm for this fixture."
        )
    minimum_f_mm = derived_dimensions["f_mm"]
    if f_mm < minimum_f_mm - TALPHA_DIMENSION_TOLERANCE_MM:
        raise ValueError(
            "TALPHA F must be at least "
            f"{minimum_f_mm:.3f} mm to keep K2 at least "
            f"{TALPHA_MIN_K2_VERTICAL_CLEARANCE_MM:g} mm above G."
        )
    branch_axis_xz = (
        math.cos(math.radians(alpha_deg)),
        math.sin(math.radians(alpha_deg)),
    )
    branch_width_axis_xz = (
        branch_axis_xz[1],
        -branch_axis_xz[0],
    )
    if not main_x_origin_mm < e_mm < main_length_mm - frame_depth_mm:
        raise ValueError("TALPHA E must lie between the two main-port frame entries.")
    right_connection_x_mm = derived_dimensions["right_entry_x_mm"]

    branch_root = (
        e_mm,
        _outer_main_top_z(
            a_mm,
            d_mm,
            sheet_main_length_mm,
            e_mm,
            main_x_origin_mm,
        ),
    )
    port_top = (
        branch_root[0] + branch_axis_xz[0] * f_mm,
        branch_root[1] + branch_axis_xz[1] * f_mm,
    )
    port_bottom = (
        port_top[0] + branch_width_axis_xz[0] * c_mm,
        port_top[1] + branch_width_axis_xz[1] * c_mm,
    )
    frame_mating_top = (
        port_top[0] + branch_axis_xz[0] * frame_depth_mm,
        port_top[1] + branch_axis_xz[1] * frame_depth_mm,
    )
    frame_return = (
        port_bottom[0]
        - branch_axis_xz[0]
        * (f_mm - derived_dimensions["alignment_length_mm"]),
        port_bottom[1]
        - branch_axis_xz[1]
        * (f_mm - derived_dimensions["alignment_length_mm"]),
    )
    right_connection = (
        right_connection_x_mm,
        _outer_main_top_z(
            a_mm,
            d_mm,
            sheet_main_length_mm,
            right_connection_x_mm,
            main_x_origin_mm,
        ),
    )
    if not math.isclose(
        frame_return[1],
        right_connection[1],
        abs_tol=TALPHA_DIMENSION_TOLERANCE_MM,
    ):
        raise ValueError(
            "TALPHA E, F, G, C, alpha, A, D, and L must place the frame return on "
            "the G main-duct line."
        )
    actual_g_mm = right_connection[0] - frame_return[0]
    if actual_g_mm <= 0:
        raise ValueError("TALPHA G leaves no downstream main-duct section.")
    if not math.isclose(
        actual_g_mm,
        g_mm,
        abs_tol=TALPHA_DIMENSION_TOLERANCE_MM,
    ):
        raise ValueError(
            "TALPHA E must satisfy the source L/G/C/alpha closure so G is "
            "the actual downstream straight section."
        )
    k2_return_length_mm = f_mm - derived_dimensions["alignment_length_mm"]
    k2_vertical_clearance_mm = k2_return_length_mm * branch_axis_xz[1]
    k2_horizontal_setback_mm = k2_return_length_mm * branch_axis_xz[0]

    outer = _profile_prism(
        [
            (main_x_origin_mm, 0.0),
            (main_length_mm - frame_depth_mm, 0.0),
            (main_length_mm - frame_depth_mm, d_mm),
            right_connection,
            frame_return,
            port_bottom,
            port_top,
            branch_root,
            (main_x_origin_mm, a_mm),
        ],
        b_mm + 2 * wall_mm,
        -wall_mm,
    )
    inner_main = _main_prism(
        a_mm,
        d_mm,
        sheet_main_length_mm + 2 * wall_mm,
        b_mm,
        0.0,
        wall_mm,
        main_x_origin_mm - wall_mm,
    )
    port_center = (
        (port_top[0] + port_bottom[0]) / 2,
        (port_top[1] + port_bottom[1]) / 2,
    )
    inner_start = (
        port_center[0] + branch_axis_xz[0] * wall_mm,
        port_center[1] + branch_axis_xz[1] * wall_mm,
    )
    inner_end = (
        inner_start[0] - branch_axis_xz[0] * (f_mm + 2 * wall_mm),
        inner_start[1] - branch_axis_xz[1] * (f_mm + 2 * wall_mm),
    )
    inner_half_width_mm = c_mm / 2 - wall_mm
    inner_branch = _profile_prism(
        [
            (
                inner_start[0] - branch_width_axis_xz[0] * inner_half_width_mm,
                inner_start[1] - branch_width_axis_xz[1] * inner_half_width_mm,
            ),
            (
                inner_start[0] + branch_width_axis_xz[0] * inner_half_width_mm,
                inner_start[1] + branch_width_axis_xz[1] * inner_half_width_mm,
            ),
            (
                inner_end[0] + branch_width_axis_xz[0] * inner_half_width_mm,
                inner_end[1] + branch_width_axis_xz[1] * inner_half_width_mm,
            ),
            (
                inner_end[0] - branch_width_axis_xz[0] * inner_half_width_mm,
                inner_end[1] - branch_width_axis_xz[1] * inner_half_width_mm,
            ),
        ],
        b_mm,
        0.0,
    )
    fitting = outer.cut(inner_main.fuse(inner_branch).removeSplitter()).removeSplitter()
    if not fitting.isValid() or len(fitting.Solids) != 1:
        raise RuntimeError("TALPHA source-profile geometry must produce one valid solid.")
    return fitting, {
        "branch_axis_xz": branch_axis_xz,
        "branch_root": branch_root,
        "frame_return": frame_return,
        "port_top": port_top,
        "frame_mating_top": frame_mating_top,
        "sheet_main_length_mm": sheet_main_length_mm,
        "actual_g_mm": actual_g_mm,
        "k2_return_length_mm": k2_return_length_mm,
        "k2_vertical_clearance_mm": k2_vertical_clearance_mm,
        "k2_horizontal_setback_mm": k2_horizontal_setback_mm,
    }


def build_tee_special(
    variant,
    a_mm,
    b_mm,
    c_mm,
    d_mm,
    main_length_mm,
    branch_length_mm,
    alpha_deg,
    frame_profile=DEFAULT_GUI_FRAME_PROFILE,
    e_mm=DEFAULT_GUI_TALPHA_E_MM,
    g_mm=DEFAULT_GUI_TALPHA_G_MM,
):
    """Return sheet plus physical frame parts for a special-tee review assembly."""
    variant = _variant(variant)
    frame_profile = _frame_profile(frame_profile)
    _validate_dimensions(
        variant,
        a_mm,
        b_mm,
        c_mm,
        d_mm,
        main_length_mm,
        branch_length_mm,
        alpha_deg,
        frame_profile,
    )

    wall_mm = WALL_THICKNESS_MM
    frame_config = _frame_api()["frame_config"](
        profile=frame_profile,
        length=b_mm,
        width=max(a_mm, c_mm, d_mm),
    )
    frame_depth_mm = frame_config["profile_depth"]
    sheet_main_length_mm = main_length_mm - 2 * frame_depth_mm
    if sheet_main_length_mm <= 2 * wall_mm:
        raise ValueError("Main length is too short for frames at both main ports.")

    if variant == "TALPHA":
        fitting, talpha = _build_talpha_sheet(
            a_mm,
            b_mm,
            c_mm,
            d_mm,
            main_length_mm,
            e_mm,
            branch_length_mm,
            g_mm,
            alpha_deg,
            frame_depth_mm,
            wall_mm,
            frame_profile,
        )
        root_x_mm, root_z_mm = talpha["branch_root"]
        branch_axis_xz = talpha["branch_axis_xz"]
        sheet_branch_length_mm = branch_length_mm
    else:
        sheet_branch_length_mm = branch_length_mm - frame_depth_mm
        if sheet_branch_length_mm <= 2 * wall_mm:
            raise ValueError("Branch length is too short for its connection frame.")

        root_x_mm = main_length_mm / 2
        branch_x_min_mm = root_x_mm - c_mm / 2
        branch_x_max_mm = root_x_mm + c_mm / 2
        root_z_mm = min(
            _inner_main_top_z_at_origin(
                a_mm,
                d_mm,
                sheet_main_length_mm,
                branch_x_min_mm,
                frame_depth_mm,
            ),
            _inner_main_top_z_at_origin(
                a_mm,
                d_mm,
                sheet_main_length_mm,
                branch_x_max_mm,
                frame_depth_mm,
            ),
        ) + wall_mm
        outer_main = _main_prism(
            a_mm,
            d_mm,
            sheet_main_length_mm,
            b_mm + 2 * wall_mm,
            -wall_mm,
            0,
            frame_depth_mm,
        )
        inner_main = _main_prism(
            a_mm,
            d_mm,
            sheet_main_length_mm + 2 * wall_mm,
            b_mm,
            0,
            wall_mm,
            frame_depth_mm - wall_mm,
        )
        outer_branch = Part.makeBox(
            c_mm,
            b_mm + 2 * wall_mm,
            sheet_branch_length_mm + wall_mm,
            App.Vector(root_x_mm - c_mm / 2, -wall_mm, root_z_mm - wall_mm),
        )
        inner_branch = Part.makeBox(
            c_mm - 2 * wall_mm,
            b_mm,
            sheet_branch_length_mm + 2 * wall_mm,
            App.Vector(root_x_mm - (c_mm - 2 * wall_mm) / 2, 0, root_z_mm - wall_mm),
        )
        branch_axis_xz = (0.0, 1.0)

        outer = outer_main.fuse(outer_branch).removeSplitter()
        inner = inner_main.fuse(inner_branch).removeSplitter()
        outer = _round_outer_t_throats(
            outer,
            a_mm,
            d_mm,
            sheet_main_length_mm,
            frame_depth_mm,
            root_x_mm,
            c_mm,
        )
        inner = _round_t_throats(
            inner,
            a_mm,
            d_mm,
            sheet_main_length_mm,
            frame_depth_mm,
            root_x_mm,
            c_mm,
        )
        fitting = outer.cut(inner).removeSplitter()
        if not fitting.isValid() or len(fitting.Solids) != 1:
            raise RuntimeError("Special tee review geometry must produce one valid solid.")

    frames = []
    left_frame, _ = _build_port_frame(
        "K1",
        frame_profile,
        b_mm,
        a_mm,
        (0.0, 0.0, 0.0),
        (0.0, 1.0, 0.0),
        (0.0, 0.0, 1.0),
        (1.0, 0.0, 0.0),
    )
    frames.extend(left_frame)
    right_frame, _ = _build_port_frame(
        "K3",
        frame_profile,
        b_mm,
        d_mm,
        (main_length_mm, b_mm, 0.0),
        (0.0, -1.0, 0.0),
        (0.0, 0.0, 1.0),
        (-1.0, 0.0, 0.0),
    )
    frames.extend(right_frame)
    if variant == "TALPHA":
        branch_outward_axis = (
            branch_axis_xz[0],
            0.0,
            branch_axis_xz[1],
        )
        branch_width_axis = (
            branch_axis_xz[1],
            0.0,
            -branch_axis_xz[0],
        )
        branch_origin = (
            talpha["frame_mating_top"][0],
            b_mm,
            talpha["frame_mating_top"][1],
        )
        branch_frame, _ = _build_port_frame(
            "K2",
            frame_profile,
            c_mm,
            b_mm,
            branch_origin,
            branch_width_axis,
            (0.0, -1.0, 0.0),
            tuple(-component for component in branch_outward_axis),
        )
    else:
        branch_frame, _ = _build_port_frame(
            "K2",
            frame_profile,
            c_mm,
            b_mm,
            (branch_x_min_mm, b_mm, root_z_mm + branch_length_mm),
            (1.0, 0.0, 0.0),
            (0.0, -1.0, 0.0),
            (0.0, 0.0, -1.0),
        )
    frames.extend(branch_frame)
    if len(frames) != 24:
        raise RuntimeError(f"Expected 24 frame components, received {len(frames)}.")

    dimensions = {
        "a_mm": a_mm,
        "b_mm": b_mm,
        "c_mm": c_mm,
        "d_mm": d_mm,
        "main_length_mm": main_length_mm,
        "branch_length_mm": branch_length_mm,
        "alpha_deg": alpha_deg if variant == "TALPHA" else None,
        "e_mm": e_mm if variant == "TALPHA" else None,
        "f_mm": branch_length_mm if variant == "TALPHA" else None,
        "g_mm": g_mm if variant == "TALPHA" else None,
        "actual_g_mm": talpha["actual_g_mm"] if variant == "TALPHA" else None,
        "k2_return_length_mm": (
            talpha["k2_return_length_mm"] if variant == "TALPHA" else None
        ),
        "k2_vertical_clearance_mm": (
            talpha["k2_vertical_clearance_mm"] if variant == "TALPHA" else None
        ),
        "k2_horizontal_setback_mm": (
            talpha["k2_horizontal_setback_mm"] if variant == "TALPHA" else None
        ),
        "branch_root_x_mm": root_x_mm,
        "branch_root_z_mm": root_z_mm,
        "branch_axis_x": branch_axis_xz[0],
        "branch_axis_z": branch_axis_xz[1],
        "shoulder_radius_mm": SHOULDER_RADIUS_MM if variant in {"T", "TASYMM"} else None,
        "wall_thickness_mm": wall_mm,
        "frame_profile": frame_profile,
        "frame_depth_mm": frame_depth_mm,
        "sheet_main_length_mm": sheet_main_length_mm,
        "sheet_branch_length_mm": sheet_branch_length_mm,
        "frame_component_count": len(frames),
    }
    return fitting, frames, dimensions


def _dimension_label(value):
    if float(value).is_integer():
        return str(int(value))
    return f"{value:g}".replace(".", "_")


def _add_length_property(feature, name, value, description):
    feature.addProperty("App::PropertyLength", name, "Dimensions", description)
    setattr(feature, name, value)


def write_review(
    out_dir,
    variant,
    a_mm,
    b_mm,
    c_mm,
    d_mm,
    main_length_mm,
    branch_length_mm,
    alpha_deg,
    frame_profile=DEFAULT_GUI_FRAME_PROFILE,
    e_mm=DEFAULT_GUI_TALPHA_E_MM,
    g_mm=DEFAULT_GUI_TALPHA_G_MM,
    keep_document_open=False,
):
    out_dir.mkdir(parents=True, exist_ok=True)
    variant = _variant(variant)
    fitting, frame_parts, dimensions = build_tee_special(
        variant,
        a_mm,
        b_mm,
        c_mm,
        d_mm,
        main_length_mm,
        branch_length_mm,
        alpha_deg,
        frame_profile,
        e_mm,
        g_mm,
    )
    model_name = (
        f"TEE_SPECIAL_{variant}_{_dimension_label(a_mm)}x{_dimension_label(b_mm)}"
        f"_{_dimension_label(c_mm)}_{_dimension_label(d_mm)}_review"
    )
    document = App.newDocument(model_name)
    try:
        feature = document.addObject("Part::Feature", "TEE_SPECIAL_Sheet")
        feature.Label = f"Special tee {variant} sheet review"
        feature.Shape = fitting
        feature.addProperty("App::PropertyString", "ReviewScope", "Review")
        feature.ReviewScope = (
            "Source-profile candidate only. It is not the production TEE_RECT generator."
        )
        for name, value in dimensions.items():
            if value is not None and name.endswith("_mm"):
                _add_length_property(feature, name.title().replace("_", ""), value, name)
        feature.addProperty("App::PropertyString", "BranchAxis", "Review")
        feature.BranchAxis = f"X={dimensions['branch_axis_x']:.6g}, Z={dimensions['branch_axis_z']:.6g}"
        feature.addProperty("App::PropertyString", "CatalogueStatus", "Review")
        feature.CatalogueStatus = (
            "T/Talpha special-family dimensions and product mapping are not released."
        )
        feature.addProperty("App::PropertyString", "FrameProfile", "Review")
        feature.FrameProfile = dimensions["frame_profile"]
        if feature.ViewObject is not None:
            feature.ViewObject.ShapeColor = (0.35, 0.65, 1.0)
            feature.ViewObject.LineColor = (0.05, 0.15, 0.45)

        frame_group = document.addObject("App::Part", "Connection_Frames")
        frame_group.Label = (
            f"{dimensions['frame_profile']} connection frames ({len(frame_parts)} components)"
        )
        frame_features = []
        for index, frame_part in enumerate(frame_parts, start=1):
            frame_feature = document.addObject(
                "Part::Feature",
                f"Frame_{index:02d}",
            )
            frame_feature.Label = frame_part["name"]
            frame_feature.Shape = frame_part["shape"]
            frame_feature.addProperty("App::PropertyString", "FrameCode", "Review")
            frame_feature.FrameCode = frame_part["code"]
            frame_feature.addProperty("App::PropertyString", "FrameRole", "Review")
            frame_feature.FrameRole = frame_part["role"]
            if frame_feature.ViewObject is not None:
                frame_feature.ViewObject.ShapeColor = (0.62, 0.78, 1.0)
                frame_feature.ViewObject.LineColor = (0.05, 0.15, 0.45)
            frame_group.addObject(frame_feature)
            frame_features.append(frame_feature)

        document.recompute()
        if not feature.Shape.isValid() or len(feature.Shape.Solids) != 1:
            raise RuntimeError("Saved special tee review fitting is not one valid solid.")
        if len(frame_features) != 24 or any(
            not frame_feature.Shape.isValid()
            or len(frame_feature.Shape.Solids) != 1
            for frame_feature in frame_features
        ):
            raise RuntimeError("Saved special tee review frames are not 24 valid solids.")

        fcstd_path = out_dir / f"{model_name}.FCStd"
        step_path = out_dir / f"{model_name}.step"
        metadata_path = out_dir / f"{model_name}.json"
        document.saveAs(str(fcstd_path))
        Part.export([feature, *frame_features], str(step_path))
        metadata_path.write_text(
            json.dumps(
                {
                    "schema": "tee-special-review-v1",
                    "variant": variant,
                    "dimensions_mm": dimensions,
                    "assumptions": [
                        "All three source ports share depth B.",
                        "The review wall thickness is 1 mm.",
                        "T uses equal A and D port heights.",
                        "TASYMM permits unequal A and D port heights.",
                        "TALPHA follows the source E/F/C/G profile with an upward-right branch.",
                        "Every port has an explicit eight-component Airkan frame.",
                    ],
                    "outputs": {
                        "fcstd": fcstd_path.name,
                        "step": step_path.name,
                    },
                    "frame_components": [
                        {
                            "code": frame_part["code"],
                            "name": frame_part["name"],
                            "role": frame_part["role"],
                        }
                        for frame_part in frame_parts
                    ],
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
            "frame_count": len(frame_features),
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


def run_gui_review(
    out_dir,
    variant,
    a_mm,
    b_mm,
    c_mm,
    d_mm,
    main_length_mm,
    branch_length_mm,
    alpha_deg,
    frame_profile=DEFAULT_GUI_FRAME_PROFILE,
    e_mm=DEFAULT_GUI_TALPHA_E_MM,
    g_mm=DEFAULT_GUI_TALPHA_G_MM,
):
    """Build a dialog-free tiled FreeCAD review."""
    if not App.GuiUp:
        raise RuntimeError("The tiled review requires a FreeCAD GUI session.")

    import FreeCADGui as Gui

    result = write_review(
        out_dir,
        variant,
        a_mm,
        b_mm,
        c_mm,
        d_mm,
        main_length_mm,
        branch_length_mm,
        alpha_deg,
        frame_profile,
        e_mm,
        g_mm,
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
        default_out_dir = Path.home() / "Documents" / "ductbuild-tee-special-review"
        result = run_gui_review(
            default_out_dir,
            DEFAULT_GUI_VARIANT,
            DEFAULT_GUI_A_MM,
            DEFAULT_GUI_B_MM,
            DEFAULT_GUI_C_MM,
            DEFAULT_GUI_D_MM,
            DEFAULT_GUI_MAIN_LENGTH_MM,
            DEFAULT_GUI_BRANCH_LENGTH_MM,
            DEFAULT_GUI_ALPHA_DEG,
            DEFAULT_GUI_FRAME_PROFILE,
            DEFAULT_GUI_TALPHA_E_MM,
            DEFAULT_GUI_TALPHA_G_MM,
        )
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0

    parser = argparse.ArgumentParser(
        description="Create a standalone special rectangular T/Talpha review model."
    )
    parser.add_argument("--out", required=True, type=Path, help="Output folder for FCStd, STEP, and review JSON.")
    parser.add_argument("--variant", required=True, help="T, TASYMM, or TALPHA.")
    parser.add_argument("--a-mm", required=True, type=_positive_number, help="Left-port A size in millimetres.")
    parser.add_argument("--b-mm", required=True, type=_positive_number, help="Shared port depth B in millimetres.")
    parser.add_argument("--c-mm", required=True, type=_positive_number, help="Branch-port C size in millimetres.")
    parser.add_argument("--d-mm", required=True, type=_positive_number, help="Right-port D size in millimetres.")
    parser.add_argument("--main-length-mm", required=True, type=_positive_number, help="Overall main length L in millimetres.")
    parser.add_argument(
        "--branch-length-mm",
        type=_positive_number,
        help="Branch length in millimetres; TALPHA F is source-derived when omitted.",
    )
    parser.add_argument("--alpha-deg", type=_positive_number, default=DEFAULT_GUI_ALPHA_DEG, help="TALPHA branch angle in degrees.")
    parser.add_argument(
        "--frame-profile",
        default=DEFAULT_GUI_FRAME_PROFILE,
        help="E20, E30, A20, A30, or A40 connection frame profile.",
    )
    parser.add_argument(
        "--e-mm",
        type=_positive_number,
        help="TALPHA source E main-duct section; source-derived when omitted.",
    )
    parser.add_argument(
        "--g-mm",
        type=_positive_number,
        default=DEFAULT_GUI_TALPHA_G_MM,
        help="TALPHA source G main-duct section in millimetres.",
    )
    arguments = parser.parse_args(argv)
    try:
        variant = _variant(arguments.variant)
        branch_length_mm = arguments.branch_length_mm
        e_mm = arguments.e_mm
        if variant == "TALPHA":
            source_dimensions = derive_talpha_source_dimensions(
                arguments.a_mm,
                arguments.c_mm,
                arguments.d_mm,
                arguments.main_length_mm,
                arguments.g_mm,
                arguments.alpha_deg,
                arguments.frame_profile,
            )
            if branch_length_mm is None:
                branch_length_mm = source_dimensions["f_mm"]
            if e_mm is None:
                e_mm = source_dimensions["e_mm"]
        else:
            if branch_length_mm is None:
                branch_length_mm = DEFAULT_GUI_BRANCH_LENGTH_MM
            if e_mm is None:
                e_mm = DEFAULT_GUI_TALPHA_E_MM
        _validate_dimensions(
            variant,
            arguments.a_mm,
            arguments.b_mm,
            arguments.c_mm,
            arguments.d_mm,
            arguments.main_length_mm,
            branch_length_mm,
            arguments.alpha_deg,
            arguments.frame_profile,
        )
    except ValueError as error:
        parser.error(str(error))
    result = write_review(
        arguments.out.expanduser().resolve(),
        variant,
        arguments.a_mm,
        arguments.b_mm,
        arguments.c_mm,
        arguments.d_mm,
        arguments.main_length_mm,
        branch_length_mm,
        arguments.alpha_deg,
        arguments.frame_profile,
        e_mm,
        arguments.g_mm,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
