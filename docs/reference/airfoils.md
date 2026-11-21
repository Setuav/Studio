# Airfoils

Every profile station of a lifting surface has an airfoil. An airfoil is either
a NACA 4- or 5-digit code, which Studio generates from the digits, or a named
set of coordinates from the bundled library or from a `.dat` file you import.
This page covers the library, the NACA generator, importing your own
coordinates, and how an airfoil is assigned to a station. The lifting surface
itself is described in [Geometry](geometry.md).

## Choosing an airfoil

1. Select a lifting surface and open its **Parameters** tab.
2. Select a section in the **Sections** table.
3. In **Section Profiles**, click **Choose** next to **Root Airfoil** or **Tip
   Airfoil**. The **Airfoil Selector & Manager** dialog opens.
4. Pick an airfoil in one of the three tabs: **Preset Library**, **NACA
   Generator**, or **Import File (.dat)**.
5. Click **Apply to Section** to set it on that one station, or **Apply to All
   Stations** to set it on the root and on every section tip.

The root of a section is the tip of the section before it, so one station is
shared by two neighbouring sections. Changing the tip airfoil of section 1 also
changes the root airfoil of section 2.

The dialog opens on the airfoil the station already has: a library airfoil is
selected in **Preset Library**, any other NACA code is shown in **NACA
Generator**, and imported coordinates are shown in **Import File (.dat)**.

The right side of the dialog draws the airfoil and lists **Airfoil
Properties**:

| Property | Unit | Description |
|---|---|---|
| Max Thickness | % chord | Largest distance between the upper and lower surface, and where along the chord it occurs. |
| Max Camber | % chord | Largest distance of the mean line from the chord line, and where it occurs. Shown without a position for a symmetric airfoil. |
| Trailing Edge Gap | % chord | Distance between the upper and the lower trailing edge point. |
| Points | — | Number of coordinate points. |

Thickness and camber are measured at 49 stations, every 2 % of the chord.

### What the project stores

A NACA airfoil is stored as its code, for example `2412`. The coordinates are
generated again from the code whenever they are needed. A library or imported
airfoil is stored as its name and its coordinate points, normalized to a unit
chord. The project file therefore keeps working without the original `.dat`
file.

The airfoil name shown in the editor is the library name (for example **NACA
2412** or **Clark-Y**), `NACA` followed by the code for other NACA airfoils, or
the name read from the imported file.

## Bundled library

The **Preset Library** tab lists 18 airfoils. Use the **Category** box to
filter them. Nine are read from the coordinate files in the application, the
other nine are NACA sections generated from their codes.

The thickness and camber values below are the ones the dialog measures.

### Coordinate files

| Name | File | Category | Thickness / camber | Typical use |
|---|---|---|---|---|
| Clark-Y | `clarky.dat` | General Aviation | 11.7 % / 3.4 % | Classic flat-bottomed general-purpose section. |
| Selig S1223 | `s1223.dat` | High Lift UAV | 12.1 % / 8.7 % | High-lift section for low Reynolds numbers. |
| Selig S8036 | `s8036.dat` | High Lift UAV | 16.0 % / 1.9 % | Thick section for low Reynolds numbers. |
| Selig S9027 | `s9027.dat` | High Lift UAV | 8.0 % / 0 % | Thin symmetric section for low Reynolds numbers. |
| Eppler E423 | `e423.dat` | High Lift UAV | 12.5 % / 10.0 % | High-lift section for low Reynolds numbers. |
| Wortmann FX 63-137 | `fx63137.dat` | High Lift UAV | 13.7 % / 6.0 % | High-lift section for slow, low-Reynolds-number flight. |
| Drela AG24 | `ag24.dat` | High Lift UAV | 8.4 % / 2.2 % | Thin section designed by Mark Drela for model gliders. |
| MH 45 | `mh45.dat` | Tailless & Flying Wing | 9.8 % / 1.7 % | Reflexed section for tailless aircraft. |
| MH 60 | `mh60.dat` | Tailless & Flying Wing | 10.1 % / 1.8 % | Reflexed section for tailless aircraft. |

### NACA presets

