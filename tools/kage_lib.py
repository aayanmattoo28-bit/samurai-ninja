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

    def add(self, other, mi=None):
        off = len(self.v)
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


def _ao(nb, distance=0.03, only_local=False):
    """Ambient-occlusion factor (1 = open, 0 = deep crevice)."""
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


def _gold_shader(nb, vec, tint=(0.78, 0.53, 0.22), rough=0.3, tarnish=0.35, scale=18.0):
    n = nb.noise(vec, scale, 8, 0.6)
    tar = nb.ramp(n.outputs["Fac"], [(0.35, 0.0), (0.75, 1.0)])
    col = nb.mix(nb.math("MULTIPLY", tar, tarnish), tint, (0.20, 0.12, 0.05))
    # dark tarnish packed in crevices, polished bright on the high points
    crev = nb.math("SUBTRACT", 1.0, _ao(nb, 0.012))
    col = nb.mix(nb.math("MULTIPLY", crev, 0.85), col, (0.05, 0.03, 0.012))
    edge = _edges(nb)
    col = nb.mix(nb.math("MULTIPLY", edge, 0.5), col, (min(1, tint[0] * 1.25), min(1, tint[1] * 1.25),
                                                       min(1, tint[2] * 1.2)))
    r = nb.ramp(n.outputs["Fac"], [(0.2, rough * 0.7), (0.8, rough * 1.6)])
    r = nb.mixf(edge, r, rough * 0.5)
    r = nb.mixf(crev, r, 0.7)
    g = nb.principled(Base_Color=col, Metallic=1.0, Roughness=r)
    return g


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
                flip_u=False, straw=False, dust=0.25):
    """Black urushi lacquer with optional gilded pattern mask."""
    m = new_mat(name)
    nb = NB(m)
    tc = nb.texcoord()
    obj = tc.outputs["Object"]
    # base color variation + dust
    n1 = nb.noise(obj, 9.0, 8, 0.6)
    n2 = nb.noise(obj, 55.0, 4, 0.5)
    basecol = nb.mix(nb.ramp(n1.outputs["Fac"], [(0.3, 0.0), (0.8, 1.0)]), base, (0.035, 0.026, 0.020))
    dustmask = nb.math("MULTIPLY", nb.ramp(n2.outputs["Fac"], [(0.55, 0.0), (0.8, 1.0)]), dust)
    basecol = nb.mix(dustmask, basecol, (0.10, 0.085, 0.07))
    rough = nb.mixf(dustmask, nb.math("ADD", nb.math("MULTIPLY", n1.outputs["Fac"], 0.25), 0.18), 0.8)
    # scratches
    sc = nb.noise(nb.mapping(obj, (60, 6, 60)), 1.0, 2, 0.5)
    scratch = nb.ramp(sc.outputs["Fac"], [(0.48, 0.0), (0.5, 1.0), (0.52, 0.0)])
    height = nb.math("MULTIPLY", scratch, 0.15)
    if straw:
        # woven straw: concentric + radial fine ridges
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
        basecol = nb.mix(band, basecol, (0.034, 0.024, 0.016))
        height = nb.math("ADD", height, nb.math("MULTIPLY", band, 0.8))
    # realism: dust packed into crevices, worn brown edges, dust settled on upward faces
    crev = nb.math("SUBTRACT", 1.0, _ao(nb, 0.025))
    basecol = nb.mix(nb.math("MULTIPLY", crev, 0.9), basecol, (0.050, 0.043, 0.036))
    rough = nb.mixf(crev, rough, 0.75)
    en = nb.noise(obj, 35.0, 4, 0.6)
    edge = nb.math("MULTIPLY", _edges(nb), nb.ramp(en.outputs["Fac"], [(0.4, 0.0), (0.6, 1.0)]))
    basecol = nb.mix(nb.math("MULTIPLY", edge, 0.75), basecol, (0.080, 0.048, 0.030))
    upd = nb.math("MULTIPLY", _updust(nb, obj), dust * 1.3)
    basecol = nb.mix(upd, basecol, (0.115, 0.098, 0.082))
    rough = nb.mixf(upd, rough, 0.85)
    lacq = nb.principled((200, 200), Base_Color=basecol, Roughness=rough, Coat_Weight=0.45,
                         Coat_Roughness=0.14, Specular_IOR_Level=0.5)
    nb.link(nb.math("SUBTRACT", 0.45, nb.math("MULTIPLY", nb.math("MAXIMUM", upd, crev), 0.45)),
            lacq.inputs["Coat Weight"])
    shader = lacq.outputs[0]
    if pattern:
        if mapping == "UV":
            vec = tc.outputs["UV"]
        else:
            vec = tc.outputs[mapping]
        if flip_u:
            vec = nb.mapping(vec, (-uv_scale[0], uv_scale[1], 1), (1, 0, 0), (0, 0, pattern_rot))
        else:
            vec = nb.mapping(vec, (uv_scale[0], uv_scale[1], 1), (0, 0, 0), (0, 0, pattern_rot))
        it = nb.img(pattern, vec, extension)
        mask = it.outputs["Color"]
        wn = nb.noise(obj, 25.0, 6, 0.6)
        wearm = nb.ramp(wn.outputs["Fac"], [(0.25, 1.0 - wear), (0.7, 1.0)])
        gm = nb.math("MULTIPLY", mask, wearm, clamp_=True)
        gold = _gold_shader(nb, obj, gold_tint, 0.42, 0.45, 25.0)
        mixs = nb.n("ShaderNodeMixShader", (450, 100))
        nb.link(gm, mixs.inputs[0])
        nb.link(shader, mixs.inputs[1])
        nb.link(gold.outputs[0], mixs.inputs[2])
        shader = mixs.outputs[0]
        height = nb.math("ADD", height, nb.math("MULTIPLY", mask, relief * 10))
    bmp = nb.bump(height, 0.25, 0.0004)
    if pattern:
        bmp = nb.bump(height, 0.35, 0.0008)
    nb.link(bmp, lacq.inputs["Normal"])
    if pattern:
        nb.link(bmp, gold.inputs["Normal"])
    nb.output(shader)
    m.diffuse_color = (*base, 1)
    m.roughness = 0.3
    return m


