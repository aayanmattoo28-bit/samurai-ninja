"""Navy SEAL anatomy: torso/pelvis tables, limbs, the black drysuit (one garment), hood/neck seal, gloved hands.

Conventions: metres, Z up, ground z=0, the character faces -Y, the character's LEFT is +X.
Anchors below are for the LEFT side; mirror x for the right.  Other modules attach to body_pt()/limb_pt().
"""
import math

from mathutils import Matrix, Vector

import seal_lib as L
from seal_lib import (MD, TAU, V, catmull_path, clamp, cloth_mods, fbm, grid, interp_smooth, lerp, limb, lin,
                      mod_subsurf, smooth, to_obj, uv_sphere)
from seal_mats import M

# --- skeleton anchors (character left side) -----------------------------------------------------------
HEAD_C = V((0.0, -0.045, 1.705))
SHOULDER = V((0.225, 0.015, 1.460))
ELBOW = V((0.300, 0.030, 1.170))
WRIST = V((0.315, -0.080, 0.925))
# the right arm hangs ~2 deg further out (measured on all four views); stored with +X sign, mirrored on use
ARM_R = (V((0.225, 0.015, 1.460)), V((0.312, 0.030, 1.170)), V((0.338, -0.075, 0.925)))
HIP = V((0.100, 0.000, 0.900))
KNEE = V((0.200, -0.005, 0.480))
ANKLE = V((0.240, 0.100, 0.100))
TOE_OUT = math.radians(19)

# --- torso cross-sections of the suit: (z, half-width, front depth, back depth) ---------------------------
TORSO = [
    (0.800, 0.080, 0.070, 0.090),
    (0.850, 0.170, 0.110, 0.150),
    (0.900, 0.195, 0.120, 0.160),
    (0.950, 0.200, 0.122, 0.155),
    (1.000, 0.185, 0.125, 0.140),
    (1.070, 0.175, 0.130, 0.130),
    (1.180, 0.180, 0.135, 0.135),
    (1.300, 0.193, 0.148, 0.142),
    (1.350, 0.200, 0.155, 0.150),
    (1.410, 0.200, 0.152, 0.148),
    (1.460, 0.196, 0.142, 0.142),
    (1.510, 0.182, 0.125, 0.132),
    (1.550, 0.155, 0.100, 0.112),
    (1.580, 0.105, 0.078, 0.088),
    (1.600, 0.070, 0.066, 0.072),
    (1.640, 0.065, 0.062, 0.066),
]
TORSO_Z0, TORSO_Z1 = 0.80, 1.64


def superellipse(theta, rx, ryf, ryb, e=2.6):
    s, c = math.sin(theta), math.cos(theta)
    x = math.copysign(abs(s) ** (2.0 / e), s) * rx
    ry = ryf if c > 0 else ryb
    y = -math.copysign(abs(c) ** (2.0 / e), c) * ry
    return x, y


def body_pt(theta, z, off=0.0, e=2.6):
    """Point on the suit torso surface.  theta=0 front (-Y), +90deg = character left (+X); off = outward offset."""
    rx, ryf, ryb = interp_smooth(TORSO, z)
    x, y = superellipse(theta, rx + off, ryf + off, ryb + off, e)
    return V((x, y, z))


def body_normal(theta, z):
    a, b = body_pt(theta - 0.01, z), body_pt(theta + 0.01, z)
    c, d = body_pt(theta, z - 0.01), body_pt(theta, z + 0.01)
    n = (b - a).cross(d - c)
    if n.length < 1e-9:
        return V((math.sin(theta), -math.cos(theta), 0))
    n.normalize()
    if n.dot(V((math.sin(theta), -math.cos(theta), 0))) < 0:
        n = -n
    return n


def mirror(p, side):
    return V((p.x * side, p.y, p.z))


# --- limbs -----------------------------------------------------------------------------------------------
def arm_joints(side=1):
    if side > 0:
        return SHOULDER, ELBOW, WRIST
    return ARM_R


