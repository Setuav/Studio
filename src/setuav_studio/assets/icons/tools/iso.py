"""Draw Setuav Studio's isometric icons from small 3D models.

Each ``icon_<name>`` function builds a scene; the camera looks from (+1, +1, +1)
with z up, faces are shaded by one light and outlined. ``python iso.py`` writes
every icon as ``<name>.svg`` into the folder it belongs to (see ``destination``).
"""

import argparse
import itertools
import math
from pathlib import Path

C30 = math.cos(math.radians(30))
LIGHT = (0.45, -0.1, 1.0)
_l = math.sqrt(sum(c * c for c in LIGHT))
LIGHT = tuple(c / _l for c in LIGHT)

COLORS = {
    "f": (0x3C, 0xBC, 0xFF),  # fuselage blue
    "w": (0xFF, 0xE2, 0x3A),  # wing yellow
    "m": (0xDE, 0xE2, 0xE8),  # metal gray
    "a": (0xFF, 0x5C, 0x4A),  # accent red
    "c": (0x7C, 0x84, 0x90),  # carbon
    "e": (0x4C, 0xD9, 0x7B),  # electrical green
    "k": (0x4A, 0x4E, 0x55),  # black lead
    "l": (0xA6, 0xDA, 0xFF),  # motor light blue
    "s": (0xE6, 0xC8, 0x8C),  # propeller sand
    "o": (0xFF, 0xA0, 0x40),  # folder orange
    "u": (0xE8, 0xC8, 0x6A),  # point mass light gold
    "x": (0xFF, 0xFF, 0xFF),  # paper white
    "t": (0x00, 0xD1, 0xD1),  # spar tube cyan, as in the 3D view
    "h": (0xFF, 0x69, 0xB5),  # hinge tube pink, as in the 3D view
}
OUTLINE = "#16191d"


def sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def norm(v):
    length = math.sqrt(sum(c * c for c in v)) or 1.0
    return tuple(c / length for c in v)


def rotate(p, axis, deg):
    a = math.radians(deg)
    c, s_ = math.cos(a), math.sin(a)
    x, y, z = p
    if axis == "x":
        return (x, y * c - z * s_, y * s_ + z * c)
    if axis == "y":
        return (x * c + z * s_, y, -x * s_ + z * c)
    return (x * c - y * s_, x * s_ + y * c, z)


def badge_svg(glyph):
    """A red glyph in the lower-right corner of the icon, outlined for contrast."""
    red = "#{:02x}{:02x}{:02x}".format(*COLORS["a"])
    if glyph == "magnifier":
        lens = '<circle cx="16.6" cy="16.6" r="3.9" fill="none" stroke="{c}" stroke-width="{w}"/>'
        handle = '<path d="M19.4 19.4 L22.6 22.6" stroke="{c}" stroke-width="{w}" stroke-linecap="round"/>'
        return (
            lens.format(c=OUTLINE, w=3.6)
            + handle.format(c=OUTLINE, w=4.2)
            + lens.format(c=red, w=1.7)
            + handle.format(c=red, w=2.3)
        )
    if glyph == "point":
        return f'<circle cx="18.6" cy="18.6" r="3.6" fill="{red}" stroke="{OUTLINE}" stroke-width="1.1"/>'
    text = (
        'x="18.4" y="23.2" text-anchor="middle" font-family="DejaVu Sans, Arial, sans-serif" '
        'font-weight="bold" font-size="13"'
    )
    return (
        f'<text {text} fill="{OUTLINE}" stroke="{OUTLINE}" stroke-width="2.2" stroke-linejoin="round">{glyph}</text>'
        f'<text {text} fill="{red}">{glyph}</text>'
    )


class Scene:
    def __init__(self, turn=(), body="m", badge=None, fit=22.8, overlay=""):
        self.faces = []
        self.overlay = overlay  # SVG drawn over the icon, in its 24 px box
        self.fit = fit  # pixels the icon's longer side fills
        self.badge = badge  # glyph of the red analysis badge in the lower-right corner
        self.body = body  # color of the neutral ("n") and ghost ("g") faces
        self.turn = turn  # (axis, degrees) rotations applied to every point

    def face(self, pts, color="n", layer=0, two_sided=False):
        for axis, deg in self.turn:
            pts = [rotate(p, axis, deg) for p in pts]
        n = (0, 0, 0)
        for i in range(1, len(pts) - 1):
            c = cross(sub(pts[i], pts[0]), sub(pts[i + 1], pts[0]))
            n = (n[0] + c[0], n[1] + c[1], n[2] + c[2])
        n = norm(n)
        if n[0] + n[1] + n[2] <= 1e-6:
            if not two_sided:
                return
            n = (-n[0], -n[1], -n[2])
        self.faces.append((layer, pts, n, color))

    def loft(self, rings, color="n", caps=(True, True), layer=0, flip=False):
        k = len(rings[0])
        for r0, r1 in itertools.pairwise(rings):
            for i in range(k):
                q = [r0[i], r0[(i + 1) % k], r1[(i + 1) % k], r1[i]]
                self.face(q[::-1] if flip else q, color, layer)
        if caps[0]:
            self.face(rings[0][::-1] if not flip else rings[0], color, layer)
        if caps[1]:
            self.face(rings[-1] if not flip else rings[-1][::-1], color, layer)

    def box(self, x0, y0, z0, x1, y1, z1, color="n", layer=0):
        b = [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0)]
        t = [(x, y, z1) for x, y, _ in b]
        self.loft([b, t], color, layer=layer)

    def natural_scale(self):
        """The scale that fits this icon alone into the 24 px box."""

        def proj(p):
            return ((p[1] - p[0]) * C30, (p[0] + p[1]) * 0.5 - p[2])

        pts = [proj(p) for _layer, face, _n, _c in self.faces for p in face]
        xs = [x for x, _ in pts]
        ys = [y for _, y in pts]
        return self.fit / max(max(xs) - min(xs), max(ys) - min(ys))

    def svg(self, scale=None):
        def proj(p):
            return ((p[1] - p[0]) * C30, (p[0] + p[1]) * 0.5 - p[2])

        polys = []
        for _layer, pts, n, color in sorted(
            self.faces, key=lambda f: (f[0], sum(sum(p) for p in f[1]) / len(f[1]))
        ):
            b = 0.64 + 0.45 * max(0.0, sum(a * light for a, light in zip(n, LIGHT, strict=True)))
            base = COLORS[self.body if color in ("n", "g") else color]
            rgb = "#{:02x}{:02x}{:02x}".format(*tuple(min(255, round(c * b)) for c in base))
            polys.append(([proj(p) for p in pts], rgb, color == "g"))
        xs = [x for pl, _, _ in polys for x, _ in pl]
        ys = [y for pl, _, _ in polys for _, y in pl]
        w, h = max(xs) - min(xs), max(ys) - min(ys)
        s = scale or self.fit / max(w, h)
        cx = cy = 10.8 if self.badge else 12.0
        ox = cx - (min(xs) + max(xs)) / 2 * s
        oy = cy - (min(ys) + max(ys)) / 2 * s

        def path(pl, c):
            return (
                f'<path d="M{" L".join(f"{x * s + ox:.2f} {y * s + oy:.2f}" for x, y in pl)} Z" '
                f'fill="{c}" stroke="{c}" stroke-width="0.25" stroke-linejoin="round"/>'
            )

        def outline(pl):
            return (
                f'<path d="M{" L".join(f"{x * s + ox:.2f} {y * s + oy:.2f}" for x, y in pl)} Z" '
                f'fill="{OUTLINE}" stroke="{OUTLINE}" stroke-width="1.1" stroke-linejoin="round"/>'
            )

        under = "".join(outline(pl) for pl, c, g in polys if not g)
        ghost = "".join(path(pl, c) for pl, c, g in polys if g)
        ghost_under = "".join(outline(pl) for pl, c, g in polys if g)
        body = (
            (f'<g opacity="0.78">{ghost_under}{ghost}</g>' if ghost else "")
            + under
            + "".join(path(pl, c) for pl, c, g in polys if not g)
        )
        if self.badge:
            body += badge_svg(self.badge)
        body += self.overlay
        return f'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24">{body}</svg>'


def ring(center, axis, r, n=16, ry=None, phase=0.0):
    """Circle (or ellipse) of radius r around an axis 'x', 'y' or 'z'."""
    ry = ry or r
    out = []
    for i in range(n):
        a = 2 * math.pi * i / n + phase
        u, v = r * math.cos(a), ry * math.sin(a)
        cx, cy, cz = center
        out.append(
            {"x": (cx, cy + u, cz + v), "y": (cx + u, cy, cz + v), "z": (cx + u, cy + v, cz)}[axis]
        )
    return out


