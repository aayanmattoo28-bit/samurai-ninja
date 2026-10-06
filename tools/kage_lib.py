"""Geometry + material helpers for building the Kage Musha model with bpy.

Everything is procedural: parametric grids (with UVs), lathes, sweeps and
node-based materials.  Conventions used across the build:

* metres, Z up, the character faces -Y, character's LEFT is +X
* theta (angle around the body) is measured from the front (-Y) toward +X
"""
import math
import os
import random

import bmesh
import bpy
from mathutils import Matrix, Vector, noise

V = Vector
TAU = math.tau
RNG = random.Random(1234)

TEX_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "textures")


# =============================================================================
# small math helpers
# =============================================================================
def lerp(a, b, t):
    return a + (b - a) * t


def clamp(x, a=0.0, b=1.0):
    return max(a, min(b, x))


def smooth(t):
    t = clamp(t)
    return t * t * (3 - 2 * t)


def interp_table(table, x):
    """Piecewise-linear interpolation in a sorted [(x, value...)] table."""
    if x <= table[0][0]:
        return table[0][1:]
    if x >= table[-1][0]:
        return table[-1][1:]
    for a, b in zip(table, table[1:]):
        if a[0] <= x <= b[0]:
            t = (x - a[0]) / (b[0] - a[0])
            return tuple(lerp(p, q, t) for p, q in zip(a[1:], b[1:]))
    return table[-1][1:]


def interp_smooth(table, x):
    """Catmull-Rom interpolation through a sorted [(x, value...)] table."""
    n = len(table)
    if x <= table[0][0]:
        return table[0][1:]
    if x >= table[-1][0]:
        return table[-1][1:]
    for k in range(n - 1):
        if table[k][0] <= x <= table[k + 1][0]:
            break
    p0 = table[max(0, k - 1)]
    p1 = table[k]
    p2 = table[k + 1]
    p3 = table[min(n - 1, k + 2)]
    t = (x - p1[0]) / (p2[0] - p1[0])
    out = []
    for c in range(1, len(p1)):
        a, b, cc, d = p0[c], p1[c], p2[c], p3[c]
        out.append(0.5 * ((2 * b) + (-a + cc) * t + (2 * a - 5 * b + 4 * cc - d) * t * t + (-a + 3 * b - 3 * cc + d) * t ** 3))
    return tuple(out)


def catmull_path(points, steps=8, closed=False):
    pts = [V(p) for p in points]
    if closed:
        ext = [pts[-1]] + pts + [pts[0], pts[1]]
        segs = len(pts)
    else:
        ext = [pts[0] + (pts[0] - pts[1]) * 0.0] + pts + [pts[-1]]
        segs = len(pts) - 1
    out = []
    for i in range(segs):
        p0, p1, p2, p3 = ext[i], ext[i + 1], ext[i + 2], ext[i + 3]
        for s in range(steps):
            t = s / steps
            out.append(0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t * t + (-p0 + 3 * p1 - 3 * p2 + p3) * t ** 3))
    if not closed:
        out.append(pts[-1].copy())
    return out


def resample(path, n, closed=False):
    """Resample a polyline to n evenly spaced points."""
    pts = [V(p) for p in path]
    if closed:
        pts = pts + [pts[0]]
    d = [0.0]
    for a, b in zip(pts, pts[1:]):
        d.append(d[-1] + (b - a).length)
    L = d[-1]
    out = []
    count = n if closed else n
    for k in range(count):
        t = (k / n if closed else k / (n - 1)) * L
        for i in range(len(d) - 1):
            if d[i] <= t <= d[i + 1] or i == len(d) - 2:
                seg = d[i + 1] - d[i]
                f = 0 if seg == 0 else (t - d[i]) / seg
                out.append(pts[i].lerp(pts[i + 1], clamp(f)))
                break
    return out


def path_length(path):
    return sum((b - a).length for a, b in zip(path, path[1:]))


def ang(deg):
    return math.radians(deg)


def fbm(p, octaves=3):
    return noise.fractal(V(p), 0.5, 2.0, octaves, noise_basis='PERLIN_ORIGINAL')


def nz(p, scale=1.0):
    return noise.noise(V(p) * scale)


# =============================================================================
# Mesh data container
# =============================================================================
class MD:
    """Lightweight mesh builder: verts, faces, per-face-corner uvs, material index."""

    def __init__(self):
        self.v = []
        self.f = []
        self.uv = []
        self.mi = []
        self.hem = []  # optional per-vertex metres above the torn hem (drives the fray shader)

    def add(self, other, mi=None):
        off = len(self.v)
        if other.hem or self.hem:
            self.hem.extend([9.0] * (len(self.v) - len(self.hem)))
            self.hem.extend(other.hem if other.hem else [9.0] * len(other.v))
        self.v.extend(other.v)
        self.f.extend([tuple(i + off for i in face) for face in other.f])
        self.uv.extend(other.uv)
        self.mi.extend(other.mi if mi is None else [mi] * len(other.f))
        return self

    def transform(self, m):
        self.v = [m @ V(p) for p in self.v]
        return self

    def translate(self, t):
        t = V(t)
        self.v = [V(p) + t for p in self.v]
        return self

    def set_mi(self, mi):
        self.mi = [mi] * len(self.f)
        return self

    def copy(self):
        o = MD()
        o.v = [V(p) for p in self.v]
        o.f = list(self.f)
        o.uv = [list(u) for u in self.uv]
        o.mi = list(self.mi)
        o.hem = list(self.hem)
        return o

    def displace(self, fn):
        self.v = [fn(V(p)) for p in self.v]
        return self

    def mirror_x(self):
        """Mirror across the YZ plane (character left -> right), keeping normals outward."""
        o = self.copy()
        o.v = [V((-p.x, p.y, p.z)) for p in o.v]
        o.f = [tuple(reversed(f)) for f in o.f]
        o.uv = [list(reversed(u)) for u in o.uv]
        return o


def limb(path, radius, nth=24, nt=None, ref=(0, -1, 0), mi=0, closed=False, cap0=False, cap1=False, th0=0.0,
         th1=TAU, uv_flip=False):
    """Tube along a path whose radius(t, theta) varies.  theta=0 points along `ref` (projected).

    Returns MD with uv (u = theta fraction, v = t).
    """
    path = [V(p) for p in path]
    if nt is not None and nt != len(path) - 1:
        path = resample(path, nt + 1)
    fr = frames_along(path, up=lambda i, p: ref)
    L = [0.0]
    for a, b in zip(path, path[1:]):
        L.append(L[-1] + (b - a).length)
    tot = L[-1] or 1.0
    full = abs(th1 - th0 - TAU) < 1e-6
    us = lin(th0, th1, nth)
    vs = list(range(len(path)))

    def fn(u, v, i, j):
        T, N, B = fr[j]
        t = L[j] / tot
        r = radius(t, u)
        if isinstance(r, tuple):
            r, extra = r
        else:
            extra = V((0, 0, 0))
        return path[j] + (N * math.cos(u) + B * math.sin(u)) * r + extra

    def uvf(u, v, i, j):
        return ((u - th0) / (th1 - th0), (1 - L[j] / tot) if uv_flip else L[j] / tot)

    md = grid(fn, us, vs, closed_u=full, uv_fn=uvf, mi=mi)
    if (cap0 or cap1) and full:
        cols = nth
        for capflag, ring in ((cap0, 0), (cap1, len(path) - 1)):
            if not capflag:
                continue
            ids = [ring * cols + i for i in range(cols)]
            c = sum((md.v[k] for k in ids), V()) / cols
            ci = len(md.v)
            md.v.append(c)
            for a in range(cols):
                b = (a + 1) % cols
                md.f.append((ids[b], ids[a], ci) if ring == 0 else (ids[a], ids[b], ci))
                md.uv.append([(0.5, 0.5)] * 3)
                md.mi.append(mi)
    return md


def grid(fn, us, vs, closed_u=False, closed_v=False, keep=None, uv_fn=None, mi=0, flip=False,
         pole_v0=False, pole_v1=False):
    """Parametric surface.  fn(u, v, i, j) -> point.  us / vs are lists of params."""
    md = MD()
    nu = len(us) - (1 if closed_u else 0)  # number of distinct columns
    cols = len(us) if not closed_u else len(us) - 1
    if closed_u:
        cols = len(us) - 1
    rows = len(vs) - (1 if closed_v else 0)
    index = {}
    for j in range(rows):
        if (pole_v0 and j == 0) or (pole_v1 and j == rows - 1):
            p = fn(us[0], vs[j], 0, j)
            index[(None, j)] = len(md.v)
            md.v.append(V(p))
            continue
        for i in range(cols):
            index[(i, j)] = len(md.v)
            md.v.append(V(fn(us[i], vs[j], i, j)))

    def vid(i, j):
        jj = j % rows if closed_v else j
        if (pole_v0 and jj == 0) or (pole_v1 and jj == rows - 1):
            return index[(None, jj)]
        ii = i % cols if closed_u else i
        return index[(ii, jj)]

    du = len(us) - 1
    dv = len(vs) - 1
    for j in range(dv):
        for i in range(du):
            if keep is not None and not keep(i, j):
                continue
            ids = [vid(i, j), vid(i + 1, j), vid(i + 1, j + 1), vid(i, j + 1)]
            if uv_fn:
                uvs = [uv_fn(us[i], vs[j], i, j), uv_fn(us[i + 1], vs[j], i + 1, j),
                       uv_fn(us[i + 1], vs[j + 1], i + 1, j + 1), uv_fn(us[i], vs[j + 1], i, j + 1)]
            else:
                uvs = [(i / du, j / dv), ((i + 1) / du, j / dv), ((i + 1) / du, (j + 1) / dv), (i / du, (j + 1) / dv)]
            # collapse poles into triangles
            face, fuv = [], []
            for k, vi in enumerate(ids):
                if vi not in face:
                    face.append(vi)
                    fuv.append(uvs[k])
            if len(face) < 3:
                continue
            if flip:
                face.reverse()
                fuv.reverse()
            md.f.append(tuple(face))
            md.uv.append(fuv)
            md.mi.append(mi)
    return md


def lin(a, b, n):
    return [a + (b - a) * k / n for k in range(n + 1)]


