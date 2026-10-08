"""Head (measured from the concept sheet): high-cut ballistic helmet with rail band, forehead arches, NVG shroud +
flipped-up binocular NVG, rail lights, ring knobs, rear antenna boxes, crown strip, battery box, velcro panels and the
rear retention dial; D-shaped comms ear cups; one panoramic blue goggle lens in a rubber frame; a faceted respirator
with nose ridge, seams and the round regulator; thin beaded jaw hoses; the rebreather neck manifold wrapped in hose
turns; and the single continuous corrugated breathing-hose loop that sags across the chest under the chin."""
import math

from mathutils import Matrix

import seal_lib as L
from seal_lib import (MD, TAU, V, box, catmull_path, grid, interp_smooth, lathe, lerp, lin, look_matrix, mod_bevel,
                      mod_solidify, mod_subsurf, rect_profile, smooth, sweep, to_obj, torus_md, tube, uv_sphere)
from seal_mats import M

# ----------------------------------------------------------------------------------------- measurements
HC = V((0.0, -0.045, 1.700))          # helmet ellipsoid centre
HA, HB, HCZ = 0.1025, 0.130, 0.160     # outer semi-axes (X, Y, Z): top of the dome at z 1.860
EDGE = [(0, 1.735), (30, 1.736), (45, 1.744), (60, 1.749), (100, 1.749), (124, 1.736), (150, 1.708), (180, 1.705)]
GOG_C = V((0.0, -0.071, 0.0))         # goggle plan-circle centre (x, y)
GOG_R = 0.100
REG_C = V((0.0, -0.175, 1.591))       # regulator face centre
MANIFOLD = {"x0": -0.175, "x1": 0.185, "y": 0.150, "z": 1.592, "r": 0.058}

LENSES = MD()
LENSES_DARK = MD()
LENSES_VISOR = MD()


def edge_z(th):
    return interp_smooth(EDGE, abs(math.degrees(math.atan2(math.sin(th), math.cos(th)))))[0]


def helmet_pt(th, phi, off=0.0):
    """Shell point: th azimuth from the front (+ toward the character's left), phi elevation above HC."""
    c = math.cos(phi)
    return V((HC.x + (HA + off) * c * math.sin(th), HC.y - (HB + off) * c * math.cos(th),
              HC.z + (HCZ + off) * math.sin(phi)))


def phi_of(z):
    return math.asin(max(-0.999, min(0.999, (z - HC.z) / HCZ)))


def helmet_normal(th, phi):
    a, b = helmet_pt(th - 0.01, phi), helmet_pt(th + 0.01, phi)
    c, d = helmet_pt(th, phi - 0.01), helmet_pt(th, phi + 0.01)
    n = (b - a).cross(d - c).normalized()
    return n if n.dot(helmet_pt(th, phi) - HC) > 0 else -n


def on_shell(th, z, off=0.0):
    phi = phi_of(z)
    n = helmet_normal(th, phi)
    return helmet_pt(th, phi) + n * off, n


def tbox(md, p, n, w, h, d, up=(0, 0, 1)):
    """Box w (side) x h (up) x d (along n) whose back face sits on p, facing n.  Returns its matrix."""
    m = look_matrix(p + V(n) * (d / 2), n, up)
    md.add(box(w, h, d).transform(m))
    return m


def corrugated(path, r, pitch=0.0085, depth=0.003, n=16):
    pts = L.resample(path, max(8, int(L.path_length(path) / pitch * 6)))
    Lt = L.path_length(pts)

    def sc(t):
        return 1.0 + (depth / r) * ((0.5 + 0.5 * math.cos(TAU * t * Lt / pitch)) ** 3 - 1.0)

    return tube(pts, r, n, scale=sc)