def cylinder(sc, center, axis, r, length, color="n", n=18, layer=0):
    c0 = center
    d = {"x": (length, 0, 0), "y": (0, length, 0), "z": (0, 0, length)}[axis]
    c1 = (c0[0] + d[0], c0[1] + d[1], c0[2] + d[2])
    r0, r1 = ring(c0, axis, r, n), ring(c1, axis, r, n)
    if axis == "y":
        r0, r1 = r0[::-1], r1[::-1]
    sc.loft([r0, r1], color, layer=layer)


# --- wing -------------------------------------------------------------------
TH = 0.2


def thick(c):
    c = min(max(c, 0.0), 1.0)
    return (
        5
        * TH
        * (0.2969 * math.sqrt(c) - 0.126 * c - 0.3516 * c * c + 0.2843 * c**3 - 0.1036 * c**4)
    )


def airfoil(c0, c1, n=14):
    cs = [c0 + (c1 - c0) * (1 - math.cos(math.pi * i / n)) / 2 for i in range(n + 1)]
    top = [(c, thick(c)) for c in cs]
    bot = [(c, -thick(c)) for c in reversed(cs)]
    return top + bot


SPAN = 1.8


def wing_station(s):  # s: 0 tip .. SPAN root ; returns (le_x, chord)
    f = s / SPAN
    return (0.35 * (1 - f), 0.8 + 0.6 * f)


def wing_piece(sc, s0, s1, c0, c1, color="n", z_off=0.0, dz=0.0, station=None):
    rings = []
    for s in (s0, s1):
        le, ch = (station or wing_station)(s)
        y = s
        rings.append(
            [(le + c * ch, y, (t + z_off) * ch + dz * (c - c0) * ch) for c, t in airfoil(c0, c1)]
        )
    sc.loft(rings, color)


def wing(sc, skip=None):
    wing_piece(sc, 0, SPAN, 0, 1)


def icon_geometry_add_lifting_surface():
    sc = Scene((("y", 28), ("z", -12)), body="w")
    wing(sc)
    return sc


def icon_geometry_add_control_surface():
    sc = Scene((("y", 28), ("z", -12)), body="w")
    wing_piece(sc, 0, 0.15, 0, 1)
    wing_piece(sc, 0.15, 1.2, 0, 0.66)
    wing_piece(sc, 0.17, 1.18, 0.68, 1, "a")
    wing_piece(sc, 1.2, SPAN, 0, 1)
    return sc


def tube(sc, r_out, r_in, length, color, n=36):
    """Hollow tube along y, open end facing the viewer."""
    outer = [ring((0, 0, 0), "y", r_out, n)[::-1], ring((0, length, 0), "y", r_out, n)[::-1]]
    inner = [ring((0, 0, 0), "y", r_in, n)[::-1], ring((0, length, 0), "y", r_in, n)[::-1]]
    sc.loft(inner, color, caps=(False, False), layer=0, flip=True)
    sc.loft(outer, color, caps=(False, False), layer=1)
    o, i = outer[1], inner[1]
    for j in range(n):
        sc.face([o[j], o[(j + 1) % n], i[(j + 1) % n], i[j]], color, layer=2, two_sided=True)


def icon_manufacturing_spar():
    sc = Scene((("z", -20),), body="c")
    tube(sc, 0.32, 0.22, 3.0, "c")
    return sc


def icon_manufacturing_wing_joint():
    """A hex-head screw with a threaded shank."""
    sc = Scene((("y", 18), ("z", -20)))
    r_major, r_minor, pitch, length = 0.3, 0.22, 0.2, 2.1
    rings = []
    steps = int(length / (pitch / 2))
    for i in range(steps + 1):
        z = -length + i * pitch / 2
        r = r_major if i % 2 else r_minor
        if z < -length + 0.35:  # pointed tip
            r *= max((z + length) / 0.35, 0.05)
        rings.append(ring((0, 0, z), "z", r, 24))
    sc.loft(rings, "n")
    sc.loft([ring((0, 0, 0.0), "z", 0.62, 6), ring((0, 0, 0.42), "z", 0.62, 6)], "n", layer=1)
    sc.loft([ring((0, 0, 0.42), "z", 0.58, 6), ring((0, 0, 0.5), "z", 0.5, 6)], "n", layer=1)
    return sc


def icon_manufacturing_servo_bay():
    """A hobby servo: body with mounting ears and its output spline."""
    sc = Scene((("z", -10),))
    L, W, H = 1.6, 0.8, 1.45  # body length (x), width (y), height (z)
    sc.box(-L / 2, -W / 2, 0.0, L / 2, W / 2, H, "e")
    ear_z = H * 0.72
    sc.box(-L / 2 - 0.32, -W / 2, ear_z, L / 2 + 0.32, W / 2, ear_z + 0.12, "e")
    shaft_x = L / 2 - 0.42
    cylinder(sc, (shaft_x, 0, H), "z", 0.3, 0.1, "e", n=28)
    cylinder(sc, (shaft_x, 0, H + 0.1), "z", 0.1, 0.12, "m", n=16)
    return sc


# --- fuselage ---------------------------------------------------------------
FUS_L, FUS_R, SEG = 2.5, 0.6, 28


def interp_r(x):
    """Streamlined fuselage radius: rounded nose at x = FUS_L, tapering tail."""
    t = x / FUS_L
    if t >= 0.78:
        u = min((t - 0.78) / 0.22, 1.0)
        return FUS_R * max(1 - u**2.2, 0.0) ** (1 / 2.2) + 0.004
    if t >= 0.6:
        return FUS_R
    u = t / 0.6
    return FUS_R * (0.16 + 0.84 * math.sin(u * math.pi / 2) ** 0.9)


def stations(x0=0.0, x1=FUS_L):
    xs = [x0 + (x1 - x0) * i / 20 for i in range(21)]
    if x1 >= FUS_L - 1e-9:
        xs = [x for x in xs if x < FUS_L * 0.88] + [
            FUS_L * (0.88 + 0.12 * (1 - math.cos(math.pi / 2 * i / 6))) for i in range(7)
        ]
    return sorted({round(x, 5) for x in xs if x0 <= x <= x1})


def fus_ring(x, scale=1.0):
    r = interp_r(x) * scale
    return ring((x, 0, 0), "x", r, SEG, ry=r * 1.05)


def plate(sc, pts, z0, z1, color="n"):
    sc.loft([[(x, y, z0) for x, y in pts], [(x, y, z1) for x, y in pts]], color)


def tail(sc):
    pts2 = [(0.0, 0.05), (0.62, 0.08), (0.34, 0.95), (0.1, 0.95)]
    t = 0.04
    sc.loft([[(x, -t, z) for x, z in pts2], [(x, t, z) for x, z in pts2]], "n")
    plate(sc, [(0.0, 0.0), (0.42, 0.0), (0.28, 0.6), (0.06, 0.6)], -0.02, 0.03)
    plate(sc, [(0.0, -0.6), (0.28, -0.6), (0.42, 0.0), (0.0, 0.0)], -0.02, 0.03)


def fuselage(sc, x0=0.0, x1=FUS_L, color="n"):
    sc.loft([fus_ring(x) for x in stations(x0, x1)], color)


def icon_geometry_add_fuselage():
    sc = Scene((("z", -22),), body="f")
    fuselage(sc)
    return sc


def icon_manufacturing_nose_cut():
    sc = Scene((("z", -22),), body="f")
    cut = FUS_L * 0.8
    sc.loft([fus_ring(x) for x in stations(0.0, cut)], "n")
    nose = [fus_ring(cut)] + [fus_ring(x) for x in stations(cut, FUS_L) if x > cut]
    shift = 0.22
    sc.loft([[(p[0] + shift, p[1], p[2]) for p in r] for r in nose], "a")
    return sc


def icon_manufacturing_access_cover():
    sc = Scene((("z", -22),), body="f")
    fuselage(sc)
    xs = list(stations(0.95, 2.0))
    arcs = []
    for x in xs:
        r = interp_r(x) * 1.04
        arcs.append(
            [
                (x, r * math.cos(a), r * 1.05 * math.sin(a))
                for a in (math.radians(15 + 125 * i / 14) for i in range(15))
            ]
        )
    for r0, r1 in itertools.pairwise(arcs):
        for i in range(len(r0) - 1):
            sc.face([r0[i], r0[i + 1], r1[i + 1], r1[i]], "a", layer=1)
    return sc


