"""Weapons: openwork tsuba, curved blades with hamon, sheathed/drawn katana & wakizashi, tanegashima
matchlock pistol, and a lacquered sword stand (katana-kake) for the props showcase."""
import math

from mathutils import Matrix, Vector

from kage_lib import (MD, NB, RNG, TAU, V, box, catmull_path, circle_profile, clamp, frame_matrix, grid, lathe, lerp,
                      lin, look_matrix, mat_lacquer, mod_solidify, mod_subsurf, new_mat, rect_profile, smooth, sweep,
                      to_obj, torus_md, tube, uv_sphere)
from kage_mats import M


# =============================================================================
# materials specific to weapons
# =============================================================================
def mat_blade(name="Blade_Steel_Hamon"):
    """Polished steel with a frosty wavy hamon along the edge (uv u = 0.5 is the edge)."""
    m = new_mat(name)
    nb = NB(m)
    tc = nb.texcoord()
    sep = nb.n("ShaderNodeSeparateXYZ", (-1200, 0))
    nb.link(tc.outputs["UV"], sep.inputs[0])
    edge_d = nb.math("ABSOLUTE", nb.math("SUBTRACT", sep.outputs[0], 0.5))
    wave = nb.math("MULTIPLY", nb.math("SINE", nb.math("MULTIPLY", sep.outputs[1], 70.0)), 0.025)
    n = nb.noise(tc.outputs["Object"], 90.0, 4, 0.5)
    wave = nb.math("ADD", wave, nb.math("MULTIPLY", n.outputs["Fac"], 0.04))
    th = nb.math("ADD", wave, 0.10)
    hamon = nb.math("LESS_THAN", edge_d, th)
    nioi = nb.n("ShaderNodeMapRange", (-500, -200))
    nb.link(nb.math("SUBTRACT", edge_d, th), nioi.inputs["Value"])
    nioi.inputs["From Min"].default_value = -0.03
    nioi.inputs["From Max"].default_value = 0.0
    nioi.inputs["To Min"].default_value = 1.0
    nioi.inputs["To Max"].default_value = 0.0
    frost = nb.math("MAXIMUM", hamon, nb.math("MULTIPLY", nioi.outputs[0], 0.6))
    col = nb.mix(frost, (0.50, 0.51, 0.53), (0.78, 0.79, 0.80))
    rough = nb.mixf(frost, 0.12, 0.32)
    p = nb.principled(Base_Color=col, Metallic=1.0, Roughness=rough)
    nb.output(p.outputs[0])
    return m


def weapon_mats():
    if "blade" not in M:
        M["blade"] = mat_blade()
        M["stock"] = mat_lacquer("Matchlock_Stock_Wood", "filigree_sparse.png", uv_scale=(3.0, 1.0), wear=0.35,
                                 base=(0.045, 0.016, 0.008), gold_tint=(0.70, 0.48, 0.20), relief=0.2, dust=0.1)
        M["barrel"] = mat_lacquer("Matchlock_Barrel_Iron", "filigree_sparse.png", uv_scale=(1.0, 4.0), wear=0.4,
                                  base=(0.02, 0.02, 0.022), gold_tint=(0.72, 0.50, 0.21), relief=0.15, dust=0.1)
        M["brass"] = M["gold"]
    return M


