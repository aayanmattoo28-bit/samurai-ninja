"""Render settings, light rig, turnaround/detail cameras, courtyard environment, props showcase.

Turnaround panels: the character is static; each camera sits square-on to its view, and the whole environment
(Env_Root) is yawed so the panel shows its own angular slice of one virtual wide shot.  Side by side, the four
panels therefore share one continuous castle backdrop, like the concept sheet.
"""
import math

import bpy
from mathutils import Euler, Matrix, Vector

from kage_lib import (MD, NB, TAU, V, _ao, collection, grid, lathe, lin, mat_simple, mod_subsurf, new_mat, to_obj,
                      box, RNG, fbm, uv_sphere, tube, sweep, rect_profile, catmull_path, lerp, clamp, smooth,
                      mat_decal)
from kage_mats import M

# view name -> (camera location relative to the character, rotation (deg), view yaw (deg))
CAM_DIST, CAM_Z, TILT = 5.7, 0.865, 1.0
TURNAROUND = {
    "Front": ((0.0, -CAM_DIST, CAM_Z), (90 + TILT, 0, 0), 0),
    "Left": ((CAM_DIST, 0.0, CAM_Z), (90 + TILT, 0, 90), 90),
    "Right": ((-CAM_DIST, 0.0, CAM_Z), (90 + TILT, 0, -90), -90),
    "Back": ((0.0, CAM_DIST, CAM_Z), (90 + TILT, 0, 180), 180),
}
TURN_FOCAL = 65
# panel centre offset from the strip centre, in frame heights (make_sheet boxes: centres 203/423/633/849, strip 524)
PANEL_SHIFT = {"Front": -0.451, "Left": -0.142, "Right": 0.153, "Back": 0.456}
# exact panel aspect (2x the sheet boxes) so the sheet needs no cropping
PANEL_RES = {"Front": (460, 1424), "Left": (420, 1424), "Right": (420, 1424), "Back": (444, 1424)}

# detail cameras: name -> (location, target, focal mm, f-stop, rake light W)
DETAILS = {
    "FrontWaist": ((-0.02, -1.15, 1.10), (-0.02, -0.1, 1.00), 50, 2.8, 40),
    "BackWaist": ((0.04, 1.15, 1.02), (0.04, 0.1, 0.94), 50, 2.8, 40),
    "Kasa": ((-0.40, -0.58, 2.08), (0.0, 0.0, 1.82), 50, 2.8, 60),
    "Mask": ((-0.18, -0.62, 1.74), (0.0, 0.0, 1.70), 50, 2.8, 15),
    "Armor": ((0.85, -0.25, 1.40), (0.30, 0.0, 1.40), 50, 4.0, 40),
    "Fabric": ((-0.07, 0.66, 1.26), (-0.075, 0.20, 1.24), 50, 2.8, 40),
    "LegArmor": ((0.44, -0.66, 0.36), (0.22, -0.02, 0.30), 50, 4.0, 40),
}


def env_root():
    e = bpy.data.objects.get("Env_Root")
    if e is None:
        e = bpy.data.objects.new("Env_Root", None)
        collection("Environment_Courtyard").objects.link(e)
        e.empty_display_size = 2.0
    return e


def view_yaw(direction):
    """Yaw (rad) that turns the environment's +Y toward a horizontal camera direction."""
    d = V((direction[0], direction[1], 0.0))
    if d.length < 1e-6:
        return 0.0
    d.normalize()
    return math.atan2(-d.x, d.y)


def set_view(yaw):
    """Rotate the light rig and the environment together (the character stays still)."""
    rig = bpy.data.objects.get("Light_Rig")
    if rig is not None:
        rig.rotation_euler[2] = yaw
    env = bpy.data.objects.get("Env_Root")
    if env is not None:
        env.location = (0, 0, 0)
        env.rotation_euler = (0, 0, yaw)


def place_turn(v):
    """Set up turnaround view v: light rig yaw = view yaw, environment yaw = view yaw + this panel's slice."""
    phi = math.radians(TURNAROUND[v][2])
    alpha = math.atan(PANEL_SHIFT[v] * 2 * 12.0 / TURN_FOCAL)
    rig = bpy.data.objects.get("Light_Rig")
    if rig is not None:
        rig.rotation_euler[2] = phi
    env = bpy.data.objects.get("Env_Root")
    if env is not None:
        env.location = (0, 0, 0)
        env.rotation_euler = (0, 0, phi + alpha)
    return bpy.data.objects["CAM_" + v]


def setup_render(sc):
    sc.render.engine = "CYCLES"
    cy = sc.cycles
    cy.device = "CPU"
    cy.samples = 128
    cy.use_denoising = True
    try:
        cy.denoiser = "OPENIMAGEDENOISE"
        cy.denoising_prefilter = "ACCURATE"
        cy.denoising_input_passes = "RGB_ALBEDO_NORMAL"
    except Exception:
        pass
    cy.use_adaptive_sampling = True
    cy.adaptive_threshold = 0.01
    cy.max_bounces = 8
    cy.glossy_bounces = 4
    cy.transmission_bounces = 8
    cy.transparent_max_bounces = 32
    cy.caustics_reflective = False
    cy.caustics_refractive = False
    cy.blur_glossy = 0.6
    cy.sample_clamp_indirect = 8.0
    cy.filter_width = 1.1
    sc.render.resolution_x = 900
    sc.render.resolution_y = 1800
    sc.render.film_transparent = False
    sc.view_settings.view_transform = "AgX"
    try:
        sc.view_settings.look = "AgX - Medium High Contrast"
    except Exception:
        pass
    sc.view_settings.exposure = 0.2
    try:
        compositor(sc)
    except Exception as e:  # compositor is a finishing touch only
        print("compositor setup skipped:", e)
    try:
        ee = sc.eevee
        ee.use_shadows = True
        ee.use_raytracing = True
    except Exception:
        pass


def compositor(sc):
    """Camera-like finish: bloom, clarity (unsharp mask), split-tone grade, mild desaturation, vignette."""
    sc.use_nodes = True
    nt = sc.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    L = nt.links.new
    rl = nt.nodes.new("CompositorNodeRLayers")
    gl = nt.nodes.new("CompositorNodeGlare")
    gl.glare_type = "FOG_GLOW"
    gl.quality = "HIGH"
    gl.threshold = 0.6
    gl.size = 8
    gl.mix = -0.70
    blur = nt.nodes.new("CompositorNodeBlur")
    blur.filter_type = "FAST_GAUSS"
    blur.use_relative = False
    blur.size_x = 3
    blur.size_y = 3
    sub = nt.nodes.new("CompositorNodeMixRGB")
    sub.blend_type = "SUBTRACT"
    sub.use_clamp = False
    sub.inputs["Fac"].default_value = 1.0
    add = nt.nodes.new("CompositorNodeMixRGB")
    add.blend_type = "ADD"
    add.use_clamp = False
    add.inputs["Fac"].default_value = 0.18
    cb = nt.nodes.new("CompositorNodeColorBalance")
    cb.correction_method = "LIFT_GAMMA_GAIN"
    cb.lift = (0.992, 0.996, 1.012)
    cb.gamma = (0.985, 1.0, 1.035)
    cb.gain = (1.03, 1.0, 0.96)
    hs = nt.nodes.new("CompositorNodeHueSat")
    hs.inputs["Saturation"].default_value = 0.92
    em = nt.nodes.new("CompositorNodeEllipseMask")
    em.width = 0.98
    em.height = 0.98
    bl = nt.nodes.new("CompositorNodeBlur")
    bl.filter_type = "FAST_GAUSS"
    bl.use_relative = True
    bl.factor_x = 30
    bl.factor_y = 30
    vg = nt.nodes.new("CompositorNodeMapRange")
    vg.inputs["To Min"].default_value = 0.62
    vg.inputs["To Max"].default_value = 1.0
    mul = nt.nodes.new("CompositorNodeMixRGB")
    mul.blend_type = "MULTIPLY"
    mul.inputs["Fac"].default_value = 1.0
    comp = nt.nodes.new("CompositorNodeComposite")
    L(rl.outputs["Image"], gl.inputs["Image"])
    L(gl.outputs["Image"], blur.inputs["Image"])
    L(gl.outputs["Image"], sub.inputs[1])
    L(blur.outputs["Image"], sub.inputs[2])
    L(gl.outputs["Image"], add.inputs[1])
    L(sub.outputs["Image"], add.inputs[2])
    L(add.outputs["Image"], cb.inputs["Image"])
    L(cb.outputs["Image"], hs.inputs["Image"])
    L(em.outputs["Mask"], bl.inputs["Image"])
    L(bl.outputs["Image"], vg.inputs["Value"])
    L(hs.outputs["Image"], mul.inputs[1])
    L(vg.outputs["Value"], mul.inputs[2])
    L(mul.outputs["Image"], comp.inputs["Image"])