def icon_manufacturing_fuselage_shell():
    sc = Scene(body="f")
    xs = stations(0.45 * FUS_L, 0.8 * FUS_L)
    outer = [fus_ring(x) for x in xs]
    inner = [fus_ring(x, 0.8) for x in xs]
    sc.loft(inner, "a", caps=(False, False), layer=0, flip=True)
    sc.loft(outer, "n", caps=(False, False), layer=1)
    o, i = outer[-1], inner[-1]
    k = len(o)
    for j in range(k):
        sc.face([o[j], o[(j + 1) % k], i[(j + 1) % k], i[j]], "n", layer=2, two_sided=True)
    return sc


def icon_vehicle():
    sc = Scene((("z", -30),), body="f")
    sc.loft([fus_ring(x, 0.5) for x in stations()], "n")

    def surface(y0, y1, le0, ch0, le1, ch1, z, flip=False):
        rings = []
        for yy in (y0, y1):
            f = (yy - y0) / (y1 - y0)
            le, ch = le0 + (le1 - le0) * f, ch0 + (ch1 - ch0) * f
            rings.append(
                [(le + c * ch, (-yy if flip else yy), z + t * ch) for c, t in airfoil(0, 1)]
            )
        if flip:
            rings = [r[::-1] for r in rings]
        sc.loft(rings, "w")

    x_le = 0.42 * FUS_L
    for flip in (False, True):
        surface(0.2, 2.2, x_le, 0.62, x_le + 0.2, 0.34, 0.06, flip)
        surface(0.06, 0.75, 0.0, 0.38, 0.1, 0.22, 0.0, flip)
    pts2 = [(0.0, 0.08), (0.45, 0.12), (0.22, 0.62), (0.04, 0.62)]
    t = 0.035
    sc.loft([[(x, -t, z) for x, z in pts2], [(x, t, z) for x, z in pts2]], "w")
    return sc


# --- propulsion -------------------------------------------------------------
def motor(sc, x=0.0, color="l"):
    cylinder(sc, (x - 0.3, 0, 0), "x", 0.5, 0.24, color, n=36)
    cylinder(sc, (x - 0.06, 0, 0), "x", 0.44, 0.08, color, n=36)
    cylinder(sc, (x + 0.02, 0, 0), "x", 0.55, 0.62, color, n=36)
    cylinder(sc, (x + 0.64, 0, 0), "x", 0.18, 0.08, color, n=20)
    cylinder(sc, (x + 0.72, 0, 0), "x", 0.07, 0.36, color, n=12)


def icon_propulsion_motor():
    sc = Scene()
    motor(sc)
    return sc


def icon_manufacturing_motor_mount():
    sc = Scene()
    motor(sc)
    sc.box(-0.42, -0.85, -0.85, -0.27, 0.85, 0.85, "a")
    return sc


def blade(sc, x, angle, length=1.6, color="n"):
    a = math.radians(angle)
    u = (0, math.cos(a), math.sin(a))
    v = (0, -math.sin(a), math.cos(a))
    k = length / 1.6
    shape = [
        (0.15, -0.1),
        (0.5 * k, -0.2),
        (1.15 * k, -0.15),
        (1.5 * k, -0.1),
        (length, -0.03),
        (length, 0.04),
        (1.5 * k, 0.1),
        (1.1 * k, 0.22),
        (0.55 * k, 0.26),
        (0.15, 0.15),
    ]

    def pt(s, w, dx):
        return (x + dx, u[1] * s + v[1] * w, u[2] * s + v[2] * w)

    sc.loft([[pt(s, w, 0) for s, w in shape], [pt(s, w, 0.06) for s, w in shape]], color)


def propeller(sc, x=0.0, color="s", length=1.6):
    for angle in (90, 210, 330):
        blade(sc, x, angle, length, color)
    cylinder(sc, (x - 0.06, 0, 0), "x", 0.26, 0.2, color, n=18)
    rings = [
        ring((x + 0.12 + 0.36 * t, 0, 0), "x", 0.26 * (1 - t) ** 0.7 + 0.001, 18)
        for t in (0, 0.3, 0.6, 1.0)
    ]
    sc.loft(rings, color)


def icon_propulsion_propeller():
    sc = Scene((("z", 45),))
    propeller(sc)
    return sc


def icon_propulsion_propulsor():
    sc = Scene()
    motor(sc)
    propeller(sc, 1.2, length=1.3)
    return sc


def icon_propulsion_battery():
    """A block battery: body between a base and a lid, two terminals, a bolt on the front."""
    sc = Scene((("z", 25),), body="e")
    W, L, H, lip = 1.0, 1.9, 1.25, 0.07  # x: depth, y: length, z: height
    sc.box(-lip, -lip, 0.0, W + lip, L + lip, 0.16, "e")
    sc.box(0.0, 0.0, 0.16, W, L, H - 0.24, "e")
    sc.box(-lip, -lip, H - 0.24, W + lip, L + lip, H, "e")
    for y in (0.38, L - 0.38):
        sc.box(W / 2 - 0.2, y - 0.2, H, W / 2 + 0.2, y + 0.2, H + 0.06, "e", layer=1)
        sc.box(W / 2 - 0.12, y - 0.12, H + 0.06, W / 2 + 0.12, y + 0.12, H + 0.26, "e", layer=1)
    bolt = [
        (0.98, 0.98),
        (0.7, 0.46),
        (0.92, 0.46),
        (0.74, 0.02),
        (1.2, 0.62),
        (0.96, 0.62),
        (1.18, 0.98),
    ]
    x = W + 0.004
    sc.face([(x, y, 0.2 + z * (H - 0.48)) for y, z in bolt], "x", layer=1, two_sided=True)
    return sc


def icon_point_mass():
    """The weight symbol: a tapered block with a ring handle."""
    sc = Scene(body="u")

    def rounded_square(z, half, r=0.12, k=4):
        pts = []
        for cx, cy, a0 in (
            (half - r, -half + r, -90),
            (half - r, half - r, 0),
            (-half + r, half - r, 90),
            (-half + r, -half + r, 180),
        ):
            for i in range(k + 1):
                a = math.radians(a0 + 90 * i / k)
                pts.append((cx + r * math.cos(a), cy + r * math.sin(a), z))
        return pts

    sc.loft([rounded_square(0.0, 0.95), rounded_square(1.05, 0.62)], "n")
    # Ring handle: a flat annulus standing on the block, facing the viewer.
    R, r_in, t, n = 0.52, 0.3, 0.18, 40
    cz = 1.05 + R - 0.08
    d = (1 / math.sqrt(2), -1 / math.sqrt(2), 0.0)  # in the ring plane, horizontal on screen
    nrm = (1 / math.sqrt(2), 1 / math.sqrt(2), 0.0)  # ring plane normal

    def pt(rad, a, off):
        u, z = rad * math.cos(a), cz + rad * math.sin(a)
        return (d[0] * u + nrm[0] * off, d[1] * u + nrm[1] * off, z)

    angles = [2 * math.pi * i / n for i in range(n)]
    o0 = [pt(R, a, -t / 2) for a in angles]
    o1 = [pt(R, a, t / 2) for a in angles]
    i0 = [pt(r_in, a, -t / 2) for a in angles]
    i1 = [pt(r_in, a, t / 2) for a in angles]
    for j in range(n):
        k = (j + 1) % n
        sc.face([i0[j], i0[k], i1[k], i1[j]], "n", layer=1, two_sided=True)
        sc.face([o0[j], o0[k], o1[k], o1[j]], "n", layer=1, two_sided=True)
    for j in range(n):
        k = (j + 1) % n
        sc.face([o1[j], o1[k], i1[k], i1[j]], "n", layer=2, two_sided=True)
    return sc


# --- other ------------------------------------------------------------------
class Raw:
    def __init__(self, body):
        self.body = body

    def natural_scale(self):
        return None

    def svg(self, scale=None):
        return (
            '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24">'
            + self.body
            + "</svg>"
        )


