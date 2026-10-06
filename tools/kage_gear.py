"""Waist (obi, belts, red cords), skirts (kusazuri, apron, tattered skirt, red strips), swords, belt gear,
back banner, rope coil + grappling hook, kunai, and the props-showcase layout."""
import math

from mathutils import Matrix, Vector

from kage_armor import bow_knot, cui_pt, hang_cord, knot, tassel, both, deg, rivets_along
from kage_body import CUIRASS, HIPS, hip_normal, hip_pt, torso_normal, torso_pt
from kage_lib import (MD, RNG, TAU, V, box, catmull_path, circle_profile, clamp, fbm, frame_matrix, frames_along,
                      grid, interp_smooth, lathe, lerp, limb, lin, look_matrix, mod_solidify, mod_subsurf,
                      rect_profile, resample, smooth, sweep, to_obj, torus_md, tube, uv_sphere)
from kage_mats import M


def body_pt(theta, z, off=0.0):
    """Outer reference surface: cuirass table above 1.03, hips table below (blended)."""
    if z >= 1.06:
        return torso_pt(theta, z, off)
    if z <= 0.98:
        return hip_pt(theta, z, off)
    t = (z - 0.98) / 0.08
    return hip_pt(theta, z, off).lerp(torso_pt(theta, z, off), smooth(t))


def body_normal(theta, z):
    return torso_normal(theta, z) if z > 1.02 else hip_normal(theta, z)


def ring_path(z, off, n=128, fn=None):
    pts, ups = [], []
    for k in range(n):
        th = TAU * k / n
        zz = z if fn is None else fn(th)
        pts.append(body_pt(th, zz, off))
        ups.append(body_normal(th, zz))
    return pts, ups


# =============================================================================
# WAIST
# =============================================================================
def build_waist(coll, root):
    # obi sash (dark crimson-black) with horizontal wrinkles
    def obi(u, v, i, j):
        z = lerp(1.028, 1.122, v)
        off = 0.016 + 0.006 * math.sin(math.pi * v) + 0.0018 * math.sin(v * 34 + u * 3) + 0.002 * fbm(
            V((u * 3, v * 5, 0)))
        return body_pt(u, z, off)

    md = grid(obi, lin(0, TAU, 128), lin(0, 1, 14), closed_u=True)
    ob = to_obj("Obi_Sash", md, M["obi"], coll, parent=root)
    mod_subsurf(ob, 1, 2)

    # black leather belt + gold plaques
    belt = MD()
    pts, ups = ring_path(1.142, 0.027)
    belt.add(sweep(pts, rect_profile(0.034, 0.005, 2), up=lambda i, p: ups[i], closed_path=True))
    gold = MD()
    for a in range(-165, 166, 30):
        th = deg(a)
        p = body_pt(th, 1.142, 0.031)
        n = body_normal(th, 1.142)
        b = box(0.026, 0.022, 0.004)
        b.transform(look_matrix(p, n, (0, 0, 1)))
        gold.add(b)
        s = uv_sphere(0.004, 8, 5)
        s.transform(look_matrix(p + n * 0.003, n))
        gold.add(s)
    # brown leather upper belt with buckle
    brown = MD()
    pts, ups = ring_path(1.188, 0.021)
    brown.add(sweep(pts, rect_profile(0.030, 0.005, 2), up=lambda i, p: ups[i], closed_path=True))
    th = deg(20)
    p = body_pt(th, 1.188, 0.026)
    n = body_normal(th, 1.188)
    fr = [p + V((0, 0, 0.022)), p + V((0, 0, -0.022))]
    m = look_matrix(p, n, (0, 0, 1))
    frame_pts = [m @ V((x, y, 0.002)) for x, y in ((-0.016, -0.022), (0.016, -0.022), (0.016, 0.022), (-0.016, 0.022))]
    gold.add(sweep(frame_pts, rect_profile(0.004, 0.004, 1), up=lambda i, q: n, closed_path=True))
    gold.add(tube([m @ V((0, -0.022, 0.004)), m @ V((0, 0.022, 0.004))], 0.002, 6))
    brown.add(rivets_along(pts, 0.09, 0.003, normals=ups, offset=0.0025))

    # red rope belt: twisted double cord, big knot at front, hanging ends
    red = MD()
    for z, ph in ((1.082, 0.0), (1.064, 1.4)):
        pts, ups = ring_path(z, 0.030, 160)
        twist = []
        for k, (p, u) in enumerate(zip(pts, ups)):
            a = k / 160 * TAU * 30 + ph
            twist.append(p + u * 0.003 * math.cos(a) + V((0, 0, 0.003 * math.sin(a))))
        red.add(sweep(twist, circle_profile(0.0048, 6), up=lambda i, p: ups[i], closed_path=True))
    kth = deg(12)
    kp = body_pt(kth, 1.073, 0.040)
    kn = body_normal(kth, 1.073)
    red.add(knot(kp, kn, 0.013, 0.0055))
    red.add(knot(kp + V((0.012, 0, -0.012)) + kn * 0.004, kn, 0.009, 0.0045))
    for k, (dx, L) in enumerate(((-0.02, 0.15), (0.0, 0.20), (0.025, 0.12), (0.045, 0.17))):
        a = kp + kn * 0.006 + V((dx * 0.4, 0, -0.01))
        b = body_pt(kth + dx * 3, 1.073 - L, 0.075) + V((dx, 0, 0))
        mid = (a + b) / 2 + kn * 0.02
        red.add(tube(catmull_path([a, mid, b], 6), 0.004, 6))
        red.add(tassel(b, 0.05, 0.004, 0.009, 14))
    # extra short cords hanging from the belt at the front-left (as in the front-waist detail)
    for a, L in ((-22, 0.11), (34, 0.13)):
        th = deg(a)
        top = body_pt(th, 1.125, 0.034)
        bot = body_pt(th, 1.125 - L, 0.07)
        red.add(tube(catmull_path([top, (top + bot) / 2 + body_normal(th, 1.1) * 0.012, bot], 6), 0.0032, 6))
        red.add(knot(bot + V((0, 0, 0.012)), body_normal(th, 1.0), 0.006, 0.003))
        red.add(tassel(bot, 0.04, 0.0035, 0.007, 12))

    # hanging gold charms (chains of small ornaments) and an inro case at the front of the belt
    for a, L in ((-5, 0.17), (27, 0.12)):
        th = deg(a)
        top = body_pt(th, 1.12, 0.036)
        n = body_normal(th, 1.05)
        n = V((n.x, n.y, 0)).normalized()
        red.add(tube([top, top + V((0, 0, -0.03)) + n * 0.01], 0.0025, 6))
        z = top.z - 0.035
        for k, kind in enumerate(("disc", "bell", "bar", "disc")):
            c = V((top.x, top.y, z)) + n * (0.012 + 0.01 * k)
            if kind == "disc":
                d = lathe([(0.0, 0.003), (0.013, 0.002), (0.014, 0.0), (0.013, -0.002), (0.0, -0.003)], 16)
                d.transform(look_matrix(c, n))
                gold.add(d)
                z -= 0.032
            elif kind == "bell":
                b = lathe([(0.0, 0.012), (0.006, 0.010), (0.010, 0.0), (0.011, -0.010), (0.0, -0.010)], 16)
                b.translate(c)
                gold.add(b)
                z -= 0.030
            else:
                b = box(0.010, 0.006, 0.030)
                b.translate(c)
                gold.add(b)
                z -= 0.040
            if k < 3:
                red.add(tube([c + V((0, 0, -0.012)), c + V((0, 0, -0.02))], 0.0018, 6))
            if z < top.z - L:
                break
    th = deg(-20)
    top = body_pt(th, 1.12, 0.036)
    n = body_normal(th, 1.0)
    n = V((n.x, n.y, 0)).normalized()
    inro = box(0.05, 0.022, 0.065)
    ic = top + n * 0.03 + V((0, 0, -0.11))
    inro.transform(look_matrix(ic, V((0, 0, 1)), n))
    belt.add(inro)
    red.add(tube([top, ic + V((0, 0, 0.034))], 0.0022, 6))
    red.add(tassel(ic + V((0, 0, -0.034)), 0.035, 0.003, 0.006, 10))
    nk = uv_sphere(0.012, 12, 8)
    nk.translate(top + n * 0.012 + V((0, 0, 0.016)))
    gold.add(nk)

    for name, md, mat, sub in (("Belt_Black_Leather", belt, M["leather_dark"], 1),
                               ("Belt_Brown_Leather", brown, M["leather"], 1),
                               ("Belt_Gold_Fittings", gold, M["gold"], 0),
                               ("Belt_Red_Cords", red, M["cord_red"], 0)):
        ob = to_obj(name, md, mat, coll, parent=root)
        if sub:
            mod_subsurf(ob, 1, sub)


