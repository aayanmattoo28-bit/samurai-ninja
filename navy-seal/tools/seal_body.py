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
SHOULDER = V((0.219, 0.015, 1.457))     # humeral head: the deltoid adds ~8 cm outside it
ELBOW = V((0.305, 0.030, 1.170))
WRIST = V((0.337, -0.080, 0.925))
# the right arm hangs ~2 deg further out (measured on all four views); stored with +X sign, mirrored on use.
# Lateral spread centred between the sheet's back view and its (wider) front view.
ARM_R = (V((0.219, 0.015, 1.457)), V((0.317, 0.030, 1.170)), V((0.350, -0.075, 0.925)))
HIP = V((0.100, -0.006, 0.900))
KNEE = V((0.197, -0.010, 0.480))
ANKLE = V((0.240, 0.100, 0.100))
TOE_OUT = math.radians(19)

# --- torso cross-sections of the suit: (z, half-width, front depth, back depth) ---------------------------
# Natural upright posture: lumbar curve (back depth smallest at z ~1.10), chest carried forward, trapezius sloping
# ~23 deg from the neck (X 0.075, Z 1.605) to the shoulder (X 0.18, Z 1.555); the waist and pelvis fit inside the
# belt (inner 0.186 x 0.126) and the plate bags; glutes, pecs, scapulae, lats and the spine are added by _relief().
TORSO = [
    (0.800, 0.060, 0.062, 0.070),
    (0.840, 0.155, 0.098, 0.112),
    (0.880, 0.198, 0.110, 0.134),
    (0.920, 0.208, 0.115, 0.140),
    (0.960, 0.205, 0.118, 0.138),
    (0.990, 0.182, 0.118, 0.120),
    (1.020, 0.178, 0.118, 0.113),
    (1.050, 0.177, 0.119, 0.110),
    (1.080, 0.173, 0.122, 0.107),
    (1.140, 0.169, 0.126, 0.107),
    (1.200, 0.175, 0.132, 0.114),
    (1.260, 0.185, 0.140, 0.124),
    (1.320, 0.195, 0.147, 0.134),
    (1.380, 0.201, 0.145, 0.139),
    (1.440, 0.203, 0.139, 0.139),
    (1.490, 0.204, 0.120, 0.130),
    (1.530, 0.197, 0.098, 0.114),
    (1.555, 0.180, 0.080, 0.097),
    (1.575, 0.140, 0.071, 0.084),
    (1.590, 0.100, 0.069, 0.073),
    (1.605, 0.074, 0.070, 0.060),
    (1.620, 0.062, 0.074, 0.046),
]
TORSO_Z0, TORSO_Z1 = 0.80, 1.62
# superellipse exponent by height: round neck/trapezius and waist, squarer chest and pelvis
TORSO_E = [(0.80, 2.4), (0.92, 2.6), (1.00, 2.3), (1.14, 2.3), (1.32, 2.6), (1.44, 2.6), (1.53, 2.3), (1.60, 2.1),
           (1.62, 2.1)]


def superellipse(theta, rx, ryf, ryb, e=2.6):
    s, c = math.sin(theta), math.cos(theta)
    x = math.copysign(abs(s) ** (2.0 / e), s) * rx
    ry = ryf if c > 0 else ryb
    y = -math.copysign(abs(c) ** (2.0 / e), c) * ry
    return x, y


def _tbump(x, c, w):
    return math.exp(-((x - c) / w) ** 2)


def _tbump2(x, c, lo, hi):
    """Gaussian with different spreads below/above the centre (sharp lower border of a pec or a buttock)."""
    return math.exp(-((x - c) / (lo if x < c else hi)) ** 2)


def _relief(x, y, z, rx, ryf, ryb):
    """Muscle masses under the drysuit as an outward offset (m) at the base-section point (x, y, z)."""
    ax = abs(x)
    f = clamp(-y / ryf, 0.0, 1.0) ** 2           # facing front
    b = clamp(y / ryb, 0.0, 1.0) ** 2            # facing back
    s = clamp(ax / rx, 0.0, 1.0) ** 4            # facing sideways
    d = 0.0
    # front: pectorals with a crisp lower border, sternal groove, upper abs
    d += 0.0085 * _tbump(ax, 0.088, 0.055) * _tbump2(z, 1.385, 0.032, 0.070) * f
    d -= 0.0040 * _tbump(ax, 0.0, 0.016) * _tbump(z, 1.37, 0.07) * f
    d += 0.0030 * _tbump(ax, 0.042, 0.026) * _tbump(z, 1.17, 0.07) * f
    w = gusset_halfwidth(z)
    if w > 0.0:  # the ribbed stretch gusset over the fly bulges as a shield proud of the thigh fronts
        d += 0.012 * math.sqrt(max(0.0, 1.0 - (ax / w) ** 2)) * smooth((0.985 - z) / 0.03) * f
    # back: scapulae / infraspinatus, erector columns either side of the spine groove, lats flaring under the arms
    d += 0.0070 * _tbump(ax, 0.098, 0.045) * _tbump(z, 1.405, 0.065) * b
    d += 0.0055 * _tbump(ax, 0.038, 0.020) * _tbump(z, 1.10, 0.10) * b
    d -= 0.0060 * _tbump(ax, 0.0, 0.017) * smooth((z - 0.99) / 0.05) * smooth((1.50 - z) / 0.08) * b
    d += 0.0110 * _tbump(ax / rx, 0.86, 0.20) * clamp(y / ryb + 0.25, 0.0, 1.0) * _tbump(z, 1.31, 0.075)
    # glutes: two round lobes with the gluteal fold underneath and a shallow cleft the cloth bridges over
    d += 0.0200 * _tbump(ax, 0.095, 0.080) * _tbump2(z, 0.905, 0.030, 0.070) * b
    d -= 0.0070 * _tbump(ax, 0.0, 0.015) * _tbump2(z, 0.870, 0.060, 0.050) * b
    # flanks: obliques rolling over the belt top, gluteus medius under it
    d += 0.0040 * _tbump(z, 1.072, 0.018) * s
    d += 0.0050 * _tbump(z, 0.955, 0.035) * s
    return d


