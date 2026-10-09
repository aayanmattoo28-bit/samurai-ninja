"""Arm gear (measured from the concept): bellows pockets on the lateral upper arms with the subdued flag patches on
their flaps and a round PVC emblem below, glossy hard elbow pads, two-band rubberised wrist gauntlets with back ribs
and buckles, the wrist computer with its HUD on the LEFT wrist, the small unlit module on the RIGHT wrist, and the
sleeve seams (raglan, back of the arm, spiral forearm panel).  Everything sits on the sleeve envelope
B.arm_shape() so it follows the anatomy of the arms."""
import math

from mathutils import Matrix

import seal_lib as L
from seal_lib import (MD, TAU, V, grid, interp_smooth, lathe, lerp, lin, look_matrix, mod_bevel, mod_solidify,
                      mod_subsurf, rect_profile, smooth, sweep, to_obj, tube, uv_sphere)
from seal_mats import M
import seal_body as B


def arm_t_at_z(path, z):
    for k in range(len(path) - 1):
        if (path[k].z - z) * (path[k + 1].z - z) <= 0:
            f = (path[k].z - z) / (path[k].z - path[k + 1].z + 1e-9)
            return (k + f) / (len(path) - 1)
    return 0.2


def shape_fn(side):
    return lambda t, u: B.arm_shape(t, u, side)


def lat_u(side, phi=0.0):
    """Limb angle of the arm's lateral midline turned phi radians toward the back (negative = toward the front)."""
    return -side * (math.pi / 2 + phi)


def on_arm(side, path, t, d, off):
    """Point and radial direction on the outer face of the sleeve envelope at path fraction t, d metres behind the
    lateral midline (negative = in front), lifted `off` off the surface: d is measured like a side-view y."""
    c, T, N, Bv = B.limb_frame(path, t)
    a = interp_smooth(B.ARM_DEPTH, t)[0]
    b = interp_smooth(B.ARM_WIDTH, t)[0]
    bc = b * math.sqrt(max(0.0, 1.0 - (d / a) ** 2))
    u = math.atan2(-side * bc, -d)
    dr = N * math.cos(u) + Bv * math.sin(u)
    return c + dr * (B.arm_shape(t, u, side) + off), dr


def t_at_surface_z(side, path, z, d=0.0):
    """Path fraction whose lateral surface point (not the axis) is at height z."""
    ts = lin(0.08, 0.95, 120)
    zs = [on_arm(side, path, t, d, 0.0)[0].z for t in ts]
    for k in range(len(ts) - 1):
        if (zs[k] - z) * (zs[k + 1] - z) <= 0:
            return lerp(ts[k], ts[k + 1], (zs[k] - z) / (zs[k] - zs[k + 1] + 1e-9))
    return arm_t_at_z(path, z)


def ring_on_arm(path, t0, t1, rfun, nu=36, nv=6):
    """Band around the arm between path fractions t0..t1 with radius rfun(t, u) (u = 0 front)."""
    sub = [B.limb_frame(path, lerp(t0, t1, k / nv))[0] for k in range(nv + 1)]
    return L.limb(sub, lambda tt, u: rfun(lerp(t0, t1, tt), u), nu)


def cuff_clear(hm, c, dr, rc=0.0505, top=0.052):
    """Distance along dr from c at which the ray leaves the glove cuff (wrist frame hm: a cylinder of radius rc
    reaching `top` up the wrist axis), faded out above the cuff."""
    h = hm.col[2].xyz.normalized()
    w = c - hm.translation
    p, q = dr - h * dr.dot(h), w - h * w.dot(h)
    A, Bq, C = p.dot(p), 2 * p.dot(q), q.dot(q) - rc * rc
    disc = Bq * Bq - 4 * A * C
    if A < 1e-9 or disc < 0:
        return 0.0
    rho = (-Bq + math.sqrt(disc)) / (2 * A)
    return rho * smooth((top + 0.012 - (w + dr * rho).dot(h)) / 0.012)