def icon_center_of_gravity():
    def grad(gid, base):
        hi = "#{:02x}{:02x}{:02x}".format(*tuple(min(255, round(c * 1.0)) for c in base))
        mid = "#{:02x}{:02x}{:02x}".format(*tuple(round(c * 0.72) for c in base))
        lo = "#{:02x}{:02x}{:02x}".format(*tuple(round(c * 0.36) for c in base))
        return (
            f'<radialGradient id="{gid}" cx="8.5" cy="7.5" r="15" gradientUnits="userSpaceOnUse">'
            f'<stop offset="0" stop-color="{hi}"/><stop offset="0.55" stop-color="{mid}"/><stop offset="1" stop-color="{lo}"/></radialGradient>'
        )

    return Raw(
        "<defs>" + grad("n", COLORS["m"]) + grad("a", COLORS["a"]) + "</defs>"
        f'<circle cx="12" cy="12" r="10.4" fill="{OUTLINE}"/><circle cx="12" cy="12" r="9.8" fill="url(#n)"/>'
        '<path d="M12 12 V2.2 A9.8 9.8 0 0 1 21.8 12 Z" fill="url(#a)"/>'
        '<path d="M12 12 V21.8 A9.8 9.8 0 0 1 2.2 12 Z" fill="url(#a)"/>'
    )


def icon_manufacturing():
    """A print bed, a part printed in layers and the nozzle above it."""
    sc = Scene()
    sc.box(-0.85, -0.85, -0.16, 0.85, 0.85, 0.0)
    for i in range(4):
        z0 = i * 0.22
        sc.box(-0.48, -0.48, z0 + 0.05, 0.48, 0.48, z0 + 0.22, "a")
    sc.box(-0.26, -0.26, 1.45, 0.26, 0.26, 1.95)
    rings = [ring((0, 0, 1.45 - 0.38 * t), "z", 0.2 * (1 - t) + 0.04, 16) for t in (0, 1)]
    sc.loft(rings, "n")
    return sc


def icon_manufacturing_control_surface_hinge():
    """The hinge tube, thinner than the spar, with an arrow turning around it."""
    sc = Scene((("z", -20),), body="c")
    tube(sc, 0.17, 0.1, 3.0, "c")
    y = 1.2
    pts = [
        (0.62 * math.cos(math.radians(a)), y, 0.62 * math.sin(math.radians(a)))
        for a in (200 - 230 * i / 24 for i in range(25))
    ]
    tube_path(sc, pts[:-3], 0.09, "a", n=12, layer=1)
    cone(sc, pts[-4], sub(pts[-1], pts[-4]), 0.24, 0.42, "a", layer=1)
    return sc


# --- analyses -------------------------------------------------------------
def _basis(t):
    t = norm(t)
    up = (0, 0, 1) if abs(t[2]) < 0.9 else (1, 0, 0)
    u = norm(cross(t, up))
    v = cross(t, u)
    return u, v


def tube_path(sc, pts, r, color, n=12, layer=0):
    """A round tube swept along a polyline; the cross-section is carried along, so it never twists."""
    rings = []
    prev_u = None
    for i, p in enumerate(pts):
        a = pts[max(i - 1, 0)]
        b = pts[min(i + 1, len(pts) - 1)]
        t = norm(sub(b, a))
        if prev_u is None:
            u, v = _basis(t)
        else:
            dot = sum(prev_u[k] * t[k] for k in range(3))
            u = norm(tuple(prev_u[k] - dot * t[k] for k in range(3)))
            v = cross(t, u)
        prev_u = u
        rings.append(
            [
                tuple(
                    p[k]
                    + r
                    * (math.cos(2 * math.pi * j / n) * u[k] + math.sin(2 * math.pi * j / n) * v[k])
                    for k in range(3)
                )
                for j in range(n)
            ]
        )
    sc.loft(rings, color, layer=layer)


def cone(sc, base, direction, r, length, color, n=16, layer=0):
    d = norm(direction)
    u, v = _basis(d)
    tip = tuple(base[k] + d[k] * length for k in range(3))
    ring_b = [
        tuple(
            base[k]
            + r * (math.cos(2 * math.pi * j / n) * u[k] + math.sin(2 * math.pi * j / n) * v[k])
            for k in range(3)
        )
        for j in range(n)
    ]
    ring_t = [
        tuple(
            tip[k]
            + 0.002 * (math.cos(2 * math.pi * j / n) * u[k] + math.sin(2 * math.pi * j / n) * v[k])
            for k in range(3)
        )
        for j in range(n)
    ]
    sc.loft([ring_b, ring_t], color, layer=layer)


def straight_arrow(sc, start, end, r=0.07, color="a", layer=1):
    head = 0.34
    d = norm(sub(end, start))
    shaft_end = tuple(end[k] - d[k] * head for k in range(3))
    tube_path(sc, [start, shaft_end], r, color, layer=layer)
    cone(sc, shaft_end, d, r * 2.6, head, color, layer=layer)


def pin(sc, tip, height=0.9, r=0.26, color="a", layer=2):
    """A map pin: a ball on a cone pointing at ``tip``."""
    cz = tip[2] + height
    cone(
        sc,
        (tip[0], tip[1], cz - r * 0.4),
        (0, 0, -1),
        r * 0.75,
        height - r * 0.4,
        color,
        layer=layer,
    )
    nl, nm = 10, 20
    rings = []
    for i in range(1, nl):
        th = math.pi * i / nl
        rings.append(
            [
                (
                    tip[0] + r * math.sin(th) * math.cos(2 * math.pi * j / nm),
                    tip[1] + r * math.sin(th) * math.sin(2 * math.pi * j / nm),
                    cz - r * math.cos(th),
                )
                for j in range(nm)
            ]
        )
    sc.loft(rings, color, layer=layer)


SECTION_VIEW = (("z", -45),)  # the profile faces the viewer, chord horizontal
SECTION_CHORD, SECTION_SPAN = 1.6, 1.1


def section_station(_s):
    return (0.0, SECTION_CHORD)


def wing_section(sc, c0=0.0, c1=1.0, color="n"):
    global TH
    keep, TH = TH, 0.28
    wing_piece(sc, 0, SECTION_SPAN, c0, c1, color=color, station=section_station)
    TH = keep


def _aero(glyph):
    sc = Scene(SECTION_VIEW, body="w", badge=glyph)
    wing_section(sc)
    return sc


def icon_aero_alpha_sweep():
    return _aero("α")


def icon_aero_beta_sweep():
    return _aero("β")


def icon_aero_control_deflection():
    sc = Scene(SECTION_VIEW, body="w", badge="δ")
    wing_section(sc, 0.0, 0.7)
    hinge = 0.72 * SECTION_CHORD
    a = math.radians(26)
    rings = []
    for yy in (0, SECTION_SPAN):
        ring_pts = []
        for c, t in airfoil(0.72, 1.0):
            x, z = c * SECTION_CHORD - hinge, t * SECTION_CHORD
            ring_pts.append(
                (hinge + x * math.cos(a) + z * math.sin(a), yy, -x * math.sin(a) + z * math.cos(a))
            )
        rings.append(ring_pts)
    sc.loft(rings, "n")
    return sc


def icon_aero_operating_point():
    return _aero("point")


PROP_VIEW = (("z", 45),)


def _propulsion(glyph):
    sc = Scene(PROP_VIEW, badge=glyph)
    propeller(sc, length=1.4)
    return sc


def icon_propulsion_throttle_sweep():
    return _propulsion("%")


def icon_propulsion_airspeed_sweep():
    return _propulsion("V")


def icon_propulsion_operating_point():
    return _propulsion("point")


def icon_flight_performance():
    """The aircraft in flight: motion streaks trail behind its wings."""
    sc = icon_vehicle()
    for y, length in ((-1.5, 1.3), (1.5, 1.3), (0.0, 1.0)):
        x1 = 0.42 * FUS_L - 0.15 if y else -0.15
        tube_path(sc, [(x1 - length, y, 0.06), (x1, y, 0.06)], 0.09, "a", layer=1)
    return sc


# --- parameters -----------------------------------------------------------
GLYPH_D = (-1 / math.sqrt(2), 1 / math.sqrt(2), 0.0)  # screen-horizontal, left to right
GLYPH_N = (1 / math.sqrt(2), 1 / math.sqrt(2), 0.0)  # toward the viewer


def glyph_point(u, v, w):
    return tuple(GLYPH_D[k] * u + GLYPH_N[k] * w + (v if k == 2 else 0.0) for k in range(3))


def glyph_prism(sc, outline, color, depth=0.32):
    """Extrude a 2D outline (u right, v up) toward the viewer."""
    back = [glyph_point(u, v, -depth / 2) for u, v in outline]
    front = [glyph_point(u, v, depth / 2) for u, v in outline]
    n = len(outline)
    area = sum(
        outline[i][0] * outline[(i + 1) % n][1] - outline[(i + 1) % n][0] * outline[i][1]
        for i in range(n)
    )
    if area < 0:
        back, front = back[::-1], front[::-1]
    for j in range(n):
        k = (j + 1) % n
        sc.face([back[j], back[k], front[k], front[j]], color, two_sided=True)
    sc.face(front, color, layer=1, two_sided=True)


