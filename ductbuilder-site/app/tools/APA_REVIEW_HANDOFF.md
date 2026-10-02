# APA Review Geometry Handoff

## Current scope

APA is a standalone, review-only FreeCAD model. Do not integrate it into the
catalogue rules, price grids, geometry registry, or GUI until its rendered
geometry has a user visual go/no-go.

The active model is [apa_review.py](./apa_review.py). It subsumes the
symmetric AP review geometry:

```text
APA S, D1=200, D2=90, e=20
= AP 200-90, e=20
```

Native FreeCAD Boolean comparison verified zero volume in both differences:

```text
APA S - AP = 0.0 mm³
AP - APA S = 0.0 mm³
```

The existing [ap_200_90_review.py](./ap_200_90_review.py) remains unchanged
as the user-approved historical fixture. Use `apa_review.py` for further
round-branch review work.

[apa_gui_review.FCMacro](./apa_gui_review.FCMacro) launches the dialog-free
native GUI review. APA attempt 1 has native, full-resolution tiled captures
for `200-90 S`, `P40`, and `A`; all three exported STEP files re-import as
one valid solid. The `S` capture visually matches the AP source transition,
and its Boolean difference from the AP fixture remains zero.

## Required reading order

1. This handoff.
2. The supplier drawings: [AP.png](../../../pngs/originals/AP.png) and
   [APA.png](../../../pngs/originals/APA.png).
3. [apa_review.py](./apa_review.py).
4. [apa_gui_review.FCMacro](./apa_gui_review.FCMacro).
5. [ap_200_90_review.py](./ap_200_90_review.py) for the approved symmetric
   construction.
6. [render_freecad_step_views.py](./render_freecad_step_views.py) for the
   required headless visual review.

## Coordinate and asymmetry contract

```text
D1 = horizontal host/reference duct
D2 = vertical branch

origin = D1 centre in the D2 offset direction
X      = right
Y      = along D1
Z      = upward
```

D1 remains centred at `X=0` and is used only as a Boolean cutter. It is never
part of the exported fitting.

The D2 centre moves right by asymmetry `a`:

```text
S       a = 0
number  0 <= a < (D1 - D2) / 2
A       a = (D1 - D2) / 2
```

`A` is distinct from PSA: its physical condition is

```text
D2 right tangent = D1 right tangent
```

For the AP-equivalent review fixture:

```text
D1=200, D2=90
S   -> D2 centre X = 0
40  -> D2 centre X = +40
A   -> D2 centre X = +55
```

Numeric equality with the maximum is rejected so that the fully asymmetric
position remains explicit as `A`.

## Construction

The model uses the approved AP construction, with only the upper D2 shoulder,
loft, and spigot translated right:

1. Build the D1 contact footprint centred on D1.
2. Build the rectangular-to-square 60 mm transition.
3. Loft its square shoulder to the D2 circle.
4. Create the explicit `e` straight D2 spigot.
5. Hollow the fitting with a 1 mm review wall.
6. Use the D1 cylinder as a cutter to form the concave saddle.
7. Export only the fitting.

Source/review dimensions:

```text
transition height      = 60 mm
saddle length          = D2 + 120 mm
requested contact width = D2 + 100 mm
contact-width limit     = D1
```

The contact-width limit prevents a review saddle extending beyond the D1 host
surface where the requested width is larger than D1.

## Required validation

For each change:

1. Run the script in FreeCAD's native Python runtime.
2. Export FCStd, STEP, and JSON.
3. Re-import the STEP and verify one valid solid.
4. Run [apa_gui_review.FCMacro](./apa_gui_review.FCMacro) in normal-profile
   FreeCAD, create four tiled native views, wait for painting, and capture the
   physical `2560×1440` desktop image. This is the acceptance evidence.
5. Optionally render the exported STEP with
   [render_freecad_step_views.py](./render_freecad_step_views.py) for a
   headless diagnostic only; do not present it as a native GUI screenshot.
6. Inspect the native isometric, front, side, and top views for:

   ```text
   S
   partial (use 40 for D1=200, D2=90)
   A
   ```

The front view should retain the AP-like symmetric silhouette. The side view
must show D2 move to the right until, at `A`, its right tangent reaches D1's
right tangent.
