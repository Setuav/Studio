# Geometry

The Geometry plugin adds three components to the vehicle: the **Fuselage**,
the **Lifting Surface**, and the **Control Surface**. This page explains the
coordinate system, how parts are placed and attached, and every value you can
edit on the three components. Airfoils are described in [Airfoils](airfoils.md).
Most numeric fields also accept a formula; see
[Parametric Model](../user-guide/parametric-model.md).

## Coordinates and units

All geometry uses one right-handed axis system:

| Axis | Direction |
|---|---|
| +X | Aft, from the nose toward the tail. |
| +Y | Right (starboard), looking forward. A lifting surface is built along +Y. |
| +Z | Up. |

Each component has its own frame. A component that is not attached to another
one is placed in the vehicle frame. The fuselage created by **Add Fuselage** has
its nose at X = 0.

The project stores lengths in millimeters, angles in degrees, and areas in
square decimeters. The Properties panel shows values in the units chosen under
**Edit → Settings → Units**. The default preset, **Metric (SI Standard)**, uses
mm, dm², and degrees. The **End Caps** fields of a lifting surface are always in
mm and degrees.

## Placing and attaching parts

Select a component and open its **Transform** tab.

| Parameter | Unit | Description |
|---|---|---|
| Attached to | — | **Vehicle**, or the component whose frame this component is placed in. |
| Position X, Y, Z | mm | Origin of the component in the frame it is attached to. |
| Rotation X | ° | Roll, about the X axis. |
| Rotation Y | ° | Pitch, about the Y axis. A positive value raises the nose or the leading edge. |
| Rotation Z | ° | Yaw, about the Z axis. |

The rotations are applied in the order yaw, pitch, roll: \(R = R_z R_y R_x\).
Use Rotation Y to set the incidence of a wing. Rotation X = 90° turns the +Y
span of a lifting surface to +Z, for example for a vertical fin.

The origin of each component is:

- **Fuselage**: the point its section positions are measured from.
- **Lifting surface**: the leading edge of the root profile.
- **Control surface**: placed by its lifting surface. Its Transform tab shows
  **Attached to** but does not let you change it there.

### Attachment

A component that is attached to another one moves and rotates with it. To
change the attachment, pick another entry in **Attached to**. The list leaves
out the component itself, the components attached to it, and control surfaces.
The component keeps its place in the 3D Viewer; Studio recalculates its
Position and Rotation in the new frame.

- **Add Lifting Surface** attaches the new surface to the first fuselage in the
  project, if there is one.
- A control surface is always attached to a lifting surface. Choose the surface
  under **Lifting Surface** in the control surface's **General** section.
- A mirrored lifting surface is mirrored across the XZ plane of the component
  it is attached to.
- When a lifting surface is attached to a fuselage and its root does not reach
  the fuselage surface, the 3D Viewer fills the gap between the root and the
  fuselage.

### Vehicle tree

In the Project Explorer, fuselages and lifting surfaces are listed directly
under **Vehicle**, whatever they are attached to. Control surfaces are listed
under their lifting surface. Deleting a lifting surface also deletes its control
surfaces. Components attached to a deleted component are attached to the
vehicle where they are.

## Fuselage

A fuselage is a loft through cross-sections. The sections are grouped in
**segments**; each segment is lofted on its own, from its first section to its
last, and drawn in its own color. A segment needs at least two sections.

Select the fuselage to edit it in the **Parameters** tab.

### General

| Parameter | Unit | Description |
|---|---|---|
| Name | — | Name of the component. |
| Type | — | Component type. Read-only. |

### Segments

The **Segments** table has one row per segment.

| Column | Description |
|---|---|
| Tag | Name of the segment. Double-click to edit. |
| Sections | Number of sections in the segment. Read-only. |
| Method | **Smooth** lofts a smooth surface through the sections. **Ruled** joins neighbouring sections with straight lines. |

The buttons under the table add a segment after the selected one, duplicate,
move up, move down, and delete the selected segment. A new segment has two
circular sections of 100 mm diameter at X = 0 and X = 100 mm. The last segment
cannot be deleted.

### Sections

Select a segment to list its sections. The **Sections** table shows each
section's number, **Profile** type, **X** position, and **Size**.

The buttons under the table open the 2D inspector, add a section after the
selected one, duplicate, move up, move down, and delete the selected section.
A new section is a 100 mm circle. It is placed halfway between its neighbours,
or 100 mm behind the last section, or 100 mm in front of the first section. A
segment keeps at least two sections. The selected section is highlighted in
the 3D Viewer.

The **Transform** section below the table places the selected section in the
fuselage frame. The profile lies in the section's YZ plane.

| Parameter | Unit | Description |
|---|---|---|
| Position X | mm | Station of the section along the fuselage. |
| Position Y, Z | mm | Center of the profile. Use Z to raise or lower the section. |
| Rotation X, Y, Z | ° | Rotation of the section plane about its center. |

