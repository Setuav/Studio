# Flight Performance

The Flight Performance analysis computes the steady level flight envelope of a
fixed-wing aircraft over a range of airspeeds. It combines the aircraft mass,
an aerodynamic polar of the aircraft, and the electric powertrain. It reports
the drag and power required at each airspeed and, when the aircraft has a
powertrain, the throttle, battery load, climb, endurance, and range.

## Add and run the analysis

1. Click **Add Flight Performance Analysis** in the toolbar. A configuration
   named **Flight Performance** appears under **Analyses**.
2. Select it and set its parameters in the Properties panel.
3. Click **Run Analysis**.

See [Interface](../user-guide/interface.md) for the panels and the result area.

## Inputs

The analysis reads three things from the project:

- **Mass**: the total mass of the vehicle components, as shown in
  [Mass and Balance](mass-balance.md), plus **Payload**. The analysis stops
  with an error when the mass is zero.
- **Aerodynamics**: an AeroBuildup alpha sweep of the aircraft, run with the
  engine of the [Aerodynamics](aerodynamics.md) plugin at **Polar Airspeed**
  and **Altitude**, from **Polar AoA Min** to **Polar AoA Max**. This needs the
  optional AeroSandbox package. The aircraft needs at least one lifting
  surface; see [Geometry](geometry.md).
- **Powertrain**: every propulsor and battery of the project, combined as in
  the [Propulsion](propulsion.md) analyses. All propulsors run at the same
  throttle from battery packs in parallel on one bus. When the project has no
  propulsor and no battery, the analysis gives an aerodynamic result only.
  When it has one but not the other, the analysis stops with an error.

## Parameters

| Parameter | Unit | Default | Description |
|---|---|---|---|
| Payload | g | 0 | Mass carried in addition to the component masses. Range 0 to 100000. |
| Altitude | m | 0 | Flight altitude. Range −500 to 15000. |
| Temperature | °C | 15 | Ambient air temperature. Range −50 to 60. |
| Min Speed | m/s | 8 | Lowest swept airspeed. The sweep never starts below the stall margin. Range 1 to 100. |
| Max Speed | m/s | 35 | Highest swept airspeed. Range 5 to 200. |
| Speed Step | m/s | 0.25 | Airspeed increment of the sweep. Range 0.05 to 5. |
| Stall Margin | × | 1.15 | Lowest swept airspeed as a multiple of the stall speed. Range 1 to 2. |
| Battery State of Charge | % | 100 | State of charge at the start of the flight. Range 1 to 100. |
| Landing Reserve | % | 20 | State of charge left at the end of the endurance and range flights. Range 0 to 99. |
| Polar Airspeed | m/s | 15 | Airspeed of the AeroBuildup polar. It sets the polar's Reynolds numbers. Range 1 to 200. |
| Polar AoA Min | ° | −8 | First angle of attack of the polar. Range −30 to 30. |
| Polar AoA Max | ° | 25 | Last angle of attack of the polar. It must reach stall. Range 0 to 45. |
| Polar AoA Step | ° | 0.5 | Angle of attack increment of the polar. Range 0.1 to 5. |

## Method

### Symbols

| Symbol | Unit | Meaning |
|---|---|---|
| \(m\) | kg | Flight mass: component masses plus **Payload** |
| \(g_0\) | m/s² | Standard gravity, 9.80665 |
| \(W\) | N | Weight, \(W = m\,g_0\) |
| \(\rho\) | kg/m³ | Air density |
| \(p\) | Pa | ISA pressure at **Altitude** |
| \(T\) | K | Air temperature from **Temperature** |
| \(R\) | J/(kg·K) | Gas constant of dry air, 287.05287 |
| \(S\) | m² | Reference area of the polar |
| \(V\) | m/s | Airspeed |
| \(q\) | Pa | Dynamic pressure, \(q = \tfrac{1}{2}\rho V^2\) |
| \(C_L\) | — | Lift coefficient |
| \(C_D\) | — | Drag coefficient |
| \(C_{L,\max}\) | — | Maximum lift coefficient of the polar |
| \(C_{D0}\) | — | Zero-lift drag coefficient of the fitted polar |
| \(k\) | — | Induced drag factor of the fitted polar |
| \(D\) | N | Drag |
| \(P_\text{req}\) | W | Power required |
| \(T_\text{av}\) | N | Thrust available |
| \(P_\text{av}\) | W | Power available |
| \(P_\text{bat}\) | W | Battery power in level flight |
| \(k_s\) | — | **Stall Margin** |
| \(\dot h\) | m/s | Rate of climb |
| \(\gamma\) | ° | Climb angle |
| \(t\) | s | Endurance |
| \(R_\text{range}\) | m | Range |

