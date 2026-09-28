# AIRKAN catalogue technical drawing extraction - VS Code / GitHub Copilot handoff

## Goal

Build a reliable local pipeline that processes the full AIRKAN catalogue and extracts **technical drawings only** from the catalogue, redraws them as clean editable **SVG** files, and produces matching high-resolution **PNG** exports.

The large source PDF is already local:

```text
D:\github\ductbuild\shared\sources\pdf\airkan\airkan cataloog.pdf
```

The catalogue has about **211 pages** and contains roughly **100 technical drawings**, but the number must be discovered rather than assumed.

This is **not** a simple fixed crop job. The drawings appear in different positions and layouts throughout the catalogue. Some pages have one drawing, some have several, some have photos, some have only tables, and some mix multiple product types.

---

## Core rules

1. **Extract/redraw drawings only.**
   - Technical line drawings: YES.
   - Product photographs: NO.
   - AIRKAN logos, page decorations, tables, price grids, page headers/footers: NO.

2. **Use the official AIRKAN code/name shown on the page for the filename.**
   Examples already identified:

```text
PSA - Ø1 - Ø2
APA - Ø1 - Ø2
T1 - Ø1 - Ø2 - Ø3
VSFX - Ø1 - Ø2
KRSX - Ø
```

3. **Do not guess technical values.**
   - Every dimension number, diameter symbol, annotation, dimension line, leader and label must be checked against the source.
   - If a number cannot be read confidently, do not invent it.

4. **Uncertain values must be numbered.**
   Use:

```text
Q1
Q2
Q3
...
```

   Numbering restarts at `Q1` for each drawing.

   Example review feedback from Johan:

```text
KRSX: Q1 = 50, Q2 = 50
```

5. **Final SVG must contain only the clean redraw.**
   A source/background layer may be used temporarily during tracing and comparison, but it must be removed from the final SVG.

6. **SVG is the master format.**
   PNG is exported from the final SVG after validation.

---

## Important example: KRSX

A previous test used the AIRKAN page for:

```text
Kappen KX - KTX - KSLX - KRSX
```

with separate drawings on the same page:

```text
KX - Ø
KTX - Ø
KSLX - Ø
KRSX - Ø
```

This is a good test page because it requires:

- identifying several drawings on one page;
- assigning the correct code to each drawing;
- separating each drawing from the price table;
- preserving dimensions and callouts;
- rejecting uncertainty rather than guessing.

For the KRSX test, previously uncertain small vertical dimensions were confirmed by Johan as:

```text
50
```

So when recreating KRSX, use `50` for those confirmed dimensions.

---

# Recommended local folder structure

Use the existing AIRKAN source area and add working/output folders alongside it:

```text
D:\github\ductbuild\shared\sources\pdf\airkan\
    airkan cataloog.pdf
    work\
        pages\
        crops\
        overlays\
        diagnostics\
    svgs\
    pngs\
    review\
        airkan_questions.pdf
        airkan_index.csv
        airkan_questions.csv
```

Do not overwrite the original PDF.

---

# Required pipeline

## Stage 1 - inspect the full catalogue

Programmatically render and inspect the entire PDF.

Recommended Python libraries:

- `PyMuPDF` / `fitz` for PDF reading, text positions and rendering;
- `pdfplumber` optionally for layout/text coordinates;
- `Pillow` / OpenCV for image analysis;
- `cairosvg` or Inkscape CLI for SVG -> PNG;
- `reportlab` or PyMuPDF for the final review PDF.

Render pages at a useful inspection resolution, e.g. 200-300 dpi first.

For final tracing/reference, render only relevant areas/pages at 600 dpi or higher.

Do **not** blindly render all 211 pages at 600 dpi if it is unnecessary.

---

## Stage 2 - identify candidate technical drawings

The pipeline must determine which pages contain technical line drawings.

Useful signals:

- strong black/grey line art;
- dimension lines and extension lines;
- diameter symbols `Ø`;
- short technical labels;
- low photographic texture;
- drawing area usually adjacent to a product code/name;
- tables have repeated grids and should be excluded;
- photos have continuous-tone image content and must be ignored.

This can be semi-automatic. Accuracy is more important than full automation.

Create an index such as:

```csv
pdf_page,catalogue_page,title,code,drawing_index,status,questions
42,42,Asymmetrische aftakkingen PSA,"PSA - Ø1 - Ø2",1,detected,
44,44,Asymmetrische aftakkingen APA,"APA - Ø1 - Ø2",1,detected,
50,50,Symmetrische T-stukken T1,"T1 - Ø1 - Ø2 - Ø3",1,detected,
132,132,Kappen,"KX - Ø",1,detected,
132,132,Kappen,"KTX - Ø",2,detected,
132,132,Kappen,"KSLX - Ø",3,detected,
132,132,Kappen,"KRSX - Ø",4,detected,
```

The exact page numbers above are examples from prior inspection and can be used for initial testing.

---

## Stage 3 - crop the source drawing precisely

For each drawing:

- crop only the technical figure and its directly related dimensioning/annotations;
- do not include price tables or unrelated page text;
- include dimension lines and leaders when they belong to the drawing;
- keep enough whitespace around the drawing to avoid clipping arrowheads/text.

For pages with multiple drawings, create one crop per drawing.

---

## Stage 4 - redraw as SVG

