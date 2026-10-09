"""Lower body (measured from the concept): segmented battle belt with a cobra buckle, O-ring and lanyard, seven belt
pouches (teardrop sheath with LED, right-hip, right-rear, rear dump pouch, rear marker cylinder, rear-left, left-hip);
right drop-leg holster rig (platform, kydex holster, two mag pouches, sloped leg straps, hanger); left drop-leg double
mag panel; tan rope hanks and loop; thigh cargo, shin and slim calf pockets (right one holds the knife); vented
hard-shell knee pads on backing pads with straps and buckles; 8-inch laced combat boots."""
import math

from mathutils import Matrix

import seal_lib as L
from seal_lib import (MD, TAU, V, box, catmull_path, grid, interp_smooth, lathe, lerp, lin, look_matrix, mod_bevel,
                      mod_solidify, mod_subsurf, rect_profile, rope, smooth, sweep, to_obj, torus_md, tube, uv_sphere)
from seal_mats import M
import seal_body as B
from seal_vest import frame_dir, pouch

BELT_A, BELT_B, BELT_E = 0.200, 0.140, 2.3
BELT_Z0, BELT_Z1 = 0.987, 1.054
HOLSTER = {}
GEAR_FRAMES = {}  # pouch / sheath frames that seal_weapons fills with the carried gear


# ------------------------------------------------------------------------------------------------- helpers
def belt_pt(th, z, off=0.0):
    s, c = math.sin(th), math.cos(th)
    x = math.copysign(abs(s) ** (2 / BELT_E), s) * (BELT_A + off)
    y = -math.copysign(abs(c) ** (2 / BELT_E), c) * (BELT_B + off)
    return V((x, y, z))


def belt_normal(th):
    a, b = belt_pt(th - 0.01, 0.0), belt_pt(th + 0.01, 0.0)
    t = (b - a).normalized()
    n = t.cross(V((0, 0, 1))).normalized()
    return n if n.dot(belt_pt(th, 0.0)) > 0 else -n


def leg_t_at_z(path, z):
    for k in range(len(path) - 1):
        if (path[k].z - z) * (path[k + 1].z - z) <= 0:
            f = (path[k].z - z) / (path[k].z - path[k + 1].z + 1e-9)
            return (k + f) / (len(path) - 1)
    return 0.5


def leg_frame(side, z, u, extra=0.0):
    path = B.leg_path(side)
    t = leg_t_at_z(path, z)
    p = B.limb_pt(path, lambda t_, u_: B.leg_radius(t_, u_, side), t, u, extra)
    c, T, N, Bv = B.limb_frame(path, t)
    n = p - c
    n = (n - T * n.dot(T)).normalized()
    zv = (-T if T.z < 0 else T).normalized()
    x = zv.cross(n).normalized()
    return p, x, n, zv, t


def outside_u(side):
    """Leg frames: N = front (-Y), B = T x N = -X for a downward leg, so +X (the left leg's outside) is u = -90 deg."""
    return -side * math.pi / 2


def leg_strap(side, z_out, z_in, width, off=0.006, u_in=None, u_out=None):
    """Strap ring around the leg, sloping from z_out at u_out (default the outside) to z_in opposite; buckle at u_in
    (default front-inner)."""
    path = B.leg_path(side)
    rad = lambda t_, u_: B.leg_radius(t_, u_, side)  # noqa: E731
    u_out = outside_u(side) if u_out is None else u_out
    u_in = u_in if u_in is not None else side * math.radians(35)
    zm = (z_out + z_in) / 2
    t = leg_t_at_z(path, zm)
    c = B.limb_frame(path, t)[0]
    pts = []
    for a in lin(0, TAU, 48)[:-1]:
        f = 0.5 - 0.5 * math.cos(a - u_out)  # 0 at the outside, 1 opposite
        dz = (z_out - zm) * (1 - 2 * smooth(f))
        q = B.limb_pt(path, rad, t, a, off) + V((0, 0, dz))
        pts.append(q)
    md = sweep(pts, rect_profile(width, 0.003), closed_path=True, up=lambda i, p, c=c: (p - c))   # width along the leg
    buckle_p = B.limb_pt(path, rad, t, u_in, off + 0.004) + V((0, 0, (z_in - zm)))
    return md, buckle_p, (buckle_p - c).normalized()


def ladder_buckle(md, p, n, up=(0, 0, 1), w=0.030, h=0.030):
    m = look_matrix(p, n, up)
    for (bw, bh, x, y) in ((w, 0.004, 0, h / 2 - 0.002), (w, 0.004, 0, -h / 2 + 0.002), (0.004, h, w / 2 - 0.002, 0),
                           (0.004, h, -w / 2 + 0.002, 0), (w, 0.003, 0, 0.004), (w, 0.003, 0, -0.004)):
        md.add(box(bw, bh, 0.006).transform(m @ Matrix.Translation((x, y, 0.003))))


def frame(p, n, up=(0, 0, 1)):
    """Matrix with local x across, local y = n (outward depth), local z = up (orthogonalised)."""
    n = V(n).normalized()
    u = V(up)
    u = (u - n * u.dot(n)).normalized()
    x = u.cross(n)
    m = Matrix((x, n, u)).transposed().to_4x4()
    m.translation = V(p)
    return m


def slab(outline, depth, m, bevel_z=0.0):
    """Extrude a closed 2D outline (x, z) in a frame m (local y = outward depth) into a closed slab."""
    md = MD()
    n = len(outline)
    front = [m @ V((x, depth, z)) for x, z in outline]
    back = [m @ V((x, 0.0, z)) for x, z in outline]
    md.v.extend(front + back)
    cf = sum(front, V()) / n
    cb = sum(back, V()) / n
    md.v.extend([cf, cb])
    for k in range(n):
        k2 = (k + 1) % n
        md.f.append((k, k2, n + k2, n + k))
        md.uv.append([(k / n, 1), (k2 / n, 1), (k2 / n, 0), (k / n, 0)])
        md.f.append((2 * n, k2, k))
        md.uv.append([(0.5, 0.5), (0, 0), (1, 0)])
        md.f.append((2 * n + 1, n + k, n + k2))
        md.uv.append([(0.5, 0.5), (0, 0), (1, 0)])
    md.mi = [0] * len(md.f)
    return md


def rope_hank(c, length, width, seed=0, loops=6):
    """Wrapped hank of rope: several long narrow loops side by side, two wrap bands."""
    md = MD()
    for k in range(loops):
        a = (k / loops - 0.5) * 1.2
        rot = Matrix.Rotation(a, 4, "Z")
        pts = []
        for q in range(40):
            t = TAU * q / 40
            pts.append(V((width * 0.45 * math.sin(t) * (0.8 + 0.2 * math.cos(k + q * 0.3)), 0.0,
                          length * 0.5 * math.cos(t))))
        md.add(rope([c + rot @ p for p in pts], 0.0042, closed=True))
    for zz in (length * 0.28, -length * 0.05):
        md.add(torus_md(width * 0.55, 0.004, 24, 6).translate(c + V((0, 0, zz))))
    return md


# ------------------------------------------------------------------------------------------------- boots
# Foot-local frame (foot_axes): s along the foot (0 under the ankle, + toward the toe), l lateral (+ outward), z up.
# BOOT rows: (s, footprint half-width, crown height of the upper); boot_w() rounds the heel and the toe off in plan.
BOOT = [(-0.0735, 0.0420, 0.080), (-0.064, 0.0420, 0.095), (-0.050, 0.0420, 0.108), (-0.025, 0.0425, 0.121),
        (0.000, 0.0435, 0.131), (0.020, 0.0450, 0.138), (0.045, 0.0480, 0.129), (0.070, 0.0515, 0.117),
        (0.095, 0.0550, 0.104), (0.125, 0.0575, 0.094), (0.150, 0.0580, 0.0835), (0.172, 0.0570, 0.0745),
        (0.192, 0.0560, 0.0670), (0.204, 0.0550, 0.0590), (0.2115, 0.0545, 0.0500), (0.2165, 0.0540, 0.042)]
