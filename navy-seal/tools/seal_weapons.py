"""Weapons and carried gear, built to the concept's gear cards and turnaround:
- the suppressed short carbine slung flat on the back (front end up at the left shoulder blade, stock at the right
  buttock), its back-panel retention bracket and handguard strap, and the light beaded carry strap;
- the compact 9mm in the right drop-leg holster (muzzle down, grip up and back);
- the tactical gear stowed in the pouches that suit each item's shape: dive knife (right calf sheath), flash-bang
  canister (left-hip pouch), frag canister (front-left corner pouch), folded recon drone (rear dump pouch), twin
  breaching charges (left drop-leg pouches, bead-chain leads hanging under the flaps), closed multi-tool (front-right
  teardrop sheath)."""
import math

from mathutils import Matrix

import seal_lib as L
from seal_lib import (MD, TAU, V, box, grid, lathe, lerp, lin, look_matrix, mod_bevel, rect_profile, sweep, to_obj,
                      torus_md, tube, uv_sphere)
from seal_mats import M, mat_metal, mat_nylon, mat_polymer, mat_screen


def ext(outline, w, y0=0.0):
    """Extrude a closed, star-shaped 2D outline [(x, z)] symmetrically to width w along local Y (centred on y0)."""
    md = MD()
    n = len(outline)
    a = [V((x, y0 + w / 2, z)) for x, z in outline]
    b = [V((x, y0 - w / 2, z)) for x, z in outline]
    md.v.extend(a + b)
    cx = sum(x for x, _ in outline) / n
    cz = sum(z for _, z in outline) / n
    md.v.extend([V((cx, y0 + w / 2, cz)), V((cx, y0 - w / 2, cz))])
    for k in range(n):
        k2 = (k + 1) % n
        md.f.append((k, n + k, n + k2, k2))
        md.uv.append([(k / n, 1), (k / n, 0), (k2 / n, 0), (k2 / n, 1)])
        md.f.append((2 * n, k, k2))
        md.uv.append([(0.5, 0.5), (0, 0), (1, 0)])
        md.f.append((2 * n + 1, n + k2, n + k))
        md.uv.append([(0.5, 0.5), (0, 0), (1, 0)])
    md.mi = [0] * len(md.f)
    return md


def _along_x(md):
    """Lathe meshes are built along +Z; turn them to run along +X."""
    return md.transform(Matrix(((0, 0, 1, 0), (0, 1, 0, 0), (-1, 0, 0, 0), (0, 0, 0, 1))))


def cyl_x(x0, x1, r, z=0.0, y=0.0, n=24, prof=None):
    """Closed cylinder (or lathe profile [(r, x)]) on the local X axis."""
    pr = prof or [(0.0, x0), (r, x0), (r, x1), (0.0, x1)]
    return _along_x(lathe([(rr, xx) for rr, xx in pr], n)).translate((0.0, y, z))


def cyl_y(x, z, r, w, n=16):
    return lathe([(0.0, -w / 2), (r, -w / 2), (r, w / 2), (0.0, w / 2)], n).transform(
        Matrix.Translation((x, 0.0, z)) @ Matrix.Rotation(math.pi / 2, 4, "X"))


def bx(x0, x1, z0, z1, w, y=0.0):
    return box(x1 - x0, w, z1 - z0).translate(((x0 + x1) / 2, y, (z0 + z1) / 2))


