"""Render settings, light rig, turnaround/detail cameras, courtyard environment, props showcase."""
import math

import bpy
from mathutils import Euler, Vector

from kage_lib import (MD, NB, TAU, V, collection, grid, lathe, lin, mat_simple, mod_subsurf, new_mat, to_obj,
                      box, RNG, fbm, uv_sphere, tube, sweep, rect_profile, catmull_path, lerp, clamp, smooth)
from kage_mats import M

# view name -> (camera location, rotation (deg), light-rig z rotation)
TURNAROUND = {
    "Front": ((0.0, -6.3, 1.0), (90, 0, 0), 0),
    "Left": ((6.3, 0.0, 1.0), (90, 0, 90), 90),
    "Right": ((-6.3, 0.0, 1.0), (90, 0, -90), -90),
    "Back": ((0.0, 6.3, 1.0), (90, 0, 180), 180),
}
TURN_FOCAL = 70

# detail cameras: name -> (location, target, focal mm)
DETAILS = {
    "FrontWaist": ((-0.02, -1.15, 1.10), (-0.02, -0.1, 1.00), 50),
    "BackWaist": ((0.04, 1.15, 1.02), (0.04, 0.1, 0.94), 50),
    "Kasa": ((-0.42, -0.62, 1.93), (0.0, 0.0, 1.80), 50),
    "Mask": ((-0.18, -0.62, 1.74), (0.0, 0.0, 1.70), 50),
    "Armor": ((0.85, -0.25, 1.40), (0.30, 0.0, 1.40), 50),
    "Fabric": ((-0.07, 0.66, 1.26), (-0.075, 0.20, 1.24), 50),
    "LegArmor": ((0.48, -0.78, 0.34), (0.24, -0.02, 0.24), 50),
}


def setup_render(sc):
    sc.render.engine = "CYCLES"
    cy = sc.cycles
    cy.device = "CPU"
    cy.samples = 128
    cy.use_denoising = True
    try:
        cy.denoiser = "OPENIMAGEDENOISE"
    except Exception:
        pass
    cy.max_bounces = 8
    cy.transparent_max_bounces = 16
    cy.caustics_reflective = False
    cy.caustics_refractive = False
    sc.render.resolution_x = 900
    sc.render.resolution_y = 1800
    sc.render.film_transparent = False
    sc.view_settings.view_transform = "AgX"
    try:
        sc.view_settings.look = "AgX - Medium High Contrast"
    except Exception:
        pass
    sc.view_settings.exposure = 0.05
    try:
        compositor(sc)
    except Exception as e:  # compositor is a finishing touch only
        print("compositor setup skipped:", e)
    # EEVEE settings (for viewport / quick renders)
    try:
        ee = sc.eevee
        ee.use_shadows = True
        ee.use_raytracing = True
    except Exception:
        pass


def compositor(sc):
    """Camera-like finish: soft highlight bloom, gentle grade, saturation and a vignette."""
    sc.use_nodes = True
    nt = sc.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    L = nt.links.new
    rl = nt.nodes.new("CompositorNodeRLayers")
    gl = nt.nodes.new("CompositorNodeGlare")
    gl.glare_type = "FOG_GLOW"
    gl.quality = "MEDIUM"
    gl.threshold = 0.85
    gl.size = 7
    gl.mix = -0.82
    cb = nt.nodes.new("CompositorNodeColorBalance")
    cb.correction_method = "LIFT_GAMMA_GAIN"
    cb.lift = (0.985, 0.985, 1.0)
    cb.gamma = (1.0, 0.995, 0.99)
    cb.gain = (1.0, 0.99, 1.0)
    hs = nt.nodes.new("CompositorNodeHueSat")
    hs.inputs["Saturation"].default_value = 1.04
    em = nt.nodes.new("CompositorNodeEllipseMask")
    em.width = 0.98
    em.height = 0.98
    bl = nt.nodes.new("CompositorNodeBlur")
    bl.filter_type = "FAST_GAUSS"
    bl.use_relative = True
    bl.factor_x = 30
    bl.factor_y = 30
    vg = nt.nodes.new("CompositorNodeMapRange")
    vg.inputs["To Min"].default_value = 0.74
    vg.inputs["To Max"].default_value = 1.0
    mul = nt.nodes.new("CompositorNodeMixRGB")
    mul.blend_type = "MULTIPLY"
    mul.inputs["Fac"].default_value = 1.0
    comp = nt.nodes.new("CompositorNodeComposite")
    L(rl.outputs["Image"], gl.inputs["Image"])
    L(gl.outputs["Image"], cb.inputs["Image"])
    L(cb.outputs["Image"], hs.inputs["Image"])
    L(em.outputs["Mask"], bl.inputs["Image"])
    L(bl.outputs["Image"], vg.inputs["Value"])
    L(hs.outputs["Image"], mul.inputs[1])
    L(vg.outputs["Value"], mul.inputs[2])
    L(mul.outputs["Image"], comp.inputs["Image"])


