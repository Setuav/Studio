# Propulsion

The Electrical Propulsion plugin adds two components, the **Propulsor** and the
**Battery**, and three analyses of the powertrain they form: **Throttle
Sweep**, **Airspeed Sweep**, and **Operating Point**. The analyses use the
[PyThrust](https://setuav.github.io/PyThrust/) package to solve the motors,
propellers, and battery packs together. The
[Flight Performance](flight-performance.md) analysis uses the same powertrain.

## Propulsor

A propulsor is one electric motor and the propeller on its shaft. To add one,
click **Add Propulsor** in the toolbar. A new propulsor has no motor and no
propeller. You pick both from the PyThrust catalogs.

In the Project Explorer the propulsor has two nodes below it, **Motor** and
**Propeller**. Each opens its own page in the Properties panel. See
[Interface](../user-guide/interface.md) for the panels.

Once a propeller is picked, the 3D Viewer draws the propeller disk as a ring at
the propulsor's position. The ring has the propeller's diameter, and its axis is
the propulsor's local x axis.

### General

Select the propulsor itself to see its **General** section.

| Parameter | Unit | Default | Description |
|---|---|---|---|
| Name | — | Propulsor | Name of the component. Editable. |
| Type | — | — | Component type. Read-only. |
| Mass [Motor + Propeller] | g | 0 | Sum of the motor **Mass** and the propeller **Mass**. Read-only. This is the component mass used in [Mass and Balance](mass-balance.md). |
| Motor | — | Not selected | Model name of the picked motor. Read-only. |
| Propeller | — | Not selected | Catalog entry of the picked propeller. Read-only. |

### Motor

Select the **Motor** node, then click **Choose Motor from Catalog…**. Pick a
motor and click **Apply to Component**, or double-click the row. All values
come from the catalog entry and are read-only, except **Mass**. Until you pick
a motor the fields are empty and **Model** shows "Not selected: pick one from
the catalog".

| Parameter | Unit | Default | Description |
|---|---|---|---|
| Manufacturer | — | — | Motor manufacturer. |
| Model | — | — | Motor model name. |
| Velocity Constant (KV) | RPM/V | — | Motor velocity constant in revolutions per minute per volt. |
| Winding Resistance (Rm) | Ω | — | Phase-to-phase winding resistance. |
| No-Load Current (I0) | A | — | No-load current at the catalog's test voltage. |
| Max Current | A | — | Maximum continuous motor current. A point above it is not feasible. |
| Mass | g | — | Motor mass from the catalog. Editable after a motor is picked. |

### Propeller

Select the **Propeller** node, then click **Choose Propeller from Catalog…**.
Pick a propeller and click **Apply to Component**, or double-click the row. The
catalog has no propeller masses, so enter **Mass** yourself. It is the only
editable field and becomes editable after a propeller is picked.

| Parameter | Unit | Default | Description |
|---|---|---|---|
| Catalog Entry | — | — | PyThrust catalog ID of the propeller's thrust and power data, for example `APC_10x10`. |
| Diameter | mm | — | Propeller diameter from the catalog. |
| Pitch | mm | — | Propeller pitch from the catalog. |
| Blades | — | — | Number of blades from the catalog. |
| Mass | g | — | Propeller mass. Enter it by hand. |

Picking a new motor or propeller replaces all catalog values of that part. You
can undo a pick.

## Battery

A battery is a pack of cells of one chemistry, with **Series Count (S)** cells
in series and **Parallel Count (P)** cells in parallel. To add one, click
**Add Battery** in the toolbar. A new battery is a 6S1P LiPo pack of 5000 mAh
cells.

The chemistry derives the cell properties from the cell capacity. You can
override each derived value. The component mass always equals **Pack Mass**.

### General

| Parameter | Unit | Default | Description |
|---|---|---|---|
| Name | — | Battery | Name of the component. Editable. |
| Type | — | — | Component type. Read-only. |
| Mass [Pack Mass] | g | derived | Equal to **Pack Mass**. Read-only. |
| Manufacturer | — | empty | Free text. Not used in analyses. |
| Model | — | empty | Free text. Not used in analyses. |

### Pack Configuration

| Parameter | Unit | Default | Description |
|---|---|---|---|
| Chemistry | — | LiPo | Cell chemistry: **LiPo** or **Li-Ion**. It selects the discharge curves and the scaling rules. Changing it clears all overrides in **Cell Properties**. |
| Series Count (S) | S | 6 | Cells in series. Sets the pack voltage. Whole number, at least 1. |
| Parallel Count (P) | P | 1 | Cells in parallel. Sets the pack capacity. Whole number, at least 1. |
| Cell Capacity | mAh | 5000 | Rated capacity of one cell. Range 100 to 200000. |

### Cell Properties

Each row has a check box on its label. Unchecked, the field shows the value
derived from the chemistry and is read-only. Check the box to override it; the
override starts from the derived value. Uncheck it to return to the derived
value.

| Parameter | Unit | Default | Description |
|---|---|---|---|
| Charge Voltage | V | 4.20 (LiPo and Li-Ion) | Cell voltage at full charge. Allowed from the cell's nominal voltage to its maximum charge voltage: 3.70 to 4.35 V for LiPo, 3.60 to 4.20 V for Li-Ion. A lower charge voltage starts the discharge further down the same open-circuit voltage curve. |
| Cell Resistance (50% DoD) | Ω | derived | Cell DC resistance at half the usable depth of discharge. Derived as a specific resistance divided by the cell capacity in Ah: 25.0 mΩ·Ah for LiPo, 55.2 mΩ·Ah for Li-Ion. Override range 0.00001 to 10 Ω. |
| Continuous C-Rate | C | 15.0 (LiPo), 10.7 (Li-Ion) | Continuous discharge rate. Override range 0.1 to 500. |
| Pack Mass | g | derived | Pack mass with wiring and packaging. Derived as \(S \cdot P \cdot a \cdot C^{\,b}\), with the cell capacity \(C\) in Ah. LiPo: \(a = 28.76\) g, \(b = 0.859\). Li-Ion: \(a = 16.67\) g, \(b = 1\); this is the cell mass alone, without pack hardware. Override range 1 to 1000000 g. |

### Pack Performance

These values are read-only and follow from the fields above.

| Parameter | Unit | Description |
|---|---|---|
| Pack Capacity | mAh | Cell Capacity × P. |
| Nominal Voltage | V | Cell nominal voltage × S. The cell nominal voltage is 3.7 V for LiPo and 3.6 V for Li-Ion. |
| Full-Charge Voltage | V | Charge Voltage × S. |
| Cut-Off Voltage | V | Cell cut-off voltage × S. The cell cut-off voltage is 3.0 V for LiPo and 2.5 V for Li-Ion. |
| Internal Resistance (50% DoD) | Ω | Cell Resistance × S / P. |
| Max Continuous Current | A | Continuous C-Rate × cell capacity in Ah × P. |
| Energy | Wh | Open-circuit voltage averaged over the usable discharge × Pack Capacity × S. |

### Chemistry data

Each chemistry has a profile file in the plugin. It holds the open-circuit
voltage and the resistance shape against depth of discharge, and the rules
above for resistance, C-rate, and mass.

- **LiPo**: open-circuit voltage and resistance shape from the SINTEF discharge
  rate test of a Melasta SLPBA842124HV LCO pouch cell (Clark, Guldahl,
  Tolchard, 2025, [doi:10.5281/zenodo.15077312](https://doi.org/10.5281/zenodo.15077312),
  CC BY 4.0). Specific resistance and C-rate come from the same cell. The pack
  mass rule is fitted to 26 Tattu LCO packs of 3.7 Ah to 40 Ah, with an rms
  error of 6 %.
- **Li-Ion**: open-circuit voltage and resistance from the Molicel
  INR-21700-P42A fit in R. A. McDonald's
  [bat-perf](https://github.com/ramcdona/bat-perf). Specific resistance, C-rate,
  and mass come from the same cell and its datasheet (4.2 Ah, 45 A, 70 g).

## Component Database

The motor and propeller catalogs ship with the PyThrust package. Open them in
two ways:

- **Tools → Electrical Propulsion → Component Database…** opens the
  **Component Database Catalog** window with a **Motors** tab and a
  **Propellers** tab, for browsing.
- **Choose Motor from Catalog…** and **Choose Propeller from Catalog…** on the
  Motor and Propeller pages open the same list for one part. Use **Apply to
  Component** or double-click a row to pick it.

Click a column header to sort. Type in the search box to filter; every word
you type must appear in the manufacturer, name, or ID.

| Catalog | Columns | Filters |
|---|---|---|
| Motors | Manufacturer, Model / Name, KV (RPM/V), Max Current (A), Max Power (W), Mass (g), Rm (Ω) | Search box and a manufacturer list (**All Manufacturers**). The list shows at most 500 matches. |
| Propellers | Manufacturer, Model, Diameter (in), Diameter (mm), Pitch (in), Blades | Search box. |

PyThrust 0.4.1, the version Studio uses, contains 7,880 motors from 129
manufacturers and 441 APC propellers. Each propeller entry has a table of
thrust and power coefficients against RPM and advance ratio. There is no
battery catalog; batteries are defined by their chemistry.

To use another dataset, set the `PYTHRUST_DATA_DIR` environment variable to a
folder with `motors` and `propellers` subfolders in the PyThrust format.

## Powertrain model

The propulsion analyses take every propulsor and every battery of the project
and build one powertrain:

- All battery packs connect in parallel to one bus. Packs that cannot share a
  bus, for example packs with different series counts, stop the analysis with
  an error.
- All propulsors draw from that bus and run at the same throttle.
- The bus voltage sags with the total current through the packs' resistance.

An analysis needs at least one battery and one propulsor, and every propulsor
needs a motor and a propeller.

Studio passes these inputs to PyThrust:

- **Motor**: Velocity Constant (KV), Winding Resistance (Rm), No-Load Current
  (I0), and Max Current. PyThrust uses them in a DC motor model: back-EMF from
  KV, a constant winding resistance, and a constant no-load current. The
  applied motor voltage is the throttle times the battery voltage. Studio sets
  no speed controller resistance or current limit.
- **Propeller**: Diameter, Pitch, Blades, and the catalog entry's thrust and
  power coefficient table, looked up by RPM and advance ratio
  \(J = V / (n D)\), where \(V\) is the airspeed, \(n\) the shaft speed in
  revolutions per second, and \(D\) the diameter.
- **Battery**: each pack as an equivalent-circuit model driven by its
  open-circuit voltage and resistance curves over the depth of discharge, with
  its capacity, charge voltage, cut-off voltage, and continuous current limit,
  evaluated at the analysis' **Battery State of Charge**.

PyThrust then solves for the RPM at which the motor, driven by the throttled
bus voltage, delivers the torque the propeller absorbs. See the [PyThrust documentation](https://setuav.github.io/PyThrust/)
for the models.

### Feasible points

A point is feasible when PyThrust finds an equilibrium RPM and no limit is
exceeded: the motor current stays at or below **Max Current**, each battery
cell stays within its continuous current and above its cut-off voltage, and
the propeller coefficients are valid. At a low throttle and a high airspeed,
for example, the propeller has no operating point and the point is not
feasible.

### Totals and efficiencies

With several propulsors, thrust, power, and current are totals. RPM and advance
ratio are the mean over the propulsors. The efficiencies are ratios of summed
powers:

- **Propeller Efficiency** = thrust × airspeed / shaft power
- **Motor Efficiency** = shaft power / motor electrical power
- **System Efficiency** = thrust × airspeed / battery power

Propeller and system efficiency are 0 at zero airspeed, where the thrust does no work.

## Analyses

Add an analysis with **Add Throttle Sweep Analysis**, **Add Airspeed Sweep
Analysis**, or **Add Propulsion Operating Point Analysis** in the toolbar.
Then set its parameters and click **Run Analysis**.

All three analyses share these parameters:

| Parameter | Unit | Default | Description |
|---|---|---|---|
| Altitude | m | 0 | Flight altitude. Range −500 to 25000. |
| Temperature | °C | 15 | Ambient air temperature. Range −50 to 60. The air density follows from the ISA pressure at **Altitude** and this temperature. |
| Battery State of Charge | % | 100 | State of charge every pack is evaluated at. Range 1 to 100. |

### Throttle Sweep

Solves the powertrain at one airspeed for a range of throttle settings.

| Parameter | Unit | Default | Description |
|---|---|---|---|
| Airspeed | m/s | 15 | Constant airspeed. Range 0 to 200. |
| Throttle Min | % | 10 | First throttle. Range 1 to 100. |
| Throttle Max | % | 100 | Last throttle. Range 1 to 100. Must not be below **Throttle Min**. |
| Throttle Step | % | 5 | Throttle increment. Range 1 to 50. |

### Airspeed Sweep

Solves the powertrain at one throttle for a range of airspeeds.

| Parameter | Unit | Default | Description |
|---|---|---|---|
| Airspeed Min | m/s | 0 | First airspeed. Range 0 to 200. |
| Airspeed Max | m/s | 35 | Last airspeed. Range 0.5 to 200. Must not be below **Airspeed Min**. |
| Airspeed Step | m/s | 1 | Airspeed increment. Range 0.1 to 20. |
| Throttle | % | 100 | Constant throttle. Range 1 to 100. |

### Operating Point

Solves the powertrain at one airspeed and one throttle.

| Parameter | Unit | Default | Description |
|---|---|---|---|
| Airspeed | m/s | 18 | Airspeed. Range 0 to 200. |
| Throttle | % | 75 | Throttle. Range 1 to 100. |

The sweeps run from the minimum to the maximum in step increments. The maximum
is included when it falls on a step.

## Results

### Performance table

Each analysis produces one table, **Performance**, with one row per point.

| Column | Unit | Description |
|---|---|---|
| Throttle or Airspeed | % or m/s | Swept value: **Throttle** for Throttle Sweep, **Airspeed** for Airspeed Sweep and Operating Point. |
| RPM | RPM | Equilibrium motor speed. |
| Thrust | N | Total thrust. |
| Electrical Power | W | Power drawn from the battery bus. |
| Current | A | Current drawn from the battery bus. |
| Battery Voltage | V | Bus voltage under load. |
| Advance Ratio (J) | — | Propeller advance ratio. |
| System Efficiency | — | Thrust power / battery power. |
| Propeller Efficiency | — | Thrust power / shaft power. |
| Motor Efficiency | — | Shaft power / motor electrical power. |
| Feasible | — | Whether the point is feasible. |
| Endurance to 20% SoC | min | Time to discharge at this point's battery power until the first pack reaches 20 % state of charge, or earlier when a pack reaches its cut-off voltage or current limit. Shown only when **Battery State of Charge** is above 20 %. |

### Plots

All plots use the swept value on the x axis. Ranges with infeasible points are
shaded.

| Plot | Series |
|---|---|
| Thrust | Thrust Force (N) |
| Power & Current | Battery Power (W) on the left axis, Battery Current (A) dashed on the right axis |
| RPM | Equilibrium RPM (RPM) |
| Efficiency | System Efficiency, Propeller Efficiency, Motor Efficiency (—) |

### Summary

The summary counts the feasible points and reports values over them only.

| Item | Unit | Description |
|---|---|---|
| Feasible Points (of N) | — | Number of feasible points out of N points. |
| Max Thrust | N | Highest thrust. |
| Peak Power | W | Highest battery power. |
| Peak Current | A | Highest battery current. |
| Max RPM | RPM | Highest RPM. |
| Best System Efficiency | — | Highest system efficiency. |
| Best Efficiency Throttle or Best Efficiency Airspeed | % or m/s | Swept value at the highest system efficiency. |
| Static Thrust | N | Highest thrust at zero advance ratio. Shown only when a feasible point is at zero airspeed. |
| Endurance to 20% SoC | min | Shown only for a single-point analysis, such as Operating Point, when **Battery State of Charge** is above 20 %. |

Without feasible points the summary shows only **Feasible Points**.

Values with a physical quantity follow the units chosen in **Edit → Settings**.
