"""Arm gear (measured from the concept): bellows pockets on the lateral upper arms with the subdued flag patches on
their flaps and a round PVC emblem below, glossy hard elbow pads, two-band rubberised wrist gauntlets with back ribs
and buckles, the wrist computer with its HUD on the LEFT wrist, and the small unlit module on the RIGHT wrist."""
import math

from mathutils import Matrix

import seal_lib as L
from seal_lib import (MD, TAU, V, box, grid, interp_smooth, lathe, lerp, lin, look_matrix, mod_bevel, mod_solidify,
                      mod_subsurf, rect_profile, smooth, sweep, to_obj, torus_md, tube, uv_sphere)
from seal_mats import M
import seal_body as B


def arm_t_at_z(path, z):
    for k in range(len(path) - 1):
        if (path[k].z - z) * (path[k + 1].z - z) <= 0:
            f = (path[k].z - z) / (path[k].z - path[k + 1].z + 1e-9)
            return (k + f) / (len(path) - 1)
    return 0.2


def arm_surface(side, y, z, off=0.003):
    """Point on the outer (lateral) sleeve surface at world (y, z): the arm section's circle crossing at that y."""
    path = B.arm_path(side)
    t = arm_t_at_z(path, z)
    c, T, N, Bv = B.limb_frame(path, t)
    r = B.arm_radius(t, -side * math.pi / 2)
    dy = y - c.y
    x = c.x + side * math.sqrt(max(0.0, r * r - dy * dy))
    return V((x + side * off, y, z))


def ring_on_arm(path, t0, t1, rfun, nu=36, nv=6):
    """Band around the arm between path fractions t0..t1 with radius rfun(t, u) (u = 0 front)."""
    sub = [B.limb_frame(path, lerp(t0, t1, k / nv))[0] for k in range(nv + 1)]
    return L.limb(sub, lambda tt, u: rfun(lerp(t0, t1, tt), u), nu)


