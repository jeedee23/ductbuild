# TEE_SPECIAL Review Geometry Handoff

## Current scope

TASYMM was reviewed in native FreeCAD and approved by the user on
2026-10-03. It is integrated into the catalogue rules, geometry registry, and
GUI as the `TEE_SPECIAL` `TASYMM` variant. It retains its source-reviewed
sheet, physical K1/K2/K3 frames, and normal STEP-export/re-import validation.

The user-approved Talpha source profile is implemented in the application as
the `TEE_SPECIAL` `TALPHA` variant. Both special-tee variants use explicit
`ON_REQUEST` pricing: catalogue page 157 identifies the geometry codes but
does not give a special-tee price rule. They are coordination models, not
priced products or fabrication certifications. The project register can record
a positive confirmed supplier quote and its reference; that quote is cleared
when the special-tee geometry changes.

The equal-port `T.png` drawing is already the source for the established
`TEE_RECT` family. It is not a separate special-family review task.

The active implementation is [tee_special_review.py](./tee_special_review.py).
Run its dialog-free native GUI review with
[tee_special_gui_review.FCMacro](./tee_special_gui_review.FCMacro).

This special review is intentionally separate from the production `TEE_RECT`
generator. The existing generator already covers the equal-port `T`, but its
constant main section and 90-degree branch must not be repurposed as T-ASSYM
or Talpha.

## Supplier sources

Inspect the relevant drawing before every geometry change:

1. [T.png](../../../pngs/originals/T.png) - equal main ports and vertical
   branch; covered by `TEE_RECT`.
2. [T_2.png](../../../pngs/originals/T_2.png) - `T-ASSYM`, with unequal A/D
   main ports.
3. [T_3.png](../../../pngs/originals/T_3.png) - angled `Talpha`.

The diagrams define three ports with common depth `B`:

```text
K1  left main port:    A x B
K2  branch port:       C x B
K3  right main port:   D x B
```

The drawings also call out physical connection-frame alternatives. Frames are
not cosmetic lines and must be modelled as physical BReps.

## Current review fixtures

The retained vertical-fixture candidates use:

```text
B                  = 200 mm
C                  = 400 mm
main length L      = 1000 mm
branch length      = 300 mm
frame profile      = E20
frame entry depth  = 25 mm
```

Variant values:

```text
T       A=300, D=300, vertical branch
TASYMM  A=300, D=200, vertical branch
```

The rebuilt Talpha source-profile fixture uses:

```text
A=300 mm, B=200 mm, C=300 mm, D=300 mm
L=1000 mm, G=250 mm, alpha=45 degrees, E20
derived E=300.736 mm, minimum F=441.421 mm
K2 return h=141.421 mm, vertical clearance i=100 mm,
horizontal set-back j=100 mm, frame entry depth=25 mm
```

`E20` is an explicit review choice from the source's E20/TDC20 alternatives;
it is not a released automatic profile-selection rule. The code accepts
`E20`, `E30`, `A20`, `A30`, and `A40` through an explicit frame-profile input.

## Construction and coordinate contract

```text
X = main duct from K1 (left) to K3 (right)
Y = common B depth
Z = upward
```

The sheet is a 1 mm hollow BRep. `T` and `TASYMM` have the two visible
`R=150 mm` throat transitions shown in the source.

`TALPHA` is not a diagonal rectangular branch. Its outer XZ profile is:

```text
K1 main top -> E -> rising F wall -> oblique C x B K2 entry face
             -> variable K2 return h -> downstream G main section
```

The K2 return is a source-profile transition, not the frame-entry depth:

```text
h = K2 return length, parallel to F
i = h x sin(alpha), perpendicular/vertical clearance to G; i >= 100 mm
j = h x cos(alpha), horizontal set-back to the G connection
```

Increasing `F` increases `h`, `i`, and `j`. When `F` is omitted, the review
macro derives the minimum valid `F` for `i=100 mm`; a smaller alpha derives a
larger `F`. The 25 mm E20 frame-entry depth remains separate:

```text
outward direction         = (+cos(alpha), 0, +sin(alpha))
opening-length direction  = (+sin(alpha), 0, -cos(alpha))
frame local +Z            = opposite the outward direction
frame mating plane        = source entry face + outward direction x frame depth
```

Each open port has a real Airkan frame from
[makeframe_v2.FCMacro](../vendor/makeframe_v2.FCMacro):

```text
K1  local frame +Z points into the sheet in global +X
K3  local frame +Z points into the sheet in global -X
K2  vertical variants: local frame +Z points into global -Z
K2  TALPHA: local frame +Z points from its mating plane to the source entry face
```

Each frame has four rails and four corner pieces. Consequently, the exported
review assembly has:

```text
1 sheet solid + (3 ports x 8 frame components) = 25 physical solids
```

The sheet terminates at each frame's 25 mm entry plane. The rebuilt Talpha
fixture was verified:

```text
sheet-to-frame gap        = 0.0 mm
sheet/frame overlap       = 0.0 mm3
```

## Visual attempts and evidence

Only real native GUI view/capture comparisons count as visual attempts.

