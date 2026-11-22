# Mass and balance

Setuav Studio adds up the masses of all components to find the total mass,
the center of gravity (CG), and the inertia tensor of the aircraft. This page
describes where the masses come from, how they are combined, and where the
results are shown and used.

## Where masses come from

Each component has one mass, entered or derived in grams. A component with no
mass, or a mass of zero, does not count.

| Component | Mass |
|---|---|
| Fuselage, Lifting Surface, Control Surface | **Mass** on the component's **Mass** tab. New parts start with 350 g, 250 g, and 25 g. |
| Propulsor | **Mass [Motor + Propeller]**: the motor **Mass** plus the propeller **Mass**. Picking a motor from the catalog fills in its mass. The catalog has no propeller masses, so enter the propeller's own. The sum is updated whenever a value changes, also when a formula changes it. |
| Battery | **Mass [Pack Mass]**: the **Pack Mass** field. When **Pack Mass** is empty, the mass follows from the chemistry, the series and parallel counts, and the cell capacity. It is updated whenever one of these changes, also through a formula. |
| Point Mass | **Mass** in the **General** section. New point masses start with 50 g. |

The **Mass** of a point mass accepts a formula, for example `=payload_mass`
for a constant named `payload_mass`. See
[Parametric model](../user-guide/parametric-model.md).

## Point Mass

A point mass stands for an item that has no geometry, such as a receiver,
a camera, or ballast.

Click **Add Point Mass** in the **Model** group of the toolbar. Studio adds a
point mass named **Point Mass** (then **Point Mass 2**, and so on) at the
vehicle origin and selects it.

| Tab | Field | Unit |
|---|---|---|
| **Parameters** | **Name** | — |
| **Parameters** | **Type** (read-only) | — |
| **Parameters** | **Mass** | mass, stored in g |
| **Transform** | **Attached to** | — |
| **Transform** | **Position** X, Y, Z | length, stored in mm |
| **Transform** | **Rotation** X, Y, Z | angle, stored in deg |

A point mass has no envelope, so its CG lies at its position unless you set a
local CG on the **Mass** tab.

Fields are shown in the display units chosen in **Edit → Settings**.

## The Mass tab

Every component has a **Mass** tab in the Properties panel:

| Section | Fields | Unit |
|---|---|---|
| **Mass** | **Component**, **Mass**, **Total with Subparts** (read-only, only for a component with control surfaces) | g |
| **Local Center of Gravity** | **Position** X, Y, Z | mm, in the component's own frame |
| **Inertia Tensor** | **Moments** IXX, IYY, IZZ; **Products** IXY, IXZ, IYZ | kg·m², about the component's CG |

The tab shows the values in use:

- **Local Center of Gravity** — per axis, the stored value if there is one,
  otherwise the centroid of the envelope, otherwise the origin.
- **Inertia Tensor** — per entry, the stored value if there is one, otherwise
  the envelope's inertia per unit mass times the component mass, otherwise
  zero.

The envelope of a fuselage, lifting surface, or control surface is computed
from its geometry, so its CG and inertia follow the shape. When you edit a
field on the **Mass** tab, Studio stores that one value on the component; it
replaces the envelope's value for that field only, and the other fields keep
following the shape. Every field accepts a formula, which is kept and
evaluated again when the constants it uses change.

The mass of a propulsor or a battery is derived from its parameters, so its
**Mass** field on this tab is read-only. Change the motor, propeller, or pack
values instead.

For a lifting surface with control surfaces, the fields hold the surface's own
values, and a read-only **Total with Subparts** row shows the mass of the
surface and its control surfaces together.

## Aggregation

Studio combines every component with a mass greater than zero. The results
are in the vehicle frame: mass in kg, CG in m, inertia in kg·m².

### Component CG

The CG of component \(i\) in the vehicle frame is

\[
\mathbf{r}_i = \mathbf{p}_i + R_i\,\mathbf{c}_i
\]

where \(\mathbf{p}_i\) is the position of the component origin, \(R_i\) its
rotation, and \(\mathbf{c}_i\) its local CG. Position and rotation follow the
chain of **Attached to** components up to the vehicle. The rotation uses the
yaw–pitch–roll order:

\[
R = R_z(\psi)\,R_y(\theta)\,R_x(\phi)
\]

A mirrored lifting surface stands for both halves. Its CG is placed on the
plane it is mirrored in: the XZ plane of the component it is attached to, or
of the vehicle, which is \(r_{i,y} = 0\) for a part on the center line. The
same holds for a control surface on a mirrored lifting surface, unless its
**Symmetry Mode** is **None (Single)**. The mass is not doubled, so the mass of
a mirrored surface is the mass of both halves. Its inertia tensor is taken
about that CG and covers both halves, so their distance from the mirror plane
adds to IXX and IZZ, and IXY and IYZ are zero.

### Total mass and CG

\[
M = \sum_i m_i
\qquad
\mathbf{r}_{cg} = \frac{1}{M} \sum_i m_i\,\mathbf{r}_i
\]

### Inertia

Each component's tensor is turned into the vehicle frame and moved to the
aircraft CG with the parallel-axis theorem:

\[
I_{cg} = \sum_i \left( R_i\,I_i\,R_i^{\mathsf{T}}
+ m_i \left( \lVert \mathbf{d}_i \rVert^2 E - \mathbf{d}_i\,\mathbf{d}_i^{\mathsf{T}} \right) \right),
\qquad
\mathbf{d}_i = \mathbf{r}_i - \mathbf{r}_{cg}
\]

where \(E\) is the identity matrix. A tensor is written with the products of
inertia as positive values:

\[
I = \begin{bmatrix}
I_{xx} & -I_{xy} & -I_{xz} \\
-I_{xy} & I_{yy} & -I_{yz} \\
-I_{xz} & -I_{yz} & I_{zz}
\end{bmatrix}
\]

The Vehicle node does not show the aircraft inertia tensor. Plugins read the
total mass, CG, and inertia with `StudioAPI.get_aircraft_mass_properties()`.

## Vehicle properties

Select **Vehicle** in the Project Explorer. The Properties panel shows:

| Property | Meaning |
|---|---|
| **Components** | The number of components in the project. |
| **Total Mass** | \(M\), in the mass display unit. |
| **CG X**, **CG Y**, **CG Z** | \(\mathbf{r}_{cg}\), in the length display unit. |

The values are read-only and update after every change to the project.

## CG marker in the 3D Viewer

The **Show Center of Gravity** button in the bar at the bottom of the 3D Viewer
shows or hides the **Center of Gravity** layer.

- The aircraft CG is drawn as a gold dot with a gold ring and red, green, and
  blue lines along X, Y, and Z. It is not drawn while the total mass is zero.
- While the **Mass** tab of a component is open, the component's CG is drawn
  as a smaller gold dot with colored axis lines. For a mirrored lifting
  surface, the marker sits on the symmetry plane.

## Use in analyses

- **Flight Performance** uses the total mass plus its **Payload** parameter
  (g), the mass carried in addition to the component masses. The analysis
  stops with an error when this sum is zero.
- The aerodynamic analyses take moments about the aircraft CG. When the total
  mass is zero, they use the quarter chord of the root of the largest lifting
  surface instead.

See [Flight Performance](../analyses/flight-performance.md),
[Aerodynamics](../analyses/aerodynamics.md), and [Placement and Attachment](placement.md).