def world(sc, follow):
    """Cool lilac dusk sky with a warm sunset lobe and streaky clouds; locked to the environment's yaw.

    The camera sees a brighter sky (0.75) than the scene is lit by (0.38); glossy rays see the bright one too."""
    w = bpy.data.worlds.new("Dusk_Sky")
    sc.world = w
    nb = NB(w)
    tc = nb.n("ShaderNodeTexCoord", (-1200, 0))
    rot = nb.n("ShaderNodeMapping", (-1000, 0))
    rot.vector_type = "VECTOR"
    nb.link(tc.outputs["Generated"], rot.inputs["Vector"])
    fc = rot.inputs["Rotation"].driver_add("default_value", 2)
    var = fc.driver.variables.new()
    var.name = "r"
    var.type = "TRANSFORMS"
    var.targets[0].id = follow
    var.targets[0].transform_type = "ROT_Z"
    var.targets[0].transform_space = "WORLD_SPACE"
    fc.driver.expression = "-r"
    d = rot.outputs["Vector"]
    sep = nb.n("ShaderNodeSeparateXYZ", (-800, 0))
    nb.link(d, sep.inputs[0])
    sky = nb.ramp(sep.outputs[2], [(0.0, (0.045, 0.04, 0.045)), (0.02, (0.50, 0.38, 0.36)), (0.08, (0.40, 0.36, 0.46)),
                                   (0.20, (0.28, 0.27, 0.40)), (0.50, (0.14, 0.15, 0.25)), (1.0, (0.06, 0.07, 0.13))])
    dp = nb.n("ShaderNodeVectorMath", (-800, -300))
    dp.operation = "DOT_PRODUCT"
    nb.link(d, dp.inputs[0])
    dp.inputs[1].default_value = (-0.906, 0.423, 0.0)
    lobe = nb.math("MULTIPLY", nb.math("POWER", nb.math("MAXIMUM", dp.outputs["Value"], 0.0), 1.5),
                   nb.ramp(sep.outputs[2], [(0.0, 1.0), (0.25, 0.0)]))
    lobe = nb.math("MULTIPLY", lobe, 0.8)
    sky = nb.mix(lobe, sky, (1.0, 0.52, 0.26), "ADD")
    mp = nb.mapping(d, (1.0, 1.0, 7.0))
    cl = nb.noise(mp, 3.0, 10, 0.6, distortion=0.8)
    cloud = nb.math("MULTIPLY", nb.ramp(cl.outputs["Fac"], [(0.46, 0.0), (0.64, 1.0)]),
                    nb.ramp(sep.outputs[2], [(0.02, 0.0), (0.10, 1.0)]))
    ccol = nb.mix(lobe, (0.50, 0.45, 0.52), (0.95, 0.62, 0.40))
    col = nb.mix(nb.math("MULTIPLY", cloud, 0.8), sky, ccol)
    bg_cam = nb.n("ShaderNodeBackground", (200, 100))
    nb.link(col, bg_cam.inputs["Color"])
    bg_cam.inputs["Strength"].default_value = 0.75
    bg_lit = nb.n("ShaderNodeBackground", (200, -100))
    nb.link(col, bg_lit.inputs["Color"])
    bg_lit.inputs["Strength"].default_value = 0.38
    lp = nb.n("ShaderNodeLightPath", (0, 300))
    fac = nb.math("MAXIMUM", lp.outputs["Is Camera Ray"], lp.outputs["Is Glossy Ray"])
    mx = nb.n("ShaderNodeMixShader", (400, 0))
    nb.link(fac, mx.inputs[0])
    nb.link(bg_lit.outputs[0], mx.inputs[1])
    nb.link(bg_cam.outputs[0], mx.inputs[2])
    o = nb.n("ShaderNodeOutputWorld", (600, 0))
    nb.link(mx.outputs[0], o.inputs["Surface"])


def area(name, coll, loc, target, power, color, size, parent, spread=None):
    ld = bpy.data.lights.new(name, "AREA")
    ld.energy = power
    ld.color = color
    ld.shape = "DISK"
    ld.size = size
    if spread is not None:
        ld.spread = math.radians(spread)
    ob = bpy.data.objects.new(name, ld)
    coll.objects.link(ob)
    ob.location = loc
    d = V(target) - V(loc)
    ob.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()
    ob.parent = parent
    return ob


def link_light(ob, receivers):
    try:
        ob.light_linking.receiver_collection = receivers
    except Exception as e:  # pragma: no cover - light linking needs Blender 4.0+
        print("light linking unavailable:", e)


def build_lights(sc):
    coll = collection("Lighting")
    rig = bpy.data.objects.new("Light_Rig", None)
    coll.objects.link(rig)
    rig.empty_display_size = 1.0
    world(sc, env_root())
    char = bpy.data.collections.get("KageMusha_Character")
    envc = collection("Environment_Courtyard")
    c = (0, 0, 1.1)
    area("Key_Warm", coll, (-3.6, -3.4, 4.6), c, 300, (1.0, 0.87, 0.74), 1.2, rig)
    lk = [area("Fill_Cool", coll, (3.8, -3.6, 1.8), c, 40, (0.58, 0.66, 1.0), 4.0, rig),
          # rims aim at the shoulders with a narrow spread so they never graze the feet or the wet slabs
          area("Rim_Warm_L", coll, (-1.7, 3.4, 3.2), (0, 0, 1.45), 60, (1.0, 0.60, 0.32), 1.4, rig, spread=32),
          area("Rim_Warm_R", coll, (1.9, 3.3, 2.4), (0, 0, 1.45), 22, (1.0, 0.70, 0.46), 1.4, rig, spread=30),
          area("Top_Sky_Rim", coll, (0.0, 1.6, 5.0), (0, 0, 1.5), 70, (0.70, 0.76, 1.0), 2.5, rig),
          area("Face_Fill", coll, (0.4, -2.2, 1.55), (0, 0, 1.72), 7, (1.0, 0.82, 0.68), 0.6, rig),
          area("Top_Kasa", coll, (0.0, -1.0, 4.5), (0, 0, 1.8), 25, (1.0, 0.85, 0.7), 1.2, rig),
          area("Low_Bounce", coll, (0.0, -3.0, 0.2), (0, 0, 0.6), 5, (0.55, 0.50, 0.50), 3.0, rig)]
    if char is not None:
        for ob in lk:
            link_light(ob, char)
    sun = bpy.data.lights.new("Sun_Low", "SUN")
    sun.energy = 3.5
    sun.color = (1.0, 0.78, 0.55)
    sun.angle = math.radians(1.5)
    so = bpy.data.objects.new("Sun_Low", sun)
    coll.objects.link(so)
    so.rotation_euler = Euler((math.radians(62), 0, math.radians(-115)))
    so.parent = rig
    sb = bpy.data.lights.new("Sun_Backdrop", "SUN")
    sb.energy = 2.5
    sb.color = (1.0, 0.74, 0.52)
    sb.angle = math.radians(2.0)
    sbo = bpy.data.objects.new("Sun_Backdrop", sb)
    coll.objects.link(sbo)
    sbo.rotation_euler = Euler((math.radians(78), 0, math.radians(-60)))
    sbo.parent = rig
    link_light(sbo, envc)
    return rig


