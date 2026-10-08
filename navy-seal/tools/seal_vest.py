"""Plate carrier, measured from the concept: curved front/back plate bags, padded shoulder straps with armhole piping,
cummerbund, MOLLE, the upper row (two flap pouches around the dive computer, the hose-clip box), the magazine row
(three mag pouches, a narrow dark pouch, two angled corner pouches), side and rear cummerbund pouches, the back
(drag-handle box, central rebreather case, MOLLE, edge straps), the coiled PTT cable, the beaded antenna lead,
the single whip antenna, and the subdued flag + velcro ID patches on the deltoids."""
import math

from mathutils import Matrix

import seal_lib as L
from seal_lib import (MD, TAU, V, box, catmull_path, grid, interp_smooth, lathe, lerp, lin, look_matrix, mod_bevel,
                      mod_solidify, mod_subsurf, rect_profile, smooth, sweep, to_obj, torus_md, tube, uv_sphere)
from seal_mats import M
import seal_body as B

T_PLATE = 0.035
BEND_R = 0.60


def front_y(x, outer=True):
    """Front plate bag: inner face at Y -0.155 at the centre, curving back with a 0.6 m bend radius."""
    yin = -0.155 + x * x / (2 * BEND_R)
    return yin - (T_PLATE if outer else 0.0)


def back_y(x, outer=True):
    yin = 0.155 - x * x / (2 * BEND_R)
    return yin + (T_PLATE if outer else 0.0)


def front_top(x):
    return 1.450 + 0.030 * smooth(abs(x) / 0.085)  # shallow neck scoop


FX0, FX1, FZ0 = -0.158, 0.157, 1.085
BX, BZ0, BZ1 = 0.170, 1.085, 1.520


def frame_flat(xc, zc, inset=0.0):
    """Frame on the outer face of the front plate bag at (x, z): x right, n forward (-Y), z up."""
    return V((xc, front_y(xc) - inset, zc)), V((1, 0, 0)), V((0, -1, 0)), V((0, 0, 1))


def frame_dir(cx, cy, zc, nx, ny, d):
    """Frame for a pouch of depth d whose CENTRE is (cx, cy) and whose face points along (nx, ny)."""
    n = V((nx, ny, 0)).normalized()
    x = V((0, 0, 1)).cross(n).normalized() * -1.0
    p = V((cx, cy, zc)) - n * (d / 2)
    return p, x, n, V((0, 0, 1))


def pouch(md_body, md_flap, md_trim, md_metal, p, x, n, z, w, h, d, flap=0.24, bungee=True, tab=True, bands=2):
    """Pouch on a surface frame: p = centre of its back face; body w (x) by h (z) by d (n).  Rounded body (bevel
    on the object), overhanging top flap with a pull tab, optional bungee, elastic bands, bottom drain grommet."""
    m = Matrix((x, n, z)).transposed().to_4x4()
    m.translation = p
    b = box(w, d, h)
    # slight front bulge: push the front-face vertices outward a touch in the middle
    md_body.add(b.transform(m @ Matrix.Translation((0, d / 2, 0))))
    fh = h * flap

    def ff(uu, vv, i, j):
        xx = lerp(-w / 2 - 0.003, w / 2 + 0.003, uu)
        if vv < 0.3:
            t = vv / 0.3
            yy = lerp(0.004, d + 0.004, t)
            zz = h / 2 + 0.004 + 0.003 * math.sin(math.pi * t)
        else:
            t = (vv - 0.3) / 0.7
            yy = d + 0.004 + 0.0015 * math.sin(math.pi * t)
            zz = h / 2 + 0.004 - t * fh
        corner = max(0.0, abs(xx) - (w / 2 - 0.010)) / 0.013
        zz += 0.010 * (1 - math.sqrt(max(0.0, 1 - corner * corner))) * (t if vv >= 0.3 else 0.0)
        return m @ V((xx, yy, zz))

    md_flap.add(grid(ff, lin(0, 1, 10), lin(0, 1, 9)))
    if tab:
        md_trim.add(box(0.016, 0.004, 0.022).transform(m @ Matrix.Translation((0, d + 0.008, h / 2 - fh - 0.004))))
    if bungee:
        cord = [m @ V((0, d + 0.006, h / 2 + 0.002)), m @ V((0, d + 0.009, h / 2 - fh * 0.5)),
                m @ V((0, d + 0.007, h / 2 - fh - 0.014))]
        md_trim.add(tube(catmull_path(cord, 4), 0.0022, 6))
    for k in range(bands):
        md_trim.add(box(w + 0.004, 0.003, 0.012).transform(m @ Matrix.Translation((0, d + 0.0005, -h * (0.18 + 0.2 * k)))))
    md_metal.add(torus_md(0.0035, 0.0012, 12, 4).transform(m @ Matrix.Translation((0, d * 0.5, -h / 2 - 0.0005))))
    return m