def bar(u0, v0, u1, v1, width):
    du, dv = u1 - u0, v1 - v0
    length = math.hypot(du, dv)
    pu, pv = -dv / length * width / 2, du / length * width / 2
    return [(u0 + pu, v0 + pv), (u1 + pu, v1 + pv), (u1 - pu, v1 - pv), (u0 - pu, v0 - pv)]


def arc_pts(cu, cv, r, a0, a1, n=10):
    return [
        (
            cu + r * math.cos(math.radians(a0 + (a1 - a0) * i / n)),
            cv + r * math.sin(math.radians(a0 + (a1 - a0) * i / n)),
        )
        for i in range(n + 1)
    ]


GLYPH_FIT = 16.5


def icon_constant():
    sc = Scene(fit=GLYPH_FIT)
    t = 0.22
    glyph_prism(sc, [(-1.0, 0.76), (1.0, 0.76), (1.0, 0.76 + t), (-1.0, 0.76 + t)], "n", depth=0.26)
    glyph_prism(
        sc, [(-0.56, -0.95), (-0.56 + t, -0.95), (-0.56 + t, 0.76), (-0.56, 0.76)], "n", depth=0.26
    )
    # right leg ending in a small hook to the right
    inner = arc_pts(0.62, -0.62, 0.3 - t, 180, 270, 8)
    outer = arc_pts(0.62, -0.62, 0.3, 270, 180, 8)
    glyph_prism(
        sc,
        [(0.32, 0.76), (0.32 + t, 0.76), *inner, (0.86, -0.62 - (0.3 - t)), (0.86, -0.92), *outer],
        "n",
        depth=0.26,
    )
    return sc


def icon_formula():
    sc = Scene(fit=GLYPH_FIT)
    t, d = 0.22, 0.26
    # f: a stem that rises into a hook to the right
    inner = arc_pts(0.0, 0.6, 0.2, 180, 55, 12)
    outer = arc_pts(0.0, 0.6, 0.42, 55, 180, 12)
    glyph_prism(sc, [(-0.42, -1.0), (-0.2, -1.0), *inner, *outer], "n", depth=d)
    glyph_prism(sc, [(-0.74, 0.1), (0.06, 0.1), (0.06, 0.1 + t), (-0.74, 0.1 + t)], "n", depth=d)
    # x: the variable, in red
    glyph_prism(sc, bar(0.26, 0.18, 1.0, -0.98, 0.24), "a", depth=d)
    glyph_prism(sc, bar(1.0, 0.18, 0.26, -0.98, 0.24), "a", depth=d)
    return sc


def chain_link(sc, center, axis_u, axis_v, color, half=0.38, radius=0.36, tube=0.11):
    """A chain link: a stadium-shaped ring in the plane of axis_u and axis_v."""
    pts = []
    for i in range(25):
        a = -math.pi / 2 + math.pi * i / 24
        pts.append((half + radius * math.cos(a), radius * math.sin(a)))
    for i in range(25):
        a = math.pi / 2 + math.pi * i / 24
        pts.append((-half + radius * math.cos(a), radius * math.sin(a)))
    path3 = [tuple(center[k] + axis_u[k] * u + axis_v[k] * v for k in range(3)) for u, v in pts]
    tube_path(sc, [*path3, path3[0], path3[1]], tube, color, n=18)


def icon_constraint():
    sc = Scene(fit=19.5)
    tilt = math.radians(45)
    along = tuple(
        GLYPH_D[k] * math.cos(tilt) + (math.sin(tilt) if k == 2 else 0.0) for k in range(3)
    )
    up = tuple(-GLYPH_D[k] * math.sin(tilt) + (math.cos(tilt) if k == 2 else 0.0) for k in range(3))
    c1 = tuple(-along[k] * 0.55 for k in range(3))
    c2 = tuple(along[k] * 0.55 for k in range(3))
    chain_link(sc, c1, along, up, "n")
    chain_link(sc, c2, along, GLYPH_N, "a")
    return sc


def icon_run_analysis():
    """A gear with a play triangle in front of it."""
    sc = Scene(fit=22.0)
    teeth, n_per = 9, 8
    angles = [2 * math.pi * i / (teeth * n_per) for i in range(teeth * n_per)]

    def tooth_r(a):
        f = (a * teeth / (2 * math.pi)) % 1.0
        if f < 0.18 or f > 0.82:
            return 1.0
        if 0.32 < f < 0.68:
            return 0.78
        return 1.0 - 0.22 * ((f - 0.18) / 0.14 if f < 0.5 else (0.82 - f) / 0.14)

    d = 0.3
    gu, gv = -0.25, 0.22
    outer = [(gu + tooth_r(a) * math.cos(a), gv + tooth_r(a) * math.sin(a)) for a in angles]
    hole = [(gu + 0.32 * math.cos(a), gv + 0.32 * math.sin(a)) for a in angles]
    o0 = [glyph_point(u, v, -d / 2) for u, v in outer]
    o1 = [glyph_point(u, v, d / 2) for u, v in outer]
    i0 = [glyph_point(u, v, -d / 2) for u, v in hole]
    i1 = [glyph_point(u, v, d / 2) for u, v in hole]
    n = len(outer)
    for j in range(n):
        k = (j + 1) % n
        sc.face([o0[j], o0[k], o1[k], o1[j]], "f", two_sided=True)
        sc.face([i0[j], i0[k], i1[k], i1[j]], "f", two_sided=True)
    for j in range(n):
        k = (j + 1) % n
        sc.face([o1[j], o1[k], i1[k], i1[j]], "f", layer=1, two_sided=True)
    # play triangle, in front and to the lower right
    tri = [(-0.05, -1.05), (1.15, -0.3), (-0.05, 0.45)]
    back = [glyph_point(u, v, d / 2 + 0.05) for u, v in tri]
    front = [glyph_point(u, v, d / 2 + 0.4) for u, v in tri]
    for j in range(3):
        k = (j + 1) % 3
        sc.face([back[j], back[k], front[k], front[j]], "e", layer=2, two_sided=True)
    sc.face(front, "e", layer=3, two_sided=True)
    return sc


def icon_manufacturing_add_feature():
    sc = icon_manufacturing()
    sc.badge = "+"
    return sc


def icon_manufacturing_generate():
    """Printed layers with a play triangle in front: generate the parts."""
    sc = Scene(fit=22.0)
    for i in range(4):
        z0 = i * 0.32
        sc.box(-0.75 - 0.02 * i, -0.75, z0 + 0.1, 0.75, 0.75 + 0.02 * i, z0 + 0.32, "a")
    d = 0.3
    tri = [(-0.35, -1.35), (1.35, -0.3), (-0.35, 0.75)]
    shift = (0.6, 0.6, 0.05)

    def gp(u, v, w):
        p = glyph_point(u, v, w)
        return (p[0] + shift[0], p[1] + shift[1], p[2] + shift[2])

    back = [gp(u, v, 0.4) for u, v in tri]
    front = [gp(u, v, 0.4 + d) for u, v in tri]
    for j in range(3):
        k = (j + 1) % 3
        sc.face([back[j], back[k], front[k], front[j]], "e", layer=2, two_sided=True)
    sc.face(front, "e", layer=3, two_sided=True)
    return sc


# --- file and edit commands --------------------------------------------------
FILE_TURN = (("z", -24),)


def glyph_slab(sc, outline, w0, w1, color, layer=0, front_layer=1, place=glyph_point):
    """A flat slab: ``outline`` in the glyph plane, from depth w0 to w1."""
    back = [place(u, v, w0) for u, v in outline]
    front = [place(u, v, w1) for u, v in outline]
    n = len(outline)
    for j in range(n):
        k = (j + 1) % n
        sc.face([back[j], back[k], front[k], front[j]], color, layer=layer, two_sided=True)
    sc.face(front, color, layer=front_layer, two_sided=True)
    return front


def icon_file_new():
    """A sheet with a folded corner and a plus."""
    sc = Scene(FILE_TURN, fit=21.0, body="x", badge="+")
    page = [(-0.75, -1.0), (0.75, -1.0), (0.75, 0.62), (0.37, 1.0), (-0.75, 1.0)]
    glyph_slab(sc, page, -0.06, 0.06, "n")
    glyph_slab(
        sc, [(0.37, 1.0), (0.37, 0.62), (0.75, 0.62)], 0.06, 0.1, "n", layer=2, front_layer=3
    )
    return sc