# =============================================================================
# components
# =============================================================================
def tsuba_md(r_out=0.040, r_in=0.0135, thick=0.0055, petals=4, oval=0.92):
    """Iron tsuba (YZ plane, axis X) with sukashi openwork; returns (iron, gold) MDs."""
    iron, gold = MD(), MD()
    us = lin(0, TAU, 96)
    vs = lin(r_in, r_out, 14)

    def fn(u, v, i, j):
        return V((0.0, v * math.cos(u), v * math.sin(u) * oval))

    def keep(i, j):
        a = (us[i] + us[i + 1]) / 2
        rr = (vs[j] + vs[j + 1]) / 2
        # petal-shaped openings between r 0.018 and 0.034
        for k in range(petals):
            ca = TAU * (k + 0.5) / petals
            da = math.atan2(math.sin(a - ca), math.cos(a - ca))
            w = 0.30 * math.sin(math.pi * clamp((rr - 0.019) / 0.014))
            if 0.019 < rr < 0.033 and abs(da) < w:
                return False
        return True

    face = grid(fn, us, vs, closed_u=True, keep=keep)
    iron.add(face)
    # inner solid disc (where seppa sit)
    disc = grid(lambda u, v, i, j: V((0.0, v * math.cos(u), v * math.sin(u) * oval)), lin(0, TAU, 32),
                lin(0.0, r_in, 2), closed_u=True, pole_v0=True)
    iron.add(disc)
    # gold rim (fukurin)
    rim = [V((0.0, r_out * math.cos(a), r_out * math.sin(a) * oval)) for a in lin(0, TAU, 65)[:-1]]
    gold.add(sweep(rim, rect_profile(thick + 0.0015, 0.004, 1), up=lambda i, p: V((0, p.y, p.z)), closed_path=True))
    # gold inlay bead around each opening
    for k in range(petals):
        ca = TAU * (k + 0.5) / petals
        pts = []
        for q in range(25):
            t = q / 24
            rr = lerp(0.0195, 0.0325, t)
            w = 0.30 * math.sin(math.pi * clamp((rr - 0.019) / 0.014)) + 0.03
            pts.append((rr, ca + w))
        for q in range(24, -1, -1):
            t = q / 24
            rr = lerp(0.0195, 0.0325, t)
            w = 0.30 * math.sin(math.pi * clamp((rr - 0.019) / 0.014)) + 0.03
            pts.append((rr, ca - w))
        for sx in (-1, 1):
            loop = [V((sx * thick / 2, rr * math.cos(a), rr * math.sin(a) * oval)) for rr, a in pts]
            gold.add(tube(loop, 0.0007, 4, cap0=False, cap1=False))
    return iron, gold


def blade_md(length=0.70, width=0.031, thick=0.0072, sori=0.020, tip=0.055):
    """Curved shinogi-zukuri blade along +X from the habaki; edge toward -Z. uv u=0.5 at the edge."""
    n = 60
    path = []
    for k in range(n + 1):
        x = length * k / n
        path.append(V((x, 0.0, sori * (x / length) ** 2)))
    # cross-section (y = thickness, z = height), ordered so that u=0.5 is the edge
    prof = [(0.0, 0.5), (0.30, 0.47), (0.48, 0.10), (0.15, -0.40), (0.0, -0.5),
            (-0.15, -0.40), (-0.48, 0.10), (-0.30, 0.47), (0.0, 0.5)]
    # rotate so index 4 (edge) sits at u = 0.5
    def scale(t):
        x = t * length
        w = lerp(width, width * 0.72, t)
        if x > length - tip:
            k = (x - (length - tip)) / tip
            w *= math.sqrt(max(0.0, 1 - k ** 1.6))
        th = lerp(thick, thick * 0.65, t) * (1 if x < length - tip else max(0.05, 1 - (x - length + tip) / tip))
        return (th, max(w, 0.0005))

    prof2 = [(p[0], p[1]) for p in prof]
    md = sweep(path, prof2, up=(0, 0, 1), scale=scale, cap0=True)
    # bend the kissaki: lift the edge side near the tip so the point curves up
    out = []
    for p in md.v:
        if p.x > length - tip:
            k = (p.x - (length - tip)) / tip
            p = V((p.x, p.y, p.z + width * 0.35 * k ** 2))
        out.append(p)
    md.v = out
    return md