def gusset_halfwidth(z):
    """Half-width of the shield-shaped crotch gusset below the belt (0 outside z 0.805-0.985)."""
    if not 0.805 < z < 0.985:
        return 0.0
    return 0.095 * clamp((z - 0.805) / 0.115) ** 0.6


def body_pt(theta, z, off=0.0, e=None):
    """Point on the suit torso surface.  theta=0 front (-Y), +90deg = character left (+X); off = outward offset."""
    rx, ryf, ryb = interp_smooth(TORSO, z)
    if e is None:
        e = interp_smooth(TORSO_E, z)[0]
    x, y = superellipse(theta, rx, ryf, ryb, e)
    d = off + _relief(x, y, z, rx, ryf, ryb)
    return V((x, y, z)) + V((math.sin(theta), -math.cos(theta), 0)) * d


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


def arm_path(side=1, n=72):
    """Arm axis from inside the trapezius (sloping down over the humeral head) through the elbow to the wrist,
    resampled evenly so that an index fraction is also the arc-length fraction that limb() uses."""
    sh, el, wr = arm_joints(side)
    pts = [V((0.120, 0.014, 1.503)), V((0.176, 0.015, 1.491)), sh, (sh + el) / 2 + V((0.004, 0.0, 0.0)), el,
           (el + wr) / 2 + V((0.005, 0.004, 0.0)), wr]
    return [mirror(p, side) for p in L.resample(catmull_path([V(p) for p in pts], 8), n)]


# sleeve half-depth (front/back, along the limb N axis) and half-width (lateral) along the arm, t = arc-length
# fraction from the trapezius root (0) to the wrist (1): shoulder joint t~0.16, deltoid belly 0.23, deltoid
# insertion 0.33, elbow 0.60, forearm swell 0.67, gauntlet top 0.81
ARM_DEPTH = [(0.0, 0.058), (0.08, 0.068), (0.16, 0.080), (0.23, 0.083), (0.33, 0.078), (0.42, 0.073), (0.52, 0.063),
             (0.60, 0.057), (0.67, 0.057), (0.80, 0.049), (0.90, 0.044), (1.0, 0.041)]
ARM_WIDTH = [(0.0, 0.055), (0.08, 0.058), (0.16, 0.061), (0.23, 0.063), (0.33, 0.062), (0.42, 0.059), (0.52, 0.055),
             (0.60, 0.054), (0.67, 0.057), (0.80, 0.051), (0.90, 0.046), (1.0, 0.044)]
ELBOW_PAD_U = 0.50   # elbow pad centre, radians from the back of the elbow toward the outside


def _g(x, c, w):
    return math.exp(-((x - c) / w) ** 2)


def arm_shape(t, u, side=1):
    """Smooth sleeve envelope over an athletic arm, without fabric folds (u = 0 front, pi back, the outside is
    u = -side*pi/2): deltoid cap sloping into the trapezius, biceps/triceps, elbow with olecranon and inner hollow,
    brachioradialis/flexor swell below the elbow tapering to the wrist.  Gear sits on this surface."""
    a = interp_smooth(ARM_DEPTH, t)[0]
    b = interp_smooth(ARM_WIDTH, t)[0]
    cu, su = math.cos(u), math.sin(u)
    lat = -su * side                      # +1 outside, -1 inside (armpit / inner arm)
    front, back = max(0.0, cu), max(0.0, -cu)
    r = a * b / math.sqrt((b * cu) ** 2 + (a * su) ** 2)
    r += 0.010 * max(0.0, lat) ** 1.3 * _g(t, 0.225, 0.075)                         # lateral deltoid cap
    r += 0.003 * (front + back) * _g(t, 0.20, 0.05)                                  # anterior/posterior heads
    r -= 0.005 * max(0.0, -lat) ** 2 * smooth((t - 0.12) / 0.06) * smooth((0.36 - t) / 0.06)   # armpit hollow
    r += 0.005 * front ** 2 * _g(t, 0.43, 0.06)                                      # biceps belly
    r += 0.010 * front ** 1.5 * smooth((t - 0.22) / 0.06) * smooth((0.52 - t) / 0.06)  # sleeve slack in front
    r += 0.005 * max(0.0, 0.8 * back + 0.4 * lat) ** 2 * _g(t, 0.37, 0.07)           # triceps (lateral head)
    r -= 0.006 * front ** 3 * _g(t, 0.585, 0.025)                                   # inner-elbow hollow
    r += 0.004 * back ** 4 * _g(t, 0.605, 0.02)                                      # olecranon
    r += 0.003 * max(0.0, -lat) * back * _g(t, 0.595, 0.02)                         # medial epicondyle
    r += 0.006 * max(0.0, 0.7 * front + 0.7 * lat) ** 2 * _g(t, 0.665, 0.045)        # brachioradialis/extensors
    r += 0.005 * max(0.0, 0.6 * front - 0.8 * lat) ** 2 * _g(t, 0.69, 0.05)          # flexor mass
    return r


