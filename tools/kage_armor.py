"""Torso (do cuirass, straps), sode shoulder guards, arms (kote + gloves), legs (pants, suneate, boots)."""
import math

from mathutils import Matrix, Vector

from kage_body import (ANKLE, CUIRASS, ELBOW, HIP, KNEE, SHOULDER, WRIST, torso_normal, torso_pt, superellipse)
from kage_lib import (MD, RNG, TAU, V, ang, catmull_path, circle_profile, clamp, fbm, frames_along, grid,
                      interp_smooth, lathe, lerp, limb, lin, look_matrix, mod_solidify, mod_subsurf, rect_profile,
                      resample, smooth, sweep, to_obj, torus_md, tube, uv_sphere, frame_matrix, cloth_mods, torn_profile)
from kage_mats import M


def both(md):
    """Return left + mirrored right copy."""
    out = MD()
    out.add(md)
    out.add(md.mirror_x())
    return out


def deg(a):
    return math.radians(a)


# =============================================================================
# helpers: cords, knots, tassels, rivets
# =============================================================================
def hang_cord(start, end, sag=0.02, r=0.003, n=10):
    mid = (V(start) + V(end)) / 2 + V((0, 0, -sag))
    path = catmull_path([V(start), mid, V(end)], n)
    return tube(path, r, 6)


def knot(center, normal, r=0.008, cord=0.0032):
    """Square-knot lump: two interlocked small tori."""
    md = MD()
    for k, tilt in enumerate((0.0, 1.2)):
        t = torus_md(r, cord, 16, 6)
        m = look_matrix(center, normal, (0, 0, 1))
        rot = Matrix.Rotation(tilt, 4, "Z") @ Matrix.Rotation(1.57 * k, 4, "X")
        t.transform(m @ rot)
        md.add(t)
    return md


def tassel(top, length=0.05, r0=0.004, r1=0.008, strands=18):
    lens = [length * RNG.uniform(0.85, 1.0) for _ in range(strands + 1)]

    def fn(u, v, i, j):
        rr = lerp(r0, r1, v ** 0.6) * (1 + 0.12 * math.sin(u * strands))
        return V(top) + V((rr * math.sin(u), -rr * math.cos(u), -v * lens[i % strands]))

    md = grid(fn, lin(0, TAU, strands), lin(0, 1, 6), closed_u=True)
    return md


def bow_knot(center, out_dir, down=(0, 0, -1), loop=0.022, tail=0.07, r=0.0032, seed=0):
    """Decorative bow: knot + two loops + two hanging tails (red cord ties)."""
    rng = RNG
    md = MD()
    c = V(center)
    o = V(out_dir).normalized()
    side = o.cross(V((0, 0, 1))).normalized()
    md.add(knot(c, o, 0.006, r))
    for s in (-1, 1):
        loop_pts = [c, c + side * s * loop * 0.6 + V((0, 0, loop * 0.5)) + o * 0.006,
                    c + side * s * loop * 1.1 + V((0, 0, 0.0)) + o * 0.008,
                    c + side * s * loop * 0.6 + V((0, 0, -loop * 0.45)) + o * 0.006, c]
        md.add(tube(catmull_path(loop_pts, 5), r, 6, cap0=False, cap1=False))
        t_end = c + side * s * rng.uniform(0.005, 0.02) + V(down) * tail * rng.uniform(0.8, 1.1) + o * 0.006
        tail_pts = [c, c + side * s * 0.008 + V(down) * tail * 0.4 + o * 0.008, t_end]
        md.add(tube(catmull_path(tail_pts, 6), r, 6))
        md.add(tassel(t_end, 0.022, r * 0.9, r * 1.8, 10))
    return md


def rivets_along(path, spacing, r, normals=None, offset=0.0):
    md = MD()
    L = 0.0
    nxt = spacing * 0.5
    for i in range(1, len(path)):
        a, b = V(path[i - 1]), V(path[i])
        seg = (b - a).length
        while L + seg >= nxt:
            t = (nxt - L) / seg if seg else 0
            p = a.lerp(b, t)
            n = normals[i] if normals else V((0, 0, 1))
            s = uv_sphere(r, 8, 5)
            s.v = [V((q.x, q.y, q.z * 0.6)) for q in s.v]
            s.transform(look_matrix(p + n * offset, n))
            md.add(s)
            nxt += spacing
        L += seg
    return md


# =============================================================================
# TORSO: under-kimono, cuirass, trims, crest, watagami, bandolier straps
# =============================================================================
TOP_TABLE = [(0, 1.438), (20, 1.452), (38, 1.470), (55, 1.445), (72, 1.385), (88, 1.338), (104, 1.385),
             (122, 1.445), (140, 1.468), (160, 1.462), (180, 1.456)]
CUI_BOTTOM = 1.025
LAME = 0.056


def cuirass_top(theta):
    d = abs(math.degrees(math.atan2(math.sin(theta), math.cos(theta))))
    return interp_smooth(TOP_TABLE, d)[0]


def cuirass_off(theta, z):
    """Surface offset of the cuirass: stepped lames below 1.25, chest swell above."""
    off = 0.0
    if z < CUI_BOTTOM + 4 * LAME:
        f = ((z - CUI_BOTTOM) / LAME) % 1.0
        off += 0.007 * (1.0 - f)
    front = max(0.0, math.cos(theta))
    for c in (-0.42, 0.42):
        off += 0.008 * math.exp(-((theta - c) / 0.35) ** 2) * math.exp(-((z - 1.37) / 0.06) ** 2)
    return off


def cui_pt(theta, z, extra=0.0):
    return torso_pt(theta, z, cuirass_off(theta, z) + extra)


def front_pt(x, z, off=0.0, table=CUIRASS, e=2.6):
    """Point on the front of a torso-table surface for a given x."""
    rx, ryf, ryb = interp_smooth(table, z)
    rx += off
    ryf += off
    q = clamp(abs(x) / rx, 0, 0.999)
    y = -ryf * (1 - q ** e) ** (1 / e)
    return V((x, y, z))