# --------------------------------------------------------------------------------------------------------------
def carbine_md():
    """Carbine prop in its own frame: +X along the bore to the front end, +Z toward the scope, +Y its left side;
    origin on the bore line at the receiver's rear face.  0.90 m from butt pad to muzzle.  {material key: MD}"""
    P = {k: MD() for k in ("metal", "polymer", "rail", "cap", "glass", "lamp")}
    Mt, Po, R = P["metal"], P["polymer"], P["rail"]
    # skeletal stock: butt pad, cheek bar, diagonal lower strut, sling cup; short tube with a ring
    Po.add(bx(-0.246, -0.227, -0.106, 0.030, 0.036))
    for k in range(6):                                                   # butt pad ribs
        Po.add(bx(-0.249, -0.246, -0.100 + k * 0.022, -0.092 + k * 0.022, 0.034))
    Po.add(bx(-0.246, -0.061, -0.018, 0.030, 0.030))
    Po.add(bx(-0.200, -0.110, 0.030, 0.038, 0.026))                      # cheek pad
    Po.add(ext([(-0.235, -0.112), (-0.226, -0.112), (-0.098, -0.031), (-0.098, -0.018), (-0.112, -0.018)], 0.020))
    Mt.add(cyl_y(-0.134, -0.059, 0.007, 0.028))
    Mt.add(cyl_x(-0.061, 0.0, 0.016))
    Mt.add(cyl_x(-0.008, 0.0, 0.019))
    # upper receiver with ejection port cover, forward assist, charging handle; top rail with 18 ridges
    Mt.add(bx(0.0, 0.242, -0.018, 0.049, 0.028))
    Mt.add(bx(0.085, 0.160, 0.000, 0.030, 0.003, y=-0.0155))            # port cover (right side, outward)
    Mt.add(cyl_x(0.0, 0.030, 0.008, z=0.026, y=-0.020).transform(Matrix.Translation((0.040, 0.0, 0.0))))
    Mt.add(bx(-0.012, 0.010, 0.040, 0.052, 0.040))                       # charging handle latch
    R.add(bx(0.004, 0.240, 0.049, 0.053, 0.022))
    for k in range(18):
        R.add(bx(0.008 + k * 0.0128, 0.0135 + k * 0.0128, 0.053, 0.057, 0.022))
    # lower receiver, magwell, loop guard + trigger, raked rear grip
    Mt.add(bx(0.0, 0.226, -0.046, -0.018, 0.024))
    Mt.add(bx(0.140, 0.226, -0.094, -0.046, 0.028))
    Mt.add(bx(0.0, 0.040, -0.060, -0.046, 0.024))
    Mt.add(tube([V((0.060, 0.0, -0.046)), V((0.058, 0.0, -0.092)), V((0.066, 0.0, -0.100)), V((0.116, 0.0, -0.100)),
                 V((0.126, 0.0, -0.093)), V((0.140, 0.0, -0.084))], 0.0025, 6))
    Mt.add(tube([V((0.090, 0.0, -0.046)), V((0.093, 0.0, -0.064)), V((0.088, 0.0, -0.076))], 0.002, 5))
    grip = [(0.020, -0.046), (0.067, -0.046), (0.067, -0.056), (0.058, -0.075), (0.050, -0.084), (0.046, -0.100),
            (0.036, -0.114), (0.031, -0.140), (0.026, -0.150), (-0.026, -0.150), (-0.028, -0.142), (0.018, -0.056)]
    Po.add(ext(grip, 0.028))

    # curved ribbed box magazine
    def mag(u, v, i, j):
        t = v
        x0 = 0.147 + 0.020 * t * t
        z = lerp(-0.088, -0.212, t)
        hw, hd = 0.012, 0.035
        ca, sa = math.cos(u), math.sin(u)
        return V((x0 + hd + hd * math.copysign(abs(ca) ** 0.35, ca), hw * math.copysign(abs(sa) ** 0.35, sa), z))
    Po.add(grid(mag, lin(0, TAU, 24), lin(0, 1, 10), closed_u=True))
    Po.add(bx(0.163, 0.241, -0.222, -0.210, 0.028))                     # base plate
    for k in range(3):                                                   # vertical ribs on both faces
        for s in (1, -1):
            Po.add(sweep([V((0.165 + k * 0.016 + 0.020 * t * t, s * 0.0125, lerp(-0.098, -0.204, t)))
                          for t in lin(0, 1, 6)], rect_profile(0.004, 0.003), up=(0, s, 0)))
    # scope on the top rail: base block, two rings, body, front bell, eyepiece, turrets, small box sight on top
    Mt.add(bx(0.075, 0.205, 0.057, 0.066, 0.024))
    for x0 in (0.090, 0.170):
        Mt.add(bx(x0, x0 + 0.014, 0.060, 0.081, 0.022))
        Mt.add(cyl_x(x0, x0 + 0.014, 0.0205, z=0.081))
    Mt.add(cyl_x(0, 0, 0, z=0.081, prof=[(0.0, 0.061), (0.019, 0.061), (0.019, 0.085), (0.0175, 0.090),
                                         (0.0175, 0.188), (0.021, 0.200), (0.021, 0.220), (0.0, 0.220)]))
    Mt.add(cyl_y(0.140, 0.081, 0.009, 0.050))
    Mt.add(lathe([(0.0, 0.0), (0.009, 0.0), (0.009, 0.024), (0.0, 0.024)], 16).translate((0.140, 0.0, 0.090)))
    Mt.add(bx(0.083, 0.121, 0.100, 0.126, 0.022))
    P["glass"].add(cyl_x(0.2195, 0.2205, 0.019, z=0.081))
    P["glass"].add(cyl_x(0.0605, 0.0615, 0.017, z=0.081))
    P["glass"].add(bx(0.120, 0.1215, 0.104, 0.122, 0.018))

    # long free-float railed handguard (rails on all four faces) running almost to the muzzle, as the turnaround
    # draws it in hand and slung, with a ring at its rear
    HG0, HG1, HW, HH = 0.242, 0.585, 0.029, 0.034

    def hg(u, v, i, j):
        x = lerp(HG0, HG1, v)
        ca, sa = math.cos(u), math.sin(u)
        return V((x, HW * math.copysign(abs(sa) ** 0.3, sa), -0.0025 + HH * math.copysign(abs(ca) ** 0.3, ca)))
    R.add(grid(hg, lin(0, TAU, 32), lin(0, 1, 2), closed_u=True))
    R.add(bx(HG0 + 0.0005, HG0 + 0.0006, -0.037, 0.032, 0.058))
    R.add(bx(HG1 - 0.0006, HG1 - 0.0005, -0.037, 0.032, 0.058))
    Mt.add(cyl_x(HG0, HG0 + 0.010, 0.033))
    nrib = int((HG1 - 0.012 - 0.250) / 0.0098)
    for k in range(nrib):
        xk = 0.250 + k * 0.0098
        R.add(bx(xk, xk + 0.004, HH - 0.0025, HH + 0.0015, 0.020))           # top
        R.add(bx(xk, xk + 0.004, -HH - 0.0065, -HH - 0.0025, 0.020))         # bottom
        for s in (1, -1):
            R.add(box(0.004, 0.004, 0.020).translate((xk + 0.002, s * (HW + 0.002), -0.0025)))
    for k in range(9):                                                   # lightening slots between the rails
        for s in (1, -1):
            Mt.add(box(0.022, 0.002, 0.008).translate((0.268 + k * 0.034, s * (HW - 0.0005), 0.018)))
    # slim vertical front grip with four finger grooves
    fg = [(0.0, 0.0)] + [(0.0175 - 0.003 * (0.5 + 0.5 * math.cos(TAU * t * 4)) * (t > 0.15), 0.111 * t)
                         for t in lin(0, 1, 33)] + [(0.0, 0.111)]
    Po.add(lathe(fg, 18).transform(Matrix.Translation((0.3365, 0.0, -0.040)) @ Matrix.Rotation(math.pi, 4, "X")))
    # low folding front sight on the top rail, weapon light on the right-side rail, short barrel stub and a
    # fluted flash-hider / can on the muzzle
    Mt.add(ext([(0.556, HH + 0.0015), (0.580, HH + 0.0015), (0.580, HH + 0.010), (0.571, HH + 0.026),
                (0.566, HH + 0.026), (0.560, HH + 0.010)], 0.014))
    Mt.add(bx(0.506, 0.522, -0.012, 0.007, 0.010, y=-HW - 0.006))
    Mt.add(cyl_x(0.495, 0.562, 0.011, y=-HW - 0.017, z=-0.0025))
    P["lamp"].add(cyl_x(0.5615, 0.5625, 0.0095, y=-HW - 0.017, z=-0.0025))
    Mt.add(cyl_x(HG1 - 0.002, 0.600, 0.0085))
    P["cap"].add(cyl_x(0, 0, 0, prof=[(0.0, 0.600), (0.017, 0.600), (0.017, 0.607), (0.015, 0.608), (0.015, 0.640),
                                      (0.017, 0.641), (0.017, 0.650), (0.013, 0.656), (0.0, 0.656)], n=28))
    for k in range(8):                                                   # vent flutes on the muzzle device
        a = TAU * k / 8
        P["cap"].add(box(0.026, 0.003, 0.0015).transform(Matrix.Translation((0.626, 0.0, 0.0)) @
                                                         Matrix.Rotation(a, 4, "X") @ Matrix.Translation((0, 0, 0.015))))
    return P