def _folder(sc, open_angle):
    back = [(-1.0, -0.8), (1.0, -0.8), (1.0, 0.62), (-0.05, 0.62), (-0.2, 0.8), (-1.0, 0.8)]
    glyph_slab(sc, back, -0.3, -0.16, "o")
    a = math.radians(open_angle)

    def tilted(u, v, w):
        vv = v + 0.8
        return glyph_point(u, -0.8 + vv * math.cos(a), w + vv * math.sin(a))

    front = [(-1.0, -0.8), (1.0, -0.8), (1.0, 0.45), (-1.0, 0.45)]
    glyph_slab(sc, front, 0.1, 0.24, "o", layer=2, front_layer=3, place=tilted)


def icon_folder_open():
    sc = Scene(FILE_TURN, fit=21.5)
    _folder(sc, 32)
    return sc


def icon_project_folder():
    sc = Scene(FILE_TURN, fit=21.5)
    _folder(sc, 0)
    return sc


def _floppy(sc):
    body = [(-1.0, -1.0), (1.0, -1.0), (1.0, 0.72), (0.72, 1.0), (-1.0, 1.0)]
    glyph_slab(sc, body, -0.12, 0.12, "f")
    glyph_slab(
        sc,
        [(-0.62, -1.0), (0.62, -1.0), (0.62, -0.12), (-0.62, -0.12)],
        0.12,
        0.16,
        "m",
        layer=2,
        front_layer=3,
    )
    glyph_slab(
        sc,
        [(-0.45, 0.42), (0.45, 0.42), (0.45, 1.0), (-0.45, 1.0)],
        0.12,
        0.16,
        "k",
        layer=2,
        front_layer=3,
    )


def icon_save():
    sc = Scene(FILE_TURN, fit=21.0)
    _floppy(sc)
    return sc


def icon_save_as():
    sc = Scene(FILE_TURN, fit=21.0, badge="+")
    _floppy(sc)
    return sc


def _curved_arrow(sc, mirror, color="l"):
    """The undo arrow: a tail curling up on the right, the head pointing left."""
    sgn = -1 if mirror else 1
    cu, cv, r = 0.2, -0.1, 0.52
    pts = [
        (cu + r * math.cos(math.radians(a)), cv + r * math.sin(math.radians(a)))
        for a in (-90 + 180 * i / 18 for i in range(19))
    ]
    pts.append((-0.35, cv + r))
    path3 = [glyph_point(sgn * u, v, 0.0) for u, v in pts]
    tube_path(sc, path3, 0.15, color, n=16)
    cone(sc, path3[-1], glyph_point(-sgn, 0, 0), 0.4, 0.6, color)


def icon_undo():
    sc = Scene(fit=21.0)
    _curved_arrow(sc, mirror=False)
    return sc


def icon_redo():
    sc = Scene(fit=21.0)
    _curved_arrow(sc, mirror=True)
    return sc


def icon_exit():
    """An open door with a red arrow leaving it."""
    sc = Scene((("z", 24),), fit=21.5)
    frame = [(-1.0, -1.0), (0.2, -1.0), (0.2, 1.0), (-1.0, 1.0)]
    glyph_slab(sc, frame, -0.2, -0.1, "k")
    a = math.radians(55)

    def swung(u, v, w):
        du = u + 1.0
        return glyph_point(-1.0 + du * math.cos(a), v, w + du * math.sin(a))

    glyph_slab(
        sc,
        [(-1.0, -1.0), (0.2, -1.0), (0.2, 1.0), (-1.0, 1.0)],
        -0.1,
        0.0,
        "o",
        layer=1,
        front_layer=2,
        place=swung,
    )
    start, end = glyph_point(-0.3, 0.0, 0.3), glyph_point(1.2, 0.0, 0.3)
    straight_arrow(sc, start, end, r=0.13, layer=3)
    return sc


# --- settings -------------------------------------------------------------
def gear(sc, gu, gv, color, d=0.3, teeth=9, r_out=1.0, r_root=0.78, r_hole=0.32, layer=0):
    n_per = 8
    angles = [2 * math.pi * i / (teeth * n_per) for i in range(teeth * n_per)]

    def tooth_r(a):
        f = (a * teeth / (2 * math.pi)) % 1.0
        if f < 0.18 or f > 0.82:
            return r_out
        if 0.32 < f < 0.68:
            return r_root
        k = (f - 0.18) / 0.14 if f < 0.5 else (0.82 - f) / 0.14
        return r_out - (r_out - r_root) * k

    outer = [(gu + tooth_r(a) * math.cos(a), gv + tooth_r(a) * math.sin(a)) for a in angles]
    hole = [(gu + r_hole * math.cos(a), gv + r_hole * math.sin(a)) for a in angles]
    o0 = [glyph_point(u, v, -d / 2) for u, v in outer]
    o1 = [glyph_point(u, v, d / 2) for u, v in outer]
    i0 = [glyph_point(u, v, -d / 2) for u, v in hole]
    i1 = [glyph_point(u, v, d / 2) for u, v in hole]
    n = len(outer)
    for j in range(n):
        k = (j + 1) % n
        sc.face([o0[j], o0[k], o1[k], o1[j]], color, layer=layer, two_sided=True)
        sc.face([i0[j], i0[k], i1[k], i1[j]], color, layer=layer, two_sided=True)
    for j in range(n):
        k = (j + 1) % n
        sc.face([o1[j], o1[k], i1[k], i1[j]], color, layer=layer + 1, two_sided=True)


def icon_settings():
    sc = Scene(FILE_TURN, fit=21.5)
    gear(sc, 0.0, 0.0, "f")
    return sc


def icon_settings_general():
    """Three slider tracks with their knobs at different heights."""
    sc = Scene(FILE_TURN, fit=21.0)
    glyph_slab(sc, [(-1.0, -1.0), (1.0, -1.0), (1.0, 1.0), (-1.0, 1.0)], -0.12, 0.0, "m")
    for u, knob, color in ((-0.55, 0.35, "a"), (0.0, -0.4, "f"), (0.55, 0.15, "e")):
        glyph_slab(
            sc,
            [(u - 0.06, -0.78), (u + 0.06, -0.78), (u + 0.06, 0.78), (u - 0.06, 0.78)],
            0.0,
            0.04,
            "k",
            layer=1,
            front_layer=2,
        )
        glyph_slab(
            sc,
            [
                (u - 0.2, knob - 0.14),
                (u + 0.2, knob - 0.14),
                (u + 0.2, knob + 0.14),
                (u - 0.2, knob + 0.14),
            ],
            0.04,
            0.2,
            color,
            layer=3,
            front_layer=4,
        )
    return sc


def icon_settings_appearance():
    """A painter's palette with four paints."""
    sc = Scene(FILE_TURN, fit=21.0)
    outline = []
    for i in range(48):
        a = 2 * math.pi * i / 48
        r = 1.0 + 0.08 * math.cos(3 * a)
        outline.append((r * math.cos(a), 0.82 * r * math.sin(a)))
    glyph_slab(sc, outline, -0.08, 0.08, "s")
    hole = [
        (0.42 + 0.17 * math.cos(2 * math.pi * i / 20), -0.4 + 0.15 * math.sin(2 * math.pi * i / 20))
        for i in range(20)
    ]
    glyph_slab(sc, hole, 0.08, 0.1, "k", layer=2, front_layer=3)
    for (u, v), color in (
        ((-0.5, 0.32), "a"),
        ((0.0, 0.5), "w"),
        ((0.5, 0.3), "f"),
        ((-0.45, -0.3), "e"),
    ):
        blob = [
            (u + 0.2 * math.cos(2 * math.pi * i / 20), v + 0.18 * math.sin(2 * math.pi * i / 20))
            for i in range(20)
        ]
        glyph_slab(sc, blob, 0.08, 0.16, color, layer=2, front_layer=3)
    return sc


def icon_settings_units():
    """A ruler with its tick marks."""
    sc = Scene((("z", -24), ("x", 0)), fit=22.0)

    def place(u, v, w):
        a = math.radians(35)
        uu, vv = u * math.cos(a) - v * math.sin(a), u * math.sin(a) + v * math.cos(a)
        return glyph_point(uu, vv, w)

    glyph_slab(
        sc, [(-1.3, -0.32), (1.3, -0.32), (1.3, 0.32), (-1.3, 0.32)], -0.08, 0.08, "w", place=place
    )
    for i in range(11):
        u = -1.1 + 0.22 * i
        tick = 0.3 if i % 5 == 0 else 0.16
        glyph_slab(
            sc,
            [
                (u - 0.025, 0.32 - tick),
                (u + 0.025, 0.32 - tick),
                (u + 0.025, 0.32),
                (u - 0.025, 0.32),
            ],
            0.08,
            0.1,
            "k",
            layer=2,
            front_layer=3,
            place=place,
        )
    return sc