def lathe(profile, segs=32, mi=0, a0=0.0, a1=TAU, closed=True, flip=False, uv_v=None):
    """Revolve [(r, z)] around Z.  Angle measured from -Y toward +X."""
    us = lin(a0, a1, segs)
    vs = list(range(len(profile)))
    pole0 = profile[0][0] < 1e-6
    pole1 = profile[-1][0] < 1e-6

    def fn(u, v, i, j):
        r, z = profile[j]
        return (r * math.sin(u), -r * math.cos(u), z)

    total = sum(math.hypot(profile[k + 1][0] - profile[k][0], profile[k + 1][1] - profile[k][1]) for k in range(len(profile) - 1)) or 1
    acc = [0.0]
    for k in range(len(profile) - 1):
        acc.append(acc[-1] + math.hypot(profile[k + 1][0] - profile[k][0], profile[k + 1][1] - profile[k][1]))

    def uvf(u, v, i, j):
        return ((u - a0) / (a1 - a0), acc[j] / total if uv_v is None else uv_v(j))

    return grid(fn, us, vs, closed_u=closed and abs(a1 - a0 - TAU) < 1e-6, uv_fn=uvf, mi=mi, flip=not flip,
                pole_v0=pole0, pole_v1=pole1)


def frames_along(path, up=None, closed=False):
    """Rotation-minimising frames.  Returns list of (T, N, B)."""
    n = len(path)
    T = []
    for i in range(n):
        if closed:
            a, b = path[(i - 1) % n], path[(i + 1) % n]
        else:
            a, b = path[max(0, i - 1)], path[min(n - 1, i + 1)]
        t = (b - a)
        T.append(t.normalized() if t.length > 1e-9 else V((0, 0, 1)))
    frames = []
    if up is not None:
        for i in range(n):
            u = V(up(i, path[i]) if callable(up) else up)
            Nn = (u - T[i] * u.dot(T[i]))
            if Nn.length < 1e-6:
                Nn = T[i].orthogonal()
            Nn.normalize()
            frames.append((T[i], Nn, T[i].cross(Nn)))
        return frames
    Nn = T[0].orthogonal().normalized()
    for i in range(n):
        if i > 0:
            # parallel transport
            axis = T[i - 1].cross(T[i])
            if axis.length > 1e-9:
                angle = T[i - 1].angle(T[i])
                Nn = Matrix.Rotation(angle, 3, axis.normalized()) @ Nn
            Nn = (Nn - T[i] * Nn.dot(T[i])).normalized()
        frames.append((T[i], Nn, T[i].cross(Nn)))
    return frames


def circle_profile(r, n=8, rx=None):
    rx = r if rx is None else rx
    return [(rx * math.cos(TAU * k / n), r * math.sin(TAU * k / n)) for k in range(n)] + \
           [(rx, 0.0)]


def rect_profile(w, h, n_round=0):
    """Rounded rectangle cross-section, width along B (x), height along N (y)."""
    hw, hh = w / 2, h / 2
    if n_round <= 0:
        pts = [(hw, -hh), (hw, hh), (-hw, hh), (-hw, -hh)]
    else:
        r = min(hw, hh) * 0.9
        pts = []
        for cx, cy, a0 in ((hw - r, hh - r, 0), (-hw + r, hh - r, 90), (-hw + r, -hh + r, 180), (hw - r, -hh + r, 270)):
            for k in range(n_round + 1):
                a = math.radians(a0 + 90 * k / n_round)
                pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return pts + [pts[0]]


def sweep(path, profile, up=None, closed_path=False, scale=None, mi=0, cap0=False, cap1=False,
          uv_len=None, twist=0.0, frames=None):
    """Sweep a 2D profile [(b, n)] (first point repeated at end if closed) along a path.

    The profile x axis maps to the B vector, y axis to the N vector.
    scale(t) -> float or (sx, sy) multiplies the profile at path fraction t.
    """
    path = [V(p) for p in path]
    fr = frames or frames_along(path, up, closed_path)
    n = len(path)
    L = [0.0]
    for a, b in zip(path, path[1:]):
        L.append(L[-1] + (b - a).length)
    total = L[-1] or 1.0
    prof_closed = (V(profile[0]) - V(profile[-1])).length < 1e-9
    us = list(range(len(profile)))
    vs = list(range(n + (1 if closed_path else 0)))

    def fn(u, v, i, j):
        jj = j % n
        T, N, B = fr[jj]
        t = L[jj] / total
        px, py = profile[i]
        if twist:
            a = twist * t
            px, py = px * math.cos(a) - py * math.sin(a), px * math.sin(a) + py * math.cos(a)
        if scale is not None:
            s = scale(t)
            if isinstance(s, tuple):
                px, py = px * s[0], py * s[1]
            else:
                px, py = px * s, py * s
        return path[jj] + B * px + N * py

    uvl = uv_len if uv_len is not None else total

    def uvf(u, v, i, j):
        jj = j if not closed_path else j
        d = L[jj] if jj < n else total + (path[0] - path[-1]).length
        return (i / (len(profile) - 1), d / uvl)

    md = grid(fn, us, vs, closed_u=prof_closed, closed_v=False, uv_fn=uvf, mi=mi)
    if closed_path:
        # stitch last ring to first
        cols = len(profile) - 1 if prof_closed else len(profile)
        last = n  # ring index n duplicates ring 0 -> remap
        remap = {}
        for i in range(cols):
            remap[n * cols + i] = i
        md.f = [tuple(remap.get(x, x) for x in f) for f in md.f]
        md.v = md.v[: n * cols]
    for capflag, ring in ((cap0, 0), (cap1, n - 1)):
        if not capflag or closed_path:
            continue
        cols = len(profile) - 1 if prof_closed else len(profile)
        ids = [ring * cols + i for i in range(cols)]
        c = sum((md.v[k] for k in ids), V()) / cols
        ci = len(md.v)
        md.v.append(c)
        for a in range(cols):
            b = (a + 1) % cols
            f = (ids[a], ids[b], ci) if ring else (ids[b], ids[a], ci)
            md.f.append(f)
            md.uv.append([(0.5, 0.5)] * 3)
            md.mi.append(mi)
    return md


def tube(path, r, n=8, up=None, scale=None, mi=0, cap0=True, cap1=True, closed=False, twist=0.0, rx=None):
    return sweep(path, circle_profile(r, n, rx), up=up, scale=scale, mi=mi, cap0=cap0, cap1=cap1,
                 closed_path=closed, twist=twist)


def uv_sphere(r, seg=16, rings=10, mi=0, rx=None, ry=None, rz=None):
    rx = rx or r
    ry = ry or r
    rz = rz or r
    prof = []
    for k in range(rings + 1):
        a = math.pi * k / rings
        prof.append((math.sin(a), math.cos(a)))
    md = lathe([(p[0], p[1]) for p in prof], seg, mi=mi)
    md.v = [V((p.x * rx, p.y * ry, p.z * rz)) for p in md.v]
    return md


def box(sx, sy, sz, mi=0):
    md = MD()
    hx, hy, hz = sx / 2, sy / 2, sz / 2
    md.v = [V(p) for p in [(-hx, -hy, -hz), (hx, -hy, -hz), (hx, hy, -hz), (-hx, hy, -hz),
                           (-hx, -hy, hz), (hx, -hy, hz), (hx, hy, hz), (-hx, hy, hz)]]
    md.f = [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]
    md.uv = [[(0, 0), (1, 0), (1, 1), (0, 1)] for _ in md.f]
    md.mi = [mi] * 6
    return md


def torus_md(R, r, seg=32, rseg=8, mi=0):
    us = lin(0, TAU, seg)
    vs = lin(0, TAU, rseg)

    def fn(u, v, i, j):
        c = R + r * math.cos(v)
        return (c * math.sin(u), -c * math.cos(u), r * math.sin(v))

    return grid(fn, us, vs, closed_u=True, closed_v=True, mi=mi)


def frame_matrix(origin, x_axis, z_hint):
    """Matrix whose local X -> x_axis, local Z ~ z_hint, located at origin."""
    x = V(x_axis).normalized()
    z = V(z_hint)
    z = (z - x * z.dot(x)).normalized()
    y = z.cross(x)
    m = Matrix((x, y, z)).transposed().to_4x4()
    m.translation = V(origin)
    return m


def look_matrix(origin, z_axis, y_hint=(0, 1, 0)):
    """Matrix whose local Z -> z_axis."""
    z = V(z_axis).normalized()
    y = V(y_hint)
    y = (y - z * y.dot(z))
    if y.length < 1e-6:
        y = z.orthogonal()
    y.normalize()
    x = y.cross(z)
    m = Matrix((x, y, z)).transposed().to_4x4()
    m.translation = V(origin)
    return m


# =============================================================================
# Object creation
# =============================================================================
_COLLS = {}


def collection(name, parent=None):
    if name in _COLLS:
        return _COLLS[name]
    c = bpy.data.collections.new(name)
    (parent or bpy.context.scene.collection).children.link(c)
    _COLLS[name] = c
    return c


def to_obj(name, md, mats, coll, smooth=True, recalc=False, parent=None, auto_smooth=None):
    me = bpy.data.meshes.new(name)
    me.from_pydata([tuple(p) for p in md.v], [], md.f)
    if md.uv:
        uvl = me.uv_layers.new(name="UVMap")
        flat = []
        for fu in md.uv:
            for u in fu:
                flat.extend((u[0], u[1]))
        if len(flat) == len(uvl.data) * 2:
            uvl.data.foreach_set("uv", flat)
    if md.mi:
        me.polygons.foreach_set("material_index", md.mi)
    me.polygons.foreach_set("use_smooth", [smooth] * len(me.polygons))
    if md.hem and len(md.hem) == len(md.v):
        a = me.attributes.new("hem1", "FLOAT", "POINT")
        a.data.foreach_set("value", [h + 1.0 for h in md.hem])
    if not isinstance(mats, (list, tuple)):
        mats = [mats]
    for m in mats:
        me.materials.append(m)
    if recalc:
        bm = bmesh.new()
        bm.from_mesh(me)
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        bm.to_mesh(me)
        bm.free()
    me.update()
    ob = bpy.data.objects.new(name, me)
    coll.objects.link(ob)
    if parent is not None:
        ob.parent = parent
    return ob


def mod_subsurf(ob, view=1, render=2):
    m = ob.modifiers.new("Subdivision", "SUBSURF")
    m.levels = view
    m.render_levels = render
    m.quality = 3
    return m


def mod_solidify(ob, t, offset=0.0, rim=True):
    m = ob.modifiers.new("Solidify", "SOLIDIFY")
    m.thickness = t
    m.offset = offset
    m.use_rim = rim
    m.use_even_offset = True
    return m


def mod_bevel(ob, w, segs=2, limit="ANGLE"):
    m = ob.modifiers.new("Bevel", "BEVEL")
    m.width = w
    m.segments = segs
    m.limit_method = limit
    return m


_WRINKLE_TEX = {}
_WRINKLE_SPACE = {}