def make_camera(name, coll, loc, rot=None, target=None, focal=100, ortho=False):
    cd = bpy.data.cameras.new(name)
    cd.lens = focal
    cd.sensor_fit = "VERTICAL"
    cd.sensor_height = 24
    cd.clip_start = 0.05
    cd.clip_end = 1200
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
    lc = collection("Lighting")
    char = bpy.data.collections.get("KageMusha_Character")
    first = None
    for name, (loc, rot, _) in TURNAROUND.items():
        cam = make_camera("CAM_" + name, coll, loc, rot=rot, focal=TURN_FOCAL)
        cam.data.dof.use_dof = True
        cam.data.dof.focus_distance = CAM_DIST
        cam.data.dof.aperture_fstop = 5.6
        first = first or cam
    for name, (loc, tgt, f, fstop, rake) in DETAILS.items():
        cam = make_camera("CAM_Detail_" + name, coll, loc, target=tgt, focal=f)
        cam.data.dof.use_dof = True
        cam.data.dof.focus_distance = (V(tgt) - V(loc)).length
        cam.data.dof.aperture_fstop = fstop
        # hard warm raking light from the upper left of the view (enabled only for this close-up)
        d = (V(tgt) - V(loc)).normalized()
        right = d.cross(V((0, 0, 1))).normalized()
        p = V(tgt) - right * 0.9 + V((0, 0, 0.8)) + d * 0.25
        ob = area("Rake_" + name, lc, p, tgt, rake, (1.0, 0.80, 0.58), 0.3, None)
        if char is not None:
            link_light(ob, char)
        ob.hide_render = True
    sc.camera = first


# =============================================================================
# Environment materials
# =============================================================================
def fog_wrap(mat, fog_col=(0.31, 0.28, 0.35), near=20.0, scale=260.0, max_fac=0.7):
    """Aerial perspective: exponential distance haze, denser low in the valleys, blended toward the sky colour."""
    nt = mat.node_tree
    out = [n for n in nt.nodes if n.type == "OUTPUT_MATERIAL"][0]
    src = out.inputs["Surface"].links[0].from_socket

    def mth(op, a, b=None):
        m = nt.nodes.new("ShaderNodeMath")
        m.operation = op
        for k, val in enumerate((a, b)):
            if val is None:
                continue
            if isinstance(val, (int, float)):
                m.inputs[k].default_value = val
            else:
                nt.links.new(val, m.inputs[k])
        return m.outputs[0]

    cam = nt.nodes.new("ShaderNodeCameraData")
    dist = mth("SUBTRACT", 1.0, mth("EXPONENT", mth("DIVIDE", mth("MAXIMUM", mth("SUBTRACT", cam.outputs["View Distance"],
                                                                                   near), 0.0), -scale)))
    geo = nt.nodes.new("ShaderNodeNewGeometry")
    sp = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(geo.outputs["Position"], sp.inputs[0])
    hr = nt.nodes.new("ShaderNodeMapRange")
    hr.clamp = True
    hr.inputs["From Min"].default_value = 0.0
    hr.inputs["From Max"].default_value = 45.0
    hr.inputs["To Min"].default_value = 1.0
    hr.inputs["To Max"].default_value = 0.75
    nt.links.new(sp.outputs[2], hr.inputs["Value"])
    fac = mth("MULTIPLY", mth("MULTIPLY", dist, hr.outputs[0]), max_fac)
    em = nt.nodes.new("ShaderNodeEmission")
    em.inputs["Color"].default_value = (*fog_col, 1)
    em.inputs["Strength"].default_value = 1.0
    mx = nt.nodes.new("ShaderNodeMixShader")
    nt.links.new(fac, mx.inputs[0])
    nt.links.new(src, mx.inputs[1])
    nt.links.new(em.outputs[0], mx.inputs[2])
    nt.links.new(mx.outputs[0], out.inputs["Surface"])
    return mat


def mat_stone(name="Stone_Courtyard"):
    """Granite flagstones: running bond, chipped and cracked, with crisp wet patches that mirror the sky."""
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
    br.inputs["Color1"].default_value = (0.062, 0.060, 0.060, 1)
    br.inputs["Color2"].default_value = (0.043, 0.042, 0.042, 1)
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
    crack = nb.ramp(cr.outputs["Fac"], [(0.49, 0.0), (0.5, 1.0), (0.51, 0.0)])
    vc = nb.n("ShaderNodeTexVoronoi", (-900, -300), feature="DISTANCE_TO_EDGE")
    vc.inputs["Scale"].default_value = 2.5
    nb.link(obj, vc.inputs["Vector"])
    crack2 = nb.ramp(vc.outputs["Distance"], [(0.0, 1.0), (0.015, 0.0)])
    crack = nb.math("MAXIMUM", crack, crack2)
    col = nb.mix(nb.math("MAXIMUM", mortar, nb.math("MULTIPLY", crack, 0.7)), base, (0.015, 0.013, 0.012))
    wet = nb.ramp(nb.noise(obj, 0.45, 4, 0.5).outputs["Fac"], [(0.56, 0.0), (0.60, 1.0)])
    col = nb.mix(nb.math("MULTIPLY", wet, 0.55), col, (0.02, 0.019, 0.019))  # wet stone darkens
    rough = nb.mixf(wet, 0.62, 0.03)
    grit = nb.noise(obj, 60.0, 8, 0.7)
    h = nb.math("ADD", nb.math("MULTIPLY", nb.math("SUBTRACT", 1.0, mortar), 1.0),
                nb.math("ADD", nb.math("MULTIPLY", grit.outputs["Fac"], 0.25), nb.math("MULTIPLY", crack, -0.5)))
    bmp = nb.n("ShaderNodeBump", (-200, -300))
    nb.link(nb.math("MULTIPLY", nb.math("SUBTRACT", 1.0, wet), 0.5), bmp.inputs["Strength"])
    bmp.inputs["Distance"].default_value = 0.01
    nb.link(h, bmp.inputs["Height"])
    p = nb.principled(Base_Color=col, Roughness=rough, Coat_Roughness=0.02, Normal=bmp.outputs["Normal"])
    nb.link(wet, p.inputs["Coat Weight"])
    nb.output(p.outputs[0])
    return m


