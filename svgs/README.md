# AIRKAN SVG review carousel

## Start

From the repository root:

```powershell
python .\svgs\review_server.py
```

Then open <http://127.0.0.1:8765/> if the browser does not open
automatically.

## Review

- Use the left and right buttons or arrow keys to move through drawings.
- Compare the original PNG on the left with the redrawn SVG on the right.
- Choose **Approve**, **Request changes**, or **Reset to pending**.
- Add an optional remark.
- When the local review server is running, changes are saved directly to
  `reviews.json`.
- **Download JSON** creates a portable copy.
- **Import JSON** merges an existing review file.
- Search and status filters help revisit pending or rejected drawings.

The browser also keeps unsaved changes in local storage as a safety net.

## Refresh the catalog

After adding or removing SVG files:

```powershell
python .\svgs\build_catalog.py
```

The four Copilot logo/icon SVGs are intentionally excluded from the drawing
catalog. PNGs are matched by filename from the repository-level
`pngs/originals` folder; drawings without an exact match display a
missing-reference message. Other PNGs in `pngs` remain untouched.