def sword_parts(tsuka_len=0.27, saya_len=0.76, sori=0.020, wrap="tsuka", drawn=False, blade_len=None):
    """Returns dict material-key -> MD in sword-local space (+X toward tip, origin at the tsuba)."""
    weapon_mats()
    parts = {k: MD() for k in ("saya", "gold", "iron", "tsuka", "tsuka_gold", "cord", "blade")}
    blade_len = blade_len or saya_len - 0.06

    def curve(x, L=saya_len, s_=sori):
        return V((x, 0.0, s_ * (max(x, 0) / L) ** 2))

    if not drawn:
        n = 44
        path = [curve(lerp(0.012, saya_len, k / n)) for k in range(n + 1)]
        prof = [(0.0088 * math.cos(a), 0.0138 * math.sin(a)) for a in lin(0, TAU, 18)]
        parts["saya"].add(sweep(path, prof, up=(0, 0, 1), scale=lambda t: 1.0 - 0.18 * t, cap1=True))

        def band(x0, x1, grow=0.0012, mat="gold"):
            p = [curve(lerp(x0, x1, k / 3)) for k in range(4)]
            t0 = (x0 - 0.012) / saya_len
            s = 1.0 - 0.18 * clamp(t0)
            pr = [((0.0088 * s + grow) * math.cos(a), (0.0138 * s + grow) * math.sin(a)) for a in lin(0, TAU, 18)]
            parts[mat].add(sweep(p, pr, up=(0, 0, 1), cap0=True, cap1=True))

        band(0.010, 0.028)                                      # koiguchi
        band(0.20, 0.212, 0.0010)
        band(saya_len * 0.42, saya_len * 0.42 + 0.065, 0.0009)  # ornate sleeve
        band(saya_len * 0.42 + 0.075, saya_len * 0.42 + 0.083, 0.0010)
        band(saya_len * 0.62, saya_len * 0.62 + 0.012, 0.0010)
        band(saya_len - 0.048, saya_len + 0.002, 0.0016)        # kojiri
        end = uv_sphere(1.0, 14, 8)
        end.v = [V((p.x * 0.006, p.y * 0.0088 * 0.84, p.z * 0.0138 * 0.84)) + curve(saya_len + 0.002) for p in end.v]
        parts["gold"].add(end)
        # kurikata knob + sageo cord wrapped and hanging
        kk = box(0.024, 0.010, 0.011)
        kk.translate(curve(0.11) + V((0, -0.0115, -0.004)))
        parts["saya"].add(kk)
        kp = curve(0.11) + V((0, -0.019, -0.004))
        parts["cord"].add(torus_md(0.006, 0.0024, 12, 6).transform(look_matrix(kp, (0, -1, 0))))
        for k in range(5):
            x = 0.125 + k * 0.012
            ring = [curve(x) + V((0, 0.0098 * math.cos(a), 0.0148 * math.sin(a))) for a in lin(0, TAU, 17)[:-1]]
            parts["cord"].add(sweep(ring, circle_profile(0.0022, 5), closed_path=True, up=lambda i, p, c=curve(x): p - c))
        sageo = catmull_path([kp, kp + V((-0.03, -0.02, -0.03)), kp + V((-0.06, -0.015, -0.055)),
                              kp + V((-0.05, -0.01, -0.095)), kp + V((0.02, -0.012, -0.085)),
                              kp + V((0.06, -0.012, -0.05))], 6)
        parts["cord"].add(tube(sageo, 0.0028, 6, rx=0.0045))
    else:
        parts["blade"].add(blade_md(blade_len, sori=sori * 1.05))
    # habaki (blade collar)
    hb = sweep([V((0.002, 0, 0)), V((0.030, 0, 0.0005))],
               [(0.0052 * math.cos(a), 0.0170 * math.sin(a) - 0.001) for a in lin(0, TAU, 18)], up=(0, 0, 1),
               scale=lambda t: 1.0 - 0.12 * t, cap0=True, cap1=True)
    parts["gold"].add(hb)
    # tsuba + seppa
    ti, tg = tsuba_md()
    parts["iron"].add(ti)
    parts["gold"].add(tg)
    for sx in (-1, 1):
        sep = lathe([(0.0, -0.0008), (0.018, -0.0008), (0.018, 0.0008), (0.0, 0.0008)], 24)
        sep.v = [V((p.x * 0.72, p.y, p.z)) for p in sep.v]
        sep.transform(Matrix.Translation((0.0038 * sx, 0, 0)) @ Matrix.Rotation(math.pi / 2, 4, "Y"))
        parts["gold"].add(sep)
    # tsuka: diamond silk wrap over same, fuchi, kashira, menuki
    hp = [V((lerp(-0.006, -tsuka_len + 0.022, k / 24), 0, 0)) for k in range(25)]
    hprof = [(0.0125 * math.cos(a), 0.0158 * math.sin(a)) for a in lin(0, TAU, 22)]
    parts[wrap].add(sweep(hp, hprof, up=(0, 0, 1), scale=lambda t: 1.0 - 0.05 * math.sin(math.pi * t) + 0.02 * t))
    # raised ito crossings (diamond knots) along both faces
    nd = int(tsuka_len / 0.024)
    for k in range(nd):
        x = -0.020 - k * (tsuka_len - 0.045) / max(1, nd - 1)
        for sz in (-1, 1):
            kn = uv_sphere(1.0, 8, 5)
            kn.v = [V((p.x * 0.006, p.y * 0.004, p.z * 0.0025)) + V((x, 0.0, sz * 0.0158)) for p in kn.v]
            parts[wrap].add(kn)
    fp = [V((-0.006, 0, 0)), V((-0.020, 0, 0))]
    parts["gold"].add(sweep(fp, [(0.0138 * math.cos(a), 0.0172 * math.sin(a)) for a in lin(0, TAU, 22)],
                            up=(0, 0, 1), cap0=True, cap1=True))
    kp = [V((-tsuka_len + 0.026, 0, 0)), V((-tsuka_len + 0.004, 0, 0))]
    parts["gold"].add(sweep(kp, [(0.0140 * math.cos(a), 0.0174 * math.sin(a)) for a in lin(0, TAU, 22)],
                            up=(0, 0, 1), scale=lambda t: 1.0 - 0.08 * t, cap0=True))
    kc = uv_sphere(1.0, 16, 8)
    kc.v = [V((-tsuka_len + 0.004 - max(0.0, -p.x) * 0.007, p.y * 0.0128, p.z * 0.016)) for p in kc.v]
    parts["gold"].add(kc)
    for s in (-1, 1):
        mk = uv_sphere(1.0, 10, 6)
        mk.v = [V((p.x * 0.016, p.y * 0.0032, p.z * 0.006)) + V((-tsuka_len * 0.55, 0.0128 * s, 0.002)) for p in mk.v]
        parts["gold"].add(mk)
    return parts