BOOT_CL = [(-0.0735, 0.000), (-0.030, 0.001), (0.030, 0.004), (0.100, 0.002), (0.160, -0.003), (0.2165, -0.008)]
# outer shaft, horizontal sections around the shin axis: z, half-depth, half-width (the 0.25 top opening, inner
# ~0.085 x 0.075, takes the end of the bloused trouser leg)
BOOT_SHAFT = [(0.095, 0.068, 0.056), (0.130, 0.069, 0.057), (0.160, 0.073, 0.062), (0.190, 0.079, 0.068),
              (0.220, 0.086, 0.076), (0.250, 0.091, 0.081)]
BOOT_TOP = 0.250
# welt (top of the grey midsole) along the foot: heel block, waist, forefoot, toe spring
BOOT_WELT = [(-0.085, 0.0385), (-0.040, 0.0385), (-0.015, 0.0370), (0.030, 0.0320), (0.080, 0.0275),
             (0.130, 0.0260), (0.170, 0.0262), (0.200, 0.0285), (0.215, 0.0315), (0.235, 0.0370)]
_BOOTS = {}


def _sm(t):
    import numpy as np
    t = np.clip(t, 0.0, 1.0)
    return t * t * (3 - 2 * t)


def _pchip(table, x, col=1):
    """Monotone cubic (Fritsch-Carlson) interpolation through a sorted table column; numpy in / out, clamped."""
    import numpy as np
    xs = np.array([q[0] for q in table], float)
    ys = np.array([q[col] for q in table], float)
    h = np.diff(xs)
    d = np.diff(ys) / h
    m = np.empty_like(ys)
    m[0], m[-1] = d[0], d[-1]
    w1, w2 = 2 * h[1:] + h[:-1], h[1:] + 2 * h[:-1]
    with np.errstate(divide="ignore", invalid="ignore"):
        mm = (w1 + w2) / (w1 / d[:-1] + w2 / d[1:])
    m[1:-1] = np.where(d[:-1] * d[1:] > 0, mm, 0.0)
    x = np.clip(np.asarray(x, float), xs[0], xs[-1])
    k = np.clip(np.searchsorted(xs, x) - 1, 0, len(xs) - 2)
    t = (x - xs[k]) / h[k]
    return ((1 + 2 * t) * (1 - t) ** 2 * ys[k] + t * (1 - t) ** 2 * h[k] * m[k] + t * t * (3 - 2 * t) * ys[k + 1] +
            t * t * (t - 1) * h[k] * m[k + 1])


def foot_axes(side):
    a = V((B.ANKLE.x * side, B.ANKLE.y, 0.0))
    to = B.TOE_OUT
    fwd = V((side * math.sin(to), -math.cos(to), 0.0))
    rt = V((-fwd.y, fwd.x, 0.0)) if side > 0 else V((fwd.y, -fwd.x, 0.0))  # lateral, pointing outward
    return a, fwd, rt


def sole_z(s):
    """Welt height (top of the midsole stripe) along the foot; works on floats and numpy arrays."""
    z = _pchip(BOOT_WELT, s)
    return float(z) if z.ndim == 0 else z


def sole_bot(s):
    """Underside of the outsole: toe spring, the waist lifted behind a square heel breast, rounded heel strike."""
    import numpy as np
    s = np.asarray(s, float)
    z = (0.014 * _sm((s - 0.150) / 0.075) ** 1.6 + 0.006 * _sm((s + 0.020) / 0.005) * _sm((0.080 - s) / 0.050) +
         0.004 * _sm((-0.068 - s) / 0.012))
    return float(z) if z.ndim == 0 else z


def boot_w(s):
    """Footprint half-width: BOOT column with a round heel cup and a blunt rounded toe."""
    import numpy as np
    s = np.asarray(s, float)
    s0, s1 = BOOT[0][0], BOOT[-1][0]
    hc = np.clip((-0.035 - s) / (-0.035 - s0), 0, 1)
    tc = np.clip((s - 0.145) / (s1 - 0.145), 0, 1)
    w = _pchip(BOOT, s) * np.sqrt(1 - hc ** 2) * (1 - tc ** 2.4) ** (1 / 2.4)
    return np.where((s < s0) | (s > s1), 0.0, w)


def _boot_field(side):
    """Implicit field of the upper in foot-local coordinates (< 0 inside, ~metres): a crowned last over the footprint
    smoothly united with an elliptical shaft that follows the shin (its front turned half way to the leg's), and the
    ankle-bone swellings (lateral malleolus lower and further back)."""
    import numpy as np
    a, fwd, rt = foot_axes(side)
    shin = sorted((((p - a).dot(fwd), (p - a).dot(rt), p.z) for p in B.leg_path(side) if p.z < 0.45),
                  key=lambda q: q[2])
    zsh = np.array([q[2] for q in shin])
    css, cls = np.array([q[0] for q in shin]), np.array([q[1] for q in shin])
    psi = 0.5 * B.TOE_OUT
    cp, sp = math.cos(psi), math.sin(psi)

    def centre(z):
        return np.interp(z, zsh, css), np.interp(z, zsh, cls)

    def field(s, l, z):
        z0 = sole_z(s)
        cl = _pchip(BOOT_CL, s)
        t = np.clip((z - z0) / np.maximum(_pchip(BOOT, s, 2) - z0, 1e-4), 0, None)
        w = boot_w(s)
        u = np.abs(l - cl) / np.maximum(w, 1e-6)
        fd = np.where(w > 1e-6, ((u ** 2.4 + t ** 2.6) ** (1 / 2.4) - 1) * 0.05, 0.05)
        cs, cc = centre(z)
        ds, dl = s - cs, l - cc
        d1, d2 = ds * cp - dl * sp, ds * sp + dl * cp
        e = (d1 / _pchip(BOOT_SHAFT, z)) ** 2 + (d2 / _pchip(BOOT_SHAFT, z, 2)) ** 2 + \
            np.clip((0.095 - z) / 0.040, 0, None) ** 2
        fs = (np.sqrt(e) - 1) * 0.065
        k = 0.030  # generous blend: the tongue fills the instep crease, the ankle stays full
        hh = np.clip(0.5 + 0.5 * (fs - fd) / k, 0, 1)
        f = fs + (fd - fs) * hh - k * hh * (1 - hh)
        f -= 0.0040 * np.exp(-((s + 0.010) ** 2 + (z - 0.088) ** 2) / 0.016 ** 2) * _sm((l - cc) / 0.02)
        f -= 0.0035 * np.exp(-((s - 0.004) ** 2 + (z - 0.100) ** 2) / 0.016 ** 2) * _sm((cc - l) / 0.02)
        return f

    return field, centre