def mat_foliage(name, stops=None):
    """Maple foliage: ragged leaf-cluster cut-outs, per-cluster colour scatter, dark self-shadowed canopy
    interiors and a little back-lit translucency."""
    m = new_mat(name)
    nb = NB(m)
    tc = nb.texcoord()
    obj = tc.outputs["Object"]
    holes = nb.noise(obj, 2.2, 5, 0.7, distortion=0.4)
    leaves = nb.noise(obj, 14.0, 3, 0.6)
    leafmask = nb.math("MULTIPLY", nb.ramp(holes.outputs["Fac"], [(0.36, 0.0), (0.44, 1.0)]),
                       nb.ramp(leaves.outputs["Fac"], [(0.40, 0.0), (0.47, 1.0)]))
    n = nb.noise(obj, 0.6, 6, 0.6)
    stops = stops or [(0.30, (0.15, 0.010, 0.008)), (0.50, (0.38, 0.035, 0.014)), (0.68, (0.58, 0.11, 0.025)),
                      (0.85, (0.50, 0.22, 0.045))]
    col = nb.ramp(n.outputs["Fac"], stops)
    speck = nb.noise(obj, 5.0, 2, 0.5)
    col = nb.mix(nb.ramp(speck.outputs["Fac"], [(0.55, 0.0), (0.70, 0.6)]), col, (0.07, 0.008, 0.006))
    occ = _ao(nb, 1.2)
    col = nb.mix(nb.ramp(occ, [(0.0, 0.85), (0.8, 0.0)]), col, (0.025, 0.004, 0.004))
    p = nb.principled(Base_Color=col, Roughness=0.62, Specular_IOR_Level=0.3)
    tl = nb.n("ShaderNodeBsdfTranslucent", (200, -500))
    nb.link(col, tl.inputs["Color"])
    leaf = nb.n("ShaderNodeMixShader", (380, -200))
    leaf.inputs[0].default_value = 0.22
    nb.link(p.outputs[0], leaf.inputs[1])
    nb.link(tl.outputs[0], leaf.inputs[2])
    tr = nb.n("ShaderNodeBsdfTransparent", (200, -300))
    mx = nb.n("ShaderNodeMixShader", (550, 0))
    nb.link(leafmask, mx.inputs[0])
    nb.link(tr.outputs[0], mx.inputs[1])
    nb.link(leaf.outputs[0], mx.inputs[2])
    nb.output(mx.outputs[0])
    m.diffuse_color = (0.4, 0.05, 0.02, 1)
    return m


def mat_hill(name="Castle_Hill_Terraces"):
    """Ishigaki stone on the steep terrace faces; moss, soil and red leaf litter on the flats."""
    m = new_mat(name)
    nb = NB(m)
    tc = nb.texcoord()
    obj = tc.outputs["Object"]
    g = nb.n("ShaderNodeNewGeometry", (-1100, 300))
    sn = nb.n("ShaderNodeSeparateXYZ", (-900, 300))
    nb.link(g.outputs["Normal"], sn.inputs[0])
    slope = nb.ramp(sn.outputs[2], [(0.55, 1.0), (0.75, 0.0)])
    br = nb.n("ShaderNodeTexBrick", (-900, 0))
    br.offset = 0.5
    br.inputs["Scale"].default_value = 0.9
    br.inputs["Mortar Size"].default_value = 0.03
    br.inputs["Brick Width"].default_value = 0.8
    br.inputs["Row Height"].default_value = 0.5
    br.inputs["Color1"].default_value = (0.16, 0.15, 0.135, 1)
    br.inputs["Color2"].default_value = (0.11, 0.105, 0.10, 1)
    br.inputs["Mortar"].default_value = (0.03, 0.028, 0.025, 1)
    nb.link(obj, br.inputs["Vector"])
    flat = nb.mix(nb.ramp(nb.noise(obj, 0.3, 6, 0.6).outputs["Fac"], [(0.5, 0.0), (0.65, 1.0)]), (0.035, 0.04, 0.025),
                  (0.16, 0.035, 0.02))
    col = nb.mix(slope, flat, br.outputs["Color"])
    p = nb.principled(Base_Color=col, Roughness=0.85,
                      Normal=nb.bump(nb.math("MULTIPLY", br.outputs["Fac"], slope), 0.6, 0.05))
    nb.output(p.outputs[0])
    return m


def mat_mist(name, col=(0.36, 0.34, 0.42), dens=0.5):
    """Wispy mist band on a camera-facing card."""
    m = new_mat(name)
    nb = NB(m)
    tc = nb.texcoord()
    obj = tc.outputs["Object"]
    wisps = nb.ramp(nb.noise(nb.mapping(obj, (0.025, 0.025, 0.22)), 2.0, 6, 0.6, distortion=0.5).outputs["Fac"],
                    [(0.38, 0.0), (0.70, 1.0)])
    su = nb.n("ShaderNodeSeparateXYZ", (-900, -300))
    nb.link(tc.outputs["UV"], su.inputs[0])
    band = nb.ramp(su.outputs[1], [(0.0, 0.0), (0.25, 1.0), (1.0, 0.0)])
    alpha = nb.math("MULTIPLY", nb.math("MULTIPLY", wisps, band), dens)
    em = nb.n("ShaderNodeEmission", (200, -100))
    em.inputs["Color"].default_value = (*col, 1)
    em.inputs["Strength"].default_value = 1.0
    tr = nb.n("ShaderNodeBsdfTransparent", (200, 100))
    mx = nb.n("ShaderNodeMixShader", (400, 0))
    nb.link(alpha, mx.inputs[0])
    nb.link(tr.outputs[0], mx.inputs[1])
    nb.link(em.outputs[0], mx.inputs[2])
    nb.output(mx.outputs[0])
    return m


# =============================================================================
# Environment geometry (all parented to Env_Root; the hero backdrop is authored along +Y)
# =============================================================================
def hill_h(r, a=0.0):
    """Courtyard (r<17), moat, then a steep terraced castle hill with 5 m stone faces."""
    if r < 17.0:
        return 0.0
    if r < 20.0:
        return -3.5 * smooth((r - 17.0) / 3.0)
    if r < 28.0:
        return -3.5
    base = -3.5 + 0.135 * (r - 28.0) + 1.5 * fbm(V((math.cos(a) * 4, math.sin(a) * 4, r * 0.03)))
    t = (base + 3.5) / 5.0
    k = math.floor(t)
    f = t - k
    return -3.5 + 5.0 * (k + smooth((f - 0.72) / 0.28))


def on_hill(x, y):
    return hill_h(math.hypot(x, y), math.atan2(y, x))


