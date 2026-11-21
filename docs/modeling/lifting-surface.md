# Lifting Surface

A lifting surface is a wing, tail, or fin. It is a chain of **sections** that
starts at the **root profile**. Each section has a span, a sweep, a dihedral, a
twist, and a **tip profile** (chord and airfoil). The root profile of a section
is the tip profile of the section before it. Studio builds the profile stations
of the surface from this chain; the planform values and overall angles are
measured from it.

Select the surface to edit it in the **Parameters** tab. The editor has the
sections **General**, **Planform**, **Angles**, **Sections**, **Section
Profiles**, **End Caps**, **Control Surfaces**, and **Airfoil Shaping**. An
edit that would give a section a span or chord of zero or less is refused, and
the status bar says why. Its airfoils are described in [Airfoils](airfoils.md),
and the control surfaces cut into it in [Control Surface](control-surface.md).

## General

| Parameter | Unit | Description |
|---|---|---|
| Name | — | Name of the component. |
| Type | — | Component type. Read-only. |
| Symmetry / Mirror | — | **Single (No Mirror)** builds one panel along +Y. **Bilateral (Mirror XZ)** adds the mirror image on the −Y side. |

Use **Single (No Mirror)** for a fin. A V-tail is a mirrored surface with a large
dihedral; use the **Ruddervator** control surface type on it.