def arm_radius(t, u, side=None):
    """Drysuit sleeve = arm_shape + fabric: soft pipe folds hanging from the shoulder round the back, front and inside
    of the baggy upper sleeve (the outside carries the pocket), a gathered double roll above the elbow pad, compression
    folds in the inner elbow, soft pleats below it, two long spiral folds down the forearm and the fabric bunched
    where it enters the gauntlet; flat under the strapped elbow pad.  Without `side` the sampled lateral face is
    taken as the outside (callers asking for the outer radius at u = -side*pi/2)."""
    if side is None:
        side = 1 if math.sin(u) <= 0 else -1
    r = arm_shape(t, u, side)
    cu, su = math.cos(u), math.sin(u)
    lat = -su * side
    front = max(0.0, cu)
    n = fbm(V((t * 4.0, cu * 1.1, su * 1.1 + side)))
    n3 = fbm(V((t * 2.0, cu * 0.7, su * 0.7 + 3.0 * side)))
    # the elbow pad footprint (back-outer face, t 0.53-0.74) presses the fabric flat
    du = math.acos(clamp(-cu * math.cos(ELBOW_PAD_U) + lat * math.sin(ELBOW_PAD_U), -1.0, 1.0))
    free = 1.0 - smooth((1.15 - du) / 0.3) * smooth((t - 0.51) / 0.025) * smooth((0.765 - t) / 0.025)
    # pipe folds: rounded ridges with narrow valleys, leaning diagonally toward the back, each of its own length
    up = smooth((t - 0.20) / 0.06) * smooth((0.50 - t) / 0.05)
    off_pocket = smooth((0.42 - t) / 0.04) * smooth((0.45 - lat) / 0.3) + smooth((t - 0.40) / 0.04)
    ph = u * 14 / TAU * side + 0.9 * n3 + (t - 0.20) * 3.0 * (0.3 + 0.7 * cu)                  # 14 round the arm
    length = smooth((0.1 + fbm(V((math.floor(ph + 0.5) % 14 * 1.7, 0.0, 5.0 + side))) + (t - 0.20) * 2.5) / 0.35)
    crest = (0.5 + 0.5 * math.cos(ph * TAU)) ** 2 * length - 0.2     # zero at the valleys: no seams
    r += 0.0055 * up * min(1.0, off_pocket) * crest * (1.0 - 0.4 * front) * free
    # gathered double roll just above the pad, dipping toward the back
    tr = 0.484 + 0.010 * cu
    roll = 0.0055 * _g(t, tr, 0.016) + 0.0025 * _g(t, tr - 0.034, 0.012)
    r += roll * (0.45 + 0.55 * smooth((0.3 - cu) / 0.6)) * (1.0 + 0.25 * math.sin(u * 3 * side + 2.0 * n))
    # compression folds round the inner elbow: chevrons that open toward the sides and fade at the back
    w = (t - 0.585) / 0.017 + 1.2 * (1.0 - cu) + 0.4 * n
    r += 0.0042 * front ** 1.5 * smooth((t - 0.53) / 0.03) * smooth((0.645 - t) / 0.03) * \
        (max(0.0, math.cos(w * math.pi)) ** 2 - 0.25)
    # soft pleats below the elbow, strongest on the front/inner side, then two long spiral folds
    pl = smooth((t - 0.635) / 0.02) * smooth((0.78 - t) / 0.02)
    ph = (t - 0.635) / 0.019 + 0.3 * su * side + 0.2 * cu + 0.35 * n
    r += 0.0045 * pl * ((0.5 + 0.5 * math.sin(ph * TAU)) ** 2 - 0.375) * (0.55 + 0.45 * front) * free * \
        (0.6 + 0.4 * smooth((0.25 + n3) / 0.5))
    r += 0.0025 * math.sin(u * 2 * side + t * 50 + 1.5 * n) * smooth((t - 0.70) / 0.04) * \
        smooth((0.81 - t) / 0.025) * free
    r += 0.004 * _g(t, 0.80, 0.012) * (1.0 + 0.3 * math.sin(u * 4 + 2 * n))          # bunched over the gauntlet
    return r


def leg_path(side=1):
    top = V((0.093, 0.010, 1.000))
    # the femur shaft bows slightly forward/outward; the shank runs straight from the knee to the ankle
    pts = [top, HIP, (HIP + KNEE) / 2 + V((0.006, -0.006, 0)), KNEE, (KNEE + ANKLE) / 2, ANKLE]
    return [mirror(p, side) for p in catmull_path([V(p) for p in pts], 6)]


# trouser half-depths (front, back: N axis) and half-widths (outer, inner) along the leg; t = 0 at the hip top (z 1.00),
# 0.2 hip joint (0.90), 0.3 crotch (0.80), 0.4 mid-thigh (0.69), 0.6 knee (0.48), 0.7 calf (0.38), 0.84 boot top (0.25),
# 1 ankle (0.10).  Measured girths: upper thigh 0.22 x 0.23, mid-thigh 0.20 x 0.20, knee 0.15 x 0.14, calf 0.165 x 0.17;
# below the calf the cloth hangs straight, bunches over the boot top and tucks into the shaft (inner 0.085 / 0.075)
LEG_DEPTH = [(0.0, 0.108, 0.128), (0.10, 0.110, 0.138), (0.167, 0.112, 0.142), (0.20, 0.112, 0.140),
             (0.233, 0.112, 0.134), (0.267, 0.112, 0.124), (0.30, 0.111, 0.114), (0.333, 0.110, 0.108),
             (0.367, 0.108, 0.104), (0.40, 0.104, 0.099), (0.433, 0.099, 0.094), (0.467, 0.092, 0.088),
             (0.50, 0.085, 0.082), (0.533, 0.077, 0.077), (0.567, 0.071, 0.073), (0.60, 0.069, 0.072),
             (0.633, 0.069, 0.076), (0.667, 0.071, 0.083), (0.70, 0.073, 0.088), (0.733, 0.075, 0.090),
             (0.767, 0.078, 0.088), (0.80, 0.082, 0.087), (0.818, 0.085, 0.089), (0.832, 0.086, 0.089),
             (0.841, 0.075, 0.078), (0.853, 0.071, 0.074), (0.90, 0.069, 0.072), (1.0, 0.066, 0.070)]
LEG_WIDTH = [(0.0, 0.106, 0.100), (0.10, 0.110, 0.104), (0.167, 0.115, 0.108), (0.20, 0.117, 0.110),
             (0.233, 0.117, 0.112), (0.267, 0.115, 0.113), (0.30, 0.112, 0.112), (0.333, 0.107, 0.108),
             (0.367, 0.102, 0.102), (0.40, 0.094, 0.096), (0.433, 0.088, 0.090), (0.467, 0.084, 0.085),
             (0.50, 0.081, 0.081), (0.533, 0.077, 0.077), (0.567, 0.074, 0.074), (0.60, 0.073, 0.073),
             (0.633, 0.074, 0.075), (0.667, 0.078, 0.080), (0.70, 0.081, 0.084), (0.733, 0.082, 0.085),
             (0.767, 0.081, 0.083), (0.80, 0.080, 0.081), (0.818, 0.083, 0.083), (0.832, 0.083, 0.083),
             (0.841, 0.066, 0.066), (0.853, 0.062, 0.062), (0.90, 0.061, 0.061), (1.0, 0.060, 0.060)]