def keep_md(cx, cy, cz, scale, tiers, rot=0.0):
    """Castle keep (tenshu): battered stone base, stacked plaster tiers, flared upturned roofs, gold ornaments."""
    md_wall, md_roof, md_base, md_gold, md_win = MD(), MD(), MD(), MD(), MD()

    def base_fn(u, v, i, j):
        a = u * TAU
        ca, sa = math.cos(a), math.sin(a)
        m = max(abs(ca), abs(sa))
        sx, sy = ca / m, sa / m
        w = lerp(24 * scale, 18 * scale, v ** 0.7)
        d = lerp(21 * scale, 15.5 * scale, v ** 0.7)
        return (sx * w / 2, sy * d / 2, -3.0 + v * (3.0 + 3.2 * scale))

    md_base.add(grid(base_fn, lin(0, 1, 64), lin(0, 1, 6), closed_u=True))
    sc_ = scale

    def gable(md_face, md_rf, md_orn, gw, gh, gd, zb, yf, ang):
        """Chidori-hafu: plaster triangle under a pitched, overhanging roof, turned to face direction ang."""
        g_face, g_roof, g_orn = MD(), MD(), MD()
        g_face.v = [V((-gw / 2, -yf, zb)), V((gw / 2, -yf, zb)), V((0, -yf, zb + gh)), V((0, -yf + gd, zb + gh)),
                    V((-gw / 2, -yf + gd, zb)), V((gw / 2, -yf + gd, zb))]
        g_face.f = [(0, 1, 2), (0, 2, 3, 4), (1, 5, 3, 2)]
        g_face.uv = [[(0, 0), (1, 0), (0.5, 1)], [(0, 0), (1, 0), (1, 1), (0, 1)], [(0, 0), (1, 0), (1, 1), (0, 1)]]
        g_face.mi = [0, 0, 0]
        ov = 0.45 * sc_
        for sgn in (-1, 1):
            def sl(u, v, i, j, sgn=sgn):
                y = lerp(-yf - ov, -yf + gd, u)
                x = sgn * lerp(0.0, gw / 2 + ov, v)
                z = zb + gh + 0.12 * sc_ - (gh + 0.4 * sc_) * v + 0.25 * sc_ * v * v
                return V((x, y, z))
            g_roof.add(grid(sl, lin(0, 1, 3), lin(0, 1, 6)))
            g_roof.add(tube([sl(0.0, q / 6, 0, 0) for q in range(7)], 0.09 * sc_, 6))  # dark barge board
        orn = box(0.35 * sc_, 0.12 * sc_, 0.5 * sc_)
        orn.translate((0, -yf - 0.05 * sc_, zb + gh - 0.35 * sc_))
        g_orn.add(orn)
        rm = Matrix.Rotation(ang, 4, "Z")
        for src, dst in ((g_face, md_face), (g_roof, md_rf), (g_orn, md_orn)):
            src.transform(rm)
            dst.add(src)

    z = 3.2 * scale
    w, d = 15.0 * scale, 12.4 * scale
    for t in range(tiers):
        h = (3.0 if t < tiers - 1 else 3.3) * scale
        wb = box(w, d, h)
        wb.translate((0, 0, z + h / 2))
        md_wall.add(wb)
        # dark timber: sill and lintel beams, posts, barred windows on every face
        for zz, bh in ((z + 0.12 * scale, 0.24 * scale), (z + h - 0.16 * scale, 0.32 * scale)):
            bb = box(w + 0.12 * scale, d + 0.12 * scale, bh)
            bb.translate((0, 0, zz))
            md_win.add(bb)
        for face_len, along_x in ((w, True), (d, False)):
            nq = max(2, int(face_len / (1.6 * scale)))
            for side in (-1, 1):
                for q in range(nq + 1):
                    c_ = -face_len / 2 + q * face_len / nq
                    post = box(0.14 * scale, 0.08 * scale, h) if along_x else box(0.08 * scale, 0.14 * scale, h)
                    off = side * ((d if along_x else w) / 2 + 0.03 * scale)
                    post.translate((c_, off, z + h / 2) if along_x else (off, c_, z + h / 2))
                    md_win.add(post)
                    if q == nq:
                        continue
                    c2 = c_ + face_len / nq / 2
                    win = box(0.72 * scale, 0.07 * scale, 0.8 * scale) if along_x else box(0.07 * scale, 0.72 * scale, 0.8 * scale)
                    off = side * ((d if along_x else w) / 2 + 0.035 * scale)
                    win.translate((c2, off, z + h * 0.58) if along_x else (off, c2, z + h * 0.58))
                    md_win.add(win)
        z += h
        top = t == tiers - 1
        ow, od = w * (1.45 if top else 1.58), d * (1.45 if top else 1.58)
        rh = (2.6 if top else 2.2) * scale

        def rf(u, v, i, j, ow=ow, od=od, w=w, d=d, z=z, rh=rh):
            a = u * TAU
            ca, sa = math.cos(a), math.sin(a)
            m = max(abs(ca), abs(sa))
            sx, sy = ca / m, sa / m
            ww = lerp(ow, w * 0.50, v ** 0.6)
            dd = lerp(od, d * 0.50, v ** 0.6)
            corner = abs(sx * sy) ** 3
            lift = 1.25 * scale * (1 - v) ** 3 * corner
            return (sx * ww / 2, sy * dd / 2, z - 0.50 * scale + rh * (v ** 1.5) + lift)

        md_roof.add(grid(rf, lin(0, 1, 96), lin(0, 1, 10), closed_u=True))
        eave = [V(rf(q / 96, 0.0, 0, 0)) for q in range(97)]
        md_roof.add(tube(eave, 0.16 * scale, 6))  # thick tiled eave fascia
        md_wall.add(tube([p_ + V((0, 0, -0.06 * scale)) for p_ in eave], 0.035 * scale, 4))  # pale tile-end line
        # gables: front/back on even tiers (and on the top roof), sides on odd tiers
        gz = z - 0.50 * scale + rh * 0.18
        if t % 2 == 0 or top:
            for ang in (0.0, math.pi):
                gable(md_wall, md_roof, md_gold, w * (0.75 if top else 0.48), (2.2 if top else 1.5) * scale,
                      d * 0.35, gz, d / 2 + 0.55 * scale, ang)
        if t % 2 == 1:
            for ang in (math.pi / 2, -math.pi / 2):
                gable(md_wall, md_roof, md_gold, d * 0.45, 1.4 * scale, w * 0.3, gz, w / 2 + 0.55 * scale, ang)
        w *= 0.78
        d *= 0.78
        z += rh * 0.55
    rb = box(w * 1.1, d * 0.3, 0.6 * scale)
    rb.translate((0, 0, z + 0.2 * scale))
    md_roof.add(rb)
    for s_ in (-1, 1):
        sh = box(0.5 * scale, 0.3 * scale, 1.3 * scale)
        sh.translate((s_ * w * 0.55, 0, z + 0.9 * scale))
        md_gold.add(sh)
    m = Euler((0, 0, rot)).to_matrix().to_4x4()
    m.translation = (cx, cy, cz)
    for md in (md_wall, md_roof, md_base, md_gold, md_win):
        md.transform(m)
    return md_wall, md_roof, md_base, md_gold, md_win


def wall_run(md_wall, md_roof, pts, height=2.4, depth=2.2):
    """Tamon wall: plaster boxes along a polyline with a one-tier tiled roof."""
    for a, b in zip(pts, pts[1:]):
        a, b = V(a), V(b)
        seg = b - a
        L = seg.length
        if L < 1e-3:
            continue
        ang_ = math.atan2(seg.y, seg.x)
        mid = (a + b) / 2
        wb = box(L, depth, height)
        wb.transform(Matrix.Translation(mid + V((0, 0, height / 2))) @ Matrix.Rotation(ang_, 4, "Z"))
        md_wall.add(wb)

        def rf(u, v, i, j):
            x = lerp(-L / 2 - 0.3, L / 2 + 0.3, u)
            y = lerp(-depth / 2 - 0.6, depth / 2 + 0.6, v)
            z = height + 0.9 * (1 - abs(y) / (depth / 2 + 0.6)) - 0.1
            return V((x, y, z))

        r = grid(rf, lin(0, 1, 6), lin(0, 1, 6))
        r.transform(Matrix.Translation(mid) @ Matrix.Rotation(ang_, 4, "Z"))
        md_roof.add(r)