### Section profiles

**Section Properties** sets the profile of the selected section. Pick the shape
in **Profile**. Changing the shape resets the section to that shape's default
size.

| Profile | Parameter | Unit | Description |
|---|---|---|---|
| Circle | Diameter | mm | Diameter of the circle. Default 100. |
| Ellipse | Width | mm | Width along Y. Default 100. |
| Ellipse | Height | mm | Height along Z. Default 100. |
| Rectangle | Width, Height | mm | Outer size. Default 100 × 100. |
| Rectangle | Corner radius | mm | Radius of the four corners. Default 0. |
| Trapezoid | Top width | mm | Width of the upper (+Z) edge. Default 80. |
| Trapezoid | Bottom width | mm | Width of the lower (−Z) edge. Default 100. |
| Trapezoid | Height | mm | Height along Z. Default 100. |
| Trapezoid | Corner radius | mm | Radius of the four corners. Default 0. |
| Triangle | Base width | mm | Width of the base. Default 100. |
| Triangle | Height | mm | Height along Z. Default 100. |
| Triangle | Orientation | — | **Up** puts the apex at the top, **Down** at the bottom. |
| Triangle | Corner radius | mm | Radius of the three corners. Default 0. |
| Polygon | Vertices | — | Number of vertices. Edit them in the vertex table. |

A polygon profile has a vertex table with **Y**, **Z**, and **Radius** (all in
mm) for each vertex. Radius rounds that corner. A polygon needs at least three
vertices; the default is a triangle with vertices at (−50, −50), (50, −50), and
(0, 50).

Dimensions must not be negative. Each corner radius is limited so that it fits
on the edges next to it.

### 2D section inspector

Click **Inspect & Edit 2D Section...**, or double-click a section, to open the
**Fuselage Section Inspector**. Use **Segment** and the arrow buttons to move
between sections. The inspector edits the same **Profile Definition** and
**Section Transform** values as the panel. For a polygon, drag a vertex on the
canvas to move it, or click an edge to insert a vertex.

**Section Properties & Engineering Metrics** shows the area, perimeter, width
and height, aspect ratio (W/H), centroid, and hydraulic diameter of the
section. **Display Options** shows the previous and next sections as ghosts,
dimension annotations, the centroid, the grid, and the 128 sample points.
Click **Apply** to keep your changes, **Save & Close** to keep them and close,
or **Cancel** to discard the changes made since the last **Apply**.

Every fuselage profile is sampled with 128 points around its outline.

## Lifting surface

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
the status bar says why.

### General

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

### Sections

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

### Section Profiles

**Section Profiles** shows the two profiles of the selected section.

| Parameter | Unit | Description |
|---|---|---|
| Root Chord | mm | Chord of the section's root profile. |
| Root Airfoil | — | Airfoil of the root profile. Click **Choose** to change it. |
| Tip Chord | mm | Chord of the section's tip profile. |
| Tip Airfoil | — | Airfoil of the tip profile. Click **Choose** to change it. |

