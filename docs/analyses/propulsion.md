# Propulsion Analyses

Three analyses solve the powertrain formed by the project's propulsors and
batteries: **Throttle Sweep**, **Airspeed Sweep**, and **Operating Point**. They
use the [PyThrust](https://setuav.github.io/PyThrust/) package to solve motors,
propellers, and battery packs together. [Flight Performance](flight-performance.md)
uses the same powertrain. The components are described in
[Propulsion Components](../modeling/propulsion-components.md).

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