For a mirrored surface, Position Y in the Transform tab moves both panels away
from the plane of symmetry. The gap between them counts toward the span and the
area (see [Planform](#planform)).

## Sections

The **Sections** table has one row per section, from root to tip. The units in
the column headers follow the display units.

| Parameter | Unit | Description |
|---|---|---|
| Span | mm | Length of the section along Y, not along the dihedral slope. |
| Sweep | ° | Sweep of the section, measured on the line at **Sweep Location**. Positive moves the tip aft. |
| Dihedral | ° | Dihedral of the section. Positive raises the tip. |
| Twist | ° | Change of incidence from the section's root to its tip. Positive raises the leading edge. The twists add up from root to tip. |

The buttons under the table:

- **Split** divides the selected section into two at half its span. Each half
  gets half the twist. The new station between them gets the mean of the two
  chords and the section's root airfoil. A section whose span or twist is a
  formula cannot be split.
- **Add** appends a section at the tip. It continues the tip section's sweep,
  dihedral, twist, and airfoil, with 0.8 × its span and 0.7 × its tip chord.
- **Remove** deletes the selected section. The sections after it move inboard.
  The last section cannot be deleted.

The selected section is highlighted in the 3D Viewer.

## Section Profiles

**Section Profiles** shows the two profiles of the selected section.

| Parameter | Unit | Description |
|---|---|---|
| Root Chord | mm | Chord of the section's root profile. |
| Root Airfoil | — | Airfoil of the root profile. Click **Choose** to change it. |
| Tip Chord | mm | Chord of the section's tip profile. |
| Tip Airfoil | — | Airfoil of the tip profile. Click **Choose** to change it. |

See [Airfoils](airfoils.md#choosing-an-airfoil) for the airfoil dialog.

## Planform

The **Planform** table shows eight values for the whole surface. Check
**Driver** on up to three of them. Driver values are editable; the others are
calculated.

| Parameter | Unit | Description |
|---|---|---|
| Planform Area | dm² | Area \(S\). See below. |
| Span | mm | Span \(b\). Tip to tip for a mirrored surface. |
| Aspect Ratio | — | \(b^2 / S\). |
| Taper Ratio | — | Tip chord divided by root chord. |
| Root Chord | mm | Chord \(c_r\) of the root profile. |
| Tip Chord | mm | Chord \(c_t\) of the last tip profile. |
| Average Chord | mm | \((c_r + c_t)/2\). |
| Mean Aerodyn Chord (MAC) | mm | \(\tfrac{2}{3}\left(c_r + c_t - \dfrac{c_r c_t}{c_r + c_t}\right)\). |

The planform values treat the surface as one straight-tapered panel from the
root chord to the tip chord. With \(b_p\) the sum of the section spans and
\(y_0\) the Position Y of the component:

| Surface | Span | Area |
|---|---|---|
| Single | \(b = b_p\) | \(S = b_p (c_r + c_t)/2\) |
| Mirrored | \(b = 2(b_p + \lvert y_0 \rvert)\) | \(S = b_p (c_r + c_t) + 2\lvert y_0 \rvert c_r\) |

The default drivers are **Span**, **Root Chord**, and **Tip Chord**. When you
type a number into a driver, the sections change at once: the span is spread
over the sections in proportion to their spans, and inner chords keep their
place between the root and tip chords. When you type a formula, Studio stores
it on the planform and changes the sections whenever its value changes.
Unchecking a driver removes its formula. A planform formula may not change a
value that has its own formula in a section; Studio refuses such an edit.

## Angles

The **Angles** section shows the root-to-tip angles of the whole surface.

| Parameter | Unit | Description |
|---|---|---|
| Sweep Angle | ° | Sweep from the root to the tip profile, on the **Sweep Location** line. |
| Sweep Location | — | Chord line the sweep is measured on: **Leading Edge (0%)**, **Quarter Chord (25% MAC)**, **Half Chord (50%)**, or **Trailing Edge (100%)**. |
| Dihedral Angle | ° | Dihedral from the root to the tip profile. |
| Twist / Washout | ° | Tip incidence minus root incidence. A negative value is washout. |
| Twist Axis Location | — | Chord point the profiles twist about: **Leading Edge (0%)**, **Quarter Chord (25% c)**, **Half Chord (50%)**, **Hinge Line (75%)**, or **Trailing Edge (100%)**. |

A value typed into **Sweep Angle** or **Dihedral Angle** changes the slope of
every section by the same amount, so cranks are kept. A value typed into
**Twist / Washout** adds the difference to the sections in proportion to their
spans. A formula is stored and applied whenever its value changes, as for the
planform drivers.

**Sweep Location** also sets the line each section's **Sweep** is measured on.
Changing it keeps the section sweep values, so the shape of the surface changes.

## End Caps

**Tip Cap Type** sets the shape of the outer tip.

| Type | Description |
|---|---|
| Flat | The surface ends at the tip profile. |
| Round (Dome) | A rounded cap beyond the tip profile. |
| Sharp (Bevel) | A beveled cap beyond the tip profile. |
| Winglet | A winglet that continues from the tip profile. |

Round and sharp caps:

| Parameter | Unit | Description |
|---|---|---|
| Tip Length | mm | How far the cap extends beyond the tip profile. Default 20. |
| Tip Sweep Offset | mm | Shift of the cap's outer end along X. Default 0. |

Winglets:

| Parameter | Unit | Description |
|---|---|---|
| Match Tangent | — | **Yes (Continuous Tangent)** continues the wing's leading- and trailing-edge sweep at the winglet root and hides **LE Sweep Root** and **TE Sweep Root**. **No (Manual Angle)** uses those two values. |
| Arc Span | mm | Length of the winglet along its curve. Default 130. The row below shows the resulting **Height** (along Z) and **Span** (along Y). |
| Cant Root | ° | Cant angle at the winglet root. 0° continues along the span; 90° is vertical. Default 0. |
| Cant Tip | ° | Cant angle at the winglet tip. Default 80. |
| Blend Radius | mm | Length along the winglet over which the cant changes from Cant Root to Cant Tip; beyond it the cant stays at Cant Tip. With 0 the cant changes evenly over the whole winglet. Default 0. |
| LE Sweep Root, LE Sweep Tip | ° | Leading-edge sweep at the winglet root and tip. Defaults 20 and 48. |
| LE Curvature | mm | Extra X offset of the leading edge at the middle of the winglet, fading to 0 at both ends. Default 0. |
| TE Sweep Root, TE Sweep Tip | ° | Trailing-edge sweep at the winglet root and tip. Defaults 14 and 24. |
| TE Curvature | mm | Extra X offset of the trailing edge at the middle of the winglet, fading to 0 at both ends. Default 0. |
| Toe Root, Toe Tip | ° | Toe angle of the winglet sections at the root and tip. Defaults 0 and −1.5. |
| Root Chord Scale | × | Winglet root chord as a multiple of the wing tip chord. Default 1.0. |
| Tip Chord Scale | × | Winglet tip chord as a multiple of the wing tip chord. Default 0.45. |
| Tip Thickness Scale | × | Airfoil thickness at the winglet tip as a multiple of the wing tip airfoil. Default 0.7. |

Switching between Round and Sharp keeps the cap values. Any other change of type
starts from the defaults of the new type.

## Airfoil Shaping

| Parameter | Unit | Description |
|---|---|---|
| Section Alignment | — | **Planform Parallel (XZ)** keeps every airfoil parallel to the XZ plane. **Dihedral Normal (Perpendicular)** rolls each airfoil to stand normal to the surface: by the section's dihedral at the root and tip, and by the mean of the two dihedrals where two sections meet. |
| TE Thickness | fraction of chord | Thickness added at the trailing edge of every airfoil. |
| Thickness Scale | × | Multiplier on the thickness of every airfoil. |
| Camber Scale | × | Multiplier on the camber of every airfoil. |

The last three are described in [Airfoils](airfoils.md#airfoil-shaping).

## Control Surfaces

This section lists the control surfaces attached to the surface, with **Name**,
**Type**, and deflection (**Defl**). The buttons add, duplicate, move up, move
down, and delete a control surface. The table below the list edits the selected
control surface; its rows are the same as in the control surface's own editor.

## Default shape

The **Model** group of the toolbar creates each part with a starting shape.
A new part is selected after it is created. Its name gets a number, such as
**Fuselage 2**, when the name is already taken.

| Property | Value |
|---|---|
| Name | Lifting Surface |
| Attached to | The first fuselage in the project, or Vehicle when there is none |
| Position | 0, 0, 0: the root leading edge is at the origin of the frame it is attached to |
| Mass | 250 g |
| Symmetry / Mirror | Bilateral (Mirror XZ) |
| Sections | One section: span 500 mm, dihedral 0°, twist 0° |
| Chords | Root 220 mm, tip 110 mm |
| Airfoil | NACA 2412 at the root and the tip |
| Sweep | −3.15° on the quarter-chord line, which gives a straight leading edge |
| Sweep Location, Twist Axis Location | Quarter chord |
| Section Alignment | Planform Parallel (XZ) |
| Tip Cap Type | Flat |
| Planform drivers | Span, Root Chord, Tip Chord |

The resulting planform has a span of 1000 mm, an area of 16.5 dm², an aspect
ratio of 6.06, and a MAC of 171.1 mm. Set Position X in the Transform tab to
move the surface aft along the fuselage.