# muscle masses under the cloth: (t, t spread, u, u spread, height); u for the LEFT leg (outer side u < 0)
LEG_MUSCLES = [
    (0.37, 0.07, 0.0, 0.55, 0.005),          # rectus femoris
    (0.36, 0.07, -0.9, 0.42, 0.005),         # vastus lateralis (the drop-leg panels cover the outer thigh)
    (0.475, 0.035, 0.85, 0.42, 0.007),       # vastus medialis teardrop above the inner knee
    (0.31, 0.06, 1.75, 0.5, 0.004),          # adductors
    (0.37, 0.08, math.pi, 0.75, 0.004),      # hamstrings
    (0.262, 0.016, math.pi, 0.8, -0.005),    # gluteal fold
    (0.595, 0.02, math.pi, 0.45, -0.004),    # hollow behind the knee
    (0.695, 0.05, 2.4, 0.6, 0.013),          # gastrocnemius, inner head (larger, lower)
    (0.68, 0.045, -2.5, 0.55, 0.009),        # gastrocnemius, outer head
]


def leg_base(t, u, side=1):
    """Smooth trouser surface without folds: four elliptical quadrants plus the muscle masses (u = 0 front, pi back;
    the outer side is u = -side * pi / 2)."""
    uc = u * side
    af, ab = interp_smooth(LEG_DEPTH, t)
    bo, bi = interp_smooth(LEG_WIDTH, t)
    cu, su = math.cos(uc), math.sin(uc)
    a = af if cu > 0 else ab
    b = bo if su < 0 else bi
    r = a * b / math.sqrt((b * cu) ** 2 + (a * su) ** 2)
    for t0, dt, u0, du, h in LEG_MUSCLES:
        d = (uc - u0 + math.pi) % TAU - math.pi
        r += h * math.exp(-((t - t0) / dt) ** 2 - (d / du) ** 2)
    return r


def leg_radius(t, u, side=1):
    """Loose combat trousers over an athletic leg: soft vertical drape on the thigh, compression folds fanning from
    the crotch, a roll over the knee-pad top, horizontal folds behind the knee, long folds down the shin and soft
    rolls bunched over the boot top before the cloth tucks into the shaft."""
    uc = u * side
    r = leg_base(t, u, side)
    cu = math.cos(uc)
    back = smooth((-cu - 0.25) / 0.4)
    ph = 2.2 * fbm(V((uc * 0.8, t * 2.5, 1.3)))
    thigh = smooth((t - 0.26) / 0.06) * smooth((0.50 - t) / 0.06)
    r += (0.0042 * math.sin(uc * 4 + ph) + 0.0016 * math.sin(uc * 9 - 1.5 * ph)) * thigh                 # drape
    r += 0.0028 * max(0.0, math.sin((t - 0.30) / 0.032 * TAU + 1.3 * uc + ph)) ** 1.5 * thigh * \
        smooth((cu + 0.2) / 0.6)                                                       # pulls across the thigh front
    inner = math.exp(-((uc - 1.6) / 0.65) ** 2)
    r += 0.0040 * max(0.0, math.sin((t - 0.17) / 0.019 * TAU + 1.4 * uc)) ** 1.5 * inner * \
        smooth((t - 0.17) / 0.03) * smooth((0.32 - t) / 0.04)                                             # crotch
    r += 0.0065 * math.exp(-((t - 0.486) / 0.010) ** 2) * smooth((cu + 0.1) / 0.5)                     # pad-top roll
    gap = 1.0 - math.exp(-((t - 0.533) / 0.012) ** 2)  # the upper knee strap presses the folds flat
    r += 0.0055 * max(0.0, math.sin((t - 0.49) / 0.018 * TAU + 0.5 * math.cos(2 * uc))) ** 1.5 * back * gap * \
        smooth((t - 0.49) / 0.015) * smooth((0.575 - t) / 0.012)                                       # knee pit
    r += 0.0022 * math.sin(uc * 5 + t * 22 + ph) * smooth((t - 0.63) / 0.04) * smooth((0.80 - t) / 0.03)  # shin
    roll = (t - 0.79) / 0.016 * TAU + 2.2 * fbm(V((uc * 1.2, t * 10, 2.7))) + 0.9 * math.sin(3 * uc + 1.0)
    w = smooth((t - 0.79) / 0.01) * smooth((0.836 - t) / 0.006)
    r += (0.0055 * max(0.0, math.sin(roll)) ** 1.5 * max(0.0, 0.55 + 0.9 * fbm(V((uc * 1.6, 0.4, t * 5)))) +
          0.0026 * math.sin(uc * 7 + 2 * ph)) * w                                                    # boot bunch
    return r


def trouser_md(path, side, t_end=0.867, nt=210, nth=48):
    """One trouser leg evaluated at the same (t, u) as limb_pt so the leg gear sits on it; ring frames are smoothed
    over a few rings, the top is capped inside the pelvis and the open bottom ends inside the boot (z ~0.22)."""
    ts = [t_end * k / nt for k in range(nt + 1)]
    pts = [limb_frame(path, t)[0] for t in ts]
    fr = []
    for j in range(nt + 1):
        T = (pts[min(nt, j + 3)] - pts[max(0, j - 3)]).normalized()
        N = V((0.0, -1.0, 0.0))
        N = (N - T * N.dot(T)).normalized()
        fr.append((N, T.cross(N)))
    md = grid(lambda u, v, i, j: pts[j] + (fr[j][0] * math.cos(u) + fr[j][1] * math.sin(u)) *
              leg_radius(ts[j], u, side), lin(0, TAU, nth), list(range(nt + 1)), closed_u=True)
    c = len(md.v)
    md.v.append(pts[0].copy())
    for a in range(nth):
        md.f.append(((a + 1) % nth, a, c))
        md.uv.append([(0.5, 0.5)] * 3)
        md.mi.append(0)
    return md


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
# Hand frame: wrist joint at the origin, local -Z toward the fingertips, +X the back of the hand, -Y the thumb (radial)
# edge -- LEFT-hand convention, the right hand is its mirror.
HAND_POSE = {  # palmar flexion from the forearm line, deviation toward the body, back of the hand turned forward (deg)
    "relaxed": (8.0, -2.0, 35.0),   # hangs ~15 deg forward in line with the forearm, mid-prone: the back faces out
    "grip": (10.0, -20.0, 85.0),    # right fist on the carbine: its back faces the front, ulnar-deviated
}


