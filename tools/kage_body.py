"""Body anchors, body-conforming surfaces, and the head / hood / scarf / kasa."""
import math

from mathutils import Matrix, Vector

from kage_lib import (MD, TAU, V, mod_wrinkle, cloth_mods, torn_profile, ang, catmull_path, clamp, fbm, grid, interp_smooth, lathe, lin, look_matrix,
                      mod_solidify, mod_subsurf, nz, sweep, to_obj, torus_md, tube, uv_sphere, smooth, lerp,
                      RNG, circle_profile, rect_profile)
from kage_mats import M

# -----------------------------------------------------------------------------
# Anchors (character's LEFT side; mirror x for the right side)
# -----------------------------------------------------------------------------
SHOULDER = V((0.212, 0.012, 1.445))
ELBOW = V((0.282, 0.035, 1.180))
WRIST = V((0.318, 0.002, 0.948))
HIP = V((0.100, 0.000, 0.920))
KNEE = V((0.188, -0.018, 0.470))
ANKLE = V((0.245, 0.006, 0.112))
HEAD_C = V((0.0, 0.0, 1.752))


def deg(a):
    return math.radians(a)


def mirror(p, side):
    return V((p.x * side, p.y, p.z))


# -----------------------------------------------------------------------------
# Body-conforming surfaces.  theta from front (-Y) toward +X (character's left).
# Tables: (z, rx, ry_front, ry_back)
# -----------------------------------------------------------------------------
CUIRASS = [
    (0.990, 0.192, 0.152, 0.138),
    (1.030, 0.190, 0.150, 0.136),
    (1.080, 0.186, 0.146, 0.133),
    (1.160, 0.189, 0.149, 0.136),
    (1.240, 0.200, 0.158, 0.143),
    (1.320, 0.212, 0.163, 0.147),
    (1.400, 0.215, 0.156, 0.143),
    (1.460, 0.207, 0.141, 0.134),
    (1.500, 0.190, 0.122, 0.120),
    (1.540, 0.140, 0.100, 0.100),
    (1.575, 0.090, 0.082, 0.084),
]

HIPS = [
    (0.200, 0.300, 0.230, 0.250),
    (0.400, 0.278, 0.212, 0.232),
    (0.600, 0.252, 0.196, 0.212),
    (0.800, 0.226, 0.178, 0.190),
    (0.950, 0.207, 0.164, 0.168),
    (1.040, 0.198, 0.158, 0.150),
    (1.100, 0.195, 0.155, 0.145),
]


def superellipse(theta, rx, ryf, ryb, e=2.5):
    s, c = math.sin(theta), math.cos(theta)
    x = math.copysign(abs(s) ** (2.0 / e), s) * rx
    ry = ryf if c > 0 else ryb
    y = -math.copysign(abs(c) ** (2.0 / e), c) * ry
    return x, y


def torso_pt(theta, z, off=0.0, table=CUIRASS, e=2.6, yoff=0.0):
    rx, ryf, ryb = interp_smooth(table, z)
    x, y = superellipse(theta, rx + off, ryf + off, ryb + off, e)
    return V((x, y + yoff, z))


def torso_normal(theta, z, table=CUIRASS):
    a = torso_pt(theta - 0.01, z, table=table)
    b = torso_pt(theta + 0.01, z, table=table)
    c = torso_pt(theta, z - 0.01, table=table)
    d = torso_pt(theta, z + 0.01, table=table)
    n = (b - a).cross(d - c)
    if n.length < 1e-9:
        return V((math.sin(theta), -math.cos(theta), 0))
    n.normalize()
    if n.dot(V((math.sin(theta), -math.cos(theta), 0))) < 0:
        n = -n
    return n


def hip_pt(theta, z, off=0.0, e=2.3):
    return torso_pt(theta, z, off, HIPS, e)


def hip_normal(theta, z):
    return torso_normal(theta, z, HIPS)


HOOD_OBJ = []