def place_sword(parts, m, coll, root, prefix):
    weapon_mats()
    mats = {"saya": M["lacquer_saya"], "gold": M["gold"], "iron": M["iron"], "tsuka": M["tsuka"],
            "tsuka_gold": M["tsuka_gold"], "cord": M["cord_red"], "blade": M["blade"]}
    out = []
    for k, md in parts.items():
        if not md.v:
            continue
        ob = to_obj(f"{prefix}_{k.capitalize()}", md.copy().transform(m), mats[k], coll, parent=root)
        if k in ("saya", "tsuka", "tsuka_gold"):
            mod_subsurf(ob, 1, 2)
        if k == "iron":
            mod_solidify(ob, 0.0055, 0.0)
        out.append(ob)
    return out


# =============================================================================
# Tanegashima matchlock pistol (from the item row of the concept sheet)
# =============================================================================
def matchlock_parts(L=0.56):
    weapon_mats()
    parts = {k: MD() for k in ("stock", "barrel", "brass", "cord", "iron")}
    # octagonal barrel along +X from the breech (x=0) to the muzzle (x=L*0.72)
    bl = L * 0.72
    oct8 = [(0.0115 * math.cos(a + math.pi / 8), 0.0115 * math.sin(a + math.pi / 8)) for a in lin(0, TAU, 9)]
    bpath = [V((x, 0, 0.018)) for x in lin(0.0, bl, 16)]
    parts["barrel"].add(sweep(bpath, oct8, up=(0, 0, 1), scale=lambda t: 1.0 - 0.15 * t, cap0=True, cap1=False))
    # muzzle flare + bore
    mz = lathe([(0.0068, 0.0), (0.0125, 0.0), (0.0130, 0.012), (0.0110, 0.016), (0.0060, 0.016)], 16)
    mz.transform(Matrix.Translation((bl - 0.012, 0, 0.018)) @ Matrix.Rotation(math.pi / 2, 4, "Y"))
    parts["brass"].add(mz)
    for x in (0.06, bl * 0.45, bl * 0.80):
        ring = lathe([(0.0122, 0.0), (0.0128, 0.002), (0.0128, 0.008), (0.0122, 0.010)], 16)
        ring.transform(Matrix.Translation((x, 0, 0.018)) @ Matrix.Rotation(math.pi / 2, 4, "Y"))
        parts["brass"].add(ring)
    # front sight & rear sight
    fs = box(0.008, 0.003, 0.006)
    fs.translate((bl - 0.02, 0, 0.032))
    parts["brass"].add(fs)
    rs = box(0.012, 0.010, 0.008)
    rs.translate((0.04, 0, 0.032))
    parts["brass"].add(rs)

    # stock: lofted sections along x (fore-stock under the barrel + curved pistol grip)
    def sect(x):
        # returns (z_center, half_height, half_width)
        if x >= 0.0:
            t = x / bl
            return (0.005 - 0.004 * t, 0.017 - 0.006 * t, 0.0135 - 0.003 * t)
        t = -x / 0.16
        return (0.005 - 0.075 * t ** 1.6, 0.020 + 0.006 * t, 0.0150)

    xs = lin(-0.16, bl * 0.92, 40)

    def sfn(u, v, i, j):
        x = xs[j]
        zc, hh, hw = sect(x)
        a = u
        e = 2.6
        c, s = math.cos(a), math.sin(a)
        y = math.copysign(abs(c) ** (2 / e), c) * hw
        z = zc + math.copysign(abs(s) ** (2 / e), s) * hh
        # the grip curves down: shear x with z for the butt
        xx = x + (0.03 * (-x / 0.16) ** 2 if x < 0 else 0.0)
        return V((xx, y, z))

    st = grid(sfn, lin(0, TAU, 20), list(range(len(xs))), closed_u=True)
    parts["stock"].add(st)
    # butt cap
    bc = lathe([(0.0, 0.0), (0.022, 0.0), (0.024, 0.006), (0.0, 0.007)], 16)
    zc, hh, hw = sect(-0.16)
    bc.transform(Matrix.Translation((-0.16 + 0.03, 0, zc)) @ Matrix.Rotation(-math.pi / 2, 4, "Y"))
    parts["brass"].add(bc)
    # gold inlay panels on the stock sides
    for sx in (-1, 1):
        pnl = box(0.10, 0.001, 0.016)
        pnl.translate((0.12, sx * 0.0128, 0.004))
        parts["brass"].add(pnl)
    # lock plate (right side, -Y), serpentine, pan, spring, trigger
    lp = box(0.085, 0.003, 0.022)
    lp.translate((0.015, -0.0150, 0.006))
    parts["brass"].add(lp)
    pan = lathe([(0.0, 0.0), (0.008, 0.0), (0.009, 0.004), (0.0, 0.003)], 12)
    pan.translate((0.008, -0.020, 0.022))
    parts["brass"].add(pan)
    cover = box(0.014, 0.012, 0.002)
    cover.translate((0.010, -0.022, 0.027))
    parts["brass"].add(cover)
    serp = catmull_path([V((0.050, -0.019, 0.010)), V((0.058, -0.021, 0.030)), V((0.042, -0.022, 0.044)),
                         V((0.022, -0.022, 0.040)), V((0.014, -0.022, 0.030))], 6)
    parts["brass"].add(tube(serp, 0.0026, 6))
    clamp_ = box(0.006, 0.006, 0.008)
    clamp_.translate((0.013, -0.022, 0.028))
    parts["brass"].add(clamp_)
    spring = catmull_path([V((0.055, -0.0175, 0.000)), V((0.035, -0.0180, -0.004)), V((0.015, -0.0175, 0.002))], 5)
    parts["brass"].add(tube(spring, 0.0012, 5))
    trig = catmull_path([V((0.000, 0, -0.012)), V((-0.002, 0, -0.026)), V((0.006, 0, -0.036))], 6)
    parts["brass"].add(tube(trig, 0.0025, 6, rx=0.0015))
    # ramrod under the barrel
    parts["stock"].add(tube([V((0.06, 0, -0.010)), V((bl * 0.95, 0, -0.008))], 0.0032, 6))
    tipm = uv_sphere(0.0045, 8, 6)
    tipm.translate((bl * 0.95, 0, -0.008))
    parts["brass"].add(tipm)
    # match cord coiled at the grip
    coil = MD()
    for k in range(4):
        ring = [V((-0.05 - k * 0.006, 0.019 * math.cos(a), -0.02 + 0.026 * math.sin(a))) for a in lin(0, TAU, 21)[:-1]]
        coil.add(sweep(ring, circle_profile(0.0022, 5), closed_path=True, up=(1, 0, 0)))
    parts["cord"].add(coil)
    return parts


