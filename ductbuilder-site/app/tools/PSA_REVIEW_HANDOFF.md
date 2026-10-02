# PSA Review Geometry Handoff

## Current status

The PSA family is **review-only**. Do not integrate it into the application,
catalogue rules, pricing, or GUI yet.

The current Fusion-style review candidate is
[psa_fusion_saddle_review.py](./psa_fusion_saddle_review.py). It builds the
10 mm saddle from the actual D1/D2 seam in D1's developed surface, then sews
that band and the seam-trimmed D2 shell into one closed six-face BRep solid.
The attempt-4 native FreeCAD captures for `200-100 S`, `P40`, and `A` are
valid, single-solid exports and remove the former broad horn, detached
fragment, and flat D2 base. The rendered review candidate still requires the
user's visual go/no-go; do not treat a valid solid or STEP re-import as visual
approval.

[psa_review.py](./psa_review.py) is an earlier rejected experiment. Leave it
unchanged unless the user explicitly asks to revisit it.

## Required reading order

Read these before changing PSA geometry:

1. This handoff.
2. The supplier drawing: [PSA.png](../../../pngs/originals/PSA.png).
3. The active review script:
   [psa_fusion_saddle_review.py](./psa_fusion_saddle_review.py).
4. The earlier/rejected script for pitfalls only:
   [psa_review.py](./psa_review.py).
5. The approved standalone AP review script for FreeCAD macro/export patterns:
   [ap_200_90_review.py](./ap_200_90_review.py).
6. The headless STEP renderer:
   [render_freecad_step_views.py](./render_freecad_step_views.py).

Read these only if a future task explicitly moves from review geometry into the
application:

- [catalogue_rules_v3.json](../airkan_builder/catalogue_rules_v3.json)
- [geometry.py](../airkan_builder/geometry.py)
- [Allshield_Project_GUI.py](../Allshield_Project_GUI.py)

FreeCAD references:

- [Power Users hub](https://wiki.freecad.org/Power_users_hub)
- [Part TopoShape API source](../../../FreeCAD-main/src/Mod/Part/App/TopoShape.h)
- [Part Python bindings](../../../FreeCAD-main/src/Mod/Part/App/TopoShapePyImp.cpp)

The installed FreeCAD 1.1 runtime exposes:

```python
shape.makeOffset2D(offset, join=0, fill=False, openResult=False, intersection=False)
shape.makeOffsetShape(offset, tolerance, inter=False, self_inter=False,
                      offsetMode=0, join=0, fill=False)
shape.makeThickness(faces, offset, tolerance)
```

The source-level `makeThickSolid` operation is exposed as `makeThickness` in
the installed Python API.

## Authoritative PSA coordinate contract

Definitions:

```text
D1 = big horizontal reference tube
D2 = small vertical tube
```

Coordinate system:

```text
origin = centre of the D2 bottom plane
X      = right
Y      = into the D2 tube
Z      = upward
```

The small tube:

```text
axis                 = +Z
centre               = (0, 0, 0)
outer radius         = D2 / 2
height               = 2 × D2
right tangent plane  = X = +D2 / 2
front tangent plane  = Y = -D2 / 2
```

The big tube:

```text
axis                 = Y
centre X             = a
centre Z             = -D1 / 2
crown                = Z = 0
extent               = Y = -D1 through Y = +D1
construction         = hollow tube, not a solid cylinder
```

The D1 X position is never derived from D1. It is the asymmetry value `a`
directly. There is no left-side placement for this review.

## Asymmetry input

The macro asks for D1, D2, then asymmetry:

```text
S                 symmetric             a = 0
A                 fully asymmetric      a = D2 / 2
number            partial asymmetry     0 <= a < D2 / 2
number > D2 / 2   forbidden
```

For `D1 = 200`, `D2 = 100`:

```text
S   -> D1 centre X = 0
40  -> D1 centre X = +40
A   -> D1 centre X = +50
```

`A` places the D1 centre on the right tangent plane of D2. Numeric `D2 / 2`
is rejected so that `A` is the explicit fully asymmetric choice.

Always enforce:

```text
D1 > D2
```

The lower-right large-circle label in the supplied PSA source drawing is
printed as D2. It is a source error; it must be interpreted as D1.

## Intended Fusion-style construction

This is the user-provided construction contract:

1. Derive D1's outer/inner seam with the D2 outer/inner shell. D1 remains a
   hollow 1 mm sheet; do not export its complete host tube.
2. Develop the D1 outer seam into a plane.
3. Create:

   ```text
   Offset A = 10 mm
   Offset B = 3 × D1
   ```

4. Retain only the developed surface band between the seam and Offset A,
   then map its outer and inner faces back onto D1's curvature.
5. Terminate D2's outer and inner walls at the corresponding outer and inner
   D1 seam curves; its top rim remains at `2 × D2`.
6. Sew the D1 outer band, D1 inner band, offset edge, D2 outer wall, D2
   inner wall, and top rim into one closed solid.

The retained material must be no more than the D1 tube around the opening
edge: a 10 mm saddle patch that follows D1 curvature. It is not a separate D2
collar. At the fully tangential point there may be no D1 material to retain;
that is acceptable for the review drawing.

This construction renders the D2 lower seam as the U-shaped profile in the
supplier drawing without a flat `Z = 0` cap or a Boolean overlap workaround.

## Non-negotiable pitfalls

Do not:

- substitute a standalone D2 fish-mouth for the joined seam assembly; D2 must
  remain joined to the local 10 mm D1 saddle band;
- generate an independent 360-degree D2 collar;
- use D1/2, `-D1/2`, or any left-side formula for the D1 X position;
- export the complete D1 host tube;
- describe a candidate as correct solely because FreeCAD reports one valid
  solid or STEP re-import succeeds;
- modify `psa_review.py` while iterating on the separate Fusion-style model.

## Required review loop

For every geometry iteration:

1. Run in native FreeCAD.
2. Export FCStd, STEP, and JSON.
3. Verify topology:

   ```text
   one valid solid
   STEP re-import is valid
   ```

4. Render and inspect actual geometry in:

   ```text
   isometric view
   front view
   side view
   ```

   Use the exported STEP rather than a surrogate shape:

   ```text
   "C:\Program Files\FreeCAD 1.1\bin\python.exe" ^
       app\tools\render_freecad_step_views.py ^
       --step <exported-step> --out <review-view-folder>
   ```

5. Inspect all three asymmetry cases:

   ```text
   S
   partial (use 40 for D1=200, D2=100)
   A
   ```

6. Compare every view to the supplier drawing before reporting the candidate
   for user review.

The user explicitly requires visual review. Valid Booleans are necessary but
not sufficient.
