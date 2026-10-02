"""Render headless FreeCAD STEP geometry to repeatable PNG review views.

FreeCADCmd has no active GUI viewport in the installed runtime, so it cannot
reliably use ``activeView().saveImage()``. This tool imports the exported STEP,
tessellates the actual FreeCAD BRep, and rasterizes the tessellation with Qt.

Example:
    "C:\Program Files\FreeCAD 1.1\bin\python.exe" ^
        app\tools\render_freecad_step_views.py ^
        --step C:\temp\PSA_Fusion_200_100_A_review.step ^
        --out C:\temp\PSA_Fusion_200_100_A_views
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import FreeCAD as App
import Part
from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPolygonF


IMAGE_SIZE_PX = 900
PADDING_PX = 48
TESSELLATION_DEFLECTION_MM = 0.5
VIEW_DIRECTIONS = {
    "isometric": App.Vector(1, -1, 1),
    "front": App.Vector(-1, 0, 0),
    "side": App.Vector(0, -1, 0),
}


def _normalized(vector):
    length = vector.Length
    if length == 0:
        raise ValueError("A camera vector cannot have zero length.")
    return vector / length


def _projector(direction):
    """Return a screen basis and depth direction for one orthographic camera."""
    forward = _normalized(direction)
    world_up = App.Vector(0, 0, 1)
    right = _normalized(world_up.cross(forward))
    up = _normalized(forward.cross(right))
    return right, up, forward


def _triangle_normal(a, b, c):
    normal = (b - a).cross(c - a)
    if normal.Length == 0:
        return App.Vector()
    return normal / normal.Length


def _shade(normal, light_direction):
    if normal.Length == 0:
        return QColor(125, 135, 145)
    brightness = 0.42 + 0.48 * abs(normal.dot(light_direction))
    return QColor(
        round(75 * brightness),
        round(115 * brightness),
        round(145 * brightness),
    )


def _project_points(points, right, up, forward):
    return [
        (
            point.dot(right),
            point.dot(up),
            point.dot(forward),
        )
        for point in points
    ]


def _screen_transform(projected_points):
    horizontal = [point[0] for point in projected_points]
    vertical = [point[1] for point in projected_points]
    min_x, max_x = min(horizontal), max(horizontal)
    min_y, max_y = min(vertical), max(vertical)
    span = max(max_x - min_x, max_y - min_y)
    if span == 0:
        raise RuntimeError("Cannot render a zero-size FreeCAD shape.")
    scale = (IMAGE_SIZE_PX - 2 * PADDING_PX) / span

    def to_screen(point):
        x = PADDING_PX + (point[0] - min_x) * scale
        y = IMAGE_SIZE_PX - PADDING_PX - (point[1] - min_y) * scale
        return QPointF(x, y)

    return to_screen


def render_shape(shape, output_path, view_name):
    """Tessellate and rasterize one FreeCAD shape as a PNG review view."""
    points, triangles = shape.tessellate(TESSELLATION_DEFLECTION_MM)
    if not points or not triangles:
        raise RuntimeError("The imported STEP contains no tessellatable geometry.")

    right, up, forward = _projector(VIEW_DIRECTIONS[view_name])
    projected_points = _project_points(points, right, up, forward)
    to_screen = _screen_transform(projected_points)
    light_direction = _normalized(forward + App.Vector(-1, 1, 2))

    triangles_with_depth = []
    for indices in triangles:
        a_index, b_index, c_index = indices
        a, b, c = points[a_index], points[b_index], points[c_index]
        depth = (
            projected_points[a_index][2]
            + projected_points[b_index][2]
            + projected_points[c_index][2]
        ) / 3
        triangles_with_depth.append((depth, indices, _triangle_normal(a, b, c)))
    triangles_with_depth.sort(key=lambda item: item[0])

    image = QImage(IMAGE_SIZE_PX, IMAGE_SIZE_PX, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.white)
    painter = QPainter(image)
    try:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(Qt.PenStyle.NoPen)
        for _, indices, normal in triangles_with_depth:
            polygon = QPolygonF([to_screen(projected_points[index]) for index in indices])
            painter.setBrush(_shade(normal, light_direction))
            painter.drawPolygon(polygon)
    finally:
        painter.end()

    if not image.save(str(output_path), "PNG"):
        raise OSError(f"Could not write PNG view: {output_path}")
    return {
        "path": str(output_path),
        "triangle_count": len(triangles),
        "view": view_name,
    }


def _import_step_shape(step_path):
    document = App.newDocument("Headless_STEP_Render")
    try:
        Part.insert(str(step_path), document.Name)
        document.recompute()
        shapes = [
            object_.Shape
            for object_ in document.Objects
            if hasattr(object_, "Shape") and not object_.Shape.isNull()
        ]
        if not shapes:
            raise RuntimeError(f"STEP import produced no visible shapes: {step_path}")
        return shapes[0] if len(shapes) == 1 else Part.makeCompound(shapes)
    finally:
        App.closeDocument(document.Name)


def render_step_views(step_path, out_dir):
    """Import one STEP file and write isometric, front, and side PNGs."""
    if not step_path.is_file():
        raise FileNotFoundError(f"STEP file does not exist: {step_path}")
    out_dir.mkdir(parents=True, exist_ok=True)
    shape = _import_step_shape(step_path)
    if not shape.isValid():
        raise RuntimeError(f"STEP import is invalid: {step_path}")

    result = {
        "step": str(step_path),
        "solid_count": len(shape.Solids),
        "views": [],
    }
    for view_name in VIEW_DIRECTIONS:
        output_path = out_dir / f"{step_path.stem}_{view_name}.png"
        result["views"].append(render_shape(shape, output_path, view_name))
    metadata_path = out_dir / f"{step_path.stem}_render.json"
    metadata_path.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    result["metadata"] = str(metadata_path)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Render imported FreeCAD STEP geometry as headless PNG review views."
    )
    parser.add_argument("--step", required=True, type=Path, help="STEP file to import and render.")
    parser.add_argument("--out", required=True, type=Path, help="Directory for rendered PNG views.")
    arguments = parser.parse_args(argv)
    result = render_step_views(arguments.step.expanduser().resolve(), arguments.out.expanduser().resolve())
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