# -----------------------------------------------------------------------------
# Head, eyes, hood + mask
# -----------------------------------------------------------------------------
HOOD = [
    (1.560, 0.100, 0.096, 0.096),
    (1.600, 0.092, 0.094, 0.092),
    (1.640, 0.082, 0.098, 0.090),
    (1.680, 0.090, 0.106, 0.100),
    (1.720, 0.099, 0.109, 0.110),
    (1.760, 0.101, 0.106, 0.116),
    (1.800, 0.098, 0.099, 0.114),
    (1.840, 0.084, 0.084, 0.098),
    (1.870, 0.060, 0.058, 0.070),
    (1.892, 0.024, 0.022, 0.028),
]
EYE_Z0, EYE_Z1 = 1.739, 1.769


def build_head(coll, parent):
    # skin
    md = uv_sphere(1.0, 32, 20)
    md.v = [V((p.x * 0.079, p.y * 0.094, p.z * 0.108)) + HEAD_C + V((0, 0.002, -0.004)) for p in md.v]
    # brow ridge + nose bridge bulge on the skin (visible through the slit)
    out = []
    for p in md.v:
        d = p - HEAD_C
        if d.y < 0:
            fz = math.exp(-((p.z - 1.772) / 0.008) ** 2)
            p = p + V((0, -0.008 * fz * clamp(1 - abs(d.x) / 0.065), 0))
            fn = math.exp(-((p.z - 1.735) / 0.02) ** 2) * math.exp(-(d.x / 0.012) ** 2)
            p = p + V((0, -0.012 * fn, 0))
            # eye sockets
            for sx in (-1, 1):
                fs = math.exp(-(((d.x - sx * 0.031) / 0.017) ** 2) - ((p.z - 1.755) / 0.011) ** 2)
                p = p + V((0, 0.009 * fs, 0))
            # cheekbones
            for sx in (-1, 1):
                fc = math.exp(-(((d.x - sx * 0.040) / 0.02) ** 2) - ((p.z - 1.735) / 0.012) ** 2)
                p = p + V((0, -0.004 * fc, 0))
        out.append(p)
    md.v = out
    sk = to_obj("Head_Skin", md, M["skin"], coll, parent=parent)
    mod_subsurf(sk, 1, 2)
    # eyes (local +Z = gaze) with almond-shaped eyelid shells
    lids = MD()
    for sx in (-1, 1):
        e = uv_sphere(0.0112, 24, 16)
        ob = to_obj("Eye_" + ("L" if sx > 0 else "R"), e, M["eye"], coll, parent=parent)
        m = look_matrix(V((sx * 0.0305, -0.0755, 1.7545)), V((sx * 0.05, -1, -0.03)), (0, 0, 1))
        ob.matrix_world = m
        rl = 0.0124

        def lid_keep_factory():
            us_ = lin(0, TAU, 32)
            vs_ = lin(0, math.pi, 16)

            def fn(u, v, i, j):
                return V((rl * math.sin(v) * math.cos(u), rl * math.sin(v) * math.sin(u), rl * math.cos(v)))

            def keep(i, j):
                u = (us_[i] + us_[i + 1]) / 2
                v = (vs_[j] + vs_[j + 1]) / 2
                p = fn(u, v, 0, 0)
                if p.z < 0.25 * rl:
                    return True
                # almond aperture: wider than tall, slightly tilted
                xx = p.x / (0.97 * rl)
                ap = 0.36 * rl * max(0.0, 1 - xx * xx) ** 0.65
                yc = -0.10 * rl + 0.08 * rl * xx * sx
                return not (abs(p.y - yc) < ap)

            return grid(fn, us_, vs_, keep=keep)

        lid = lid_keep_factory()
        lid.transform(m)
        lids.add(lid)
    lo = to_obj("Eyelids", lids, M["skin"], coll, parent=parent)
    mod_solidify(lo, 0.0015, 1.0)
    mod_subsurf(lo, 1, 2)

    # hood / mask shell.  Rows are laid out so the eye opening edges follow smooth curves:
    # v in [0, A] mask (neck -> under the eyes), [A, B] the opening band, [B, 1] hood over the head.
    A, B = 0.40, 0.44
    MID = 1.754

    def open_edges(th):
        t = abs(math.degrees(math.atan2(math.sin(th), math.cos(th)))) / 46.0
        if t >= 1.0:
            return MID - 0.003, MID + 0.003, False
        lower0 = 1.737 + 0.007 * math.exp(-(math.degrees(th) / 9.0) ** 2 if abs(math.sin(th)) < 0.5 else 0.0)
        upper0 = 1.769 - 0.004 * t * t
        h = (1 - t ** 2.5) ** 0.6
        lo = MID - (MID - lower0) * h
        hi = MID + (upper0 - MID) * h
        return lo, hi, (hi - lo) > 0.009

    def hood_fn(u, v, i, j):
        th = u
        lo, hi, _ = open_edges(th)
        if v <= A:
            z = lerp(1.555, lo, v / A)
        elif v <= B:
            z = lerp(lo, hi, (v - A) / (B - A))
        else:
            z = lerp(hi, 1.892, (v - B) / (1 - B))
        p = torso_pt(th, z, 0.0, HOOD, 2.0)
        front = max(0.0, math.cos(th))
        p.y -= 0.010 * front ** 6 * math.exp(-((z - 1.715) / 0.022) ** 2)
        p.y -= 0.006 * front ** 4 * math.exp(-((z - 1.640) / 0.02) ** 2)
        n = V((math.sin(th), -math.cos(th), 0))
        w = 0.0030 * math.sin(z * 240.0 + abs(math.sin(th)) * 40) * front ** 2 * clamp((1.733 - z) / 0.04)
        w += 0.002 * fbm(V((p.x * 6, p.y * 6, p.z * 40)))
        if v <= A and front > 0.3:  # tension folds radiating from the nose bridge
            dz = z - 1.738
            dx = math.sin(th) * 0.09
            rr = math.hypot(dx, dz)
            phi = math.atan2(dz, abs(dx) + 1e-4)
            w += 0.0022 * math.sin(phi * 7 + 0.8) * smooth((rr - 0.015) / 0.03) * smooth((0.11 - rr) / 0.04) * front ** 2
        # hood gathered into vertical drape folds at the back of the head
        w += 0.005 * (1 - front) ** 1.5 * math.sin(th * 9 + 1.5 * fbm(V((math.cos(th), math.sin(th), z * 4)))) * \
            smooth((1.84 - z) / 0.12) * smooth((z - 1.58) / 0.06)
        # rolled cloth edges around the opening (mask top edge + hood front edge)
        if front > 0.5:
            k = (front - 0.5) / 0.5
            w += 0.0045 * k * math.exp(-((z - lo + 0.002) / 0.004) ** 2)
            w += 0.0050 * k * math.exp(-((z - hi - 0.003) / 0.005) ** 2)
        return p + n * w

    us = lin(0, TAU, 128)
    vs = lin(0.0, A, 26) + lin(A, B, 2)[1:] + lin(B, 1.0, 26)[1:]
    band_rows = set(range(26, 28))

    def keep(i, j):
        if j not in band_rows:
            return True
        th = (us[i] + us[i + 1]) * 0.5
        return not open_edges(th)[2]

    md = grid(hood_fn, us, vs, closed_u=True, keep=keep, pole_v1=False)
    hood = to_obj("Hood_Mask", md, M["cloth_hood"], coll, parent=parent)
    HOOD_OBJ.append(hood)
    # embroidered gold flower on the mask cheek (as in the mask detail of the concept)
    def emb(u, v, i, j):
        th = deg(lerp(17, 31, u))
        z = lerp(1.688, 1.712, v)
        p = torso_pt(th, z, 0.0, HOOD, 2.0)
        front = max(0.0, math.cos(th))
        p.y -= 0.010 * front ** 6 * math.exp(-((z - 1.715) / 0.022) ** 2)
        nrm = V((math.sin(th), -math.cos(th), 0))
        return p + nrm * 0.0065
    to_obj("Mask_Embroidery", grid(emb, lin(0, 1, 8), lin(0, 1, 8)), M["decal_mask_flower"], coll, parent=parent)
    cloth_mods(hood, 3, [(0.0018, 0.010, {"stretch": (8, 8, 1)})], 0.005, 1.0)

    # scarf / cowl: one wrapped surface with diagonal rolls and creases
    scarf = MD()

    def cowl(u, v, i, j):
        th = u
        front = max(0.0, math.cos(th))
        z = lerp(1.662, 1.476, v) - 0.050 * front ** 2 * v ** 1.4
        rx = lerp(0.074, 0.178, v ** 1.05)
        ryf = lerp(0.090, 0.158, v)
        ryb = lerp(0.082, 0.146, v)
        x, y = superellipse(th, rx, ryf, ryb, 2.2)
        radial = V((math.sin(th), -math.cos(th), 0))
        shift = 0.38 * math.sin(th) + 0.14 * math.sin(2 * th + 0.5)
        s_ = v * 3.3 + shift
        roll = 0.012 * (0.5 - 0.5 * math.cos(TAU * s_)) ** 0.7 * (0.40 + 0.60 * v)
        crease = 0.004 * math.sin(th * 5 + v * 9) * v + 0.0015 * math.sin(th * 13 - v * 11)
        p = V((x, y, z))
        p += radial * (roll + crease + 0.002 * fbm(V((p.x * 6, p.y * 6, p.z * 30))))
        p.z += 0.006 * math.sin(th * 5 + v * 4)
        return p

    scarf.add(grid(cowl, lin(0, TAU, 96), lin(0, 1, 30), closed_u=True))

    # four separate thick wraps rolled around the neck, overlapping, with dark gaps between them
    def neck_base(th, z):
        return torso_pt(th, z, 0.0, HOOD, 2.0) if z >= 1.56 else torso_pt(th, z, 0.030)

    wraps = MD()
    # (z at back, z at front, band width, thickness, extra offset, half twists, phase, side tilt)
    WRAPS = ((1.656, 1.622, 0.042, 0.016, 0.006, 0, 0.0, 0.012), (1.618, 1.574, 0.050, 0.019, 0.010, 1, 1.1, -0.016),
             (1.582, 1.530, 0.054, 0.021, 0.013, 0, 2.3, 0.018), (1.548, 1.492, 0.058, 0.018, 0.017, 1, 0.6, -0.010))
    for zb_, zf_, bw, thk, ex, half_turns, ph, tilt in WRAPS:
        pts, ups = [], []
        for k in range(144):
            th = TAU * k / 144
            front = 0.5 + 0.5 * math.cos(th)
            # diagonal, sagging wraps: tilted sideways, drooping into a loose fold at the front
            z = lerp(zb_, zf_, front ** 1.5) + tilt * math.sin(th) + 0.006 * math.sin(2 * th + ph) + \
                0.004 * fbm(V((math.cos(th) * 2, math.sin(th) * 2, ph))) - 0.012 * math.exp(-((th - math.pi * 2 * (th > math.pi)) / 0.5) ** 2)
            rad = V((math.sin(th), -math.cos(th), 0.0))
            base_r = neck_base(th, z)
            cow = cowl(th, clamp((1.662 - z) / 0.186), 0, 0)
            outer = max(V((base_r.x, base_r.y, 0)).length, V((cow.x, cow.y, 0)).length)
            pts.append(V((rad.x * outer, rad.y * outer, z)) + rad * (thk * 0.5 + ex))
            ups.append(rad + V((0, 0, 0.35)))
        prof = [(0.5 * bw * math.cos(a), 0.5 * thk * math.sin(a)) for a in lin(0, TAU, 16)]

        def sc(t, ph=ph):
            c, s_ = math.cos(TAU * t), math.sin(TAU * t)
            return (0.82 + 0.14 * math.sin(TAU * 5 * t + ph) + 0.06 * fbm(V((c * 1.5, s_ * 1.5, ph))),
                    0.80 + 0.40 * max(0.0, math.sin(TAU * 3 * t + 2 * ph)))

        wraps.add(sweep(pts, prof, up=lambda i, p, ups=ups: ups[i], closed_path=True, scale=sc,
                        twist=math.pi * half_turns))
    # front V drape tucked into the cuirass
    def drape(u, v, i, j):
        x = lerp(-0.075, 0.075, u)
        z = lerp(1.545, 1.430, v) + 0.03 * (abs(x) / 0.075) ** 2 * (1 - v)
        th = math.atan2(x, 0.12)
        p = torso_pt(th, z, 0.012)
        p.y -= 0.012 * math.sin(math.pi * u) * (1 - v)
        p.y -= 0.004 * math.sin(u * 18 + v * 3)
        return p

    scarf.add(grid(drape, lin(0, 1, 16), lin(0, 1, 8)))
    sc = to_obj("Neck_Scarf", scarf, M["cloth_hood"], coll, parent=parent)
    cloth_mods(sc, 2, [(0.003, 0.014, {"stretch": (8, 8, 1)})], 0.004, -1.0)
    wo = to_obj("Neck_Scarf_Wraps", wraps, M["cloth_hood"], coll, parent=parent)
    cloth_mods(wo, 2, [(0.0025, 0.012, {"stretch": (8, 8, 1)})])

    # shawl / capelet over the shoulders & upper back (tattered hem)
    rng = RNG

    def bottom_z(th):
        b = 0.5 - 0.5 * math.cos(th)  # 0 front, 1 back
        return lerp(1.475, 1.410, b ** 1.2)

    ragged = torn_profile(96, 0.03, 9, deep=4, tongues=2)
    SF = [(rng.uniform(0, TAU), rng.uniform(0.06, 0.12), rng.choice((-1, 1)) * rng.uniform(0.6, 1.0)) for _ in range(14)]

    def shawl(u, v, i, j):
        th = u
        zb = bottom_z(th) - ragged[i % 96] * (0.5 - 0.5 * math.cos(th))
        z = lerp(1.575, zb, v)
        off = lerp(0.010, 0.030, v)
        p = torso_pt(th, z, off)
        radial = V((math.sin(th), -math.cos(th), 0))
        fold = 0.014 * v ** 1.2 * sum(a_ * math.exp(-(math.atan2(math.sin(th - c_), math.cos(th - c_)) / w_) ** 2)
                                      for c_, w_, a_ in SF)
        p += radial * (fold + 0.003 * fbm(V((p.x * 15, p.y * 15, p.z * 3))))
        return p

    md = grid(shawl, lin(0, TAU, 96), lin(0, 1, 14), closed_u=True)
    sh = to_obj("Shawl_Cowl", md, M["cloth_hood"], coll, parent=parent)
    cloth_mods(sh, 2, [(0.0045, 0.018, {"stretch": (1, 1, 3), "hard": True})], 0.004, 1.0)


