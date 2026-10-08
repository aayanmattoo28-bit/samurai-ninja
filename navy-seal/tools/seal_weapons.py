"""Weapons and carried gear: the suppressed short-barrel AR carbine (maritime coating) on its sling, the 9mm pistol in
the drop-leg holster, and the tactical gear on the body (smoke, flashbang and frag grenades, folded recon drone,
breaching charge, multi-tool)."""
import math

from mathutils import Matrix

import seal_lib as L
from seal_lib import (MD, TAU, V, box, catmull_path, grid, interp_smooth, lathe, lerp, lin, look_matrix, mod_bevel,
                      mod_solidify, mod_subsurf, rect_profile, smooth, sweep, to_obj, torus_md, tube, uv_sphere)
from seal_mats import M


def _along_x(md, y=0.0, z=0.0):
    """Lathe meshes are built along +Z; turn them to run along +X."""
    m = Matrix(((0, 0, 1, 0), (0, 1, 0, 0), (-1, 0, 0, 0), (0, 0, 0, 1)))
    return md.transform(Matrix.Translation((0, y, z)) @ m)


def _profile_x(prof, n=20, y=0.0, z=0.0):
    """Lathe a (radius, x) profile around the local X axis."""
    return _along_x(lathe([(r, x) for r, x in prof], n), y, z)