def build_torso(coll, root):
    # --- under-kimono torso (visible at arm holes, neck, between plates) ------
    def body(u, v, i, j):
        z = v
        p = torso_pt(u, z, -0.012)
        n = V((math.sin(u), -math.cos(u), 0))
        return p + n * 0.003 * fbm(p * 20)

    md = grid(body, lin(0, TAU, 64), lin(0.86, 1.565, 40), closed_u=True)
    ob = to_obj("Kimono_Torso", md, M["cloth"], coll, parent=root)
    mod_subsurf(ob, 1, 2)

    # --- cuirass shell ---------------------------------------------------------
    def shell(u, v, i, j):
        top = cuirass_top(u)
        z = lerp(CUI_BOTTOM, top, v)
        return cui_pt(u, z)

    nv = 48
    md = grid(shell, lin(0, TAU, 128), lin(0, 1, nv), closed_u=True)
    cu = to_obj("Do_Cuirass", md, M["lacquer_engraved"], coll, parent=root)
    mod_solidify(cu, 0.006, 1.0)
    mod_subsurf(cu, 1, 3)

    # --- gold trims -------------------------------------------------------------
    trims = MD()
    N = 160

    def loop_path(zf, extra):
        pts, ups = [], []
        for k in range(N):
            th = TAU * k / N
            z = zf(th)
            pts.append(cui_pt(th, z, extra))
            ups.append(torso_normal(th, z))
        return pts, ups

    pts, ups = loop_path(lambda th: cuirass_top(th) - 0.002, 0.004)
    trims.add(sweep(pts, circle_profile(0.0045, 8), up=lambda i, p: ups[i], closed_path=True))
    pts, ups = loop_path(lambda th: CUI_BOTTOM + 0.004, 0.009)
    trims.add(sweep(pts, rect_profile(0.010, 0.004, 1), up=lambda i, p: ups[i], closed_path=True))
    for k in range(1, 5):
        zz = CUI_BOTTOM + k * LAME - 0.004
        pts, ups = loop_path(lambda th, zz=zz: zz, 0.0085)
        trims.add(sweep(pts, rect_profile(0.006, 0.003, 1), up=lambda i, p: ups[i], closed_path=True))
    # muna-ita (chest plate) separation line
    pts, ups = loop_path(lambda th: 1.300 + 0.02 * math.cos(th), 0.005)
    trims.add(sweep(pts, rect_profile(0.005, 0.003, 1), up=lambda i, p: ups[i], closed_path=True))
    tr = to_obj("Do_Gold_Trims", trims, M["gold"], coll, parent=root)
    mod_subsurf(tr, 0, 1)

    # rivets along lame lines (front half)
    rv = MD()
    for k in range(5):
        zz = CUI_BOTTOM + k * LAME + 0.02
        for a in range(-60, 61, 12):
            th = deg(a)
            p = cui_pt(th, zz, 0.006)
            n = torso_normal(th, zz)
            s = uv_sphere(0.003, 8, 5)
            s.transform(look_matrix(p, n))
            rv.add(s)
    to_obj("Do_Rivets", rv, M["gold"], coll, parent=root)

    # --- chest crest decal (mon) ---------------------------------------------
    cz, cr = 1.392, 0.058

    def crest(u, v, i, j):
        x = lerp(-cr, cr, u)
        z = lerp(cz - cr, cz + cr, v)
        th = math.atan2(x, 0.16)
        p = front_pt(x, z, cuirass_off(th, z) + 0.0068)
        return p

    md = grid(crest, lin(0, 1, 24), lin(0, 1, 24))
    to_obj("Do_Chest_Mon", md, M["decal_mon_chest"], coll, parent=root)
    # raised black disc behind the crest with gold ring
    ring = MD()
    path, ups = [], []
    for k in range(64):
        a = TAU * k / 64
        x = cr * 0.97 * math.sin(a)
        z = cz + cr * 0.97 * math.cos(a)
        th = math.atan2(x, 0.16)
        path.append(front_pt(x, z, cuirass_off(th, z) + 0.0075))
        ups.append(torso_normal(th, z))
    ring.add(sweep(path, circle_profile(0.0028, 6), up=lambda i, p: ups[i], closed_path=True))
    to_obj("Do_Chest_Mon_Ring", ring, M["gold"], coll, parent=root)

    # --- watagami (shoulder straps of the do) --------------------------------
    wat = MD()
    wat_trim = MD()
    for side in (1, -1):
        pts, ups = [], []
        for k in range(25):
            t = k / 24
            th = deg(lerp(34, 146, t)) * side
            z = lerp(cuirass_top(deg(34)), cuirass_top(deg(146)), t) + 0.075 * math.sin(math.pi * t)
            off = 0.008
            pts.append(torso_pt(th, z, off))
            ups.append(torso_normal(th, z))
        wat.add(sweep(pts, rect_profile(0.052, 0.006, 2), up=lambda i, p, ups=ups: ups[i]))
        fr = frames_along(pts, up=lambda i, p, ups=ups: ups[i])
        for s in (-1, 1):
            edge = [p + B * 0.026 * s + Nn * 0.003 for p, (T, Nn, B) in zip(pts, fr)]
            wat_trim.add(tube(edge, 0.0025, 6))
    w = to_obj("Do_Watagami", wat, M["lacquer"], coll, parent=root)
    mod_subsurf(w, 1, 2)
    to_obj("Do_Watagami_Trim", wat_trim, M["gold"], coll, parent=root)

    # --- red cord knots + hanging cords at the chest-plate top corners ----------
    cords = MD()
    for side in (1, -1):
        th = deg(32) * side
        z = cuirass_top(th) - 0.008
        p = cui_pt(th, z, 0.010)
        n = torso_normal(th, z)
        cords.add(knot(p, n, 0.008, 0.0034))
        for k, (dx, L) in enumerate(((-0.012, 0.075), (0.010, 0.095))):
            a = p + n * 0.004
            b = cui_pt(th + deg(dx * 60) * side, z - L, 0.012)
            cords.add(hang_cord(a, b, 0.0, 0.0028, 8))
            cords.add(tassel(b, 0.03, 0.003, 0.006, 10))
    to_obj("Do_Red_Cords", cords, M["cord_red"], coll, parent=root)

    build_bandoliers(coll, root)


def strap_path(segments, n=60):
    """segments: list of (theta_deg, z, off) control points along the body."""
    ctrl = [cui_pt(deg(t), z, o) for t, z, o in segments]
    pts = catmull_path(ctrl, 8)
    pts = resample(pts, n)
    ups = []
    for p in pts:
        th = math.atan2(p.x, -p.y)
        ups.append(torso_normal(th, clamp(p.z, 1.0, 1.55)))
    return pts, ups