def mat_cloth(name, base=(0.016, 0.014, 0.014), print_img=None, print_scale=(1, 1), print_col=(0.30, 0.20, 0.09),
              print_strength=0.7, mapping="UV", extension="REPEAT", fade=(0.03, 0.026, 0.024), dust=0.35,
              sheen=0.18, weave=220.0, print_metal=0.25):
    m = new_mat(name)
    nb = NB(m)
    tc = nb.texcoord()
    obj = tc.outputs["Object"]
    n1 = nb.noise(obj, 4.0, 8, 0.65)
    col = nb.mix(nb.ramp(n1.outputs["Fac"], [(0.35, 0.0), (0.75, 1.0)]), base, fade)
    # dust toward the bottom (object z) + noise
    sep = nb.n("ShaderNodeSeparateXYZ", (-1000, -400))
    nb.link(tc.outputs["Object"], sep.inputs[0])
    n2 = nb.noise(obj, 14.0, 6, 0.6)
    dmask = nb.math("MULTIPLY", nb.ramp(n2.outputs["Fac"], [(0.5, 0.0), (0.85, 1.0)]), dust)
    col = nb.mix(dmask, col, (0.11, 0.09, 0.075))
    rough = 0.88
    metal = 0.0
    if print_img:
        vec = tc.outputs["UV"] if mapping == "UV" else tc.outputs[mapping]
        vec = nb.mapping(vec, (print_scale[0], print_scale[1], 1))
        it = nb.img(print_img, vec, extension, proj="BOX" if mapping != "UV" else "FLAT")
        pn = nb.noise(obj, 30.0, 5, 0.6)
        pmask = nb.math("MULTIPLY", it.outputs["Color"],
                        nb.ramp(pn.outputs["Fac"], [(0.3, 0.35), (0.65, 1.0)]))
        pmask = nb.math("MULTIPLY", pmask, print_strength, clamp_=True)
        col = nb.mix(pmask, col, print_col)
        rough = nb.mixf(pmask, 0.88, 0.55)
        metal = nb.mixf(pmask, 0.0, print_metal)
    # realism: deep shadow in folds (AO), dust on the lower hems and upward faces
    ao = _ao(nb, 0.05)
    col = nb.mix(nb.math("SUBTRACT", 1.0, ao), col, (0.004, 0.0035, 0.003))
    low = nb.ramp(sep.outputs[2], [(0.15, 1.0), (0.75, 0.0)])
    hem = nb.math("MULTIPLY", low, nb.ramp(nb.noise(obj, 6.0, 6, 0.6).outputs["Fac"], [(0.3, 0.2), (0.7, 1.0)]))
    col = nb.mix(nb.math("MULTIPLY", hem, dust * 0.9), col, (0.12, 0.10, 0.082))
    col = nb.mix(nb.math("MULTIPLY", _updust(nb, obj, 8.0), dust * 0.8), col, (0.11, 0.095, 0.08))
    # plain-weave threads (crosshatch) + slub noise
    wx = nb.n("ShaderNodeTexWave", (-900, -600), wave_type="BANDS", bands_direction="X")
    wx.inputs["Scale"].default_value = 520.0
    wx.inputs["Distortion"].default_value = 0.6
    nb.link(obj, wx.inputs["Vector"])
    wy = nb.n("ShaderNodeTexWave", (-900, -800), wave_type="BANDS", bands_direction="Z")
    wy.inputs["Scale"].default_value = 520.0
    wy.inputs["Distortion"].default_value = 0.6
    nb.link(obj, wy.inputs["Vector"])
    n3 = nb.noise(obj, 160.0, 3, 0.5)
    h = nb.math("ADD", nb.math("MULTIPLY", nb.math("MULTIPLY", wx.outputs["Fac"], wy.outputs["Fac"]), 0.6),
                nb.math("MULTIPLY", n3.outputs["Fac"], 0.5))
    fold = nb.noise(obj, 25.0, 4, 0.5)
    h = nb.math("ADD", h, nb.math("MULTIPLY", fold.outputs["Fac"], 1.5))
    bmp = nb.bump(h, 0.30, 0.0006)
    p = nb.principled(Base_Color=col, Roughness=rough, Metallic=metal, Sheen_Weight=max(sheen, 0.3),
                      Sheen_Roughness=0.5, Normal=bmp)
    nb.output(p.outputs[0])
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
    if dirt:
        en = nb.noise(obj, 40.0, 4, 0.6)
        edge = nb.math("MULTIPLY", _edges(nb), nb.ramp(en.outputs["Fac"], [(0.4, 0.0), (0.6, 1.0)]))
        col = nb.mix(nb.math("MULTIPLY", edge, 0.5 * min(1.0, dirt * 2)), col, (0.16, 0.12, 0.09))
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
    bmp = nb.bump(h, bump_str, 0.001)
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
    col = nb.ramp(z, [(0.70, (0.20, 0.14, 0.12)), (0.80, (0.30, 0.26, 0.24)), (0.845, (0.10, 0.05, 0.025)),
                      (0.93, (0.055, 0.028, 0.014)), (0.95, (0.004, 0.003, 0.003))])
    p = nb.principled(Base_Color=col, Roughness=0.25, Coat_Weight=0.6, Coat_Roughness=0.08)
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
    p = nb.principled(Base_Color=col, Roughness=nb.mixf(diamond, 0.55, 0.35), Sheen_Weight=0.4,
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
