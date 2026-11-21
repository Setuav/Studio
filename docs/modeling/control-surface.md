# Control Surface

A control surface is a movable part of a lifting surface: an aileron, flap,
elevator, rudder, elevon, or ruddervator. It is cut from its lifting surface
between two spanwise positions and hinged at a chordwise line. On a mirrored
surface it is built on both sides.

Select the control surface in the Project Explorer to edit it, or select its
row in the lifting surface's **Control Surfaces** section.

## General

| Parameter | Unit | Description |
|---|---|---|
| Name | — | Name of the component. |
| Type | — | Component type. Read-only. |
| Lifting Surface | — | The lifting surface the control surface belongs to. |

## Control Surfaces

Span positions are measured along Y from the root profile of the lifting
surface. The semi-span \(s\) is the Y distance from the root profile to the tip
profile of one side. Fractions of the span are "eta" values: \(\eta = y / s\).

| Parameter | Unit | Description |
|---|---|---|
| Type | — | **Aileron**, **Flap**, **Elevator**, **Rudder**, **Elevon**, or **Ruddervator**. |
| Sizing Driver Mode | — | Which values you edit and which ones are kept when the lifting surface changes. See below. |
| Area | dm² | Area of the control surface on one side, behind the hinge line the 3D model cuts, integrated along the span. |
| Area Ratio | % | Area as a share of one side of the lifting surface, the sum of its section trapezoids. Read-only. |
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

## Mirrored side and channels

**Symmetry Mode** sets how the mirrored side deflects, in the 3D Viewer and in
the aerodynamic model alike. With **Auto
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

See [Aerodynamics](../analyses/aerodynamics.md) for the analyses.

## Default shape

The **Model** group of the toolbar creates each part with a starting shape.
A new part is selected after it is created. Its name gets a number, such as
**Fuselage 2**, when the name is already taken.

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