def build_bandoliers(coll, root):
    leather = MD()
    metal = MD()
    W, T = 0.040, 0.0055
    straps = [
        # strap A: left shoulder -> across chest -> right hip ; and down the back
        [(62, 1.468, 0.016), (40, 1.40, 0.016), (18, 1.345, 0.017), (0, 1.302, 0.019), (-25, 1.235, 0.020),
         (-48, 1.165, 0.021), (-68, 1.085, 0.030)],
        [(70, 1.475, 0.016), (90, 1.545, 0.020), (112, 1.52, 0.030), (135, 1.475, 0.036), (155, 1.42, 0.030),
         (180, 1.33, 0.016), (205, 1.24, 0.016), (232, 1.14, 0.030), (250, 1.07, 0.036)],
        # strap B: right shoulder -> across chest -> left hip
        [(-62, 1.468, 0.020), (-40, 1.40, 0.021), (-18, 1.345, 0.022), (0, 1.300, 0.024), (25, 1.235, 0.024),
         (48, 1.165, 0.025), (68, 1.085, 0.032)],
        [(-70, 1.475, 0.020), (-90, 1.545, 0.024), (-112, 1.52, 0.032), (-135, 1.475, 0.04)],
    ]
    for k, seg in enumerate(straps):
        pts, ups = strap_path(seg, 70)
        leather.add(sweep(pts, rect_profile(W, T, 2), up=lambda i, p, ups=ups: ups[i]))
        metal.add(rivets_along(pts, 0.06, 0.0032, normals=ups, offset=T * 0.5))
    # buckles on the front straps
    for seg, t in ((straps[0], 0.72), (straps[2], 0.70)):
        pts, ups = strap_path(seg, 70)
        i = int(t * (len(pts) - 1))
        fr = frames_along(pts, up=lambda i_, p, ups=ups: ups[i_])
        Tn, Nn, B = fr[i]
        c = pts[i] + Nn * (T * 0.5 + 0.002)
        frame = [c + Tn * a + B * b for a, b in ((-0.018, -0.026), (0.018, -0.026), (0.018, 0.026), (-0.018, 0.026))]
        metal.add(sweep(frame, rect_profile(0.004, 0.004, 1), up=lambda i_, p: Nn, closed_path=True))
        metal.add(tube([c - B * 0.026 + Nn * 0.002, c + B * 0.026 + Nn * 0.002], 0.0022, 6))
    lo = to_obj("Bandolier_Straps", leather, M["leather"], coll, parent=root)
    mod_subsurf(lo, 0, 1)
    to_obj("Bandolier_Buckles_Rivets", metal, M["gold_dark"], coll, parent=root)


# =============================================================================
# SODE (shoulder guards) with gilded dragons
# =============================================================================
SODE_W = 0.185
SODE_R = 0.13
SODE_LAMES = [
    # name, z_top, z_bot, flare_top, flare_bot, width_scale, material key
    ("Kanmuri", 0.000, -0.024, 0.004, 0.004, 1.04, "lacquer"),
    ("Ichi", -0.017, -0.140, 0.000, 0.008, 1.00, "dragon"),
    ("Ni", -0.131, -0.179, 0.009, 0.014, 1.02, "lamellar"),
    ("San", -0.169, -0.217, 0.015, 0.020, 1.04, "lamellar"),
    ("Yon", -0.208, -0.256, 0.020, 0.025, 1.06, "lamellar"),
]


def sode_local(x, z, flare):
    y = -(x * x) / (2 * SODE_R) + flare
    return V((x, y, z))


def build_sode(coll, root):
    for side in (1, -1):
        sname = "L" if side > 0 else "R"
        tilt = deg(15)
        origin = V((0.260 * side, 0.016, 1.528))
        xl = V((0, -1, 0)) if side > 0 else V((0, 1, 0))
        zl = V((0, 0, 1))
        yl = zl.cross(xl)
        rot = Matrix((xl, yl, zl)).transposed().to_4x4()
        tiltm = Matrix.Rotation(-tilt * side, 4, "Y")
        turn = Matrix.Rotation(-deg(22) * side, 4, "Z")
        mw = Matrix.Translation(origin) @ turn @ tiltm @ rot
        plates = {"lacquer": MD(), "dragon": MD(), "lamellar": MD()}
        gold = MD()
        gold_dk = MD()
        red = MD()
        for name, zt, zb, ft, fb, ws, mk in SODE_LAMES:
            W = SODE_W * ws

            def fn(u, v, i, j, W=W, zt=zt, zb=zb, ft=ft, fb=fb):
                x = lerp(-W / 2, W / 2, u)
                z = lerp(zb, zt, v)
                fl = lerp(fb, ft, v)
                return sode_local(x, z, fl)

            if mk == "dragon":
                # map the emblem onto the visible window (below the lacing, above the next lame)
                vis0, vis1 = -0.134, -0.037

                def uvd(u, v, i, j, zt=zt, zb=zb):
                    z = lerp(zb, zt, v)
                    return ((u - 0.04) / 0.92, (z - vis0) / (vis1 - vis0))

                md = grid(fn, lin(0, 1, 64), lin(0, 1, 24), uv_fn=uvd)
            else:
                md = grid(fn, lin(0, 1, 24), lin(0, 1, 8))
            plates[mk].add(md)
            # gold trims: bottom (+ sides) of each lame; full border on the dragon plate
            tgt = gold if mk == "dragon" else gold_dk
            bottom = [sode_local(lerp(-W / 2, W / 2, k / 24), zb + 0.003, fb + 0.004) for k in range(25)]
            tgt.add(tube(bottom, 0.0032, 6, rx=0.0045))
            for sx in (-1, 1):
                sidep = [sode_local(sx * W / 2 * 0.995, lerp(zb, zt, k / 6), lerp(fb, ft, k / 6) + 0.003)
                         for k in range(7)]
                tgt.add(tube(sidep, 0.0026, 6))
            if mk == "dragon":
                top = [sode_local(lerp(-W / 2, W / 2, k / 24), zt - 0.004, ft + 0.004) for k in range(25)]
                gold.add(tube(top, 0.0028, 6))
                # rivet studs along the border
                for k in range(11):
                    for zz, ff in ((zb + 0.010, fb + 0.004), (zt - 0.012, ft + 0.004)):
                        s = uv_sphere(0.0028, 8, 5)
                        s.translate(sode_local(lerp(-W / 2 + 0.01, W / 2 - 0.01, k / 10), zz, ff + 0.001))
                        gold.add(s)
                # red kebiki lacing band across the top of the dragon plate
                for k in range(13):
                    x = lerp(-W / 2 + 0.012, W / 2 - 0.012, k / 12)
                    a = sode_local(x, zt - 0.006, ft + 0.0045)
                    b = sode_local(x, zt - 0.030, lerp(ft, fb, 0.18) + 0.0045)
                    red.add(tube([a, b], 0.0022, 6, rx=0.0032))
            if mk == "lamellar":
                # vertical lacing between lames + hishinui cross stitches on the last lame
                for k in range(7):
                    x = lerp(-W / 2 + 0.018, W / 2 - 0.018, k / 6)
                    a = sode_local(x, zt + 0.004, ft + 0.002)
                    b = sode_local(x, zt - 0.014, lerp(ft, fb, 0.3) + 0.0045)
                    red.add(tube([a, b], 0.0022, 6, rx=0.003))
                if name == "Yon":
                    for k in range(6):
                        x = lerp(-W / 2 + 0.025, W / 2 - 0.025, k / 5)
                        for s in (-1, 1):
                            a = sode_local(x - 0.007 * s, zb + 0.016, fb + 0.0045)
                            b = sode_local(x + 0.007 * s, zb + 0.004, fb + 0.0045)
                            red.add(tube([a, b], 0.0018, 6))
        # kanmuri ridge (top bar) in gold
        ridge = [sode_local(lerp(-SODE_W * 0.54, SODE_W * 0.54, k / 24), 0.002, 0.006) for k in range(25)]
        gold.add(tube(ridge, 0.0045, 8))
        for sx in (-1, 1):
            cap = uv_sphere(0.0065, 10, 6)
            cap.translate(sode_local(sx * SODE_W * 0.54, 0.002, 0.006))
            gold.add(cap)
        # tie cords up to the watagami
        tie = MD()
        for sx in (-1, 1):
            a = sode_local(sx * SODE_W * 0.35, -0.004, 0.0)
            b = a + V((0, -0.035, 0.02))
            tie.add(tube([a, (a + b) / 2 + V((0, -0.01, 0.008)), b], 0.0026, 6))
        red.add(tie)
        objs = []
        dragon_mat = M["lacquer_dragon_L"] if side > 0 else M["lacquer_dragon_R"]
        for mk, mat in (("lacquer", M["lacquer"]), ("dragon", dragon_mat), ("lamellar", M["lacquer_lamellar"])):
            ob = to_obj(f"Sode_{sname}_{mk.capitalize()}", plates[mk].transform(mw), mat, coll, parent=root)
            mod_solidify(ob, 0.0045, -1.0)
            mod_subsurf(ob, 1, 3 if mk == "dragon" else 2)
            objs.append(ob)
        to_obj(f"Sode_{sname}_Gold", gold.transform(mw), M["gold"], coll, parent=root)
        to_obj(f"Sode_{sname}_Gold_Antique", gold_dk.transform(mw), M["gold_dark"], coll, parent=root)
        to_obj(f"Sode_{sname}_Lacing", red.transform(mw), M["cord_red"], coll, parent=root)


