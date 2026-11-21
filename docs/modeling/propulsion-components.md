# Propulsion Components

The Electrical Propulsion plugin adds two components: the **Propulsor**, a motor
with its propeller, and the **Battery**. Their motors and propellers come from
the [Component Database](#component-database). The analyses of the powertrain
they form are described in [Propulsion Analyses](../analyses/propulsion.md).

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

!!! warning "Motors without a rated current"
    Some catalog motors have no maximum current (0 A). The analyses cannot
    judge such a motor and stop with an error asking for another motor.

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
| Series Count (S) | S | 6 | Cells in series. Sets the pack voltage. Whole number, 1 to 32. |
| Parallel Count (P) | P | 1 | Cells in parallel. Sets the pack capacity. Whole number, 1 to 64. |
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
folder with `motors` and `propellers` subfolders in the PyThrust format. If
the variable names a folder that does not exist, or the dataset lacks one of
these subfolders, opening the catalog reports an error naming the path.