def mod_wrinkle(ob, strength=0.003, size=0.025, kind="CLOUDS", stretch=(1.0, 1.0, 1.0), hard=False):
    """Geometric cloth wrinkles: displace along normals.

    hard=True uses |noise| valleys inverted into sharp fold ridges; stretch elongates the features
    (e.g. (1, 1, 6) = long vertical gravity folds, (3, 3, 1) = horizontal tension wrinkles).
    """
    key = (kind, size, hard)
    tex = _WRINKLE_TEX.get(key)
    if tex is None:
        tex = bpy.data.textures.new(f"Wrinkle_{kind}_{size}_{int(hard)}", kind)
        if kind == "CLOUDS":
            tex.noise_scale = size
            tex.noise_depth = 1 if hard else 2
            tex.noise_type = "HARD_NOISE" if hard else "SOFT_NOISE"
            tex.noise_basis = "IMPROVED_PERLIN"
        elif kind == "STUCCI":
            tex.noise_scale = size
            tex.turbulence = 6.0
        _WRINKLE_TEX[key] = tex
    m = ob.modifiers.new("Wrinkles", "DISPLACE")
    m.texture = tex
    st = tuple(float(x) for x in stretch)
    if st != (1.0, 1.0, 1.0):
        emp = _WRINKLE_SPACE.get(st)
        if emp is None or emp.name not in bpy.data.objects:
            emp = bpy.data.objects.new("WrinkleSpace_%.1f_%.1f_%.1f" % st, None)
            bpy.context.scene.collection.objects.link(emp)
            emp.scale = st
            emp.hide_render = True
            emp.hide_viewport = True
            _WRINKLE_SPACE[st] = emp
        m.texture_coords = "OBJECT"
        m.texture_coords_object = emp
    else:
        m.texture_coords = "GLOBAL"
    if hard:
        m.mid_level, m.strength = 1.0, -strength
    else:
        m.mid_level, m.strength = 0.5, strength
    return m


def cloth_mods(ob, sub=2, wrinkles=(), solid=0.0, offset=0.0):
    """Cloth modifier stack in the right order: Subdivision -> Wrinkles -> Solidify."""
    if sub:
        mod_subsurf(ob, 1, sub)
    for w in wrinkles:
        mod_wrinkle(ob, *w[:2], **(w[2] if len(w) > 2 else {}))
    if solid:
        sm = mod_solidify(ob, solid, offset)
        sm.use_even_offset = False  # even offset explodes into spikes on sharp displaced creases
    return ob