| Name | Category |
|---|---|
| NACA 2412, NACA 2414, NACA 4412, NACA 4415 | General Aviation |
| NACA 23012 | Tailless & Flying Wing |
| NACA 0006, NACA 0009, NACA 0012, NACA 0015 | Symmetric & Tail |

The NACA presets are the same airfoils the **NACA Generator** makes from these
codes. They are stored as codes, not as coordinates.

## NACA generator

The **NACA Generator** tab builds an airfoil from its digits.

1. Under **NACA Series**, choose **4-Digit** or **5-Digit**.
2. Type the digits in **Airfoil Code**, for example `4415` or `23012`.

Type digits only. Spaces before and after the code are ignored, but `NACA
4415` or `4415a` is not accepted. While the code is not valid, the line under
the code explains why and the dialog keeps the last valid airfoil. Switching
the series replaces a code of the wrong length with `2412` or `23012`.

### Accepted codes

| Series | Digits | Rules |
|---|---|---|
| 4-digit | `MPTT` | Exactly four digits. A cambered section (M > 0) needs a camber position P from 1 to 9. With M = 0 the section is symmetric and P is not used. |
| 5-digit | `LPQTT` | Exactly five digits. Q = 0 gives the standard mean line and needs P from 1 to 5. Q = 1 gives the reflexed mean line and needs P from 2 to 5. Other Q values are rejected. |

For example, `2012` is rejected because it has 2 % camber but camber position
0, and `23212` is rejected because its reflex digit is 2.

### Points

The generator places 65 stations along the chord with cosine spacing, so
points are closer together at the leading and trailing edges:

\[
x_i = \tfrac{1}{2}\left(1 - \cos\frac{\pi i}{64}\right), \qquad i = 0, 1, \dots, 64
\]

The upper surface uses all 65 stations and the lower surface the 64 stations
after the leading edge, so a NACA airfoil has 129 points. Like every other
airfoil, the loop starts at the upper trailing edge, runs over the leading
edge, and ends at the lower trailing edge. Coordinates are fractions of the
chord, with the leading edge at \(x = 0\) and the trailing edge at \(x = 1\).

### Thickness

Both series use the standard NACA thickness distribution, where \(t\) is the
last two digits divided by 100:

\[
y_t = 5t\left(0.2969\sqrt{x} - 0.1260\,x - 0.3516\,x^2 + 0.2843\,x^3 - 0.1015\,x^4\right)
\]