def carbine_frame():
    """World placement measured from the back/left/right views: origin (-0.001, 0.244, 1.021), bore x_l up toward
    the left shoulder, scope side z_l toward +X, the prop's right side facing out of the back."""
    xl = V((0.200, 0.078, 0.977)).normalized()
    zl = V((0.977, 0.0, -0.200))
    zl = (zl - xl * zl.dot(xl)).normalized()
    yl = zl.cross(xl).normalized()
    m = Matrix((xl, yl, zl)).transposed().to_4x4()
    m.translation = V((-0.001, 0.244, 1.021))
    return m


def carbine_mount(m):
    """Back-panel retention bracket (horizontal band + two angled ladder tabs: `tabs`, part of the vest), the loops
    around the receiver and the handguard, and the light-grey beaded carry strap cinched along the prop's outer
    side (these travel with the slung prop)."""
    tabs, web, light, hard, beads = MD(), MD(), MD(), MD(), MD()
    yo = m.to_3x3() @ V((0, -1, 0))                                     # the prop's outward side (-y_l)
    for xl, (z0, z1), hw in ((0.170, (-0.102, 0.104), 0.020), (0.410, (-0.048, 0.043), 0.036)):
        loop = [V((xl, -hw, z0)), V((xl, -hw, z1)), V((xl, hw, z1)), V((xl, hw, z0))]
        web.add(sweep([m @ q for q in loop], rect_profile(0.003, 0.030), up=m.to_3x3() @ V((1, 0, 0)),
                      closed_path=True))
    import seal_vest as SV
    for s, xa, xb in ((1, 0.060, 0.170), (-1, -0.020, -0.130)):
        zc = 1.205
        dz = -math.tan(math.radians(22)) * abs(xb - xa)
        pts = [V((x, SV.back_y(x) + 0.003, lerp(zc, zc + dz, (x - xa) / (xb - xa)))) for x in lin(xa, xb, 6)]
        tabs.add(sweep(pts, rect_profile(0.070, 0.004), up=(0, 1, 0)))
        for k in range(3):                                               # ladder slots
            q = pts[2 + k]
            tabs.add(box(0.004, 0.003, 0.040).translate(q + V((0.0, 0.0025, 0.0))))
    tabs.add(sweep([V((x, SV.back_y(x) + 0.002, 1.205)) for x in lin(-0.040, 0.080, 8)], rect_profile(0.030, 0.003),
                   up=(0, 1, 0)))
    # carry strap: from the handguard front down to the stock's sling cup, along the outer face
    path = [(0.430, -0.036, -0.020), (0.330, -0.036, -0.026), (0.245, -0.035, -0.030), (0.200, -0.019, -0.040),
            (0.060, -0.019, -0.040), (0.0, -0.020, -0.036), (-0.070, -0.022, -0.040), (-0.134, -0.020, -0.059)]
    pw = L.catmull_path([m @ V(q) for q in path], 6)
    light.add(sweep(pw, rect_profile(0.016, 0.003), up=yo))
    for q in L.resample(pw, int(L.path_length(pw) / 0.006)):
        beads.add(uv_sphere(0.0016, 6, 4).translate(q + yo * 0.0018 + (m.to_3x3() @ V((0, 0, -0.0095)))))
    for xq in (0.300, 0.020):                                            # two square buckle frames
        c = m @ V((xq, -0.039, -0.030))
        hard.add(torus_md(0.012, 0.0018, 4, 4).transform(look_matrix(c, yo, m.to_3x3() @ V((1, 0, 0)))))
    return tabs, web, light, hard, beads