def crown(path_top, h, n, spread, rng):
    """Maple canopy: many small lumpy leaf clusters packed into a flattened dome, denser on the outer shell
    so the silhouette is ragged and the clusters read as foliage rather than a few big balls."""
    md = MD()
    R = h * 0.42 * spread / 2.4
    H = h * 0.30
    for c in range(n * 3):
        a = rng.uniform(0, TAU)
        rr = R * rng.uniform(0.35, 1.0) ** 0.5
        zz = rng.uniform(-0.6, 1.0)
        rr *= math.sqrt(max(0.05, 1.0 - 0.55 * zz * zz))
        cen = path_top + V((rr * math.cos(a), rr * math.sin(a), zz * H))
        s_ = rng.uniform(0.16, 0.30) * h / 5 * (1.15 - 0.3 * rr / max(R, 1e-3))
        cr = uv_sphere(1.0, 8, 6)
        cr.v = [cen + V((p.x * s_ * 1.25, p.y * s_ * 1.25, p.z * s_ * 0.8)) +
                V((p.x, p.y, p.z)) * s_ * 0.55 * fbm(p * 3.0 + cen) for p in cr.v]
        md.add(cr)
    return md


def conifer(top, h, rng):
    """Japanese pine: tiered, wind-swept needle pads on a leaning trunk (clusters, not a cone)."""
    md = MD()
    tiers = 4 + int(rng.random() * 2)
    for t in range(tiers):
        f = t / max(1, tiers - 1)
        zc = top.z - f * h * 0.55
        R = h * (0.10 + 0.20 * f)
        for c in range(5 + int(6 * f)):
            a = rng.uniform(0, TAU)
            rr = R * rng.uniform(0.3, 1.0)
            cen = V((top.x + rr * math.cos(a), top.y + rr * math.sin(a), zc + rng.uniform(-0.3, 0.3) * h * 0.06))
            s_ = h * rng.uniform(0.05, 0.085)
            cr = uv_sphere(1.0, 8, 5)
            cr.v = [cen + V((p.x * s_ * 1.6, p.y * s_ * 1.6, p.z * s_ * 0.55)) +
                    V((p.x, p.y, p.z)) * s_ * 0.5 * fbm(p * 3.0 + cen) for p in cr.v]
            md.add(cr)
    return md


