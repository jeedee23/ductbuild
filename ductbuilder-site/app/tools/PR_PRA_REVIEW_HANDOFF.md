# PR/PRA Review Geometry Handoff

## Current scope

PR/PRA is implemented in the application for the reviewed `B < D1` scope.
The catalogue rules, geometry registry, GUI, and price grid use the accepted
mapping: `S` is PR, `A` is PRA, and a manual intermediate `P` remains on
request because it is not a catalogue position.

The active model is [pr_pra_review.py](./pr_pra_review.py), launched for
native review by [pr_pra_gui_review.FCMacro](./pr_pra_gui_review.FCMacro).
It represents the rectangular branch alone; D1 is a Boolean cutter and is
never exported as part of the fitting.

The exact supplier page 46 matrix is used without interpolation. It selects
the first `L+B` maximum band and the physical frame column:

```text
NO_FRAME
E20 or E30
A40
```

`E20`, `E30`, and `A40` create the corresponding physical branch frame in
the application export. `B >= D1` is not exposed: it needs a separate native
geometry review before the page's `B > Ø` price rows can be used safely.

## Source comparison and accepted review result

Read these drawings before changing the review geometry:

1. [PR.png](../../../pngs/originals/PR.png) for the centred branch.
2. [PRA.png](../../../pngs/originals/PRA.png) for the right-tangent branch.
3. [PR - PRA.png](../../../pngs/originals/PR%20-%20PRA.png) for the
   isometric branch-on-round arrangement.

Native FreeCAD review attempt 1 used a 200 mm D1 host with a 100 mm by 200 mm
rectangular branch. Full physical `2560x1440` desktop captures were made for:

```text
S    centred PR silhouette
P40  40 mm right partial offset
A    right-tangent PRA silhouette
```

The blue native views show the expected open rectangular branch, 1 mm review
wall, 100 mm projection above D1's crown, and concave D1 saddle. The `S`
front profile matches PR's symmetric semicircle contact; the `A` profile
matches PRA's crown-to-right-tangent quarter-circle contact. `P40` supplies
the intermediate offset evidence.

Every reviewed STEP was re-imported in FreeCAD as exactly one valid solid:

```text
S    65659.860216 mm3
P40 73541.088128 mm3
A    81828.407483 mm3
```

The originally attempted `P40` GUI run was a launcher failure, not a visual
attempt: `P40` was parsed before the macro's error boundary, so FreeCAD showed
a transient dialog. The launcher now parses inside that boundary and writes
`PR_PRA_GUI_review_error.txt` on any startup failure without a popup.

## Coordinate and asymmetry contract

```text
origin = D1 centre line at the branch mid-length
X      = right across D1
Y      = along the D1 host axis
Z      = upward

D1 axis = +Y
D1 radius = D1 / 2
```

The hollow branch spans `Y=-L/2` through `Y=+L/2`. Its top plane is at:

```text
Z = D1 / 2 + 100 mm
```

Asymmetry `a` moves the branch centre in positive X:

```text
S        a = 0
P<number> or number
         0 <= a < (D1 - B) / 2
A        a = (D1 - B) / 2
```

At `A`, the branch's right side is tangent to the right side of D1. A numeric
value equal to the maximum is rejected so that the catalogue-significant
right-tangent case stays explicit as `A`.

For the reviewed fixture:

```text
D1=200, B=100
S   -> branch centre X = 0
P40 -> branch centre X = +40
A   -> branch centre X = +50
```

## Construction

The review fitting is made with real FreeCAD BReps:

1. Create the outer `B x L` branch box from `Z=0` to `Z=D1/2+100`.
2. Remove an oversized inner box to leave a 1 mm hollow review wall and open
   branch end.
3. Subtract the D1 cylinder to form the concave saddle contact.
4. Verify one valid solid, then export FCStd, STEP, and review JSON.

The review view uses a light blue shape colour with dark-blue edges so the
inner wall, open top, and saddle profile remain visible in native captures.

## Required validation

For any geometry change:

1. Run the review script using FreeCAD's Python runtime.
2. Confirm the FCStd, STEP, and JSON outputs exist.
3. Re-import the STEP in FreeCAD and verify one valid solid.
4. Run the GUI macro with explicit environment variables.
5. Create axonometric, front, right, and top native tiled views.
6. Verify that the intended FreeCAD process is foreground, then capture the
   composed physical `2560x1440` desktop image.
7. Inspect the screenshot against the supplier drawings.
8. Close that exact FreeCAD review process immediately after the capture.

Count only a geometry change followed by a valid native visual comparison as
one correction attempt. Limit a fitting type to ten such attempts. Do not
describe a headless render as native FreeCAD screenshot evidence.

## Production status

The reviewed `B < D1` PR/PRA construction is in production as a FreeCAD
coordination model:

- `S` maps to PR and `A` maps to PRA;
- matrix prices are direct catalogue prices, including the selected physical
  frame column;
- `P` remains `ON_REQUEST`;
- D1 is retained as a curved-host Boolean reference and is not exported;
- a framed E20 worker export/re-import passed with nine valid solids.

The `B >= D1` supplier rows remain deliberately unavailable until their
geometry and product mapping have native-review evidence.