def world(sc):
    """Overcast dusk sky: warm horizon glow, purple-grey clouds."""
    w = bpy.data.worlds.new("Dusk_Sky")
    sc.world = w
    nb = NB(w)
    tc = nb.n("ShaderNodeTexCoord", (-900, 0))
    sep = nb.n("ShaderNodeSeparateXYZ", (-700, 0))
    nb.link(tc.outputs["Generated"], sep.inputs[0])
    sky = nb.ramp(sep.outputs[2], [(0.0, (0.05, 0.04, 0.04)), (0.02, (0.55, 0.32, 0.22)), (0.10, (0.36, 0.27, 0.34)),
                                   (0.35, (0.17, 0.16, 0.26)), (1.0, (0.07, 0.08, 0.14))])
    mp = nb.mapping(tc.outputs["Generated"], (2.0, 2.0, 6.0))
    cl = nb.noise(mp, 2.5, 8, 0.62, distortion=0.4)
    cloud = nb.ramp(cl.outputs["Fac"], [(0.42, 0.0), (0.68, 1.0)])
    above = nb.ramp(sep.outputs[2], [(0.01, 0.0), (0.08, 1.0)])
    cmask = nb.math("MULTIPLY", cloud, above)
    col = nb.mix(nb.math("MULTIPLY", cmask, 0.75), sky, (0.46, 0.38, 0.42))
    bg = nb.n("ShaderNodeBackground", (200, 0))
    nb.link(col, bg.inputs["Color"])
    bg.inputs["Strength"].default_value = 0.55
    o = nb.n("ShaderNodeOutputWorld", (400, 0))
    nb.link(bg.outputs[0], o.inputs["Surface"])


def area(name, coll, loc, target, power, color, size, parent):
    ld = bpy.data.lights.new(name, "AREA")
    ld.energy = power
    ld.color = color
    ld.shape = "DISK"
    ld.size = size
    ob = bpy.data.objects.new(name, ld)
    coll.objects.link(ob)
    ob.location = loc
    d = V(target) - V(loc)
    ob.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()
    ob.parent = parent
    return ob


def build_lights(sc):
    coll = collection("Lighting")
    world(sc)
    rig = bpy.data.objects.new("Light_Rig", None)
    coll.objects.link(rig)
    rig.empty_display_size = 1.0
    c = (0, 0, 1.1)
    area("Key_Warm", coll, (-3.2, -4.5, 4.2), c, 220, (1.0, 0.80, 0.60), 3.0, rig)
    area("Fill_Cool", coll, (3.8, -3.6, 1.8), c, 95, (0.62, 0.62, 0.90), 3.0, rig)
    area("Rim_Orange_L", coll, (-3.0, 3.8, 2.8), c, 520, (1.0, 0.64, 0.42), 2.0, rig)
    area("Rim_Red_R", coll, (3.2, 3.5, 2.2), c, 300, (1.0, 0.52, 0.40), 2.0, rig)
    area("Face_Fill", coll, (0.4, -2.2, 1.55), (0, 0, 1.72), 7, (1.0, 0.82, 0.68), 0.6, rig)
    area("Top_Kasa", coll, (0.0, -1.0, 4.5), (0, 0, 1.8), 25, (1.0, 0.85, 0.7), 1.2, rig)
    area("Low_Bounce", coll, (0.0, -3.0, 0.2), (0, 0, 0.6), 12, (0.8, 0.6, 0.5), 3.0, rig)
    sun = bpy.data.lights.new("Sun_Low", "SUN")
    sun.energy = 3.0
    sun.color = (1.0, 0.86, 0.72)
    sun.angle = math.radians(3)
    so = bpy.data.objects.new("Sun_Low", sun)
    coll.objects.link(so)
    so.rotation_euler = Euler((math.radians(62), 0, math.radians(-115)))
    so.parent = rig
    return rig


def make_camera(name, coll, loc, rot=None, target=None, focal=100, ortho=False):
    cd = bpy.data.cameras.new(name)
    cd.lens = focal
    cd.sensor_fit = "VERTICAL"
    cd.sensor_height = 24
    cd.clip_start = 0.05
    cd.clip_end = 400
    ob = bpy.data.objects.new(name, cd)
    coll.objects.link(ob)
    ob.location = loc
    if rot is not None:
        ob.rotation_euler = Euler([math.radians(a) for a in rot])
    elif target is not None:
        d = V(target) - V(loc)
        ob.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()
    return ob