def icon_settings_startup():
    """A clock: when the application starts."""
    sc = Scene(FILE_TURN, fit=21.0)
    rim = [(math.cos(2 * math.pi * i / 40), math.sin(2 * math.pi * i / 40)) for i in range(40)]
    glyph_slab(sc, rim, -0.18, 0.0, "f")
    face = [
        (0.82 * math.cos(2 * math.pi * i / 40), 0.82 * math.sin(2 * math.pi * i / 40))
        for i in range(40)
    ]
    glyph_slab(sc, face, 0.0, 0.03, "x", layer=2, front_layer=3)
    glyph_slab(sc, bar(0.0, 0.0, 0.0, 0.58, 0.12), 0.03, 0.08, "k", layer=4, front_layer=5)
    glyph_slab(sc, bar(0.0, 0.0, 0.42, -0.18, 0.12), 0.03, 0.08, "a", layer=4, front_layer=5)
    return sc


# --- tools and status bar ---------------------------------------------------
def disc_pts(cu, cv, r, n=40, ry=None):
    ry = ry or r
    return [
        (cu + r * math.cos(2 * math.pi * i / n), cv + ry * math.sin(2 * math.pi * i / n))
        for i in range(n)
    ]


def rect(u0, v0, u1, v1):
    return [(u0, v0), (u1, v0), (u1, v1), (u0, v1)]


def icon_command_palette():
    """A terminal window with a prompt."""
    sc = Scene(FILE_TURN, fit=21.5)
    glyph_slab(sc, rect(-1.0, -0.8, 1.0, 0.8), -0.12, 0.0, "k")
    glyph_slab(sc, rect(-1.0, 0.56, 1.0, 0.8), 0.0, 0.03, "m", layer=2, front_layer=3)
    glyph_slab(
        sc,
        [
            (-0.72, 0.22),
            (-0.22, -0.06),
            (-0.72, -0.34),
            (-0.72, -0.16),
            (-0.44, -0.06),
            (-0.72, 0.04),
        ],
        0.0,
        0.05,
        "e",
        layer=2,
        front_layer=3,
    )
    glyph_slab(sc, rect(-0.12, -0.42, 0.45, -0.28), 0.0, 0.05, "e", layer=2, front_layer=3)
    return sc


def icon_task_manager():
    """A board with three progress bars."""
    sc = Scene(FILE_TURN, fit=21.5)
    glyph_slab(sc, rect(-1.0, -0.9, 1.0, 0.9), -0.1, 0.0, "x")
    for v, done, color in ((0.45, 0.85, "e"), (0.0, 0.45, "f"), (-0.45, 0.2, "a")):
        glyph_slab(
            sc, rect(-0.75, v - 0.12, 0.75, v + 0.12), 0.0, 0.02, "m", layer=2, front_layer=3
        )
        glyph_slab(
            sc,
            rect(-0.75, v - 0.12, -0.75 + 1.5 * done, v + 0.12),
            0.02,
            0.07,
            color,
            layer=4,
            front_layer=5,
        )
    return sc


def icon_plugin_manager():
    """An open cardboard box."""
    sc = Scene(fit=22.0)
    w, h = 0.9, 1.0
    sc.box(-w, -w, 0.0, w, w, h, "s")
    sc.box(-w + 0.06, -w + 0.06, h - 0.05, w - 0.06, w - 0.06, h + 0.001, "k", layer=1)
    a = math.radians(40)
    for side in (1, -1):
        p0 = (side * w, -w, h)
        p1 = (side * w, w, h)
        out = (side * (w + 0.7 * math.cos(a)), 0, h + 0.7 * math.sin(a))
        sc.face([p0, p1, (out[0], w, out[2]), (out[0], -w, out[2])], "s", layer=2, two_sided=True)
    return sc


def icon_aero_airfoil_analysis():
    sc = Scene(SECTION_VIEW, body="w", badge="Cl")
    wing_section(sc)
    return sc


def icon_propulsion_component_database():
    """Stacked database disks."""
    sc = Scene(fit=21.0)
    for i in range(3):
        z0 = i * 0.55
        cylinder(sc, (0, 0, z0), "z", 1.0, 0.42, "l", n=36)
    return sc


def icon_debug_panel():
    """A beetle: red shell, dark head and legs."""
    sc = Scene((("z", -45),), fit=21.5)
    rings = []
    for i in range(1, 12):
        th = math.pi / 2 * i / 11
        rings.append(
            [
                (
                    0.75 * math.cos(2 * math.pi * j / 28) * math.sin(th) * 1.0,
                    1.0 * math.sin(2 * math.pi * j / 28) * math.sin(th),
                    0.6 * math.cos(th),
                )
                for j in range(28)
            ]
        )
    sc.loft(rings[::-1], "a", caps=(False, True), layer=1)
    cylinder(sc, (0, 1.0, 0.18), "y", 0.32, 0.35, "k", n=18, layer=1)
    for y in (-0.5, 0.0, 0.5):
        for side in (1, -1):
            tube_path(
                sc,
                [(side * 0.6, y, 0.1), (side * 1.05, y + 0.15, 0.2), (side * 1.25, y + 0.05, -0.2)],
                0.06,
                "k",
                n=8,
            )
    return sc


def icon_log():
    """A speech bubble with three lines."""
    sc = Scene(FILE_TURN, fit=21.5)
    bubble = [
        (-1.0, -0.4),
        (-0.45, -0.4),
        (-0.7, -0.95),
        (0.0, -0.4),
        (1.0, -0.4),
        (1.0, 0.9),
        (-1.0, 0.9),
    ]
    glyph_slab(sc, bubble, -0.12, 0.0, "x")
    for v, length in ((0.55, 1.4), (0.22, 1.1), (-0.1, 1.25)):
        glyph_slab(
            sc,
            rect(-0.7, v - 0.07, -0.7 + length, v + 0.07),
            0.0,
            0.04,
            "f",
            layer=2,
            front_layer=3,
        )
    return sc


def icon_cancel():
    """A red disc with a white cross."""
    sc = Scene(FILE_TURN, fit=21.0)
    glyph_slab(sc, disc_pts(0, 0, 1.0), -0.15, 0.0, "a")
    glyph_slab(sc, bar(-0.45, -0.45, 0.45, 0.45, 0.24), 0.0, 0.05, "x", layer=2, front_layer=3)
    glyph_slab(sc, bar(-0.45, 0.45, 0.45, -0.45, 0.24), 0.0, 0.05, "x", layer=2, front_layer=3)
    return sc


def icon_view_layers():
    """Three stacked sheets: the viewport layers."""
    sc = Scene(fit=22.0)
    for i, color in enumerate(("f", "w", "a")):
        z0 = i * 0.42
        sc.box(-1.0, -1.0, z0, 1.0, 1.0, z0 + 0.16, color)
    return sc


def icon_manufacturing_inspect():
    sc = icon_manufacturing()
    sc.badge = "magnifier"
    return sc


def icon_manufacturing_printer():
    """A 3D printer: frame, gantry with the print head, bed and a printed part."""
    sc = Scene(fit=22.0)
    w, h, p = 1.0, 2.0, 0.12
    for x in (-w, w - p):
        for y in (-w, w - p):
            sc.box(x, y, 0.0, x + p, y + p, h, "k")
    sc.box(-w, -w, h - p, w, -w + p, h, "k")
    sc.box(-w, w - p, h - p, w, w, h, "k")
    sc.box(-w, -w, 0.0, w, w, 0.14, "k")
    sc.box(-w + p, -0.08, 1.3, w - p, 0.08, 1.42, "m", layer=1)
    sc.box(-0.22, -0.22, 1.12, 0.22, 0.22, 1.5, "o", layer=2)
    rings = [ring((0, 0, 1.12 - 0.22 * t), "z", 0.12 * (1 - t) + 0.02, 12) for t in (0, 1)]
    sc.loft(rings, "m", layer=2)
    sc.box(-0.75, -0.75, 0.14, 0.75, 0.75, 0.26, "m", layer=1)
    sc.box(-0.3, -0.3, 0.26, 0.3, 0.3, 0.62, "a", layer=1)
    return sc