def rifle_md():
    """Mk18-style carbine in local coordinates: bore along +X (muzzle at +X), top rail up (+Z), left side +Y.
    Origin at the rear of the receiver (where the buffer tube starts).  Returns {material key: MD}."""
    parts = {"metal": MD(), "polymer": MD(), "rail": MD(), "glass": MD(), "sling": MD()}
    P, Mt, R = parts["polymer"], parts["metal"], parts["rail"]
    # buffer tube + collapsible stock (ribbed, cheek riser, sling QD socket, rubber butt pad)
    Mt.add(_profile_x([(0.0, -0.20), (0.0145, -0.20), (0.0145, 0.0), (0.0, 0.0)], 16, 0.0, 0.010))
    stock = MD()
    stock.add(box(0.150, 0.042, 0.060).translate((-0.135, 0.0, 0.006)))
    stock.add(box(0.110, 0.040, 0.030).translate((-0.130, 0.0, 0.040)))     # cheek riser
    stock.add(box(0.016, 0.046, 0.120).translate((-0.212, 0.0, -0.010)))    # butt pad
    stock.add(box(0.070, 0.020, 0.050).translate((-0.090, 0.0, -0.032)))    # lower lever/latch housing
    for k in range(5):
        stock.add(box(0.006, 0.044, 0.050).translate((-0.185 + k * 0.022, 0.0, 0.006)))
    P.add(stock)
    # lower receiver, magwell, trigger guard, pistol grip, curved 30-round magazine
    Mt.add(box(0.190, 0.024, 0.052).translate((0.090, 0.0, -0.016)))
    Mt.add(box(0.075, 0.030, 0.060).translate((0.150, 0.0, -0.060)))       # magwell
    Mt.add(tube([V((0.090, 0.0, -0.045)), V((0.085, 0.0, -0.068)), V((0.120, 0.0, -0.070)), V((0.130, 0.0, -0.047))],
                0.004, 6))                                                   # trigger guard
    grip = MD()

    def gp(u, v, i, j):
        t = v
        c = V((0.070 - 0.040 * t, 0.0, -0.040 - 0.095 * t))
        w, d = 0.015 * (1 - 0.1 * t), 0.022 * (1 - 0.15 * t)
        return c + V((d * math.cos(u), w * math.sin(u), 0.0))
    grip.add(grid(gp, lin(0, TAU, 16), lin(0, 1, 8), closed_u=True, pole_v1=True))
    P.add(grip)
    mag = MD()

    def mg(u, v, i, j):
        t = v
        a = 0.35 * t                                        # magazine curve
        cx = 0.150 + 0.17 * math.sin(a) * 0.55
        cz = -0.090 - 0.17 * t
        w, d = 0.0125, 0.032 + 0.004 * t
        ca, sa = math.cos(u), math.sin(u)
        return V((cx + d * math.copysign(abs(ca) ** 0.4, ca) * math.cos(a), w * math.copysign(abs(sa) ** 0.4, sa),
                  cz + d * math.copysign(abs(ca) ** 0.4, ca) * math.sin(a) * 0.3))
    mag.add(grid(mg, lin(0, TAU, 20), lin(0, 1, 10), closed_u=True))
    P.add(mag)
    P.add(box(0.072, 0.030, 0.012).translate((0.150 + 0.17 * math.sin(0.35) * 0.55, 0.0, -0.265)))  # base plate
    # upper receiver with charging handle, forward assist, ejection port cover, full-length top rail
    Mt.add(box(0.200, 0.030, 0.042).translate((0.100, 0.0, 0.026)))
    Mt.add(box(0.030, 0.050, 0.010).translate((0.008, 0.0, 0.035)))       # charging handle latch
    Mt.add(_profile_x([(0.0, 0.0), (0.008, 0.0), (0.008, 0.020), (0.0, 0.022)], 12, -0.020, 0.030)
           .transform(Matrix.Translation((0.050, 0.0, 0.0))))              # forward assist
    # free-float handguard with M-LOK slots and a top rail, 0.27 m
    hg = MD()

    def hgf(u, v, i, j):
        x = lerp(0.200, 0.470, v)
        r = 0.022
        ca, sa = math.cos(u), math.sin(u)
        return V((x, r * math.copysign(abs(sa) ** 0.55, sa), 0.012 + r * math.copysign(abs(ca) ** 0.55, ca)))
    hg.add(grid(hgf, lin(0, TAU, 24), lin(0, 1, 12), closed_u=True))
    R.add(hg)
    for k in range(7):                                       # M-LOK slots (dark) on each side and underneath
        for (yy, zz, w, h) in ((0.0225, 0.012, 0.024, 0.008), (-0.0225, 0.012, 0.024, 0.008), (0.0, -0.011, 0.024, 0.008)):
            Mt.add(box(w, 0.002 if abs(yy) > 0 else h, 0.008 if abs(yy) > 0 else 0.002)
                   .translate((0.225 + k * 0.035, yy, zz)))
    for k in range(34):                                      # picatinny top rail teeth from the receiver to the muzzle end
        Mt.add(box(0.0055, 0.022, 0.006).translate((0.010 + k * 0.0135, 0.0, 0.050)))
    Mt.add(box(0.46, 0.016, 0.004).translate((0.240, 0.0, 0.0455)))
    # vertical grip, light, flip-up sights, red-dot with magnifier
    P.add(_profile_x([(0.0, 0.0), (0.016, 0.0), (0.015, 0.085), (0.0, 0.088)], 14)
          .transform(Matrix.Translation((0.340, 0.0, -0.012)) @ Matrix.Rotation(-math.pi / 2, 4, "Y")))
    Mt.add(_profile_x([(0.0, 0.0), (0.012, 0.0), (0.012, 0.070), (0.016, 0.078), (0.016, 0.095), (0.0, 0.095)], 16,
                      0.030, 0.018).transform(Matrix.Translation((0.330, 0.0, 0.0))))
    parts["glass"].add(_profile_x([(0.0, 0.0), (0.015, 0.0), (0.0, 0.001)], 16, 0.030, 0.018)
                       .transform(Matrix.Translation((0.4255, 0.0, 0.0))))
    for x0, h in ((0.035, 0.030), (0.440, 0.034)):          # BUIS folded up
        Mt.add(box(0.012, 0.020, h).translate((x0, 0.0, 0.053 + h / 2)))
    Mt.add(box(0.040, 0.026, 0.012).translate((0.150, 0.0, 0.059)))        # optic mount
    Mt.add(_profile_x([(0.0, 0.0), (0.019, 0.0), (0.019, 0.075), (0.0, 0.075)], 20, 0.0, 0.088)
           .transform(Matrix.Translation((0.115, 0.0, 0.0))))              # red dot tube
    Mt.add(_profile_x([(0.0, 0.0), (0.017, 0.0), (0.017, 0.10), (0.0, 0.10)], 20, 0.0, 0.088)
           .transform(Matrix.Translation((-0.005, 0.0, 0.0))))             # magnifier
    Mt.add(box(0.030, 0.026, 0.020).translate((0.150, 0.0, 0.074)))
    parts["glass"].add(_profile_x([(0.0, 0.0), (0.017, 0.0), (0.0, 0.001)], 16, 0.0, 0.088)
                       .transform(Matrix.Translation((0.1905, 0.0, 0.0))))
    # barrel stub, flash hider and the suppressor (long, with a textured mid-section)
    Mt.add(_profile_x([(0.0, 0.47), (0.0095, 0.47), (0.0095, 0.53), (0.0, 0.53)], 14, 0.0, 0.012))
    sup = [(0.0, 0.52), (0.018, 0.52), (0.022, 0.53), (0.022, 0.685), (0.019, 0.70), (0.006, 0.70), (0.0, 0.70)]
    Mt.add(_profile_x(sup, 24, 0.0, 0.012))
    for k in range(8):
        R.add(_profile_x([(0.0, 0.0), (0.0228, 0.0), (0.0228, 0.006), (0.0, 0.006)], 24, 0.0, 0.012)
              .transform(Matrix.Translation((0.560 + k * 0.014, 0.0, 0.0))))
    # sling swivels
    for x0, z0 in ((-0.205, 0.004), (0.455, -0.005)):
        Mt.add(torus_md(0.012, 0.0025, 16, 5).transform(Matrix.Translation((x0, 0.022, z0)) @
                                                       Matrix.Rotation(math.pi / 2, 4, "X")))
    return parts