def build(coll, root):
    pockets, flaps, flags, pvc, pads, gaunt, hw, comp, bezel = (MD() for _ in range(9))
    screen, seams = MD(), MD()
    for s in (1, -1):
        path = B.arm_path(s)
        shp = shape_fn(s)
        # ---------------------------------------------------------- bellows pocket (body) + flap with the flag
        # lateral face, centred 2 cm behind the arm axis line of the side views; grid u runs front->back on the
        # left arm and back->front on the right one (keeps the flag's canton at the image's upper-left in both)
        tz = {z: t_at_surface_z(s, path, z) for z in (1.285, 1.330, 1.375, 1.378, 1.443, 1.368, 1.453)}

        def body(u, v, i, j):
            d = lerp(-0.046, 0.064, u) * s
            t = lerp(tz[1.285], tz[1.375], v)
            bul = (1 - (2 * u - 1) ** 4) * (1 - (2 * v - 1) ** 4)
            return on_arm(s, path, t, d, 0.004 + 0.010 * bul)[0]

        pockets.add(grid(body, lin(0, 1, 12), lin(0, 1, 10)))

        def flap(u, v, i, j):
            d = lerp(-0.047, 0.065, u) * s
            t = lerp(tz[1.368], tz[1.453], v)
            return on_arm(s, path, t, d, 0.0125 - 0.006 * smooth((v - 0.75) / 0.25))[0]

        flaps.add(grid(flap, lin(0, 1, 12), lin(0, 1, 10)))
        fg = grid(lambda u, v, i, j: on_arm(s, path, lerp(tz[1.378], tz[1.443], v), lerp(-0.031, 0.049, u) * s,
                                            0.0155 - 0.004 * smooth((v - 0.85) / 0.15))[0],
                  lin(0, 1, 14), lin(0, 1, 8))
        if s < 0:
            fg.uv = [[(1 - a, b) for a, b in f] for f in fg.uv]
        flags.add(fg)
        # round PVC emblem with two light eye dots and an X ridge
        c, n = on_arm(s, path, tz[1.330], 0.009, 0.0140)
        up = (path[0] - path[-1])
        up = (up - n * up.dot(n)).normalized()
        fb = up.cross(n).normalized()
        pvc.add(lathe([(0.0, 0.0), (0.025, 0.0), (0.025, 0.002), (0.022, 0.003), (0.0, 0.0032)], 28)
                .transform(look_matrix(c, n, up)))
        for dy in (-0.010, 0.010):
            hw.add(uv_sphere(0.003, 8, 5).translate(c + n * 0.0035 + fb * dy + up * 0.004))
        for a_ in (0.7, -0.7):
            pvc.add(L.box(0.002, 0.030, 0.0025).transform(look_matrix(c + n * 0.003 - fb * 0.006 * s - up * 0.008, n,
                                                                         up * math.cos(a_) + fb * math.sin(a_))))

        # ---------------------------------------------------------- elbow pad: hard shield over the olecranon,
        # bent round the elbow (its upper half follows the upper arm, the lower half the forearm)
        te = arm_t_at_z(path, B.arm_joints(s)[1].z)
        u_pad = math.pi + s * B.ELBOW_PAD_U           # back-outer face of the elbow
        ts_ = lin(te - 0.20, te + 0.20, 80)                      # surface arc length along the back of the elbow
        ps_ = [B.limb_pt(path, shp, t, u_pad) for t in ts_]
        arc = [0.0]
        for p0, p1 in zip(ps_, ps_[1:]):
            arc.append(arc[-1] + (p1 - p0).length)
        a_e = arc[40]

        def t_of_arc(x):
            for k in range(len(arc) - 1):
                if arc[k] <= x <= arc[k + 1]:
                    return lerp(ts_[k], ts_[k + 1], (x - arc[k]) / (arc[k + 1] - arc[k] + 1e-9))
            return ts_[-1] if x > arc[-1] else ts_[0]

        def pad_pt(u, v, lift=0.0):
            # u across (-1..1, ~0.093 wide, +1 = front edge), v along the arm (+1 = top, 0.14 tall); the strapped
            # rim presses into the sleeve (flat there, see B.arm_radius), the dome stands ~2 cm off it
            t = t_of_arc(a_e - v * 0.069 + 0.016)       # centred 1.6 cm below the elbow point
            k = abs(u) ** 3 + abs(v) ** 3
            dome = 0.0155 * max(0.0, 1 - min(1.0, k)) ** 0.45 + 0.002     # shell: flat crown, rolled edge
            ang = u * 0.049 * (1.0 + 0.10 * v) / 0.062
            return B.limb_pt(path, shp, t, u_pad + s * ang, 0.003 + dome + lift)

        pm = grid(lambda u, v, i, j: pad_pt(u, v), lin(-1, 1, 14), lin(-1, 1, 18),
                  keep=lambda i, j: (abs(i - 7) / 7.0) ** 3 + (abs(j - 9) / 9.0) ** 3 <= 1.15)
        pads.add(pm)
        rim = [pad_pt(math.cos(a) * 0.98, math.sin(a) * 0.98) for a in lin(0, TAU, 40)[:-1]]
        hw.add(tube(rim, 0.0018, 6, closed=True))
        for uk in lin(0.60, 0.84, 5):  # rubber flex ribs along the front edge
            gaunt.add(tube([pad_pt(uk, v, 0.0004) for v in lin(-0.5, 0.5, 9)], 0.0011, 5))

        # ---------------------------------------------------------- wrist gauntlet: upper band, groove, lower strap,
        # moulded to the tapering forearm and kept clear of the glove cuff that tucks under it
        hm = B.hand_matrix(s)
        tw0 = arm_t_at_z(path, 1.040)
        tw1 = 1.0

        def gr(t, u, lo, hi, extra):
            f = (t - lo) / max(1e-6, hi - lo)
            edge = smooth(min(f, 1 - f) / 0.15)
            c_, T_, N_, B_ = B.limb_frame(path, t)
            dr = N_ * math.cos(u) + B_ * math.sin(u)
            r = max(B.arm_shape(t, u, s) + 0.0085, cuff_clear(hm, c_, dr) + 0.004)
            return r - 0.0055 * (1 - edge) + extra

        tm = lerp(tw0, tw1, 0.52)
        tg = lerp(tw0, tw1, 0.60)
        tl = lerp(tw0, tw1, 0.90)
        gaunt.add(ring_on_arm(path, tw0, tm, lambda t, u: gr(t, u, tw0, tm, 0.0), 40, 8))
        gaunt.add(ring_on_arm(path, tg, tl, lambda t, u: gr(t, u, tg, tl, -0.002), 40, 6))
        gaunt.add(ring_on_arm(path, tm - 0.004, tg + 0.004, lambda t, u: gr(t, u, tw0, tl, -0.0045), 40, 3))  # groove
        for k in range(4):  # ribs on the back of the upper band
            tk = lerp(tw0, tm, 0.2 + 0.2 * k)
            ck, Tk, Nk, Bk = B.limb_frame(path, tk)
            arc_ = [ck + (Nk * math.cos(u) + Bk * math.sin(u)) * (gr(tk, u, tw0, tm, 0.0025))
                    for u in lin(math.radians(110), math.radians(250), 12)]
            gaunt.add(tube(arc_, 0.0018, 5))
        # buckle on the lower strap's outer face
        tb_ = lerp(tg, tl, 0.5)
        cb_, Tb, Nb, Bb = B.limb_frame(path, tb_)
        ub = lat_u(s)
        outv = Nb * math.cos(ub) + Bb * math.sin(ub)
        hw.add(L.box(0.018, 0.014, 0.004).transform(look_matrix(cb_ + outv * (gr(tb_, ub, tg, tl, -0.002) + 0.0015),
                                                                outv, Tb)))

        # ---------------------------------------------------------- wrist computer (left) / small module (right)
        tc_ = lerp(tw0, tw1, 0.40)
        cc, Tc, Nc, Bc = B.limb_frame(path, tc_)
        face_n = V((s * 0.95, -0.30, 0.10)).normalized()
        fp = face_n - Tc * face_n.dot(Tc)
        u_f = math.atan2(fp.dot(Bc), fp.dot(Nc))
        r_f = gr(tc_, u_f, tw0, tm, 0.0)
        along = (Tc - face_n * Tc.dot(face_n)).normalized()
        if s > 0:
            m = look_matrix(cc + face_n * (r_f + 0.0005), face_n, along)
            comp.add(L.box(0.058, 0.068, 0.017).transform(m @ Matrix.Translation((0, 0, 0.0085))))
            # bezel frame
            for (w, h, x, y) in ((0.058, 0.006, 0.0, 0.031), (0.058, 0.006, 0.0, -0.031), (0.006, 0.068, 0.026, 0.0),
                                 (0.006, 0.068, -0.026, 0.0)):
                bezel.add(L.box(w, h, 0.004).transform(m @ Matrix.Translation((x, y, 0.0185))))
            sc = grid(lambda u, v, i, j: m @ V((lerp(-0.021, 0.021, u), lerp(-0.026, 0.026, v), 0.0172)),
                      lin(0, 1, 2), lin(0, 1, 2))
            sc.uv = [[(1 - b, a) for a, b in f] for f in sc.uv]  # landscape along the forearm
            screen.add(sc)
            comp.add(L.box(0.050, 0.072, 0.006).transform(m @ Matrix.Translation((0, -0.012, -0.002))))  # mount plate
            for k in range(3):
                hw.add(L.box(0.030, 0.003, 0.002).transform(m @ Matrix.Translation((0, -0.040 - k * 0.006, 0.001))))
            # straps: main strap at the device, a narrower one toward the elbow with a snap and keeper
            t2 = tw0 - 0.014
            for tt, wdt, rf in ((tc_, 0.035, lambda u: gr(tc_, u, tw0, tm, 0.003)),
                                (t2, 0.025, lambda u: B.arm_shape(t2, u, s) + 0.0075)):
                c2, T2, N2, B2 = B.limb_frame(path, tt)
                ring = [c2 + (N2 * math.cos(u) + B2 * math.sin(u)) * rf(u) for u in lin(0, TAU, 37)[:-1]]
                gaunt.add(sweep(ring, rect_profile(wdt, 0.004), closed_path=True, up=lambda i, p, c2=c2: p - c2))
            c2, T2, N2, B2 = B.limb_frame(path, t2)
            u2 = lat_u(s)
            o2 = N2 * math.cos(u2) + B2 * math.sin(u2)
            r2 = B.arm_shape(t2, u2, s) + 0.0115
            hw.add(lathe([(0.0, 0.0), (0.004, 0.0), (0.004, 0.003), (0.0, 0.004)], 12)
                   .transform(look_matrix(c2 + o2 * r2, o2)))
            hw.add(L.box(0.020, 0.012, 0.004).transform(look_matrix(c2 + o2 * r2 + V((0, -0.02, 0)), o2, T2)))
        else:
            m = look_matrix(cc + face_n * (r_f + 0.0005), face_n, along)
            comp.add(L.box(0.040, 0.055, 0.014).transform(m @ Matrix.Translation((0, 0, 0.007))))
            bezel.add(L.box(0.034, 0.049, 0.002).transform(m @ Matrix.Translation((0, 0, 0.0145))))

        # ---------------------------------------------------------- welted seams on the sleeve fabric
        rad = lambda t, u, s=s: B.arm_radius(t, u, s)  # noqa: E731
        lines = []
        for k in (0, 1):  # raglan seams: from the yoke over the front / back of the shoulder into the armpit
            pts = []
            for t in lin(0.03, 0.28, 30):
                ul = lerp(-0.85, 0.20, smooth((t - 0.03) / 0.25))
                ul = ul if k == 0 else -math.pi - ul
                pts.append((t, ul * s))
            lines.append(pts)
        lines.append([(t, lat_u(s, 0.95)) for t in lin(0.24, 0.47, 24)])           # down the back of the arm
        lines.append([(t, lat_u(s, lerp(1.30, -1.25, (t - 0.70) / 0.105))) for t in lin(0.70, 0.805, 24)])  # spiral
        for pts in lines:
            seams.add(tube([B.limb_pt(path, rad, t, u, 0.0006) for t, u in pts], 0.0019, 6))

    ob = to_obj("Sleeve_Pockets", pockets, M["velcro"], coll, parent=root)
    mod_solidify(ob, 0.003, -1.0)
    ob = to_obj("Sleeve_Pocket_Flaps", flaps, M["suit_panel"], coll, parent=root)
    mod_solidify(ob, 0.004, -1.0)
    mod_subsurf(ob, 1, 1)
    to_obj("Flag_Patches", flags, M["patch_flag"], coll, parent=root)
    to_obj("Sleeve_PVC_Emblems", pvc, M["polymer"], coll, parent=root)
    ob = to_obj("Elbow_Pads", pads, M["pad_gloss"], coll, parent=root)
    mod_solidify(ob, 0.004, -1.0)
    mod_subsurf(ob, 1, 2)
    ob = to_obj("Wrist_Gauntlets", gaunt, M["gauntlet"], coll, parent=root)
    mod_subsurf(ob, 1, 1)
    to_obj("Arm_Hardware", hw, M["metal"], coll, parent=root)
    ob = to_obj("Wrist_Computer_Housing", comp, M["polymer_gloss"], coll, parent=root)
    mod_bevel(ob, 0.003, 2)
    ob = to_obj("Wrist_Computer_Bezel", bezel, M["bezel"], coll, parent=root)
    mod_bevel(ob, 0.0015, 2)
    to_obj("Wrist_Computer_Screen", screen, M["screen_hud"], coll, parent=root)
    to_obj("Sleeve_Seams", seams, M["suit_panel"], coll, parent=root)