```text
T is covered by the existing TEE_RECT source mapping and has no further
special-family visual attempt.

TASYMM attempt 1  frameless candidate.
TASYMM attempt 2  framed E20 candidate captured and retained.

TALPHA attempt 1  frameless candidate.
TALPHA attempt 2  rejected: generic diagonal-box branch disagreed with T_3.
TALPHA attempt 3  rejected: K2 return used only the 25 mm frame-entry depth.
TALPHA attempt 4  variable K2 return with i=100 mm captured and approved.
```

TASYMM attempt 2 was approved by the user on 2026-10-03 after the native
tiled FreeCAD review of A=300, B=200, C=400, D=200, L=1000,
K2 length=300, with E20 frames. The review output is retained in
`C:\Users\johan\Documents\ductbuild-tee-special-review\tasymm-native-open-2026-10-03`.

Talpha attempt 4 is a physical `2560x1440` desktop capture with native
FreeCAD axonometric, front, right, and top tiled views. It shows the blue
sheet and physical E20 frames. The evidence image is
`TALPHA_K2_clearance_i100_native_2560x1440.png` in the user's Documents review
folder. Its FreeCAD PID was foreground-verified and closed without saving
through the macro's auto-close path.

The review captures are session evidence, not repository release assets.

## Export validation

The rejected Talpha attempts 2 and 3 measurements are superseded. The approved
Talpha attempt 4 passed native validation:

```text
sheet body               valid, one solid
physical frames          24 valid one-solid components
sheet-to-frame gap       0.0 mm
positive-volume overlap  0.0 mm3
STEP re-import           valid, 25 solids, 1398037.692025 mm3
```

The previous `F=325 mm` fixture is explicitly rejected: it cannot keep K2 at
least 100 mm above `G`. At 45 degrees, the minimum valid F is 441.421 mm.

## Dialog-free macro inputs

The macro reads explicit environment variables:

```text
DUCTBUILD_TEE_REVIEW_OUT
DUCTBUILD_TEE_VARIANT
DUCTBUILD_TEE_A_MM
DUCTBUILD_TEE_B_MM
DUCTBUILD_TEE_C_MM
DUCTBUILD_TEE_D_MM
DUCTBUILD_TEE_MAIN_LENGTH_MM
DUCTBUILD_TEE_BRANCH_LENGTH_MM
DUCTBUILD_TEE_ALPHA_DEG
DUCTBUILD_TEE_FRAME_PROFILE
DUCTBUILD_TEE_E_MM
DUCTBUILD_TEE_G_MM
DUCTBUILD_TEE_TOOLS_DIR
DUCTBUILD_TEE_AUTO_CLOSE_SECONDS
```

For Talpha, `DUCTBUILD_TEE_BRANCH_LENGTH_MM` is source dimension `F` and
`G` is the actual downstream straight section. Omitting `E` and `F` causes the
macro to derive the source dimensions and the minimum `i=100 mm` clearance.
An explicit F may be larger, but not smaller. The macro locates
`tee_special_review.py` beside itself or beneath a conventional sibling
`ductbuild` repository. Set `DUCTBUILD_TEE_TOOLS_DIR` explicitly when a copied
macro is outside those locations.

Set `DUCTBUILD_TEE_AUTO_CLOSE_SECONDS` to a positive delay only for automated
captures. After that delay, the macro closes the document without saving and
quits FreeCAD. Interactive runs remain open by default.

On any startup or geometry exception, it writes
`TEE_SPECIAL_GUI_review_error.txt`; it must not require a modal input/output
dialog.

## Required review procedure

For a geometry change:

1. Build through FreeCAD's native Python runtime.
2. Verify one valid sheet solid, 24 valid frame solids, and zero sheet/frame
   gap and volume overlap.
3. Export FCStd, STEP, and JSON.
4. Re-import STEP and verify 25 valid solids.
5. Launch the GUI macro with explicit variables.
6. Create axonometric/front/right/top tiled native views.
7. Foreground-verify the intended FreeCAD window, capture physical
   `2560x1440` desktop evidence, open it in VS Code, and then close that exact
   FreeCAD process.
8. Compare against the supplier drawing.

Allow no more than ten real visual correction attempts per type. Do not call
a headless render a native FreeCAD screenshot.

## Production status

Talpha and TASYMM have cleared the application-production requirements that
are supported by the available source evidence:

- Talpha's approved E/F/C/G dimensional contract and `i >= 100 mm` rule are
  validated by the native builder;
- TASYMM's approved vertical K2 length and unequal-main-port profile are
  validated by the native builder;
- the app exposes K1/K2/K3 joining datums and preserves 24 physical frame
  solids for both variants;
- the normal FreeCAD worker exports and re-imports a valid 25-solid STEP;
- pricing is explicit `ON_REQUEST`, not an invented catalogue amount.

The native STEP translator resolves intentional contacting frame material
differently from the raw independent-solid sum. The app therefore preserves
the raw volume and validates against the OCC physical-union reference with a
0.01% translator tolerance, as well as exact solid count, validity, and
bounds checks.

TASYMM is approved and implemented. Keep its price on request until the
supplier provides a special-tee pricing rule or confirmed quote.
