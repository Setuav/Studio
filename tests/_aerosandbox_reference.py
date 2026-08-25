"""Independent native AeroSandbox models used by aerodynamic validation tests.

This module deliberately does not import or call the Setuav aerodynamic engine.
Its geometry is an explicit AeroSandbox representation of the fixed-wing test
aircraft, so it can expose regressions in Setuav's project-to-AeroSandbox adapter.
"""
from __future__ import annotations

from collections.abc import Sequence

import aerosandbox as asb


def build_fixed_wing_reference(
    clark_y_coordinates: Sequence[Sequence[float]],
) -> asb.Airplane:
    """Build the fixed-wing fixture directly with native AeroSandbox objects."""
    # The project schema treats coordinate profiles as normalized airfoil
    # shapes, regardless of the source DAT file's exact x-origin/chord.
    source_coordinates = [
        (float(point[0]), float(point[1]))
        for point in clark_y_coordinates
    ]
    min_x = min(point[0] for point in source_coordinates)
    max_x = max(point[0] for point in source_coordinates)
    source_chord = max(max_x - min_x, 1e-12)
    normalized_coordinates = [
        ((x - min_x) / source_chord, y / source_chord)
        for x, y in source_coordinates
    ]
    leading_edge_index = min(
        range(len(normalized_coordinates)),
        key=lambda index: normalized_coordinates[index][0],
    )
    normalized_coordinates[leading_edge_index] = (
        0.0,
        normalized_coordinates[leading_edge_index][1],
    )

    clark_y = asb.Airfoil(name="Clark-Y", coordinates=normalized_coordinates)
    naca0012 = asb.Airfoil("naca0012")

    main_root = (0.280, 0.075, 0.040)
    main_tip = (0.3209766178455207, 0.7511904761904761, 0.05180294866574713)
    main_etas = (0.0, 0.08, 0.425, 0.45, 0.95, 1.0)

    main_xsecs: list[asb.WingXSec] = []
    for eta in main_etas:
        controls: list[asb.ControlSurface] = []
        if eta == 0.08:
            controls.append(
                asb.ControlSurface(
                    name="flap",
                    symmetric=True,
                    deflection=0.0,
                    hinge_point=0.68,
                )
            )
        if eta == 0.45:
            controls.append(
                asb.ControlSurface(
                    name="Aileron",
                    symmetric=True,
                    deflection=0.0,
                    hinge_point=0.732,
                )
            )

        main_xsecs.append(
            asb.WingXSec(
                xyz_le=[
                    start + eta * (end - start)
                    for start, end in zip(main_root, main_tip)
                ],
                chord=0.240 + eta * (0.180 - 0.240),
                twist=3.0 * eta,
                airfoil=clark_y,
                control_surfaces=controls,
            )
        )

    main_wing = asb.Wing(
        name="Main Wing",
        symmetric=True,
        xsecs=main_xsecs,
    )

    vtail_root = (0.645, 0.038, 0.058)
    vtail_tip = (0.7039964122553721, 0.1915802670214772, 0.186869146057733)
    vtail_etas = (0.0, 0.1107, 0.8855, 1.0)

    vtail_xsecs: list[asb.WingXSec] = []
    for eta in vtail_etas:
        controls = []
        if eta == 0.1107:
            controls.append(
                asb.ControlSurface(
                    name="Ruddervator",
                    symmetric=True,
                    deflection=0.0,
                    hinge_point=0.697,
                )
            )

        vtail_xsecs.append(
            asb.WingXSec(
                xyz_le=[
                    start + eta * (end - start)
                    for start, end in zip(vtail_root, vtail_tip)
                ],
                chord=0.16382052424974758 + eta * (0.09829231454984856 - 0.16382052424974758),
                twist=0.0,
                airfoil=naca0012,
                control_surfaces=controls,
            )
        )

    vtail = asb.Wing(
        name="V-Tail",
        symmetric=True,
        xsecs=vtail_xsecs,
    )

    fuselage_sections = (
        ((0.000, 0.0, -0.007), 0.020, 0.020, 3.080000000000),
        ((0.007, 0.0, -0.005), 0.040, 0.036, 4.370370370370),
        ((0.040, 0.0, 0.003), 0.080, 0.077, 4.204081632653),
        ((0.050, 0.0, 0.004), 0.087, 0.084, 3.965986394558),
        ((0.120, 0.0, 0.011), 0.110, 0.113, 4.479338842975),
        ((0.190, 0.0, 0.015), 0.118, 0.123, 3.985636311405),
        ((0.275, 0.0, 0.017), 0.122, 0.125, 4.180059123891),
        ((0.360, 0.0, 0.018), 0.120, 0.122, 4.613333333333),
        ((0.440, 0.0, 0.020), 0.110, 0.113, 4.098512396694),
        ((0.520, 0.0, 0.022), 0.100, 0.100, 3.555200000000),
        ((0.700, 0.0, 0.025), 0.075, 0.075, 2.480000000000),
        ((0.830, 0.0, 0.030), 0.055, 0.055, 2.099173553719),
    )
    fuselage = asb.Fuselage(
        name="Fuselage",
        xsecs=[
            asb.FuselageXSec(
                xyz_c=xyz_c,
                width=width,
                height=height,
                shape=shape,
                xyz_normal=[1.0, 0.0, 0.0],
            )
            for xyz_c, width, height, shape in fuselage_sections
        ],
    )

    return asb.Airplane(
        name="Fixed-Wing Native Reference",
        wings=[main_wing, vtail],
        fuselages=[fuselage],
        s_ref=0.28404326116446976,
        b_ref=1.5023809523809522,
        c_ref=0.18906207557698465,
        # Keep the independent model's moment reference aligned with the
        # fixture's current Weight-Balance CG.
        xyz_ref=[0.36659149902660615, 0.0, 0.023860642439974045],
    )