def build(coll, root):
    pockets, flaps, flags, pvc, pads, gaunt, hw, comp, bezel = (MD() for _ in range(9))
    screen = MD()
    for s in (1, -1):
        path = B.arm_path(s)
        # ---------------------------------------------------------- bellows pocket (body) + flap with the flag
        cy = 0.020

        def body(u, v, i, j):
            y = cy + lerp(-0.055, 0.055, u) * (1 if s > 0 else -1)
            z = lerp(1.290, 1.380, v)
            bul = (1 - (2 * u - 1) ** 4) * (1 - (2 * v - 1) ** 4)
            return arm_surface(s, y, z, 0.004 + 0.014 * bul)

        pockets.add(grid(body, lin(0, 1, 12), lin(0, 1, 10)))

        def flap(u, v, i, j, off=0.0):
            y = cy + lerp(-0.057, 0.057, u) * (1 if s > 0 else -1)
            z = lerp(1.372, 1.468, v)
            return arm_surface(s, y, z, 0.019 + off - 0.010 * smooth((v - 0.75) / 0.25))

        flaps.add(grid(flap, lin(0, 1, 12), lin(0, 1, 10)))
        # flag: canton at the image's upper-left in both side views (front on the left arm, back on the right)
        fg = grid(lambda u, v, i, j: arm_surface(s, cy + lerp(-0.050, 0.050, u) * (1 if s > 0 else -1),
                                                 lerp(1.390, 1.455, v), 0.0235 - 0.006 * smooth((v - 0.85) / 0.15)),
                  lin(0, 1, 14), lin(0, 1, 8))
        if s < 0:
            fg.uv = [[(1 - a, b) for a, b in f] for f in fg.uv]
        flags.add(fg)
        # round PVC emblem with two light eye dots and an X ridge
        c = arm_surface(s, cy, 1.335, 0.021)
        n = V((s, 0.08 * s, 0.0)).normalized()
        pvc.add(lathe([(0.0, 0.0), (0.025, 0.0), (0.025, 0.002), (0.022, 0.003), (0.0, 0.0032)], 28)
                .transform(look_matrix(c, n, (0, 0, 1))))
        for dy in (-0.010, 0.010):
            hw.add(uv_sphere(0.003, 8, 5).translate(c + n * 0.0035 + V((0, dy, 0.004))))
        for a_ in (0.7, -0.7):
            pvc.add(L.box(0.002, 0.030, 0.0025).transform(look_matrix(c + n * 0.003 + V((0, 0.006 * s, -0.008)), n,
                                                                         (0, math.sin(a_), math.cos(a_)))))

        # ---------------------------------------------------------- elbow pad (shield dome on the back-outer elbow)
        te = arm_t_at_z(path, 1.170)
        ce, T, N, Bv = B.limb_frame(path, te)
        nrm = V((s * 0.40, 0.92, 0.0)).normalized()
        axis = T.normalized()
        side_v = axis.cross(nrm).normalized()
        r0 = 0.066

        def pad(u, v, i, j):
            # u across (-1..1, 0.093 wide), v along the arm (-1..1, 0.15 tall), superellipse footprint
            w = 0.0465 * (1.0 + 0.10 * v)
            e = 3.0
            k = (abs(u) ** e + abs(v) ** e)
            dome = 0.022 * max(0.0, 1 - min(1.0, k)) ** 0.5 + 0.003
            ang = u * w / r0
            return ce + axis * (-v * 0.075) + (nrm * math.cos(ang) + side_v * math.sin(ang)) * (r0 + dome)

        pm = grid(pad, lin(-1, 1, 14), lin(-1, 1, 18),
                  keep=lambda i, j: (abs(i - 7) / 7.0) ** 3 + (abs(j - 9) / 9.0) ** 3 <= 1.15)
        pads.add(pm)
        rim = [pad(math.cos(a) * 0.98, math.sin(a) * 0.98, 0, 0) for a in lin(0, TAU, 40)[:-1]]
        hw.add(tube(rim, 0.0018, 6, closed=True))

        # ---------------------------------------------------------- wrist gauntlet: upper band, groove, lower strap
        tw0 = arm_t_at_z(path, 1.040)
        tw1 = 1.0

        def gr(t, u, lo, hi, extra):
            f = (t - lo) / max(1e-6, hi - lo)
            edge = smooth(min(f, 1 - f) / 0.15)
            a, b = 0.050 + 0.006, 0.058 + 0.006
            cu, su = math.cos(u), math.sin(u)
            r = a * b / math.sqrt((b * cu) ** 2 + (a * su) ** 2)
            return r * (0.93 + 0.07 * edge) + extra

        tm = lerp(tw0, tw1, 0.52)
        tg = lerp(tw0, tw1, 0.60)
        gaunt.add(ring_on_arm(path, tw0, tm, lambda t, u: gr(t, u, tw0, tm, 0.0)))
        gaunt.add(ring_on_arm(path, tg, lerp(tw0, tw1, 0.90), lambda t, u: gr(t, u, tg, lerp(tw0, tw1, 0.90), -0.002)))
        for k in range(4):  # ribs on the back of the upper band
            tk = lerp(tw0, tm, 0.2 + 0.2 * k)
            ck, Tk, Nk, Bk = B.limb_frame(path, tk)
            arc = [ck + (Nk * math.cos(u) + Bk * math.sin(u)) * (gr(tk, u, tw0, tm, 0.003))
                   for u in lin(math.radians(110), math.radians(250), 12)]
            gaunt.add(tube(arc, 0.0018, 5))
        # buckle on the lower strap's outer face
        tb_ = lerp(tw0, tw1, 0.75)
        cb_, Tb, Nb, Bb = B.limb_frame(path, tb_)
        outv = (Bb * (-s)).normalized()
        hw.add(L.box(0.018, 0.014, 0.004).transform(look_matrix(cb_ + outv * 0.060, outv, Tb)))

        # ---------------------------------------------------------- wrist computer (left) / small module (right)
        tc_ = lerp(tw0, tw1, 0.40)
        cc, Tc, Nc, Bc = B.limb_frame(path, tc_)
        face_n = V((s * 0.95, -0.30, 0.10)).normalized()
        along = (Tc - face_n * Tc.dot(face_n)).normalized()
        if s > 0:
            base = cc + face_n * 0.058
            m = Matrix((along, face_n.cross(along).normalized() * -1, face_n)).transposed().to_4x4()
            m = look_matrix(base, face_n, along)
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
            for tt, wdt in ((tc_, 0.035), (lerp(tw0, tw1, 0.05) - 0.02, 0.025)):
                c2, T2, N2, B2 = B.limb_frame(path, tt)
                ring = [c2 + (N2 * math.cos(u) + B2 * math.sin(u)) * (gr(tt, u, tw0, tm, 0.003))
                        for u in lin(0, TAU, 37)[:-1]]
                gaunt.add(sweep(ring, rect_profile(0.004, wdt), closed_path=True, up=lambda i, p, c2=c2: p - c2))
            c2, T2, N2, B2 = B.limb_frame(path, lerp(tw0, tw1, 0.05) - 0.02)
            o2 = (B2 * -1).normalized()
            hw.add(lathe([(0.0, 0.0), (0.004, 0.0), (0.004, 0.003), (0.0, 0.004)], 12)
                   .transform(look_matrix(c2 + o2 * 0.066, o2)))
            hw.add(L.box(0.020, 0.012, 0.004).transform(look_matrix(c2 + o2 * 0.065 + V((0, -0.02, 0)), o2, T2)))
        else:
            m = look_matrix(cc + face_n * 0.060, face_n, along)
            comp.add(L.box(0.040, 0.055, 0.014).transform(m @ Matrix.Translation((0, 0, 0.007))))
            bezel.add(L.box(0.034, 0.049, 0.002).transform(m @ Matrix.Translation((0, 0, 0.0145))))

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
