"""Lower body (measured from the concept): segmented battle belt with a cobra buckle, O-ring and lanyard, seven belt
pouches (teardrop sheath with LED, right-hip, right-rear, rear dump pouch, rear marker cylinder, rear-left, left-hip);
right drop-leg holster rig (platform, kydex holster, two mag pouches, sloped leg straps, hanger); left drop-leg double
mag panel; tan rope hanks and loop; thigh cargo, shin and slim calf pockets (right one holds the knife); ribbed crotch
gusset; vented hard-shell knee pads on backing pads with straps and buckles; 8-inch laced combat boots."""
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
    p = B.limb_pt(path, B.leg_radius, t, u, extra)
    c, T, N, Bv = B.limb_frame(path, t)
    n = p - c
    n = (n - T * n.dot(T)).normalized()
    zv = (-T if T.z < 0 else T).normalized()
    x = zv.cross(n).normalized()
    return p, x, n, zv, t


def outside_u(side):
    """Leg frames: N = front (-Y), B = T x N = -X for a downward leg, so +X (the left leg's outside) is u = -90 deg."""
    return -side * math.pi / 2


def leg_strap(side, z_out, z_in, width, off=0.006, u_in=None):
    """Strap ring around the thigh, sloping from z_out at the outside to z_in at the front-inner buckle."""
    path = B.leg_path(side)
    u_out = outside_u(side)
    u_in = u_in if u_in is not None else side * math.radians(35)
    zm = (z_out + z_in) / 2
    t = leg_t_at_z(path, zm)
    c = B.limb_frame(path, t)[0]
    pts = []
    for a in lin(0, TAU, 48)[:-1]:
        f = 0.5 - 0.5 * math.cos(a - u_out)  # 0 at the outside, 1 opposite
        dz = (z_out - zm) * (1 - 2 * smooth(f))
        q = B.limb_pt(path, B.leg_radius, t, a, off) + V((0, 0, dz))
        pts.append(q)
    md = sweep(pts, rect_profile(0.003, width), closed_path=True, up=lambda i, p, c=c: (p - c))
    buckle_p = B.limb_pt(path, B.leg_radius, t, u_in, off + 0.004) + V((0, 0, (z_in - zm)))
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
BOOT = [(-0.078, 0.034, 0.090), (-0.060, 0.041, 0.100), (-0.030, 0.045, 0.110), (0.000, 0.046, 0.118),
        (0.030, 0.050, 0.112), (0.060, 0.054, 0.104), (0.100, 0.0575, 0.090), (0.140, 0.057, 0.080),
        (0.170, 0.053, 0.074), (0.195, 0.045, 0.062), (0.212, 0.032, 0.048), (0.222, 0.012, 0.036)]


def foot_axes(side):
    a = V((B.ANKLE.x * side, B.ANKLE.y, 0.0))
    to = B.TOE_OUT
    fwd = V((side * math.sin(to), -math.cos(to), 0.0))
    rt = V((-fwd.y, fwd.x, 0.0)) if side > 0 else V((fwd.y, -fwd.x, 0.0))  # lateral, pointing outward
    return a, fwd, rt


def sole_z(s):
    """Top of the outsole along the foot (heel block thicker, toe spring)."""
    return interp_smooth([(-0.08, 0.036), (-0.03, 0.035), (0.03, 0.026), (0.10, 0.023), (0.18, 0.024), (0.225, 0.032)],
                         s)[0]


def boot_pt(side, s, a_, off=0.0):
    a, fwd, rt = foot_axes(side)
    w = interp_smooth([(q[0], q[1]) for q in BOOT], s)[0] + off
    h = interp_smooth([(q[0], q[2]) for q in BOOT], s)[0] + off
    z0 = sole_z(s)
    ca, sa = math.cos(a_), math.sin(a_)
    lx = math.copysign(abs(ca) ** (2.0 / 2.6), ca) * w
    lz = (math.copysign(abs(sa) ** (2.0 / 2.4), sa) * 0.5 + 0.5)
    return a + fwd * s + rt * lx + V((0, 0, z0 + lz * (h - z0)))