# =============================================================================
# ARMS: sleeves, kote (bracers), elbow cops, gloves with tekko
# =============================================================================
def arm_axis_frame(a, b, out_hint):
    ax = (V(b) - V(a)).normalized()
    out = V(out_hint)
    out = (out - ax * out.dot(ax)).normalized()
    return ax, out, ax.cross(out)


FINGER_PLATES = MD()


def build_hand():
    """Left glove in hand-local space: fingers -Z, back of hand +X, thumb -Y."""
    global FINGER_PLATES
    FINGER_PLATES = MD()
    md = MD()

    def palm(u, v, i, j):
        # superellipsoid
        th, ph = u, v
        cx, sx = math.cos(th), math.sin(th)
        cp, sp = math.cos(ph), math.sin(ph)
        e = 0.55
        fx = math.copysign(abs(cp) ** e, cp) * math.copysign(abs(cx) ** e, cx)
        fy = math.copysign(abs(cp) ** e, cp) * math.copysign(abs(sx) ** e, sx)
        fz = math.copysign(abs(sp) ** e, sp)
        x = fx * 0.0195
        y = fy * 0.047
        z = -0.052 + fz * 0.054
        # palm slightly cupped, back slightly domed
        x += 0.004 * (1 - (y / 0.043) ** 2) * (1 if x > 0 else -0.5)
        return V((x, y, z))

    md.add(grid(palm, lin(0, TAU, 24), lin(-math.pi / 2, math.pi / 2, 14), closed_u=True, pole_v0=False))
    fingers = [(-0.034, 0.080, 0.0118), (-0.0115, 0.089, 0.0122), (0.0115, 0.085, 0.0118), (0.034, 0.068, 0.0108)]
    curls = [(14, 24, 16), (18, 28, 18), (22, 30, 20), (26, 32, 22)]
    for (y, L, r), cu in zip(fingers, curls):
        p = V((0.001, y * 0.97, -0.100))
        d = V((0, 0, -1))
        pts = [p.copy()]
        for seg, c in zip((0.45, 0.30, 0.25), cu):
            d = Matrix.Rotation(deg(c), 3, "Y") @ d
            for s in range(3):
                p = p + d * (L * seg / 3)
                pts.append(p.copy())
        n = len(pts)

        def sc(t):
            k = 1.0 - 0.18 * t
            if t > 0.86:
                k *= math.sqrt(max(0.05, 1 - ((t - 0.86) / 0.14) ** 2))
            # knuckle bulges
            k *= 1 + 0.08 * math.exp(-((t - 0.0) / 0.06) ** 2) + 0.06 * math.exp(-((t - 0.45) / 0.05) ** 2)
            return k

        md.add(tube(pts, r, 10, scale=sc, cap0=True, cap1=True))
        # small lacquered plates on the back of the first two finger segments
        for a_i, b_i in ((0, 3), (3, 6)):
            pa, pb = pts[a_i], pts[b_i]
            ax_ = (pb - pa).normalized()
            out = V((1, 0, 0))
            out = (out - ax_ * out.dot(ax_)).normalized()
            plate = box(0.0035, r * 1.7, (pb - pa).length * 0.82)
            m = Matrix((out.cross(ax_).normalized(), out, ax_)).transposed().to_4x4()
            m = look_matrix((pa + pb) / 2 + out * (r * 0.95), ax_, out)
            plate.transform(m @ Matrix.Rotation(math.pi / 2, 4, "Z"))
            FINGER_PLATES.add(plate)
    # thumb
    base = V((-0.006, -0.044, -0.030))
    d = V((-0.30, -0.55, -0.78)).normalized()
    pts = [base]
    p = base.copy()
    for seg, c in ((0.040, 12), (0.032, 25)):
        d = Matrix.Rotation(deg(c), 3, V((0, 0, 1)).cross(d).normalized()) @ d
        for s in range(3):
            p = p + d * seg / 3
            pts.append(p.copy())
    md.add(tube(pts, 0.0135, 10, scale=lambda t: (1.0 - 0.15 * t) * (math.sqrt(max(0.05, 1 - ((t - 0.82) / 0.18) ** 2)) if t > 0.82 else 1.0), cap0=True, cap1=True))
    # cuff of the glove
    md.add(limb([V((0, 0, 0.035)), V((0, 0, -0.012))], lambda t, th: 0.040 + 0.006 * t, 20, ref=(1, 0, 0),
                closed=False))
    return md