def arm_path(side=1, n=24):
    sh, el, wr = arm_joints(side)
    cl = V((0.140, 0.012, 1.470))
    pts = [cl, sh, (sh + el) / 2 + V((0.006, 0.0, 0.0)), el, (el + wr) / 2 + V((0.003, 0.0, 0.0)), wr]
    return [mirror(p, side) for p in catmull_path([V(p) for p in pts], 5)]


# sleeve half-depth (front/back, along the limb N axis) and half-width (lateral) along the arm, t = 0 at the
# clavicle and 1 at the wrist (shoulder joint t~0.13, elbow t~0.59)
ARM_DEPTH = [(0.0, 0.060), (0.13, 0.085), (0.30, 0.078), (0.40, 0.075), (0.52, 0.065), (0.59, 0.060), (0.72, 0.057),
             (0.88, 0.048), (1.0, 0.044)]
ARM_WIDTH = [(0.0, 0.060), (0.13, 0.078), (0.30, 0.070), (0.40, 0.065), (0.52, 0.060), (0.59, 0.058), (0.72, 0.058),
             (0.88, 0.050), (1.0, 0.046)]


def arm_radius(t, u):
    """Elliptical baggy sleeve with posterior drape creases, a gathered roll above the elbow and accordion pleats
    below it (u = 0 front, +-pi/2 sides, pi back)."""
    a = interp_smooth(ARM_DEPTH, t)[0]
    b = interp_smooth(ARM_WIDTH, t)[0]
    cu, su = math.cos(u), math.sin(u)
    r = a * b / math.sqrt((b * cu) ** 2 + (a * su) ** 2)
    r += 0.006 * cu * cu * smooth((t - 0.20) / 0.1) * smooth((0.45 - t) / 0.1)            # biceps bulk
    back = smooth((-cu - 0.4) / 0.4)
    r += 0.004 * back * math.sin(u * 6 + 3.0 * L.fbm(V((t * 9, u, 0.3)))) * smooth((t - 0.15) / 0.05) * \
        smooth((0.45 - t) / 0.05)                                                            # drape creases
    r += 0.006 * math.exp(-((t - 0.475) / 0.022) ** 2) * (1 + 0.25 * math.sin(u * 7))     # gathered roll
    pleat = smooth((t - 0.625) / 0.01) * smooth((0.735 - t) / 0.01)
    r += 0.004 * pleat * max(0.0, math.sin((t - 0.625) * 0.653 / 0.018 * TAU)) * (1.0 if cu > -0.3 else 0.5)
    r += 0.002 * math.sin(u * 3 + t * 40) * smooth((t - 0.75) / 0.05)                     # loose diagonal wrinkles
    return r


def leg_path(side=1):
    top = V((0.095, 0.010, 1.000))
    pts = [top, HIP, (HIP + KNEE) / 2 + V((0.004, -0.004, 0)), KNEE, (KNEE + ANKLE) / 2 + V((0.0, 0.0, 0)), ANKLE]
    return [mirror(p, side) for p in catmull_path([V(p) for p in pts], 6)]


# trouser half-depth (front/back, N axis) and half-width (lateral) along the leg, t = 0 at the hip top (z 1.00),
# 1 at the ankle (z 0.10); measured girths: upper thigh z 0.82, mid-thigh 0.70, knee 0.48, calf 0.36, cuff 0.22
LEG_DEPTH = [(0.0, 0.125), (0.10, 0.122), (0.19, 0.1125), (0.32, 0.100), (0.50, 0.078), (0.57, 0.070), (0.64, 0.078),
             (0.70, 0.085), (0.80, 0.090), (0.86, 0.100), (0.90, 0.090), (1.0, 0.062)]
LEG_WIDTH = [(0.0, 0.115), (0.10, 0.112), (0.19, 0.1075), (0.32, 0.100), (0.50, 0.080), (0.57, 0.0725), (0.64, 0.078),
             (0.70, 0.0825), (0.80, 0.082), (0.86, 0.080), (0.90, 0.072), (1.0, 0.055)]