# --------------------------------------------------------------------------------------------------------------
def pistol_md():
    """Compact 9mm prop: +X toward the muzzle, +Z the slide top, +Y its left side; origin at the slide's rear face on
    the bore line.  0.195 long x 0.129 tall x 0.032 wide.  {material key: MD}"""
    P = {"slide": MD(), "frame": MD(), "dark": MD()}

    def X(xs):                                                           # spec x is measured from the front face
        return 0.190 - xs
    sl = [(X(0.190), -0.011), (X(0.003), -0.011), (X(0.0), -0.006), (X(0.0), 0.012), (X(0.004), 0.0195),
          (X(0.190), 0.0195)]
    P["slide"].add(ext(sl, 0.030))
    P["slide"].add(bx(X(0.016), X(0.005), 0.0195, 0.024, 0.006))        # front post
    P["slide"].add(bx(X(0.190), X(0.180), 0.0195, 0.0245, 0.022))       # rear notch block
    P["slide"].add(bx(X(0.170), X(0.130), 0.0195, 0.0205, 0.022))       # optic cover plate
    for k in range(10):                                                  # rear serrations
        xs = 0.128 + k * 0.0064
        P["dark"].add(bx(X(xs + 0.0022), X(xs), -0.006, 0.016, 0.0306))
    fr = [(X(0.122), -0.011), (X(0.002), -0.011), (X(0.002), -0.024), (X(0.122), -0.024)]
    P["frame"].add(ext(fr, 0.028))
    for k in range(3):
        P["dark"].add(bx(X(0.016 + k * 0.016 + 0.006), X(0.016 + k * 0.016), -0.0245, -0.020, 0.029))
    P["frame"].add(tube([V((X(0.101), 0.0, -0.024)), V((X(0.099), 0.0, -0.046)), V((X(0.090), 0.0, -0.049)),
                         V((X(0.045), 0.0, -0.049)), V((X(0.036), 0.0, -0.040)), V((X(0.034), 0.0, -0.030))],
                        0.0024, 6))
    grip = [(X(0.122), -0.024), (X(0.138), -0.0975), (X(0.140), -0.104), (X(0.197), -0.104), (X(0.195), -0.093),
            (X(0.187), -0.006), (X(0.195), -0.004), (X(0.196), -0.012)]
    P["frame"].add(ext(grip, 0.030))
    P["frame"].add(bx(X(0.200), X(0.136), -0.105, -0.0975, 0.033))      # base plate
    P["frame"].add(bx(X(0.135), X(0.122), -0.039, -0.019, 0.034))       # side lever
    for k in range(5):                                                   # stippled grip panel
        P["dark"].add(bx(X(0.180), X(0.145), -0.090 + k * 0.014, -0.082 + k * 0.014, 0.0315))
    return P