### Air density

The pressure follows the ISA profile at **Altitude**. The density uses the
temperature you enter:

\[
\rho = \frac{p}{R\,T}
\]

### Aerodynamic polar

The AeroBuildup sweep gives \(C_L\) and \(C_D\) at each angle of attack. Only
converged points are used.

- \(C_{L,\max}\) is the highest \(C_L\) of the sweep. It counts only when a
  later point in the sweep drops at least \(\max(0.02\,|C_{L,\max}|,\ 0.01)\)
  below it. Otherwise the sweep has not reached stall, and the analysis stops
  with an error that asks you to increase **Polar AoA Max**.
- The points up to the angle of \(C_{L,\max}\) form the pre-stall polar.
- \(S\) is the reference area the coefficients are normalized with: the
  planform area of the main wing. See
  [Reference values](aerodynamics.md#reference-values).

A parabolic drag polar is fitted to the pre-stall points by least squares:

\[
C_D = C_{D0} + k\,C_L^2
\]

The fit is rejected when it has fewer than three valid points, when
\(C_{D0} \le 0\) or \(k \le 0\), or when its coefficient of determination is
below 0.80. Then \(C_D\) is interpolated linearly in the pre-stall polar
instead. Outside the polar's \(C_L\) range the end value is used.

### Stall speed and sweep

\[
V_\text{stall} = \sqrt{\frac{2\,W}{\rho\,S\,C_{L,\max}}}
\]

The sweep starts at \(\max(V_\text{min},\ k_s V_\text{stall})\), where
\(V_\text{min}\) is **Min Speed**, and steps by **Speed Step** up to **Max
Speed**. The sweep must have at least two points.

### Level flight

At each airspeed, lift equals weight and thrust equals drag:

\[
C_L = \frac{W}{q\,S}, \qquad
D = q\,S\,C_D(C_L), \qquad
P_\text{req} = D\,V
\]

### Powertrain

At each airspeed the analysis solves the powertrain with PyThrust; see
[Propulsion](propulsion.md#powertrain-model).

1. **Usable throttle range.** The powertrain is solved at 20 throttles evenly
   spaced from 5 % to 100 %. The range runs from the lowest to the highest
   feasible one, and each end is refined by bisection. Below the range the
   propeller runs outside its data at this airspeed. Above it a motor or a
   battery exceeds its current limit.
2. **Thrust available.** \(T_\text{av}\) is the thrust at the top of the usable
   range, and \(P_\text{av} = T_\text{av}\,V\). Without a usable range,
   \(T_\text{av} = 0\).
3. **Level-flight throttle.** A root search finds the throttle in the usable
   range whose thrust equals \(D\). \(P_\text{bat}\) and the current are taken
   at that throttle.

A point is **feasible** when the usable range exists, the thrust \(D\) lies
within the thrust of that range, and the operating point at the level-flight
throttle is feasible. When \(D\) is above the thrust at the top of the range,
the **Throttle** column shows the top of the range. When \(D\) is below the
thrust at the bottom of the range, it shows the bottom. Without a usable range
it shows 0.

### Climb

The excess power lifts the aircraft:

\[
\dot h = \frac{\max(0,\ P_\text{av} - P_\text{req})}{W}, \qquad
\gamma = \arcsin\!\left(\min\!\left(1,\ \frac{\dot h}{V}\right)\right)
\]

Both are 0 at infeasible points.

### Endurance and range

The endurance \(t\) is the time the battery packs supply the constant power
\(P_\text{bat}\), starting at **Battery State of Charge**, until the first pack
reaches **Landing Reserve**. The flight ends earlier when a pack reaches its
cut-off voltage or current limit. PyThrust integrates the discharge with the
packs' open-circuit voltage and resistance curves, so the voltage sag losses
are included.

\[
R_\text{range} = V\,t
\]

Both are 0 at infeasible points.

### Characteristic speeds

| Speed | How it is found |
|---|---|
| Stall Speed | \(V_\text{stall}\) above. |
| Best L/D Speed | \(\sqrt{2W / (\rho\,S\,C_L^*)}\), with \(C_L^* = \sqrt{C_{D0}/k}\) for the fitted polar, or the \(C_L\) of the highest \(C_L/C_D\) in the pre-stall polar. |
| Min Power Speed | Swept airspeed with the lowest \(P_\text{req}\). |
| Best Endurance Speed | Feasible airspeed with the lowest \(P_\text{bat}\). |
| Best Range Speed | Feasible airspeed with the highest range. |
| Best Climb Speed | Feasible airspeed with the highest rate of climb. |
| Max Level Speed | Airspeed where \(T_\text{av}\) falls below \(D\), interpolated linearly after the last feasible point with \(T_\text{av} \ge D\). |

With the fitted polar, \((L/D)_\max = 1 / \left(2\sqrt{C_{D0}\,k}\right)\).
Otherwise it is the highest \(C_L/C_D\) of the pre-stall polar.

## Results

### Envelope table

The **Envelope** table has one row per swept airspeed. The columns from
**Thrust Available** on appear only when the project has a powertrain.

| Column | Unit | Description |
|---|---|---|
| Airspeed | m/s | Swept airspeed \(V\). |
| CL | — | Lift coefficient \(C_L\) in level flight. |
| Drag | N | Drag \(D\). |
| Power Required | W | \(P_\text{req} = D\,V\). |
| Thrust Available | N | \(T_\text{av}\), thrust at the top of the usable throttle range. |
| Power Available | W | \(P_\text{av} = T_\text{av}\,V\). |
| Throttle | % | Throttle that holds level flight. |
| Battery Power | W | \(P_\text{bat}\), power drawn from the batteries in level flight. |
| Current | A | Battery current in level flight. |
| Rate of Climb | m/s | \(\dot h\). |
| Climb Angle | ° | \(\gamma\). |
| Endurance | min | \(t\). |
| Range | km | \(R_\text{range}\). |
| Feasible | — | Whether the powertrain can hold level flight at this airspeed. |

At infeasible points **Battery Power**, **Current**, **Rate of Climb**,
**Climb Angle**, **Endurance**, and **Range** are 0.

### Plots

All plots have the airspeed on the x axis. When the project has a powertrain,
airspeeds that are not feasible are shaded.

| Plot | Series | Shown |
|---|---|---|
| Power | Required (W); Available (W) | Always; Available only with a powertrain |
| Drag & Thrust | Drag (N); Thrust Available (N) | Always; Thrust Available only with a powertrain |
| Rate of Climb | Rate of Climb (m/s) | With a powertrain |
| Endurance | Endurance (min) | With a powertrain |
| Range | Range (km) | With a powertrain |
| Current & Throttle | Current (A) on the left axis; Throttle (%) dashed on the right axis | With a powertrain |

### Summary

| Item | Unit | Shown |
|---|---|---|
| Flight Mass | g | Always |
| Air Density | kg/m³ | Always |
| Wing Area | dm² | Always; this is \(S\) |
| Max Lift (CL,max) | — | Always |
| Max L/D | — | Always |
| Stall Speed | m/s | Always |
| Best L/D Speed | m/s | Always |
| Min Power Speed | m/s | Always |
| Zero-Lift Drag CD0 | — | When the parabolic fit is accepted |
| Induced Drag k | — | When the parabolic fit is accepted |
| Battery Open-Circuit Voltage | V | With a powertrain; bus open-circuit voltage at **Battery State of Charge** |
| Max Level Speed | m/s | With a powertrain |
| Max Speed Within Sweep | — | With a powertrain; false when the sweep ends before thrust falls below drag, so **Max Level Speed** is only the last feasible airspeed |
| Level Flight Feasible | — | With a powertrain; false when no airspeed is feasible |
| Best Endurance Speed, Max Endurance | m/s, min | With feasible points |
| Best Range Speed, Max Range | m/s, km | With feasible points |
| Cruise Battery Power, Cruise Current, Cruise Throttle | W, A, % | With feasible points; values at the best range speed |
| Best Climb Speed, Max Rate of Climb | m/s, m/s | With feasible points |
| Max Climb Angle | ° | With feasible points |
| Note | — | When a mirrored surface had to be modelled as two wings; see [Geometry conversion](aerodynamics.md#geometry-conversion) |

## Assumptions and limits

- Flight is steady, level, and unaccelerated: lift equals weight and thrust
  equals drag. The thrust line is taken along the flight path.
- The polar is untrimmed and is computed once, at **Polar Airspeed**. Its
  Reynolds numbers do not change with the swept airspeed.
- The mass is constant during the flight.
- The characteristic speeds from the sweep are swept airspeeds, so their
  precision is the **Speed Step**. Only **Stall Speed**, **Best L/D Speed**,
  and **Max Level Speed** are computed between sweep points.
- The rate of climb uses the excess power at the level-flight airspeed. It is
  the excess power divided by the weight, without a change of drag in the
  climb.
- Throttles below 5 % are not considered.
- Endurance and range assume constant battery power for the whole flight, with
  no take-off, climb, or descent.
- **Landing Reserve** must be below **Battery State of Charge** when the
  aircraft has a powertrain. Otherwise the analysis stops at once with an error
  naming both parameters.
- The sweep must contain at least two airspeeds from the stall margin up to
  **Max Speed**; otherwise the analysis stops with an error.