def leg_radius(t, u):
    """Baggy trousers: elliptical section, back bias at the cuff, compression folds on the inner upper thigh, folds
    behind the knee, three roll folds of the bloused cuff over the boot (z 0.205-0.27)."""
    a = interp_smooth(LEG_DEPTH, t)[0]
    b = interp_smooth(LEG_WIDTH, t)[0]
    cu, su = math.cos(u), math.sin(u)
    if cu < 0:  # the bloused cuff bulges more at the back
        a *= 1.0 + 0.12 * smooth((t - 0.80) / 0.05) * smooth((0.92 - t) / 0.03)
    r = a * b / math.sqrt((b * cu) ** 2 + (a * su) ** 2)
    r += 0.003 * math.sin(u * 6 + t * 30) * smooth((t - 0.08) / 0.1) * smooth((0.80 - t) / 0.1)
    r += 0.0035 * math.sin(t * 0.9 / 0.012 * TAU) * smooth((-cu - 0.3) / 0.3) * smooth((t - 0.46) / 0.02) * \
        smooth((0.56 - t) / 0.02)                                                    # folds behind the knee
    r += 0.006 * max(0.0, math.sin((t - 0.81) / 0.075 * 3 * math.pi)) * smooth((t - 0.81) / 0.01) * \
        smooth((0.885 - t) / 0.01)                                                   # cuff roll folds
    return r


def limb_frame(path, t):
    """Point and local frame (tangent, front-ish normal, binormal) at fraction t along a path."""
    from seal_lib import frames_along
    fr = frames_along(path, up=lambda i, p: (0, -1, 0))
    k = clamp(t, 0, 1) * (len(path) - 1)
    i = min(int(k), len(path) - 2)
    f = k - i
    p = path[i].lerp(path[i + 1], f)
    T, N, B = fr[i]
    return p, T, N, B


def limb_pt(path, radius, t, u, off=0.0):
    """Point on a limb surface at fraction t, angle u (0 = front) plus an outward offset."""
    p, T, N, B = limb_frame(path, t)
    r = radius(t, u) + off
    return p + (N * math.cos(u) + B * math.sin(u)) * r


# --- gloved hand -----------------------------------------------------------------------------------------
def hand_matrix(side=1):
    """Wrist frame for the LEFT hand (mirrored for the right): local -Z points to the fingertips (forward-down),
    +X is the back of the hand (outward, turned ~15 deg forward), the thumb sits on the local -Y (front) edge."""
    sh, el, wr = arm_joints(side)
    d = V((0.0, -0.25, -0.97)).normalized()
    z = -d
    x = V((0.97, -0.25, 0.0))
    x = (x - z * x.dot(z)).normalized()
    y = z.cross(x)
    m = Matrix((x, y, z)).transposed().to_4x4()
    m.translation = V((wr.x, wr.y, wr.z))
    if side < 0:
        m = Matrix.Scale(-1, 4, (1, 0, 0)) @ m
    return m


FINGERS = [  # (local y of the knuckle, segment lengths, radius) index .. little; index is on the thumb (front) side
    (-0.031, (0.040, 0.026, 0.019), 0.0115),
    (-0.010, (0.045, 0.029, 0.021), 0.0120),
    (0.011, (0.042, 0.028, 0.020), 0.0110),
    (0.031, (0.034, 0.022, 0.016), 0.0095),
]