# --------------------------------------------------------------------------------------------------------------
def knife_md():
    """Dive knife (the gear card's dagger): leaf blade, oval guard, grooved round handle, rounded butt.  Local +Z
    from the blade tip (z = -0.105) up to the butt (z = 0.068); the guard sits at z 0..0.012."""
    blade, grip = MD(), MD()
    leaf = [(0.0, -0.105), (0.008, -0.085), (0.016, -0.050), (0.015, -0.010), (0.010, 0.0), (-0.010, 0.0),
            (-0.015, -0.010), (-0.016, -0.050), (-0.008, -0.085)]
    blade.add(ext(leaf, 0.006))
    grip.add(lathe([(0.0, 0.0), (0.024, 0.0), (0.024, 0.012), (0.0, 0.012)], 20).transform(
        Matrix.Diagonal((1.0, 0.42, 1.0, 1.0))))
    prof = [(0.0, 0.012), (0.014, 0.012)]
    for k in range(5):
        z0 = 0.016 + k * 0.009
        prof += [(0.016, z0), (0.016, z0 + 0.005), (0.0145, z0 + 0.0065)]
    prof += [(0.016, 0.060), (0.012, 0.0645), (0.006, 0.067), (0.0, 0.068)]
    grip.add(lathe(prof, 20))
    return blade, grip


def canister_shock():
    """Flash-bang canister: cap with a raised rim, neck, egg body with two bands and a square emblem, wire bails."""
    body, wire = MD(), MD()
    body.add(lathe([(0.0, 0.0), (0.012, 0.0), (0.022, 0.008), (0.027, 0.025), (0.027, 0.060), (0.024, 0.072),
                    (0.014, 0.078), (0.014, 0.090), (0.0175, 0.090), (0.0175, 0.106), (0.016, 0.110),
                    (0.0, 0.110)], 28))
    for zb in (0.035, 0.065):
        body.add(torus_md(0.0272, 0.0015, 28, 5).translate((0.0, 0.0, zb)))
    body.add(box(0.020, 0.002, 0.020).translate((0.0, -0.0275, 0.050)))
    for s in (1, -1):
        wire.add(tube([V((s * 0.014, 0.0, 0.082)), V((s * 0.024, 0.0, 0.072)), V((s * 0.029, 0.0, 0.050)),
                       V((s * 0.0285, 0.003, 0.040))], 0.0015, 5))
    return body, wire


def canister_frag():
    """Frag canister: squared cap, side ring and a flat lever down the body, two bands and a raised shield."""
    body, wire = MD(), MD()
    body.add(lathe([(0.0, 0.0), (0.012, 0.0), (0.024, 0.010), (0.028, 0.030), (0.027, 0.065), (0.020, 0.080),
                    (0.013, 0.085), (0.0, 0.085)], 28))
    body.add(box(0.034, 0.028, 0.030).translate((0.0, 0.0, 0.098)))
    for zb in (0.028, 0.058):
        body.add(torus_md(0.0282, 0.0014, 28, 5).translate((0.0, 0.0, zb)))
    sh = [(0.011, 0.060), (-0.011, 0.060), (-0.011, 0.045), (-0.006, 0.036), (0.0, 0.032), (0.006, 0.036),
          (0.011, 0.045)]
    body.add(ext(sh, 0.002, -0.028))
    body.add(sweep([V((0.019, 0.0, 0.106)), V((0.029, 0.0, 0.085)), V((0.031, 0.0, 0.055)), V((0.030, 0.0, 0.045))],
                   rect_profile(0.012, 0.002), up=(1, 0, 0)))
    wire.add(torus_md(0.010, 0.0016, 20, 5).transform(Matrix.Translation((-0.024, 0.0, 0.104)) @
                                                      Matrix.Rotation(math.pi / 2, 4, "X")))
    return body, wire