# -----------------------------------------------------------------------------
# Kasa (conical lacquered hat) with ribs, rim, finial and tassels
# -----------------------------------------------------------------------------
KASA_BASE = V((0.0, 0.006, 1.778))
KASA_R = 0.262
KASA_PROFILE = [(0.0, 0.136), (0.010, 0.130), (0.025, 0.119), (0.050, 0.101), (0.090, 0.077),
                (0.130, 0.055), (0.170, 0.035), (0.210, 0.017), (0.245, 0.004), (0.262, -0.002)]


def kasa_h(r):
    return interp_smooth([(p[0], p[1]) for p in KASA_PROFILE], r)[0]


def build_kasa(coll, parent):
    base = KASA_BASE
    prof = []
    for k in range(41):
        r = KASA_R * k / 40
        prof.append((r, kasa_h(r)))
    # main shell: u = angle, v = radius fraction  (uv v: 0 apex -> 1 rim)
    md = lathe(prof, 96, uv_v=lambda j: j / 40)
    md.translate(base)
    shell = to_obj("Kasa_Shell", md, M["lacquer_hat"], coll, parent=parent)
    mod_solidify(shell, 0.005, -1.0)
    mod_subsurf(shell, 1, 2)

    def surf(r, a, off=0.0):
        h = kasa_h(r)
        # outward normal of the cone surface
        dh = (kasa_h(r + 0.002) - kasa_h(max(0, r - 0.002))) / 0.004
        n = V((-dh * math.sin(a), dh * math.cos(a), 1.0)).normalized()
        return base + V((r * math.sin(a), -r * math.cos(a), h)) + n * off, n

    ribs = MD()
    nrib = 40
    for k in range(nrib):
        a = TAU * k / nrib
        path, ups = [], []
        for s in range(14):
            r = lerp(0.016, KASA_R - 0.004, s / 13)
            p, n = surf(r, a, 0.0035)
            path.append(p)
            ups.append(n)
        ribs.add(sweep(path, circle_profile(0.0015, 6, 0.0024), up=lambda i, p, ups=ups: ups[i], cap0=True, cap1=True))
    # concentric rings
    for rr in ():
        path, ups = [], []
        for s in range(97):
            p, n = surf(rr, TAU * s / 96, 0.0042)
            path.append(p)
            ups.append(n)
        ribs.add(sweep(path[:-1], circle_profile(0.0022, 6), up=lambda i, p, ups=ups: ups[i], closed_path=True))
    rb = to_obj("Kasa_Ribs", ribs, M["bronze_rib"], coll, parent=parent)
    mod_subsurf(rb, 0, 1)

    # rim band
    path = [base + V((KASA_R * math.sin(TAU * s / 128), -KASA_R * math.cos(TAU * s / 128), kasa_h(KASA_R) - 0.001))
            for s in range(128)]
    rim = sweep(path, rect_profile(0.010, 0.014, 2), up=(0, 0, 1), closed_path=True)
    rimo = to_obj("Kasa_Rim", rim, M["gold_dark"], coll, parent=parent)
    mod_subsurf(rimo, 1, 2)

    # finial
    fin = lathe([(0.0, 0.166), (0.004, 0.165), (0.006, 0.160), (0.004, 0.156), (0.007, 0.153), (0.010, 0.150),
                 (0.011, 0.146), (0.008, 0.144), (0.015, 0.142), (0.020, 0.137), (0.021, 0.134), (0.018, 0.131),
                 (0.0, 0.130)], 32)
    fin.translate(base)
    fo = to_obj("Kasa_Finial", fin, M["gold"], coll, parent=parent)
    mod_subsurf(fo, 1, 2)

    # inner head ring (hidden support)
    ring = torus_md(0.085, 0.010, 32, 8)
    ring.translate(base + V((0, -0.004, 0.055)))
    to_obj("Kasa_HeadRing", ring, M["cloth_plain"], coll, parent=parent)

    # tassels around the rim (none at the very front, as in the concept)
    tassel_md = MD()
    cap_md = MD()
    cord_md = MD()
    for k in range(1, 8):
        a = TAU * k / 8
        top = base + V((0.256 * math.sin(a), -0.256 * math.cos(a), kasa_h(0.256) - 0.006))
        drop = RNG.uniform(0.0, 0.006)
        cord_md.add(tube([top, top + V((0, 0, -0.012 - drop))], 0.0018, 6))
        cap_top = top + V((0, 0, -0.012 - drop))
        cap = lathe([(0.0, 0.0), (0.004, -0.001), (0.007, -0.006), (0.0085, -0.014), (0.0095, -0.018),
                     (0.006, -0.019), (0.0, -0.019)], 16)
        cap.translate(cap_top)
        cap_md.add(cap)
        # fringe: grooved skirt with ragged ends
        L = 0.062 + RNG.uniform(-0.006, 0.006)
        lens = [L * RNG.uniform(0.85, 1.0) for _ in range(25)]

        def fr(u, v, i, j, lens=lens, ct=cap_top):
            rr = lerp(0.0075, 0.0115, v ** 0.7) * (1.0 + 0.10 * math.sin(u * 24))
            z = -0.016 - v * lens[i % 24]
            return ct + V((rr * math.sin(u), -rr * math.cos(u), z))

        tassel_md.add(grid(fr, lin(0, TAU, 24), lin(0, 1, 8), closed_u=True))
    to_obj("Kasa_Tassels", tassel_md, M["tassel"], coll, parent=parent)
    to_obj("Kasa_TasselCaps", cap_md, M["gold_dark"], coll, parent=parent)
    to_obj("Kasa_TasselCords", cord_md, M["tassel"], coll, parent=parent)