def _hand_rot(side=1, pose="relaxed"):
    """Unmirrored hand axes (columns X, Y, Z), the wrist and the unit forearm direction (wrist -> elbow)."""
    sh, el, wr = arm_joints(side)
    fa = (wr - el).normalized()
    ext, dev, turn = (math.radians(a) for a in HAND_POSE[pose])
    pitch = math.atan2(-fa.y, -fa.z) - ext
    lat = math.atan2(fa.x, -fa.z) - dev
    z = V((-math.tan(lat), math.tan(pitch), 1.0)).normalized()
    x = V((math.cos(turn), -math.sin(turn), 0.0))
    x = (x - z * x.dot(z)).normalized()
    return Matrix((x, z.cross(x), z)).transposed(), V(wr), -fa


def hand_matrix(side=1, grip=False):
    """Wrist frame for the LEFT hand (mirrored for the right): local -Z points to the fingertips (forward-down),
    +X is the back of the hand (outward, turned forward), the thumb sits on the local -Y (front) edge.  The relaxed
    hand hangs a little straighter than the forearm, clear of the thigh rig; grip=True is the right fist that holds
    the carbine in the FRONT view."""
    r, wr, _ = _hand_rot(side, "grip" if grip else "relaxed")
    m = r.to_4x4()
    m.translation = wr
    if side < 0:
        m = Matrix.Scale(-1, 4, (1, 0, 0)) @ m
    return m


FINGERS = [  # index .. little: MCP joint centre, phalanx lengths (proximal, middle, distal), gloved radius, splay (deg)
    ((0.000, -0.0315, -0.097), (0.043, 0.026, 0.020), 0.0114, -4.0),
    ((0.003, -0.0105, -0.100), (0.047, 0.030, 0.021), 0.0118, -1.0),
    ((0.001, 0.0100, -0.096), (0.044, 0.028, 0.020), 0.0111, 2.0),
    ((-0.004, 0.0290, -0.088), (0.034, 0.022, 0.018), 0.0098, 5.0),
]
CURL = {  # MCP, PIP, DIP flexion (deg) per finger, index .. little, and how much of the splay each pose keeps
    "relaxed": (((22, 36, 16), (30, 46, 22), (38, 54, 26), (45, 58, 30)), 0.7),
    "half_fist": (((34, 52, 28), (40, 60, 32), (46, 64, 36), (52, 68, 38)), 0.5),
    "grip": (((48, 48, 67), (60, 54, 61), (58, 54, 58), (48, 36, 67)), 0.0),  # wrapped round GRIP_FIST
}
THUMB = {  # CMC (inside the thenar), MCP, IP and tip joint centres
    "relaxed": ((-0.008, -0.024, -0.018), (-0.029, -0.050, -0.055), (-0.042, -0.058, -0.083), (-0.050, -0.054, -0.103)),
    "half_fist": ((-0.008, -0.024, -0.018), (-0.030, -0.049, -0.054), (-0.046, -0.051, -0.083),
                  (-0.052, -0.043, -0.103)),
    "grip": ((-0.008, -0.024, -0.018), (-0.036, -0.046, -0.044), (-0.060, -0.050, -0.066), (-0.069, -0.046, -0.088)),
}
# the carbine's pistol grip in the right fist: centre and axis (index -> little side, rising 11 deg toward the wrist on
# the little-finger side: an oblique power grip); with the ulnar deviation the grip points out from the thigh and the
# carbine hangs in profile
GRIP_FIST = (V((-0.039, 0.004, -0.082)), V((0.0, math.cos(math.radians(11)), math.sin(math.radians(11)))))
# palm loft: (fraction to the knuckle line, half-width, back half-thickness, palm half-thickness)
PALM = [(0.0, 0.034, 0.0185, 0.0195), (0.3, 0.040, 0.0180, 0.0190), (0.6, 0.0455, 0.0172, 0.0185),
        (0.85, 0.0475, 0.0165, 0.0178), (1.0, 0.0480, 0.0160, 0.0172)]


def _gauss(x):
    return math.exp(-x * x)


def _win(x, a, b, w=0.12):
    return smooth((x - a) / w) * smooth((b - x) / w)


def _knuckle_z(y):
    """z of the MCP joint line across the hand (oblique: the little finger's knuckle sits highest)."""
    tab = [(-0.06, -0.090)] + [(f[0][1], f[0][2]) for f in FINGERS] + [(0.05, -0.080)]
    return interp_smooth(tab, y)[0]