def drone_md():
    """Folding recon drone, stood on end for stowage: pill housing with a display window, lens on one end, vent
    slots on the other, hinge bumps, a handle recess and four two-segment legs folded underneath.  Local Z = long
    axis (0.16), Y = screen normal."""
    shell, screen, legs, lens = MD(), MD(), MD(), MD()

    def pill(u, v, i, j):
        z = lerp(-0.080, 0.080, v)
        ca, sa = math.cos(u), math.sin(u)
        e = math.sqrt(max(0.0, 1 - (max(0.0, abs(z) - 0.060) / 0.020) ** 2))
        return V((0.045 * e * math.copysign(abs(ca) ** 0.45, ca), 0.030 * e * math.copysign(abs(sa) ** 0.45, sa), z))
    shell.add(grid(pill, lin(0, TAU, 28), lin(0, 1, 16), closed_u=True))
    screen.add(box(0.030, 0.002, 0.050).translate((0.0, 0.0305, 0.004)))
    lens.add(lathe([(0.0, -0.001), (0.007, -0.001), (0.007, 0.001), (0.0, 0.001)], 16).translate((0.0, 0.016, 0.081)))
    for k in range(5):                                                   # vent slots on the lower end
        shell.add(box(0.026, 0.003, 0.002).translate((0.0, 0.016 - 0.007 * k, -0.0805)))
    for sx in (1, -1):
        for sz in (1, -1):
            shell.add(uv_sphere(0.009, 10, 6).translate((sx * 0.036, 0.022, sz * 0.060)))
            pts = [V((sx * 0.040, -0.030, sz * 0.050)), V((sx * 0.044, -0.036, sz * 0.020)),
                   V((sx * 0.030, -0.034, sz * 0.002))]
            legs.add(sweep(pts, rect_profile(0.008, 0.004), up=(0, 1, 0)))
    shell.add(box(0.030, 0.004, 0.010).translate((0.0, 0.029, -0.034)))
    return shell, screen, legs, lens


def charge_md():
    """One breaching-charge cylinder: domed cap, two bands, ring clip near the bottom.  Local Z up, base at z=0."""
    body, metal = MD(), MD()
    body.add(lathe([(0.0, 0.0), (0.0225, 0.0), (0.0225, 0.143)] +
                   [(0.0225 * math.cos(a), 0.143 + 0.012 * math.sin(a)) for a in lin(0, math.pi / 2, 6)[1:]], 24))
    for zb in (0.120, 0.050):
        body.add(torus_md(0.0228, 0.003, 24, 5).translate((0.0, 0.0, zb)))
    metal.add(torus_md(0.006, 0.0012, 12, 4).transform(Matrix.Translation((0.0, -0.024, 0.020)) @
                                                       Matrix.Rotation(math.pi / 2, 4, "Y")))
    return body, metal


def multitool_md():
    """Closed folding pliers multi-tool: two handle slabs, rounded butt, two pivot bolts.  Local Z up (butt at top)."""
    body, bolts = MD(), MD()
    for s in (1, -1):
        sl = [(-0.0175, -0.052), (0.0175, -0.052), (0.0175, 0.040), (0.012, 0.050), (0.0, 0.053), (-0.012, 0.050),
              (-0.0175, 0.040)]
        body.add(ext(sl, 0.0095, s * 0.0052))
    for zz in (0.034, -0.040):
        bolts.add(lathe([(0.0, -0.011), (0.003, -0.011), (0.003, 0.011), (0.0, 0.011)], 10).transform(
            Matrix.Translation((0.0, 0.0, zz)) @ Matrix.Rotation(math.pi / 2, 4, "X")))
    return body, bolts