def _boot_upper(side, nu=72, nk=60):
    """Upper as a stack of near-horizontal slices of the field (z blends from the welt line to the flat top), spaced
    evenly along the front and back profiles; each slice is sampled by rays from its centre."""
    import numpy as np
    field, centre = _boot_field(side)
    lam = np.linspace(0.0, 1.0, 361)
    ss = np.linspace(-0.10, 0.26, 721)
    S, LAM = np.meshgrid(ss, lam)

    def zof(s, lm):
        return sole_z(s) * (1 - lm) + BOOT_TOP * lm

    def lline(s, z):
        return _pchip(BOOT_CL, s) * (1 - _sm((z - 0.09) / 0.07)) + centre(z)[1] * _sm((z - 0.09) / 0.07)

    Z = zof(S, LAM)
    f = field(S, lline(S, Z), Z)
    ins = f < 0
    i0 = np.argmax(ins, axis=1)
    i1 = ins.shape[1] - 1 - np.argmax(ins[:, ::-1], axis=1)
    rows = np.arange(len(lam))
    fb0, fb1 = f[rows, i0 - 1], f[rows, i0]
    sb = ss[i0 - 1] + (ss[i0] - ss[i0 - 1]) * fb0 / (fb0 - fb1)
    ff0, ff1 = f[rows, i1], f[rows, i1 + 1]
    sf = ss[i1] + (ss[i1 + 1] - ss[i1]) * ff0 / (ff0 - ff1)
    zf, zb = zof(sf, lam), zof(sb, lam)
    dl = 0.5 * (np.hypot(np.diff(sf), np.diff(zf)) + np.hypot(np.diff(sb), np.diff(zb))) + 0.05 * np.diff(lam)
    cum = np.concatenate([[0.0], np.cumsum(dl)])
    lams = np.interp(np.linspace(0, cum[-1], nk + 1), cum, lam)
    phi = np.arange(nu) * TAU / nu
    grid_pts = []
    for lm in lams:
        b_, f_ = np.interp(lm, lam, sb), np.interp(lm, lam, sf)
        sc = 0.5 * (b_ + f_)
        zc = zof(sc, lm)
        ls = np.linspace(-0.16, 0.16, 641)
        fl = field(np.full_like(ls, sc), ls, np.full_like(ls, zc))
        li = np.nonzero(fl < 0)[0]
        lo, hi = ls[li[0]], ls[li[-1]]
        lc, rl, rs = 0.5 * (lo + hi), 0.5 * (hi - lo), 0.5 * (f_ - b_)
        dv = np.stack([rs * np.cos(phi), rl * np.sin(phi)])
        dv /= np.linalg.norm(dv, axis=0)
        r = np.linspace(0.0, 1.6 * max(rs, rl) + 0.01, 700)
        Sq = sc + r[:, None] * dv[0][None, :]
        Lq = lc + r[:, None] * dv[1][None, :]
        Zq = zof(Sq, lm)
        fq = field(Sq, Lq, Zq)
        j1 = np.maximum(np.argmax(fq >= 0, axis=0), 1)
        cols = np.arange(nu)
        g0, g1 = fq[j1 - 1, cols], fq[j1, cols]
        fr = g0 / (g0 - g1)
        rr = r[j1 - 1] + (r[j1] - r[j1 - 1]) * fr
        sq, lq = sc + rr * dv[0], lc + rr * dv[1]
        grid_pts.append(list(zip(sq, lq, zof(sq, lm))))
    return grid_pts, field, centre


def _boot_data(side):
    """Cached upper of one boot: world-space grid rows (welt -> top), BVH for surface lookups, foot frame."""
    if side in _BOOTS:
        return _BOOTS[side]
    from mathutils.bvhtree import BVHTree
    a, fwd, rt = foot_axes(side)
    loc, _, centre = _boot_upper(side)
    rows = [[a + fwd * s + rt * l + V((0, 0, z)) for s, l, z in row] for row in loc]
    nu = len(rows[0])
    verts = [p for row in rows for p in row]
    polys = [(j * nu + i, j * nu + (i + 1) % nu, (j + 1) * nu + (i + 1) % nu, (j + 1) * nu + i)
             for j in range(len(rows) - 1) for i in range(nu)]
    verts.append(sum(rows[0], V()) / nu)  # insole cap so that low rays always hit
    polys += [(i, len(verts) - 1, (i + 1) % nu) for i in range(nu)]
    d = {"a": a, "fwd": fwd, "rt": rt, "rows": rows, "loc": loc, "bvh": BVHTree.FromPolygons(verts, polys),
         "centre": centre}
    _BOOTS[side] = d
    return d


def _boot_hit(side, o, d, off=0.0):
    """Ray from an interior point o along d to the upper; returns (point + normal * off, outward normal)."""
    bd = _boot_data(side)
    d = V(d).normalized()
    p, n, _, _ = bd["bvh"].ray_cast(V(o), d)
    if p is None:
        return V(o) + d * 0.04, d
    n = V(n).normalized()
    if n.dot(d) < 0:
        n = -n
    return p + n * off, n


def boot_loc(side, s, l, z):
    a, fwd, rt = foot_axes(side)
    return a + fwd * s + rt * l + V((0, 0, z))


def boot_pt(side, s, a_, off=0.0):
    """Point on the upper over foot station s; a_ = 0 lateral, pi/2 top, pi medial (rays from just above the welt)."""
    bd = _boot_data(side)
    o = boot_loc(side, s, float(_pchip(BOOT_CL, s)), sole_z(s) + 0.012)
    return _boot_hit(side, o, bd["rt"] * math.cos(a_) + V((0, 0, math.sin(a_))), off)[0]


def shaft_hit(side, z, u, off=0.0):
    """Shaft lookup at height z: u = 0 front (turned with the shaft), pi/2 lateral, pi back."""
    bd = _boot_data(side)
    cs, cl = bd["centre"](z)
    psi = 0.5 * B.TOE_OUT
    e1 = bd["fwd"] * math.cos(psi) - bd["rt"] * math.sin(psi)
    e2 = bd["fwd"] * math.sin(psi) + bd["rt"] * math.cos(psi)
    return _boot_hit(side, boot_loc(side, float(cs), float(cl), z), e1 * math.cos(u) + e2 * math.sin(u), off)


