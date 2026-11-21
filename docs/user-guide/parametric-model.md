# Parametric model

A Setuav Studio project can hold named constants, formulas in numeric fields,
and constraints. Constants store design values in one place. Formulas tie a
field to constants and to other parts of the model. Constraints check design
rules and report violations in the status bar.

## Constants

### Add a constant

- Click **Add Constant** in the **Parameters** group of the toolbar, or
- right-click the **Constants** group in the Project Explorer and choose
  **Add Constant…**.

The new constant is named `const_1` (then `const_2`, and so on), has the
value `0`, and is selected so you can edit it in the Properties panel.

Constants with a number as their value are listed in the **Constants** group.
A constant whose value is a formula is listed in the **Equations** group.
Items with unsaved changes are shown in a highlight color.

### Constant properties

| Property | Meaning |
|---|---|
| **Name** | The name formulas use to refer to the constant. |
| **Value / Formula** | A number, or a formula that starts with `=`. |
| **Quantity** | The physical quantity, for example **Area (area)** or **Length / Dimensions (length)**. **Dimensionless (None)** means no unit. |
| **Active Unit** | The display unit of the quantity. Read-only. |
| **Resolved Value** | The evaluated value in the active unit, or `#ERR!` and the error message. Read-only. |

When a quantity is set, a number you type is read in the active display unit
and stored in the quantity's base unit (see [Units](#units)). Changing the
quantity does not convert the stored number.

A constant's formula can use other constants and the built-in functions and
constants. It cannot use component properties.

### Names