def gear_mats():
    g = {}
    # satin coatings: the sheet's carbine catches the light along every rail tooth and edge
    g["gun_metal"] = mat_metal("Carbine_Coating_Grey", base=(0.019, 0.020, 0.023), rough=0.32,
                               edge_col=(0.20, 0.195, 0.18))
    g["gun_polymer"] = mat_polymer("Carbine_Polymer_Black", base=(0.012, 0.012, 0.013), rough=0.42, grain=1400.0)
    g["gun_rail"] = mat_metal("Carbine_Rail_Grey", base=(0.022, 0.023, 0.026), rough=0.28,
                              edge_col=(0.30, 0.29, 0.27))
    g["gun_cap"] = mat_metal("Carbine_EndCap_Worn", base=(0.031, 0.024, 0.019), rough=0.45, edge_col=(0.17, 0.16, 0.13))
    g["strap"] = mat_nylon("Carry_Strap_Light_Grey", base=(0.060, 0.063, 0.068), light=(0.095, 0.098, 0.104),
                           tiles=26.0)
    g["slide"] = mat_metal("Pistol_Slide_Blue_Grey", base=(0.012, 0.021, 0.028), rough=0.45, edge_col=(0.093, 0.11, 0.14))
    g["knife_grip"] = mat_polymer("Knife_Grip_Tan_Grey", base=(0.028, 0.022, 0.018), rough=0.55, grain=1200.0)
    g["blade"] = mat_metal("Knife_Blade_Steel", base=(0.120, 0.080, 0.061), rough=0.40, edge_col=(0.30, 0.27, 0.24))
    g["shock"] = mat_metal("Canister_Gunmetal", base=(0.009, 0.012, 0.014), rough=0.45, edge_col=(0.078, 0.070, 0.076))
    g["frag"] = mat_metal("Canister_Black", base=(0.010, 0.008, 0.009), rough=0.50, edge_col=(0.050, 0.042, 0.038))
    g["wire"] = mat_metal("Wire_Steel", base=(0.20, 0.20, 0.21), rough=0.30, edge_col=(0.35, 0.35, 0.36))
    g["drone"] = mat_polymer("Drone_Housing_Black", base=(0.007, 0.010, 0.012), rough=0.50, grain=1500.0)
    g["drone_screen"] = mat_screen("Drone_Display_Blue", col=(0.018, 0.080, 0.171), strength=1.5)
    g["charge"] = mat_metal("Charge_Olive_Grey", base=(0.010, 0.007, 0.008), rough=0.55, edge_col=(0.054, 0.035, 0.030))
    g["mtool"] = mat_metal("Multitool_Stainless", base=(0.25, 0.24, 0.22), rough=0.35, edge_col=(0.45, 0.44, 0.42))
    return g


def in_hand_frame():
    """FRONT-view carry: the carbine hangs muzzle-down beside the right leg, its pistol grip in the right fist
    (seal_body.GRIP_FIST: grip centre and axis in the hand frame), the right side panel against the palm.  The fist is
    pronated and ulnar-deviated, so the rifle hangs in profile: right side to the camera, magazine and grip pointing
    out, rail and optic toward the thigh, muzzle a little forward."""
    import seal_body as B
    hm = B.hand_matrix(-1, grip=True)
    c, h = B.GRIP_FIST
    rot = hm.to_3x3()
    g = (rot @ h).normalized()                                       # grip axis, receiver -> grip bottom
    yl = (rot @ V((-1.0, 0.0, 0.0))).normalized()                    # its left side away from the palm
    yl = (yl - g * yl.dot(g)).normalized()
    w = yl.cross(g)
    sa, ca = math.sin(math.radians(26.5)), math.cos(math.radians(26.5))   # rake of the grip behind the bore normal
    xl = -g * sa - w * ca                                            # bore toward the muzzle
    zl = w * sa - g * ca                                             # scope side
    m = Matrix((xl, yl, zl)).transposed().to_4x4()
    m.translation = hm @ c - xl * 0.022 + zl * 0.098                 # grip centre (0.022, 0, -0.098) in the fist
    return m