def build_boot(side, boots, soles, mids, laces, metal, trim):
    a, fwd, rt = foot_axes(side)
    ss = lin(-0.078, 0.222, 34)
    boots.add(grid(lambda u, v, i, j: boot_pt(side, v, u), lin(-math.pi / 2, 3 * math.pi / 2, 30), ss, closed_u=True))
    # shaft along the lower leg up to z 0.215 (hidden under the bloused cuff above ~0.205)
    path = B.leg_path(side)
    t0 = leg_t_at_z(path, 0.225)
    sub = [B.limb_frame(path, lerp(t0, 1.0, k / 10))[0] for k in range(11)]
    sub[-1] = sub[-1] + V((0, 0, -0.035))

    def shaft_r(t, u):
        a_, b_ = lerp(0.065, 0.0625, t), lerp(0.055, 0.050, t)  # half-depth, half-width
        cu, su = math.cos(u), math.sin(u)
        return a_ * b_ / math.sqrt((b_ * cu) ** 2 + (a_ * su) ** 2) + 0.002 * math.sin(u * 5 + t * 7)

    boots.add(L.limb(sub, shaft_r, 30))
    # padded collar + ankle strap with an outer buckle + heel ribs
    c0 = sub[0]
    trim.add(L.limb([c0 + V((0, 0, 0.010)), c0 + V((0, 0, -0.012))], lambda t, u: shaft_r(0.0, u) + 0.004, 30))
    ts = leg_t_at_z(path, 0.150)
    c1, T1, N1, B1 = B.limb_frame(path, min(1.0, ts))
    ring = [c1 + (N1 * math.cos(u) + B1 * math.sin(u)) * (shaft_r(0.6, u) + 0.003) for u in lin(0, TAU, 33)[:-1]]
    trim.add(sweep(ring, rect_profile(0.003, 0.020), closed_path=True, up=lambda i, p, c=c1: p - c))
    outv = V((side, 0.0, 0.0))
    ladder_buckle(metal, c1 + outv * 0.056, outv, w=0.025, h=0.020)
    for k in range(4):
        zz = 0.060 + k * 0.012
        heel = [a - fwd * 0.070 + rt * (0.040 * math.sin(t_)) + fwd * (0.012 * (1 - math.cos(t_))) + V((0, 0, zz))
                for t_ in lin(-1.2, 1.2, 10)]
        trim.add(tube(heel, 0.0025, 6))
    # outsole (offset footprint), heel block, grey midsole stripe, side lugs, toe bumper
    outline = []
    for q in range(56):
        ang = TAU * q / 56
        s = lerp(-0.083, 0.226, 0.5 - 0.5 * math.cos(ang))
        w = interp_smooth([(p[0], p[1]) for p in BOOT], max(-0.078, min(0.222, s)))[0] + 0.004
        frac = math.sin(ang)
        outline.append((s, w * (1 if frac >= 0 else -1) * min(1.0, abs(frac) * 2.5)))
    base = [a + fwd * s + rt * w for s, w in outline]
    n = len(base)
    for z0f, z1f, mdx, grow in ((lambda s: 0.0, lambda s: sole_z(s) - 0.004, soles, 0.0),
                                (lambda s: sole_z(s) - 0.004, lambda s: sole_z(s), mids, 0.001)):
        top = [p + (p - (a + fwd * 0.07)).normalized() * grow + V((0, 0, z1f(s))) for p, (s, w) in zip(base, outline)]
        bot = [p + (p - (a + fwd * 0.07)).normalized() * grow + V((0, 0, z0f(s))) for p, (s, w) in zip(base, outline)]
        b0 = len(mdx.v)
        mdx.v.extend(top + bot)
        for k in range(n):
            k2 = (k + 1) % n
            mdx.f.append((b0 + k, b0 + k2, b0 + n + k2, b0 + n + k))
            mdx.uv.append([(k / n, 1), ((k + 1) / n, 1), ((k + 1) / n, 0), (k / n, 0)])
            mdx.mi.append(0)
        cb = len(mdx.v)
        mdx.v.append(sum(bot, V()) / n)
        for k in range(n):
            mdx.f.append((b0 + n + ((k + 1) % n), b0 + n + k, cb))
            mdx.uv.append([(0, 0), (1, 0), (0.5, 0.5)])
            mdx.mi.append(0)
    for k, (s, w) in enumerate(outline):  # side lugs: chunky blocks around the rim at the bottom
        if k % 2:
            continue
        p = a + fwd * s + rt * w
        out = (p - (a + fwd * 0.07)).normalized()
        soles.add(box(0.014, 0.010, 0.012).transform(look_matrix(p + out * 0.003 + V((0, 0, 0.008)), out, (0, 0, 1))))
    trim.add(grid(lambda u, v, i, j: boot_pt(side, lerp(0.165, 0.224, v), u, 0.0015), lin(-math.pi / 2, math.pi / 2, 16),
                  lin(0, 1, 6)))   # glossy toe cap
    # laces: 9 crossings from the vamp up the shaft front, eyelets low, speed hooks high
    lp, rp_ = [], []
    for k in range(9):
        if k < 5:
            s = lerp(0.112, 0.020, k / 4)
            pl, pr = boot_pt(side, s, math.pi / 2 - 0.45, 0.003), boot_pt(side, s, math.pi / 2 + 0.45, 0.003)
        else:
            tt = lerp(1.0, t0, (k - 4) / 4.5)
            cc, Tt, Nt, Bt = B.limb_frame(path, tt)
            pl = cc + (Nt * math.cos(0.42) + Bt * math.sin(0.42)) * 0.066
            pr = cc + (Nt * math.cos(-0.42) + Bt * math.sin(-0.42)) * 0.066
        lp.append(pl)
        rp_.append(pr)
        if k < 5:
            for q in (pl, pr):
                metal.add(torus_md(0.0035, 0.0012, 10, 4).transform(look_matrix(q, (q - a - V((0, 0, 0.05))).normalized())))
        else:
            for q in (pl, pr):
                metal.add(box(0.008, 0.004, 0.006).translate(q))
    for k in range(len(lp) - 1):
        laces.add(sweep([lp[k], rp_[k + 1]], rect_profile(0.004, 0.0015), up=(0, -1, 0.3)))
        laces.add(sweep([rp_[k], lp[k + 1]], rect_profile(0.004, 0.0015), up=(0, -1, 0.3)))