The trailing edge is not closed. At \(x = 1\) the half thickness is
\(0.0105\,t\), so the trailing edge is \(0.021\,t\) thick, about 0.25 % of the
chord for a 12 % section. To change the trailing edge of a whole surface, use
**TE Thickness** under [Airfoil Shaping](#airfoil-shaping).

### 4-digit mean line

With \(m\) the first digit divided by 100 and \(p\) the second digit divided by
10:

\[
y_c =
\begin{cases}
\dfrac{m}{p^2}\left(2px - x^2\right), & x < p \\[2ex]
\dfrac{m}{(1-p)^2}\left(1 - 2p + 2px - x^2\right), & x \ge p
\end{cases}
\qquad
\frac{dy_c}{dx} =
\begin{cases}
\dfrac{2m}{p^2}\left(p - x\right), & x < p \\[2ex]
\dfrac{2m}{(1-p)^2}\left(p - x\right), & x \ge p
\end{cases}
\]

For `2412` this gives 2 % camber at 40 % chord and 12 % thickness. With
\(m = 0\) the mean line is the chord line.

### 5-digit mean line

The first digit \(L\) sets the design lift coefficient \(C_{l,d} = 0.15\,L\).
The second digit \(P\) selects the tabulated mean line, with the maximum camber
near \(5P\) % of the chord. The third digit selects the standard (0) or
reflexed (1) mean line. The tabulated constants are for \(C_{l,d} = 0.3\);
Studio scales \(k_1\) by \(C_{l,d} / 0.3\).

| P | Standard \(r\) | Standard \(k_1\) | Reflexed \(r\) | Reflexed \(k_1\) | Reflexed \(k_2/k_1\) |
|---|---|---|---|---|---|
| 1 | 0.0580 | 361.4 | — | — | — |
| 2 | 0.1260 | 51.64 | 0.1300 | 51.99 | 0.000764 |
| 3 | 0.2025 | 15.957 | 0.2170 | 15.793 | 0.00677 |
| 4 | 0.2900 | 6.643 | 0.3180 | 6.520 | 0.0303 |
| 5 | 0.3910 | 3.230 | 0.4410 | 3.191 | 0.1355 |

Standard mean line:

\[
y_c =
\begin{cases}
\dfrac{k_1}{6}\left(x^3 - 3rx^2 + r^2(3 - r)\,x\right), & x < r \\[2ex]
\dfrac{k_1 r^3}{6}\left(1 - x\right), & x \ge r
\end{cases}
\]

Reflexed mean line:

\[
y_c =
\begin{cases}
\dfrac{k_1}{6}\left[(x - r)^3 - \dfrac{k_2}{k_1}(1 - r)^3 x - r^3 x + r^3\right], & x < r \\[2ex]
\dfrac{k_1}{6}\left[\dfrac{k_2}{k_1}(x - r)^3 - \dfrac{k_2}{k_1}(1 - r)^3 x - r^3 x + r^3\right], & x \ge r
\end{cases}
\]

For `23012` this gives a maximum camber of 1.84 % at 15 % chord.

### Upper and lower surface

For both series, the thickness is laid off normal to the mean line, with
\(\theta = \arctan(dy_c/dx)\):

\[
x_u = x - y_t \sin\theta, \quad z_u = y_c + y_t \cos\theta, \qquad
x_l = x + y_t \sin\theta, \quad z_l = y_c - y_t \cos\theta
\]

## Importing a coordinate file

1. Open the **Airfoil Selector & Manager** dialog from a station's **Choose**
   button.
2. Select the **Import File (.dat)** tab and click **Browse .DAT File...**.
3. Pick the file. The file dialog lists `*.dat`, `*.txt`, `*.cor`, and `*.af`
   files.
4. Check the shape and the coordinate table, then click **Apply to Section** or
   **Apply to All Stations**.

The airfoil is saved in the project, not in the library. To use it on another
surface, import the file there too.

### Accepted formats

Both common coordinate formats are read:

- **Selig**: the first line is the name. The points follow as one loop from the
  trailing edge over the upper surface to the leading edge and back along the
  lower surface to the trailing edge.
- **Lednicer**: the first line is the name. The second line holds the number of
  upper and lower surface points, for example `61. 61.`. The upper surface
  follows from the leading edge to the trailing edge, then the lower surface
  from the leading edge to the trailing edge.

A file is read as Lednicer when its second line has exactly two numbers, at
least one of them larger than 5 and at least one a whole number. Values may be
separated by spaces, tabs, or commas. Lines that are not a pair of numbers, such
as extra description lines, are skipped.

The first line becomes the airfoil name. The coordinates are shifted and scaled
so the chord runs from \(x = 0\) to \(x = 1\), with the leading edge, the point
with the smallest \(x\), at \(x = 0\). The coordinates are not rotated.

The import stops with an **Airfoil Import** message when the file is empty, has
fewer than 3 coordinate points, or has no upper or lower surface points.

## Airfoil Shaping

The **Airfoil Shaping** section of the lifting surface editor changes every
airfoil of that surface at once, in the 3D model and in the aerodynamic model.
The stored airfoils do not change.

| Parameter | Unit | Description |
|---|---|---|
| TE Thickness | fraction of chord | Thickness added at the trailing edge, from 0 to 0.05. The added thickness grows linearly from 0 at the leading edge. |
| Thickness Scale | × | Multiplier on the airfoil thickness, from 0.1 to 3.0. |
| Camber Scale | × | Multiplier on the mean line, from 0 to 3.0. 0 makes the airfoils symmetric. |

**Section Alignment** in the same section is described in
[Geometry](geometry.md#airfoil-shaping).

## Airfoil Analysis tool

**Tools → Aerodynamics → Airfoil Analysis…** analyzes one airfoil on its own
with NeuralFoil. Its **Profile** list holds the preset library, and **Import
.dat** adds a coordinate file in the formats above. It does not change the
project. See [Aerodynamics](aerodynamics.md) for the analysis settings and
results.