def torn_profile(n, depth, seed, deep=2, tongues=1):
    """Per-column hem shortening (in units of the drop).  Neighbours are correlated (no sawtooth):
    low + mid frequency raggedness, a few deep V-rips and optional streamers hanging below the hem."""
    r = random.Random(1000 + int(seed))
    out = []
    for k in range(n + 1):
        x = k / n
        lo = 0.5 + 0.5 * fbm(V((x * 2.2, seed * 1.37, 0.3)))
        mid = 0.5 + 0.5 * fbm(V((x * 8.0, seed * 1.37, 4.1)))
        out.append(depth * (0.35 * lo + 0.30 * mid + 0.35 * r.random() ** 3))
    for _ in range(deep):
        c, w = r.randrange(1, n), r.randint(1, max(1, n // 12))
        d = depth * r.uniform(1.6, 2.8)
        for k in range(max(0, c - w), min(n, c + w) + 1):
            out[k] = max(out[k], d * (1 - abs(k - c) / (w + 1)) ** 0.6)
    for _ in range(tongues if n >= 10 else 0):
        c = r.randrange(2, n - 2)
        for k in (c - 1, c, c + 1):
            out[k] = -depth * r.uniform(0.5, 0.9)
    return out


def mod_weighted_normals(ob):
    try:
        m = ob.modifiers.new("WeightedNormal", "WEIGHTED_NORMAL")
        m.keep_sharp = True
    except Exception:
        pass


def empty(name, coll, loc=(0, 0, 0), parent=None, size=0.1):
    e = bpy.data.objects.new(name, None)
    e.empty_display_size = size
    e.location = loc
    coll.objects.link(e)
    if parent:
        e.parent = parent
    return e


# =============================================================================
# Materials
# =============================================================================
_IMAGES = {}


def image(name, colorspace="Non-Color"):
    if name in _IMAGES:
        return _IMAGES[name]
    path = os.path.join(TEX_DIR, name)
    img = bpy.data.images.load(path, check_existing=True)
    img.colorspace_settings.name = colorspace
    _IMAGES[name] = img
    return img


class NB:
    """Tiny node-builder."""

    def __init__(self, mat):
        mat.use_nodes = True
        self.nt = mat.node_tree
        for n in list(self.nt.nodes):
            self.nt.nodes.remove(n)
        self.mat = mat
        self.x = 0

    def n(self, kind, loc=(0, 0), **kw):
        node = self.nt.nodes.new(kind)
        node.location = loc
        for k, v in kw.items():
            if k.startswith("i_"):
                key = k[2:].replace("__", " ")
                node.inputs[key].default_value = v
            else:
                setattr(node, k, v)
        return node

    def inp(self, node, key, value):
        node.inputs[key].default_value = value
        return node

    def link(self, a, b):
        self.nt.links.new(a, b)

    # common building blocks ----------------------------------------------
    def texcoord(self):
        return self.n("ShaderNodeTexCoord", (-1400, 0))

    def mapping(self, vec, scale=(1, 1, 1), loc=(0, 0, 0), rot=(0, 0, 0)):
        m = self.n("ShaderNodeMapping", (-1200, 0))
        m.inputs["Scale"].default_value = scale
        m.inputs["Location"].default_value = loc
        m.inputs["Rotation"].default_value = rot
        self.link(vec, m.inputs["Vector"])
        return m.outputs["Vector"]

    def noise(self, vec, scale=5.0, detail=6.0, rough=0.55, distortion=0.0, dims="3D"):
        t = self.n("ShaderNodeTexNoise", (-900, 0))
        t.noise_dimensions = dims
        t.inputs["Scale"].default_value = scale
        t.inputs["Detail"].default_value = detail
        t.inputs["Roughness"].default_value = rough
        t.inputs["Distortion"].default_value = distortion
        if vec is not None:
            self.link(vec, t.inputs["Vector"])
        return t

    def ramp(self, fac, stops, interp="LINEAR"):
        r = self.n("ShaderNodeValToRGB", (-600, 0))
        r.color_ramp.interpolation = interp
        els = r.color_ramp.elements
        while len(els) > 2:
            els.remove(els[-1])
        for k, (pos, col) in enumerate(stops):
            if k < 2:
                e = els[k]
                e.position = pos
            else:
                e = els.new(pos)
            if isinstance(col, (int, float)):
                col = (col, col, col, 1.0)
            elif len(col) == 3:
                col = (*col, 1.0)
            e.color = col
        self.link(fac, r.inputs["Fac"])
        return r.outputs["Color"]

    def math(self, op, a, b=None, clamp_=False):
        m = self.n("ShaderNodeMath", (-400, 0))
        m.operation = op
        m.use_clamp = clamp_
        for k, val in enumerate((a, b)):
            if val is None:
                continue
            if isinstance(val, (int, float)):
                m.inputs[k].default_value = val
            else:
                self.link(val, m.inputs[k])
        return m.outputs[0]

    def mix(self, fac, a, b, blend="MIX"):
        m = self.n("ShaderNodeMix", (-300, 0))
        m.data_type = "RGBA"
        m.blend_type = blend
        for sock, val in ((m.inputs[0], fac), (m.inputs[6], a), (m.inputs[7], b)):
            if isinstance(val, (int, float)):
                sock.default_value = val
            elif isinstance(val, tuple):
                sock.default_value = val if len(val) == 4 else (*val, 1.0)
            else:
                self.link(val, sock)
        return m.outputs[2]

    def mixf(self, fac, a, b):
        m = self.n("ShaderNodeMix", (-300, 0))
        m.data_type = "FLOAT"
        for sock, val in ((m.inputs[0], fac), (m.inputs[2], a), (m.inputs[3], b)):
            if isinstance(val, (int, float)):
                sock.default_value = val
            else:
                self.link(val, sock)
        return m.outputs[0]

    def img(self, name, vec, extension="REPEAT", interp="Linear", proj="FLAT"):
        t = self.n("ShaderNodeTexImage", (-900, 300))
        t.image = image(name)
        t.extension = extension
        t.interpolation = interp
        t.projection = proj
        if proj == "BOX":
            t.projection_blend = 0.25
        if vec is not None:
            self.link(vec, t.inputs["Vector"])
        return t

    def bump(self, height, strength=0.3, distance=0.002, normal=None):
        b = self.n("ShaderNodeBump", (-200, -300))
        b.inputs["Strength"].default_value = strength
        b.inputs["Distance"].default_value = distance
        self.link(height, b.inputs["Height"])
        if normal is not None:
            self.link(normal, b.inputs["Normal"])
        return b.outputs["Normal"]

    def principled(self, loc=(200, 0), **kw):
        p = self.n("ShaderNodeBsdfPrincipled", loc)
        for k, v in kw.items():
            key = k.replace("_", " ")
            key = {"Base Color": "Base Color", "Subsurface Weight": "Subsurface Weight"}.get(key, key)
            if isinstance(v, (int, float, tuple)):
                p.inputs[key].default_value = v if not (isinstance(v, tuple) and len(v) == 3 and key in (
                    "Base Color", "Emission Color", "Sheen Tint", "Coat Tint", "Specular Tint")) else (*v, 1.0)
            else:
                self.link(v, p.inputs[key])
        return p

    def output(self, shader, loc=(600, 0)):
        o = self.n("ShaderNodeOutputMaterial", loc)
        self.link(shader, o.inputs["Surface"])
        return o


_MATS = {}


def new_mat(name):
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    _MATS[name] = m
    return m


def _ao(nb, distance=0.03, only_local=True):
    """Ambient-occlusion factor (1 = open, 0 = deep crevice).

    only_local: occlusion from the object itself only, so transparent decal shells floating a few mm above a
    surface do not read as crevices (they would turn whole surfaces into grime)."""
    ao = nb.n("ShaderNodeAmbientOcclusion", (-1000, -800))
    ao.samples = 8
    ao.only_local = only_local
    ao.inputs["Distance"].default_value = distance
    return ao.outputs["AO"]


def _edges(nb, lo=0.505, hi=0.545):
    """Convex-edge mask from Cycles pointiness (EEVEE: 0 everywhere)."""
    g = nb.n("ShaderNodeNewGeometry", (-1000, -1000))
    return nb.ramp(g.outputs["Pointiness"], [(lo, 0.0), (hi, 1.0)])


def _updust(nb, obj, scale=10.0):
    """Dust that settles on upward-facing surfaces, broken up by noise."""
    g = nb.n("ShaderNodeNewGeometry", (-1000, -1200))
    sep = nb.n("ShaderNodeSeparateXYZ", (-800, -1200))
    nb.link(g.outputs["Normal"], sep.inputs[0])
    up = nb.ramp(sep.outputs[2], [(0.25, 0.0), (0.85, 1.0)])
    n = nb.noise(obj, scale, 6, 0.65)
    return nb.math("MULTIPLY", up, nb.ramp(n.outputs["Fac"], [(0.35, 0.0), (0.7, 1.0)]))


def _bevel(nb, radius=0.0025, samples=8):
    """Rounded-edge shading normal (Cycles Bevel node)."""
    bv = nb.n("ShaderNodeBevel", (-1000, -1400))
    bv.samples = samples
    bv.inputs["Radius"].default_value = radius
    return bv.outputs["Normal"]


def _hard_edges(nb, bevel_n, lo=0.02, hi=0.12, convex_only=True):
    """Edge mask from the angle between the bevelled and the true normal (resolution independent)."""
    g = nb.n("ShaderNodeNewGeometry", (-1000, -1600))
    vm = nb.n("ShaderNodeVectorMath", (-800, -1500))
    vm.operation = "DOT_PRODUCT"
    nb.link(bevel_n, vm.inputs[0])
    nb.link(g.outputs["Normal"], vm.inputs[1])
    e = nb.ramp(nb.math("SUBTRACT", 1.0, vm.outputs["Value"]), [(lo, 0.0), (hi, 1.0)])
    if convex_only:
        e = nb.math("MULTIPLY", e, nb.ramp(_ao(nb, 0.006), [(0.70, 0.0), (0.92, 1.0)]))
    return e


def _gold_shader(nb, vec, tint=(0.78, 0.53, 0.22), rough=0.3, tarnish=0.35, scale=18.0, crest=None, cav=None):
    """Antique gilt: tarnish breakup, dielectric grime packed in recesses, polished crowns, hammered surface."""
    n = nb.noise(vec, scale, 8, 0.6)
    tar = nb.ramp(n.outputs["Fac"], [(0.35, 0.0), (0.75, 1.0)])
    col = nb.mix(nb.math("MULTIPLY", tar, tarnish), tint, (0.11, 0.07, 0.03))
    crev = nb.math("SUBTRACT", 1.0, _ao(nb, 0.012))
    if cav is not None:
        crev = nb.math("MAXIMUM", crev, cav)
    grime = nb.math("MULTIPLY", crev, 0.9)
    col = nb.mix(grime, col, (0.040, 0.032, 0.025))  # grime colour, not dark metal
    metal = nb.math("SUBTRACT", 1.0, grime)  # grime and patina are dielectric
    edge = _hard_edges(nb, _bevel(nb, 0.0008), 0.04, 0.15, False)
    col = nb.mix(nb.math("MULTIPLY", edge, 0.5), col, (min(1, tint[0] * 1.25), min(1, tint[1] * 1.25),
                                                       min(1, tint[2] * 1.2)))
    r = nb.ramp(n.outputs["Fac"], [(0.2, rough * 0.7), (0.8, rough * 1.6)])
    r = nb.mixf(edge, r, rough * 0.5)
    r = nb.mixf(grime, r, 0.9)
    if crest is not None:
        top = nb.ramp(crest, [(0.40, 0.0), (0.80, 1.0)])
        flank = nb.ramp(crest, [(0.05, 1.0), (0.40, 0.0)])
        col = nb.mix(nb.math("MULTIPLY", flank, 0.85), col, tuple(c * 0.20 for c in tint))
        col = nb.mix(nb.math("MULTIPLY", top, 0.75), col, tuple(min(1.0, c * 1.35) for c in tint))
        r = nb.mixf(top, r, rough * 0.35)
        r = nb.mixf(flank, r, 0.62)
    hv = nb.n("ShaderNodeTexVoronoi", (-900, -900), feature="SMOOTH_F1")
    hv.inputs["Scale"].default_value = 160.0
    nb.link(vec, hv.inputs["Vector"])
    g = nb.principled(Base_Color=col, Metallic=metal, Roughness=r, Normal=nb.bump(hv.outputs["Distance"], 0.10, 0.0005))
    return g


def _hammer(g):
    """The hammered-surface normal socket created inside _gold_shader (to chain further bumps onto)."""
    return g.inputs["Normal"].links[0].from_socket


def mat_gold(name="Gold_Trim", tint=(0.78, 0.53, 0.22), rough=0.3, tarnish=0.4):
    m = new_mat(name)
    nb = NB(m)
    tc = nb.texcoord()
    vec = tc.outputs["Object"]
    g = _gold_shader(nb, vec, tint, rough, tarnish, 30.0)
    nb.output(g.outputs[0])
    m.diffuse_color = (*tint, 1)
    m.metallic = 1.0
    return m


def mat_lacquer(name, pattern=None, uv_scale=(1, 1), mapping="UV", gold_tint=(0.62, 0.42, 0.18),
                base=(0.010, 0.009, 0.009), wear=0.35, relief=0.35, pattern_rot=0.0, extension="REPEAT",
                flip_u=False, straw=False, dust=0.25, coat=0.18, stone=0.6, edge_col=(0.10, 0.034, 0.018), disp=0.0):
    """Aged black urushi: crusty stone-finish grain, patchy coat with scratches, worn undercoat edges,
    and optional raised gilt ornament (pattern mask + generated _height/_cavity maps, optional displacement)."""
    m = new_mat(name)
    nb = NB(m)
    tc = nb.texcoord()
    obj = tc.outputs["Object"]
    n1 = nb.noise(obj, 9.0, 8, 0.6)
    n2 = nb.noise(obj, 55.0, 4, 0.5)
    basecol = nb.mix(nb.ramp(n1.outputs["Fac"], [(0.3, 0.0), (0.8, 1.0)]), base, (0.035, 0.026, 0.020))
    dustmask = nb.math("MULTIPLY", nb.ramp(n2.outputs["Fac"], [(0.55, 0.0), (0.8, 1.0)]), dust)
    basecol = nb.mix(dustmask, basecol, (0.10, 0.085, 0.07))
    rough = nb.mixf(dustmask, nb.math("ADD", nb.math("MULTIPLY", n1.outputs["Fac"], 0.22), 0.34), 0.85)
    # scratches (they live in the coat only)
    sc = nb.noise(nb.mapping(obj, (90, 7, 90)), 1.0, 3, 0.5)
    scratch = nb.ramp(sc.outputs["Fac"], [(0.485, 0.0), (0.5, 1.0), (0.515, 0.0)])
    sc2 = nb.noise(nb.mapping(obj, (8, 70, 70)), 1.0, 3, 0.5)
    scratch = nb.math("MAXIMUM", scratch, nb.ramp(sc2.outputs["Fac"], [(0.49, 0.0), (0.5, 0.7), (0.51, 0.0)]))
    basecol = nb.mix(nb.math("MULTIPLY", scratch, 0.5), basecol, (0.06, 0.05, 0.045))
    rough = nb.mixf(scratch, rough, 0.6)
    height = nb.math("MULTIPLY", scratch, 0.0)
    if stone > 0:  # ishime-ji stone-finish grain
        sv = nb.n("ShaderNodeTexVoronoi", (-900, -1700), feature="F1")
        sv.inputs["Scale"].default_value = 700.0
        nb.link(obj, sv.inputs["Vector"])
        grain = nb.ramp(sv.outputs["Distance"], [(0.0, 1.0), (0.45, 0.0)])
        gfine = nb.noise(obj, 1600.0, 2, 0.5)
        height = nb.math("ADD", height, nb.math("MULTIPLY", nb.math("ADD", nb.math("MULTIPLY", grain, 0.7),
                                                                       nb.math("MULTIPLY", gfine.outputs["Fac"], 0.5)),
                                                 stone * 1.6))
        basecol = nb.mix(nb.math("MULTIPLY", nb.math("MULTIPLY", grain, nb.ramp(n2.outputs["Fac"], [(0.4, 0.0), (0.7, 1.0)])),
                                 stone * 0.5), basecol, (0.045, 0.040, 0.034))
        rough = nb.math("ADD", rough, nb.math("MULTIPLY", grain, 0.12 * stone))
    if straw:
        w1 = nb.n("ShaderNodeTexWave", (-900, -500), wave_type="RINGS", rings_direction="Z")
        w1.inputs["Scale"].default_value = 140.0
        w1.inputs["Distortion"].default_value = 1.5
        w1.inputs["Detail"].default_value = 2.0
        nb.link(obj, w1.inputs["Vector"])
        height = nb.math("ADD", height, nb.math("MULTIPLY", w1.outputs["Fac"], 0.6))
        w2 = nb.n("ShaderNodeTexWave", (-900, -700), wave_type="RINGS", rings_direction="Z")
        w2.inputs["Scale"].default_value = 70.0
        w2.inputs["Distortion"].default_value = 0.5
        nb.link(obj, w2.inputs["Vector"])
        band = nb.ramp(w2.outputs["Fac"], [(0.35, 0.0), (0.65, 1.0)])
        basecol = nb.mix(band, basecol, (0.024, 0.018, 0.013))
        height = nb.math("ADD", height, nb.math("MULTIPLY", band, 0.8))
    crev = nb.math("SUBTRACT", 1.0, _ao(nb, 0.025))
    basecol = nb.mix(nb.math("MULTIPLY", crev, 0.9), basecol, (0.050, 0.043, 0.036))
    rough = nb.mixf(crev, rough, 0.75)
    # worn edges: red-brown undercoat, then bare ground on the most worn spots
    bev = _bevel(nb, 0.0025)
    en = nb.noise(obj, 35.0, 4, 0.6)
    edge = nb.math("MULTIPLY", _hard_edges(nb, bev), nb.ramp(en.outputs["Fac"], [(0.35, 0.0), (0.55, 1.0)]))
    basecol = nb.mix(nb.math("MULTIPLY", edge, 0.7), basecol, edge_col)
    basecol = nb.mix(nb.math("MULTIPLY", edge, nb.ramp(en.outputs["Fac"], [(0.55, 0.0), (0.7, 1.0)])), basecol,
                     (0.17, 0.10, 0.055))
    rough = nb.mixf(edge, rough, 0.28)
    upd = nb.math("MULTIPLY", _updust(nb, obj), dust * 1.3)
    basecol = nb.mix(upd, basecol, (0.115, 0.098, 0.082))
    rough = nb.mixf(upd, rough, 0.85)
    if straw:
        rough = nb.math("ADD", nb.math("MULTIPLY", rough, 0.5), 0.35)
        sepw = nb.n("ShaderNodeSeparateXYZ", (-1100, -900))
        nb.link(tc.outputs["UV"], sepw.inputs[0])
        fu = nb.math("FRACT", nb.math("MULTIPLY", sepw.outputs[0], 130.0))
        fv = nb.math("FRACT", nb.math("MULTIPLY", sepw.outputs[1], 26.0))
        cu = nb.math("GREATER_THAN", fu, 0.5)
        cv = nb.math("GREATER_THAN", fv, 0.5)
        chk = nb.math("ABSOLUTE", nb.math("SUBTRACT", cu, cv))
        strand = nb.math("MULTIPLY", nb.math("SINE", nb.math("MULTIPLY", fu, 3.14159)),
                         nb.math("SINE", nb.math("MULTIPLY", fv, 3.14159)))
        weave_h = nb.math("ADD", nb.math("MULTIPLY", chk, 0.6), nb.math("MULTIPLY", strand, 0.6))
        basecol = nb.mix(nb.math("MULTIPLY", chk, 0.9), basecol, (0.095, 0.064, 0.036))
        basecol = nb.mix(nb.math("MULTIPLY", nb.math("SUBTRACT", 1.0, strand), 0.8), basecol, (0.006, 0.005, 0.004))
        height = nb.math("ADD", height, nb.math("MULTIPLY", weave_h, 4.0))
    hi = cav = mask = None
    if pattern:
        vec = tc.outputs["UV"] if mapping == "UV" else tc.outputs[mapping]
        vec = nb.mapping(vec, (-uv_scale[0] if flip_u else uv_scale[0], uv_scale[1], 1), (1 if flip_u else 0, 0, 0),
                         (0, 0, pattern_rot))
        mask = nb.img(pattern, vec, extension).outputs["Color"]
        stem = pattern[:-4]
        hi = nb.img(stem + "_height.png", vec, extension).outputs["Color"]
        cav = nb.img(stem + "_cavity.png", vec, extension).outputs["Color"]
        gn_ = nb.noise(obj, 40.0, 5, 0.6)
        basecol = nb.mix(nb.math("MULTIPLY", cav, 0.85), basecol, (0.004, 0.0035, 0.003))  # black grime moat
        basecol = nb.mix(nb.math("MULTIPLY", nb.math("MULTIPLY", cav, nb.ramp(gn_.outputs["Fac"], [(0.45, 0.0), (0.7, 1.0)])),
                                 dust * 2.0), basecol, (0.085, 0.074, 0.060))  # dusty fringe
        rough = nb.mixf(cav, rough, 0.88)
    cr_n = nb.noise(obj, 4.0, 6, 0.6)
    lacq = nb.principled((200, 200), Base_Color=basecol, Roughness=rough, Coat_Weight=coat,
                         Coat_Roughness=nb.ramp(cr_n.outputs["Fac"], [(0.3, 0.12), (0.75, 0.45)]),
                         Specular_IOR_Level=0.4)
    occl = nb.math("MAXIMUM", upd, crev)
    if cav is not None:
        occl = nb.math("MAXIMUM", occl, cav)
    cw = nb.math("MULTIPLY", nb.math("SUBTRACT", coat, nb.math("MULTIPLY", occl, coat)), nb.math("SUBTRACT", 1.0, edge))
    nb.link(cw, lacq.inputs["Coat Weight"])
    nb.link(nb.bump(nb.math("MULTIPLY", scratch, -1.0), 0.3, 0.0003, normal=bev), lacq.inputs["Coat Normal"])
    shader = lacq.outputs[0]
    gold = None
    if pattern:
        wn = nb.noise(obj, 25.0, 6, 0.6)
        wearm = nb.ramp(wn.outputs["Fac"], [(0.25, 1.0 - wear), (0.7, 1.0)])
        gm = nb.math("MULTIPLY", mask, wearm, clamp_=True)
        gold = _gold_shader(nb, obj, gold_tint, 0.42, 0.45, 25.0, crest=hi, cav=cav)
        mixs = nb.n("ShaderNodeMixShader", (450, 100))
        nb.link(gm, mixs.inputs[0])
        nb.link(shader, mixs.inputs[1])
        nb.link(gold.outputs[0], mixs.inputs[2])
        shader = mixs.outputs[0]
        height = nb.math("ADD", height, nb.math("MULTIPLY", hi, relief * (4 if disp > 0 else 10)))
        height = nb.math("ADD", height, nb.math("MULTIPLY", mask, relief * 3))
        height = nb.math("SUBTRACT", height, nb.math("MULTIPLY", cav, relief * 3))
        eng = nb.noise(obj, 260.0, 2, 0.5)
        height = nb.math("ADD", height, nb.math("MULTIPLY", nb.math("MULTIPLY", eng.outputs["Fac"], mask), 0.8))
        nb.link(nb.bump(height, 0.45, 0.0010, normal=_hammer(gold)), gold.inputs["Normal"])
        bmp = nb.bump(height, 0.45, 0.0010, normal=bev)
    else:
        bmp = nb.bump(height, 0.25, 0.0004, normal=bev)
    nb.link(bmp, lacq.inputs["Normal"])
    out = nb.output(shader)
    if pattern and disp > 0:
        dn = nb.n("ShaderNodeDisplacement", (400, -500))
        dn.space = "OBJECT"
        dn.inputs["Midlevel"].default_value = 0.0
        dn.inputs["Scale"].default_value = disp
        nb.link(nb.math("SUBTRACT", hi, nb.math("MULTIPLY", cav, 0.3)), dn.inputs["Height"])
        nb.link(dn.outputs["Displacement"], out.inputs["Displacement"])
        try:
            m.displacement_method = "BOTH"
        except AttributeError:
            m.cycles.displacement_method = "BOTH"
    m.diffuse_color = (*base, 1)
    m.roughness = 0.3
    return m


def _triplanar(nb, name, obj, scale, extension="REPEAT"):
    """Sign-corrected triplanar lookup of a mask image, `scale` tiles per metre (no mirrored glyphs)."""
    sp = nb.n("ShaderNodeSeparateXYZ", (-1300, 600))
    nb.link(obj, sp.inputs[0])
    g = nb.n("ShaderNodeNewGeometry", (-1300, 800))
    sn = nb.n("ShaderNodeSeparateXYZ", (-1100, 800))
    nb.link(g.outputs["Normal"], sn.inputs[0])
    x, y, z = sp.outputs[0], sp.outputs[1], sp.outputs[2]
    nx, ny, nz = sn.outputs[0], sn.outputs[1], sn.outputs[2]

    def vec(u, v):
        c = nb.n("ShaderNodeCombineXYZ", (-900, 600))
        nb.link(nb.math("MULTIPLY", u, scale), c.inputs[0])
        nb.link(nb.math("MULTIPLY", v, scale), c.inputs[1])
        return c.outputs[0]

    ix = nb.img(name, vec(nb.math("MULTIPLY", y, nb.math("SIGN", nx)), z), extension).outputs["Color"]
    iy = nb.img(name, vec(nb.math("MULTIPLY", x, nb.math("MULTIPLY", nb.math("SIGN", ny), -1.0)), z),
                extension).outputs["Color"]
    iz = nb.img(name, vec(x, y), extension).outputs["Color"]
    wx, wy, wz = (nb.math("POWER", nb.math("ABSOLUTE", n_), 4.0) for n_ in (nx, ny, nz))
    acc = nb.math("ADD", nb.math("ADD", nb.math("MULTIPLY", ix, wx), nb.math("MULTIPLY", iy, wy)),
                  nb.math("MULTIPLY", iz, wz))
    return nb.math("DIVIDE", acc, nb.math("ADD", nb.math("ADD", wx, wy), nb.math("ADD", wz, 1e-4)))


def mat_cloth(name, base=(0.020, 0.018, 0.017), print_img=None, print_scale=(1, 1), print_col=(0.34, 0.23, 0.11),
              print_strength=0.7, mapping="UV", extension="REPEAT", fade=(0.050, 0.043, 0.037), dust=0.35,
              sheen=0.75, weave=210.0, print_metal=0.0, fray=0.0, rot=0.0, sheen_tint=(0.55, 0.50, 0.45),
              folds=1.0):
    """Heavy, worn, dusty cotton/hemp.

    mapping: "UV" (artwork panels, CLIP) or "TRI" (scattered prints, print_scale[0] tiles per metre).
    fray: height in metres of the frayed band above the torn hem (needs the mesh 'hem1' attribute).
    rot: fraction of the panel (uv v from the bottom) that is bleached / rotted.
    """
    m = new_mat(name)
    nb = NB(m)
    tc = nb.texcoord()
    obj = tc.outputs["Object"]
    n1 = nb.noise(obj, 4.0, 8, 0.65)
    col = nb.mix(nb.ramp(n1.outputs["Fac"], [(0.35, 0.0), (0.75, 1.0)]), base, fade)
    sep = nb.n("ShaderNodeSeparateXYZ", (-1000, -400))
    nb.link(obj, sep.inputs[0])
    n2 = nb.noise(obj, 14.0, 6, 0.6)
    dmask = nb.math("MULTIPLY", nb.ramp(n2.outputs["Fac"], [(0.5, 0.0), (0.85, 1.0)]), dust)
    col = nb.mix(dmask, col, (0.11, 0.09, 0.075))
    # rubbed, lighter fold crests
    cn = nb.noise(obj, 18.0, 4, 0.6)
    crest = nb.math("MULTIPLY", _edges(nb, 0.50, 0.525), nb.ramp(cn.outputs["Fac"], [(0.35, 0.0), (0.6, 1.0)]))
    col = nb.mix(nb.math("MULTIPLY", crest, 0.55), col, (0.080, 0.070, 0.060))
    rough = 0.90
    metal = 0.0
    rm = None
    if rot > 0:
        su = nb.n("ShaderNodeSeparateXYZ", (-1000, -200))
        nb.link(tc.outputs["UV"], su.inputs[0])
        rm = nb.math("MULTIPLY", nb.ramp(su.outputs[1], [(0.0, 1.0), (rot, 0.0)]),
                     nb.ramp(nb.noise(obj, 7.0, 6, 0.65).outputs["Fac"], [(0.3, 0.25), (0.65, 1.0)]))
        col = nb.mix(nb.math("MULTIPLY", rm, 0.85), col, (0.105, 0.082, 0.058))
    pmask = None
    if print_img:
        if mapping == "TRI":
            ptex = _triplanar(nb, print_img, obj, print_scale[0], extension)
        else:
            vec = tc.outputs["UV"] if mapping == "UV" else tc.outputs[mapping]
            vec = nb.mapping(vec, (print_scale[0], print_scale[1], 1))
            ptex = nb.img(print_img, vec, extension).outputs["Color"]
        pn = nb.noise(obj, 30.0, 5, 0.6)
        pmask = nb.math("MULTIPLY", ptex, nb.ramp(pn.outputs["Fac"], [(0.25, 0.15), (0.70, 1.0)]))
        vor = nb.n("ShaderNodeTexVoronoi", (-900, -1500), feature="DISTANCE_TO_EDGE")
        vor.inputs["Scale"].default_value = 140.0
        nb.link(obj, vor.inputs["Vector"])
        pmask = nb.math("MULTIPLY", pmask, nb.ramp(vor.outputs["Distance"], [(0.0, 0.0), (0.05, 1.0)]))  # crackle
        sp_ = nb.noise(obj, 420.0, 2, 0.5)
        pmask = nb.math("MULTIPLY", pmask, nb.ramp(sp_.outputs["Fac"], [(0.56, 1.0), (0.64, 0.0)]))      # flakes
        pmask = nb.math("MULTIPLY", pmask, nb.math("SUBTRACT", 1.0, nb.math("MULTIPLY", crest, 0.65)))  # rubbed off
        if rm is not None:
            pmask = nb.math("MULTIPLY", pmask, nb.math("SUBTRACT", 1.0, nb.math("MULTIPLY", rm, 0.7)))
        pmask = nb.math("MULTIPLY", pmask, print_strength, clamp_=True)
        col = nb.mix(pmask, col, print_col)
        rough = nb.mixf(pmask, 0.90, 0.74)
        metal = nb.mixf(pmask, 0.0, print_metal)
    # faded / sun-bleached patches
    fp = nb.noise(obj, 1.8, 5, 0.6)
    col = nb.mix(nb.math("MULTIPLY", nb.ramp(fp.outputs["Fac"], [(0.55, 0.0), (0.75, 1.0)]), 0.6), col,
                 (0.055, 0.045, 0.038))
    # deep shadow in folds (AO), dust on the lower hems and upward faces
    ao = _ao(nb, 0.05)
    col = nb.mix(nb.math("SUBTRACT", 1.0, ao), col, (0.004, 0.0035, 0.003))
    low = nb.ramp(sep.outputs[2], [(0.15, 1.0), (0.75, 0.0)])
    hem = nb.math("MULTIPLY", low, nb.ramp(nb.noise(obj, 6.0, 6, 0.6).outputs["Fac"], [(0.3, 0.2), (0.7, 1.0)]))
    col = nb.mix(nb.math("MULTIPLY", hem, dust * 0.9), col, (0.12, 0.10, 0.082))
    col = nb.mix(nb.math("MULTIPLY", _updust(nb, obj, 8.0), dust * 0.8), col, (0.11, 0.095, 0.08))
    # weave visible from every orientation: three band waves weighted by |normal|
    wv = {}
    for d in ("X", "Y", "Z"):
        w = nb.n("ShaderNodeTexWave", (-900, -600), wave_type="BANDS", bands_direction=d)
        w.inputs["Scale"].default_value = weave
        w.inputs["Distortion"].default_value = 0.8
        nb.link(obj, w.inputs["Vector"])
        wv[d] = w.outputs["Fac"]
    gn = nb.n("ShaderNodeNewGeometry", (-1100, -700))
    sn = nb.n("ShaderNodeSeparateXYZ", (-950, -700))
    nb.link(gn.outputs["Normal"], sn.inputs[0])
    ax_, ay_, az_ = (nb.math("ABSOLUTE", sn.outputs[k]) for k in range(3))
    weave_h = nb.math("ADD", nb.math("ADD", nb.math("MULTIPLY", ax_, nb.math("MULTIPLY", wv["Y"], wv["Z"])),
                                     nb.math("MULTIPLY", ay_, nb.math("MULTIPLY", wv["X"], wv["Z"]))),
                      nb.math("MULTIPLY", az_, nb.math("MULTIPLY", wv["X"], wv["Y"])))
    n3 = nb.noise(obj, 160.0, 3, 0.5)
    h = nb.math("ADD", nb.math("MULTIPLY", weave_h, 0.22), nb.math("MULTIPLY", n3.outputs["Fac"], 0.4))
    # vertical stress lines + sharp creases (anisotropic)
    fold = nb.noise(nb.mapping(obj, (1.0, 1.0, 0.2)), 30.0, 4, 0.55)
    h = nb.math("ADD", h, nb.math("MULTIPLY", fold.outputs["Fac"], 0.6 * folds))
    cz = nb.noise(nb.mapping(obj, (1.0, 1.0, 0.25)), 45.0, 3, 0.5)
    h = nb.math("SUBTRACT", h, nb.math("MULTIPLY", nb.ramp(cz.outputs["Fac"], [(0.47, 0.0), (0.5, 1.0), (0.53, 0.0)]),
                                       0.5 * folds))
    if pmask is not None:
        h = nb.math("ADD", h, nb.math("MULTIPLY", pmask, 0.35))  # raised pigment
    edge = None
    if fray > 0:
        at = nb.n("ShaderNodeAttribute", (-1000, -1400))
        at.attribute_name = "hem1"
        present = nb.math("GREATER_THAN", at.outputs["Fac"], 0.5)
        dist = nb.math("SUBTRACT", at.outputs["Fac"], 1.0)
        edge = nb.math("MULTIPLY", nb.math("SUBTRACT", 1.0, nb.math("DIVIDE", dist, fray), clamp_=True), present)
        col = nb.mix(nb.math("MULTIPLY", edge, 0.8), col, (0.060, 0.050, 0.040))  # faded fibre ends
    bmp = nb.bump(h, 0.35, 0.0006)
    p = nb.principled(Base_Color=col, Roughness=rough, Metallic=metal, Sheen_Weight=sheen, Sheen_Roughness=0.35,
                      Sheen_Tint=sheen_tint, Specular_IOR_Level=0.22, Normal=bmp)
    shader = p.outputs[0]
    if edge is not None:
        thr = nb.noise(nb.mapping(obj, (700.0, 700.0, 18.0)), 1.0, 2, 0.5)  # vertical threads ~1.4 mm wide
        hl = nb.noise(obj, 60.0, 3, 0.6)
        cut = nb.math("ADD", nb.math("MULTIPLY", thr.outputs["Fac"], 0.75), nb.math("MULTIPLY", hl.outputs["Fac"], 0.25))
        alpha = nb.math("GREATER_THAN", cut, nb.math("ADD", nb.math("MULTIPLY", edge, 0.55), 0.12))
        tr = nb.n("ShaderNodeBsdfTransparent", (200, -400))
        mx = nb.n("ShaderNodeMixShader", (450, 0))
        nb.link(alpha, mx.inputs[0])
        nb.link(tr.outputs[0], mx.inputs[1])
        nb.link(shader, mx.inputs[2])
        shader = mx.outputs[0]
        try:
            m.surface_render_method = "DITHERED"
        except Exception:
            pass
    nb.output(shader)
    m.diffuse_color = (*base, 1)
    return m


def mat_simple(name, base, rough=0.5, metal=0.0, coat=0.0, sheen=0.0, bump_scale=60.0, bump_str=0.2,
               var_col=None, var_scale=6.0, sss=0.0, wave=None, wave_scale=40.0, wave_str=0.5, wave_dir="DIAGONAL",
               wave_coord="UV", dirt=0.0, emission=None):
    m = new_mat(name)
    nb = NB(m)
    tc = nb.texcoord()
    obj = tc.outputs["Object"]
    n1 = nb.noise(obj, var_scale, 8, 0.6)
    col = base
    if var_col is not None:
        col = nb.mix(nb.ramp(n1.outputs["Fac"], [(0.3, 0.0), (0.75, 1.0)]), base, var_col)
    if dirt:
        n4 = nb.noise(obj, 20.0, 6, 0.6)
        col = nb.mix(nb.math("MULTIPLY", nb.ramp(n4.outputs["Fac"], [(0.5, 0.0), (0.85, 1.0)]), dirt), col,
                     (0.09, 0.075, 0.06))
    crev = nb.math("SUBTRACT", 1.0, _ao(nb, 0.02))
    col = nb.mix(nb.math("MULTIPLY", crev, 0.8), col, (0.02, 0.016, 0.013))
    bev = None
    if dirt:
        bev = _bevel(nb, 0.002)
        en = nb.noise(obj, 40.0, 4, 0.6)
        edge = nb.math("MULTIPLY", _hard_edges(nb, bev, 0.02, 0.10), nb.ramp(en.outputs["Fac"], [(0.45, 0.0), (0.65, 1.0)]))
        col = nb.mix(nb.math("MULTIPLY", edge, 0.3 * min(1.0, dirt * 2)), col, (0.10, 0.075, 0.055))
    rough = nb.mixf(crev, rough, min(1.0, rough + 0.3))
    n2 = nb.noise(obj, bump_scale, 6, 0.6)
    h = n2.outputs["Fac"]
    if wave:
        w = nb.n("ShaderNodeTexWave", (-900, -600), wave_type="BANDS", bands_direction=wave_dir)
        w.inputs["Scale"].default_value = wave_scale
        w.inputs["Distortion"].default_value = 1.0
        w.inputs["Detail"].default_value = 3.0
        nb.link(tc.outputs[wave_coord], w.inputs["Vector"])
        h = nb.math("ADD", nb.math("MULTIPLY", w.outputs["Fac"], wave_str), nb.math("MULTIPLY", h, 0.3))
    bmp = nb.bump(h, bump_str, 0.001, normal=bev)
    kw = dict(Base_Color=col, Roughness=rough, Metallic=metal, Coat_Weight=coat, Sheen_Weight=sheen,
              Normal=bmp)
    if sss:
        kw.update(Subsurface_Weight=sss)
    p = nb.principled(**kw)
    if sss:
        p.inputs["Subsurface Radius"].default_value = (1.0, 0.35, 0.2)
        p.inputs["Subsurface Scale"].default_value = 0.008
    if emission:
        p.inputs["Emission Color"].default_value = (*emission[0], 1)
        p.inputs["Emission Strength"].default_value = emission[1]
    nb.output(p.outputs[0])
    m.diffuse_color = (*base, 1) if isinstance(base, tuple) else (0.2, 0.2, 0.2, 1)
    return m


def mat_decal(name, img, tint=(0.62, 0.42, 0.18), wear=0.3, metal=1.0, rough=0.3, uv_scale=(1, 1), flip_u=False):
    """Gold (or printed) decal: transparent where the mask is black."""
    m = new_mat(name)
    nb = NB(m)
    tc = nb.texcoord()
    vec = nb.mapping(tc.outputs["UV"], (-uv_scale[0] if flip_u else uv_scale[0], uv_scale[1], 1),
                     (1 if flip_u else 0, 0, 0))
    it = nb.img(img, vec, "CLIP")
    obj = tc.outputs["Object"]
    wn = nb.noise(obj, 30.0, 6, 0.6)
    wearm = nb.ramp(wn.outputs["Fac"], [(0.25, 1.0 - wear), (0.7, 1.0)])
    alpha = nb.math("MULTIPLY", it.outputs["Color"], wearm, clamp_=True)
    alpha = nb.ramp(alpha, [(0.25, 0.0), (0.45, 1.0)])
    if metal > 0.5:
        g = _gold_shader(nb, obj, tint, rough, 0.45, 30.0)
    else:
        g = nb.principled(Base_Color=tint, Roughness=rough, Metallic=metal)
    nb.link(nb.bump(it.outputs["Color"], 0.4, 0.001), g.inputs["Normal"])
    tr = nb.n("ShaderNodeBsdfTransparent", (200, -300))
    mx = nb.n("ShaderNodeMixShader", (450, 0))
    nb.link(alpha, mx.inputs[0])
    nb.link(tr.outputs[0], mx.inputs[1])
    nb.link(g.outputs[0], mx.inputs[2])
    nb.output(mx.outputs[0])
    try:
        m.surface_render_method = "DITHERED"
    except Exception:
        pass
    m.diffuse_color = (*tint, 1)
    return m


def mat_eye(name="Eye"):
    m = new_mat(name)
    nb = NB(m)
    tc = nb.texcoord()
    sep = nb.n("ShaderNodeSeparateXYZ", (-1000, 0))
    nb.link(tc.outputs["Object"], sep.inputs[0])
    # local +Z is the gaze direction; normalise by radius 0.0125
    z = nb.math("DIVIDE", sep.outputs[2], 0.0125)
    col = nb.ramp(z, [(0.70, (0.12, 0.085, 0.07)), (0.80, (0.20, 0.17, 0.155)), (0.845, (0.075, 0.038, 0.019)),
                      (0.93, (0.045, 0.023, 0.011)), (0.95, (0.004, 0.003, 0.003))])
    p = nb.principled(Base_Color=col, Roughness=0.3, Coat_Weight=0.35, Coat_Roughness=0.12)
    nb.output(p.outputs[0])
    return m


def mat_tsuka(name="Tsuka_Wrap", ito=(0.012, 0.011, 0.011), same=(0.45, 0.06, 0.04), n_diamonds=11):
    """Diamond pattern (hishigami) silk wrap over same (ray skin)."""
    m = new_mat(name)
    nb = NB(m)
    tc = nb.texcoord()
    sep = nb.n("ShaderNodeSeparateXYZ", (-1200, 0))
    nb.link(tc.outputs["UV"], sep.inputs[0])
    # u = around, v = along length (uv from sweep: u around profile, v along path in metres)
    a = nb.math("MULTIPLY", sep.outputs[1], n_diamonds / 0.25)   # along
    b = nb.math("MULTIPLY", sep.outputs[0], 2.0)                 # around (2 diamonds visible per side)
    fa = nb.math("SUBTRACT", nb.math("FRACT", a), 0.5)
    fb = nb.math("SUBTRACT", nb.math("FRACT", b), 0.5)
    d = nb.math("ADD", nb.math("ABSOLUTE", fa), nb.math("ABSOLUTE", fb))
    diamond = nb.ramp(d, [(0.22, 1.0), (0.26, 0.0)])
    col = nb.mix(diamond, ito, same)
    n = nb.noise(tc.outputs["Object"], 400.0, 3, 0.5)
    h = nb.math("ADD", nb.math("MULTIPLY", nb.math("SUBTRACT", 1.0, diamond), 1.0), nb.math("MULTIPLY", n.outputs["Fac"], 0.2))
    p = nb.principled(Base_Color=col, Roughness=nb.mixf(diamond, 0.62, 0.38), Sheen_Weight=0.08,
                      Normal=nb.bump(h, 0.6, 0.001))
    nb.output(p.outputs[0])
    return m


def mat_mail(name="Chainmail_Iron"):
    """Kusari (chain mail): small interlocking rings via voronoi distance, dark oiled iron."""
    m = new_mat(name)
    nb = NB(m)
    tc = nb.texcoord()
    vor = nb.n("ShaderNodeTexVoronoi", (-900, 0), feature="F1")
    vor.inputs["Scale"].default_value = 420.0
    vor.inputs["Randomness"].default_value = 0.0
    nb.link(tc.outputs["Object"], vor.inputs["Vector"])
    ring = nb.ramp(vor.outputs["Distance"], [(0.18, 0.0), (0.26, 1.0), (0.36, 1.0), (0.44, 0.0)])
    col = nb.mix(ring, (0.004, 0.004, 0.004), (0.05, 0.045, 0.04))
    n = nb.noise(tc.outputs["Object"], 30.0, 4, 0.5)
    col = nb.mix(nb.math("MULTIPLY", nb.ramp(n.outputs["Fac"], [(0.55, 0.0), (0.8, 1.0)]), ring), col,
                 (0.09, 0.04, 0.02))
    p = nb.principled(Base_Color=col, Metallic=nb.mixf(ring, 0.0, 0.9), Roughness=0.45,
                      Normal=nb.bump(ring, 0.8, 0.002))
    nb.output(p.outputs[0])
    return m


def mat_leather_tooled(name="Leather_Pouch_Tooled", base=(0.030, 0.012, 0.006), light=(0.085, 0.036, 0.016)):
    """Waxed, scuffed red-brown leather with raised embossed tooling (pouch_tooling height/cavity maps)."""
    m = new_mat(name)
    nb = NB(m)
    tc = nb.texcoord()
    obj = tc.outputs["Object"]
    hi = nb.img("pouch_tooling_height.png", tc.outputs["UV"], "CLIP").outputs["Color"]
    cav = nb.img("pouch_tooling_cavity.png", tc.outputs["UV"], "CLIP").outputs["Color"]
    n1 = nb.noise(obj, 9.0, 8, 0.6)
    col = nb.mix(nb.ramp(n1.outputs["Fac"], [(0.3, 0.0), (0.75, 1.0)]), base, light)
    col = nb.mix(nb.ramp(nb.noise(obj, 3.0, 6, 0.7).outputs["Fac"], [(0.35, 0.0), (0.65, 1.0)]), col,
                 (0.012, 0.006, 0.003))  # mottling
    vor = nb.n("ShaderNodeTexVoronoi", (-900, -300), feature="DISTANCE_TO_EDGE")
    vor.inputs["Scale"].default_value = 420.0
    nb.link(obj, vor.inputs["Vector"])
    grain = nb.ramp(vor.outputs["Distance"], [(0.0, 0.0), (0.08, 1.0)])
    crev = nb.math("SUBTRACT", 1.0, _ao(nb, 0.015))
    col = nb.mix(nb.math("MULTIPLY", crev, 0.8), col, (0.018, 0.010, 0.006))
    col = nb.mix(nb.math("MULTIPLY", nb.ramp(hi, [(0.4, 0.0), (0.8, 1.0)]), 0.6), col, (0.11, 0.055, 0.028))
    col = nb.mix(nb.math("MULTIPLY", cav, 0.8), col, (0.010, 0.005, 0.003))
    bev = _bevel(nb, 0.003)
    en = nb.noise(obj, 30.0, 4, 0.6)
    edge = nb.math("MULTIPLY", _hard_edges(nb, bev, 0.02, 0.10), nb.ramp(en.outputs["Fac"], [(0.35, 0.0), (0.6, 1.0)]))
    col = nb.mix(nb.math("MULTIPLY", edge, 0.7), col, (0.16, 0.085, 0.045))
    col = nb.mix(nb.math("MULTIPLY", _updust(nb, obj, 10.0), 0.15), col, (0.10, 0.085, 0.07))
    h = nb.math("ADD", nb.math("MULTIPLY", grain, 0.08), nb.math("MULTIPLY", hi, 1.2))
    wr = nb.noise(obj, 35.0, 5, 0.6)
    h = nb.math("ADD", h, nb.math("MULTIPLY", wr.outputs["Fac"], 0.8))
    p = nb.principled(Base_Color=col, Roughness=nb.mixf(edge, 0.70, 0.45), Coat_Weight=0.07, Coat_Roughness=0.45,
                      Specular_IOR_Level=0.35, Normal=nb.bump(h, 0.45, 0.0015, normal=bev))
    nb.output(p.outputs[0])
    m.diffuse_color = (*base, 1)
    return m


def mat_metal_engraved(name, tint=(0.36, 0.22, 0.10), img="filigree.png", uv_scale=(3.0, 2.0), rough=0.38):
    """Cast bronze with raised ornament: polished crowns, black-green patina packed in the recesses."""
    m = new_mat(name)
    nb = NB(m)
    tc = nb.texcoord()
    obj = tc.outputs["Object"]
    vec = nb.mapping(tc.outputs["UV"], (uv_scale[0], uv_scale[1], 1))
    stem = img[:-4]
    hi = nb.img(stem + "_height.png", vec, "REPEAT").outputs["Color"]
    cav = nb.img(stem + "_cavity.png", vec, "REPEAT").outputs["Color"]
    g = _gold_shader(nb, obj, tint, rough, 0.6, 22.0, crest=hi, cav=cav)
    col_in = g.inputs["Base Color"].links[0].from_socket
    col = nb.mix(nb.math("MULTIPLY", cav, 0.9), col_in, (0.018, 0.020, 0.013))
    nb.link(col, g.inputs["Base Color"])
    nb.link(nb.bump(hi, 0.7, 0.0015, normal=_hammer(g)), g.inputs["Normal"])
    nb.output(g.outputs[0])
    m.diffuse_color = (*tint, 1)
    return m


def mat_leather(name, base=(0.035, 0.017, 0.009), light=(0.075, 0.038, 0.019), rough=0.62, scuff=0.5, dirt=0.3):
    """Worn grained leather: pebble grain, creases, scuffed lighter edges, grime in crevices."""
    m = new_mat(name)
    nb = NB(m)
    tc = nb.texcoord()
    obj = tc.outputs["Object"]
    n1 = nb.noise(obj, 7.0, 8, 0.62)
    col = nb.mix(nb.ramp(n1.outputs["Fac"], [(0.3, 0.0), (0.75, 1.0)]), base, light)
    vor = nb.n("ShaderNodeTexVoronoi", (-900, -300), feature="DISTANCE_TO_EDGE")
    vor.inputs["Scale"].default_value = 160.0
    nb.link(obj, vor.inputs["Vector"])
    grain = nb.ramp(vor.outputs["Distance"], [(0.0, 0.0), (0.09, 1.0)])
    cr = nb.noise(nb.mapping(obj, (60.0, 8.0, 60.0)), 1.0, 4, 0.6)
    crease = nb.ramp(cr.outputs["Fac"], [(0.47, 0.0), (0.5, 1.0), (0.53, 0.0)])
    crev = nb.math("SUBTRACT", 1.0, _ao(nb, 0.015))
    col = nb.mix(nb.math("MULTIPLY", crev, 0.85), col, (0.012, 0.007, 0.004))
    col = nb.mix(nb.math("MULTIPLY", crease, 0.5), col, (0.012, 0.007, 0.004))
    en = nb.noise(obj, 25.0, 4, 0.6)
    bev = _bevel(nb, 0.003)
    edge = nb.math("MULTIPLY", _hard_edges(nb, bev, 0.02, 0.10), nb.ramp(en.outputs["Fac"], [(0.4, 0.0), (0.62, 1.0)]))
    col = nb.mix(nb.math("MULTIPLY", edge, scuff), col, (light[0] * 1.6, light[1] * 1.6, light[2] * 1.6))
    dn = nb.noise(obj, 12.0, 6, 0.6)
    col = nb.mix(nb.math("MULTIPLY", nb.ramp(dn.outputs["Fac"], [(0.55, 0.0), (0.8, 1.0)]), dirt), col,
                 (0.07, 0.06, 0.05))
    r = nb.mixf(crev, rough, 0.85)
    r = nb.mixf(edge, r, rough * 0.6)
    h = nb.math("ADD", nb.math("MULTIPLY", grain, 0.35), nb.math("MULTIPLY", crease, -0.6))
    h = nb.math("ADD", h, nb.math("MULTIPLY", nb.noise(obj, 40.0, 5, 0.6).outputs["Fac"], 0.6))
    p = nb.principled(Base_Color=col, Roughness=r, Coat_Weight=0.05, Specular_IOR_Level=0.35,
                      Normal=nb.bump(h, 0.45, 0.0012, normal=bev))
    nb.output(p.outputs[0])
    m.diffuse_color = (*base, 1)
    return m


def rope(path, r, up=None, closed=False, lay=None, strands=3, n=6):
    """Three-strand laid rope swept along a path (whole number of turns on closed loops: no seam)."""
    path = [V(p) for p in path]
    total = path_length(path + ([path[0]] if closed else []))
    lay = lay or 7.0 * r
    lay = total / max(1, round(total / lay))
    core = resample(path, max(12, int(total / (lay / 12))), closed)
    fr = frames_along(core, up, closed)
    acc = [0.0]
    for a, b in zip(core, core[1:]):
        acc.append(acc[-1] + (b - a).length)
    md = MD()
    for st in range(strands):
        pts = [p + (Nn * math.cos(TAU * (st / strands + acc[i] / lay)) + B * math.sin(TAU * (st / strands + acc[i] / lay)))
               * r * 0.56 for i, (p, (T, Nn, B)) in enumerate(zip(core, fr))]
        md.add(sweep(pts, circle_profile(r * 0.50, n), closed_path=closed, up=lambda i, p, c=core: p - c[i],
                     cap0=not closed, cap1=not closed))
    return md


def mat_rope(name="Rope_Hemp"):
    m = new_mat(name)
    nb = NB(m)
    tc = nb.texcoord()
    obj = tc.outputs["Object"]
    fl = nb.noise(nb.mapping(tc.outputs["UV"], (70.0, 260.0, 1.0)), 1.0, 3, 0.55).outputs["Fac"]
    col = nb.mix(nb.ramp(nb.noise(obj, 9.0, 6, 0.6).outputs["Fac"], [(0.3, 0.0), (0.75, 1.0)]), (0.085, 0.048, 0.024),
                 (0.17, 0.105, 0.055))
    col = nb.mix(nb.math("MULTIPLY", nb.ramp(fl, [(0.35, 1.0), (0.6, 0.0)]), 0.6), col, (0.035, 0.020, 0.010))
    col = nb.mix(nb.math("MULTIPLY", nb.math("SUBTRACT", 1.0, _ao(nb, 0.004)), 0.9), col, (0.012, 0.008, 0.005))
    col = nb.mix(nb.math("MULTIPLY", _updust(nb, obj, 12.0), 0.4), col, (0.12, 0.10, 0.08))
    h = nb.math("ADD", nb.math("MULTIPLY", fl, 0.8), nb.math("MULTIPLY", nb.noise(obj, 600.0, 2, 0.5).outputs["Fac"], 0.3))
    p = nb.principled(Base_Color=col, Roughness=0.88, Sheen_Weight=0.6, Sheen_Roughness=0.5, Sheen_Tint=(0.9, 0.8, 0.65),
                      Specular_IOR_Level=0.3, Normal=nb.bump(h, 0.5, 0.0006))
    nb.output(p.outputs[0])
    return m


def mat_gourd(name="Gourd_Calabash", base=(0.20, 0.062, 0.020), light=(0.46, 0.18, 0.06), dark=(0.045, 0.016, 0.008)):
    """Dried lacquered calabash: mottled orange-brown with sap/smoke blotches, chips, smudged gloss."""
    m = new_mat(name)
    nb = NB(m)
    tc = nb.texcoord()
    obj = tc.outputs["Object"]
    n1 = nb.noise(obj, 11.0, 6, 0.62, distortion=0.6)
    col = nb.ramp(n1.outputs["Fac"], [(0.30, dark), (0.48, base), (0.70, light)])
    vb = nb.n("ShaderNodeTexVoronoi", (-900, -400), feature="F1")
    vb.inputs["Scale"].default_value = 18.0
    nb.link(obj, vb.inputs["Vector"])
    blot = nb.math("MULTIPLY", nb.ramp(vb.outputs["Distance"], [(0.0, 1.0), (0.22, 0.0)]),
                   nb.ramp(nb.noise(obj, 5.0, 4, 0.5).outputs["Fac"], [(0.45, 0.0), (0.6, 1.0)]))
    col = nb.mix(nb.math("MULTIPLY", blot, 0.8), col, dark)
    speck = nb.ramp(nb.noise(obj, 320.0, 2, 0.5).outputs["Fac"], [(0.70, 0.0), (0.74, 1.0)])
    col = nb.mix(nb.math("MULTIPLY", speck, 0.7), col, (0.55, 0.36, 0.18))
    crev = nb.math("SUBTRACT", 1.0, _ao(nb, 0.02))
    col = nb.mix(nb.math("MULTIPLY", crev, 0.9), col, (0.03, 0.02, 0.014))
    upd = nb.math("MULTIPLY", _updust(nb, obj, 14.0), 0.45)
    col = nb.mix(upd, col, (0.12, 0.10, 0.08))
    occl = nb.math("MAXIMUM", upd, crev)
    rough = nb.mixf(occl, nb.ramp(nb.noise(obj, 6.0, 5, 0.6).outputs["Fac"], [(0.35, 0.18), (0.7, 0.42)]), 0.8)
    h = nb.math("ADD", nb.math("MULTIPLY", nb.noise(obj, 90.0, 4, 0.6).outputs["Fac"], 0.5),
                nb.math("MULTIPLY", speck, -0.6))
    p = nb.principled(Base_Color=col, Roughness=rough, Coat_Weight=0.6, Coat_Roughness=0.08, Specular_IOR_Level=0.5,
                      Normal=nb.bump(h, 0.12, 0.0008))
    nb.link(nb.math("SUBTRACT", 0.6, nb.math("MULTIPLY", occl, 0.6)), p.inputs["Coat Weight"])
    nb.output(p.outputs[0])
    return m


def mat_cast_iron(name, base=(0.014, 0.013, 0.012), rust=(0.10, 0.042, 0.016), rough=0.62, hammer=45.0):
    """Hammered, pitted cast iron with brown oxide in the pits and rubbed lighter high spots."""
    m = new_mat(name)
    nb = NB(m)
    tc = nb.texcoord()
    obj = tc.outputs["Object"]
    hv = nb.n("ShaderNodeTexVoronoi", (-900, 0), feature="SMOOTH_F1")
    hv.inputs["Scale"].default_value = hammer
    nb.link(obj, hv.inputs["Vector"])
    dent = hv.outputs["Distance"]
    pits = nb.ramp(nb.noise(obj, 650.0, 2, 0.5).outputs["Fac"], [(0.60, 0.0), (0.66, 1.0)])
    h = nb.math("SUBTRACT", dent, nb.math("MULTIPLY", pits, 0.35))
    crev = nb.math("SUBTRACT", 1.0, _ao(nb, 0.015))
    rustm = nb.math("MAXIMUM", nb.ramp(nb.noise(obj, 8.0, 8, 0.65, distortion=0.3).outputs["Fac"], [(0.64, 0.0), (0.80, 0.5)]),
                    nb.math("MULTIPLY", nb.ramp(crev, [(0.3, 0.0), (0.8, 1.0)]), 0.5))
    rustm = nb.math("MAXIMUM", rustm, nb.math("MULTIPLY", pits, 0.6))
    hiq = nb.ramp(dent, [(0.55, 0.0), (0.85, 1.0)])
    col = nb.mix(rustm, nb.mix(nb.math("MULTIPLY", hiq, 0.6), base, (0.085, 0.080, 0.075)), rust)
    p = nb.principled(Base_Color=col, Metallic=nb.mixf(rustm, nb.mixf(hiq, 0.25, 0.7), 0.0),
                      Roughness=nb.mixf(rustm, nb.mixf(hiq, rough, 0.34), 0.92), Specular_IOR_Level=0.35,
                      Normal=nb.bump(h, 0.35, 0.002))
    nb.output(p.outputs[0])
    return m


def mat_forged(name, base=(0.045, 0.045, 0.050), polish=(0.50, 0.50, 0.52), rust=(0.10, 0.040, 0.015)):
    """Dark forged steel: polished edge bevels, cross-grind lines, rust and grime in the recesses."""
    m = new_mat(name)
    nb = NB(m)
    tc = nb.texcoord()
    obj = tc.outputs["Object"]
    bev = _bevel(nb, 0.0012)
    edge = _hard_edges(nb, bev, 0.01, 0.06, False)
    grind = nb.noise(nb.mapping(obj, (1.0, 1.0, 40.0)), 120.0, 3, 0.5).outputs["Fac"]
    rn = nb.ramp(nb.noise(obj, 12.0, 8, 0.65).outputs["Fac"], [(0.58, 0.0), (0.72, 1.0)])
    rustm = nb.math("MAXIMUM", nb.math("MULTIPLY", rn, nb.math("SUBTRACT", 1.0, edge)),
                    nb.math("MULTIPLY", nb.math("SUBTRACT", 1.0, _ao(nb, 0.01)), 0.8))
    col = nb.mix(rustm, nb.mix(edge, base, polish), rust)
    r = nb.mixf(rustm, nb.mixf(edge, 0.42, 0.16), 0.9)
    tg = nb.n("ShaderNodeTangent", (-600, -800))
    tg.direction_type = "RADIAL"
    tg.axis = "Z"
    hgt = nb.math("ADD", nb.math("MULTIPLY", grind, 0.3), nb.math("MULTIPLY", nb.noise(obj, 700.0, 2, 0.5).outputs["Fac"], 0.2))
    p = nb.principled(Base_Color=col, Metallic=nb.mixf(rustm, 0.95, 0.0), Roughness=r, Anisotropic=0.55,
                      Normal=nb.bump(hgt, 0.15, 0.0005, normal=bev))
    nb.link(tg.outputs["Tangent"], p.inputs["Tangent"])
    nb.output(p.outputs[0])
    return m