See [Airfoils](airfoils.md#choosing-an-airfoil) for the airfoil dialog.

### Planform

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

### Angles

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

### End Caps

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

### Airfoil Shaping

| Parameter | Unit | Description |
|---|---|---|
| Section Alignment | — | **Planform Parallel (XZ)** keeps every airfoil parallel to the XZ plane. **Dihedral Normal (Perpendicular)** rolls each airfoil to stand normal to the surface: by the section's dihedral at the root and tip, and by the mean of the two dihedrals where two sections meet. |
| TE Thickness | fraction of chord | Thickness added at the trailing edge of every airfoil. |
| Thickness Scale | × | Multiplier on the thickness of every airfoil. |
| Camber Scale | × | Multiplier on the camber of every airfoil. |

The last three are described in [Airfoils](airfoils.md#airfoil-shaping).

### Control Surfaces

This section lists the control surfaces attached to the surface, with **Name**,
**Type**, and deflection (**Defl**). The buttons add, duplicate, move up, move
down, and delete a control surface. The table below the list edits the selected
control surface; its rows are the same as in the control surface's own editor.

## Control surface

A control surface is a movable part of a lifting surface: an aileron, flap,
elevator, rudder, elevon, or ruddervator. It is cut from its lifting surface
between two spanwise positions and hinged at a chordwise line. On a mirrored
surface it is built on both sides.

Select the control surface in the Project Explorer to edit it, or select its
row in the lifting surface's **Control Surfaces** section.

### General

| Parameter | Unit | Description |
|---|---|---|
| Name | — | Name of the component. |
| Type | — | Component type. Read-only. |
| Lifting Surface | — | The lifting surface the control surface belongs to. |

### Control Surfaces

Span positions are measured along Y from the root profile of the lifting
surface. The semi-span \(s\) is the Y distance from the root profile to the tip
profile of one side. Fractions of the span are "eta" values: \(\eta = y / s\).

| Parameter | Unit | Description |
|---|---|---|
| Type | — | **Aileron**, **Flap**, **Elevator**, **Rudder**, **Elevon**, or **Ruddervator**. |
| Sizing Driver Mode | — | Which values you edit and which ones are kept when the lifting surface changes. See below. |
| Area | dm² | Area of the control surface on one side: Span Length × Chord Fraction × the chord at its mid-span, interpolated linearly between the root and tip chords. |
| Area Ratio | % | Area divided by \(s\,(c_r + c_t)\) of the lifting surface. Read-only. |
| Span Start | mm | Inboard end, from the root profile. |
| Span End | mm | Outboard end, from the root profile. |
| Span Length | mm | Span End minus Span Start. Read-only. |
| Eta Start | — | Span Start as a fraction of \(s\). |
| Eta End | — | Span End as a fraction of \(s\). |
| Chord Fraction | c | Control Chord as a fraction of the lifting surface's root chord. |
| Control Chord | mm | Depth of the control surface, from the hinge to the trailing edge, at Span Start. |
| Hinge Sweep | ° | Sweep of the hinge line. 0° gives a hinge parallel to the Y axis. |
| Deflection Angle | ° | Deflection, from −90° to 90°. Positive moves the trailing edge down (−Z) on an unrotated surface. |
| Symmetry Mode | — | How the mirrored side deflects: **Auto (By Type)**, **Antisymmetric (Differential)**, **Symmetric**, or **None (Single)**. |

The editable values depend on **Sizing Driver Mode**. The other values are
calculated and shown dimmed.

| Sizing Driver Mode | Editable values | Kept when the lifting surface changes |
|---|---|---|
| Preserve Ratio (Eta & %c) | Eta Start, Eta End, Chord Fraction | Eta values and chord fraction. |
| Preserve Dimension (Span & Depth mm) | Span Start, Span End, Control Chord | Span positions and chord in mm. |
| Area + Chord Fraction Driven | Area, Span Start, Eta Start, Chord Fraction | Span positions in mm and chord fraction. Typing an Area moves Span End. |
| Area + Span Extent Driven | Area, Span Start, Span End, Eta Start, Eta End | Span positions in mm and chord fraction. Typing an Area changes Chord Fraction, between 0.02 and 0.95. |

The hinge line starts **Control Chord** ahead of the trailing edge at Span
Start and runs outboard at **Hinge Sweep**. Along the span, the hinge stays
between 5 % and 95 % of the local chord.

### Mirrored side and channels

In the 3D Viewer, the mirrored side of an **Aileron** or **Elevon** deflects
opposite to the modeled side; other types deflect the same way. **Symmetry
Mode** sets how the aerodynamic model deflects the mirrored side. With **Auto
(By Type)**, the Deflection Angle of an aileron or elevon and the aileron and
rudder commands of an analysis act opposite on the two sides; everything else
acts the same on both sides. **Antisymmetric (Differential)** and
**Symmetric** apply opposite or equal deflections to every command. **None
(Single)** leaves the mirrored side out.

The type also sets the control channels the aerodynamic analyses can deflect:

| Type | Channels |
|---|---|
| Aileron | Aileron |
| Flap | Flap |
| Elevator | Elevator |
| Rudder | Rudder |
| Elevon | Elevator, Aileron |
| Ruddervator | Elevator, Rudder |

See [Aerodynamics](aerodynamics.md) for the analyses.

## Default shapes

The **Model** group of the toolbar creates each part with a starting shape.
A new part is selected after it is created. Its name gets a number, such as
**Fuselage 2**, when the name is already taken.

### Add Fuselage

| Property | Value |
|---|---|
| Name | Fuselage |
| Attached to | Vehicle |
| Mass | 350 g |
| Segments | One segment, tag `main`, method Smooth |
| Sections | Three circles at X = 0, 140, and 600 mm, with diameters 25, 120, and 35 mm |

### Add Lifting Surface

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

### Add Control Surface

The button is enabled when a lifting surface is selected.

| Property | Value |
|---|---|
| Name | Control Surface |
| Lifting Surface | The selected lifting surface |
| Mass | 25 g |
| Type | Aileron |
| Sizing Driver Mode | Preserve Ratio (Eta & %c) |
| Eta Start, Eta End | 0.40, 0.85 |
| Chord Fraction | 0.25 |
| Hinge Sweep, Deflection Angle | 0° |
| Symmetry Mode | Auto (By Type) |

The add button in the lifting surface's **Control Surfaces** section creates
a similar aileron, named **Control 1**, **Control 2**, and so on.