def build(coll, root):
    # ------------------------------------------------------------------------- helmet shell
    def shell(u, v, i, j):
        p0 = phi_of(edge_z(u))
        return helmet_pt(u, lerp(p0, math.pi / 2 - 1e-3, v ** 0.9))

    hs = to_obj("Helmet_Shell", grid(shell, lin(-math.pi, math.pi, 112), lin(0, 1, 34), closed_u=True),
                M["helmet"], coll, parent=root)
    mod_solidify(hs, 0.011, -1.0)
    mod_subsurf(hs, 1, 2)
    edge = [helmet_pt(th, phi_of(edge_z(th))) for th in lin(-math.pi, math.pi, 180)[:-1]]
    edge = [p + (p - HC).normalized() * 0.002 for p in edge]
    to_obj("Helmet_Edge_Trim", tube(edge, 0.006, 8, closed=True), M["rubber"], coll, parent=root)
    seams = MD()
    for s in (-1, 1):
        for th_d in (68, 88):
            th = s * math.radians(th_d)
            seams.add(tube([helmet_pt(th, phi, 0.0008) for phi in lin(phi_of(1.80), math.radians(68), 10)], 0.0012, 5))
    to_obj("Helmet_Seams", seams, M["rubber"], coll, parent=root)

    # velcro: crown strip along the midline and a panel on each upper side
    velcro = MD()

    def crown(u, v, i, j):
        x = lerp(-0.020, 0.020, u)
        ang = lerp(math.radians(26), math.radians(150), v)
        k = math.sqrt(max(0.0, 1 - (x / HA) ** 2))
        p = V((x, HC.y - HB * math.cos(ang) * k, HC.z + HCZ * math.sin(ang) * k))
        return p + (p - HC).normalized() * 0.004

    velcro.add(grid(crown, lin(0, 1, 3), lin(0, 1, 26)))
    for s in (-1, 1):
        velcro.add(grid(lambda u, v, i, j, s=s: helmet_pt(s * math.radians(lerp(42, 70, u)),
                                                          math.radians(lerp(40, 58, v)), 0.003),
                        lin(0, 1, 6), lin(0, 1, 4)))
    vo = to_obj("Helmet_Velcro_Panels", velcro, M["velcro"], coll, parent=root)
    mod_solidify(vo, 0.003, 1.0)

    # ------------------------------------------------------------------------- rail band ring + bits
    rails, metal, poly = MD(), MD(), MD()

    def band_z(th):
        a = abs(math.degrees(math.atan2(math.sin(th), math.cos(th))))
        return interp_smooth([(0, 1.768), (40, 1.778), (60, 1.781), (110, 1.781), (140, 1.762), (180, 1.756)], a)[0]

    def band_h(th):
        a = abs(math.degrees(math.atan2(math.sin(th), math.cos(th))))
        return interp_smooth([(0, 0.020), (110, 0.022), (150, 0.036), (180, 0.040)], a)[0]

    ths = lin(-math.pi, math.pi, 128)
    band, ups = [], []
    for th in ths:
        p, n = on_shell(th, band_z(th), 0.004)
        band.append(p)
        ups.append(n)
    rails.add(sweep(band, rect_profile(0.022, 0.008), up=lambda i, p: ups[i],
                    scale=lambda t: (band_h(lerp(-math.pi, math.pi, t)) / 0.022, 1.0)))
    for s in (-1, 1):
        for k in range(5):  # picatinny cross-ribs on the side rails
            p, n = on_shell(s * math.radians(48 + k * 11), 1.781, 0.010)
            tbox(metal, p, n, 0.004, 0.020, 0.003)
        p, n = on_shell(s * math.radians(118), 1.772, 0.012)  # rear brackets with oval windows
        ov = torus_md(0.018, 0.004, 24, 6)
        ov.v = [V((q.x * 0.85, q.y * 1.1, q.z)) for q in ov.v]
        metal.add(ov.transform(look_matrix(p, n, (0, 0, 1))))
        for k in range(3):
            pp, nn = on_shell(s * math.radians(128 + k * 7), 1.770, 0.012)
            tbox(poly, pp, nn, 0.012, 0.008, 0.002)
        arch = []
        for t in lin(0, 1, 16):  # forehead arches (inverted U) either side of the shroud
            a_ = math.pi * t
            x = s * 0.066 + 0.0175 * math.cos(a_)
            arch.append(on_shell(math.atan2(x / HA, 1.0), 1.761 + 0.040 * math.sin(a_), 0.006)[0])
        metal.add(tube(arch, 0.0032, 6))
        p, n = on_shell(math.atan2(s * 0.066 / HA, 1.0), 1.785, 0.005)
        ovl = torus_md(0.009, 0.0025, 16, 5)
        ovl.v = [V((q.x * 0.7, q.y * 1.1, q.z)) for q in ovl.v]
        metal.add(ovl.transform(look_matrix(p, n, (0, 0, 1))))
        p, n = on_shell(s * math.radians(52), 1.760, 0.006)  # ring knobs at the front of the rails
        metal.add(torus_md(0.0095, 0.0035, 20, 6).transform(look_matrix(p, n, (0, 0, 1))))
        metal.add(lathe([(0.0, 0.0), (0.006, 0.0), (0.006, 0.004), (0.0, 0.004)], 12).transform(look_matrix(p, n, (0, 0, 1))))
        p, n = on_shell(s * math.radians(90), 1.783, 0.012)  # pill-shaped rail lights, two lenses each
        lm = tbox(poly, p, n, 0.070, 0.030, 0.020)
        for dy in (-0.0125, 0.0125):
            lp = lm @ V((dy, 0.0, 0.0105))
            LENSES.add(lathe([(0.0, 0.0), (0.006, 0.0), (0.006, 0.002), (0.0, 0.002)], 16)
                       .transform(look_matrix(lp, n, (0, 0, 1))))
            metal.add(torus_md(0.0068, 0.0015, 16, 4).transform(look_matrix(lp, n, (0, 0, 1))))
        p, n = on_shell(s * math.radians(142), 1.800, 0.004)  # rear antenna boxes + whip rods + pale lens
        bm = tbox(poly, p, n, 0.035, 0.050, 0.026)
        top = bm @ V((0, 0.025, 0.013))
        metal.add(tube([top, top + V((s * 0.003, 0.002, 0.036))], 0.0025, 8))
        metal.add(uv_sphere(0.004, 8, 5).translate(top + V((s * 0.003, 0.002, 0.040))))
        LENSES.add(lathe([(0.0, 0.0), (0.005, 0.0), (0.005, 0.002), (0.0, 0.002)], 12)
                   .transform(look_matrix(bm @ V((0.0, -0.016, 0.0135)), n, (0, 0, 1))))
        a = helmet_pt(s * math.radians(36), math.radians(48), 0.004)  # small strap across the upper side
        b = helmet_pt(s * math.radians(70), math.radians(38), 0.004)
        poly.add(sweep([a, (a + b) / 2 + (a - HC).normalized() * 0.003, b], rect_profile(0.012, 0.002),
                       up=(a - HC).normalized()))
    # crown top block, rear battery/counterweight box (with latch window), retention dial and nape loop
    tbox(poly, helmet_pt(0.0, math.radians(84), 0.004), helmet_normal(0.0, math.radians(84)), 0.037, 0.030, 0.012,
         up=(0, -1, 0))
    p, n = on_shell(math.pi, 1.812, 0.002)
    bm = tbox(poly, p, n, 0.040, 0.066, 0.022)
    tbox(metal, bm @ V((0, 0.006, 0.011)), n, 0.016, 0.010, 0.002)
    dial = V((0.0, 0.072, 1.700))
    tbox(poly, dial, V((0, 1, 0)), 0.040, 0.052, 0.012)
    metal.add(lathe([(0.0, 0.0), (0.010, 0.0), (0.010, 0.006), (0.0, 0.007)], 20)
              .transform(look_matrix(dial + V((0, 0.012, 0)), (0, 1, 0), (0, 0, 1))))
    tbox(poly, V((0.0, 0.092, 1.668)), V((0, 1, 0)), 0.058, 0.025, 0.008)

    # ------------------------------------------------------------------------- NVG shroud, hinge, flipped-up binocular
    nvg = MD()
    shroud = grid(lambda u, v, i, j: on_shell(math.atan2(lerp(-0.0225, 0.0225, u) / HA, 1.0), lerp(1.738, 1.778, v),
                                              0.004)[0], lin(0, 1, 6), lin(0, 1, 5))
    boss = V((0.0, -0.178, 1.749))
    nvg.add(torus_md(0.0095, 0.0035, 20, 6).transform(look_matrix(boss, (0, -1, 0), (0, 0, 1))))
    nvg.add(lathe([(0.0, -0.008), (0.006, -0.008), (0.006, 0.004), (0.0, 0.004)], 12)
            .transform(look_matrix(boss, (0, -1, 0), (0, 0, 1))))
    nvg.add(sweep([boss + V((0, -0.004, 0.006)), V((0.0, -0.213, 1.762))], rect_profile(0.018, 0.012), up=(0, -1, 0.3)))
    ax = V((0.0, 0.55, 0.83)).normalized()           # ocular tube axis: lower-front -> upper-rear
    side = V((1, 0, 0))
    upv = ax.cross(side).normalized()
    bridge = box(0.035, 0.050, 0.040)
    mb = Matrix((side, ax, upv)).transposed().to_4x4()
    mb.translation = V((0.0, -0.205, 1.795))
    nvg.add(bridge.transform(mb))
    for s in (-1, 1):
        a = V((s * 0.030, -0.235, 1.755))
        tb = lathe([(0.0, 0.0), (0.016, 0.0), (0.016, 0.012), (0.015, 0.014), (0.015, 0.060), (0.0155, 0.072),
                    (0.0, 0.072)], 24)
        nvg.add(tb.transform(look_matrix(a, ax, (0, 0, 1))))
        nvg.add(torus_md(0.0125, 0.0040, 24, 6).transform(look_matrix(V((s * 0.050, -0.205, 1.790)), (s, 0, 0), (0, 0, 1))))
        nvg.add(lathe([(0.0, 0.0), (0.012, 0.0), (0.012, 0.006), (0.0, 0.006)], 16)
                .transform(look_matrix(V((s * 0.048, -0.205, 1.790)), (s, 0, 0), (0, 0, 1))))
        LENSES_DARK.add(lathe([(0.0, 0.0), (0.0135, 0.0), (0.0, 0.002)], 20)
                        .transform(look_matrix(a - ax * 0.001, -ax, (0, 0, 1))))
        nvg.add(box(0.008, 0.008, 0.006).translate((s * 0.009, -0.185, 1.871)))
        nvg.add(box(0.014, 0.012, 0.012).translate((s * 0.040, -0.222, 1.770)))
    nvg.add(box(0.037, 0.030, 0.030).translate((0.0, -0.185, 1.853)))
    LENSES.add(box(0.010, 0.002, 0.009).translate((0.0, -0.226, 1.808)))

    # ------------------------------------------------------------------------- comms ear cups (D-shaped)
    cups, cupd = MD(), MD()
    for s in (-1, 1):
        c = V((s * 0.103, -0.045, 1.700))
        n = V((s, 0, 0))

        def cup(u, v, i, j, s=s, c=c):
            ca, sa = math.cos(u), math.sin(u)
            e = 2.0 / (4.0 if ca < 0 else 2.6)  # flatter (D) toward the front edge
            yy = math.copysign(abs(ca) ** e, ca) * 0.0375
            zz = math.copysign(abs(sa) ** (2.0 / 2.8), sa) * 0.041
            if v <= 0.8:
                x, r = lerp(0.0, 0.033, v / 0.8), 1.0 - 0.10 * smooth((v - 0.55) / 0.25)
            else:
                x, r = 0.035, 0.9 * (1.0 - (v - 0.8) / 0.2)
            return V((c.x + s * (x - 0.016), c.y - yy * r, c.z + zz * r))

        cups.add(grid(cup, lin(0, TAU, 40), lin(0, 1, 10), closed_u=True, pole_v1=True, flip=(s < 0)))
        face = V((c.x + s * 0.0195, c.y, c.z))
        cupd.add(torus_md(0.025, 0.0022, 32, 5).transform(look_matrix(face + n * 0.001, n, (0, 0, 1))))
        cupd.add(lathe([(0.0, 0.0), (0.009, 0.0), (0.009, 0.006), (0.0, 0.0065)], 20)
                 .transform(look_matrix(face, n, (0, 0, 1))))
        metal.add(torus_md(0.0095, 0.0016, 20, 4).transform(look_matrix(face + n * 0.004, n, (0, 0, 1))))
        for dy in (-0.030, 0.030):  # mounting arms up to the rail
            a_ = V((c.x + s * 0.008, c.y + dy, c.z + 0.036))
            b_ = V((s * 0.104, c.y + dy, 1.776))
            poly.add(sweep([a_, b_], rect_profile(0.012, 0.006), up=n))

    # ------------------------------------------------------------------------- goggle: one panoramic lens + frame
    def gog_pt(th, z, off=0.0):
        bul = 0.006 * (1 - ((z - 1.699) / 0.036) ** 2)
        R = GOG_R + off + bul
        return V((GOG_C.x + R * math.sin(th), GOG_C.y - R * math.cos(th), z))

    def notch(th):
        x = abs(GOG_R * math.sin(th))
        if x < 0.009:
            return 1.692
        if x < 0.017:
            return lerp(1.692, 1.668, (x - 0.009) / 0.008)
        return 1.668

    th_max = math.radians(56)
    LENSES_VISOR.add(grid(lambda u, v, i, j: gog_pt(u, lerp(notch(u), 1.731, v), 0.001), lin(-th_max, th_max, 56),
                          lin(0, 1, 10)))
    frame = MD()
    ring = ([gog_pt(th, 1.733, 0.004) for th in lin(-th_max, th_max, 40)] +
            [gog_pt(th_max + 0.03, lerp(1.731, 1.668, t), 0.004) for t in lin(0.1, 0.9, 6)] +
            [gog_pt(th, notch(th) - 0.003, 0.004) for th in lin(th_max, -th_max, 56)] +
            [gog_pt(-th_max - 0.03, lerp(1.668, 1.731, t), 0.004) for t in lin(0.1, 0.9, 6)])
    frame.add(tube(ring, 0.0065, 8, closed=True))
    frame.add(grid(lambda u, v, i, j: gog_pt(u, lerp(1.663, 1.736, v), -0.004), lin(-th_max - 0.06, th_max + 0.06, 40),
                   lin(0, 1, 6)))
    for s in (-1, 1):
        a = gog_pt(s * (th_max + 0.05), 1.700, 0.0)
        frame.add(sweep([a, V((s * 0.096, -0.080, 1.700))], rect_profile(0.030, 0.004), up=(s, 0.3, 0)))
    to_obj("Goggle_Lens", LENSES_VISOR, M["visor"], coll, parent=root)
    fo = to_obj("Goggle_Frame", frame, M["rubber"], coll, parent=root)
    mod_subsurf(fo, 1, 1)

    # ------------------------------------------------------------------------- respirator (faceted)
    # control outline per height: front y, cheek (x, y), rear edge (x, y)
    RT = [(1.561, -0.160, 0.045, -0.140, 0.050, -0.105), (1.590, -0.178, 0.065, -0.130, 0.075, -0.090),
          (1.620, -0.182, 0.075, -0.128, 0.084, -0.087), (1.645, -0.186, 0.080, -0.125, 0.088, -0.085),
          (1.665, -0.180, 0.084, -0.122, 0.090, -0.086)]

    def rpt(u, z):
        """u in -1..1 across the mask (0 = nose ridge); piecewise-linear facets through the control outline."""
        yf, xc, yc, xr, yr = [interp_smooth([(r[0], r[k]) for r in RT], z)[0] for k in range(1, 6)]
        a = abs(u)
        if a < 0.5:
            t = a / 0.5
            x, y = lerp(0.0, xc, t), lerp(yf, yc, t)
            y -= 0.010 * math.exp(-(a / 0.08) ** 2) * smooth((z - 1.60) / 0.03)  # nose ridge prism
        else:
            t = (a - 0.5) / 0.5
            x, y = lerp(xc, xr, t), lerp(yc, yr, t)
        return V((math.copysign(x, u), y, z))

    ro = to_obj("Mask_Respirator", grid(lambda u, v, i, j: rpt(u, lerp(1.561, 1.665, v)), lin(-1, 1, 24), lin(0, 1, 12)),
                M["mask"], coll, parent=root, smooth=False)
    mod_solidify(ro, 0.006, 1.0)
    mod_bevel(ro, 0.0015, 1)
    to_obj("Mask_Chin", grid(lambda u, v, i, j: rpt(u, 1.561) * (1 - v) + V((0.0, -0.13, 1.556)) * v, lin(-1, 1, 16),
                             lin(0, 1, 3), flip=True), M["mask"], coll, parent=root)
    rs_t = MD()
    rs_t.add(tube([rpt(u, 1.648) + V((0, -0.0015, 0)) for u in lin(-0.55, 0.55, 12)], 0.0013, 5))
    for s in (-1, 1):
        rs_t.add(tube([rpt(s * lerp(0.95, 0.30, t), lerp(1.662, 1.612, t)) + V((0, -0.0015, 0)) for t in lin(0, 1, 10)],
                      0.0013, 5))
    to_obj("Mask_Seams", rs_t, M["rubber"], coll, parent=root)
    reg = MD()
    axr = V((0, -1, 0))
    reg.add(lathe([(0.0, 0.0), (0.0275, 0.0), (0.0275, 0.024), (0.0175, 0.026), (0.0175, 0.022), (0.0, 0.022)], 32)
            .transform(look_matrix(REG_C + V((0, 0.026, 0)), axr, (0, 0, 1))))
    reg.add(box(0.065, 0.020, 0.055).translate(REG_C + V((0, 0.035, 0))))
    for k in range(6):
        reg.add(box(0.026, 0.002, 0.002).translate(REG_C + V((0, -0.0005, -0.010 + k * 0.004))))
    for s in (-1, 1):
        reg.add(lathe([(0.0, 0.0), (0.007, 0.0), (0.007, 0.015), (0.0, 0.015)], 12)
                .transform(look_matrix(V((s * 0.042, -0.160, 1.593)), V((s, 0.6, 0)).normalized(), (0, 0, 1))))
    to_obj("Mask_Regulator", reg, M["polymer_gloss"], coll, parent=root)
    metal.add(torus_md(0.0235, 0.0035, 32, 6).transform(look_matrix(REG_C + V((0, 0.003, 0)), axr, (0, 0, 1))))
    jaw = MD()
    for s in (-1, 1):
        P = [V((s * 0.045, -0.158, 1.592)), V((s * 0.068, -0.132, 1.612)), V((s * 0.086, -0.098, 1.635)),
             V((s * 0.092, -0.060, 1.648))]
        jaw.add(corrugated(catmull_path(P, 6), 0.0075, pitch=0.006, depth=0.0018, n=10))
        jaw.add(lathe([(0.0, 0.0), (0.010, 0.0), (0.010, 0.010), (0.0, 0.010)], 14)
                .transform(look_matrix(V((s * 0.093, -0.055, 1.650)), V((s * 0.3, 1, 0.2)).normalized(), (0, 0, 1))))
    to_obj("Mask_Jaw_Hoses", jaw, M["rubber"], coll, parent=root)
    hz = MD()
    for s in (-1, 1):
        a = rpt(s * 1.0, 1.640)
        hz.add(sweep([a, V((s * 0.094, -0.035, 1.66)), V((s * 0.085, 0.02, 1.665))], rect_profile(0.018, 0.003),
                     up=(s, 0, 0)))
    to_obj("Mask_Harness", hz, M["nylon_dark"], coll, parent=root)

    # ------------------------------------------------------------------------- rebreather neck manifold + hose wrap
    Mf = MANIFOLD
    axis_pts = [V((lerp(Mf["x0"], Mf["x1"], t), Mf["y"], Mf["z"])) for t in lin(0, 1, 16)]

    def man_r(t, u):
        cap = min(1.0, min(t, 1 - t) / 0.08)
        return Mf["r"] * (0.70 + 0.30 * math.sqrt(max(0.0, cap)))

    to_obj("Rebreather_Manifold", L.limb(axis_pts, man_r, 32, ref=(0, 0, 1), cap0=True, cap1=True),
           M["rubber"], coll, parent=root)
    # the hose is coiled over the whole manifold, end domes included, so the hump behind the neck reads ribbed
    hel = []
    turns, steps = 11, 40
    for k in range(turns * steps + 1):
        t = k / (turns * steps)
        a = TAU * k / steps
        rr = man_r(lerp(0.02, 0.98, t), 0.0) + 0.013
        hel.append(V((lerp(Mf["x0"] + 0.012, Mf["x1"] - 0.012, t), Mf["y"] + rr * math.sin(a),
                      Mf["z"] + rr * math.cos(a))))
    to_obj("Rebreather_Manifold_Hose_Wrap", corrugated(hel, 0.0155, pitch=0.0065, depth=0.0018, n=10), M["rubber"],
           coll, parent=root)
    for s in (-1, 1):
        pc = V((0.170 if s > 0 else -0.160, Mf["y"] + 0.040, Mf["z"] + 0.015))
        metal.add(lathe([(0.0, 0.0), (0.020, 0.0), (0.020, 0.010), (0.011, 0.010), (0.011, 0.006), (0.0, 0.006)], 24)
                  .transform(look_matrix(pc, V((s * 0.5, 0.7, 0.4)).normalized(), (0, 0, 1))))
    tbox(poly, V((0.008, Mf["y"] + 0.066, Mf["z"] + 0.045)), V((0, 1, 0)), 0.060, 0.030, 0.020)

    # ------------------------------------------------------------------------- the main breathing-hose loop
    P = [V((0.150, 0.075, 1.608)), V((0.180, -0.035, 1.590)), V((0.162, -0.135, 1.546)), V((0.110, -0.176, 1.519)),
         V((0.0, -0.204, 1.508))]
    full = P + [V((-p.x, p.y, p.z)) for p in reversed(P[:-1])]
    hose = corrugated(catmull_path(full, 10), 0.0225, pitch=0.0095, depth=0.0034, n=18)
    for p, d in ((full[0], (full[0] - full[1]).normalized()), (full[-1], (full[-1] - full[-2]).normalized())):
        hose.add(lathe([(0.0, -0.022), (0.022, -0.022), (0.023, 0.0), (0.0, 0.0)], 24).transform(look_matrix(p, d)))
    to_obj("Breathing_Hose_Loop", hose, M["rubber"], coll, parent=root)

    # ------------------------------------------------------------------------- remaining objects
    sh = to_obj("NVG_Shroud", shroud, M["metal_black"], coll, parent=root)
    mod_solidify(sh, 0.008, 1.0)
    no = to_obj("NVG_Binocular_Mount", nvg, M["polymer"], coll, parent=root)
    mod_bevel(no, 0.002, 2)
    to_obj("Helmet_Rail_Band", rails, M["rail"], coll, parent=root)
    to_obj("Helmet_Metal_Bits", metal, M["metal"], coll, parent=root)
    po = to_obj("Helmet_Accessories", poly, M["polymer"], coll, parent=root)
    mod_bevel(po, 0.003, 2)
    co = to_obj("Comms_Ear_Cups", cups, M["polymer"], coll, parent=root)
    mod_subsurf(co, 1, 1)
    to_obj("Comms_Ear_Cup_Rings", cupd, M["polymer_gloss"], coll, parent=root)
    to_obj("Helmet_Light_Lenses", LENSES, M["lens_pale"], coll, parent=root)
    to_obj("NVG_Objective_Lenses", LENSES_DARK, M["lens_dark"], coll, parent=root)
    for md in (LENSES, LENSES_DARK, LENSES_VISOR):
        md.v, md.f, md.uv, md.mi, md.hem = [], [], [], [], []