Formulas read names as identifiers. Use letters, digits, and underscores, and
start the name with a letter, for example `wing_area`. Avoid the names of the
built-in functions and constants listed under [Formula syntax](#formula-syntax).

To rename a constant, edit its **Name**. Formulas that use the old name are not
updated; they report an error until you change them.

### Delete a constant

Right-click the constant and choose **Delete**. If formulas use the constant,
the confirmation lists them first. After the delete, those formulas report an
error.

## Formulas in numeric fields

Most numeric fields in the Properties panel accept either a number or a
formula. This includes component parameters, the **Mass** of a point mass,
and the values in a lifting surface's **Planform** table.

### Enter a formula

1. Click the field.
2. Type `=` followed by the expression, for example `=wing_area / 2`.
3. Press **Enter** or leave the field.

While you type, Studio suggests constants, components, component parameters,
and functions that match the current word. Press **Tab** to insert the
highlighted suggestion, or **Ctrl+Space** to open the list.

When you leave the field, it shows the evaluated value in green italics. Hover
over the field to see the formula and the calculated value. Click the field
again to edit the formula.

To go back to a fixed value, type a plain number. The formula is removed.

A formula in a numeric field must give a finite number. When you type it, a
result outside the field's allowed range is clipped to the range. When a
constant later changes the result, the new value is stored as it is, and a
value the component cannot use, such as a battery Parallel Count of 0, is
reported as an error naming the field.

### Formula syntax

The expression engine is `asteval`, which evaluates a Python expression.

| Element | Available |
|---|---|
| Arithmetic | `+`, `-`, `*`, `/`, `**` (power), `//` (floor division), `%` (remainder), parentheses |
| Comparison and logic | `<`, `<=`, `>`, `>=`, `==`, `!=`, `and`, `or`, `not` |
| Constants | `pi`, `e`, `g` (9.80665) |
| Trigonometry | `sin`, `cos`, `tan`, `asin`, `acos`, `atan`, `atan2(y, x)` |
| Angle conversion | `radians(deg)`, `degrees(rad)` |
| Powers and logarithms | `sqrt`, `exp`, `log` (natural), `log10`, `pow(x, y)` |
| Rounding and limits | `abs`, `min`, `max`, `ceil`, `floor`, `round(x, n)` |

Use `**` for powers: `^` is not a power operator. Conditional expressions
(`a if c else b`) are not supported; use `min` and `max` to limit a value.
Trigonometric functions work in radians, so write `sin(radians(angle))` for an
angle in degrees.

### Names a formula can use

| Example | Meaning |
|---|---|
| `wing_area` | A project constant. A `-` in a constant name is read as `_`. |
| `lifting_surface` | A component, by its ID with `-` replaced by `_`. |
| `lifting_surface.span` | A property of a component. |
| `lifting_surface.profile_0.chord` | A property of a lifting surface profile station, by index. |
| `lifting_surface_mass` | The same property as `lifting_surface.mass`, written as one name. |
| `total_mass` | The sum of the **Mass** of all components, in grams. |
| `mtow` | The constant named `mtow` if there is one, otherwise `total_mass`. |

Every component exposes `mass`, its position `x`, `y`, `z`, its rotation
`roll`, `pitch`, `yaw`, its local center of gravity `cg_x`, `cg_y`, `cg_z`, and
its parameters. A lifting surface also exposes measured planform values such
as `planform_area`, `span`, `aspect_ratio`, `taper_ratio`, `root_chord`,
`tip_chord`, `average_chord`, and `mac`, with the same values as its
**Planform** table. A fuselage exposes `length`, `width`, and `height` and the
`width` and `height` of each section outline. The
[Formula Assistant](#formula-assistant) lists every name with its current
value.

### Units

Formulas work on stored values. Each quantity has a base unit for storage,
independent of the display units chosen in **Edit → Settings**:

| Quantity | Base unit |
|---|---|
| Length | mm |
| Area | dm² |
| Volume | dm³ |
| Mass | g |
| Angle | deg |
| Speed | m/s |
| Force | N |
| Power | W |
| Battery capacity | mAh |
| Energy | Wh |
| Moment of inertia | kg·m² |

A formula's result is stored in the field's base unit. For example, a
**Span** formula must give millimetres, so `=sqrt(wing_area *
wing_aspect_ratio) * 100` turns an area in dm² into a span in mm. Component
properties are also read in base units, for example `planform_area` in dm². The display unit only changes how a
value is shown and how a typed number is read.

### When formulas are evaluated

Studio evaluates every formula in the project:

- after each change to the project,
- when a project is opened,
- before a project is saved.

Formulas that depend on other formulas are evaluated again until the values
settle. A wing's planform formulas then reshape its sections, so the 3D Viewer
and the analyses use the new geometry.

### Errors and cycles

- A field whose formula fails shows `#REF!` and the formula in red. Hover over
  it to see the error. The field keeps its last valid value.
- If you enter a formula that cannot be evaluated, the field turns red and the
  status bar shows the error. The formula is not stored.
- Constants that depend on each other in a loop report
  `Circular dependency: a -> b -> a`. Constants that use them report
  `Depends on invalid parameter`.
- Component fields that depend on each other in a loop report
  `Circular dependency: expression value does not converge`, and they keep
  their values from before the change.

After each evaluation, the status bar shows the first error as
`Expression error at <location>: <message>`, followed by `(+N more)` when
there are further errors. The problems badge in the status bar counts errors and
warnings. Click it to open the **Problems** window, which lists each problem
with its **Severity**, **Source** (`Expression`, `Constraint`, or `Plugin`),
**Problem**, and **Message**.

## Formula Assistant

The Formula Assistant is a larger editor for one formula.

1. Click a numeric field, a constant's **Value / Formula**, or a constraint's
   **Expression**.
2. Click **Formula Assistant** in the **Parameters** group of the toolbar. The
   button is enabled only while such a field is active.
3. Edit the formula and click **OK** to put it into the field.

The assistant has these parts:

- **Expression** — the formula, with suggestions as you type, and buttons
  that insert operators.
- **Insert Variables & Functions** — three tabs. Double-click an entry to
  insert it at the cursor.
    - **Component Properties** lists each component and its properties with
      **Value** and **Expression Tag**. Profile stations and sections are
      grouped in folders.
    - **Project Constants** lists each constant with **Current Value** and
      **Unit**.
    - **Math Functions** lists the functions and constants with a short
      description.
- **Live Evaluation Result** — the result of the formula as you type, and the
  value of each name it uses. For a constraint it shows
  **Condition Passed (True)** or **Condition Violated (False)**.

For a numeric field, a formula entered without a leading `=` gets one when
you click **OK**.

## Constraints

A constraint is a named condition that should be true for the design, for
example `total_mass <= 2500`. Studio evaluates each enabled constraint and
reports the ones that are false.

### Add a constraint

- Click **Add Constraint** in the **Parameters** group of the toolbar, or
- right-click the **Constraints** group in the Project Explorer and choose
  **Add Constraint…**.

The new constraint is named `Constraint 1` (then `Constraint 2`, and so on)
and starts with the expression `total_mass > 0`. Replace the expression with your
own condition. The **Constraints** group appears once the project has a
constraint.

### Constraint properties

| Property | Meaning |
|---|---|
| **Name** | The name shown in the tree and in the Problems window. |
| **Expression** | A condition, such as `wing_aspect_ratio <= 10`. It uses the same names, operators, and functions as formulas. A leading `=` is optional. |
| **Severity** | **Warning**, **Error**, or **Info**. |
| **Enabled** | **Yes** or **No**. A disabled constraint is not checked. |
| **Status** | The result: **Passed**, **Violated**, **Error** with the message, or **Disabled**. Read-only. |
| **Description** | Free text. |

Right-click a constraint to **Toggle Enabled** or **Delete** it.

### How constraints are reported

Studio checks the constraints after each change to the project and when a
project opens. An enabled constraint fails when its expression is false or
cannot be evaluated. Each failed constraint adds a problem with the source
`Constraint` and the message `Constraint violated: <expression>`. A constraint
with the severity **Error** counts as an error in the status bar badge; one
with **Warning** or **Info** counts as a warning.

## Worked example

This example sizes a lifting surface from its wing area and aspect ratio.
It uses a new lifting surface, which is mirrored and starts with a 1000 mm
span, a 220 mm root chord, and a 110 mm tip chord. The values below assume the
**Metric (SI Standard)** unit preset.

1. Click **Add Constant**. In the Properties panel, set **Name** to
   `wing_area`, **Quantity** to **Area (area)**, and **Value / Formula** to
   `30`. **Resolved Value** shows `30 dm²`.
2. Click **Add Constant** again. Set **Name** to `wing_aspect_ratio` and
   **Value / Formula** to `8`. Leave **Quantity** at
   **Dimensionless (None)**.
3. Select the lifting surface. In the **Planform** table on the
   **Parameters** tab, a new wing has **Span**, **Root Chord**, and
   **Tip Chord** as drivers.
4. In the **Driver** column, clear **Span**, **Root Chord**, and
   **Tip Chord**. Then check **Planform Area**, **Aspect Ratio**, and
   **Taper Ratio**. The table allows three drivers at a time.
5. In the **Value** column, enter `=wing_area` for **Planform Area** and
   `=wing_aspect_ratio` for **Aspect Ratio**. **Taper Ratio** keeps its
   current value, 0.5.

The wing now has:

| Value | Result |
|---|---|
| Planform Area | 30 dm² |
| Aspect Ratio | 8 |
| Span | 1549.2 mm |
| Root Chord | 258.2 mm |
| Tip Chord | 129.1 mm |

The span follows from \( b = \sqrt{S \cdot AR} = \sqrt{30 \cdot 8}\,\mathrm{dm}
\approx 15.49\,\mathrm{dm} \).

Select `wing_area` and change its value to `36`. Studio evaluates the formulas
again: the span becomes 1697.1 mm, the root chord 282.8 mm, and the tip chord
141.4 mm, while the aspect ratio stays 8.

To check a limit, click **Add Constraint**, set **Expression** to
`wing_area >= 25 and wing_aspect_ratio <= 10`, and set **Severity** to
**Error**. While both conditions hold, **Status** shows **Passed**.

Clearing a driver removes its formula. For more about the planform drivers,
see [Geometry](../reference/geometry.md). For the toolbar and panels, see
[Interface](interface.md).