def build_tekko():
    """Back-of-hand plate (hand local)."""
    def fn(u, v, i, j):
        y = lerp(-0.040, 0.040, u)
        z = lerp(-0.004, -0.085, v)
        x = 0.0215 + 0.006 * (1 - (y / 0.045) ** 2) - 0.004 * v
        return V((x, y * (1 - 0.15 * v), z))

    plate = grid(fn, lin(0, 1, 12), lin(0, 1, 10))
    trim = MD()
    edge = [fn(k / 12, 1.0, 0, 0) + V((0.002, 0, 0)) for k in range(13)]
    trim.add(tube(edge, 0.002, 6))
    for s in (0.0, 1.0):
        e2 = [fn(s, k / 10, 0, 0) + V((0.002, 0, 0)) for k in range(11)]
        trim.add(tube(e2, 0.002, 6))
    # knuckle guards: small plates over each finger's first segment
    for y in (-0.031, -0.0105, 0.0105, 0.031):
        b = box(0.004, 0.016, 0.018)
        b.translate((0.016, y, -0.100))
        plate.add(b)
    return plate, trim


def box(*a, **k):
    from kage_lib import box as _b
    return _b(*a, **k)


def build_arms(coll, root):
    sleeve = MD()
    forearm = MD()
    bracer = MD()
    gold = MD()
    straps = MD()
    cop = MD()
    glove = MD()
    tekko = MD()
    tekko_gold = MD()
    red = MD()
    S, E, Wr = SHOULDER, ELBOW, WRIST
    out_hint = V((1.0, -0.15, 0.0))

    # upper sleeve (black printed cloth), slightly baggy, folds
    def r_up(t, th):
        base = interp_smooth([(0.0, 0.050), (0.2, 0.056), (0.45, 0.060), (0.7, 0.059), (0.9, 0.055), (1.0, 0.053)], t)[0]
        f = 0.005 * math.sin(th * 5 + t * 7) + 0.003 * math.sin(th * 9 - t * 13)
        return base + f * (0.4 + 0.6 * t)

    sleeve.add(limb([S + V((-0.02, 0, 0.03)), S, (S + E) / 2, E], r_up, 32, nt=24, ref=out_hint))
    # elbow puff
    ax, out, side = arm_axis_frame(E, Wr, out_hint)

    def r_puff(t, th):
        return 0.053 + 0.011 * math.sin(math.pi * t) + 0.004 * math.sin(th * 7)

    sleeve.add(limb([E + (E - S).normalized() * 0.03, E + ax * 0.03], r_puff, 28, nt=6, ref=out_hint))
    # forearm sleeve
    forearm.add(limb([E, Wr], lambda t, th: lerp(0.049, 0.040, t) + 0.002 * math.sin(th * 6), 24, nt=10,
                     ref=out_hint))

    # kote bracer plate: partial cylinder on the outer side
    t0, t1 = 0.10, 0.96
    th0, th1 = -deg(118), deg(118)
    a_pt = E.lerp(Wr, t0)
    b_pt = E.lerp(Wr, t1)

    def r_br(t, th):
        r = lerp(0.056, 0.046, t) + 0.006 * smooth((t - 0.85) / 0.15)
        return r + 0.003 * math.cos(th) ** 2

    br = limb([a_pt, b_pt], r_br, 30, nt=20, ref=out_hint, th0=th0, th1=th1, uv_flip=True)
    bracer.add(br)
    # gold trim around bracer border
    fr_ax = arm_axis_frame(a_pt, b_pt, out_hint)

    def br_point(t, th, extra=0.0):
        axv, o, sd = fr_ax
        c = a_pt.lerp(b_pt, t)
        return c + (o * math.cos(th) + sd * math.sin(th)) * (r_br(t, th) + extra)

    for th in (th0, th1):
        gold.add(tube([br_point(k / 12, th * 0.995, 0.002) for k in range(13)], 0.0028, 6))
    for t in (0.0, 1.0):
        gold.add(tube([br_point(t, lerp(th0, th1, k / 24), 0.002) for k in range(25)], 0.0032, 6))
    # central raised plate border lines
    for th in (-deg(32), deg(32)):
        gold.add(tube([br_point(0.04 + k / 12 * 0.92, th, 0.0035) for k in range(13)], 0.0018, 6))
    # leather straps around forearm with gold buckles
    for t in (0.22, 0.52, 0.80):
        c = E.lerp(Wr, lerp(t0, t1, t))
        ring = [c + (fr_ax[1] * math.cos(a) + fr_ax[2] * math.sin(a)) * (r_br(lerp(t0, t1, t), a) + 0.0045)
                for a in lin(0, TAU, 40)[:-1]]
        straps.add(sweep(ring, rect_profile(0.004, 0.012, 1), up=lambda i, p, c=c: (p - c), closed_path=True))
        bk = c + (fr_ax[1] * math.cos(deg(150)) + fr_ax[2] * math.sin(deg(150))) * (r_br(t, deg(150)) + 0.008)
        b = box(0.012, 0.016, 0.006)
        b.transform(look_matrix(bk, (bk - c), fr_ax[0]))
        gold.add(b)
    # elbow cop (hiji-gane)
    cp_c = E + out * 0.041 + V((0, 0.0, -0.005))
    dome = lathe([(0.0, 0.016), (0.012, 0.014), (0.024, 0.009), (0.032, 0.003), (0.035, 0.0), (0.0, 0.0)], 24)
    dome.transform(look_matrix(cp_c, out, ax))
    cop.add(dome)
    rim = torus_md(0.034, 0.0028, 32, 6)
    rim.transform(look_matrix(cp_c, out, ax))
    gold.add(rim)
    boss = uv_sphere(0.006, 10, 6)
    boss.transform(look_matrix(cp_c + out * 0.016, out, ax))
    gold.add(boss)
    # elbow tie cords
    red.add(bow_knot(cp_c + out * 0.006 - ax * 0.035, out, ax, 0.014, 0.04, 0.0024))

    # glove + tekko
    hand = build_hand()
    plate, ptrim = build_tekko()
    d = (Wr - E).normalized()
    d = (d + V((0, 0, -1)) * 0.6).normalized()
    zh = -d
    xh = V((1, 0.05, -0.05))
    xh = (xh - zh * xh.dot(zh)).normalized()
    yh = zh.cross(xh)
    mh = Matrix((xh, yh, zh)).transposed().to_4x4()
    mh.translation = Wr + d * 0.008
    glove.add(hand.transform(mh))
    tekko.add(plate.transform(mh))
    tekko.add(FINGER_PLATES.copy().transform(mh))
    tekko_gold.add(ptrim.transform(mh))

    for name, md, mat, sub in (("Arm_Sleeves", sleeve, M["cloth_sleeve"], 2), ("Arm_Forearm_Sleeves", forearm, M["cloth"], 1),
                               ("Kote_Bracers", bracer, M["lacquer_bracer"], 3), ("Kote_Gold", gold, M["gold"], 0),
                               ("Kote_Straps", straps, M["leather"], 1), ("Kote_Elbow_Cops", cop, M["lacquer"], 2),
                               ("Gloves", glove, M["leather_dark"], 2), ("Gloves_Tekko", tekko, M["lacquer"], 1),
                               ("Gloves_Tekko_Trim", tekko_gold, M["gold"], 0), ("Arm_Red_Ties", red, M["cord_red"], 0)):
        ob = to_obj(name, both(md), mat, coll, parent=root)
        if name in ("Arm_Sleeves", "Arm_Forearm_Sleeves"):
            cloth_mods(ob, sub, [(0.003, 0.012, {"stretch": (8, 8, 1)})])
            continue
        if name in ("Kote_Bracers", "Gloves_Tekko"):
            mod_solidify(ob, 0.0035, -1.0)
        if sub:
            mod_subsurf(ob, 1, sub)