def hand_md(curl=(35, 45, 25)):
    """Gloved hand in the wrist frame: palm 0.105 long x 0.100 across the knuckles x 0.045 thick, three-segment
    fingers curled toward the palm (-X) by the MCP/PIP/DIP angles, thumb on the front edge, ribbed cuff."""
    md, pads = MD(), MD()

    def palm(u, v, i, j):
        z = -lerp(0.0, 0.105, v)
        w = lerp(0.041, 0.050, smooth(v * 1.5))
        th = lerp(0.021, 0.0225, v)
        x, y = math.cos(u) * th, math.sin(u) * w
        x -= 0.006 * math.sin(math.pi * v) * max(0.0, -math.cos(u))  # palm hollow
        return V((x, y, z))

    md.add(grid(palm, lin(0, TAU, 24), lin(0, 1, 10), closed_u=True))
    for k, (yy, segs, r0) in enumerate(FINGERS):
        base = V((0.0, yy, -0.100 + (0.004 if k == 3 else 0.0)))
        pts, p, acc = [base], base, 0.0
        for seg, ln in enumerate(segs):
            acc += math.radians(curl[seg])
            p = p + V((-math.sin(acc), 0, -math.cos(acc))) * ln
            pts.append(p)
        path = catmull_path(pts, 4)
        md.add(limb(path, lambda t, u, r0=r0: r0 * (1 - 0.15 * t) * (1 + 0.05 * math.cos(u * 2)), 10, cap1=True))
        for f0 in (0.22, 0.58):  # padded segments on the back of each finger
            q = path[int(f0 * (len(path) - 1))]
            pad = uv_sphere(1.0, 10, 6)
            pad.v = [V((p_.x * 0.005, p_.y * 0.009, p_.z * 0.006)) + q + V((r0 * 0.85, 0, 0)) for p_ in pad.v]
            pads.add(pad)
    tb = [V((-0.010, -0.040, -0.020)), V((-0.020, -0.052, -0.045)), V((-0.028, -0.052, -0.070)),
          V((-0.030, -0.044, -0.090))]
    md.add(limb(catmull_path(tb, 4), lambda t, u: 0.0125 * (1 - 0.2 * t), 10, cap1=True))
    # ribbed glove cuff with two thin bands
    md.add(limb([V((0, 0, 0.050)), V((0, 0, -0.008))],
                lambda t, u: 0.047 + 0.0015 * max(0.0, math.sin(t * 0.058 / 0.005 * TAU)), 24))
    # knuckle plate with four bumps, back-of-hand ridges, wrist "ladder" band
    def kn(u, v, i, j):
        y = lerp(-0.0425, 0.0425, u)
        z = lerp(-0.080, -0.110, v)
        return V((0.0235 + 0.007 * math.sin(math.pi * u) * 0.6 + 0.004, y, z))

    pads.add(grid(kn, lin(0, 1, 12), lin(0, 1, 6)))
    for yy, _, _ in FINGERS:
        b = uv_sphere(0.009, 10, 6)
        b.v = [V((q.x * 0.6, q.y, q.z * 0.8)) + V((0.031, yy, -0.096)) for q in b.v]
        pads.add(b)
    for zz in (-0.055, -0.065, -0.075):
        pads.add(L.tube([V((0.024, -0.035, zz)), V((0.024, 0.035, zz))], 0.002, 6))
    for k in range(8):
        pads.add(L.box(0.003, 0.006, 0.012).translate((0.025, -0.028 + k * 0.008, -0.012)))
    return md, pads


