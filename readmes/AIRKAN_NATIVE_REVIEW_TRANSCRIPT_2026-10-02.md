# AIRKAN Native Review Recovery Transcript - 2026-10-02

## Purpose and scope

This is a durable recovery transcript for the AIRKAN work that followed the
earlier PDF/SVG history. It is a factual chronological handoff, not a
verbatim export of every chat message. It preserves the requirements,
decisions, implementation state, evidence rules, and pause point needed to
resume safely if the active Copilot session is unavailable.

The active session can be reopened while it remains available:

[Open the saved Copilot session](agent-host-session://copilotcli/3388346a-b419-4582-bb01-b21d78da21df)

### 2026-10-03 update

The user approved the TASYMM native tiled FreeCAD review for A=300, B=200,
C=400, D=200, L=1000, K2 length=300, with E20 physical frames. `TASYMM` is
therefore implemented as a `TEE_SPECIAL` application variant with the
reviewed native BRep, three real port frames, and normal STEP
export/re-import validation. Page 157 identifies the Talpha/TASYMM geometry
codes but contains no price rule, so both special-tee variants remain
explicitly `ON_REQUEST` rather than receiving an invented catalogue price. A
project may record a confirmed supplier quote and its reference; the quote is
cleared automatically when the special-tee geometry changes.

## Important terminology

The workflow was sometimes described conversationally as "self learning." No
machine-learning model, automatic rule training, or autonomous product
release mechanism has been added.

What exists is a **human-directed, evidence-driven correction loop**:

1. Build a real FreeCAD BRep from explicit inputs.
2. Produce four real, tiled FreeCAD GUI views.
3. Capture the actual physical desktop at `2560x1440`.
4. Inspect it against the supplier drawing.
5. Correct one identified geometry defect.
6. Retain the successful construction and its evidence.

The accumulated scripts, macros, screenshots, tests, and family handoffs make
the work recoverable and progressively more reliable. They do not replace the
user's visual go/no-go.

## User-set non-negotiable review rules

These rules apply to every fitting family:

- A valid FreeCAD BRep or exported STEP alone is not approval.
- A headless tessellation render is a diagnostic only; it must never be
  described as a native FreeCAD screenshot.
- A valid visual attempt is:

  ```text
  geometry change
  -> dialog-free native GUI macro
  -> axonometric/front/right/top tiled views
  -> physical 2560x1440 desktop screenshot
  -> visual comparison with the supplier drawing
  ```

- Count no more than ten genuine visual correction attempts per fitting type.
  Tooling/capture failures do not count.
- If a type remains wrong after attempt ten, document the blocker and move to
  the next type.
- Macros must receive explicit variables and must not show input/output
  popups. On failure, they must write a durable error file.
- Verify that the intended FreeCAD document is foreground before capture.
- Open the captured PNG in VS Code, then close the exact FreeCAD review
  process immediately after the capture.
- Use a visible blue review colour with dark-blue edges; opaque black hides
  important inner walls and saddles.
- Do not change catalogue release status, prices, production geometry, or the
  application UI merely because a review BRep is valid.

## How this work evolved

### 1. AIRKAN sources, SVG redraws, and visual review

The original AIRKAN effort organized 17 supplier PDFs, extracted 134 technical
drawing PNGs, removed 28 exact duplicates, and retained 106 source drawings.
The initial contour-vectorized SVGs were rejected because they were not true
technical redraws. The established redraw convention became:

```text
white viewport
black geometry
gray hidden/centre lines
violet dimensions (#8B5CF6)
live text and editable SVG primitives
no embedded raster image
```

The repository contains the source originals in [pngs/originals/](../pngs/originals),
the redraws in [svgs/](../svgs), and the original review UI in
[svgs/index.html](../svgs/index.html). The older extraction/SVG transcript is
[AIRKAN_CHAT_TRANSCRIPT_2026-09-28.md](./AIRKAN_CHAT_TRANSCRIPT_2026-09-28.md).

### 2. The duct-builder application was identified as the real product

The user clarified that the drawings are visual references, while the product
is parameter/rules/FreeCAD driven. The active application is under
[ductbuilder-site/app/](../ductbuilder-site/app).

Earlier application work included:

- supplier-PNG previews for the selectable families;
- hover enlargement and a drawing library;
- a compacted component identity area and Project prefix in the header;
- focused GUI smoke checks;
- investigation of CM/BUY and user-supplied STEP workflows.

The planned visual family chooser/wizard, formal CM-0001 contract, and
production expansion of source-only catalogue families remain future work.

### 3. Native fitting review became the active path

The five source-only families were identified in
[catalogue_rules_v3.json](../ductbuilder-site/app/airkan_builder/catalogue_rules_v3.json):

```text
AP_APA_PSA
PR_PRA
TEE_SPECIAL
SUPPORT_AT
COMPOSITE
```

The user required that each candidate first be reviewed visually as a
standalone native FreeCAD fitting before application integration.

## Native FreeCAD review system

### Reliable screenshot procedure

The final operational procedure is:

1. Launch exactly one FreeCAD GUI process with the family macro.
2. Wait for `<FAMILY>_GUI_tiled_review.ready`; on failure, read
   `<FAMILY>_GUI_review_error.txt`.
3. Use `Gui.runCommand("Std_ViewCreate", 0)` to create three additional
   views and `Gui.runCommand("Std_TileWindows", 0)` to tile all four.
4. Close the FreeCAD Start page, set axonometric/front/right/top orientations,
   fit and redraw every view, and wait for GUI paint events.
5. Set DPI awareness before capture; verify the primary display is physically
   `2560x1440`.
6. Bring the actual FreeCAD document process to the foreground and assert the
   foreground process ID before using `Graphics.CopyFromScreen`.
7. Save/open the PNG in VS Code, then close that exact FreeCAD process.

Important established facts:

- `main_window.grab()` corrupts OpenGL view content and must not be used.
- A DPI-unaware capture reports roughly `1720x960` logical pixels and is
  insufficient.
- `StdCmdViewCreate` was rejected by the installed FreeCAD; use
  `Std_ViewCreate`.
- The installed runtime is FreeCAD 1.1.3. Use
  `C:\Program Files\FreeCAD 1.1\bin\python.exe` for review scripts.
- Import `FreeCAD` before `Part` when executing a focused FreeCAD Python
  check via stdin.

Generated capture artifacts remain in the active session's `files/` folder.
They are evidence for this local review session, not repository-managed
release assets.

## Family status

### PSA - review-ready, not production-released

Read [PSA_REVIEW_HANDOFF.md](../ductbuilder-site/app/tools/PSA_REVIEW_HANDOFF.md)
before modifying [psa_fusion_saddle_review.py](../ductbuilder-site/app/tools/psa_fusion_saddle_review.py).

The final PSA construction replaced the rejected broad-horn Boolean approach
with a single closed six-face shell:

1. Derive the D1/D2 seam in D1's developed surface.
2. Offset that seam by a true 10 mm.
3. Map the D1 outer and inner bands back to the D1 curvature.
4. Terminate D2 outer and inner walls on corresponding seam curves.
5. Add the D2 top rim and sew all six faces into one solid.

Native GUI attempt 4 passed for `S`, `P40`, and `A`; each STEP re-imported as
one valid solid. The coordinate contract is:

```text
origin = D2 bottom-plane centre
X      = right
Y      = along D1
Z      = upward

D2 axis = +Z
D1 axis = Y
S -> D1 centre X = 0
A -> D1 centre X = D2 / 2
```

The source drawing's lower-right `Ø2` label means `Ø1`; it is a supplier
typo. Do not reintroduce the old full-height vertical D1 selection cylinder:
it caused the rejected broad horn.

PSA is now implemented in the application with its distinct developed-saddle
native BRep, explicit curved-host reference and branch port, and
`ON_REQUEST` pricing. The D1 host remains a Boolean cutter and is not
exported. This is a coordination model, not a fabrication or price
certification.

### AP / APA - production coordination models

Read [APA_REVIEW_HANDOFF.md](../ductbuilder-site/app/tools/APA_REVIEW_HANDOFF.md)
and use [apa_review.py](../ductbuilder-site/app/tools/apa_review.py) with
[apa_gui_review.FCMacro](../ductbuilder-site/app/tools/apa_gui_review.FCMacro).

The symmetric review case was proven geometrically:

```text
APA S, D1=200, D2=90, e=20
equals the historical AP fixture

APA S - AP = 0.0 mm3
AP - APA S = 0.0 mm3
```

Native `S`, `P40`, and `A` blue-view captures exist and their STEP exports
re-import as one valid solid. The historical
[ap_200_90_review.py](../ductbuilder-site/app/tools/ap_200_90_review.py) is
retained unchanged. Future AP use is represented by APA `S`, not by deleting
the approved fixture.

### PR / PRA - review-ready, not production-released

Read [PR_PRA_REVIEW_HANDOFF.md](../ductbuilder-site/app/tools/PR_PRA_REVIEW_HANDOFF.md).

The review generator and macro are:

- [pr_pra_review.py](../ductbuilder-site/app/tools/pr_pra_review.py)
- [pr_pra_gui_review.FCMacro](../ductbuilder-site/app/tools/pr_pra_gui_review.FCMacro)

The accepted review fixture uses `D1=200`, `B=100`, and `L=200`.

```text
S    centred PR
P40  40 mm partial right offset
A    right-tangent PRA
```

The native blue captures show the hollow rectangular branch, 1 mm review
wall, 100 mm projection above D1's crown, and concave D1 saddle. The source
comparison passed for the centred PR and right-tangent PRA silhouettes. Native
STEP re-import results were:

```text
S    65659.860216 mm3, one valid solid
P40 73541.088128 mm3, one valid solid
A    81828.407483 mm3, one valid solid
```

The initial `P40` macro failed because parsing occurred before its exception
boundary. It is fixed:

- both `40` and `P40` resolve to `(40.0, "PARTIAL")`;
- all macro startup parsing runs inside the exception boundary;
- invalid input writes `PR_PRA_GUI_review_error.txt` without a popup.

Do not invent the unresolved product-name rule that maps every B-versus-D1
combination to PR or PRA. The catalogue and production contract are still
source-only.

### TEE_SPECIAL - Talpha and TASYMM production coordination models

Review-only files:

- [tee_special_review.py](../ductbuilder-site/app/tools/tee_special_review.py)
- [tee_special_gui_review.FCMacro](../ductbuilder-site/app/tools/tee_special_gui_review.FCMacro)
- [TEE_SPECIAL_REVIEW_HANDOFF.md](../ductbuilder-site/app/tools/TEE_SPECIAL_REVIEW_HANDOFF.md)

The supplier sources are [T.png](../pngs/originals/T.png),
[T_2.png](../pngs/originals/T_2.png), and
[T_3.png](../pngs/originals/T_3.png). The equal-port `T.png` is already the
source mapped to the established `TEE_RECT` family; only `T-ASSYM` and
`Talpha` require special-family review.

The diagnostic review model retains `T`, `TASYMM`, and `TALPHA`, each sharing
depth `B` and using a blue native display. `T` is already covered by
`TEE_RECT`; TASYMM retains the paired visible `R=150` mm throat transitions
for its outstanding source review.

The former Talpha attempt used a generic diagonal rectangular branch. The user
correctly rejected it because it disagreed with the source drawing. It has
been replaced by the source-defined asymmetric profile:

```text
K1 main top -> E -> rising F wall -> oblique C x B K2 entry face
             -> variable K2 return -> downstream G main section
```

The 25 mm E20 frame-entry depth is only the physical K2 frame attachment; it
is not the sheet return to G. The approved source-profile clearance contract
is:

```text
h = K2 return length parallel to F
i = h x sin(alpha), perpendicular/vertical clearance to G
j = h x cos(alpha), horizontal set-back to G
i >= 100 mm
```

For `A=300`, `B=200`, `C=300`, `D=300`, `L=1000`, `G=250`, `alpha=45`, and
E20, the macro derives `E=300.736 mm`, minimum `F=441.421 mm`,
`h=141.421 mm`, and `i=j=100 mm`. Reducing alpha derives a larger F; for
example, at 35 degrees the minimum F is `602.789 mm`. A larger explicit F
increases h/i/j while preserving G.

Native Talpha validation passed:

```text
one valid sheet solid
24 valid one-solid E20 frame components
sheet-to-frame gap = 0.0 mm
positive-volume overlap = 0.0 mm3
STEP re-import = 25 valid solids, 1398037.692025 mm3
```

The old `F=325` fixture is rejected because it does not provide the required
100 mm K2 clearance over G.

Current attempt record:

```text
T                   covered by the existing TEE_RECT source mapping
TASYMM attempt 2   framed E20 candidate captured; user approved 2026-10-03
TALPHA attempt 2   rejected generic diagonal-box branch
TALPHA attempt 3   rejected: return used only the 25 mm E20 frame-entry depth
TALPHA attempt 4   i=100 mm K2-clearance profile captured; user approved
```

Talpha attempt 4 is a physical `2560x1440` blue native GUI capture with four
tiled views. Its FreeCAD PID owned the foreground window, and the macro
closed the document without saving before quitting FreeCAD. The E20 choice is
explicit review input, not a production auto-selection rule. Talpha has the
required user visual approval and is now implemented through the application
geometry registry, rules, physical frames, connection datums, and normal
FreeCAD worker STEP export with explicit `ON_REQUEST` pricing. TASYMM has the
same implementation path after its user approval on 2026-10-03. Read
[TEE_SPECIAL_REVIEW_HANDOFF.md](../ductbuilder-site/app/tools/TEE_SPECIAL_REVIEW_HANDOFF.md)
for the full coordinate, construction, evidence, and release state.

### SUPPORT_AT and COMPOSITE - unstarted

Do not infer their geometry from names alone.

1. `SUPPORT_AT`: inspect the AT, ODS, ODM, and ODR drawings and distinguish
   all required dimensions and fixing details.
2. `COMPOSITE`: inspect B-G, B-B, and G-VER and decide whether each is a safe
   composition of approved generators or requires a new review model.

Both families remain `SOURCE_REGISTER_ONLY` source records and are excluded
from the application selector, type browser, drawing library, register, and
build queues. Legacy project records are retained but must be migrated before
editing or building.

## Production-release guardrail

The review models prove geometry candidates only. Before any family moves to
production, establish and test all of:

- catalogue status and official product naming;
- input-field schema and validation;
- price or `ON_REQUEST` policy;
- material and thickness policy;
- connection-port semantics;
- backend-independent geometry implementation;
- focused rules, geometry, and GUI tests;
- user visual approval.

AP/AP/APA/PSA, PR/PRA, approved Talpha, and approved TASYMM now satisfy this application
contract with native FreeCAD production adapters, focused rule tests, and
worker STEP round trips. AP/APA/PSA use the exact supplier matrix for listed
nominal D1/D2 combinations; matrix dashes and nonstandard dimensions remain
`ON_REQUEST`. PR/PRA and Talpha remain `ON_REQUEST`; no supplier price was
invented. Do not promote `SUPPORT_AT` or `COMPOSITE` solely because an
isolated review STEP is valid.

The requested application progress bar remains deferred.

## Exact resume procedure

1. Read this transcript.
2. Read the relevant family handoff in
   [ductbuilder-site/app/tools/](../ductbuilder-site/app/tools).
3. Inspect the supplier PNG before choosing dimensions or construction.
4. Check the session `todos` state:

   ```text
   pr-pra-visual-attempt-01 = done
   tee-special-review       = in progress
   integrate-approved-psa   = blocked intentionally
   ```

5. For TEE_SPECIAL, keep real frame BReps and compare every candidate directly
   to the source profile; do not replace frames with cosmetic reference lines
   or revert Talpha to a generic diagonal box.
6. Run a focused native-FreeCAD BRep test and STEP re-import.
7. Run the GUI macro, foreground-verify, capture at physical `2560x1440`,
   open the capture, inspect it, then close the exact FreeCAD process.
8. Update the relevant family handoff with the attempt number, outcome, and
   evidence before moving on.

## Related durable records

- [CHAT_HISTORY.md](./CHAT_HISTORY.md) - index of all preserved workstreams.
- [AIRKAN_CHAT_TRANSCRIPT_2026-09-28.md](./AIRKAN_CHAT_TRANSCRIPT_2026-09-28.md)
  - original source-extraction/SVG transcript.
- [PSA_REVIEW_HANDOFF.md](../ductbuilder-site/app/tools/PSA_REVIEW_HANDOFF.md)
  - PSA construction and validation detail.
- [APA_REVIEW_HANDOFF.md](../ductbuilder-site/app/tools/APA_REVIEW_HANDOFF.md)
  - APA/AP proof and review detail.
- [PR_PRA_REVIEW_HANDOFF.md](../ductbuilder-site/app/tools/PR_PRA_REVIEW_HANDOFF.md)
  - PR/PRA review contract and evidence.

## Resuming this work

The `agent-host-session` URI is not reliable in this VS Code setup. To find
this conversation, open **Chat Sessions** in VS Code and select the session
from **2026-10-02** concerning the AIRKAN native FreeCAD review work. If it is
not available there, this transcript and the linked family handoffs contain
the durable recovery state.