def pistol_md():
    """Compact 9mm with an optic cut and threaded barrel: local +X = muzzle, +Z = slide top, +Y left side.  Origin at
    the back of the slide.  Returns {material key: MD}."""
    parts = {"metal": MD(), "polymer": MD()}
    parts["metal"].add(box(0.185, 0.025, 0.030).translate((0.0925, 0.0, 0.015)))   # slide
    for k in range(7):
        parts["polymer"].add(box(0.003, 0.0255, 0.020).translate((0.015 + k * 0.006, 0.0, 0.016)))
    parts["metal"].add(box(0.030, 0.016, 0.006).translate((0.040, 0.0, 0.033)))    # optic plate
    parts["polymer"].add(box(0.160, 0.024, 0.022).translate((0.090, 0.0, -0.011)))  # frame dust cover
    gp = MD()

    def g(u, v, i, j):
        c = V((0.030 - 0.025 * v, 0.0, -0.018 - 0.110 * v))
        ca, sa = math.cos(u), math.sin(u)
        return c + V((0.024 * ca, 0.0145 * sa, 0.0))
    gp.add(grid(g, lin(0, TAU, 16), lin(0, 1, 6), closed_u=True, pole_v1=True))
    parts["polymer"].add(gp)
    parts["polymer"].add(tube([V((0.075, 0.0, -0.022)), V((0.072, 0.0, -0.046)), V((0.105, 0.0, -0.045)),
                               V((0.115, 0.0, -0.022))], 0.004, 6))
    parts["metal"].add(_profile_x([(0.0, 0.185), (0.0075, 0.185), (0.0075, 0.205), (0.0, 0.205)], 12, 0.0, 0.017))
    return parts


def place(parts, m, store):
    for k, md in parts.items():
        store.setdefault(k, MD()).add(md.transform(m))


def build(coll, root):
    store = {}
    # ------------------------------------------------------------------ carbine slung across the back
    # (placement refined from the measured concept: muzzle up behind the LEFT shoulder, stock down at the right hip)
    up = V((0.212, 0.020, 0.977)).normalized()        # bore direction: muzzle up behind the LEFT shoulder
    side = V((0.0, 1.0, 0.0))
    side = (side - up * side.dot(up)).normalized()     # rifle's left side faces away from the back
    top = up.cross(side).normalized()
    rm = Matrix((up, side, top)).transposed().to_4x4()
    rm.translation = V((-0.018, 0.268, 0.965))       # stock end at the right hip (z 0.76), muzzle at z ~1.65
    place(rifle_md(), rm, store)
    # pistol in the right drop-leg holster (grip up and raked back)
    try:
        import seal_lower
        hm = seal_lower.HOLSTER.get("m")
    except Exception:
        hm = None
    if hm is not None:
        pm = hm @ Matrix.Translation((0.008, 0.0225, 0.105)) @ Matrix.Rotation(math.radians(-90 - 15), 4, "Y")
        pistol = pistol_md()
        place(pistol, pm, store)
    mats = {"metal": M["gun_metal"], "polymer": M["gun_polymer"], "rail": M["gun_rail"], "glass": M["lens_dark"],
            "sling": M["nylon_dark"]}
    for k, md in store.items():
        if not md.v:
            continue
        ob = to_obj("Weapon_" + k.capitalize(), md, mats[k], coll, parent=root, smooth=(k in ("polymer", "glass")))
        if k in ("metal", "polymer", "rail"):
            mod_bevel(ob, 0.0015, 1)