def icon_manufacturing_hw_fastener():
    """An ISO 4762 socket-head cap screw: threaded shank, round cap head, hex recess."""
    sc = Scene((("y", 18), ("z", -20)), body="m")
    r_major, r_minor, pitch, length = 0.30, 0.22, 0.22, 1.9
    rings = []
    steps = int(length / (pitch / 2))
    for i in range(steps + 1):
        z = -length + i * pitch / 2
        r = r_major if i % 2 else r_minor
        if z < -length + 0.25:
            r *= max((z + length) / 0.25, 0.25)
        rings.append(ring((0, 0, z), "z", r, 24))
    sc.loft(rings, "m")
    cylinder(sc, (0, 0, 0.0), "z", 0.56, 0.54, "m", n=24, layer=1)
    sc.face(ring((0, 0, 0.545), "z", 0.30, 6), "k", layer=2)
    return sc


def icon_manufacturing_hw_insert():
    """A brass heat-set insert: tapered pilot base, dual knurl bands, dark bore."""
    sc = Scene(fit=21.0, body="u")
    profile = [
        (0.0, 0.56),
        (0.28, 0.66),
        (0.36, 0.80),
        (0.68, 0.80),
        (0.76, 0.66),
        (0.96, 0.66),
        (1.04, 0.80),
        (1.36, 0.80),
        (1.44, 0.72),
    ]
    rings = [ring((0, 0, z), "z", r, 24) for z, r in profile]
    sc.loft(rings, "u", layer=0)
    sc.face(ring((0, 0, 1.445), "z", 0.42, 24), "k", layer=1)
    return sc


def icon_manufacturing_hw_nut():
    """An ISO 4032 hex nut: six-sided chamfered steel body with a dark center bore."""
    sc = Scene((("z", -15),), fit=21.0, body="m")
    sc.loft([ring((0, 0, 0.0), "z", 1.0, 6), ring((0, 0, 0.62), "z", 1.0, 6)], "m", layer=0)
    sc.loft([ring((0, 0, 0.62), "z", 1.0, 6), ring((0, 0, 0.72), "z", 0.88, 6)], "m", layer=1)
    sc.face(ring((0, 0, 0.725), "z", 0.48, 24), "k", layer=2)
    return sc


def icon_manufacturing_hardware_catalog():
    """Hardware catalog: stacked steel catalog disks topped with a brass hex nut."""
    sc = Scene(fit=21.5, body="m")
    cylinder(sc, (0, 0, 0.0), "z", 1.02, 0.34, "c", n=32, layer=0)
    cylinder(sc, (0, 0, 0.48), "z", 1.02, 0.34, "m", n=32, layer=1)
    sc.loft([ring((0, 0, 0.94), "z", 0.72, 6), ring((0, 0, 1.38), "z", 0.72, 6)], "u", layer=2)
    sc.face(ring((0, 0, 1.385), "z", 0.34, 24), "k", layer=3)
    return sc


# --- 3D view ------------------------------------------------------------------
CUBE = (-1.0, -1.0, -1.0, 1.0, 1.0, 1.0)


def cube_edges(sc, color, r=0.07, layer=2):
    x0, y0, z0, x1, y1, z1 = CUBE
    corners = [(x, y, z) for x in (x0, x1) for y in (y0, y1) for z in (z0, z1)]
    for i, a in enumerate(corners):
        for b in corners[i + 1 :]:
            if sum(1 for k in range(3) if a[k] != b[k]) == 1:
                tube_path(sc, [a, b], r, color, n=10, layer=layer)


def highlight(sc, face, color="a", layer=1):
    """A colored face laid just over one face of the cube."""
    e = 1.003
    quads = {
        "top": [(-1, -1, e), (1, -1, e), (1, 1, e), (-1, 1, e)],
        "bottom": [(-1, -1, -e), (-1, 1, -e), (1, 1, -e), (1, -1, -e)],
        "front": [(e, -1, -1), (e, 1, -1), (e, 1, 1), (e, -1, 1)],
        "side": [(-1, e, -1), (-1, e, 1), (1, e, 1), (1, e, -1)],
    }
    sc.face(quads[face], color, layer=layer, two_sided=True)


def icon_view_solid():
    sc = Scene(fit=20.0, body="m")
    sc.box(*CUBE, "m")
    return sc


def icon_view_wireframe():
    sc = Scene(fit=20.0, body="m")
    cube_edges(sc, "m", r=0.09)
    return sc


def icon_view_transparent():
    sc = Scene(fit=20.0, body="m")
    sc.box(*CUBE, "g")
    cube_edges(sc, "m")
    return sc


def _camera(face):
    """A gray wire cube with the face the camera looks at filled blue."""
    sc = Scene(fit=20.0, body="m")
    cube_edges(sc, "m", r=0.09)
    highlight(sc, face, color="f", layer=1 if face == "bottom" else 3)
    return sc


def icon_camera_top():
    return _camera("top")


def icon_camera_bottom():
    return _camera("bottom")


def icon_camera_front():
    return _camera("front")


def icon_camera_side():
    return _camera("side")


def icon_camera_iso():
    sc = Scene(fit=20.0, body="m")
    sc.box(*CUBE, "m")
    return sc


def icon_view_fit():
    """A gray cube inside four blue corner brackets."""
    brackets = "".join(
        f'<path d="M{x} {y + dy * 5} L{x} {y} L{x + dx * 5} {y}" fill="none" stroke="{{c}}" '
        f'stroke-width="{{w}}" stroke-linecap="round" stroke-linejoin="round"/>'
        for x, y, dx, dy in ((2, 2, 1, 1), (22, 2, -1, 1), (2, 22, 1, -1), (22, 22, -1, -1))
    )
    blue = "#{:02x}{:02x}{:02x}".format(*COLORS["f"])
    overlay = brackets.format(c=OUTLINE, w=3.4) + brackets.format(c=blue, w=1.8)
    sc = Scene(fit=13.0, body="m", overlay=overlay)
    sc.box(*CUBE, "m")
    return sc


def icon_viewer_3d():
    """The three axes: x red, y green, z blue."""
    sc = Scene(fit=21.0)
    for end, color in (((1.9, 0, 0), "a"), ((0, 1.9, 0), "e"), ((0, 0, 1.9), "f")):
        straight_arrow(sc, (0.0, 0.0, 0.0), end, r=0.12, color=color)
    return sc


ICONS = {k[5:]: v for k, v in globals().items() if k.startswith("icon_")}
# Icons that show the same object share one scale, so the object keeps its size.
FAMILIES = (
    ("aero_alpha_sweep", "aero_beta_sweep", "aero_control_deflection", "aero_operating_point"),
    ("propulsion_throttle_sweep", "propulsion_airspeed_sweep", "propulsion_operating_point"),
)
STUDIO = Path(__file__).resolve().parents[5]
# Icon folders by name prefix; every other icon belongs to the core.
PLUGIN_FOLDERS = (
    ("geometry_", "src/plugins/geometry/assets/icons"),
    ("propulsion_", "src/plugins/electrical_propulsion/assets/icons"),
    ("aero_", "src/plugins/aerodynamics/assets/icons"),
    ("flight_performance", "src/plugins/flight_performance/assets/icons"),
    ("debug_", "devtools/debug-plugin/src/setuav_debug/assets/icons"),
)
CORE_FOLDER = "src/setuav_studio/assets/icons"


def destination(name):
    """The SVG file of icon ``name``, or None for an icon that belongs to no Studio
    folder; those are written only with ``--out``."""
    if name.startswith("manufacturing"):
        return None
    folder = next((path for prefix, path in PLUGIN_FOLDERS if name.startswith(prefix)), CORE_FOLDER)
    return STUDIO / folder / f"{name}.svg"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("names", nargs="*", help="icons to write (default: all)")
    parser.add_argument("--out", type=Path, help="write every icon into this folder instead")
    args = parser.parse_args()
    unknown = sorted(set(args.names) - set(ICONS))
    if unknown:
        parser.error(f"unknown icons: {', '.join(unknown)}")
    scenes = {name: fn() for name, fn in ICONS.items()}
    scales = {}
    for family in FAMILIES:
        shared = min(scenes[name].natural_scale() for name in family)
        scales.update(dict.fromkeys(family, shared))
    skipped = []
    for name in args.names or sorted(scenes):
        path = args.out / f"{name}.svg" if args.out else destination(name)
        if path is None:
            skipped.append(name)
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(scenes[name].svg(scales.get(name)))
        print(path)
    if skipped:
        print("not written (pass --out):", ", ".join(skipped))


if __name__ == "__main__":
    main()