The final drawing should be reconstructed as real SVG geometry where feasible:

- `<line>`
- `<polyline>`
- `<path>`
- `<circle>` / `<ellipse>`
- `<text>`
- `<marker>` for arrowheads
- dashed strokes for hidden lines / centerlines

Avoid embedding the source raster in the final file.

During construction, a temporary SVG may contain groups like:

```xml
<g id="SOURCE">...</g>
<g id="REDRAW">...</g>
<g id="CHECK">...</g>
```

But before final export:

- remove `SOURCE` completely;
- retain only the clean redraw;
- if questions remain, keep question labels clearly visible in a dedicated question/check group until Johan provides the values.

---

## Stage 5 - text and dimension handling

Every visible technical text item must be classified into one of these categories:

### A. Certain
Write it normally.

Example:

```text
1,67Ø
1,28Ø
H = 2Ø
Afwatering
Égouttage
Draining
```

### B. Uncertain numeric or symbolic value
Replace the unreadable value with a numbered question label:

```text
Q1
Q2
Q3
```

The associated dimension geometry must remain visible so Johan can identify what the question refers to.

### C. Nonessential / unrelated page text
Do not include it in the drawing.

Never let OCR silently invent values.

---

# Question workflow

This is important because some catalogue source images are low resolution.

For every drawing with uncertain values:

1. assign local question IDs starting at `Q1`;
2. render the SVG with question labels visible;
3. add it to a combined Acrobat-friendly review PDF;
4. log each question in `airkan_questions.csv`.

Suggested CSV:

```csv
code,pdf_page,question_id,description,current_guess,confirmed_value,status
KRSX - Ø,132,Q1,upper small vertical dimension,,50,confirmed
KRSX - Ø,132,Q2,lower small vertical dimension,,50,confirmed
```

For unconfirmed values leave `confirmed_value` blank.

Johan will load the SVGs/pages into one Acrobat PDF and return answers such as:

```text
KRSX Q1 = 50
KRSX Q2 = 50
VR Q1 = 35
A31X Q1 = 1670
```

Then rerun a patch/finalization step to substitute the real values and regenerate SVG + PNG.

---

# Validation / overlay comparison

For each redraw, automatically create a temporary overlay comparison.

Recommended approach:

1. render the source crop to PNG;
2. render the redraw SVG to transparent PNG;
3. align them to the same canvas;
4. generate:
   - source only;
   - redraw only;
   - overlay at 50% alpha;
   - optional absolute-difference image.

The purpose is to verify:

- no geometry is missing;
- no dimension line disappeared;
- arrowheads are present;
- labels are attached to the correct features;
- the redraw follows the original proportions closely;
- no table lines or unrelated page content were accidentally traced.

Store temporary comparisons in:

```text
work\overlays\
```

Do not ship these as final deliverables unless useful for QA.

---

# Final outputs

For each approved drawing create:

```text
svgs\<official AIRKAN code/name>.svg
pngs\<official AIRKAN code/name>.png
```

PNG target:

- transparent or white background depending on downstream usage;
- high resolution, ideally equivalent to 600 dpi for the intended print size;
- generated from SVG, not by merely enlarging the original source raster.

Filenames should preserve useful technical notation when Windows/filesystem allows it, e.g.:

```text
PSA - Ø1 - Ø2.svg
PSA - Ø1 - Ø2.png
KRSX - Ø.svg
KRSX - Ø.png
```

If any character becomes problematic for tooling, use a reversible sanitized filename but keep the official title/code inside metadata/index.

---

# Suggested metadata/index file

Create `airkan_index.csv` with at least:

```csv
pdf_page,catalogue_page,chapter,title,code,source_bbox,svg_file,png_file,question_count,status
```

Status values could be:

```text
detected
traced
needs_review
confirmed
final
skipped_photo
skipped_no_drawing
```

---

# Acceptance criteria

A drawing is considered final only if all of the following are true:

- correct AIRKAN drawing selected;
- correct product code/name used;
- no photo included;
- no table/grid contamination;
- all visible geometry reproduced;
- all dimension/leader lines reproduced;
- all readable numbers/text reproduced correctly;
- no guessed values;
- uncertainties represented by numbered `Qx` labels until confirmed;
- source/background raster removed from final SVG;
- final SVG opens cleanly in Illustrator/browser;
- final PNG is generated from SVG and is crisp;
- overlay comparison was visually checked;
- index CSV updated.

---

# Recommended first implementation milestone

Do **not** process all 211 pages immediately.

First implement and validate the pipeline on a mixed test set:

1. a simple one-drawing page: `PSA - Ø1 - Ø2`;
2. a page with multiple drawings: the KX/KTX/KSLX/KRSX page;
3. a technical drawing with more complicated geometry and multiple dimensions;
4. a photo-heavy page that must produce **no drawing output**;
5. a table-only page that must produce **no drawing output**.

Only after these five cases are correct should the catalogue-wide batch run begin.

---

# Important behavioural instruction for Copilot/agent

When uncertain, stop that specific value/drawing and flag it for review instead of making a plausible assumption.

The goal is not merely to create visually similar graphics. These SVGs will be used as technical reference material, so **data fidelity is more important than speed**.

A clean SVG with `Q1` is correct.
A beautiful SVG containing a guessed dimension is wrong.