def build_cameras(sc):
    coll = collection("Cameras")
    first = None
    for name, (loc, rot, _) in TURNAROUND.items():
        cam = make_camera("CAM_" + name, coll, loc, rot=rot, focal=TURN_FOCAL)
        cam.data.dof.use_dof = True
        cam.data.dof.focus_distance = 6.3
        cam.data.dof.aperture_fstop = 11.0
        first = first or cam
    for name, (loc, tgt, f) in DETAILS.items():
        cam = make_camera("CAM_Detail_" + name, coll, loc, target=tgt, focal=f)
        cam.data.dof.use_dof = True
        cam.data.dof.focus_distance = (V(tgt) - V(loc)).length
        cam.data.dof.aperture_fstop = 2.8
    sc.camera = first


# =============================================================================
# Environment: stone courtyard, castle keep, maples, lantern, banner
# =============================================================================
def mat_stone(name="Stone_Courtyard"):
    """Large rectangular granite flagstones in running bond, cracked, with wet patches."""
    m = new_mat(name)
    nb = NB(m)
    tc = nb.texcoord()
    obj = tc.outputs["Object"]
    br = nb.n("ShaderNodeTexBrick", (-900, 200))
    br.offset = 0.5
    br.offset_frequency = 2
    br.squash = 1.0
    br.squash_frequency = 2
    br.inputs["Scale"].default_value = 1.0
    br.inputs["Mortar Size"].default_value = 0.012
    br.inputs["Mortar Smooth"].default_value = 0.2
    br.inputs["Bias"].default_value = 0.0
    br.inputs["Brick Width"].default_value = 0.95
    br.inputs["Row Height"].default_value = 0.62
    br.inputs["Color1"].default_value = (0.085, 0.083, 0.082, 1)
    br.inputs["Color2"].default_value = (0.060, 0.058, 0.058, 1)
    br.inputs["Mortar"].default_value = (0.0, 0.0, 0.0, 1)
    dn = nb.noise(obj, 4.0, 4, 0.5)
    warped = nb.n("ShaderNodeVectorMath", (-1100, 200))
    warped.operation = "ADD"
    nb.link(obj, warped.inputs[0])
    sc_ = nb.n("ShaderNodeVectorMath", (-1100, 0))
    sc_.operation = "SCALE"
    nb.link(dn.outputs["Color"], sc_.inputs[0])
    sc_.inputs["Scale"].default_value = 0.03
    nb.link(sc_.outputs[0], warped.inputs[1])
    nb.link(warped.outputs[0], br.inputs["Vector"])
    mortar = br.outputs["Fac"]
    n = nb.noise(obj, 3.0, 10, 0.65)
    base = nb.mix(nb.ramp(n.outputs["Fac"], [(0.35, 0.0), (0.7, 1.0)]), br.outputs["Color"], (0.07, 0.062, 0.058))
    cr = nb.noise(obj, 6.0, 12, 0.75, distortion=0.6)
    crack = nb.ramp(cr.outputs["Fac"], [(0.495, 0.0), (0.5, 1.0), (0.505, 0.0)])
    col = nb.mix(nb.math("MAXIMUM", mortar, nb.math("MULTIPLY", crack, 0.7)), base, (0.015, 0.013, 0.012))
    wet = nb.ramp(nb.noise(obj, 0.7, 4, 0.5).outputs["Fac"], [(0.50, 0.0), (0.58, 1.0)])
    col = nb.mix(nb.math("MULTIPLY", wet, 0.5), col, (0.03, 0.028, 0.027))
    rough = nb.mixf(wet, 0.72, 0.12)
    grit = nb.noise(obj, 60.0, 8, 0.7)
    h = nb.math("ADD", nb.math("MULTIPLY", nb.math("SUBTRACT", 1.0, mortar), 1.0),
                nb.math("ADD", nb.math("MULTIPLY", grit.outputs["Fac"], 0.25), nb.math("MULTIPLY", crack, -0.5)))
    p = nb.principled(Base_Color=col, Roughness=rough, Normal=nb.bump(h, 0.5, 0.01))
    nb.output(p.outputs[0])
    return m