# =============================================================================
# LEGS: pelvis, baggy pants, gaiters, suneate splints, knee plates, red ties, boots
# =============================================================================
TOE_OUT = deg(15)


def foot_frame():
    F = V((math.sin(TOE_OUT), -math.cos(TOE_OUT), 0))
    Sd = V((-F.y, F.x, 0))
    return F, Sd


BOOT = [(-0.085, 0.026, 0.072), (-0.075, 0.040, 0.102), (-0.050, 0.047, 0.124), (-0.010, 0.049, 0.132),
        (0.030, 0.051, 0.116), (0.075, 0.055, 0.092), (0.120, 0.057, 0.074), (0.160, 0.055, 0.062),
        (0.192, 0.049, 0.054), (0.210, 0.036, 0.047), (0.220, 0.017, 0.041)]


def boot_pt(s, phi, extra=0.0):
    F, Sd = foot_frame()
    hw, top = interp_smooth(BOOT, s)
    zb = 0.020
    zc = (top + zb) / 2
    hh = (top - zb) / 2
    e = 2.4
    c, si = math.cos(phi), math.sin(phi)
    w = math.copysign(abs(c) ** (2 / e), c) * (hw + extra)
    h = math.copysign(abs(si) ** (2 / e), si) * (hh + extra)
    base = V((ANKLE.x, ANKLE.y, 0.0)) + F * s
    return base + Sd * w + V((0, 0, zc + h))


def boot_center(s):
    F, Sd = foot_frame()
    hw, top = interp_smooth(BOOT, s)
    return V((ANKLE.x, ANKLE.y, 0.0)) + F * s + V((0, 0, (top + 0.020) / 2))


