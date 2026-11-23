# Aerodynamics

The aerodynamics plugin computes the forces, moments, and stability
derivatives of the whole aircraft with
[AeroSandbox](https://github.com/peterdsharpe/AeroSandbox). It adds four
analyses to the **Analysis** group of the toolbar: Alpha Sweep, Beta Sweep,
Control Deflection, and Operating Point. It also adds a standalone 2D airfoil
tool under **Tools → Aerodynamics → Airfoil Analysis…**.

## Running an analysis

1. Add an analysis from the toolbar. The buttons are **Add Alpha Sweep (Polar)
   Analysis**, **Add Beta Sweep (Sideslip) Analysis**, **Add Control
   Deflection Analysis**, and **Add Aero Operating Point Analysis**. A project
   must be open.
2. Select the analysis under **Analyses** and set its parameters in the
   Properties panel.
3. Click **Run Analysis**. The analysis runs as a background task.
4. Read the scalar results in the **Results Summary** section of the
   Properties panel. **View Plot**, **View Table**, and **Export All** open or
   save the tables and plots.

See [Interface](../user-guide/interface.md) for the panels and the Result
area.

The project needs at least one lifting surface. Otherwise the analysis stops
with "Project contains no lifting surfaces."

The units in the tables below are the defaults. Values that carry a quantity,
such as angles, lengths, and forces, are shown in the units chosen in the unit
settings.

## Method

### Solver methods

Every analysis has a **Solver Method** parameter:

| Option | AeroSandbox model | Notes |
|---|---|---|
| AeroBuildup (Fast) | `AeroBuildup` | Default. Wing sections are evaluated with NeuralFoil; fuselages use Jorgensen's slender-body method. Wave drag is included. Reports the induced and profile drag breakdown and the Oswald efficiency. |
| Vortex Lattice (VLM) | `VortexLatticeMethod` | Linear, inviscid vortex lattice on the lifting surfaces. Uses **Spanwise Panels** and **Chordwise Panels**. Fuselages are not modeled. |
| Lifting Line (LLT) | `LiftingLine` | Lifting line with 2D section data. Uses **Spanwise Panels**. |

Panels use cosine spacing. AeroBuildup does not use the panel settings.

### Geometry conversion

The analysis converts the Studio vehicle into one AeroSandbox airplane. Only
lifting surfaces, their control surfaces, and fuselages are converted.
Propulsors, batteries, and point masses enter only through the center of
gravity. Positions are converted from millimeters to meters and placed with
the attachment transforms of the components. See
[Placement and Attachment](../modeling/placement.md) for the frames and the
Modeling pages for the component parameters.

**Lifting surfaces.** Each lifting surface with at least two sections becomes
an AeroSandbox wing. Each section keeps its leading-edge position, chord, and
airfoil. The section twist is the section pitch plus the pitch of the frame
the surface is attached to.

When **Symmetry / Mirror** is on, the surface becomes one symmetric wing if
its left half is the mirror image across the vehicle's center plane. A surface
is mirrored in the frame of the component it is attached to, so this holds
unless that component is rolled, yawed, or off the center plane; the surface's
own rotation, such as the roll of a V-tail, does not matter.

With AeroBuildup and Lifting Line, every control deflection is passed as a
symmetric part, \((\delta_r + \delta_l)/2\), and an antisymmetric part,
\((\delta_r - \delta_l)/2\), which together give both sides their own
deflection on one symmetric wing. With VLM the deflection is built into the
airfoils, so the wing stays symmetric only while both sides deflect alike.

Otherwise the two halves become two separate wings. They still count as one
surface for the reference values. AeroBuildup then treats each half as a wing
of half the aspect ratio and underestimates its lift, so the result adds a
**Note** naming the surface. VLM and Lifting Line are not affected.

**Airfoils.** A NACA 4-digit airfoil without airfoil shaping uses
AeroSandbox's own analytic NACA section. Every other airfoil uses the same
coordinates the geometry is built from. **TE Thickness**, **Thickness Scale**,
and **Camber Scale** are applied to those coordinates. See
[Airfoils](../modeling/airfoils.md).

**Control surfaces.** Control surfaces attached to a lifting surface are cut
into its sections. The wing is split at the span start and end of each control
surface. Each section gets the hinge position of the 3D model's hinge line at
its middle, as a fraction of the local chord limited to 0.05–0.95, so the
aerodynamic model follows **Control Chord** and **Hinge Sweep** as drawn. See
[Control Surface](../modeling/control-surface.md).

The **Deflection Angle** set on a control surface is always included. Each
analysis channel adds to it:

| Control surface type | Channels |
|---|---|
| Elevator | elevator |
| Aileron | aileron |
| Rudder | rudder |
| Flap | flap |
| Elevon | elevator + aileron |
| Ruddervator | elevator + rudder |

**Symmetry Mode** sets the deflection of the mirrored half:

| Symmetry Mode | Mirrored half |
|---|---|
| Auto (By Type) | Opposite for aileron and rudder commands and for the deflection of ailerons and elevons; same otherwise. |
| Antisymmetric (Differential) | Opposite. |
| Symmetric | Same. |
| None (Single) | No control surface on the mirrored half. |

With AeroBuildup and Lifting Line, deflections are passed to AeroSandbox as
control surfaces. With VLM, each deflection is applied to the section
airfoils.

**Fuselages.** Each fuselage segment becomes one AeroSandbox fuselage. Each
section becomes a superellipse cross-section with the section's width, height,
and orientation:

| Section profile | Cross-section |
|---|---|
| Circle | Circle of the same diameter. |
| Ellipse | Ellipse of the same width and height. |
| Rectangle | Superellipse; a larger corner radius gives a rounder shape. |
| Trapezoid | Nearly square superellipse; width is the larger of the top and bottom widths. |
| Triangle | Superellipse with a pointed shape inside the same width and height. |
| Polygon | Superellipse with a pointed shape inside the bounding box of the vertices. |

### Reference values

All coefficients, the drag breakdown, the static margin, the Reynolds number,
and [Flight Performance](flight-performance.md) use the reference values of
the **main wing**, the lifting surface with the largest planform area. Both
halves of a mirrored surface count, also when they become two AeroSandbox
wings.

| Value | Definition |
|---|---|
| \(S\) | Planform area of the main wing as AeroSandbox measures it: the summed area of the panels between its sections, both halves for a mirrored surface. |
| \(b\) | Span of the main wing from tip to tip, measured in the y–z plane and including the distance from the root to the center plane. |
| \(\bar c\) | Mean aerodynamic chord of the main wing, as AeroSandbox computes it. |

\[
C_L = \frac{L}{qS},\quad C_D = \frac{D}{qS},\quad C_Y = \frac{Y}{qS},\quad
C_l = \frac{l}{qSb},\quad C_m = \frac{m}{qS\bar c},\quad C_n = \frac{n}{qSb},\quad
q = \tfrac{1}{2}\rho V^2
\]

Lift, drag, and side force are in wind axes. Rolling, pitching, and yawing
moments are in body axes about the moment reference point.

The induced, profile, and wave drag coefficients use the same \(S\), so
\(C_{D_i} + C_{D_p} + C_{D_w} = C_D\).

### Moment reference point

Moments are taken about the aircraft center of gravity from the mass model,
the same CG shown when you select **Vehicle**. See
[Mass and Balance](../modeling/mass-balance.md). When the aircraft has no mass, the
reference point is the quarter chord of the main wing's first section, at
\(y = 0\).

### Atmosphere

Density, viscosity, and speed of sound come from AeroSandbox's `Atmosphere`
at the given **Altitude**. Its default model is a smooth fit to the
International Standard Atmosphere. There is no temperature offset. Altitudes
below 0 m are evaluated at 0 m.

### Assumptions and limits

- Steady flight with zero body rotation rates.
- No propeller slipstream, thrust, or other propulsion effects.
- Fuselage cross-sections are superellipses, so rectangles, trapezoids,
  triangles, and polygons are approximations.
- VLM is inviscid and ignores fuselages. AeroBuildup and Lifting Line take
  viscous effects from 2D section data.
- AeroBuildup is a fast semi-empirical buildup. Treat results near and past
  stall as estimates.
- An operating point where the solver fails is left out of the tables. If all
  points fail, the analysis stops with an error.

## Sweeps

The sweep analyses evaluate evenly spaced points from the minimum to the
maximum, both included. The number of points is

\[
n = \max\!\left(\operatorname{round}\!\left(\frac{\text{max} - \text{min}}{\text{step}}\right) + 1,\ 2\right)
\]

so the actual spacing can differ slightly from the step, and a step larger
than the range still evaluates both ends. The maximum must be
greater than the minimum, and the step and the airspeed must be positive.

## Alpha Sweep

Computes the polar of the aircraft over a range of angles of attack at
constant airspeed, altitude, and sideslip. Default name: **Alpha Sweep**.

### Parameters

| Parameter | Unit | Default | Description |
|---|---|---|---|
| AoA Min | ° | −5.0 | Starting angle of attack. Range −90 to 90. |
| AoA Max | ° | 15.0 | Ending angle of attack. Range −90 to 90. |
| AoA Step | ° | 1.0 | Angle of attack increment. Range 0.1 to 20. |
| Airspeed | m/s | 25.0 | Constant flight airspeed. Range 1 to 300. |
| Altitude | m | 0 | Flight altitude. Range −500 to 25000. |
| Sideslip (β) | ° | 0.0 | Constant sideslip angle. Range −45 to 45. |
| Solver Method | — | AeroBuildup (Fast) | AeroBuildup (Fast), Vortex Lattice (VLM), or Lifting Line (LLT). |
| Spanwise Panels | — | 12 | Panels along the span for VLM and LLT. Range 4 to 50. |
| Chordwise Panels | — | 8 | Panels along the chord for VLM. Range 2 to 30. |

### Table: Polar

| Output | Unit | Description |
|---|---|---|
| AoA (α) | ° | Angle of attack. |
| CL | — | Lift coefficient. |
| CD | — | Drag coefficient. |
| Cm | — | Pitching moment coefficient. |
| L/D | — | \(C_L / C_D\). |
| CDi | — | Induced drag coefficient. AeroBuildup only; 0 for VLM and LLT. |
| CDp | — | Profile drag coefficient. AeroBuildup only; 0 for VLM and LLT. |
| Lift | N | Lift force. |
| Drag | N | Drag force. |

### Plots

| Plot | X axis | Series |
|---|---|---|
| CL vs α | Angle of Attack α | CL |
| CD vs α | Angle of Attack α | Total CD, Induced CDi, Profile CDp |
| CL vs CD | Drag Coefficient CD | Polar (CL) |
| L/D vs α | Angle of Attack α | L/D |
| Cm vs α | Angle of Attack α | Cm |

### Results Summary

| Output | Unit | Description |
|---|---|---|
| Max Lift (CL,max) | — | Largest CL in the sweep. |
| AoA at CL,max | ° | Angle of attack of that point. |
| Min Drag (CD,min) | — | Smallest CD in the sweep. |
| Max Efficiency (L/D,max) | — | Largest L/D in the sweep. |
| AoA at (L/D)max | ° | Angle of attack of that point. |
| Oswald Efficiency (e) | — | AeroBuildup only. Mean over the sweep of the efficiency AeroSandbox reports for the main wing (see [Reference values](#reference-values)). |
| Neutral Point | m | See [Stability](#stability). Evaluated at α = 0°. |
| Static Margin | % | See [Stability](#stability). Evaluated at α = 0°. |

CL,max is the largest value in the sweep, not a predicted stall point. Widen
the range if it sits at **AoA Max**.

## Beta Sweep

Computes the lateral-directional response over a range of sideslip angles at
constant angle of attack, airspeed, and altitude. Default name: **Beta
Sweep**.

### Parameters

| Parameter | Unit | Default | Description |
|---|---|---|---|
| Sideslip Min | ° | −15.0 | Starting sideslip angle. Range −90 to 90. |
| Sideslip Max | ° | 15.0 | Ending sideslip angle. Range −90 to 90. |
| Sideslip Step | ° | 1.0 | Sideslip increment. Range 0.1 to 20. |
| Angle of Attack | ° | 2.0 | Constant angle of attack. Range −20 to 30. |
| Airspeed | m/s | 25.0 | Constant flight airspeed. Range 1 to 300. |
| Altitude | m | 0 | Flight altitude. Range −500 to 25000. |
| Solver Method | — | AeroBuildup (Fast) | AeroBuildup (Fast), Vortex Lattice (VLM), or Lifting Line (LLT). |
| Spanwise Panels | — | 12 | Panels along the span for VLM and LLT. Range 4 to 50. |
| Chordwise Panels | — | 8 | Panels along the chord for VLM. Range 2 to 30. |

### Table: Sideslip

| Output | Unit | Description |
|---|---|---|
| Sideslip (β) | ° | Sideslip angle. |
| CY | — | Side force coefficient. |
| Cl | — | Rolling moment coefficient. |
| Cn | — | Yawing moment coefficient. |
| Side Force | N | Side force. |

### Plots

| Plot | X axis | Series |
|---|---|---|
| CY vs β | Sideslip Angle β | CY |
| Cl vs β | Sideslip Angle β | Cl (Roll) |
| Cn vs β | Sideslip Angle β | Cn (Yaw) |

### Results Summary

| Output | Unit | Description |
|---|---|---|
| CY_beta (Sideforce slope) | 1/° | \(C_{Y_\beta}\). See [Stability](#stability). |
| Cl_beta (Dihedral Effect) | 1/° | \(C_{l_\beta}\). Negative is stable. |
| Cn_beta (Directional Stability) | 1/° | \(C_{n_\beta}\). Positive is stable. |

These derivatives are evaluated at **Angle of Attack** and β = 0°.
If the stability calculation fails, the summary shows **CY_beta
(estimated)**, **Cl_beta (estimated)**, and **Cn_beta (estimated)** instead.
They are the slopes between the first and last points of the sweep, for
example

\[
C_{n_\beta} \approx \frac{C_{n,\text{last}} - C_{n,\text{first}}}{\beta_\text{last} - \beta_\text{first}}
\]

## Control Deflection

Computes the response of the aircraft to one control surface over a range of
deflections at constant angle of attack, sideslip, airspeed, and altitude.
Default name: **Control Deflection**.

The deflection is added to the **Deflection Angle** of the chosen control
surface, and its **Symmetry Mode** sets the mirrored half (see [Geometry
conversion](#geometry-conversion)). A new analysis starts with the design's
first control surface. If the chosen surface is removed from the design, the
analysis stops until another one is chosen.

### Parameters

| Parameter | Unit | Default | Description |
|---|---|---|---|
| Control Surface | — | First control surface | One of the design's control surfaces, by name. |
| Deflection Min | ° | −20.0 | Starting deflection δ. Range −90 to 90. |
| Deflection Max | ° | 20.0 | Ending deflection δ. Range −90 to 90. |
| Deflection Step | ° | 2.0 | Deflection increment. Range 0.5 to 20. |
| Angle of Attack | ° | 2.0 | Constant angle of attack. Range −20 to 30. |
| Sideslip (β) | ° | 0.0 | Constant sideslip angle. Range −45 to 45. |
| Airspeed | m/s | 25.0 | Constant flight airspeed. Range 1 to 300. |
| Altitude | m | 0 | Flight altitude. Range −500 to 25000. |
| Solver Method | — | AeroBuildup (Fast) | AeroBuildup (Fast) or Vortex Lattice (VLM). |

Control Deflection has no panel parameters. VLM runs with 12 spanwise and 8
chordwise panels.

### Table: Response

| Output | Unit | Description |
|---|---|---|
| Deflection δ (*surface*) | ° | Deflection of the control surface, for example "Deflection δ (Elevator)". |
| CL | — | Lift coefficient. |
| CD | — | Drag coefficient. |
| Cm | — | Pitching moment coefficient. |
| Cl | — | Rolling moment coefficient. |
| Cn | — | Yawing moment coefficient. |

### Plots

| Plot | X axis | Series |
|---|---|---|
| Cm vs δ | Deflection Angle δ (*surface*) | Cm |
| CL vs δ | Deflection Angle δ (*surface*) | CL |
| Cl, Cn vs δ | Deflection Angle δ (*surface*) | Cl (Roll), Cn (Yaw) |

### Results Summary

| Output | Unit | Description |
|---|---|---|
| Control Surface | — | Name of the swept control surface. |
| Cm_delta (Pitch Authority) | 1/° | \(\partial C_m / \partial \delta\). |
| CL_delta (Lift Authority) | 1/° | \(\partial C_L / \partial \delta\). |
| Cl_delta (Roll Authority) | 1/° | \(\partial C_l / \partial \delta\). |
| Cn_delta (Yaw Authority) | 1/° | \(\partial C_n / \partial \delta\). |

Each derivative is the least-squares slope of a straight line through all
computed points of the sweep:

\[
\frac{\partial C}{\partial \delta} =
\frac{\sum_i (\delta_i - \bar\delta)(C_i - \bar C)}{\sum_i (\delta_i - \bar\delta)^2}
\]

For a nonlinear response, for example with large deflections, the slope
depends on the range. Narrow the range to get the slope near a given
deflection.

## Operating Point

Computes all forces, moments, and coefficients at one flight condition.
Default name: **Operating Point**.

### Parameters

| Parameter | Unit | Default | Description |
|---|---|---|---|
| Angle of Attack | ° | 2.0 | Flight angle of attack. Range −20 to 30. |
| Sideslip (β) | ° | 0.0 | Flight sideslip angle. Range −45 to 45. |
| Airspeed | m/s | 25.0 | Flight airspeed. Range 1 to 300. |
| Altitude | m | 0 | Flight altitude. Range −500 to 25000. |
| Solver Method | — | AeroBuildup (Fast) | AeroBuildup (Fast), Vortex Lattice (VLM), or Lifting Line (LLT). |
| Spanwise Panels | — | 12 | Panels along the span for VLM and LLT. Range 4 to 50. |
| Chordwise Panels | — | 8 | Panels along the chord for VLM. Range 2 to 30. |

### Table: State

| Output | Unit | Description |
|---|---|---|
| AoA (α) | ° | Angle of attack. |
| Sideslip (β) | ° | Sideslip angle. |
| Airspeed | m/s | Airspeed. |
| CL | — | Lift coefficient. |
| CD | — | Drag coefficient. |
| Cm | — | Pitching moment coefficient. |
| L/D | — | \(C_L / C_D\). |
| CY | — | Side force coefficient. |
| Cl | — | Rolling moment coefficient. |
| Cn | — | Yawing moment coefficient. |
| Lift | N | Lift force. |
| Drag | N | Drag force. |
| Side Force | N | Side force. |

Operating Point has no plots.

### Results Summary

| Output | Unit | Description |
|---|---|---|
| Lift Coefficient (CL) | — | Lift coefficient. |
| Drag Coefficient (CD) | — | Drag coefficient. |
| Pitching Moment (Cm) | — | Pitching moment coefficient. |
| L/D Ratio | — | \(C_L / C_D\). |
| Lift Force | N | Lift force. |
| Drag Force | N | Drag force. |
| Side Force | N | Side force. |
| Dynamic Pressure | Pa | \(q = \tfrac{1}{2}\rho V^2\). |
| Mach Number | — | \(M = V / a\), with \(a\) the speed of sound. |
| Reynolds Number | — | \(Re = \rho V \bar c / \mu\). |
| Neutral Point | m | See [Stability](#stability). |
| Static Margin | % | See [Stability](#stability). |

## Stability

The Alpha Sweep, Beta Sweep, and Operating Point summaries include stability
results. They come from AeroSandbox's stability derivative run of the chosen
solver method at a single condition: the **Angle of Attack** and **Sideslip
(β)** of an Operating Point, α = 0° and **Sideslip (β)** of an Alpha Sweep,
or **Angle of Attack** and β = 0° of a Beta Sweep.
AeroSandbox finds the derivatives by finite differences. This run uses the
analysis' own **Spanwise Panels**, **Chordwise Panels**, and spacing. If it
fails, the stability rows are left out of the summary.

AeroSandbox returns the angle derivatives per radian. Studio shows them per
degree:

\[
C_{Y_\beta}\,[1/°] = \frac{\pi}{180}\,\frac{\partial C_Y}{\partial \beta}\,[1/\text{rad}],
\quad\text{and likewise for } C_{l_\beta},\ C_{n_\beta}
\]

**Neutral point.** The x position of the neutral point, in meters, in the
vehicle frame. AeroSandbox computes it from the pitch and lift slopes about
the moment reference point \(x_\text{ref}\):

\[
x_{np} = x_\text{ref} - \frac{C_{m_\alpha}}{C_{L_\alpha}}\,\bar c
\]

where \(\bar c\) is the reference chord.

**Static margin.** The distance from the CG to the neutral point, in percent
of the same reference chord \(\bar c\):

\[
SM = \frac{x_{np} - x_{cg}}{\bar c} \times 100
\]

\(x_{cg}\) is the x position of the moment reference point. A positive static
margin means the neutral point lies behind the CG, which is statically stable
in pitch. When AeroSandbox returns no neutral point, Studio uses
\(SM = -C_{m_\alpha} / C_{L_\alpha} \times 100\) and
\(x_{np} = x_{cg} + (SM/100)\,\bar c\).

!!! warning "Define the masses first"
    When the aircraft has no mass, \(x_{cg}\) is the aerodynamic reference point
    (see [Moment reference point](#moment-reference-point)), and the static
    margin says nothing about the real aircraft. Enter the component masses
    before you read it.

## Airfoil Analysis

**Tools → Aerodynamics → Airfoil Analysis…** opens a window that computes the
2D polar of a single airfoil. It does not change the project. The analysis
uses NeuralFoil, a neural-network model of airfoil aerodynamics that is
installed with AeroSandbox.

1. Choose an airfoil in **Profile**, or click **Import .dat** to load a
   coordinate file (`.dat`, `.txt`, `.cor`, or `.af`).
2. Choose the **Model** and set the **Analysis Range**.
3. Click **Run Analysis**. The window cannot be closed while it runs.

### Inputs

| Parameter | Unit | Default | Description |
|---|---|---|---|
| Profile | — | NACA 2412 | A built-in airfoil or an imported one. See [Airfoils](../modeling/airfoils.md). |
| Model | — | large | NeuralFoil model size: small, medium, large, or xlarge. |
| α minimum | ° | −8 | First angle of attack. Range −30 to 30. |
| α maximum | ° | 18 | Last angle of attack. Must be greater than α minimum. Range −30 to 30. |
| Points | — | 27 | Number of evenly spaced angles, both ends included. Range 3 to 181. |
| Reynolds | — | 500000 | Chord Reynolds number. Range 1000 to 100000000. |
| Mach | — | 0.05 | Freestream Mach number. Range 0 to 0.95. |
| Ncrit | — | 9 | Boundary-layer transition amplification factor \(N_\text{crit}\). Range 1 to 14. |

### Outputs

The **Curves** tab shows four plots:

| Plot | X axis | Y axis |
|---|---|---|
| Lift Curve | α (°) | CL |
| Drag Polar | CD | CL |
| Pitching Moment | α (°) | CM |
| Aerodynamic Efficiency | α (°) | L/D |

The **Data** tab lists every point:

| Output | Unit | Description |
|---|---|---|
| α (°) | ° | Angle of attack. |
| CL | — | Section lift coefficient. |
| CD | — | Section drag coefficient. |
| CM | — | Section pitching moment coefficient about the quarter chord. |
| L/D | — | \(C_L / C_D\). |
| Top Xtr | — | Transition location on the upper surface, as a fraction of the chord. |
| Bottom Xtr | — | Transition location on the lower surface, as a fraction of the chord. |

The status line shows the airfoil, the model, and the number of points.
Results are kept in memory for the session. Running the same airfoil and
inputs again reuses them, and the status line then ends with "cached".