def fog_wrap(mat, fog_col=(0.36, 0.30, 0.32), near=60.0, far=480.0, max_fac=0.22):
    """Blend a material's surface toward a haze colour with camera distance (aerial perspective)."""
    nt = mat.node_tree
    out = [n for n in nt.nodes if n.type == "OUTPUT_MATERIAL"][0]
    src = out.inputs["Surface"].links[0].from_socket
    cam = nt.nodes.new("ShaderNodeCameraData")
    mr = nt.nodes.new("ShaderNodeMapRange")
    mr.inputs["From Min"].default_value = near
    mr.inputs["From Max"].default_value = far
    mr.inputs["To Max"].default_value = max_fac
    nt.links.new(cam.outputs["View Distance"], mr.inputs["Value"])
    em = nt.nodes.new("ShaderNodeEmission")
    em.inputs["Color"].default_value = (*fog_col, 1)
    em.inputs["Strength"].default_value = 1.0
    mx = nt.nodes.new("ShaderNodeMixShader")
    nt.links.new(mr.outputs[0], mx.inputs[0])
    nt.links.new(src, mx.inputs[1])
    nt.links.new(em.outputs[0], mx.inputs[2])
    nt.links.new(mx.outputs[0], out.inputs["Surface"])
    return mat


def mat_foliage(name):
    """Red/orange maple foliage with leafy cut-outs (voronoi alpha) so crowns read as leaves, not blobs."""
    m = new_mat(name)
    nb = NB(m)
    tc = nb.texcoord()
    obj = tc.outputs["Object"]
    vor = nb.n("ShaderNodeTexVoronoi", (-900, 200), feature="F1")
    vor.inputs["Scale"].default_value = 3.2
    nb.link(obj, vor.inputs["Vector"])
    leafmask = nb.ramp(vor.outputs["Distance"], [(0.52, 1.0), (0.62, 0.0)])
    n = nb.noise(obj, 0.8, 6, 0.6)
    col = nb.ramp(n.outputs["Fac"], [(0.30, (0.22, 0.010, 0.008)), (0.50, (0.55, 0.045, 0.015)),
                                     (0.70, (0.78, 0.16, 0.03)), (0.85, (0.62, 0.30, 0.05))])
    p = nb.principled(Base_Color=col, Roughness=0.6, Subsurface_Weight=0.15)
    tr = nb.n("ShaderNodeBsdfTransparent", (200, -300))
    mx = nb.n("ShaderNodeMixShader", (450, 0))
    nb.link(leafmask, mx.inputs[0])
    nb.link(tr.outputs[0], mx.inputs[1])
    nb.link(p.outputs[0], mx.inputs[2])
    nb.output(mx.outputs[0])
    m.diffuse_color = (0.5, 0.06, 0.02, 1)
    return m