def build_legs(coll, root):
    pants = MD()
    gaiter = MD()
    splints = MD()
    gold = MD()
    gold_dk = MD()
    red = MD()
    kneep = MD()
    boots = MD()
    soles = MD()
    kogake = MD()
    cords_dark = MD()
    tatters = MD()

    # pelvis bulb (under skirts)
    def pel(u, v, i, j):
        z = lerp(1.03, 0.80, v)
        rx = lerp(0.175, 0.13, v ** 2)
        ry = lerp(0.135, 0.11, v ** 2)
        return V((math.sin(u) * rx, -math.cos(u) * ry, z))

    pants.add(grid(pel, lin(0, TAU, 32), lin(0, 1, 10), closed_u=True))

    # baggy pants leg along hip -> knee -> tuck
    kdir = (ANKLE - KNEE).normalized()
    path = catmull_path([HIP + V((0, 0, 0.06)), HIP, (HIP + KNEE) / 2 + V((0.01, -0.01, 0)), KNEE,
                         KNEE + kdir * 0.105], 6)

    def r_pant(t, th):
        base = interp_smooth([(0.0, 0.105), (0.15, 0.112), (0.45, 0.118), (0.62, 0.122), (0.75, 0.127),
                              (0.86, 0.130), (0.94, 0.120), (1.0, 0.066)], t)[0]
        stack = smooth((t - 0.72) / 0.16)  # bloused over the gaiter tie
        ring_ = math.sin(TAU * 8.5 * t + 1.3 * math.sin(th * 2 + 0.5) + 0.7 * math.sin(th * 3 + 1.1))
        folds = 0.013 * stack * max(0.0, ring_) ** 1.5 - 0.004 * stack
        grav = math.exp(-(math.sin(th * 2.5 + 0.35 * t + 0.4) ** 2) / 0.06)  # ~5 long folds from the hip
        folds += 0.011 * smooth((t - 0.08) / 0.25) * (1.0 - stack) * grav
        folds += 0.004 * math.sin(th * 11 + t * 31) * (0.3 + t) + \
            0.003 * fbm(V((math.cos(th) * 2.5, math.sin(th) * 2.5, t * 30)))
        # slimmer front-to-back than side-to-side (th = 0 points forward)
        squash = 1.0 - 0.10 * math.cos(th) ** 2 * smooth((t - 0.1) / 0.3)
        return (base + folds) * squash

    pants.add(limb(path, r_pant, 72, nt=96, ref=(0, -1, 0)))

    # gaiter (kyahan) along knee->ankle
    g0 = KNEE + kdir * 0.075
    g1 = V((ANKLE.x, ANKLE.y + 0.002, 0.088))

    def r_gai(t, th):
        base = interp_smooth([(0.0, 0.064), (0.25, 0.066), (0.55, 0.058), (0.85, 0.047), (1.0, 0.045)], t)[0]
        return base + 0.0018 * math.sin(th * 8 + t * 20) + 0.0015 * math.sin(t * 90)

    gaiter.add(limb([g0, g1], r_gai, 32, nt=24, ref=(0, -1, 0)))
    # suneate splints over the front of the shin
    sp0 = KNEE + kdir * 0.065
    sp1 = ANKLE + kdir * -0.040
    ax, fwd, sd = arm_axis_frame(sp0, sp1, (0, -1, 0))

    def r_spl(t, th):
        return r_gai(lerp(0.12, 0.85, t), th) + 0.008 + 0.004 * math.cos(th * 3)

    for c, hw in ((-50, 19), (0, 23), (50, 19)):
        a0, a1 = deg(c - hw), deg(c + hw)
        splints.add(limb([sp0, sp1], r_spl, 10, nt=18, ref=(0, -1, 0), th0=a0, th1=a1, uv_flip=True))

        def sp_pt(t, th, extra=0.0):
            cc = sp0.lerp(sp1, t)
            return cc + (fwd * math.cos(th) + sd * math.sin(th)) * (r_spl(t, th) + extra)

        border = [sp_pt(0, lerp(a0, a1, k / 8), 0.002) for k in range(9)] + \
                 [sp_pt(k / 12, a1, 0.002) for k in range(1, 13)] + \
                 [sp_pt(1, lerp(a1, a0, k / 8), 0.002) for k in range(1, 9)] + \
                 [sp_pt(1 - k / 12, a0, 0.002) for k in range(1, 12)]
        gold_dk.add(sweep(border, circle_profile(0.0017, 6), closed_path=True,
                          up=lambda i, p, cc=sp0: V((0, 0, 1))))
        for t in (0.08, 0.5, 0.92):
            s = uv_sphere(0.0026, 8, 5)
            s.translate(sp_pt(t, deg(c) + deg(hw - 5), 0.004))
            gold.add(s)
            s = uv_sphere(0.0026, 8, 5)
            s.translate(sp_pt(t, deg(c) - deg(hw - 5), 0.004))
            gold.add(s)
    # chain mail between the splints
    mail = limb([sp0 + ax * 0.005, sp1 - ax * 0.005], lambda t, th: r_spl(t, th) - 0.0035, 40, nt=16, ref=(0, -1, 0),
                th0=deg(-92), th1=deg(92))
    # knee plate (tate-age) with flower crest
    kc = KNEE + kdir * 0.125 + V((0, -0.090, 0))

    def knee_fn(u, v, i, j):
        x = lerp(-0.040, 0.040, u)
        z = lerp(-0.035, 0.045, v)
        w = 1 - 0.25 * (z / 0.045) ** 2 if z > 0 else 1
        x *= w
        y = 0.016 * (x / 0.04) ** 2 + 0.010 * (z / 0.045) ** 2
        return kc + V((x, y, z))

    kneep.add(grid(knee_fn, lin(0, 1, 14), lin(0, 1, 14)))
    border = [knee_fn(k / 14, 0, 0, 0) for k in range(15)] + [knee_fn(1, k / 14, 0, 0) for k in range(1, 15)] + \
             [knee_fn(1 - k / 14, 1, 0, 0) for k in range(1, 15)] + [knee_fn(0, 1 - k / 14, 0, 0) for k in range(1, 14)]
    gold.add(sweep([p + V((0, -0.002, 0)) for p in border], circle_profile(0.0028, 6), closed_path=True,
                   up=(0, -1, 0)))

    def crest_fn(u, v, i, j):
        p = knee_fn(lerp(0.27, 0.73, u), lerp(0.30, 0.70, v), 0, 0)
        return p + V((0, -0.0025, 0))

    knee_crest = grid(crest_fn, lin(0, 1, 10), lin(0, 1, 10))
    # red ties at top and ankle
    for zt, rr, side_a in ((0.385, 0.070, 38), (0.142, 0.055, 40)):
        t = (KNEE.z - zt) / (KNEE.z - ANKLE.z)
        cc = KNEE.lerp(ANKLE, t)
        ring = []
        for k in range(48):
            a = TAU * k / 48
            ring.append(cc + (fwd * math.cos(a) + sd * math.sin(a)) * (rr + 0.002 * math.sin(a * 6)))
        red.add(sweep(ring, circle_profile(0.0034, 6), closed_path=True, up=(0, 0, 1)))
        ring2 = [p + V((0, 0, -0.008)) for p in ring]
        red.add(sweep(ring2, circle_profile(0.0030, 6), closed_path=True, up=(0, 0, 1)))
        a = deg(side_a)
        bpos = cc + (fwd * math.cos(a) + sd * math.sin(a)) * (rr + 0.004)
        red.add(bow_knot(bpos, (bpos - cc), (0, 0, -1), 0.030, 0.11 if zt > 0.3 else 0.07, 0.0034))
        # a second, criss-crossing wrap below the knot
        for q in range(2):
            cr_pts = []
            for k in range(25):
                a2 = deg(lerp(-80, 80, k / 24))
                zz = (0.012 if q == 0 else -0.012) * (k / 24 - 0.5) * 2
                cr_pts.append(cc + (fwd * math.cos(a2) + sd * math.sin(a2)) * (rr + 0.003) + V((0, 0, -0.016 + zz)))
            red.add(tube(cr_pts, 0.0028, 6))
    # tattered strips over the outer shin
    for k, (a, L) in enumerate(((70, 0.22), (95, 0.18), (115, 0.25))):
        aa = deg(a)
        top = KNEE + (fwd * math.cos(aa) + sd * math.sin(aa)) * 0.10 + V((0, 0, 0.02))
        nrm = (fwd * math.cos(aa) + sd * math.sin(aa))
        tang = V((0, 0, 1)).cross(nrm).normalized()
        lens = [L * (1 - t_) for t_ in torn_profile(10, 0.25, k, deep=1, tongues=0)]

        def tf(u, v, i, j, top=top, nrm=nrm, tang=tang, lens=lens):
            w = 0.040
            p = top + tang * lerp(-w / 2, w / 2, u) + V((0, 0, -v * lens[i]))
            # follow the leg surface
            p += nrm * (-0.035 * v + 0.004 * math.sin(v * 12 + u * 4))
            return p

        tatters.add(grid(tf, lin(0, 1, 10), lin(0, 1, 10)))

    # boots
    def bfn(u, v, i, j):
        return boot_pt(v, u)

    boots.add(grid(bfn, lin(0, TAU, 32), lin(-0.083, 0.216, 30), closed_u=True))
    # shaft / cuff around the ankle
    # (no boot shaft: the gaiter tapers into a low tabi boot, as in the concept)
    # sole (waraji)
    def sole_fn(u, v, i, j):
        p = boot_pt(v, u, 0.008)
        q = V((p.x, p.y, 0.0))
        return q + V((0, 0, 0.0 if math.sin(u) < 0 else 0.015))

    F, Sd = foot_frame()
    outline = [boot_pt(s, 0, 0.007) for s in lin(-0.083, 0.216, 20)] + \
              [boot_pt(s, math.pi, 0.007) for s in lin(0.216, -0.083, 20)]
    outline = [V((p.x, p.y, 0.0)) for p in outline]
    c = sum(outline, V()) / len(outline)
    sole = MD()
    for z0, z1 in ((0.0, 0.015),):
        top = [p + V((0, 0, z1)) for p in outline]
        bot = [p + V((0, 0, z0)) for p in outline]
        n = len(outline)
        base = len(sole.v)
        sole.v.extend(top + bot + [c + V((0, 0, z1)), c + V((0, 0, z0))])
        for k in range(n):
            k2 = (k + 1) % n
            sole.f.append((base + k, base + k2, base + n + k2, base + n + k))
            sole.uv.append([(k / n, 1), ((k + 1) / n, 1), ((k + 1) / n, 0), (k / n, 0)])
            sole.f.append((base + 2 * n, base + k2, base + k))
            sole.uv.append([(0.5, 0.5), (k2 / n, 1), (k / n, 1)])
            sole.f.append((base + 2 * n + 1, base + n + k, base + n + k2))
            sole.uv.append([(0.5, 0.5), (k / n, 0), (k2 / n, 0)])
        sole.mi.extend([0] * (3 * n))
    soles.add(sole)
    # kogake: overlapping plates over the instep
    for k, (s0, s1) in enumerate(((0.000, 0.070), (0.055, 0.120), (0.105, 0.175))):
        def kf(u, v, i, j, s0=s0, s1=s1, k=k):
            s = lerp(s1, s0, v)
            phi = lerp(deg(25), deg(155), u)
            return boot_pt(s, phi, 0.005 + 0.003 * k + 0.004 * v)

        kogake.add(grid(kf, lin(0, 1, 14), lin(0, 1, 6)))
        edge = [kf(q / 14, 0.0, 0, 0) for q in range(15)]
        gold.add(tube(edge, 0.0026, 6))
        for q in (0.0, 1.0):
            gold.add(tube([kf(q, v / 6, 0, 0) for v in range(7)], 0.0022, 6))
    # sandal straps (dark cords): toe thong + crossing over instep + around heel
    toe = boot_pt(0.17, deg(90), 0.004)
    for sgn in (-1, 1):
        sidept = boot_pt(0.06, deg(90 - sgn * 85), 0.004)
        heel = boot_pt(-0.07, deg(90 - sgn * 70), 0.004)
        cords_dark.add(tube(catmull_path([toe, boot_pt(0.11, deg(90 - sgn * 45), 0.006), sidept,
                                          boot_pt(-0.01, deg(90 - sgn * 80), 0.005), heel], 4), 0.0035, 6))
    # leather straps with gilt buckles around the instep and heel
    straps_b = MD()
    for sc_, w_ in ((0.012, 0.022), (0.085, 0.018), (-0.045, 0.024)):
        ring = [boot_pt(sc_, ph, 0.005) for ph in lin(0, TAU, 33)[:-1]]
        straps_b.add(sweep(ring, rect_profile(0.0045, w_, 1), closed_path=True,
                           up=lambda i, p, c=boot_center(sc_): p - c))
        bp = boot_pt(sc_, deg(20), 0.009)
        n_ = (bp - boot_center(sc_)).normalized()
        bk = box(0.006, 0.020, w_ + 0.006)
        bk.transform(look_matrix(bp, n_, (0, 0, 1)))
        gold.add(bk)
        for ph in (deg(60), deg(100), deg(140)):
            st = uv_sphere(0.0028, 8, 5)
            st.translate(boot_pt(sc_, ph, 0.0095))
            gold.add(st)
    # lacquered toe cap
    def toe_fn(u, v, i, j):
        sx = lerp(0.150, 0.214, v)
        phi = lerp(deg(15), deg(165), u)
        return boot_pt(sx, phi, 0.005)

    kogake.add(grid(toe_fn, lin(0, 1, 14), lin(0, 1, 6)))
    gold.add(tube([toe_fn(q / 14, 0.0, 0, 0) for q in range(15)], 0.0024, 6))
    for name, md, mat, sub, solid in (
            ("Pants_Hakama", pants, M["cloth_pants"], 2, 0), ("Gaiters_Kyahan", gaiter, M["cloth"], 1, 0),
            ("Suneate_Chainmail", mail, M["mail"], 0, 0), ("Suneate_Borders", gold_dk, M["gold_dark"], 0, 0),
            ("Suneate_Splints", splints, M["lacquer_suneate"], 3, 0.004), ("Suneate_Gold", gold, M["gold"], 0, 0),
            ("Leg_Red_Ties", red, M["cord_red"], 0, 0), ("Knee_Plates", kneep, M["lacquer"], 1, 0.004),
            ("Boots", boots, M["boot"], 2, 0), ("Sandal_Soles", soles, M["straw"], 0, 0),
            ("Kogake_Foot_Plates", kogake, M["lacquer"], 1, 0.003), ("Sandal_Cords", cords_dark, M["cord_dark"], 0, 0),
            ("Shin_Tatters", tatters, M["cloth"], 1, 0.002), ("Boot_Straps", straps_b, M["leather"], 1, 0)):
        ob = to_obj(name, both(md), mat, coll, parent=root)
        if name == "Pants_Hakama":
            cloth_mods(ob, sub, [(0.004, 0.018, {"stretch": (1, 1, 4), "hard": True}),
                                 (0.0025, 0.010, {"stretch": (8, 8, 1)})])
            continue
        if name == "Gaiters_Kyahan":
            cloth_mods(ob, sub, [(0.0015, 0.008, {"stretch": (8, 8, 1)})])
            continue
        if name == "Shin_Tatters":
            cloth_mods(ob, sub, [(0.003, 0.012, {"stretch": (1, 1, 4), "hard": True})], solid, -1.0)
            continue
        if solid:
            mod_solidify(ob, solid, -1.0)
        if sub:
            mod_subsurf(ob, 1, sub)
    to_obj("Knee_Mon", both(knee_crest), M["decal_mon_flower"], coll, parent=root)
