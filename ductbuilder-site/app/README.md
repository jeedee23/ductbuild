# Application source

This directory is the canonical source tree for the standalone **AAVDS-duct-builder** application.

The `Allshield_*` module names and `allshield-*` JSON schemas are retained temporarily for backward compatibility with existing project files and installer launchers. Renaming them is a separate migration and must include compatibility tests.

## Layout

- `Allshield_Project_GUI.py`: standalone Tkinter application entry point.
- `Allshield_FreeCAD_Worker.py`: isolated FreeCAD geometry worker.
- `allshield_project.py`: persistent project register and connection model.
- `airkan_builder/`: geometry, catalogue rules and pricing implementation.
- `assets/type_previews/`: canonical selector preview manifest and supplier-reference PNG files. Every dropdown family has one PNG preview; hovering a selector preview enlarges it, and the fixed **Drawing library** window shows all families without rebuilding drawings. CM, BUY, and COMPOSITE use clearly labelled neutral reference PNGs until a component-specific drawing is supplied.
- `vendor/makeframe_v2.FCMacro`: required frame geometry implementation.
- `tests/`: pure-Python and native FreeCAD regression tests.

## Local validation

```powershell
py -3.14 -m unittest discover -s app/tests -p "test_*.py" -v
py -3.14 app/Allshield_Project_GUI.py --project installer/work/gui-smoke --smoke-test
```

The preview manifest contains all supported families. PNG coverage is intentionally incremental; a missing PNG falls back to the application's text placeholder.