def build_environment(sc):
    coll = collection("Environment_Courtyard")
    stone = fog_wrap(mat_stone())
    plaster = fog_wrap(mat_simple("Castle_Plaster", (0.72, 0.66, 0.60), rough=0.8, var_col=(0.50, 0.45, 0.40),
                                  dirt=0.4))
    roof = fog_wrap(mat_simple("Castle_Roof_Tiles", (0.012, 0.014, 0.018), rough=0.45, metal=0.2, wave="BANDS",
                               wave_dir="X", wave_coord="Object", wave_scale=25.0, wave_str=1.0, bump_str=0.8))
    roof_gold = fog_wrap(mat_simple("Castle_Roof_Gold", (0.55, 0.38, 0.15), rough=0.35, metal=1.0))
    wood = M.get("wood")
    dark_wood = fog_wrap(mat_simple("Castle_Dark_Wood", (0.025, 0.02, 0.018), rough=0.7))
    stonewall = fog_wrap(mat_simple("Castle_Stone_Base", (0.12, 0.11, 0.10), rough=0.85, var_col=(0.06, 0.055, 0.05),
                                    var_scale=1.5, bump_scale=3.0, bump_str=0.8))
    maple = fog_wrap(mat_foliage("Maple_Leaves"))
    pine = fog_wrap(mat_simple("Pine_Needles", (0.02, 0.035, 0.022), rough=0.8, var_col=(0.06, 0.05, 0.03),
                               var_scale=2.0, bump_scale=10.0, bump_str=0.8))
    hill = fog_wrap(mat_simple("Hillside", (0.05, 0.045, 0.035), rough=0.9, var_col=(0.16, 0.04, 0.02),
                               var_scale=0.08, bump_scale=0.6, bump_str=0.6))
    bark = fog_wrap(mat_simple("Bark", (0.04, 0.03, 0.025), rough=0.9, bump_scale=20.0, bump_str=0.8))
    banner_red = mat_simple("Banner_Red", (0.22, 0.015, 0.015), rough=0.8, sheen=0.4, var_col=(0.12, 0.01, 0.01))
    leaf_ground = mat_simple("Fallen_Leaves", (0.20, 0.02, 0.012), rough=0.7, var_col=(0.38, 0.09, 0.02),
                             var_scale=3.0)

    # ground: flagstones
    g = grid(lambda u, v, i, j: (u, v, 0.0), lin(-40, 40, 40), lin(-40, 40, 40))
    to_obj("Courtyard_Flagstones", g, stone, coll)

    # fallen maple leaves
    leaves = MD()
    for k in range(1600):
        r = 0.4 + RNG.random() ** 0.8 * 12.0
        a = RNG.uniform(0, TAU)
        x, y = r * math.cos(a), r * math.sin(a)
        s_ = RNG.uniform(0.022, 0.04)
        rot = RNG.uniform(0, TAU)
        base = len(leaves.v)
        leaves.v.append(V((x, y, 0.004)))
        for q in range(7):
            aa = rot + TAU * q / 7
            rr = s_ * (1.0 if q % 2 == 0 else 0.5)
            leaves.v.append(V((x + rr * math.cos(aa), y + rr * math.sin(aa), 0.002 + RNG.uniform(0, 0.004))))
        for q in range(7):
            leaves.f.append((base, base + 1 + q, base + 1 + (q + 1) % 7))
            leaves.uv.append([(0.5, 0.5), (0, 0), (1, 0)])
            leaves.mi.append(0)
    to_obj("Fallen_Maple_Leaves", leaves, leaf_ground, coll, smooth=False)

    # terrain: courtyard edge drops to a moat, then the castle hill rises all around
    def hill_h(r, a=0.0):
        if r < 17.0:
            return 0.0
        if r < 20.0:
            return -3.5 * smooth((r - 17.0) / 3.0)
        if r < 28.0:
            return -3.5
        return -3.5 + (r - 28.0) * 0.050 + 0.012 * max(0.0, r - 150.0) ** 1.5 + \
            2.0 * fbm(V((math.cos(a) * 4, math.sin(a) * 4, r * 0.03)))

    def terrain(u, v, i, j):
        r = lerp(17.0, 320.0, v ** 1.6)
        return (r * math.cos(u), r * math.sin(u), hill_h(r, u) - 0.02)

    to_obj("Castle_Hill", grid(terrain, lin(0, TAU, 128), lin(0, 1, 48), closed_u=True), hill, coll)
    water = mat_simple("Moat_Water", (0.02, 0.025, 0.03), rough=0.05, coat=1.0)
    wg = grid(lambda u, v, i, j: (lerp(16.8, 30.0, v) * math.cos(u), lerp(16.8, 30.0, v) * math.sin(u), -2.6),
              lin(0, TAU, 96), lin(0, 1, 2), closed_u=True)
    to_obj("Moat_Water", wg, water, coll)

    # low stone parapet + wooden railing at the courtyard edge
    walls = MD()

    def wf(u, v, i, j):
        rr = 16.6 + 0.25 * (1 - v)
        return (rr * math.cos(u), rr * math.sin(u), -3.5 + v * 3.55)

    walls.add(grid(wf, lin(0, TAU, 160), lin(0, 1, 4), closed_u=True))
    to_obj("Courtyard_Stone_Parapet", walls, stonewall, coll)
    fence = MD()
    for k in range(220):
        a_ = TAU * k / 220
        bx_ = box(0.14, 0.14, 0.85)
        bx_.translate((16.45 * math.cos(a_), 16.45 * math.sin(a_), 0.45))
        fence.add(bx_)
    for zr in (0.40, 0.82):
        ring = [V((16.45 * math.cos(TAU * k / 200), 16.45 * math.sin(TAU * k / 200), zr)) for k in range(200)]
        fence.add(sweep(ring, rect_profile(0.08, 0.12), up=(0, 0, 1), closed_path=True))
    to_obj("Courtyard_Railing", fence, dark_wood, coll, smooth=False)

    # castle keeps (tenshu): stacked tiers with flared, upturned roofs + gold ridge ornaments
    def keep(cx, cy, cz, scale, tiers, rot=0.0, name="Castle_Keep"):
        md_wall, md_roof, md_base, md_gold, md_win = MD(), MD(), MD(), MD(), MD()

        def base_fn(u, v, i, j):
            # battered stone base (ishigaki): wider at the bottom
            a = u * TAU
            ca, sa = math.cos(a), math.sin(a)
            m = max(abs(ca), abs(sa))
            sx, sy = ca / m, sa / m
            w = lerp(19 * scale, 14 * scale, v ** 0.7)
            d = lerp(17 * scale, 12 * scale, v ** 0.7)
            return (sx * w / 2, sy * d / 2, -3.0 + v * (3.0 + 3.2 * scale))

        md_base.add(grid(base_fn, lin(0, 1, 64), lin(0, 1, 6), closed_u=True))
        z = 3.2 * scale
        w, d = 11.5 * scale, 9.5 * scale
        for t in range(tiers):
            h = 3.4 * scale
            wb = box(w, d, h)
            wb.translate((0, 0, z + h / 2))
            md_wall.add(wb)
            # dark window bands
            for side in (-1, 1):
                for q in range(int(w / (1.6 * scale))):
                    win = box(0.7 * scale, 0.05, 0.9 * scale)
                    win.translate((-w / 2 + (q + 0.7) * 1.6 * scale, side * (d / 2 + 0.02), z + h * 0.55))
                    md_win.add(win)
            z += h
            ow, od = w * 1.40, d * 1.40
            rh = 1.8 * scale

            def rf(u, v, i, j, ow=ow, od=od, w=w, d=d, z=z, rh=rh):
                a = u * TAU
                ca, sa = math.cos(a), math.sin(a)
                m = max(abs(ca), abs(sa))
                sx, sy = ca / m, sa / m
                ww = lerp(ow, w * 0.52, v ** 0.75)
                dd = lerp(od, d * 0.52, v ** 0.75)
                corner = abs(sx * sy) ** 3
                lift = 0.9 * scale * (1 - v) ** 3 * corner
                return (sx * ww / 2, sy * dd / 2, z - 0.35 * scale + rh * (v ** 1.4) + lift)

            md_roof.add(grid(rf, lin(0, 1, 96), lin(0, 1, 8), closed_u=True))
            # chidori gable on the front of the roof
            if t % 2 == 0:
                gb = MD()
                gw = w * 0.45
                gb.v = [V((-gw / 2, -od / 2 * 0.8, z)), V((gw / 2, -od / 2 * 0.8, z)),
                        V((0, -od / 2 * 0.8, z + rh * 0.9)), V((0, -d * 0.2, z + rh * 0.9))]
                gb.f = [(0, 1, 2), (0, 2, 3), (1, 3, 2)]
                gb.uv = [[(0, 0), (1, 0), (0.5, 1)]] * 3
                gb.mi = [0] * 3
                md_roof.add(gb)
            w *= 0.80
            d *= 0.80
            z += rh * 0.62
        rb = box(w * 1.0, d * 0.3, 0.7 * scale)
        rb.translate((0, 0, z + 0.2 * scale))
        md_roof.add(rb)
        for s_ in (-1, 1):
            sh = box(0.5 * scale, 0.3 * scale, 1.4 * scale)
            sh.translate((s_ * w * 0.5, 0, z + 0.9 * scale))
            md_gold.add(sh)
        m = Euler((0, 0, rot)).to_matrix().to_4x4()
        m.translation = (cx, cy, cz)
        for md in (md_wall, md_roof, md_base, md_gold, md_win):
            md.transform(m)
        to_obj(name + "_Walls", md_wall, plaster, coll, smooth=False)
        to_obj(name + "_Roofs", md_roof, roof, coll)
        to_obj(name + "_StoneBase", md_base, stonewall, coll, smooth=False)
        to_obj(name + "_Shachihoko", md_gold, roof_gold, coll, smooth=False)
        to_obj(name + "_Windows", md_win, dark_wood, coll, smooth=False)

    # one main keep + secondary towers in each camera direction (all four turnaround views)
    def on_hill(x, y):
        r = math.hypot(x, y)
        return hill_h(r, math.atan2(y, x))

    for (x, y, sc_, tiers, rot, name) in (
            (6.0, 205.0, 1.45, 5, 0.05, "Castle_Tenshu_North"), (-22.0, 160.0, 0.95, 3, -0.2, "Castle_Yagura_NW"),
            (26.0, 170.0, 0.85, 3, 0.3, "Castle_Yagura_NE"), (-6.0, -205.0, 1.45, 5, 3.2, "Castle_Tenshu_South"),
            (22.0, -160.0, 0.95, 3, 2.9, "Castle_Yagura_SE"), (-26.0, -170.0, 0.85, 3, 3.4, "Castle_Yagura_SW"),
            (205.0, -6.0, 1.45, 5, 1.6, "Castle_Tenshu_East"), (160.0, -22.0, 0.95, 3, 1.4, "Castle_Yagura_E"),
            (170.0, 26.0, 0.85, 3, 1.8, "Castle_Yagura_E2"), (-205.0, 6.0, 1.45, 5, -1.5, "Castle_Tenshu_West"),
            (-160.0, 22.0, 0.95, 3, -1.7, "Castle_Yagura_W"), (-170.0, -26.0, 0.85, 3, -1.3, "Castle_Yagura_W2")):
        keep(x, y, on_hill(x, y), sc_, tiers, rot, name)

    # maple trees (red) on the hill and at the courtyard edge, pines further up
    trunks, crowns, pines = MD(), MD(), MD()
    placed = 0
    for k in range(600):
        if placed >= 120:
            break
        a_ = RNG.uniform(0, TAU)
        r = RNG.uniform(18.5, 26.0) if placed < 30 else RNG.uniform(30.0, 90.0)
        x, y = r * math.cos(a_), r * math.sin(a_)
        # keep each turnaround camera's line of sight to the castles open (|offset| from the axes)
        if min(abs(x), abs(y)) < (0.22 * r + 2.0):
            continue
        placed += 1
        z0 = hill_h(r, a_)
        h = RNG.uniform(5.0, 9.0)
        base = V((x, y, z0))
        path = [base, base + V((RNG.uniform(-0.5, 0.5), RNG.uniform(-0.5, 0.5), h * 0.5)),
                base + V((RNG.uniform(-1, 1), RNG.uniform(-1, 1), h))]
        trunks.add(tube(catmull_path(path, 4), 0.14 * h / 5, 8, scale=lambda t: 1.0 - 0.6 * t))
        for c in range(22):
            cr = uv_sphere(1.0, 12, 8)
            s_ = RNG.uniform(0.55, 1.1) * h / 5
            off = V((RNG.uniform(-2.4, 2.4), RNG.uniform(-2.4, 2.4), RNG.uniform(-1.0, 1.3))) * h / 5
            cen = path[-1] + off
            cr.v = [cen + V((p.x * s_ * 1.3, p.y * s_ * 1.3, p.z * s_ * 0.75)) +
                    V((p.x, p.y, p.z)) * s_ * 0.35 * fbm(p * 2.5 + cen) for p in cr.v]
            crowns.add(cr)
    for ax, ay in ((0, 1), (0, -1), (1, 0), (-1, 0)):
        for side_, r in ((-1, 21.0), (1, 23.5)):
            lat = side_ * RNG.uniform(2.6, 3.4)
            x = ax * r + (ay != 0) * lat
            y = ay * r + (ax != 0) * lat
            z0 = hill_h(math.hypot(x, y))
            h = RNG.uniform(8.5, 10.5)
            base = V((x, y, z0))
            path = [base, base + V((RNG.uniform(-0.4, 0.4), RNG.uniform(-0.4, 0.4), h * 0.55)),
                    base + V((side_ * 1.2 * (ay != 0), side_ * 1.2 * (ax != 0), h))]
            trunks.add(tube(catmull_path(path, 4), 0.20, 8, scale=lambda t: 1.0 - 0.6 * t))
            for c in range(26):
                cr = uv_sphere(1.0, 12, 8)
                s_ = RNG.uniform(0.6, 1.2)
                off = V((RNG.uniform(-2.6, 2.6), RNG.uniform(-2.6, 2.6), RNG.uniform(-1.4, 1.0)))
                cen = path[-1] + off
                cr.v = [cen + V((p.x * s_ * 1.3, p.y * s_ * 1.3, p.z * s_ * 0.75)) +
                        V((p.x, p.y, p.z)) * s_ * 0.35 * fbm(p * 2.5 + cen) for p in cr.v]
                crowns.add(cr)
    for ax, ay in ((0, 1), (0, -1), (1, 0), (-1, 0)):
        for q in range(6):
            r = RNG.uniform(34.0, 70.0)
            side_ = -1 if q % 2 else 1
            lat = side_ * RNG.uniform(2.8, 6.5) * r / 45.0
            x = ax * r + (ay != 0) * lat
            y = ay * r + (ax != 0) * lat
            z0 = hill_h(math.hypot(x, y))
            h = RNG.uniform(6.5, 9.5)
            base = V((x, y, z0))
            path = [base, base + V((RNG.uniform(-0.4, 0.4), RNG.uniform(-0.4, 0.4), h * 0.55)),
                    base + V((RNG.uniform(-0.8, 0.8), RNG.uniform(-0.8, 0.8), h))]
            trunks.add(tube(catmull_path(path, 4), 0.18, 8, scale=lambda t: 1.0 - 0.6 * t))
            for c in range(20):
                cr = uv_sphere(1.0, 12, 8)
                s_ = RNG.uniform(0.7, 1.3)
                off = V((RNG.uniform(-2.4, 2.4), RNG.uniform(-2.4, 2.4), RNG.uniform(-1.2, 1.0)))
                cen = path[-1] + off
                cr.v = [cen + V((p.x * s_ * 1.3, p.y * s_ * 1.3, p.z * s_ * 0.75)) +
                        V((p.x, p.y, p.z)) * s_ * 0.35 * fbm(p * 2.5 + cen) for p in cr.v]
                crowns.add(cr)
    for k in range(260):
        a_ = RNG.uniform(0, TAU)
        r = RNG.uniform(40.0, 200.0)
        x, y = r * math.cos(a_), r * math.sin(a_)
        if min(abs(x), abs(y)) < 0.25 * r and r < 150:
            continue  # keep the castle sight-lines clear
        z0 = hill_h(r, a_)
        h = RNG.uniform(7.0, 14.0)
        cone = lathe([(0.0, h), (h * 0.18, h * 0.65), (h * 0.12, h * 0.6), (h * 0.26, h * 0.3), (h * 0.2, h * 0.28),
                      (h * 0.32, h * 0.05), (0.0, h * 0.05)], 8)
        cone.translate((x, y, z0))
        pines.add(cone)
    to_obj("Maple_Trunks", trunks, bark, coll)
    to_obj("Maple_Crowns", crowns, maple, coll)
    to_obj("Pines_Distant", pines, pine, coll, smooth=False)

    # stone lanterns (toro) and red nobori banners around the courtyard
    lan = MD()
    for (lx, ly) in ((-2.8, 5.0), (3.2, -5.4), (5.2, 3.0), (-5.0, -3.2)):
        part = MD()
        part.add(lathe([(0.0, 0.0), (0.28, 0.0), (0.28, 0.12), (0.12, 0.18), (0.08, 0.9), (0.2, 0.95), (0.22, 1.05),
                        (0.0, 1.05)], 6))
        lb = box(0.38, 0.38, 0.3)
        lb.translate((0, 0, 1.2))
        part.add(lb)
        part.add(lathe([(0.0, 1.85), (0.05, 1.8), (0.08, 1.62), (0.42, 1.42), (0.4, 1.36), (0.0, 1.36)], 6))
        part.translate((lx, ly, 0))
        lan.add(part)
    to_obj("Stone_Lanterns", lan, stonewall, coll, smooth=False)
    for (bx, by) in ((-3.6, 6.0), (4.2, -6.4), (6.4, 4.0), (-6.2, -4.4)):
        pole = tube([V((bx, by, 0)), V((bx, by, 3.4))], 0.035, 10)
        to_obj("Nobori_Pole", pole, wood, coll)
        flag = grid(lambda u, v, i, j, bx=bx, by=by: (bx + 0.03 + u * 0.55, by + 0.02 * math.sin(v * 9 + u * 3),
                                                     3.25 - v * 1.9), lin(0, 1, 6), lin(0, 1, 20))
        to_obj("Nobori_Banner_Red", flag, banner_red, coll)