def build_environment(sc):
    coll = collection("Environment_Courtyard")
    root = env_root()

    def put(name, md, mat, smooth_=True):
        return to_obj(name, md, mat, coll, smooth=smooth_, parent=root)

    stone = fog_wrap(mat_stone())
    plaster = fog_wrap(mat_simple("Castle_Plaster", (0.50, 0.46, 0.42), rough=0.8, var_col=(0.36, 0.33, 0.30),
                                  dirt=0.4))
    roof = fog_wrap(mat_simple("Castle_Roof_Tiles", (0.012, 0.014, 0.018), rough=0.45, metal=0.2, wave="BANDS",
                               wave_dir="X", wave_coord="Object", wave_scale=25.0, wave_str=1.0, bump_str=0.8))
    roof_gold = fog_wrap(mat_simple("Castle_Roof_Gold", (0.55, 0.38, 0.15), rough=0.35, metal=1.0))
    wood = M.get("wood")
    dark_wood = fog_wrap(mat_simple("Castle_Dark_Wood", (0.025, 0.02, 0.018), rough=0.7))
    stonewall = fog_wrap(mat_simple("Castle_Stone_Base", (0.12, 0.11, 0.10), rough=0.85, var_col=(0.06, 0.055, 0.05),
                                    var_scale=1.5, bump_scale=3.0, bump_str=0.8))
    maple = fog_wrap(mat_foliage("Maple_Leaves"))
    maple_gold = fog_wrap(mat_foliage("Maple_Leaves_Gold", [(0.30, (0.20, 0.06, 0.01)), (0.6, (0.45, 0.18, 0.04)),
                                                             (0.85, (0.55, 0.32, 0.08))]))
    pine = fog_wrap(mat_foliage("Pine_Needles", [(0.30, (0.010, 0.016, 0.010)), (0.55, (0.022, 0.036, 0.020)),
                                                  (0.80, (0.045, 0.055, 0.028))]))
    hill = fog_wrap(mat_hill())
    bark = fog_wrap(mat_simple("Bark", (0.04, 0.03, 0.025), rough=0.9, bump_scale=20.0, bump_str=0.8))
    banner_red = mat_simple("Banner_Red", (0.22, 0.015, 0.015), rough=0.8, sheen=0.4, var_col=(0.12, 0.01, 0.01))
    leaf_ground = mat_simple("Fallen_Leaves", (0.11, 0.022, 0.012), rough=0.45, var_col=(0.22, 0.06, 0.02),
                             var_scale=3.0, coat=0.4)
    mud = mat_simple("Courtyard_Mud", (0.018, 0.015, 0.012), rough=0.5, var_col=(0.03, 0.025, 0.02), var_scale=4.0)
    water = new_mat("Puddle_Water")
    nbw = NB(water)
    pw = nbw.principled(Base_Color=(0.008, 0.008, 0.009), Roughness=0.015, IOR=1.33)
    nbw.output(pw.outputs[0])

    # --- courtyard: mud bed under uneven, chipped granite slabs, puddles, clumped leaves ---------------
    put("Courtyard_Mud", grid(lambda u, v, i, j: (v * math.cos(u), v * math.sin(u), -0.012), lin(0, TAU, 128),
                              lin(0.0, 16.4, 40), closed_u=True), mud)
    slabs = MD()
    Wd, Dp = 0.95, 0.62
    row = 0
    y = -3.0
    while y < 16.0:
        x = -7.5 + (Wd / 2 if row % 2 else 0.0)
        while x < 7.5:
            pieces = [(x, Wd)]
            if RNG.random() < 0.15:
                cut = RNG.uniform(0.35, 0.65)
                pieces = [(x - Wd / 2 + Wd * cut / 2, Wd * cut), (x + Wd * cut / 2, Wd * (1 - cut))]
            for cx, w in pieces:
                b = box(w - 0.022, Dp - 0.022, 0.10)
                m_ = Euler((RNG.gauss(0, 0.008), RNG.gauss(0, 0.008), RNG.gauss(0, 0.015))).to_matrix().to_4x4()
                m_.translation = (cx, y, -0.05 + RNG.gauss(0, 0.006))
                slabs.add(b.transform(m_))
            x += Wd
        y += Dp
        row += 1
    so = put("Courtyard_Slabs", slabs, stone, smooth_=False)
    bv = so.modifiers.new("Bevel", "BEVEL")
    bv.width = 0.012
    bv.segments = 2
    bv.limit_method = "ANGLE"
    # the rest of the courtyard (outside the slab strip) stays a flat flagstone disc
    put("Courtyard_Flagstones", grid(lambda u, v, i, j: (v * math.cos(u), v * math.sin(u), -0.004), lin(0, TAU, 128),
                                     lin(7.6, 16.4, 20), closed_u=True), stone)
    puddles = MD()
    for k, (cx, cy, R) in enumerate(((-0.9, 1.2, 0.55), (0.6, 2.8, 0.8), (-1.8, 4.5, 1.1), (1.5, 6.0, 1.3),
                                     (0.25, -0.9, 0.45), (2.6, 1.0, 0.6), (-2.7, 0.3, 0.7), (-0.4, 8.5, 1.5),
                                     (2.0, 11.0, 1.2))):
        base = len(puddles.v)
        puddles.v.append(V((cx, cy, 0.003)))
        for q in range(28):
            a = TAU * q / 28
            rr = R * (1 + 0.35 * fbm(V((math.cos(a) * 2, math.sin(a) * 2, k * 3.1))))
            puddles.v.append(V((cx + rr * math.cos(a), cy + rr * math.sin(a), 0.003)))
        for q in range(28):
            puddles.f.append((base, base + 1 + q, base + 1 + (q + 1) % 28))
            puddles.uv.append([(0.5, 0.5), (0, 0), (1, 0)])
            puddles.mi.append(0)
    put("Courtyard_Puddles", puddles, water)
    leaves = MD()
    tries = 0
    while len(leaves.f) < 650 * 7 and tries < 20000:
        tries += 1
        r = 0.4 + RNG.random() ** 0.8 * 12.0
        a = RNG.uniform(0, TAU)
        x, y = r * math.cos(a), r * math.sin(a)
        if fbm(V((x * 0.5, y * 0.5, 0))) <= 0.1:
            continue
        s_ = RNG.uniform(0.022, 0.04)
        rot = RNG.uniform(0, TAU)
        base = len(leaves.v)
        leaves.v.append(V((x, y, 0.004)))
        for q in range(7):
            aa = rot + TAU * q / 7
            rr = s_ * (1.0 if q % 2 == 0 else 0.5)
            leaves.v.append(V((x + rr * math.cos(aa), y + rr * math.sin(aa), 0.003 + 0.004 * rr / s_ + RNG.uniform(0, 0.002))))
        for q in range(7):
            leaves.f.append((base, base + 1 + q, base + 1 + (q + 1) % 7))
            leaves.uv.append([(0.5, 0.5), (0, 0), (1, 0)])
            leaves.mi.append(0)
    put("Fallen_Maple_Leaves", leaves, leaf_ground, smooth_=False)

    # --- moat, parapet and railing at the courtyard edge -----------------------------------------
    put("Moat_Water", grid(lambda u, v, i, j: (lerp(16.8, 30.0, v) * math.cos(u), lerp(16.8, 30.0, v) * math.sin(u), -2.6),
                           lin(0, TAU, 96), lin(0, 1, 2), closed_u=True), water)
    walls = MD()

    def wf(u, v, i, j):
        rr = 16.6 + 0.25 * (1 - v)
        return (rr * math.cos(u), rr * math.sin(u), -3.5 + v * 3.55)

    walls.add(grid(wf, lin(0, TAU, 160), lin(0, 1, 4), closed_u=True))
    put("Courtyard_Stone_Parapet", walls, stonewall)
    fence = MD()
    for k in range(220):
        a_ = TAU * k / 220
        bx_ = box(0.14, 0.14, 0.85)
        bx_.translate((16.45 * math.cos(a_), 16.45 * math.sin(a_), 0.45))
        fence.add(bx_)
    for zr in (0.40, 0.82):
        ring = [V((16.45 * math.cos(TAU * k / 200), 16.45 * math.sin(TAU * k / 200), zr)) for k in range(200)]
        fence.add(sweep(ring, rect_profile(0.08, 0.12), up=(0, 0, 1), closed_path=True))
    put("Courtyard_Railing", fence, dark_wood, smooth_=False)

    # --- terraced castle hill --------------------------------------------------------------------
    def terrain(u, v, i, j):
        r = lerp(17.0, 320.0, v ** 1.6)
        return (r * math.cos(u), r * math.sin(u), hill_h(r, u) - 0.02)

    put("Castle_Hill", grid(terrain, lin(0, TAU, 256), lin(0, 1, 180), closed_u=True), hill)

    # --- hero castle set (behind the strip) + tamon walls on the terrace lips ----------------------
    walls_md, roofs_md, base_md, gold_md, win_md = MD(), MD(), MD(), MD(), MD()
    # main keep just right of the strip centre, one keep on each side (as in the concept), small turrets nearer
    keeps = ((2.0, 150, 0.85, 4, 0.05), (18.5, 170, 0.70, 4, -0.15), (-22.0, 170, 0.70, 4, 0.25),
             (-11, 118, 0.45, 2, 0.10), (16, 128, 0.42, 2, -0.30), (-6.5, 19.5, 0.32, 2, 0.0))
    for (x, y, sc_, tiers, rot) in keeps:
        z = on_hill(x, y) if math.hypot(x, y) > 25 else 0.0
        for dst, src in zip((walls_md, roofs_md, base_md, gold_md, win_md), keep_md(x, y, z, sc_, tiers, rot)):
            dst.add(src)
    for rr in (95.0, 140.0, 185.0):
        pts = []
        for k in range(25):
            a = math.radians(lerp(90 - 14, 90 + 14, k / 24))
            x, y = rr * math.cos(a), rr * math.sin(a)
            pts.append(V((x, y, hill_h(rr - 4.0, a) + 0.1)))
        wall_run(walls_md, roofs_md, pts, 2.6, 2.2)
    for xs in ((-14.0, -4.0), (5.0, 14.0)):  # tamon wall along the courtyard rim, centre open
        wall_run(walls_md, roofs_md, [V((xs[0], 18.6, 0.0)), V((xs[1], 18.6, 0.0))], 2.4, 2.2)
    put("Castle_Walls", walls_md, plaster, smooth_=False)
    put("Castle_Roofs", roofs_md, roof)
    put("Castle_StoneBase", base_md, stonewall, smooth_=False)
    put("Castle_Shachihoko", gold_md, roof_gold, smooth_=False)
    put("Castle_Windows", win_md, dark_wood, smooth_=False)

    # --- trees: dense red / gold maples and pines on the hero hillside, framing maples near the strip ---
    trunks, crowns_r, crowns_g, pines = MD(), MD(), MD(), MD()
    placed = 0
    tries = 0
    # each keep's view sector (azimuth from the turnaround camera, half-width) and the elevation of its base:
    # trees standing in front of a keep must stay below that line so the castle silhouettes stay readable
    sectors = []
    for (kx, ky, ks, _, _) in keeps[:3]:
        dist = ky + CAM_DIST
        sectors.append((math.atan2(kx, dist), math.atan2(9.5 * ks + 2.0, dist),
                        math.atan2(on_hill(kx, ky) + 4.5 * ks - CAM_Z, dist)))

    def blocks_keep(x, y, top):
        dist = y + CAM_DIST
        az, el = math.atan2(x, dist), math.atan2(top - CAM_Z, dist)
        return any(abs(az - a0) < hw + 0.035 and el > e0 and y < 150 for a0, hw, e0 in sectors)

    while placed < 320 and tries < 8000:
        tries += 1
        y = RNG.uniform(35.0, 280.0)
        x = RNG.uniform(-(0.24 * y + 6), 0.24 * y + 6)
        if any(math.hypot(x - kx, y - ky) < 18 * ks for kx, ky, ks, _, _ in keeps):
            continue
        kind = RNG.random()
        hh = RNG.uniform(5.0, 12.0)
        if kind < 0.36 and y < 80:
            kind = 0.6
        if blocks_keep(x, y, on_hill(x, y) + hh * 1.1):
            continue
        placed += 1
        z0 = on_hill(x, y)
        if kind < 0.36:
            h = max(7.0, hh)
            base = V((x, y, z0))
            path = [base, base + V((RNG.uniform(-0.6, 0.6), RNG.uniform(-0.6, 0.6), h * 0.5)),
                    base + V((RNG.uniform(-1.2, 1.2), RNG.uniform(-1.2, 1.2), h))]
            trunks.add(tube(catmull_path(path, 4), 0.11 * h / 5, 6, scale=lambda t: 1.0 - 0.7 * t))
            pines.add(conifer(path[-1], h, RNG))
            continue
        h = min(9.0, hh)
        base = V((x, y, z0))
        path = [base, base + V((RNG.uniform(-0.5, 0.5), RNG.uniform(-0.5, 0.5), h * 0.5)),
                base + V((RNG.uniform(-1, 1), RNG.uniform(-1, 1), h))]
        trunks.add(tube(catmull_path(path, 4), 0.14 * h / 5, 8, scale=lambda t: 1.0 - 0.6 * t))
        (crowns_g if kind < 0.50 else crowns_r).add(crown(path[-1], h, 14, 2.4, RNG))
    for side_ in (-1, 1):
        for r, lat in ((21.0, 8.8), (23.5, 9.3)):
            x, y = side_ * lat, r
            z0 = on_hill(x, y)
            h = RNG.uniform(5.0, 6.0)
            base = V((x, y, z0))
            path = [base, base + V((0, 0, h * 0.55)), base + V((-side_ * 1.2, 0, h))]
            trunks.add(tube(catmull_path(path, 4), 0.20, 8, scale=lambda t: 1.0 - 0.6 * t))
            crowns_r.add(crown(path[-1], h + 2, 18, 2.6, RNG))
    for (x, y) in ((-5.6, 12.3), (5.8, 12.3)):  # near maples leaning in: their crowns frame the strip's top corners
        h = 5.5
        base = V((x, y, 0.0))
        path = [base, base + V((0, 0, h * 0.5)), base + V((-math.copysign(1.0, x), 0, h))]
        trunks.add(tube(catmull_path(path, 4), 0.16, 8, scale=lambda t: 1.0 - 0.6 * t))
        crowns_r.add(crown(path[-1] + V((0, 0, -0.6)), h, 18, 1.6, RNG))
    put("Maple_Trunks", trunks, bark)
    put("Maple_Crowns", crowns_r, maple)
    put("Maple_Crowns_Gold", crowns_g, maple_gold)
    put("Pines", pines, pine)

    # --- mid-ground set dressing inside the strip: stone toro lanterns, nobori banners ------------
    lan = MD()
    for (lx, ly) in ((-2.4, 4.0), (2.6, 10.5)):
        part = MD()
        part.add(lathe([(0.0, 0.0), (0.28, 0.0), (0.28, 0.12), (0.12, 0.18), (0.08, 0.9), (0.2, 0.95), (0.22, 1.05),
                        (0.0, 1.05)], 6))
        lb = box(0.38, 0.38, 0.3)
        lb.translate((0, 0, 1.2))
        part.add(lb)
        part.add(lathe([(0.0, 1.85), (0.05, 1.8), (0.08, 1.62), (0.42, 1.42), (0.4, 1.36), (0.0, 1.36)], 6))
        part.transform(Matrix.Translation((lx, ly, 0)) @ Matrix.Scale(1.15, 4))
        lan.add(part)
    put("Stone_Lanterns", lan, stonewall, smooth_=False)
    mon = mat_decal("Decal_Nobori_Mon", "mon_flower.png", tint=(0.85, 0.80, 0.70), wear=0.3, metal=0.0, rough=0.8)
    for k, (bx, by) in enumerate(((-2.9, 7.5), (3.4, 12.0))):
        put(f"Nobori_Pole_{k}", tube([V((bx, by, 0)), V((bx, by, 4.2))], 0.035, 10), wood)
        flag = grid(lambda u, v, i, j, bx=bx, by=by: (bx + 0.03 + u * 0.6, by + 0.025 * math.sin(v * 9 + u * 3),
                                                     4.1 - v * 2.4), lin(0, 1, 6), lin(0, 1, 20))
        put(f"Nobori_Banner_{k}", flag, banner_red)
        md_mon = grid(lambda u, v, i, j, bx=bx, by=by: (bx + 0.13 + u * 0.36, by - 0.02 + 0.025 * math.sin((0.25 + v * 0.18) * 9 + u * 3),
                                                       3.75 - v * 0.36), lin(0, 1, 6), lin(0, 1, 6))
        put(f"Nobori_Mon_{k}", md_mon, mon)

    # --- mist cards between the terraces + low ground mist ----------------------------------------
    for k, (y, h, dens) in enumerate(((55, 5, 0.16), (110, 9, 0.26), (170, 12, 0.34), (240, 14, 0.42))):
        card = grid(lambda u, v, i, j, y=y, h=h: (lerp(-0.3 * y - 20, 0.3 * y + 20, u), y, hill_h(y) - 2.0 + v * (h + 2.0)),
                    lin(0, 1, 8), lin(0, 1, 4))
        ob = put(f"Mist_{k}", card, mat_mist(f"Mist_{k}", dens=dens))
        ob.visible_shadow = False
        ob.visible_diffuse = False
    gm = grid(lambda u, v, i, j: (lerp(-12, 12, u), 13.0, v * 2.2), lin(0, 1, 8), lin(0, 1, 4))
    ob = put("Mist_Ground", gm, mat_mist("Mist_Ground", col=(0.45, 0.43, 0.50), dens=0.16))
    ob.visible_shadow = False
    ob.visible_diffuse = False