def build_boot(side, md):
    """One boot: lofted upper (smooth vamp, grained quilted shaft, flex creases), glossy toe cap, mudguard and ribbed
    heel counter, lace stays with eyelets and speed hooks, criss-cross laces, ankle strap with buckle, diagonal
    stabilisers, back stay, padded collar, lugged outsole with a grey midsole stripe."""
    import numpy as np
    bd = _boot_data(side)
    a, fwd, rt, rows = bd["a"], bd["fwd"], bd["rt"], bd["rows"]
    up = V((0, 0, 1))
    nu = len(rows[0])
    upper = grid(lambda u, v, i, j: rows[j][i % nu], list(range(nu + 1)), list(range(len(rows))), closed_u=True,
                 flip=side < 0)
    loc = bd["loc"]
    for j in range(len(rows) - 1):  # smooth wet leather below the stabiliser line, grained leather shaft above it
        for i in range(nu):
            q = [loc[j][i], loc[j][(i + 1) % nu], loc[j + 1][(i + 1) % nu], loc[j + 1][i]]
            s, z = sum(c[0] for c in q) / 4, sum(c[2] for c in q) / 4
            upper.mi[j * nu + i] = int(z > 0.104 + (s - 0.058) * 0.49)
    md["upper"].add(upper)
    # mudguard rand round the foot between the toe cap and the heel counter: the lowest slices pushed out
    nrm = []
    for j in range(len(loc)):
        row = []
        for i in range(nu):
            du = V(loc[j][(i + 1) % nu]) - V(loc[j][i - 1])
            dv = V(loc[min(j + 1, len(loc) - 1)][i]) - V(loc[max(j - 1, 0)][i])
            n = du.cross(dv).normalized()
            row.append((fwd * n.x + rt * n.y + up * n.z).normalized())
        nrm.append(row)
    jm = max(j for j in range(len(loc)) if max(c[2] - sole_z(c[0]) for c in loc[j]) < 0.019)
    keep = lambda i, j: -0.012 < loc[j][i][0] < 0.168 and -0.012 < loc[j][(i + 1) % nu][0] < 0.168  # noqa: E731
    md["gloss"].add(grid(lambda u, v, i, j: rows[j][i % nu] + nrm[j][i % nu] * (0.0010 if j else 0.0004),
                         list(range(nu + 1)), list(range(jm + 1)), keep=keep, flip=side < 0))

    # glossy toe cap: rays fanned forward from inside the toe box, back edge arched over the vamp
    o_toe = boot_loc(side, 0.158, float(_pchip(BOOT_CL, 0.158)), sole_z(0.158) + 0.016)

    def toe(u, v, i, j):
        bmax = math.radians(70 + 18 * math.sin(L.clamp(u, 0, math.pi)))
        b = v * bmax
        d = fwd * math.cos(b) + (rt * math.cos(u) + up * math.sin(u)) * math.sin(b)
        return _boot_hit(side, o_toe, d, 0.0012)[0]

    md["gloss"].add(grid(toe, lin(-0.22, math.pi + 0.22, 26), lin(0, 1, 10), pole_v0=True, flip=side > 0))

    for k, s in enumerate((0.117, 0.128)):  # flex creases on the vamp sides behind the toe cap
        for a0, a1 in ((0.32, 1.02), (math.pi - 1.02, math.pi - 0.32)):
            pts = [boot_pt(side, s + 0.004 * math.sin(3.0 * u + k), u, -0.0007) for u in lin(a0, a1, 9)]
            md["upper"].add(tube(pts, 0.0015, 6))

    # heel counter: horizontal rays around the heel, top edge high at the back and sweeping down to the welt
    z0h = sole_z(-0.040)
    fm = math.pi / 2 + 0.15

    def ztop(ph):
        return z0h + 0.012 + (0.100 - z0h - 0.012) * (1 - min(1.0, abs(ph) / fm) ** 2.2)

    def heel(u, v, i, j):
        z = lerp(z0h + 0.0015, ztop(u), v)
        o = boot_loc(side, -0.020, float(_pchip(BOOT_CL, -0.020)), z)
        return _boot_hit(side, o, -fwd * math.cos(u) + rt * math.sin(u), 0.0015)[0]

    md["gloss"].add(grid(heel, lin(-fm, fm, 24), lin(0, 1, 8), flip=side > 0))
    for k in range(4):  # moulded ribs on the outer heel
        z = 0.050 + 0.0095 * k
        phs = [ph for ph in lin(0.20, 1.35, 14) if ztop(ph) > z + 0.006]
        if len(phs) < 3:
            continue
        pts = [_boot_hit(side, boot_loc(side, -0.020, float(_pchip(BOOT_CL, -0.020)), z),
                         -fwd * math.cos(ph) + rt * math.sin(ph), 0.0035)[0] for ph in phs]
        md["gloss"].add(tube(pts, 0.0021, 6))

    # lace line: a fan of rays from inside the ankle sweeping up from the lace start on the vamp, over the instep
    # and up the shaft front (turned with the shaft), resampled evenly
    psi = 0.5 * B.TOE_OUT
    cs, cl = bd["centre"](0.240)
    A = float(_pchip(BOOT_SHAFT, 0.240))
    s0, l0, z0 = 0.146, float(_pchip(BOOT_CL, 0.146)), float(_pchip(BOOT, 0.146, 2))
    s1, l1 = float(cs) + A * math.cos(psi), float(cl) - A * math.sin(psi)
    o_l = boot_loc(side, 0.0, 0.0, 0.075)
    th0, th1 = math.atan2(z0 - 0.075, math.hypot(s0, l0)), math.atan2(0.240 - 0.075, math.hypot(s1, l1))
    az0, az1 = math.atan2(l0, s0), math.atan2(l1, s1)
    fan = []
    for f in lin(0, 1, 90):
        th, az = lerp(th0, th1, f), lerp(az0, az1, f)
        d = (fwd * math.cos(az) + rt * math.sin(az)) * math.cos(th) + up * math.sin(th)
        fan.append(_boot_hit(side, o_l, d)[0])
    line = [_boot_hit(side, o_l, q - o_l) for q in L.resample(fan, 64)]

    def lace_frame(x):
        """Centre point, normal, up-tangent and lateral (outward) direction at fraction x of the lace line."""
        k = min(len(line) - 2, int(x * (len(line) - 1)))
        f = x * (len(line) - 1) - k
        p = line[k][0].lerp(line[k + 1][0], f)
        n = line[k][1].lerp(line[k + 1][1], f).normalized()
        t = (line[k + 1][0] - line[k][0]).normalized()
        lat = t.cross(n).normalized()
        return p, n, t, (lat if lat.dot(rt) > 0 else -lat)

    def lace_hit(x, q, off):
        """Project q onto the upper by a ray from below the lace line at x."""
        p, n, t, lat = lace_frame(x)
        return _boot_hit(side, p - n * 0.035, q - (p - n * 0.035), off)

    def lace_side(x, sgn, off):
        p, _, _, lat = lace_frame(x)
        hw = lerp(0.0190, 0.0250, smooth((x - 0.25) / 0.5)) * math.sin(math.pi / 2 * min(1.0, x / 0.05))
        return lace_hit(x, p + lat * (sgn * hw), off)

    # lace stays (eyelet facings) meeting in a U at the throat
    xs = lin(1.0, 0.0, 34) + lin(0.0, 1.0, 34)[1:]
    pts = [lace_side(x, -1 if k < 35 else 1, 0.0022) for k, x in enumerate(xs)]
    md["trim"].add(sweep([p for p, n in pts], rect_profile(0.0145, 0.0016, 2), up=lambda i, p, pts=pts: pts[i][1]))
    rowx = [0.060 + 0.905 * k / 8 for k in range(9)]
    row_pts = [(lace_side(x, 1, 0.0042)[0], lace_side(x, -1, 0.0042)[0]) for x in rowx]
    for k, (pl, pr) in enumerate(row_pts):
        _, _, t, lat = lace_frame(rowx[k])
        for q, sgn in ((pl, 1), (pr, -1)):
            nq = lace_side(rowx[k], sgn, 0.0)[1]
            if k < 5:
                md["metal"].add(torus_md(0.0034, 0.0011, 12, 5).transform(look_matrix(q, nq, t)))
            else:  # speed hook: rivet plus a J hook opening upward
                md["metal"].add(torus_md(0.0026, 0.0012, 10, 4).transform(look_matrix(q, nq, t)))
                o_ = lat * (sgn * 0.0012)
                md["metal"].add(tube([q, q + nq * 0.0040 + o_, q + nq * 0.0056 + t * 0.0018 + o_,
                                      q + nq * 0.0048 + t * 0.0040 + o_], 0.0012, 6))

    def lace(p0, p1, x0, x1, extra):
        pts = [lace_hit(lerp(x0, x1, f), p0.lerp(p1, f), 0.0035 + extra * math.sin(math.pi * f)) for f in lin(0, 1, 7)]
        md["lace"].add(sweep([p for p, n in pts], rect_profile(0.0050, 0.0018, 1), up=lambda i, p, pts=pts: pts[i][1]))

    lace(row_pts[0][0], row_pts[0][1], rowx[0], rowx[0], 0.0012)  # criss-cross, strands at two heights
    for k in range(8):
        lace(row_pts[k][0], row_pts[k + 1][1], rowx[k], rowx[k + 1], 0.0016)
        lace(row_pts[k][1], row_pts[k + 1][0], rowx[k], rowx[k + 1], 0.0027)

    # ankle strap round the back from lace stay to lace stay, ladder buckle on the outer side
    uu = lin(0.50, TAU - 0.50, 40)
    pts = [shaft_hit(side, 0.150, u, 0.0030) for u in uu]
    md["trim"].add(sweep([p for p, n in pts], rect_profile(0.020, 0.0026, 2), up=lambda i, p, pts=pts: pts[i][1]))
    bp, bn = shaft_hit(side, 0.150, math.pi / 2 + 0.25, 0.0050)
    ladder_buckle(md["metal"], bp, bn, w=0.022, h=0.024)

    for z in (0.178, 0.198, 0.218):  # padded quarters: quilting ridges round the shaft between the lace stays
        pts = [shaft_hit(side, z, u, -0.0002)[0] for u in lin(0.58, TAU - 0.58, 36)]
        md["upper"].add(tube(pts, 0.0022, 6))
    # back stay up the heel and shaft, padded collar roll
    pts = [shaft_hit(side, z, math.pi, 0.0020) for z in lin(0.088, 0.244, 16)]
    md["trim"].add(sweep([p for p, n in pts], rect_profile(0.016, 0.0018, 2), up=lambda i, p, pts=pts: pts[i][1]))
    top = rows[-1]
    ct = sum(top, V()) / nu
    ring = [p + (V((p.x - ct.x, p.y - ct.y, 0)).normalized() * 0.0012) - up * 0.0070 for p in top]
    md["pad"].add(sweep(ring, L.circle_profile(0.0095, 12, rx=0.0058), closed_path=True, up=(0, 0, 1)))

    # diagonal stabilisers from the lace stay down to the heel counter and the waist, a piping line above
    for sgn in (1, -1):
        def side_hit(s, z, off, sgn=sgn):
            cs, cl = bd["centre"](z)
            w = smooth((z - 0.09) / 0.07)
            o = boot_loc(side, s, float(_pchip(BOOT_CL, s)) * (1 - w) + float(cl) * w, z)
            return _boot_hit(side, o, rt * sgn, off)

        pts = [side_hit(lerp(0.080, -0.040, f), lerp(0.115, 0.056, f), 0.0024) for f in lin(0, 1, 16)]
        md["trim"].add(sweep([p for p, n in pts], rect_profile(0.017, 0.0018, 2), up=lambda i, p, pts=pts: pts[i][1]))
        pts = [side_hit(lerp(0.050, -0.030, f), lerp(0.128, 0.084, f), 0.0016)[0] for f in lin(0, 1, 12)]
        md["trim"].add(tube(pts, 0.0014, 6))
        pts = [side_hit(lerp(0.095, 0.035, f), lerp(0.094, 0.050, f), 0.0022) for f in lin(0, 1, 10)]
        md["trim"].add(sweep([p for p, n in pts], rect_profile(0.013, 0.0016, 2), up=lambda i, p, pts=pts: pts[i][1]))

    # outsole: welt outline offset outward, lugged side wall, toe spring and lifted waist; grey midsole stripe on top
    loc0 = bd["loc"][0]
    ring2 = L.resample(catmull_path([V((s, l, 0)) for s, l, z in loc0], 3, closed=True), 192, closed=True)
    n2 = len(ring2)
    per = [0.0]
    for p0, p1 in zip(ring2, ring2[1:] + ring2[:1]):
        per.append(per[-1] + (p1 - p0).length)
    ring_s = np.array([p.x for p in ring2])
    z0s, zbs = sole_z(ring_s), sole_bot(ring_s)
    outs = []
    for k in range(n2):
        t = ring2[(k + 1) % n2] - ring2[k - 1]
        nn = V((t.y, -t.x, 0)).normalized()
        if nn.dot(ring2[k] - V((0.07, 0.0, 0))) < 0:
            nn = -nn
        outs.append(nn)
    lug = [float(_sm((0.5 + 0.5 * math.cos(TAU * per[k] / 0.030) - 0.28) / 0.30)) for k in range(n2)]

    def ring_rows(spec, mdx, fan=None):
        b0 = len(mdx.v)
        for zf, of in spec:
            for k in range(n2):
                q = ring2[k] + outs[k] * of(k)
                mdx.v.append(boot_loc(side, q.x, q.y, zf(k)))
        nr = len(spec)
        for r in range(nr - 1):
            for k in range(n2):
                k2 = (k + 1) % n2
                f = (b0 + r * n2 + k, b0 + r * n2 + k2, b0 + (r + 1) * n2 + k2, b0 + (r + 1) * n2 + k)
                mdx.f.append(f[::-1] if side > 0 else f)
                u0, u1, v0, v1 = k / n2, (k + 1) / n2, r / nr, (r + 1) / nr
                mdx.uv.append([(u0, v0), (u1, v0), (u1, v1), (u0, v1)])
                mdx.mi.append(0)
        if fan is not None:
            c = len(mdx.v)
            mdx.v.append(boot_loc(side, 0.07, 0.0, fan))
            last = b0 + (nr - 1) * n2
            for k in range(n2):
                f = (last + k, last + (k + 1) % n2, c)
                mdx.f.append(f if side < 0 else f[::-1])
                mdx.uv.append([(0, 0), (1, 0), (0.5, 0.5)])
                mdx.mi.append(0)

    ring_rows([(lambda k: z0s[k] + 0.0010, lambda k: 0.0008), (lambda k: z0s[k], lambda k: 0.0044),
               (lambda k: z0s[k] - 0.0046, lambda k: 0.0046), (lambda k: z0s[k] - 0.0056, lambda k: 0.0030)], md["mid"])
    zr = lambda k, f: zbs[k] + f * (z0s[k] - 0.0075 - zbs[k])  # noqa: E731
    ring_rows([(lambda k: z0s[k] - 0.0042, lambda k: 0.0040), (lambda k: z0s[k] - 0.0075, lambda k: 0.0062),
               (lambda k: zr(k, 0.60), lambda k: 0.0062 + 0.0030 * lug[k]),
               (lambda k: zbs[k] + 0.0035, lambda k: 0.0062 + 0.0036 * lug[k]),
               (lambda k: zbs[k], lambda k: 0.0040 + 0.0030 * lug[k])], md["sole"], fan=float(sole_bot(0.07)))