def palm_pt(u, v):
    """Glove surface of the palm / back of the hand: u around the hand axis (0 = back, pi/2 = thumb edge, pi = palm),
    v from the wrist (0) to the rounded knuckle end (1)."""
    e = 2.5
    cu, su = math.cos(u), math.sin(u)
    sx = math.copysign(abs(cu) ** (2.0 / e), cu)
    sy = math.copysign(abs(su) ** (2.0 / e), su)
    vb = min(v / 0.78, 1.0)
    a = max(0.0, (v - 0.78) / 0.22) * math.pi / 2
    w, td, tp = interp_smooth(PALM, vb)
    y = -sy * w
    if sx >= 0:
        x = sx * td * (1.0 + 0.06 * _win(vb, 0.25, 0.75, 0.15))                       # padded back panel
    else:
        x = sx * tp
        pal = -sx
        pad = 0.010 * _gauss((y + 0.027) / 0.015) * _win(vb, 0.0, 0.62, 0.15)          # thenar
        pad += 0.0055 * _gauss((y - 0.030) / 0.013) * _win(vb, 0.12, 0.85, 0.12)       # hypothenar
        pad -= 0.0040 * _gauss(y / 0.017) * _win(vb, 0.30, 0.72, 0.12)                 # palm hollow
        pad += 0.0030 * _win(vb, 0.84, 1.2, 0.06)                                      # pads under the knuckles
        x -= pad * pal ** 0.7
    zk = _knuckle_z(y) + 0.011
    z = lerp(0.012, zk, vb)
    # rounded knuckle end; it reaches further on the palm side (the finger webs lie beyond the knuckles)
    lend = 0.012 + 0.011 * max(0.0, -cu)
    s = math.cos(a)
    return V((x * s, y * s, z - lend * math.sin(a)))


def _surf_n(fn, u, v, du=1e-3, dv=1e-3):
    a, b = fn(u - du, v), fn(u + du, v)
    c, d = fn(u, v - dv), fn(u, v + dv)
    n = (b - a).cross(d - c)
    return n.normalized() if n.length > 1e-12 else V((1, 0, 0))


def _finger(k, angles, splay_k=1.0):
    """Joint centres (MCP, PIP, DIP, tip) of finger k flexed by its (MCP, PIP, DIP) angles."""
    (mx, my, mz), segs, r0, spl = FINGERS[k]
    s = math.radians(spl * splay_k)
    dist = V((0.0, math.sin(s), -math.cos(s)))
    palm = V((-1.0, 0.0, 0.0))
    pts, acc = [V((mx, my, mz))], 0.0
    for ang, ln in zip(angles, segs):
        acc += math.radians(ang)
        pts.append(pts[-1] + (dist * math.cos(acc) + palm * math.sin(acc)) * ln)
    return pts, dist * math.cos(acc) + palm * math.sin(acc), dist


def _digit(joints, tip_dir, r0, root, radius_tab, n_u=12, n_t=34):
    """Gloved digit: tube through the joints from a root buried in the palm, padded segments, a domed fingertip.
    radius_tab: [(joint index, radius factor)] (knuckles slightly fuller than the phalanx shafts)."""
    rt = r0 * radius_tab[-1][1]
    pts = [root] + list(joints) + [joints[-1] + tip_dir * rt]
    lens = [0.0]
    for a, b in zip(pts, pts[1:]):
        lens.append(lens[-1] + (b - a).length)
    tot = lens[-1]
    sj = [lens[i + 1] / tot for i in range(len(joints))]         # joint positions as path fractions
    t_end = sj[-1]
    prof = [(0.0, r0 * 1.02)] + [(sj[i], r0 * f) for i, f in radius_tab]
    mids = [(sj[i] + sj[i + 1]) / 2 for i in range(len(sj) - 1)]

    def rad(t, u):
        r = interp_smooth(prof, min(t, t_end))[0]
        for m in mids:  # slimmer shafts between the knuckles
            r *= 1.0 - 0.05 * _gauss((t - m) / 0.06)
        cu, su = math.cos(u), math.sin(u)
        r *= 1.0 + 0.04 * cu * cu - 0.03 * su * su                                    # a little wider than deep
        pal = max(0.0, -su) ** 2
        for m in mids:
            r += 0.0012 * pal * _gauss((t - m) / 0.05)                                 # padded palm side
        for j in sj[1:-1]:
            r -= 0.0010 * pal * _gauss((t - j) / 0.015)                                # flexion creases
            r += 0.0008 * max(0.0, su) ** 2 * _gauss((t - j) / 0.03)                   # knuckles
        if t > t_end:
            f = min(1.0, (t - t_end) / (1.0 - t_end))
            r *= math.sqrt(max(0.0, 1.0 - f * f)) * (1.0 - 0.1 * pal * f)
        return max(r, 1e-4)

    path = L.resample(catmull_path(pts, 6), n_t)
    md = limb(path, rad, n_u, ref=(0, 1, 0))
    return md, path, sj, rad


def _pad(path, rad, t0, t1, uc, uw, h, nu=9, nt=7):
    """Moulded pad shell on a digit (path, rad from _digit): t0..t1 along it, uc +- uw around it, domed h proud,
    its edges flush with the glove."""
    fr = L.frames_along(path, up=lambda i, p: (0, 1, 0))
    n = len(path) - 1

    def fn(u, t, i, j):
        k = clamp(t, 0.0, 1.0) * n
        q = min(int(k), n - 1)
        f = k - q
        nn = fr[q][1].lerp(fr[q + 1][1], f).normalized()
        bb = fr[q][2].lerp(fr[q + 1][2], f).normalized()
        e = max(abs(2 * (t - t0) / (t1 - t0) - 1), abs(u - uc) / uw)
        return path[q].lerp(path[q + 1], f) + (nn * math.cos(u) + bb * math.sin(u)) * \
            (rad(t, u) + 0.0004 + h * (1.0 - e ** 4))

    return _outward(grid(fn, lin(uc - uw, uc + uw, nu), lin(t0, t1, nt)), path)