# =============================================================================
# Props showcase (items from the concept sheet laid out on a dark plinth)
# =============================================================================
def build_props_showcase(sc):
    import kage_gear
    coll = collection("Props_Showcase")
    origin = V((7.0, -7.0, 0.0))
    plinth_m = mat_simple("Showcase_Plinth", (0.006, 0.0055, 0.0055), rough=0.28, coat=0.5, bump_scale=8.0,
                          bump_str=0.05)
    p = box(3.0, 1.0, 0.9)
    p.translate(origin + V((0, 0, 0.45)))
    to_obj("Showcase_Plinth", p, plinth_m, coll, smooth=False)
    kage_gear.build_showcase_items(coll, origin + V((0, 0, 0.9)))
    velvet = mat_simple("Showcase_Black_Velvet", (0.0025, 0.0025, 0.0025), rough=0.95, sheen=0.3)
    card = grid(lambda u, v, i, j: (origin.x + lerp(-4.0, 4.0, u), origin.y + 1.3 + 0.8 * (1 - v) ** 3,
                                    lerp(0.0, 3.4, v)), lin(0, 1, 4), lin(0, 1, 12))
    to_obj("Showcase_Backdrop", card, velvet, coll)
    cams = collection("Cameras")
    make_camera("CAM_Props", cams, origin + V((0.0, -3.2, 1.9)), target=origin + V((0.0, 0.0, 1.0)), focal=40)
    make_camera("CAM_Weapons", cams, origin + V((0.65, -1.45, 1.45)), target=origin + V((0.55, 0.0, 1.05)), focal=45)
    # low-key: small hard warm key, warm rim, faint cool top; light-linked so the backdrop stays black
    lc = collection("Lighting")
    ll = bpy.data.collections.get("LL_Props") or bpy.data.collections.new("LL_Props")
    for ob in coll.objects:
        if ob.name != "Showcase_Backdrop" and ob.name not in ll.objects:
            ll.objects.link(ob)
    for ob in (area("Props_Key", lc, origin + V((-1.1, -1.3, 2.2)), origin + V((0, 0, 1.0)), 110, (1.0, 0.84, 0.66),
                    0.45, None, spread=50),
               area("Props_Softbox", lc, origin + V((0.0, 0.6, 2.6)), origin + V((0, 0, 0.9)), 30, (0.88, 0.92, 1.0),
                    2.0, None),
               area("Props_Rim", lc, origin + V((1.6, 1.4, 1.6)), origin + V((0, 0, 1.0)), 160, (1.0, 0.55, 0.3),
                    0.5, None)):
        link_light(ob, ll)