# ------------------------------------------------------------------------------------------------- build
def build(coll, root):
    belt, belt_hw, pouches, flaps, trims, grom, straps, buckles = (MD() for _ in range(8))
    kydex, ropes, cord, pockets, kp_caps, kp_back, rivets = (MD() for _ in range(7))
    boots, soles, mids, laces, bmetal, btrim = (MD() for _ in range(6))
    led, pipe = MD(), MD()

    # ------------------------------------------------------------------ battle belt (segmented), buckle, ring, cord
    ths = lin(-math.pi, math.pi, 160)
    ring = [belt_pt(th, (BELT_Z0 + BELT_Z1) / 2, -0.007) for th in ths[:-1]]
    belt.add(sweep(ring, rect_profile(0.067, 0.014, 2), closed_path=True,      # x -> vertical, y -> radial
                   up=lambda i, p: belt_normal(ths[i])))
    for k in range(22):  # box segments (laser-cut MOLLE windows) separated by webbing bars
        th = -math.pi + TAU * (k + 0.5) / 22
        if abs(th) < 0.12:
            continue
        n = belt_normal(th)
        p = belt_pt(th, (BELT_Z0 + BELT_Z1) / 2, 0.0005)
        m = look_matrix(p, n, (0, 0, 1))
        for (w, h, x, y) in ((0.040, 0.003, 0, 0.0215), (0.040, 0.003, 0, -0.0215), (0.003, 0.043, 0.0205, 0),
                             (0.003, 0.043, -0.0205, 0)):
            belt_hw.add(box(w, h, 0.0025).transform(m @ Matrix.Translation((x, y, 0.001))))
    for zz in (BELT_Z0 + 0.004, BELT_Z1 - 0.004):  # stitch lines
        belt_hw.add(tube([belt_pt(th, zz, 0.0008) for th in ths[:-1]], 0.0009, 4, closed=True))
    for th_d in (17, 27):  # lighter keepers at the front-left
        th = math.radians(th_d)
        n = belt_normal(th)
        trims.add(box(0.050, 0.055, 0.004).transform(look_matrix(belt_pt(th, 1.020, 0.002), n, (0, 0, 1))))
    # cobra buckle (gunmetal, catches the key light like the sheet's bright centre buckle)
    buckle = MD()
    bm = look_matrix(V((0.0, -0.142, 1.020)), (0, -1, 0), (0, 0, 1))
    buckle.add(box(0.068, 0.062, 0.014).transform(bm @ Matrix.Translation((0, 0, 0.007))))
    for (w, h, x, y) in ((0.068, 0.007, 0, 0.0275), (0.068, 0.007, 0, -0.0275), (0.007, 0.062, 0.0305, 0),
                         (0.007, 0.062, -0.0305, 0), (0.046, 0.004, 0, 0.0)):
        buckle.add(box(w, h, 0.005).transform(bm @ Matrix.Translation((x, y, 0.0165))))
    for sx in (-1, 1):
        buckle.add(lathe([(0.0, 0.0), (0.003, 0.0), (0.003, 0.002), (0.0, 0.003)], 10)
                   .transform(bm @ Matrix.Translation((sx * 0.022, 0.021, 0.019))))
        buckle.add(box(0.016, 0.050, 0.010).transform(bm @ Matrix.Translation((sx * 0.044, 0, 0.004))))  # wings
    # O-ring on the front-left and the light lanyard cord in two loops with a knot
    th = math.radians(70)
    rp = belt_pt(th, 1.025, 0.012)
    belt_hw.add(torus_md(0.014, 0.002, 24, 6).transform(look_matrix(rp, belt_normal(th), (0, 0, 1))))
    cpts = [rp + V((0, 0, -0.012)), V((0.175, -0.120, 0.985)), V((0.150, -0.135, 0.940)), V((0.120, -0.132, 0.905)),
            V((0.150, -0.138, 0.880)), V((0.185, -0.130, 0.915)), V((0.150, -0.134, 0.925)), V((0.125, -0.138, 0.960)),
            V((0.160, -0.140, 0.900)), V((0.170, -0.136, 0.870))]
    cord.add(tube(catmull_path(cpts, 6), 0.002, 6))
    cord.add(uv_sphere(0.006, 8, 6).translate((0.150, -0.137, 0.920)))

    # ------------------------------------------------------------------ belt pouches
    def bp(cx, cy, zc, w, h, d, tgt=(pouches, flaps), flap=0.27, **kw):
        n = V((cx, cy * (BELT_A / BELT_B) ** 2, 0)).normalized()
        p, x, nn, z = frame_dir(cx, cy, zc, n.x, n.y, d)
        kw.setdefault("md_pipe", pipe)
        return pouch(tgt[0], tgt[1], trims, grom, p, x, nn, z, w, h, d, flap=flap, **kw)

    GEAR_FRAMES.clear()
    bp(-0.225, 0.000, 1.020, 0.080, 0.130, 0.055, bungee=False)          # right-hip pouch
    m = bp(-0.205, 0.075, 1.000, 0.070, 0.150, 0.050, bungee=False)      # right-rear utility pouch + flap buckle
    ladder_buckle(buckles, m @ V((0, 0.055, 0.050)), (m.to_3x3() @ V((0, 1, 0))).normalized(), w=0.020, h=0.012)
    # utility-pouch details from the gear card: top grab loop, flat front slip pocket, centre clip tab, stitching
    straps.add(sweep([m @ V(q) for q in ((-0.020, 0.025, 0.074), (-0.016, 0.025, 0.086), (0.016, 0.025, 0.086),
                                         (0.020, 0.025, 0.074))], rect_profile(0.004, 0.008), up=m.to_3x3() @ V((0, 1, 0))))
    pouches.add(box(0.056, 0.006, 0.062).transform(m @ Matrix.Translation((0.0, 0.053, -0.036))))
    trims.add(box(0.014, 0.004, 0.030).transform(m @ Matrix.Translation((0.0, 0.058, 0.026))))
    for zz in (-0.004, -0.066):
        trims.add(box(0.050, 0.0015, 0.0015).transform(m @ Matrix.Translation((0.0, 0.0565, zz))))
    m = bp(-0.120, 0.150, 0.990, 0.120, 0.220, 0.070, flap=0.22, bands=0, bungee=False)  # rear dump pouch
    GEAR_FRAMES["dump"] = m
    for k in range(6):  # vertical stitched ribs
        trims.add(box(0.003, 0.004, 0.150).transform(m @ Matrix.Translation((-0.050 + k * 0.02, 0.071, -0.025))))
    bp(0.150, 0.130, 1.010, 0.065, 0.110, 0.045, bungee=False, bands=1)  # rear-left rounded pouch
    GEAR_FRAMES["left_hip"] = bp(0.235, 0.010, 1.000, 0.075, 0.145, 0.060, bungee=False)  # left-hip pouch
    cyl_c = V((0.046, 0.155 + 0.018, 1.010))                              # rear marker/flashlight cylinder
    belt_hw.add(lathe([(0.0, -0.0325), (0.020, -0.0325), (0.020, 0.0325), (0.0, 0.0325)], 20)
                .transform(look_matrix(cyl_c, (1, 0, 0), (0, 0, 1))))
    for k in range(6):
        belt_hw.add(torus_md(0.0202, 0.0012, 20, 4).transform(look_matrix(cyl_c + V((-0.025 + k * 0.01, 0, 0)),
                                                                          (1, 0, 0), (0, 0, 1))))
    # front-right teardrop sheath with a snap and a red-orange LED
    n = V((math.sin(math.radians(-40)), -math.cos(math.radians(-40)), 0))
    tm = frame(V((-0.140, -0.125, 0.995)) - n * 0.015, n, (math.sin(0.17), 0.0, math.cos(0.17)))
    outl = [(0.030 * math.cos(a), 0.040 + 0.030 * math.sin(a)) for a in lin(0, math.pi, 12)]
    outl += [(lerp(-0.030, 0.0, t), lerp(0.040, -0.070, t)) for t in lin(0, 1, 8)[1:]]
    outl += [(lerp(0.0, 0.030, t), lerp(-0.070, 0.040, t)) for t in lin(0, 1, 8)[1:-1]]
    kydex.add(slab(outl, 0.030, tm))
    GEAR_FRAMES["teardrop"] = tm
    belt_hw.add(lathe([(0.0, 0.0), (0.003, 0.0), (0.003, 0.002), (0.0, 0.0025)], 10).transform(
        tm @ Matrix.Translation((-0.010, 0.031, 0.035)) @ Matrix.Rotation(math.pi / 2, 4, "X") @
        Matrix.Rotation(math.pi, 4, "X")))
    led.add(uv_sphere(0.0018, 8, 5).transform(tm @ Matrix.Translation((0.016, 0.031, 0.045))))

    # ------------------------------------------------------------------ right drop-leg holster rig
    pc = V((-0.241, -0.010, 0.790))
    pm = Matrix((V((0, -1, 0)), V((-1, 0, 0)), V((0, 0, 1)))).transposed().to_4x4()
    pm.translation = pc
    outl = [(0.085 * math.copysign(1, math.cos(a)) * min(1, abs(math.cos(a)) * 1.6) * 0.98,
             0.105 * math.copysign(1, math.sin(a)) * min(1, abs(math.sin(a)) * 1.6)) for a in lin(0, TAU, 33)[:-1]]
    straps.add(slab(outl, 0.012, pm))
    hm = pm @ Matrix.Translation((-0.005, 0.012, 0.0))           # holster on the platform's rear part
    hol = [(0.045, 0.100), (-0.050, 0.100), (-0.058, 0.060), (-0.030, 0.035), (-0.028, -0.100), (0.026, -0.100),
           (0.030, 0.040), (0.050, 0.070)]
    kydex.add(slab(hol, 0.045, hm))
    HOLSTER.clear()
    HOLSTER.update({"m": hm, "top": hm @ V((0.010, 0.0225, 0.100))})
    for dx in (-0.095, -0.055):                                  # two small mag pouches in front of the holster
        mm = pm @ Matrix.Translation((-dx, 0.012, 0.010))
        p = mm @ V((0, 0, 0))
        xv = (mm.to_3x3() @ V((1, 0, 0))).normalized()
        nv = (mm.to_3x3() @ V((0, 1, 0))).normalized()
        pouch(pouches, flaps, trims, grom, p, xv, nv, V((0, 0, 1)), 0.035, 0.100, 0.030, flap=0.30, bungee=False,
              bands=1, md_pipe=pipe)
    for z_out, z_in in ((0.840, 0.820), (0.760, 0.720)):
        md, bpnt, bn = leg_strap(-1, z_out, z_in, 0.025)
        straps.add(md)
        ladder_buckle(buckles, bpnt, bn)
    hp = V((-0.230, -0.005, 0.990))
    straps.add(sweep([hp, hp + V((-0.004, 0, -0.050)), V((-0.241, -0.010, 0.895))], rect_profile(0.050, 0.004),
                     up=(-1, 0, 0)))
    ladder_buckle(buckles, hp + V((-0.008, 0, -0.050)), V((-1, 0, 0)), w=0.050, h=0.030)

    # ------------------------------------------------------------------ left drop-leg double mag-pouch panel
    pc = V((0.247, 0.020, 0.750))
    pm = Matrix((V((0, 1, 0)), V((1, 0, 0)), V((0, 0, 1)))).transposed().to_4x4()
    pm.translation = pc
    outl = [(0.095 * math.copysign(1, math.cos(a)) * min(1, abs(math.cos(a)) * 1.6),
             0.090 * math.copysign(1, math.sin(a)) * min(1, abs(math.sin(a)) * 1.6)) for a in lin(0, TAU, 33)[:-1]]
    straps.add(slab(outl, 0.012, pm))
    for dy in (-0.035, 0.030):
        mm = pm @ Matrix.Translation((dy, 0.012, 0.0))
        p = mm @ V((0, 0, 0))
        xv = (mm.to_3x3() @ V((1, 0, 0))).normalized()
        nv = (mm.to_3x3() @ V((0, 1, 0))).normalized()
        m2 = pouch(pouches, flaps, trims, grom, p, xv, nv, V((0, 0, 1)), 0.060, 0.170, 0.050, flap=0.24, bungee=True,
                   tab=False, bands=0, md_pipe=pipe)
        GEAR_FRAMES.setdefault("left_leg", []).append(m2)
        trims.add(box(0.015, 0.004, 0.015).transform(m2 @ Matrix.Translation((0, 0.055, 0.055))))
    for z_out, z_in in ((0.815, 0.800), (0.725, 0.720)):
        md, bpnt, bn = leg_strap(1, z_out, z_in, 0.025)
        straps.add(md)
        ladder_buckle(buckles, bpnt, bn)
    hp = V((0.245, 0.010, 0.930))
    straps.add(sweep([hp, V((0.247, 0.020, 0.842))], rect_profile(0.040, 0.004), up=(1, 0, 0)))

    # ------------------------------------------------------------------ tan rope: hank A (left), hank B + loop C (right)
    ropes.add(rope_hank(V((0.292, 0.140, 0.775)), 0.170, 0.035, 1))
    ropes.add(rope_hank(V((-0.262, 0.090, 0.740)), 0.180, 0.040, 2))
    ropes.add(rope([V((-0.262, 0.080, 0.660)), V((-0.268, 0.070, 0.630)), V((-0.272, 0.060, 0.600))], 0.0035))
    loop = [V((-0.150 + 0.0225 * math.sin(t) * (1 - 0.7 * (0.5 + 0.5 * math.cos(t))), 0.172,
               0.850 - 0.110 * (1 - math.cos(t)))) for t in lin(0, TAU, 40)[:-1]]
    ropes.add(rope(loop, 0.0035, closed=True))
    ropes.add(uv_sphere(0.008, 10, 6).translate((-0.150, 0.172, 0.852)))

    # ------------------------------------------------------------------ pockets: thigh cargo, shin, slim calf (+ knife)
    rig_straps = {1: ((0.815, 0.800), (0.725, 0.720)), -1: ((0.840, 0.820), (0.760, 0.720))}  # drop-leg straps above

    def strap_press(side, z, uu):
        """1 under a drop-leg leg strap (the straps pinch the cargo pockets flat), 0 away from them."""
        p = 0.0
        for z_out, z_in in rig_straps[side]:
            zs = z_out + (z_in - z_out) * smooth(0.5 - 0.5 * math.cos(uu - outside_u(side)))
            p = max(p, math.exp(-((z - zs) / 0.018) ** 2))
        return p

    for side in (1, -1):
        def cargo(u, v, i, j, side=side, lift=0.0):
            z = lerp(0.705, 0.845, v)
            uu = -side * math.radians(30) + side * lerp(-0.40, 0.40, u)
            bul = max(0.0, 1 - abs(2 * u - 1) ** 6) * max(0.0, 1 - abs(2 * v - 1) ** 6)
            return leg_frame(side, z, uu, 0.003 + 0.014 * bul * (1 - 0.85 * strap_press(side, z, uu)) + lift)[0]

        pockets.add(grid(cargo, lin(0, 1, 12), lin(0, 1, 14)))
        pockets.add(grid(lambda u, v, i, j, side=side: cargo(lerp(-0.03, 1.03, u), lerp(0.74, 1.0, v), 0, 0, side,
                                                             0.004), lin(0, 1, 12), lin(0, 1, 4)))  # wider top flap

        def shin(u, v, i, j, side=side, lift=0.0):
            z = lerp(0.300, 0.388 - 0.013 * math.sin(math.pi * min(1.0, max(0.0, u))), v)
            uu = -side * math.radians(22) + side * lerp(-0.60, 0.60, u)
            bul = max(0.0, 1 - abs(2 * u - 1) ** 5) * max(0.0, 1 - abs(2 * v - 1) ** 5)
            return leg_frame(side, z, uu, 0.003 + 0.010 * bul + lift)[0]

        pockets.add(grid(shin, lin(0, 1, 12), lin(0, 1, 10)))
        pockets.add(grid(lambda u, v, i, j, side=side: shin(lerp(-0.03, 1.03, u), lerp(0.70, 1.0, v), 0, 0, side,
                                                            0.004), lin(0, 1, 12), lin(0, 1, 4)))   # curved top flap
        p, x, n, zv, t = leg_frame(side, 0.400, outside_u(side) - side * 0.35, 0.004)
        sm = frame(p, n, zv)
        so = [(0.0175, 0.060), (-0.0175, 0.060), (-0.014, -0.060), (0.014, -0.060)]
        kydex.add(slab(so, 0.022, sm))
        straps.add(box(0.040, 0.015, 0.024).transform(look_matrix(p + n * 0.012 + zv * 0.045, n, zv)))
        if side < 0:  # the dive knife (seal_weapons) sits in the right sheath, handle up
            GEAR_FRAMES["knife"] = (p + n * 0.011, n, zv)

    # ------------------------------------------------------------------ knee pads: articulated hard shell on a backing
    for side in (1, -1):
        path = B.leg_path(side)
        tk = leg_t_at_z(path, 0.497)
        t_up, t_dn = tk - leg_t_at_z(path, 0.587), leg_t_at_z(path, 0.405) - tk

        def kp(s, h, off, wid=1.0, side=side, path=path, tk=tk, t_up=t_up, t_dn=t_dn):
            """Point on the pad: s = -1..1 across, h = -1 (top edge) .. 1 (bottom tip) on a shield outline, wide at the
            top and rounded below; off = height over the smooth (fold-free) trouser surface."""
            h = h - 0.30 * s * s * smooth((h - 0.1) / 0.9) + 0.10 * s * s * smooth((-h - 0.5) / 0.5)
            u = s * wid * lerp(0.92, 0.66, smooth((h + 1) / 2))
            t = tk + h * (t_dn if h > 0 else t_up)
            c, T, N, Bv = B.limb_frame(path, t)
            return c + (N * math.cos(u) + Bv * math.sin(u)) * (B.leg_base(t, u, side) + off)

        def dome(s, h):  # the top edge tucks under the trouser roll so the shell reads convex in profile
            return lerp(0.008, 0.020, smooth((h + 1) / 0.5)) + 0.036 * max(0.0, 1 - s * s) ** 0.55 * \
                max(0.0, 1 - ((h + 0.05) / 0.95) ** 2) ** 0.6

        def lower(s, h):  # lower articulated plate: tucked under the dome, its tip curling onto the backing
            return 0.024 + 0.013 * max(0.0, 1 - s * s) ** 0.55 * (1 - smooth((h - 0.5) / 0.5))

        kp_caps.add(grid(lambda s, h, i, j: kp(s, h, dome(s, h)), lin(-1, 1, 18), lin(-1.0, 0.62, 22)))
        kp_caps.add(grid(lambda s, h, i, j: kp(s, h, lower(s, h), 0.95), lin(-1, 1, 14), lin(0.50, 1.0, 8)))
        kp_caps.add(grid(lambda s, h, i, j: kp(s, h, dome(s, h) + 0.003), lin(-0.55, 0.55, 10), lin(-0.92, -0.74, 3)))
        rim = [kp(s, -1.0, dome(s, -1.0) + 0.0015) for s in lin(-1, 1, 14)[:-1]]
        rim += [kp(1.0, h, dome(1.0, h) + 0.0015) for h in lin(-1.0, 0.62, 14)[:-1]]
        rim += [kp(s, 0.62, dome(s, 0.62) + 0.0015) for s in lin(1, -1, 14)[:-1]]
        rim += [kp(-1.0, h, dome(-1.0, h) + 0.0015) for h in lin(0.62, -1.0, 14)[:-1]]
        kp_caps.add(tube(rim, 0.0032, 6, closed=True))                     # raised rim bead round the dome
        kp_caps.add(tube([kp(s, 1.0, lower(s, 1.0) + 0.001, 0.95) for s in lin(-1, 1, 14)], 0.002, 5))
        kp_caps.add(tube([kp(s, h, dome(0.8 * s, h) + 0.001, 0.80) for s, h in          # inner raised contour
                          [(-1, 0.45)] + [(-1, h) for h in lin(0.3, -0.62, 8)] + [(s, -0.70) for s in lin(-0.8, 0.8, 9)]
                          + [(1, h) for h in lin(-0.62, 0.3, 8)] + [(1, 0.45)]], 0.0018, 5))
        kp_back.add(grid(lambda s, h, i, j: kp(s, h, lerp(0.006, 0.019, smooth((h + 1.1) / 0.6)) + 0.002 * (1 - s * s),
                                                1.24), lin(-1, 1, 16),
                         lin(-1.10, 1.25, 22)))
        c0 = B.limb_frame(path, tk)[0]
        for k in range(5):  # vent slots in the raised band below the top rim
            q = kp((k - 2) * 0.2, -0.83, dome((k - 2) * 0.2, -0.83) + 0.0045)
            rivets.add(box(0.0045, 0.010, 0.003).transform(look_matrix(q, (q - c0).normalized(), (0, 0, 1))))
        for s, h in ((-0.35, 1.17), (0.0, 1.19), (0.35, 1.17), (-0.96, -0.6), (0.96, -0.6), (-0.96, 0.3), (0.96, 0.3)):
            q = kp(s, h, 0.0215, 1.24)                                      # rivets on the backing's rim
            rivets.add(uv_sphere(0.0025, 8, 5).translate(q))
        md, bpnt, bn = leg_strap(side, 0.550, 0.550, 0.025, off=0.006, u_in=outside_u(side) - side * 0.65)
        straps.add(md)                                                    # upper strap behind the knee, outer buckle
        ladder_buckle(buckles, bpnt, bn, w=0.030, h=0.020)
        md, bpnt, bn = leg_strap(side, 0.435, 0.515, 0.022, off=0.006, u_out=0.0)
        straps.add(md)                                                    # lower strap rising from the cap to the back

    # ------------------------------------------------------------------ boots
    bmd = {"upper": boots, "sole": soles, "mid": mids, "lace": laces, "metal": bmetal, "trim": btrim, "gloss": MD(),
           "pad": MD()}
    _BOOTS.clear()  # the uppers follow the current leg path / ankle
    for side in (1, -1):
        build_boot(side, bmd)

    # ------------------------------------------------------------------ objects
    ob = to_obj("Battle_Belt", belt, M["belt"], coll, parent=root)
    mod_subsurf(ob, 0, 1)
    to_obj("Battle_Belt_Segments", belt_hw, M["polymer_gloss"], coll, parent=root)
    ob = to_obj("Belt_Cobra_Buckle", buckle, M["metal"], coll, parent=root, smooth=False)
    mod_bevel(ob, 0.0015, 1)
    to_obj("Belt_Lanyard_Cord", cord, M["cable_grey"], coll, parent=root)
    ob = to_obj("Lower_Pouches", pouches, M["nylon_camo"], coll, parent=root)
    mod_bevel(ob, 0.005, 3)
    mod_subsurf(ob, 1, 1)
    ob = to_obj("Lower_Pouch_Flaps", flaps, M["nylon_camo"], coll, parent=root)
    mod_solidify(ob, 0.004, -1.0)
    to_obj("Lower_Pouch_Piping", pipe, M["plastic_light"], coll, parent=root)
    to_obj("Lower_Pouch_Trims_Keepers", trims, M["webbing"], coll, parent=root)
    to_obj("Lower_Grommets_Rivets", grom, M["metal_black"], coll, parent=root)
    to_obj("Lower_Straps_Platforms", straps, M["nylon_dark"], coll, parent=root)
    to_obj("Lower_Buckles", buckles, M["plastic_dark"], coll, parent=root)
    ob = to_obj("Holster_Sheaths_Kydex", kydex, M["kydex"], coll, parent=root)
    mod_bevel(ob, 0.004, 2)
    to_obj("Sheath_LED", led, M["led_red"], coll, parent=root)
    to_obj("Rope_Hanks_Loop", ropes, M["rope"], coll, parent=root)
    ob = to_obj("Trouser_Pockets_Gusset", pockets, M["suit_panel"], coll, parent=root)
    mod_solidify(ob, 0.003, -1.0)
    ob = to_obj("Knee_Pad_Caps", kp_caps, M["kneecap"], coll, parent=root)
    mod_solidify(ob, 0.005, -1.0)
    mod_subsurf(ob, 1, 2)
    ob = to_obj("Knee_Pad_Backing", kp_back, M["nylon_dark"], coll, parent=root)
    mod_solidify(ob, 0.012, -1.0)
    mod_subsurf(ob, 1, 1)
    to_obj("Knee_Pad_Vents_Rivets", rivets, M["metal"], coll, parent=root)
    import seal_mats as MT
    wet = MT.mat_polymer("Boot_Leather_Wet", base=(0.011, 0.011, 0.0125), rough=0.36, coat=0.30, grain=700.0)
    ob = to_obj("Boots", boots, [wet, M["boot"]], coll, parent=root)
    mod_subsurf(ob, 1, 2)
    ob = to_obj("Boot_ToeCaps_HeelCounters", bmd["gloss"], M["kneecap"], coll, parent=root)
    mod_solidify(ob, 0.0016, -1.0)
    mod_subsurf(ob, 1, 1)
    ob = to_obj("Boot_Outsoles_Lugs", soles, M["rubber_sole"], coll, parent=root, smooth=False)
    mod_bevel(ob, 0.0012, 2)
    ob = to_obj("Boot_Midsole_Stripe", mids, M["midsole"], coll, parent=root, smooth=False)
    mod_bevel(ob, 0.0008, 1)
    to_obj("Boot_Laces", laces, M["webbing"], coll, parent=root)
    to_obj("Boot_Eyelets_Hooks_Buckles", bmetal, M["metal"], coll, parent=root)
    to_obj("Boot_Stays_Straps_Overlays", btrim, wet, coll, parent=root)
    ob = to_obj("Boot_Padded_Collars", bmd["pad"], M["boot"], coll, parent=root)
    mod_subsurf(ob, 1, 1)