def build(coll, root):
    G = gear_mats()

    def put(name, md, mat, smooth=False, bevel=0.0, where=None):
        if not md.v:
            return None
        ob = to_obj(name, md, mat, where or coll, parent=root, smooth=smooth)
        if bevel:
            mod_bevel(ob, bevel, 1)
        return ob

    # ------------------------------------------------------------------ the carbine, as each view of the sheet shows it:
    # slung on the back (LEFT, BACK, RIGHT figures instance `Carbine_Slung`) and held in the right hand (FRONT figure)
    slung = L.collection("Carbine_Slung")
    in_hand = L.collection("Carbine_InHand_Front")
    cp = carbine_md()
    mats = {"metal": G["gun_metal"], "polymer": G["gun_polymer"], "rail": G["gun_rail"], "cap": G["gun_cap"],
            "glass": M["lens_dark"], "lamp": M["lens_pale"]}
    for where, fm, tag in ((slung, carbine_frame(), "Slung"), (in_hand, in_hand_frame(), "InHand")):
        for k, md in cp.items():
            put("Carbine_%s_%s" % (tag, k.capitalize()), md.copy().transform(fm), mats[k],
                smooth=(k in ("glass", "lamp", "cap")), bevel=0.0012 if k in ("metal", "polymer", "rail") else 0.0,
                where=where)
    tabs, web, light, hard, beads = carbine_mount(carbine_frame())
    put("Carbine_Mount_Tabs", tabs, M["webbing"])
    put("Carbine_Slung_Loops", web, M["webbing"], where=slung)
    put("Carbine_Slung_Carry_Strap", light, G["strap"], where=slung)
    put("Carbine_Slung_Buckles", hard, M["plastic_dark"], where=slung)
    put("Carbine_Slung_Strap_Beads", beads, G["wire"], smooth=True, where=slung)

    # ------------------------------------------------------------------ pistol in the right drop-leg holster
    import seal_lower as SL
    a = math.radians(-8.0)                       # muzzle down and a touch back, so the grip rises up and back
    xw = V((0.0, -math.sin(a), -math.cos(a)))
    zw = V((0.0, -math.cos(a), math.sin(a)))
    pm = Matrix((xw, zw.cross(xw), zw)).transposed().to_4x4()
    top = SL.HOLSTER.get("top")
    pm.translation = V((top.x if top is not None else -0.2755, -0.034, 0.925))  # grip shows above the holster
    pp = pistol_md()
    put("Pistol_Slide", pp["slide"].transform(pm), G["slide"], bevel=0.001)
    put("Pistol_Frame", pp["frame"].transform(pm), G["gun_polymer"], bevel=0.001)
    put("Pistol_Serrations", pp["dark"].transform(pm), G["gun_polymer"])

    # ------------------------------------------------------------------ carried gear in its pouches and sheaths
    import seal_vest as SV
    F = dict(SL.GEAR_FRAMES)
    F.update(SV.GEAR_FRAMES)
    if "knife" in F:
        p, n, zv = F["knife"]
        km = look_matrix(p + zv * 0.062, zv, n)          # local Z along the sheath, blade flat against the leg
        blade, grip = knife_md()
        put("Gear_Knife_Blade", blade.transform(km), G["blade"])
        put("Gear_Knife_Handle", grip.transform(km), G["knife_grip"], smooth=True)
    if "left_hip" in F:
        m = F["left_hip"] @ Matrix.Translation((0.0, 0.030, -0.062))
        body, wire = canister_shock()
        put("Gear_Flashbang_Canister", body.transform(m), G["shock"], smooth=True)
        put("Gear_Flashbang_Bails", wire.transform(m), G["wire"], smooth=True)
    if "corner_E" in F:
        m = F["corner_E"] @ Matrix.Translation((0.0, 0.030, -0.066))
        body, wire = canister_frag()
        put("Gear_Frag_Canister", body.transform(m), G["frag"], smooth=True)
        put("Gear_Frag_Ring", wire.transform(m), G["wire"], smooth=True)
    if "dump" in F:
        m = F["dump"] @ Matrix.Translation((0.0, 0.036, -0.010))
        shell, screen, legs, lens = drone_md()
        put("Gear_Recon_Drone", shell.transform(m), G["drone"], smooth=True)
        put("Gear_Recon_Drone_Display", screen.transform(m), G["drone_screen"])
        put("Gear_Recon_Drone_Legs", legs.transform(m), G["drone"])
        put("Gear_Recon_Drone_Lens", lens.transform(m), M["lens_dark"], smooth=True)
    if F.get("left_leg"):
        body, metal, chain = MD(), MD(), MD()
        for m2 in F["left_leg"]:
            b, mt = charge_md()
            m = m2 @ Matrix.Translation((0.0, 0.025, -0.080))
            body.add(b.transform(m))
            metal.add(mt.transform(m))
            for k in range(8):                       # bead-chain lead hanging below the flap edge
                chain.add(uv_sphere(0.0015, 6, 4).transform(m2 @ Matrix.Translation((0.012 + 0.0003 * k, 0.0525,
                                                                                     0.042 - 0.004 * k))))
        put("Gear_Breaching_Charges", body, G["charge"], smooth=True)
        put("Gear_Breaching_Clips", metal, G["wire"], smooth=True)
        put("Gear_Breaching_Bead_Leads", chain, G["wire"], smooth=True)
    if "teardrop" in F:
        m = F["teardrop"] @ Matrix.Translation((0.0, 0.015, 0.032))
        body, bolts = multitool_md()
        put("Gear_Multitool", body.transform(m), G["mtool"], bevel=0.001)
        put("Gear_Multitool_Bolts", bolts.transform(m), G["wire"], smooth=True)