# =============================================================================
# SKIRTS
# =============================================================================
def tatter_lengths(n, base=1.0, var=0.25, cut_prob=0.25, seed=None):
    r = RNG
    out = []
    for k in range(n + 1):
        L = base - r.random() * var
        if r.random() < cut_prob:
            L -= r.uniform(0.05, 0.18)
        out.append(L)
    return out


def hanging_panel(th0, th1, z_top, z_bot_fn, off_fn, nu=24, nv=24, pleat=0.008, pleats=6, tatter=0.18,
                  tatter_var=0.35, seed=0, slits=0.25):
    """Cloth panel hanging around the hips from z_top down to z_bot_fn(theta) with a tattered hem.

    tatter: fraction of the drop that the ragged hem may shorten a column by.
    UV: u across (0..1), v bottom(0) -> top(1).
    """
    rng = RNG
    lens = []
    for k in range(nu + 1):
        L = 1.0 - rng.random() * tatter * tatter_var
        if rng.random() < slits:
            L -= rng.uniform(0.3, 1.0) * tatter
        lens.append(L)

    def fn(u, v, i, j):
        th = lerp(th0, th1, u)
        drop = z_top - z_bot_fn(th)
        k = (lens[i] - 0.7) / 0.3
        vv = v if v < 0.7 else 0.7 + (v - 0.7) * k
        z = z_top - drop * vv
        p = body_pt(th, z, off_fn(th, z, vv))
        n = body_normal(th, max(z, 0.25))
        n = V((n.x, n.y, 0)).normalized()
        p += n * (pleat * math.sin(u * pleats * TAU) * clamp(vv * 1.3) + 0.006 * fbm(p * 9 + V((seed, 0, 0))) +
                  0.0025 * fbm(p * 38 + V((0, seed, 0))))
        return p

    # a few long vertical tears from the hem upward
    tears = {rng.randrange(1, nu - 1): rng.uniform(0.15, 0.35) for _ in range(max(1, nu // 6))}

    def keep(i, j):
        if i in tears and j >= nv * (1 - tears[i]):
            return False
        return True

    return grid(fn, lin(0, 1, nu), lin(0, 1, nv), keep=keep, uv_fn=lambda u, v, i, j: (u, 1 - v))


def lamellar_panel(th_c, width_deg, z_top, rows, row_h, off0, flare, seed=0):
    """Kusazuri panel: rows of lacquered lames with gold edge + red lacing."""
    plates, gold, red = MD(), MD(), MD()
    pitch = row_h - 0.013
    hw = deg(width_deg) / 2
    for k in range(rows):
        zt = z_top - k * pitch
        zb = zt - row_h
        o_top = off0 + k * flare
        o_bot = off0 + (k + 1) * flare + 0.006
        wk = hw * (1 + 0.05 * k)

        def fn(u, v, i=0, j=0, zt=zt, zb=zb, o_top=o_top, o_bot=o_bot, wk=wk):
            th = th_c + lerp(-wk, wk, u)
            z = lerp(zb, zt, v)
            return body_pt(th, z, lerp(o_bot, o_top, v))

        plates.add(grid(fn, lin(0, 1, 16), lin(0, 1, 4)))
        edge = [fn(q / 16, 0.0) + body_normal(th_c + lerp(-wk, wk, q / 16), zb) * 0.003 for q in range(17)]
        gold.add(tube(edge, 0.0016, 6, rx=0.0026))
        for s in (0.0, 1.0):
            gold.add(tube([fn(s, q / 4) + body_normal(th_c, zb) * 0.003 for q in range(5)], 0.0022, 6))
        for q in range(5):
            u = (q + 0.5) / 5
            a = fn(u, 1.0) + body_normal(th_c, zt) * 0.004 + V((0, 0, 0.006))
            b = fn(u, 0.62) + body_normal(th_c, zt) * 0.005
            red.add(tube([a, b], 0.0024, 6, rx=0.0034))
    # suspension cords up to the obi
    for q in range(4):
        u = (q + 0.5) / 4
        th = th_c + lerp(-hw, hw, u)
        a = body_pt(th, z_top + 0.035, off0 + 0.002)
        b = body_pt(th, z_top - 0.01, off0 + 0.004)
        red.add(tube([a, b], 0.0026, 6))
    return plates, gold, red


def build_skirts(coll, root):
    cloth_skirt = MD()
    plates = MD()
    gold = MD()
    red = MD()
    red_cloth = MD()
    apron = MD()

    # --- long tattered skirt panels around the sides & back ------------------
    def zb_side(th):
        b = 0.5 - 0.5 * math.cos(th)  # 0 front, 1 back
        return lerp(0.40, 0.29, smooth(b * 1.4))

    def off_skirt(th, z, v):
        return 0.018 + 0.03 * v ** 1.5

    panels = [(118, 162), (152, 200)]
    for side in (1, -1):
        for k, (a0, a1) in enumerate(panels):
            if side < 0 and a0 >= 160:
                continue
            th0, th1 = deg(a0) * side, deg(a1) * side
            if side < 0:
                th0, th1 = th1, th0
            cloth_skirt.add(hanging_panel(th0, th1, 1.05, zb_side, off_skirt, 14, 22, 0.010, 3, 0.14, 0.6,
                                          seed=k * 3 + (side > 0)))
    # --- front apron (maedare) ------------------------------------------------
    lens = tatter_lengths(14, 1.0, 0.10, 0.3)

    def apron_fn(u, v, i, j):
        x = lerp(-0.068, 0.052, u)
        L = lerp(1.0, lens[i], smooth((v - 0.75) / 0.25))
        z = lerp(1.065, 0.515, v * L if v > 0.75 else v)
        if v > 0.75:
            z = 1.065 - (1.065 - 0.515) * (0.75 + (v - 0.75) * L)
        th = math.atan2(x, 0.17)
        p = body_pt(th, max(z, 0.9), 0.034)
        y = p.y - 0.03 * smooth((1.0 - z) / 0.5)
        return V((x, y + 0.004 * math.sin(u * 9 + v * 3), z))

    apron.add(grid(apron_fn, lin(0, 1, 14), lin(0, 1, 22), uv_fn=lambda u, v, i, j: (u, 1 - v)))

    # --- front cloth panels: ornate gold-printed panel (left) and dark panels (right)
    gold_panel = MD()
    gold_panel.add(hanging_panel(deg(13), deg(41), 1.050, lambda th: 0.46, lambda th, z, v: 0.036 + 0.05 * v,
                                 10, 22, 0.005, 2, 0.12, 0.7, seed=5, slits=0.3))
    cloth_skirt.add(hanging_panel(deg(-40), deg(-16), 1.050, lambda th: 0.53, lambda th, z, v: 0.036 + 0.05 * v,
                                  10, 22, 0.005, 2, 0.14, 0.7, seed=6, slits=0.3))

    # --- kusazuri lamellar panels -------------------------------------------
    for th_c, wdeg, rows, rh, z_top in ((62, 40, 6, 0.068, 1.005), (-62, 40, 6, 0.068, 1.000),
                                         (100, 40, 7, 0.068, 1.000), (-100, 40, 7, 0.068, 1.000),
                                         (136, 38, 6, 0.068, 0.995), (-136, 38, 6, 0.068, 0.995)):
        p, g, r = lamellar_panel(deg(th_c), wdeg, z_top, rows, rh, 0.046, 0.0045)
        plates.add(p)
        gold.add(g)
        red.add(r)

    # --- red cloth strips (right side + back) --------------------------------
    for th_c, w, zb in ((-34, 6, 0.55), (-76, 7, 0.52), (-150, 5, 0.42)):
        def zbf(th, zb=zb):
            return zb

        red_cloth.add(hanging_panel(deg(th_c - w / 2), deg(th_c + w / 2), 1.045, zbf,
                                    lambda th, z, v: 0.058 + 0.05 * v, 4, 18, 0.0, 1, 0.10, 0.8, seed=th_c,
                                    slits=0.4))

    for name, md, mat, sub, solid in (("Skirt_Tattered", cloth_skirt, M["cloth_skirt"], 1, 0.003),
                                      ("Apron_Maedare", apron, M["cloth_apron"], 1, 0.003),
                                      ("Front_Panel_Gold_Print", gold_panel, M["cloth_panel"], 1, 0.003),
                                      ("Kusazuri_Plates", plates, M["lacquer_lamellar"], 1, 0.004),
                                      ("Kusazuri_Gold", gold, M["bronze_rib"], 0, 0),
                                      ("Kusazuri_Lacing", red, M["cord_red"], 0, 0),
                                      ("Red_Cloth_Strips", red_cloth, M["cloth_red"], 1, 0.002)):
        ob = to_obj(name, md, mat, coll, parent=root)
        if solid:
            mod_solidify(ob, solid, 0.0)
        if sub:
            mod_subsurf(ob, 1, sub)


# =============================================================================
# SWORDS
# =============================================================================
def build_sword(tsuka_len=0.27, saya_len=0.76, sori=0.018, wrap="tsuka", drawn=False):
    """Sheathed sword in local space: +X toward the tip, origin at the tsuba, +Z edge side."""
    parts = {k: MD() for k in ("saya", "gold", "iron", "tsuka", "tsuka_gold", "cord", "steel")}

    def curve(x):
        return V((x, 0.0, sori * (max(x, 0) / saya_len) ** 2))

    # saya
    n = 40
    path = [curve(lerp(0.010, saya_len, k / n)) for k in range(n + 1)]
    prof = [(0.0085 * math.cos(a), 0.0135 * math.sin(a)) for a in lin(0, TAU, 16)]
    parts["saya"].add(sweep(path, prof, up=(0, 0, 1), scale=lambda t: 1.0 - 0.18 * t, cap1=True))
    # fittings
    def band(x0, x1, grow=0.0012, mat="gold"):
        p = [curve(lerp(x0, x1, k / 3)) for k in range(4)]
        t0 = (x0 - 0.010) / saya_len
        s = 1.0 - 0.18 * clamp(t0)
        pr = [((0.0085 * s + grow) * math.cos(a), (0.0135 * s + grow) * math.sin(a)) for a in lin(0, TAU, 16)]
        parts[mat].add(sweep(p, pr, up=(0, 0, 1), cap0=True, cap1=True))

    band(0.008, 0.026)                     # koiguchi
    band(0.20, 0.215, 0.0010)              # decorative bands
    band(saya_len * 0.42, saya_len * 0.42 + 0.06, 0.0009)   # ornate sleeve
    band(saya_len * 0.62, saya_len * 0.62 + 0.012, 0.0010)
    band(saya_len - 0.045, saya_len + 0.002, 0.0016)        # kojiri
    end = uv_sphere(0.0085, 12, 8, rx=0.0085 * 0.84, ry=0.0085 * 0.84 * 1.0, rz=0.0135 * 0.84)
    end.translate(curve(saya_len + 0.002))
    parts["gold"].add(end)
    # kurikata knob (side, -Y) + sageo cord
    kk = box(0.022, 0.010, 0.010)
    kk.translate(curve(0.11) + V((0, -0.011, -0.004)))
    parts["saya"].add(kk)
    knot_pt = curve(0.11) + V((0, -0.018, -0.004))
    parts["cord"].add(torus_md(0.006, 0.0025, 12, 6).transform(look_matrix(knot_pt, (0, -1, 0))))
    sageo = catmull_path([knot_pt, knot_pt + V((-0.03, -0.02, -0.03)), knot_pt + V((-0.06, -0.015, -0.05)),
                          knot_pt + V((-0.05, -0.01, -0.09)), knot_pt + V((0.02, -0.012, -0.08)),
                          knot_pt + V((0.06, -0.012, -0.05))], 6)
    parts["cord"].add(tube(sageo, 0.003, 6, rx=0.0045))
    # tsuba (guard)
    tsuba = lathe([(0.0, -0.003), (0.040, -0.003), (0.042, -0.0015), (0.042, 0.0015), (0.040, 0.003), (0.0, 0.003)], 40)
    tsuba.v = [V((p.x, p.y * 0.92, p.z)) for p in tsuba.v]
    tsuba.transform(Matrix.Rotation(math.pi / 2, 4, "Y"))
    parts["iron"].add(tsuba)
    rim = torus_md(0.0405, 0.0025, 40, 6)
    rim.v = [V((p.x, p.y * 0.92, p.z)) for p in rim.v]
    rim.transform(Matrix.Rotation(math.pi / 2, 4, "Y"))
    parts["gold"].add(rim)
    for s in (-1, 1):
        sep = lathe([(0.0, -0.001), (0.019, -0.001), (0.019, 0.001), (0.0, 0.001)], 24)
        sep.v = [V((p.x * 0.75, p.y, p.z)) for p in sep.v]
        sep.transform(Matrix.Translation((0.0045 * s, 0, 0)) @ Matrix.Rotation(math.pi / 2, 4, "Y"))
        parts["gold"].add(sep)
    # tsuka (handle)
    hp = [V((lerp(-0.006, -tsuka_len + 0.02, k / 24), 0, 0.004 * math.sin(math.pi * k / 24) * 0)) for k in range(25)]
    hprof = [(0.0125 * math.cos(a), 0.0158 * math.sin(a)) for a in lin(0, TAU, 20)]
    parts[wrap].add(sweep(hp, hprof, up=(0, 0, 1), scale=lambda t: 1.0 - 0.05 * math.sin(math.pi * t) + 0.02 * t))
    # fuchi & kashira
    fp = [V((-0.006, 0, 0)), V((-0.020, 0, 0))]
    parts["gold"].add(sweep(fp, [(0.0136 * math.cos(a), 0.0170 * math.sin(a)) for a in lin(0, TAU, 20)], up=(0, 0, 1),
                            cap0=True, cap1=False))
    kp = [V((-tsuka_len + 0.024, 0, 0)), V((-tsuka_len + 0.004, 0, 0))]
    parts["gold"].add(sweep(kp, [(0.0138 * math.cos(a), 0.0172 * math.sin(a)) for a in lin(0, TAU, 20)], up=(0, 0, 1),
                            scale=lambda t: 1.0 - 0.1 * t, cap0=False, cap1=True))
    kc = uv_sphere(1.0, 16, 8)
    kc.v = [V((-tsuka_len + 0.004 - abs(p.x) * 0.006 if p.x < 0 else -tsuka_len + 0.004 - 0.0, p.y * 0.0124, p.z * 0.0155))
            for p in kc.v]
    parts["gold"].add(kc)
    # menuki ornaments
    for s in (-1, 1):
        mk = uv_sphere(1.0, 10, 6)
        mk.v = [V((p.x * 0.014, p.y * 0.003, p.z * 0.005)) + V((-tsuka_len * 0.55, 0.0125 * s, 0.0)) for p in mk.v]
        parts["gold"].add(mk)
    return parts


def place_parts(parts, m, coll, root, prefix, wrap="tsuka"):
    mats = {"saya": M["lacquer_saya"], "gold": M["gold"], "iron": M["iron"], "tsuka": M[wrap] if wrap in M else M["tsuka"],
            "tsuka_gold": M["tsuka_gold"], "cord": M["cord_red"], "steel": M["steel"]}
    for k, md in parts.items():
        if not md.v:
            continue
        ob = to_obj(f"{prefix}_{k.capitalize()}", md.copy().transform(m), mats[k], coll, parent=root)
        if k in ("saya", "tsuka"):
            mod_subsurf(ob, 1, 2)


def build_swords(coll, root):
    import kage_weapons as W
    # Katana: through the obi on the left hip, hilt forward/inward, scabbard down & back
    kat = W.sword_parts(0.27, 0.76, 0.030)
    s = V((0.45, 0.78, -0.36)).normalized()
    T = V((0.060, -0.218, 1.148))
    W.place_sword(kat, frame_matrix(T, s, (0, 0, 1)), coll, root, "Katana")
    # Wakizashi: right hip
    wak = W.sword_parts(0.19, 0.48, 0.012, wrap="tsuka_gold")
    sw = V((-0.24, 0.95, -0.14)).normalized()
    Tw = V((-0.200, -0.175, 1.120))
    W.place_sword(wak, frame_matrix(Tw, sw, (0, 0, 1)), coll, root, "Wakizashi")


# =============================================================================
# GEAR: gourds, smoke bombs, pouches, powder flask, kunai holster
# =============================================================================
def gourd_md(scale=1.0):
    prof = []
    for k in range(41):
        z = 0.16 * k / 40
        r1 = math.sqrt(max(0, 0.048 ** 2 - (z - 0.047) ** 2))
        r2 = math.sqrt(max(0, 0.031 ** 2 - (z - 0.115) ** 2))
        r = max(r1, r2, 0.019 if 0.08 < z < 0.10 else 0)
        # smooth waist
        r = max(r, 0.020 * math.exp(-((z - 0.090) / 0.02) ** 2))
        if z > 0.135:
            r = max(r, 0.011)
        prof.append((r * scale, z * scale))
    prof[0] = (0.0, 0.0)
    prof.append((0.0, 0.16 * scale))
    return lathe(prof, 28)


def place_gourd(theta, z_bot, scale, out, coll_mds, tilt=0.0):
    p = body_pt(theta, z_bot, 0.0)
    n = body_normal(theta, max(z_bot, 0.3))
    n = V((n.x, n.y, 0)).normalized()
    base = body_pt(theta, z_bot + 0.08 * scale, out)
    g = gourd_md(scale)
    m = Matrix.Translation(base) @ Matrix.Rotation(tilt, 4, n.cross(V((0, 0, 1))).normalized())
    coll_mds["gourd"].add(g.copy().transform(m))
    # stopper + cap
    st = lathe([(0.0, 0.0), (0.012, 0.0), (0.013, 0.012), (0.009, 0.02), (0.0, 0.021)], 16)
    st.transform(m @ Matrix.Translation((0, 0, 0.158 * scale)))
    coll_mds["gold"].add(st)
    # cord around the waist of the gourd and up to the belt
    w = m @ V((0, 0, 0.09 * scale))
    ring = [m @ V((0.022 * scale * math.sin(a), -0.022 * scale * math.cos(a), 0.09 * scale)) for a in lin(0, TAU, 24)[:-1]]
    coll_mds["cord"].add(sweep(ring, circle_profile(0.003, 6), closed_path=True, up=(0, 0, 1)))
    top = body_pt(theta, 1.085, 0.034)
    coll_mds["cord"].add(tube(catmull_path([top, (top + w) / 2 + n * 0.015, w + n * 0.02], 6), 0.003, 6))


def smoke_bomb(c, r, coll_mds):
    s = uv_sphere(r, 28, 18)
    s.translate(c)
    coll_mds["bomb"].add(s)
    # profile from bottom to top so the kanji texture is upright (image v=0 is the bottom row)
    d = lathe([(r * 1.012 * math.sin(math.pi * k / 18), -r * 1.012 * math.cos(math.pi * k / 18)) for k in range(19)], 32)
    # rotate so the texture seam is at the back
    d.translate(c)
    coll_mds["bomb_decal"].add(d)
    band = torus_md(r * 0.55, 0.0025, 24, 6)
    band.translate(c + V((0, 0, r * 0.83)))
    coll_mds["gold"].add(band)
    neck = lathe([(0.0, 0.0), (r * 0.30, 0.0), (r * 0.26, r * 0.25), (r * 0.30, r * 0.33), (0.0, r * 0.34)], 16)
    neck.translate(c + V((0, 0, r * 0.88)))
    coll_mds["gold"].add(neck)
    loop = torus_md(r * 0.18, 0.0022, 16, 6)
    loop.transform(look_matrix(c + V((0, 0, r * 1.38)), (0, 1, 0)))
    coll_mds["cord"].add(loop)


def pouch_md(w=0.075, h=0.085, d=0.036):
    body, flap, metal = MD(), MD(), MD()
    b = box(w, d, h)
    body.add(b)

    def flap_fn(u, v, i, j):
        x = lerp(-w / 2 - 0.003, w / 2 + 0.003, u)
        # over the top then down the front
        if v < 0.35:
            t = v / 0.35
            y = lerp(d / 2 + 0.004, -d / 2 - 0.004, t)
            z = h / 2 + 0.004 + 0.006 * math.sin(math.pi * t)
        else:
            t = (v - 0.35) / 0.65
            y = -d / 2 - 0.004 - 0.002 * math.sin(math.pi * t)
            z = h / 2 + 0.004 - t * h * 0.62
            cr = 0.018
            ex = abs(x) - (w / 2 - cr)
            if ex > 0 and t > 0.7:
                z += (1 - math.sqrt(max(0, 1 - (ex / cr) ** 2))) * 0.0 + ex * (t - 0.7) * 2.0
        return V((x, y, z))

    flap.add(grid(flap_fn, lin(0, 1, 10), lin(0, 1, 12)))
    stud = uv_sphere(0.006, 10, 6)
    stud.v = [V((p.x, p.y * 0.6, p.z)) for p in stud.v]
    stud.translate((0, -d / 2 - 0.008, h / 2 - h * 0.55))
    metal.add(stud)
    strap = box(0.012, 0.004, 0.03)
    strap.translate((0, -d / 2 - 0.006, h / 2 - h * 0.5))
    flap.add(strap)
    return body, flap, metal


def place_pouch(theta, z_top, out, mds, scale=1.0, tilt=0.0):
    n = body_normal(theta, z_top - 0.04)
    n = V((n.x, n.y, 0)).normalized()
    p = body_pt(theta, z_top - 0.045 * scale, out)
    m = look_matrix(p, V((0, 0, 1)), -n) @ Matrix.Rotation(0, 4, "Z")
    # local: -Y faces outward
    x = V((0, 0, 1)).cross(-n).normalized()
    y = -n
    z = V((0, 0, 1))
    mm = Matrix((x, y, z)).transposed().to_4x4()
    mm = Matrix.Translation(p) @ Matrix.Rotation(tilt, 4, n) @ mm @ Matrix.Scale(scale, 4)
    body, flap, metal = pouch_md()
    mds["pouch"].add(body.transform(mm))
    mds["pouch_flap"].add(flap.transform(mm))
    mds["gold"].add(metal.transform(mm))
    top = body_pt(theta, 1.15, 0.03)
    mds["leather_dark"].add(tube([mm @ V((-0.02, 0.0, 0.045)), top + V((0, 0, -0.01))], 0.004, 6, rx=0.008))


POWDER_BODY = []


def powder_flask_md():
    md, metal, cord = MD(), MD(), MD()
    body = MD()
    prof = [(0.0, 0.0), (0.012, 0.0), (0.018, 0.006), (0.034, 0.028), (0.040, 0.052), (0.036, 0.078),
            (0.022, 0.096), (0.010, 0.104), (0.009, 0.118), (0.013, 0.122), (0.007, 0.132), (0.004, 0.146),
            (0.0, 0.150)]
    body.add(lathe(prof, 32))
    # front medallion
    med = lathe([(0.0, 0.002), (0.012, 0.0015), (0.013, 0.0), (0.0, 0.0)], 24)
    med.transform(look_matrix(V((0, -0.039, 0.052)), (0, -1, 0)))
    metal.add(med)
    # bottom tassel
    md.add(tassel(V((0, 0, 0.0)), 0.045, 0.006, 0.014, 16))
    cord.add(torus_md(0.009, 0.002, 12, 6).transform(look_matrix(V((0, 0, 0.158)), (0, 1, 0))))
    POWDER_BODY.append(body)
    return md, metal, cord


def kunai_md(L=0.20):
    """Kunai along -Z (blade down), ring pommel at the top."""
    blade, grip, ring = MD(), MD(), MD()
    bl = 0.105

    def bfn(u, v, i, j):
        # diamond cross-section leaf blade
        t = v
        w = 0.024 * math.sin(math.pi * clamp(t * 1.02) ** 0.62) * (1 - t) ** 0.35 + 0.004 * (1 - t)
        th = 0.0026 * (1 - t) + 0.0004
        a = u * TAU
        x = w * math.copysign(abs(math.cos(a)) ** 1.0, math.cos(a))
        y = th * math.copysign(abs(math.sin(a)) ** 1.0, math.sin(a))
        return V((x, y, -t * bl))

    blade.add(grid(bfn, lin(0, 1, 4), lin(0, 1, 16), closed_u=True))
    # central fuller ridge line
    blade.add(tube([V((0, 0.0028, -0.004)), V((0, 0.0012, -bl * 0.85))], 0.0007, 4))
    blade.add(tube([V((0, -0.0028, -0.004)), V((0, -0.0012, -bl * 0.85))], 0.0007, 4))
    grip.add(tube([V((0, 0, 0.0)), V((0, 0, 0.075))], 0.0062, 8, cap0=True, cap1=True))
    # wrap ridges
    for k in range(9):
        z = 0.006 + k * 0.0075
        t = torus_md(0.0066, 0.0016, 12, 4)
        t.translate((0, 0, z))
        grip.add(t)
    rg = torus_md(0.014, 0.0028, 20, 6)
    rg.transform(look_matrix(V((0, 0, 0.092)), (0, 1, 0)))
    ring.add(rg)
    return blade, grip, ring


def grappling_hook_md():
    iron = MD()
    iron.add(tube([V((0, 0, 0)), V((0, 0, 0.12))], 0.0065, 8))
    iron.add(torus_md(0.017, 0.0035, 20, 6).transform(look_matrix(V((0, 0, 0.135)), (0, 1, 0))))
    for k in range(4):
        a = TAU * k / 4 + 0.4
        d = V((math.sin(a), -math.cos(a), 0))
        pts = [V((0, 0, 0.01)), d * 0.025 + V((0, 0, -0.012)), d * 0.055 + V((0, 0, 0.0)),
               d * 0.064 + V((0, 0, 0.03)), d * 0.052 + V((0, 0, 0.052))]
        iron.add(tube(catmull_path(pts, 5), 0.0055, 6, scale=lambda t: 1.0 - 0.8 * t))
    return iron


def rope_coil_md(height=0.27, width=0.11, loops=7, r=0.0062):
    """Hanging hank of rope: loops gathered at the top, fanning out below."""
    md = MD()
    for k in range(loops):
        f = (k + 0.5) / loops - 0.5
        w = width * RNG.uniform(0.75, 1.05)
        h = height * RNG.uniform(0.82, 1.0)
        yaw = f * 1.1 + RNG.uniform(-0.15, 0.15)
        ox = f * width * 0.55
        pts = []
        for q in range(48):
            a = TAU * q / 48
            # teardrop loop: pinched at the top (a = 0), round at the bottom
            pinch = (1 - math.cos(a)) / 2
            x = math.sin(a) * w / 2 * (0.25 + 0.75 * pinch)
            z = -h * pinch
            y = 0.006 * math.sin(a * 3 + k)
            p = V((x, y, z))
            p = Matrix.Rotation(yaw, 3, "Z") @ p
            pts.append(p + V((ox * pinch, 0.012 * f, 0)))
        md.add(sweep(pts, circle_profile(r, 6), closed_path=True, up=(0, 1, 0)))
    # binding wraps at the top
    for q in range(5):
        t = torus_md(0.022, r * 0.9, 16, 6)
        t.transform(look_matrix(V((0, 0, -0.010 - q * 0.0085)), (0, 0, 1)))
        md.add(t)
    # hanging free end
    md.add(tube(catmull_path([V((0.01, 0, -0.03)), V((0.03, -0.01, -0.12)), V((0.02, -0.012, -0.22)),
                              V((0.035, -0.01, -0.30))], 6), r, 6))
    return md


def build_gear(coll, root):
    mds = {k: MD() for k in ("gourd", "gold", "cord", "bomb", "bomb_decal", "pouch", "pouch_flap", "leather_dark",
                             "flask", "flask_tassel", "flask_body", "steel", "grip", "iron")}
    # gourds (hyotan)
    place_gourd(deg(14), 0.80, 0.80, 0.085, mds, 0.05)
    place_gourd(deg(70), 0.80, 0.95, 0.090, mds, -0.06)
    place_gourd(deg(108), 0.80, 0.95, 0.090, mds, 0.08)
    place_gourd(deg(175), 0.735, 1.18, 0.105, mds, 0.0)
    # smoke bombs cluster (front right)
    for th, z, r in ((-47, 0.905, 0.047), (-72, 0.975, 0.034), (-86, 0.945, 0.032)):
        c = body_pt(deg(th), z, 0.105 + r)
        smoke_bomb(c, r, mds)
        top = body_pt(deg(th), 1.085, 0.034)
        mds["cord"].add(tube(catmull_path([top, (top + c) / 2 + V((0, -0.01, 0.01)), c + V((0, 0, r * 1.25))], 6),
                             0.0028, 6))
    # pouches
    for th, zt, sc, tilt in ((-40, 1.050, 1.0, 0.04), (-58, 1.000, 0.95, -0.05), (128, 1.045, 1.05, 0.0),
                             (-138, 1.045, 1.05, 0.0), (52, 1.03, 0.8, 0.0), (-104, 1.03, 0.85, 0.0)):
        place_pouch(deg(th), zt, 0.075, mds, sc, tilt)
    # powder flask (right side)
    fl, metal, cord = powder_flask_md()
    p = body_pt(deg(-118), 0.86, 0.12)
    m = Matrix.Translation(p)
    mds["flask_tassel"].add(fl.transform(m))
    mds["flask_body"].add(POWDER_BODY.pop().transform(m))
    mds["gold"].add(metal.transform(m))
    mds["cord"].add(cord.transform(m))
    top = body_pt(deg(-118), 1.085, 0.034)
    mds["cord"].add(tube(catmull_path([top, (top + p) / 2 + V((0, 0, 0.01)), p + V((0, 0, 0.165))], 5), 0.0028, 6))
    # kunai holster (back right) with three kunai
    th = deg(-122)
    n = body_normal(th, 1.0)
    n = V((n.x, n.y, 0)).normalized()
    hp = body_pt(th, 0.985, 0.085)
    x = V((0, 0, 1)).cross(-n).normalized()
    mm = Matrix((x, -n, V((0, 0, 1)))).transposed().to_4x4()
    mm.translation = hp
    hol = box(0.07, 0.03, 0.09)
    mds["pouch"].add(hol.transform(mm))
    for k in (-1, 0, 1):
        b, g, r = kunai_md()
        km = mm @ Matrix.Translation((k * 0.02, 0.0, 0.02)) @ Matrix.Rotation(k * 0.12, 4, "Y")
        mds["steel"].add(b.transform(km))
        mds["grip"].add(g.transform(km))
        mds["iron"].add(r.transform(km))

    mats = {"gourd": M["gourd"], "gold": M["gold"], "cord": M["cord_red"], "bomb": M["iron"],
            "bomb_decal": M["decal_smoke"], "pouch": M["leather_tooled"], "pouch_flap": M["leather_tooled"],
            "leather_dark": M["leather_dark"], "flask_tassel": M["cord_red"], "flask_body": M["bronze_engraved"],
            "steel": M["steel"],
            "grip": M["cord_dark"], "iron": M["iron"]}
    names = {"gourd": "Gourds_Hyotan", "gold": "Gear_Gold_Fittings", "cord": "Gear_Red_Cords",
             "bomb": "Smoke_Bombs", "bomb_decal": "Smoke_Bombs_Kanji", "pouch": "Utility_Pouches",
             "pouch_flap": "Utility_Pouch_Flaps", "leather_dark": "Pouch_Straps", "flask_tassel": "Powder_Flask_Tassel",
             "flask_body": "Powder_Flask_Body",
             "steel": "Kunai_Blades", "grip": "Kunai_Grips", "iron": "Kunai_Rings"}
    for k, md in mds.items():
        if not md.v:
            continue
        ob = to_obj(names.get(k, k), md, mats[k], coll, parent=root, smooth=(k != "steel"))
        if k in ("gourd", "bomb"):
            mod_subsurf(ob, 1, 2)
        if k == "pouch":
            from kage_lib import mod_bevel
            mod_bevel(ob, 0.006, 3)
        if k == "pouch_flap":
            mod_solidify(ob, 0.003, -1.0)
            mod_subsurf(ob, 1, 2)


# =============================================================================
# BACK: banner cloth, rope coil + grappling hook
# =============================================================================
def build_back(coll, root):
    xc = -0.075
    lens = tatter_lengths(16, 1.0, 0.12, 0.35)

    def banner(u, v, i, j):
        # v: 0 top -> 1 bottom
        w = lerp(0.150, 0.180, v)
        x = xc + lerp(-w / 2, w / 2, u)
        z_top, z_bot = 1.565, 0.755
        L = lens[i]
        vv = v if v < 0.8 else 0.8 + (v - 0.8) * (1 + (L - 1) * 4)
        z = lerp(z_top, z_bot, vv)
        th = math.pi - math.atan2(x, 0.15)
        y1 = torso_pt(th, clamp(z, 1.0, 1.5), 0.022).y if z > 1.0 else 0
        if z > 1.33:
            # over the shawl / cowl at the back of the neck
            y = torso_pt(th, z, 0.034 + 0.040 * smooth((z - 1.33) / 0.10)).y
        elif z > 1.0:
            # over the back strap, belts and gear
            belt = math.exp(-((z - 1.12) / 0.09) ** 2)
            y = torso_pt(th, z, 0.036 + 0.030 * belt).y
        else:
            yb = hip_pt(th, 1.0, 0.070).y
            y = yb + (1.0 - z) * 0.10
        y += 0.004 * math.sin(u * 7 + v * 5) + 0.006 * fbm(V((x * 12, z * 12, 0)))
        return V((x, y, z))

    md = grid(banner, lin(0, 1, 16), lin(0, 1, 40), uv_fn=lambda u, v, i, j: (u, 1 - v))
    ob = to_obj("Back_Banner_Sashimono_Cloth", md, M["cloth_banner"], coll, parent=root)
    mod_solidify(ob, 0.003, 0.0)
    mod_subsurf(ob, 1, 2)
    # rope coil (left back) + grappling hook tucked beside it
    th = deg(150)
    n = body_normal(th, 0.95)
    n = V((n.x, n.y, 0)).normalized()
    p = body_pt(th, 0.895, 0.075)
    x = V((0, 0, 1)).cross(-n).normalized()
    mm = Matrix((x, -n, V((0, 0, 1)))).transposed().to_4x4()
    mm.translation = p
    rope = rope_coil_md(0.30, 0.13, 10, 0.0070)
    ob = to_obj("Rope_Coil", rope.transform(mm), M["rope"], coll, parent=root)
    hook = grappling_hook_md()
    hm = Matrix.Translation(body_pt(deg(118), 0.98, 0.09)) @ Matrix.Rotation(math.pi, 4, "X") @ Matrix.Scale(0.9, 4)
    to_obj("Grappling_Hook", hook.transform(hm), M["iron"], coll, parent=root)
    # cord tying the coil to the belt
    top = body_pt(th, 1.085, 0.034)
    to_obj("Rope_Tie", tube([top, mm @ V((0, 0, 0.0))], 0.004, 6), M["cord_red"], coll, parent=root)


# =============================================================================
# PROPS SHOWCASE (laid out like the item row of the concept sheet)
# =============================================================================
def build_showcase_items(coll, origin):
    o = V(origin)
    mds = {k: MD() for k in ("gourd", "gold", "cord", "bomb", "bomb_decal", "pouch", "pouch_flap", "leather_dark",
                             "flask_tassel", "flask_body", "steel", "grip", "iron", "rope")}
    # smoke bombs x3
    for k in range(3):
        smoke_bomb(o + V((-1.15 + k * 0.11, 0.0, 0.05)), 0.05, mds)
    # powder flask
    fl, metal, cord = powder_flask_md()
    m = Matrix.Translation(o + V((-0.78, 0, 0.01)))
    mds["flask_tassel"].add(fl.transform(m))
    mds["flask_body"].add(POWDER_BODY.pop().transform(m))
    mds["gold"].add(metal.transform(m))
    mds["cord"].add(cord.transform(m))
    # pouch
    body, flap, metal = pouch_md()
    pm = Matrix.Translation(o + V((-0.55, 0, 0.045))) @ Matrix.Scale(1.4, 4)
    mds["pouch"].add(body.transform(pm))
    mds["pouch_flap"].add(flap.transform(pm))
    mds["gold"].add(metal.transform(pm))
    # three kunai standing
    for k in range(3):
        b, g, r = kunai_md()
        km = Matrix.Translation(o + V((-0.30 + k * 0.05, 0, 0.11))) @ Matrix.Rotation(0.0, 4, "Y")
        mds["steel"].add(b.transform(km))
        mds["grip"].add(g.transform(km))
        mds["iron"].add(r.transform(km))
    # grappling hook + rope coil lying flat
    hook = grappling_hook_md()
    mds["iron"].add(hook.transform(Matrix.Translation(o + V((-0.05, 0, 0.08))) @ Matrix.Rotation(0.9, 4, "Y")))
    coil = MD()
    for k in range(9):
        pts = []
        for q in range(48):
            a = TAU * q / 48
            rr = 0.07 + k * 0.004
            pts.append(o + V((0.12 + rr * math.cos(a), rr * math.sin(a) * 0.9, 0.007 + 0.011 * (k % 3))))
        coil.add(sweep(pts, circle_profile(0.006, 6), closed_path=True, up=(0, 0, 1)))
    mds["rope"].add(coil)
    mats = {"gourd": M["gourd"], "gold": M["gold"], "cord": M["cord_red"], "bomb": M["iron"],
            "bomb_decal": M["decal_smoke"], "pouch": M["leather_tooled"], "pouch_flap": M["leather_tooled"],
            "leather_dark": M["leather_dark"], "flask_tassel": M["cord_red"], "flask_body": M["bronze_engraved"],
            "steel": M["steel"],
            "grip": M["cord_dark"], "iron": M["iron"], "rope": M["rope"]}
    for k, md in mds.items():
        if not md.v:
            continue
        ob = to_obj("Showcase_" + k, md, mats[k], coll, smooth=(k != "steel"))
        if k == "bomb":
            mod_subsurf(ob, 1, 2)
        if k == "pouch":
            from kage_lib import mod_bevel
            mod_bevel(ob, 0.006, 3)
        if k == "pouch_flap":
            mod_solidify(ob, 0.003, -1.0)
            mod_subsurf(ob, 1, 2)
    # weapons: sword stand with sheathed katana & wakizashi, a drawn katana and the matchlock pistol
    import kage_weapons as W
    stand = W.sword_stand_md()
    stand.translate(o + V((0.78, 0.20, 0.0)))
    st = to_obj("Showcase_Sword_Stand", stand, M["lacquer"], coll)
    from kage_lib import mod_bevel
    mod_bevel(st, 0.004, 2)
    hgt = 0.42
    kat = W.sword_parts(0.27, 0.76, 0.020)
    W.place_sword(kat, frame_matrix(o + V((0.50, 0.17, hgt * 0.95 + 0.06)), (1, 0, 0), (0, 0, 1)), coll, None,
                  "Showcase_Katana_Sheathed")
    wak = W.sword_parts(0.19, 0.48, 0.012, wrap="tsuka_gold")
    W.place_sword(wak, frame_matrix(o + V((0.62, 0.17, hgt * 0.55 + 0.06)), (1, 0, 0), (0, 0, 1)), coll, None,
                  "Showcase_Wakizashi_Sheathed")
    drawn = W.sword_parts(0.27, 0.76, 0.020, drawn=True, blade_len=0.70)
    W.place_sword(drawn, frame_matrix(o + V((0.42, -0.22, 0.018)), (1, 0, 0), (0, -1, 0.0)), coll, None,
                  "Showcase_Katana_Drawn")
    gun = W.matchlock_parts()
    gm = frame_matrix(o + V((-0.02, -0.26, 0.05)), (1, 0.12, 0), (0, -0.55, 1.0)) @ Matrix.Scale(1.25, 4)
    W.place_matchlock(gun, gm, coll, None, "Showcase_Matchlock_Tanegashima")