# =============================================================================
# Props showcase (items from the concept sheet laid out on a dark plinth)
# =============================================================================
def build_props_showcase(sc):
    import kage_gear
    coll = collection("Props_Showcase")
    origin = V((7.0, -7.0, 0.0))
    plinth_m = mat_simple("Showcase_Plinth", (0.012, 0.011, 0.011), rough=0.6)
    p = box(3.0, 1.0, 0.9)
    p.translate(origin + V((0, 0, 0.45)))
    to_obj("Showcase_Plinth", p, plinth_m, coll, smooth=False)
    kage_gear.build_showcase_items(coll, origin + V((0, 0, 0.9)))
    # black velvet backdrop behind the display (items read on black, like the concept's item row)
    velvet = mat_simple("Showcase_Black_Velvet", (0.004, 0.004, 0.004), rough=0.95, sheen=0.3)
    card = grid(lambda u, v, i, j: (origin.x + lerp(-4.0, 4.0, u), origin.y + 1.3 + 0.8 * (1 - v) ** 3,
                                    lerp(0.0, 3.4, v)), lin(0, 1, 4), lin(0, 1, 12))
    to_obj("Showcase_Backdrop", card, velvet, coll)
    cams = collection("Cameras")
    make_camera("CAM_Props", cams, origin + V((0.0, -3.2, 1.9)), target=origin + V((0.0, 0.0, 1.0)), focal=40)
    make_camera("CAM_Weapons", cams, origin + V((0.65, -1.45, 1.45)), target=origin + V((0.55, 0.0, 1.05)), focal=45)
    # soft studio lights for the showcase
    lc = collection("Lighting")
    area("Props_Key", lc, origin + V((-1.5, -2.0, 2.6)), origin + V((0, 0, 1.0)), 70, (1.0, 0.86, 0.72), 1.2, None)
    area("Props_Softbox", lc, origin + V((0.0, -0.6, 2.4)), origin + V((0, 0, 0.9)), 90, (1.0, 0.92, 0.82), 1.6, None)
    area("Props_Rim", lc, origin + V((1.8, 1.5, 2.0)), origin + V((0, 0, 1.0)), 90, (1.0, 0.55, 0.3), 1.0, None)