def place_matchlock(parts, m, coll, root, prefix):
    weapon_mats()
    mats = {"stock": M["stock"], "barrel": M["barrel"], "brass": M["gold"], "cord": M["cord_red"], "iron": M["iron"]}
    for k, md in parts.items():
        if not md.v:
            continue
        ob = to_obj(f"{prefix}_{k.capitalize()}", md.copy().transform(m), mats[k], coll, parent=root)
        if k == "stock":
            mod_subsurf(ob, 1, 2)


# =============================================================================
# Sword stand (katana-kake) for the showcase
# =============================================================================
def sword_stand_md(w=0.95, h=0.42):
    md = MD()
    base = box(w, 0.22, 0.035)
    base.translate((0, 0, 0.0175))
    md.add(base)
    for sx in (-1, 1):
        def side(u, v, i, j, sx=sx):
            # upright with a scrolled top, cut-outs for two tiers of swords
            y = lerp(-0.07, 0.07, u)
            z = lerp(0.035, h, v)
            return V((sx * w * 0.42, y * (1 - 0.3 * v), z))

        up = box(0.035, 0.16, h)
        up.translate((sx * w * 0.42, 0, h / 2 + 0.035))
        md.add(up)
        for zz in (h * 0.55, h * 0.95):
            arm = box(0.05, 0.14, 0.022)
            arm.translate((sx * w * 0.42, -0.03, zz))
            md.add(arm)
    return md