# ------------------------------------------------------------------------------------------------- build
def build(coll, root):
    belt, belt_hw, pouches, flaps, trims, grom, straps, buckles = (MD() for _ in range(8))
    kydex, ropes, cord, pockets, kp_caps, kp_back, rivets = (MD() for _ in range(7))
    boots, soles, mids, laces, bmetal, btrim = (MD() for _ in range(6))
    led = MD()

    # ------------------------------------------------------------------ battle belt (segmented), buckle, ring, cord
    ths = lin(-math.pi, math.pi, 160)
    ring = [belt_pt(th, (BELT_Z0 + BELT_Z1) / 2, -0.007) for th in ths[:-1]]
    belt.add(sweep(ring, rect_profile(0.014, 0.067, 2), closed_path=True,
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
    # cobra buckle
    bm = look_matrix(V((0.0, -0.142, 1.020)), (0, -1, 0), (0, 0, 1))
    belt_hw.add(box(0.058, 0.058, 0.014).transform(bm @ Matrix.Translation((0, 0, 0.007))))
    for (w, h, x, y) in ((0.058, 0.006, 0, 0.026), (0.058, 0.006, 0, -0.026), (0.006, 0.058, 0.026, 0),
                         (0.006, 0.058, -0.026, 0), (0.040, 0.003, 0, 0.0)):
        belt_hw.add(box(w, h, 0.004).transform(bm @ Matrix.Translation((x, y, 0.016))))
    for sx in (-1, 1):
        belt_hw.add(lathe([(0.0, 0.0), (0.0025, 0.0), (0.0025, 0.002), (0.0, 0.0025)], 10)
                    .transform(bm @ Matrix.Translation((sx * 0.020, 0.020, 0.018))))
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
              bands=1)
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
                   tab=False, bands=0)
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
    for side in (1, -1):
        def cargo(u, v, i, j, side=side):
            z = lerp(0.710, 0.850, v)
            uu = -side * math.radians(30) + side * lerp(-0.42, 0.42, u)
            bul = (1 - (2 * u - 1) ** 4) * (1 - (2 * v - 1) ** 4)
            return leg_frame(side, z, uu, 0.004 + 0.016 * bul)[0]

        pockets.add(grid(cargo, lin(0, 1, 10), lin(0, 1, 10)))
        pockets.add(grid(lambda u, v, i, j, side=side: leg_frame(side, lerp(0.815, 0.855, v),
                                                                 -side * math.radians(30) + side * lerp(-0.44, 0.44, u),
                                                                 0.022)[0], lin(0, 1, 10), lin(0, 1, 3)))

        def shin(u, v, i, j, side=side):
            z = lerp(0.240, 0.390 - 0.015 * math.sin(math.pi * u), v)
            uu = -side * math.radians(28) + side * lerp(-0.55, 0.55, u)
            bul = (1 - (2 * u - 1) ** 4) * (1 - (2 * v - 1) ** 4)
            return leg_frame(side, z, uu, 0.004 + 0.012 * bul)[0]

        pockets.add(grid(shin, lin(0, 1, 10), lin(0, 1, 10)))
        p, x, n, zv, t = leg_frame(side, 0.400, outside_u(side) - side * 0.35, 0.004)
        sm = frame(p, n, zv)
        so = [(0.0175, 0.060), (-0.0175, 0.060), (-0.014, -0.060), (0.014, -0.060)]
        kydex.add(slab(so, 0.022, sm))
        straps.add(box(0.040, 0.015, 0.024).transform(look_matrix(p + n * 0.012 + zv * 0.045, n, zv)))
        if side < 0:  # the dive knife (seal_weapons) sits in the right sheath, handle up
            GEAR_FRAMES["knife"] = (p + n * 0.011, n, zv)

    # ------------------------------------------------------------------ ribbed crotch gusset
    for k in range(12):
        z = 0.845 + k * 0.0115
        y = B.body_pt(0.0, z, 0.006).y
        pockets.add(tube([V((-0.038, y + 0.004, z)), V((0.0, y - 0.001, z)), V((0.038, y + 0.004, z))], 0.0028, 6))

    # ------------------------------------------------------------------ knee pads: vented cap on a backing pad
    for side in (1, -1):
        path = B.leg_path(side)
        tk = leg_t_at_z(path, 0.495)
        dt = 0.090 / L.path_length(path)

        def cap(u, v, i, j, path=path, tk=tk, off0=0.010, amp=0.030, grow=0.0):
            top = (1 - v) / 2  # v = -1 top .. 1 bottom
            half = lerp(0.52, 0.60, top) + grow
            r = min(1.0, (abs(u) ** 3 + abs(v) ** 3) ** (1 / 3))
            bulge = amp * (1 - r * r) ** 0.6 + off0
            return B.limb_pt(path, B.leg_radius, tk + v * dt * (1 + grow), u * half, bulge)

        keep = lambda i, j: (abs(i - 9) / 9.0) ** 3 + (abs(j - 10) / 10.0) ** 3 <= 1.12  # noqa: E731
        kp_caps.add(grid(cap, lin(-1, 1, 18), lin(-1, 1, 20), keep=keep))
        kp_back.add(grid(lambda u, v, i, j, path=path, tk=tk: B.limb_pt(path, B.leg_radius, tk + v * dt * 1.12,
                                                                        u * 0.68, 0.006),
                         lin(-1, 1, 14), lin(-1, 1, 16)))
        rim = [cap(math.cos(a) * 0.97, math.sin(a) * 0.97, 0, 0) for a in lin(0, TAU, 48)[:-1]]
        kp_caps.add(tube(rim, 0.003, 6, closed=True))
        for k in range(5):  # vent slots in a recessed band near the top
            q = cap((k - 2) * 0.22, -0.62, 0, 0)
            n = (q - B.limb_frame(path, tk - 0.62 * dt)[0]).normalized()
            rivets.add(box(0.004, 0.012, 0.003).transform(look_matrix(q, n, (0, 0, 1))))
        for k in (-1, 0, 1):  # rivets on the backing's lower edge
            q = B.limb_pt(path, B.leg_radius, tk + 1.08 * dt, k * 0.45, 0.012)
            rivets.add(uv_sphere(0.0025, 8, 5).translate(q))
        md, bpnt, bn = leg_strap(side, 0.550, 0.550, 0.025, off=0.004, u_in=outside_u(side) - side * 2.2)
        straps.add(md)
        ladder_buckle(buckles, bpnt, bn, w=0.030, h=0.020)
        md, bpnt, bn = leg_strap(side, 0.470, 0.430, 0.022, off=0.004)
        straps.add(md)

    # ------------------------------------------------------------------ boots
    for side in (1, -1):
        build_boot(side, boots, soles, mids, laces, bmetal, btrim)

    # ------------------------------------------------------------------ objects
    ob = to_obj("Battle_Belt", belt, M["webbing"], coll, parent=root)
    mod_subsurf(ob, 0, 1)
    to_obj("Battle_Belt_Segments_Buckle", belt_hw, M["polymer_gloss"], coll, parent=root)
    to_obj("Belt_Lanyard_Cord", cord, M["cable_grey"], coll, parent=root)
    ob = to_obj("Lower_Pouches", pouches, M["carrier"], coll, parent=root)
    mod_bevel(ob, 0.005, 3)
    mod_subsurf(ob, 1, 1)
    ob = to_obj("Lower_Pouch_Flaps", flaps, M["carrier"], coll, parent=root)
    mod_solidify(ob, 0.004, -1.0)
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
    ob = to_obj("Boots", boots, M["boot"], coll, parent=root)
    mod_subsurf(ob, 1, 2)
    ob = to_obj("Boot_Outsoles_Lugs", soles, M["rubber_sole"], coll, parent=root, smooth=False)
    mod_bevel(ob, 0.002, 2)
    to_obj("Boot_Midsole_Stripe", mids, M["midsole"], coll, parent=root, smooth=False)
    to_obj("Boot_Laces", laces, M["webbing"], coll, parent=root)
    to_obj("Boot_Eyelets_Hooks_Buckles", bmetal, M["metal"], coll, parent=root)
    ob = to_obj("Boot_Collar_Strap_ToeCap", btrim, M["boot"], coll, parent=root)
    mod_solidify(ob, 0.002, 1.0)