def arm_surface(side, y, z, off=0.003):
    """Point on the outer deltoid/sleeve surface (facing +-X) at world (y, z)."""
    path = B.arm_path(side)
    best = None
    for k in range(len(path) - 1):
        if (path[k].z - z) * (path[k + 1].z - z) <= 0:
            f = (path[k].z - z) / (path[k].z - path[k + 1].z + 1e-9)
            best = (k + f) / (len(path) - 1)
            break
    t = best if best is not None else 0.2
    c, T, N, Bv = B.limb_frame(path, t)
    r = B.arm_radius(t, -side * math.pi / 2)
    dy = y - c.y
    x = c.x + side * math.sqrt(max(0.0, r * r - dy * dy))
    return V((x + side * off, y, z))


def build(coll, root):
    bags, straps, pouches, flaps, trims, metal, molle, hard = MD(), MD(), MD(), MD(), MD(), MD(), MD(), MD()
    pouch_w, flap_w = MD(), MD()   # warmer-print pouches
    pouch_c, flap_c = MD(), MD()   # cooler, darker pouches

    # ------------------------------------------------------------------ plate bags
    bags.add(grid(lambda u, v, i, j: V((u, front_y(u, False), lerp(FZ0, front_top(u), v))), lin(FX0, FX1, 30),
                  lin(0, 1, 18)))
    bags.add(grid(lambda u, v, i, j: V((u, back_y(u, False), lerp(BZ0, BZ1, v))), lin(-BX, BX, 30), lin(0, 1, 18),
                  flip=True))
    # cummerbund (each side from behind the front bag edge around the flank to behind the back bag edge)
    plan = catmull_path([V((0.148, -0.150, 0)), V((0.178, -0.110, 0)), V((0.193, -0.020, 0)), V((0.189, 0.080, 0)),
                         V((0.170, 0.135, 0)), V((0.150, 0.128, 0))], 6)
    cb = grid(lambda u, v, i, j: V((plan[i].x, plan[i].y, lerp(1.085, 1.275, v))), list(range(len(plan))),
              lin(0, 1, 8))
    bags.add(cb)
    bags.add(cb.mirror_x())
    # binding tape around both plate bags
    for yf, xs, ztop, zb in ((front_y, (FX0, FX1), front_top, FZ0), (back_y, (-BX, BX), lambda x: BZ1, BZ0)):
        out = -1 if yf is front_y else 1
        ring = ([V((x, yf(x, False) + out * T_PLATE / 2, zb)) for x in lin(xs[0], xs[1], 20)] +
                [V((xs[1], yf(xs[1], False) + out * T_PLATE / 2, z)) for z in lin(zb, ztop(xs[1]), 12)[1:]] +
                [V((x, yf(x, False) + out * T_PLATE / 2, ztop(x))) for x in lin(xs[1], xs[0], 20)[1:]] +
                [V((xs[0], yf(xs[0], False) + out * T_PLATE / 2, z)) for z in lin(ztop(xs[0]), zb, 12)[1:-1]])
        trims.add(tube(ring, T_PLATE / 2 + 0.002, 8, closed=True))

    # ------------------------------------------------------------------ shoulder straps + armhole piping
    for s in (-1, 1):
        path = catmull_path([V((s * 0.150, -0.180, 1.470)), V((s * 0.160, -0.105, 1.552)), V((s * 0.165, 0.000, 1.578)),
                             V((s * 0.165, 0.100, 1.560)), V((s * 0.160, 0.180, 1.515))], 8)
        straps.add(sweep(path, rect_profile(0.055, 0.020, 3),
                         up=lambda i, p, s=s: (p - V((s * 0.110, 0.0, 1.400))).normalized()))
        pipe = [V((s * (0.190 + 0.010 * math.cos(t)), 0.135 * math.sin(t), 1.290 + 0.287 * math.cos(t)))
                for t in lin(-math.pi / 2, math.pi / 2, 30)]
        straps.add(tube(pipe, 0.010, 10))
        # lettering marks on top of the right strap
        if s < 0:
            for k in range(6):
                hard.add(box(0.004, 0.003, 0.006).translate((s * 0.166, -0.030 + k * 0.008, 1.590)))
        # edge straps down the back bag sides with stitch dots
        e0 = V((s * 0.168, back_y(0.168) + 0.002, 1.240))
        molle.add(sweep([e0, e0 + V((0, 0, 0.37))], rect_profile(0.030, 0.003), up=(0, 1, 0)))

    # ------------------------------------------------------------------ MOLLE: exposed front band + back rows + cummerbund
    for zz in (1.304,):
        molle.add(sweep([V((x, front_y(x) - 0.002, zz)) for x in lin(-0.150, 0.150, 16)], rect_profile(0.025, 0.003),
                        up=(0, -1, 0)))
        for xb in (-0.06, 0.0, 0.06):
            p, x, n, z = frame_flat(xb, zz, 0.004)
            hard.add(box(0.025, 0.008, 0.018).transform(Matrix((x, n, z)).transposed().to_4x4()).translate(p))
    molle.add(sweep([V((0.025, front_y(0.025) - 0.003, z)) for z in (1.290, 1.330)], rect_profile(0.020, 0.003),
                    up=(0, -1, 0)))
    for k in range(3):
        zz = 1.268 + k * 0.0305
        molle.add(sweep([V((x, back_y(x) + 0.002, zz)) for x in lin(-0.160, 0.160, 16)], rect_profile(0.025, 0.003),
                        up=(0, 1, 0)))
    for s in (1, -1):
        for k in range(6):
            zz = 1.098 + k * 0.0305
            row = [V((s * p.x * 1.0 + s * 0.012 * 0, p.y, zz)) for p in plan]
            row = [V((s * abs(p.x) + s * 0.013, p.y, zz)) for p in plan]
            molle.add(sweep(row, rect_profile(0.025, 0.003), up=(0, 0, 1)))

    # ------------------------------------------------------------------ upper row
    p, x, n, z = frame_flat(-0.1055, 1.3855)
    pouch(pouch_c, flap_c, trims, metal, p, x, n, z, 0.075, 0.133, 0.035, flap=0.33, bungee=False)
    p, x, n, z = frame_flat(0.092, 1.3855)
    pouch(pouch_w, flap_w, trims, metal, p, x, n, z, 0.072, 0.133, 0.035, flap=0.33, bungee=False)
    for xs_ in (0.083, 0.101):  # light stitch lines on its face
        hard.add(box(0.003, 0.002, 0.07).translate((xs_, front_y(xs_) - 0.0365, 1.355)))
    # dive computer: housing, recessed screen, knurled knob, bezel strip, strap tab up into the clip box
    dc = MD()
    p, x, n, z = frame_flat(-0.006, 1.3825)
    m = Matrix((x, n, z)).transposed().to_4x4()
    m.translation = p
    dc.add(box(0.124, 0.030, 0.109).transform(m @ Matrix.Translation((0, 0.015, 0))))
    screen = grid(lambda u, v, i, j: m @ V((-0.013 + lerp(-0.0375, 0.0375, u), 0.0305, 0.0105 + lerp(-0.031, 0.031, v))),
                  lin(0, 1, 2), lin(0, 1, 2))
    knob = lathe([(0.0, 0.0), (0.015, 0.0), (0.015, 0.010), (0.013, 0.012), (0.0, 0.012)], 24)
    for k in range(24):  # knurl
        a = TAU * k / 24
        dc.add(box(0.002, 0.002, 0.010).transform(m @ Matrix.Translation((0.042 + 0.015 * math.cos(a), 0.035,
                                                                           -0.0145 + 0.015 * math.sin(a)))))
    dc.add(knob.transform(m @ Matrix.Translation((0.042, 0.030, -0.0145)) @ Matrix.Rotation(-math.pi / 2, 4, "X")))
    hard.add(box(0.110, 0.002, 0.008).transform(m @ Matrix.Translation((0.0, 0.031, -0.037))))
    hard.add(box(0.020, 0.003, 0.035).transform(m @ Matrix.Translation((-0.014, 0.031, 0.065))))
    # hose-clip / magnetic mount box with light buckle tabs (the hose U-loop rests on it)
    p, x, n, z = frame_flat(-0.019, 1.4635)
    mb = Matrix((x, n, z)).transposed().to_4x4()
    mb.translation = p
    dc.add(box(0.062, 0.030, 0.053).transform(mb @ Matrix.Translation((0, 0.015, 0))))
    for s in (-1, 1):
        hard.add(box(0.012, 0.010, 0.008).transform(mb @ Matrix.Translation((s * 0.022, 0.020, 0.028))))

    # ------------------------------------------------------------------ magazine row
    for (x0, x1, z0, z1, kind) in ((-0.140, -0.062, 1.101, 1.288, "B"), (-0.028, 0.044, 1.107, 1.288, "C"),
                                   (0.053, 0.128, 1.101, 1.281, "D")):
        xc = (x0 + x1) / 2
        p, x, n, z = frame_flat(xc, (z0 + z1) / 2)
        tgt_b, tgt_f = (pouch_w, flap_w) if kind == "D" else (pouches, flaps)
        m = pouch(tgt_b, tgt_f, trims, metal, p, x, n, z, x1 - x0, z1 - z0, 0.066, flap=0.24,
                  bungee=(kind == "B"), tab=(kind != "C"), bands=2)
        if kind == "C":  # dagger-shaped pull tab with a crossbar
            hard.add(box(0.006, 0.004, 0.069).transform(m @ Matrix.Translation((0.002, 0.071, 0.040))))
            hard.add(box(0.016, 0.004, 0.004).transform(m @ Matrix.Translation((0.002, 0.071, 0.046))))
        if kind == "D":  # snap
            metal.add(lathe([(0.0, 0.0), (0.004, 0.0), (0.004, 0.002), (0.0, 0.002)], 12)
                      .transform(m @ Matrix.Translation((0.010, 0.071, 0.072)) @ Matrix.Rotation(-math.pi / 2, 4, "X")))
    p, x, n, z = frame_flat(-0.045, 1.1975)
    pouch(pouch_c, flap_c, trims, metal, p, x, n, z, 0.034, 0.175, 0.040, flap=0.17, bungee=False, tab=False, bands=0)
    # corner pouches on the cummerbund front corners, angled ~40 deg outward
    for s, cx, z0, z1, tgt in ((-1, -0.215, 1.104, 1.263, (pouch_c, flap_c)), (1, 0.205, 1.101, 1.256, (pouch_w, flap_w))):
        a = math.radians(40)
        p, x, n, z = frame_dir(cx, -0.205, (z0 + z1) / 2, s * math.sin(a), -math.cos(a), 0.060)
        m = pouch(tgt[0], tgt[1], trims, metal, p, x, n, z, 0.080, z1 - z0, 0.060, flap=0.26, bungee=False)
        if s < 0:  # light chem-light clip at the top inner corner (end of the coiled cable)
            hard.add(L.lathe([(0.0, 0.0), (0.006, 0.0), (0.006, 0.030), (0.0, 0.034)], 10)
                     .transform(m @ Matrix.Translation((0.030, 0.064, 0.060))))
        else:      # light shield-shaped piping on its face
            sh = [V((0.012 + 0.020 * math.cos(t), 0.0615, -0.010 + 0.03 * math.sin(t) - 0.015 * max(0.0, -math.sin(t))))
                  for t in lin(0, TAU, 24)]
            hard.add(tube([m @ q for q in sh], 0.0015, 5, closed=True))
    # side pouches (2 per side) and rear cummerbund pouches
    for s in (-1, 1):
        p, x, n, z = frame_dir(s * 0.2225, -0.145, 1.186, s, 0, 0.055)
        m = pouch(pouch_c if s < 0 else pouches, flap_c if s < 0 else flaps, trims, metal, p, x, n, z,
                  0.075, 0.152, 0.055, flap=0.20, bungee=False)
        sp = [V((0.012 * t * math.cos(t * 5.5), 0.056, 0.035 + 0.012 * t * math.sin(t * 5.5))) for t in lin(0.1, 1.6, 30)]
        hard.add(tube([m @ q for q in sp], 0.0014, 5))  # swirl ornament
        p, x, n, z = frame_dir(s * 0.2125, -0.085, 1.183, s, 0, 0.045)
        pouch(pouch_c, flap_c, trims, metal, p, x, n, z, 0.055, 0.145, 0.045, flap=0.20, bungee=False, tab=False)
        p, x, n, z = frame_dir(s * 0.180, 0.165, 1.1665, s * 0.707, 0.707, 0.055)
        pouch(pouch_w, flap_w, trims, metal, p, x, n, z, 0.080, 0.149, 0.055, flap=0.23, bungee=False)

    # ------------------------------------------------------------------ back: drag handle, central case
    bk = MD()
    p = V((0.005, back_y(0.005), 1.555))
    mbk = Matrix((V((1, 0, 0)), V((0, 1, 0)), V((0, 0, 1)))).transposed().to_4x4()
    mbk.translation = p
    bk.add(box(0.053, 0.025, 0.068).transform(mbk @ Matrix.Translation((0, 0.0125, 0))))
    hard.add(box(0.008, 0.003, 0.008).translate(p + V((0.0, 0.026, 0.024))))
    molle.add(sweep([p + V((0.03, 0.012, 0.0)), p + V((0.07, 0.008, -0.01))], rect_profile(0.020, 0.003), up=(0, 1, 0)))

    def case(u, v, i, j):
        x = lerp(-0.090, 0.070, u)
        zb = 1.330 - 0.015 * math.exp(-((x + 0.01) / 0.03) ** 2)
        z = lerp(zb, 1.530, v)
        bul = 0.050 * (1 - 0.35 * (2 * u - 1) ** 4) * (1 - 0.3 * (2 * v - 1) ** 4)
        return V((x, back_y(x) + bul, z))

    bk.add(grid(case, lin(0, 1, 16), lin(0, 1, 14), flip=True))
    border = [V((x, back_y(x) + 0.032, 1.338 - 0.015 * math.exp(-((x + 0.01) / 0.03) ** 2))) for x in lin(-0.088, 0.068, 20)]
    hard.add(sweep(border, rect_profile(0.020, 0.003), up=(0, 1, 0)))

    # ------------------------------------------------------------------ coiled PTT cable (right chest)
    cab = [V((-0.170, -0.205, 1.495)), V((-0.168, -0.212, 1.440))]
    for k, zc in enumerate((1.400, 1.345, 1.290)):
        for q in range(25):
            a = TAU * q / 24
            cab.append(V((-0.170 + 0.015 * math.cos(a), -0.214 - 0.010 * math.sin(a), zc + 0.020 - 0.040 * q / 24)))
    cab += [V((-0.200, -0.230, 1.268)), V((-0.222, -0.240, 1.262))]
    cable = MD()
    cable.add(tube(catmull_path(cab, 2), 0.003, 6))

    # ------------------------------------------------------------------ beaded antenna lead and the whip antenna
    beads = MD()
    run = catmull_path([V((0.130, -0.195, 1.290)), V((0.130, -0.197, 1.470)), V((0.150, -0.120, 1.565)),
                        V((0.160, 0.000, 1.598)), V((0.150, 0.110, 1.575)), V((0.120, 0.195, 1.520)),
                        V((0.115, 0.197, 1.120))], 10)
    for q in L.resample(run, int(L.path_length(run) / 0.011)):
        beads.add(uv_sphere(0.006, 10, 6).translate(q))
    molle.add(sweep(run, rect_profile(0.020, 0.002), up=lambda i, p: (p - V((0.0, 0.0, 1.35))).normalized()))
    ant = MD()
    base = V((0.190, 0.100, 1.540))
    ant.add(lathe([(0.0, 0.0), (0.014, 0.0), (0.014, 0.045), (0.016, 0.045), (0.016, 0.050), (0.0, 0.050)], 16)
            .translate(base))
    tip = V((0.221, 0.110, 1.775))
    ant.add(tube([base + V((0, 0, 0.05)), tip], 0.0035, 8, scale=lambda t: 1.0 - 0.3 * t))
    ant.add(lathe([(0.0, 0.0), (0.006, 0.0), (0.006, 0.020), (0.0, 0.020)], 12)
            .translate(base.lerp(tip, 0.62) + V((0, 0, -0.01))))
    ant.add(uv_sphere(0.004, 8, 5).translate(tip))

    # ------------------------------------------------------------------ objects
    ob = to_obj("PlateCarrier_Bags", bags, M["carrier"], coll, parent=root)
    mod_solidify(ob, T_PLATE, 1.0)
    mod_bevel(ob, 0.006, 2)
    ob = to_obj("PlateCarrier_Shoulder_Straps", straps, M["carrier"], coll, parent=root)
    mod_subsurf(ob, 1, 2)
    for name, bmd, fmd, mat in (("Pouches", pouches, flaps, "nylon_camo"), ("Pouches_Warm", pouch_w, flap_w, "camo_warm"),
                                ("Pouches_Cool", pouch_c, flap_c, "camo_cool")):
        ob = to_obj("Chest_" + name, bmd, M[mat], coll, parent=root)
        mod_bevel(ob, 0.006, 3)
        mod_subsurf(ob, 1, 1)
        ob = to_obj("Chest_" + name + "_Flaps", fmd, M[mat], coll, parent=root)
        mod_solidify(ob, 0.005, -1.0)
        mod_subsurf(ob, 1, 1)
    to_obj("PlateCarrier_Binding_Bands", trims, M["nylon_dark"], coll, parent=root)
    to_obj("PlateCarrier_MOLLE_Straps", molle, M["webbing"], coll, parent=root)
    ob = to_obj("PlateCarrier_Hardware_Piping", hard, M["plastic_light"], coll, parent=root)
    to_obj("PlateCarrier_Grommets", metal, M["metal_black"], coll, parent=root)
    ob = to_obj("Dive_Computer_Clip_Box", dc, M["polymer_gloss"], coll, parent=root)
    mod_bevel(ob, 0.004, 2)
    to_obj("Dive_Computer_Screen", screen, M["screen_dim"], coll, parent=root)
    ob = to_obj("Back_Case_Drag_Handle", bk, M["carrier"], coll, parent=root)
    mod_solidify(ob, 0.004, -1.0)
    to_obj("PTT_Coiled_Cable", cable, M["cable_grey"], coll, parent=root)
    to_obj("Antenna_Lead_Beads", beads, M["metal"], coll, parent=root)
    to_obj("Whip_Antenna", ant, M["polymer"], coll, parent=root)