def _outward(md, axis_pts):
    """Flip a shell's faces if they point toward the digit axis / centre points."""
    f = md.f[len(md.f) // 2]
    a, b, c = md.v[f[0]], md.v[f[1]], md.v[f[2]]
    n = (b - a).cross(c - a)
    ctr = min(axis_pts, key=lambda p: (p - a).length)
    if n.dot(a - ctr) < 0:
        md.f = [tuple(reversed(q)) for q in md.f]
    return md


def hand_md(curl="relaxed", fore=None):
    """Gloved hand in the wrist frame -> (glove, armour): anatomical palm with thenar/hypothenar pads and a rounded
    knuckle end, four three-phalanx fingers in a natural flexion cascade, an opposable thumb rooted in the thenar,
    tapered neoprene cuff with a wrap strap; armour = moulded knuckle guard, ribbed back panel, padded finger and thumb
    segments, the strap's ladder.
    curl: a CURL/THUMB pose name or an (MCP, PIP, DIP) triple; fore: unit direction up the forearm in the hand frame."""
    if isinstance(curl, str):
        angles, splay_k = CURL[curl]
        thumb = THUMB[curl]
    else:
        angles, splay_k = [tuple(a + 4 * (k - 1) for a in curl) for k in range(4)], 0.7
        thumb = THUMB["relaxed" if curl[0] < 42 else "half_fist"]
    fore = V(fore) if fore is not None else V((0.0, 0.0, 1.0))
    md, arm = MD(), MD()
    md.add(grid(lambda u, v, i, j: palm_pt(u, v), lin(0, TAU, 32), lin(0, 1, 22), closed_u=True, pole_v1=True))
    for k in range(4):
        joints, tip_dir, dist = _finger(k, angles[k], splay_k)
        r0 = FINGERS[k][2]
        f, path, sj, rad = _digit(joints, tip_dir, r0, joints[0] - dist * 0.018,
                                  [(0, 1.0), (1, 0.95), (2, 0.89), (3, 0.84)])
        md.add(f)
        for a, b in ((sj[0], sj[1]), (sj[1], sj[2])):  # padded segments on the backs of the proximal/middle phalanges
            g = 0.16 * (b - a)
            arm.add(_pad(path, rad, a + g, b - g, math.pi / 2, 1.05, 0.0016))
    # thumb: metacarpal buried in the thenar, then proximal and distal phalanges; pad on the back of the proximal one
    tj = [V(p) for p in thumb]
    tdir = (tj[3] - tj[2]).normalized()
    t_md, t_path, t_sj, t_rad = _digit(tj[1:], tdir, 0.0128, tj[0], [(0, 1.04), (1, 0.98), (2, 0.92)], 12, 30)
    md.add(t_md)
    md.add(limb([tj[0] + V((0.004, 0.006, 0.008)), tj[0], tj[0].lerp(tj[1], 0.6), tj[1]],
                lambda t, u: 0.0165 - 0.004 * t, 12, nt=10, cap0=True, cap1=True))   # thenar muscle mass
    g = 0.15 * (t_sj[1] - t_sj[0])
    arm.add(_pad(t_path, t_rad, t_sj[0] + g, t_sj[1] - g, 2.2, 1.0, 0.0016))
    # tapered neoprene cuff: from under the sleeve end / gauntlet down over the wrist, narrowing onto the heel of the
    # hand; a velcro wrap strap round the wrist with its pull tab on the little-finger side
    cp = [fore * 0.050, fore * 0.020, V((0.0, -0.001, -0.004)), V((-0.002, -0.003, -0.016)), V((-0.003, -0.004, -0.024))]
    nc = 30
    cpath = L.resample(catmull_path(cp, 6), nc)

    def cuff_r(t, u):
        cu, su = math.cos(u), math.sin(u)
        s = smooth((t - 0.50) / 0.50)
        a_, b_ = lerp(0.0455, 0.0300, s), lerp(0.0480, 0.0405, s)          # half depth (back-palm), half width
        r = a_ * b_ / math.sqrt((b_ * cu) ** 2 + (a_ * su) ** 2)
        r += 0.0008 * max(0.0, math.sin(t * 9 * TAU)) * smooth((0.50 - t) / 0.05)    # ribbed knit (under the gauntlet)
        r += 0.0016 * smooth((t - 0.94) / 0.06)                                         # rolled lower edge
        return r

    md.add(limb(cpath, cuff_r, 32, ref=(1, 0, 0)))
    sf = L.frames_along(cpath, up=lambda i, p: (1, 0, 0))
    s0, s1 = 0.56, 0.80
    i0, i1 = int(s0 * (nc - 1)), int(math.ceil(s1 * (nc - 1)))
    md.add(limb(cpath[i0:i1 + 1], lambda t, u: cuff_r(lerp(s0, s1, t), u) + 0.0026 +
                0.0010 * smooth(math.cos(u + 0.9) * 2), 32, ref=(1, 0, 0), cap0=False))
    jm = (i0 + i1) // 2
    ct, cT, cN, cB = cpath[jm], *sf[jm]
    tab_dir = (cN * math.cos(-1.3) + cB * math.sin(-1.3)).normalized()
    md.add(L.box(0.016, 0.014, 0.004).transform(L.look_matrix(ct + tab_dir * (cuff_r(0.68, -1.3) + 0.0045), tab_dir,
                                                               cT)))
    # --- armour: moulded knuckle guard (a dome over each knuckle, two grooves), ribbed back panel, strap ladder ------
    vk = [(f[0][1]) for f in FINGERS]

    def plate(u, v):
        p = palm_pt(u, v)
        n = _surf_n(palm_pt, u, v)
        h = 0.0022
        for yk in vk:
            h += 0.0042 * _gauss((p.y - yk) / 0.0085) * _gauss((v - 0.84) / 0.045)
        h -= 0.0010 * (_gauss((v - 0.765) / 0.008) + _gauss((v - 0.90) / 0.008))
        return p + n * h

    arm.add(grid(lambda u, v, i, j: plate(u, v), lin(-1.25, 1.25, 26), lin(0.72, 0.935, 12)))

    def panel(u, v):
        p = palm_pt(u, v)
        n = _surf_n(palm_pt, u, v)
        e = max(abs(u) / 1.05, abs(v - 0.475) / 0.175)
        h = 0.0006 + 0.0011 * (1.0 - e ** 6)
        for vr in (0.39, 0.475, 0.56):  # three moulded ribs across the back of the hand
            h += 0.0017 * _gauss((v - vr) / 0.016) * (1.0 - abs(u) / 1.1) ** 0.5
        return p + n * h

    arm.add(grid(lambda u, v, i, j: panel(u, v), lin(-1.05, 1.05, 22), lin(0.30, 0.65, 22)))
    for k in range(7):  # segmented ladder across the back of the wrap strap
        u = lerp(-0.55, 0.55, k / 6)
        c, T, N, B = cpath[jm], *sf[jm]
        rr = cuff_r(0.68, u) + 0.0042
        d = N * math.cos(u) + B * math.sin(u)
        arm.add(L.box(0.0050, 0.011, 0.0026).transform(L.look_matrix(c + d * rr, d, T)))
    return md, arm


def build(coll, root):
    # --- suit torso -------------------------------------------------------------------------------------
    def torso(u, v, i, j):
        z = v
        p = body_pt(u, z)
        n = V((math.sin(u), -math.cos(u), 0))
        ax, f, b = abs(p.x), max(0.0, math.cos(u)), max(0.0, -math.cos(u))
        w = fbm(V((u * 1.3, z * 6.0, 2.1)))
        # suit compressed between the belt and the carrier: soft horizontal rolls round the waist
        d = 0.0030 * max(0.0, math.sin((z - 1.056) / 0.0105 * math.pi + 1.2 * w)) ** 1.5 * \
            smooth((z - 1.054) / 0.004) * smooth((1.090 - z) / 0.006)
        # seat: curved stress folds fanning up and out from the crotch under the glutes, and over the lower belly
        arc = (z - 0.800) - 0.55 * ax + 0.9 * (ax - 0.09) ** 2
        d += 0.0030 * max(0.0, math.sin(arc / 0.024 * TAU + 2.0 * w)) ** 1.5 * b * \
            smooth((z - 0.815) / 0.02) * smooth((0.905 - z) / 0.03) * smooth((ax - 0.025) / 0.03)
        gw = gusset_halfwidth(z)
        if gw > 0.0:  # gusset: horizontal ribs sagging to the centre, a fly seam and piped edges
            q = ax / gw
            rib = max(0.0, math.sin((z - 0.81 + 0.012 * (1 - q * q) + 0.002 * w) / 0.011 * TAU)) ** 2
            d += f * (0.0024 * rib * smooth((0.92 - q) / 0.1) * smooth((0.982 - z) / 0.008) -
                      0.0028 * math.exp(-(p.x / 0.004) ** 2) + 0.0024 * math.exp(-((q - 1.0) * gw / 0.004) ** 2))
        # upper back: diagonal drag folds from the armpits toward the spine, and soft drape everywhere else
        dg = (z - 1.30) + 0.75 * ax
        d += 0.0026 * max(0.0, math.sin(dg / 0.032 * TAU + 2.0 * w)) * b * \
            smooth((ax - 0.08) / 0.05) * smooth((z - 1.24) / 0.04) * smooth((1.50 - z) / 0.05)
        return p + n * (d + 0.0018 * fbm(p * 18))

    zs = lin(TORSO_Z0, 1.10, 100) + lin(1.10, TORSO_Z1, 60)[1:]   # 3 mm rows over the gusset ribs and seat folds
    md = grid(torso, lin(0, TAU, 128), zs, closed_u=True)
    ob = to_obj("Suit_Torso", md, M["suit"], coll, parent=root)
    cloth_mods(ob, 2, [(0.0022, 0.012, {"stretch": (1, 1, 3)}), (0.0010, 0.004, {"stretch": (6, 6, 1)})])

    # --- sleeves and trousers -----------------------------------------------------------------------------
    arms, legs = MD(), MD()
    for side in (1, -1):
        a = limb(arm_path(side), lambda t, u, s=side: arm_radius(t, u, s), 64, nt=150, cap0=True)
        arms.add(a)
        lp = leg_path(side)
        legs.add(trouser_md(lp, side, t_end=0.867))  # tucked into the boot shaft (top z 0.25), ends at z ~0.22
    # creased, slightly baggy fabric: sharp fold ridges + softer drape + fine crinkle
    ob = to_obj("Suit_Sleeves", arms, M["suit"], coll, parent=root)
    cloth_mods(ob, 2, [(0.0016, 0.045, {"stretch": (1, 1, 3), "hard": True}), (0.0010, 0.018, {"stretch": (1, 1, 2)})])
    ob = to_obj("Suit_Trousers", legs, M["suit_legs"], coll, parent=root)
    cloth_mods(ob, 2, [(0.0045, 0.035, {"stretch": (1, 1, 2.5), "hard": True}),
                       (0.0025, 0.014, {"stretch": (1, 1, 3)}), (0.001, 0.004, {"stretch": (6, 6, 1)})])

    # --- hood (neoprene) under the helmet: head ellipsoid carried forward of the shoulders, snug neck ---------
    def hood(u, v, i, j):
        z = lerp(1.480, 1.820, v)
        lean = smooth((z - 1.56) / 0.12)          # the neck leans ~20 deg: head 4.5 cm forward of the shoulders
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
    # The left glove is the same in every view.  The right one differs per view: in the FRONT figure it grips the
    # carbine (it joins that view's "Carbine_InHand_Front" collection); in the instanced LEFT/BACK/RIGHT figures it
    # hangs as a loose half-fist (it joins "Carbine_Slung", the collection only those three views instance).
    for side, pose, tag, where in ((1, "relaxed", "L", coll), (-1, "grip", "R_Grip", L.collection("Carbine_InHand_Front")),
                                   (-1, "half_fist", "R", L.collection("Carbine_Slung"))):
        grip = pose == "grip"
        r, wr, fore = _hand_rot(side, "grip" if grip else "relaxed")
        h, arm = hand_md(pose, r.transposed() @ fore)
        m = hand_matrix(side, grip)
        h.transform(m)
        arm.transform(m)
        if side < 0:
            h.f = [tuple(reversed(f)) for f in h.f]
            arm.f = [tuple(reversed(f)) for f in arm.f]
        ob = to_obj("Glove_%s" % tag, h, M["glove"], where, parent=root)
        mod_subsurf(ob, 1, 2)
        ob = to_obj("Glove_%s_Knuckle_Armour" % tag, arm, M["armour_gloss"], where, parent=root)
        L.mod_solidify(ob, 0.0025, -1.0)
        mod_subsurf(ob, 1, 1)