def build(coll, root):
    # --- suit torso -------------------------------------------------------------------------------------
    def torso(u, v, i, j):
        z = v
        p = body_pt(u, z)
        n = V((math.sin(u), -math.cos(u), 0))
        crease = 0.003 * math.sin(u * 9 + z * 14) * smooth((1.42 - z) / 0.2) * smooth((z - 0.9) / 0.1)
        return p + n * (crease + 0.002 * fbm(p * 18))

    md = grid(torso, lin(0, TAU, 96), lin(TORSO_Z0, TORSO_Z1, 56), closed_u=True)
    ob = to_obj("Suit_Torso", md, M["suit"], coll, parent=root)
    cloth_mods(ob, 2, [(0.0025, 0.012, {"stretch": (1, 1, 3)}), (0.0012, 0.004, {"stretch": (6, 6, 1)})])

    # --- sleeves and trousers -----------------------------------------------------------------------------
    arms, legs = MD(), MD()
    for side in (1, -1):
        a = limb(arm_path(side), arm_radius, 32, nt=60, cap0=True)
        arms.add(a)
        lp = leg_path(side)
        t_end = 0.885  # the bloused cuff ends at z ~0.205, over the boot shaft
        sub = [limb_frame(lp, t_end * k / 80)[0] for k in range(81)]
        lg = limb(sub, lambda t, u: leg_radius(t * t_end, u) * (1.0 - 0.12 * smooth((t - 0.975) / 0.025)), 40,
                  cap0=True)
        legs.add(lg)
    # creased, slightly baggy fabric: sharp fold ridges + softer drape + fine crinkle
    ob = to_obj("Suit_Sleeves", arms, M["suit"], coll, parent=root)
    cloth_mods(ob, 2, [(0.0055, 0.030, {"stretch": (1.5, 1.5, 1), "hard": True}),
                       (0.003, 0.012, {"stretch": (1, 1, 3)}), (0.0012, 0.004, {"stretch": (6, 6, 1)})])
    ob = to_obj("Suit_Trousers", legs, M["suit_legs"], coll, parent=root)
    cloth_mods(ob, 2, [(0.007, 0.040, {"stretch": (1, 1, 2.5), "hard": True}),
                       (0.0035, 0.014, {"stretch": (1, 1, 3)}), (0.0012, 0.004, {"stretch": (6, 6, 1)})])

    # --- hood (neoprene) under the helmet: head ellipsoid carried forward of the shoulders, snug neck ---------
    def hood(u, v, i, j):
        z = lerp(1.480, 1.820, v)
        lean = smooth((z - 1.55) / 0.10)          # the head sits 4.5 cm forward of the shoulder line
        yc = lerp(0.0, HEAD_C.y, lean)
        k = (z - HEAD_C.z) / 0.115
        if z >= 1.62:
            s_ = math.sqrt(max(0.0, 1 - min(1.0, k * k))) if k > 0 else 1.0
            s_ = max(s_, 0.04)
            blend = smooth((z - 1.62) / 0.05)
            rx = lerp(0.065, 0.0775, blend) * (s_ if k > 0 else 1.0)
            ry = lerp(0.075, 0.100, blend) * (s_ if k > 0 else 1.0)
        else:
            rx, ry = 0.065, 0.075
        x, y = superellipse(u, rx, ry, ry, 2.2)
        fold = 0.0025 * math.sin(z * 260) * smooth((1.60 - z) / 0.04) * smooth((z - 1.50) / 0.03)
        n = V((math.sin(u), -math.cos(u), 0))
        return V((x, y + yc, z)) + n * fold

    ob = to_obj("Suit_Hood", grid(hood, lin(0, TAU, 40), lin(0, 1, 34), closed_u=True, pole_v1=True),
                M["suit_panel"], coll, parent=root)
    mod_subsurf(ob, 1, 2)

    # --- gloves ---------------------------------------------------------------------------------------------
    gl, gp = MD(), MD()
    for side in (1, -1):
        h, pads = hand_md((35, 45, 25) if side > 0 else (50, 70, 40))
        m = hand_matrix(side)
        hh = h.copy().transform(m)
        pp = pads.copy().transform(m)
        if side < 0:
            hh.f = [tuple(reversed(f)) for f in hh.f]
            pp.f = [tuple(reversed(f)) for f in pp.f]
        gl.add(hh)
        gp.add(pp)
    ob = to_obj("Gloves", gl, M["glove"], coll, parent=root)
    mod_subsurf(ob, 1, 2)
    ob = to_obj("Glove_Knuckle_Armour", gp, M["armour_gloss"], coll, parent=root)
    L.mod_solidify(ob, 0.003, -1.0)
    mod_subsurf(ob, 1, 1)
