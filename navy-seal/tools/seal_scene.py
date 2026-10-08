"""Navy SEAL set: render settings, night-harbour light rig, the four turnaround cameras (FRONT, LEFT, BACK, RIGHT)
sharing one continuous backdrop, and the harbour environment (wet dock, sea, submarine, ships, helicopter,
mountains, dusk sky)."""
import math

import bpy
from mathutils import Euler, Matrix, Vector

import seal_lib as L
from seal_lib import MD, NB, TAU, V, collection, fbm, grid, interp_smooth, lerp, lin, new_mat, smooth, to_obj

# --- turnaround layout, measured on the concept sheet (1536 x 1024; the turnaround strip is 630 px tall) -----
# view -> (panel left edge, figure centre, panel right edge) in sheet pixels
SHEET_H = 630.0
PANELS = {"Front": (0, 290, 407), "Left": (407, 525, 637), "Back": (637, 750, 881), "Right": (881, 1013, 1145)}
STRIP_C = 572.0
VIEW_YAW = {"Front": 0.0, "Left": 90.0, "Back": 180.0, "Right": -90.0}
CAM_DIST, CAM_Z, CAM_AIM_Z = 7.0, 0.30, 0.95  # low hero camera: the far sea line sits at boot-top height
FOCAL = 85.0
SENSOR = 24.0


def env_root():
    e = bpy.data.objects.get("Env_Root")
    if e is None:
        e = bpy.data.objects.new("Env_Root", None)
        collection("Environment_Harbour").objects.link(e)
        e.empty_display_size = 2.0
    return e


def panel_shift(v):
    a, c, b = PANELS[v]
    return (c - STRIP_C) / SHEET_H


def place_view(v):
    """Turn the light rig with the camera, and the environment by the panel's slice of the panorama."""
    phi = math.radians(VIEW_YAW[v])
    alpha = math.atan(panel_shift(v) * SENSOR / FOCAL)
    rig = bpy.data.objects.get("Light_Rig")
    if rig is not None:
        rig.rotation_euler[2] = phi
    env = bpy.data.objects.get("Env_Root")
    if env is not None:
        env.rotation_euler = (0, 0, phi + alpha)
    return bpy.data.objects["CAM_" + v]


# --- render settings ---------------------------------------------------------------------------------------
def setup_render(sc):
    sc.render.engine = "CYCLES"
    cy = sc.cycles
    cy.device = "CPU"
    cy.samples = 96
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
    cy.transparent_max_bounces = 32
    cy.caustics_reflective = False
    cy.caustics_refractive = False
    cy.blur_glossy = 0.5
    cy.sample_clamp_indirect = 6.0
    cy.filter_width = 1.1
    sc.render.resolution_x, sc.render.resolution_y = 600, 1300
    sc.view_settings.view_transform = "AgX"
    try:
        sc.view_settings.look = "AgX - High Contrast"
    except Exception:
        pass
    sc.view_settings.exposure = 0.0
    try:
        compositor(sc)
    except Exception as e:  # pragma: no cover
        print("compositor skipped:", e)


def compositor(sc):
    """Cool night grade: mild bloom on the lamps and visor, blue shadows, slight vignette."""
    sc.use_nodes = True
    nt = sc.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    Lk = nt.links.new
    rl = nt.nodes.new("CompositorNodeRLayers")
    gl = nt.nodes.new("CompositorNodeGlare")
    gl.glare_type = "FOG_GLOW"
    gl.quality = "HIGH"
    gl.threshold = 0.9
    gl.size = 8
    gl.mix = -0.6
    cb = nt.nodes.new("CompositorNodeColorBalance")
    cb.correction_method = "LIFT_GAMMA_GAIN"
    cb.lift = (0.998, 0.999, 1.006)
    cb.gamma = (0.995, 1.0, 1.012)
    cb.gain = (1.0, 1.0, 1.0)
    hs = nt.nodes.new("CompositorNodeHueSat")
    hs.inputs["Saturation"].default_value = 0.85
    em = nt.nodes.new("CompositorNodeEllipseMask")
    em.width, em.height = 1.0, 1.0
    bl = nt.nodes.new("CompositorNodeBlur")
    bl.filter_type = "FAST_GAUSS"
    bl.use_relative = True
    bl.factor_x = bl.factor_y = 30
    vg = nt.nodes.new("CompositorNodeMapRange")
    vg.inputs["To Min"].default_value = 0.70
    vg.inputs["To Max"].default_value = 1.0
    mul = nt.nodes.new("CompositorNodeMixRGB")
    mul.blend_type = "MULTIPLY"
    mul.inputs["Fac"].default_value = 1.0
    comp = nt.nodes.new("CompositorNodeComposite")
    Lk(rl.outputs["Image"], gl.inputs["Image"])
    Lk(gl.outputs["Image"], cb.inputs["Image"])
    Lk(cb.outputs["Image"], hs.inputs["Image"])
    Lk(em.outputs["Mask"], bl.inputs["Image"])
    Lk(bl.outputs["Image"], vg.inputs["Value"])
    Lk(hs.outputs["Image"], mul.inputs[1])
    Lk(vg.outputs["Value"], mul.inputs[2])
    Lk(mul.outputs["Image"], comp.inputs["Image"])


# --- sky ---------------------------------------------------------------------------------------------------
def world(sc, follow):
    """Overcast night-into-dusk sky: deep slate blue overhead, a pale lilac/peach glow low on the right of the
    strip (behind the BACK/RIGHT panels), streaky storm clouds.  Locked to the environment's yaw."""
    w = bpy.data.worlds.new("Harbour_Night_Sky")
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
    sky = nb.ramp(sep.outputs[2], [(0.0, (0.030, 0.036, 0.050)), (0.03, (0.20, 0.22, 0.30)), (0.10, (0.15, 0.17, 0.26)),
                                   (0.30, (0.075, 0.090, 0.150)), (1.0, (0.020, 0.026, 0.050))])
    # dusk glow toward +X+Y (behind the right side of the strip)
    dp = nb.n("ShaderNodeVectorMath", (-800, -300))
    dp.operation = "DOT_PRODUCT"
    nb.link(d, dp.inputs[0])
    dp.inputs[1].default_value = (0.276, 0.961, 0.0)  # +16 deg: just beyond the right edge of the strip
    lobe = nb.math("MULTIPLY", nb.math("POWER", nb.math("MAXIMUM", dp.outputs["Value"], 0.0), 60.0),
                   nb.ramp(sep.outputs[2], [(0.0, 1.0), (0.30, 0.0)]))
    sky = nb.mix(nb.math("MULTIPLY", lobe, 1.0), sky, (0.95, 0.72, 0.62), "ADD")
    mp = nb.mapping(d, (1.0, 1.0, 5.0))
    cl = nb.noise(mp, 2.6, 12, 0.62, distortion=0.9)
    cloud = nb.math("MULTIPLY", nb.ramp(cl.outputs["Fac"], [(0.40, 0.0), (0.62, 1.0)]),
                    nb.ramp(sep.outputs[2], [(0.02, 0.0), (0.09, 1.0)]))
    ccol = nb.mix(lobe, (0.20, 0.22, 0.30), (0.62, 0.52, 0.56))
    col = nb.mix(nb.math("MULTIPLY", cloud, 0.75), sky, ccol)
    dark = nb.noise(nb.mapping(d, (1.0, 1.0, 3.0)), 1.4, 6, 0.6)
    col = nb.mix(nb.math("MULTIPLY", nb.ramp(dark.outputs["Fac"], [(0.45, 0.0), (0.7, 1.0)]), 0.6), col,
                 (0.03, 0.035, 0.055))
    bg_cam = nb.n("ShaderNodeBackground", (200, 100))
    nb.link(col, bg_cam.inputs["Color"])
    bg_cam.inputs["Strength"].default_value = 1.0
    bg_lit = nb.n("ShaderNodeBackground", (200, -100))
    nb.link(col, bg_lit.inputs["Color"])
    bg_lit.inputs["Strength"].default_value = 0.30
    lp = nb.n("ShaderNodeLightPath", (0, 300))
    fac = nb.math("MAXIMUM", lp.outputs["Is Camera Ray"], lp.outputs["Is Glossy Ray"])
    mx = nb.n("ShaderNodeMixShader", (400, 0))
    nb.link(fac, mx.inputs[0])
    nb.link(bg_lit.outputs[0], mx.inputs[1])
    nb.link(bg_cam.outputs[0], mx.inputs[2])
    o = nb.n("ShaderNodeOutputWorld", (600, 0))
    nb.link(mx.outputs[0], o.inputs["Surface"])


# --- lights ------------------------------------------------------------------------------------------------
def area(name, coll, loc, target, power, color, size, parent, spread=None, shape="DISK"):
    ld = bpy.data.lights.new(name, "AREA")
    ld.energy = power
    ld.color = color
    ld.shape = shape
    ld.size = size
    if spread is not None:
        ld.spread = math.radians(spread)
    ob = bpy.data.objects.new(name, ld)
    coll.objects.link(ob)
    ob.location = loc
    ob.rotation_euler = (V(target) - V(loc)).to_track_quat("-Z", "Y").to_euler()
    ob.parent = parent
    return ob


def link_light(ob, receivers):
    try:
        ob.light_linking.receiver_collection = receivers
    except Exception as e:  # pragma: no cover
        print("light linking unavailable:", e)


def build_lights(sc):
    coll = collection("Lighting")
    rig = bpy.data.objects.new("Light_Rig", None)
    coll.objects.link(rig)
    world(sc, env_root())
    char = bpy.data.collections.get("NavySeal_Character")
    c = (0, 0, 1.1)
    # cool moonlit key high front-left, soft blue fill, white-blue rims that trace the wet edges
    area("Key_Moon", coll, (-3.0, -4.2, 5.0), c, 480, (0.86, 0.90, 1.0), 1.6, rig)
    lk = [area("Fill_Blue", coll, (4.0, -3.5, 1.6), c, 35, (0.62, 0.70, 0.90), 4.0, rig),
          area("Rim_Left", coll, (-2.0, 3.4, 3.0), (0, 0, 1.3), 35, (0.75, 0.85, 1.0), 1.4, rig, spread=40),
          area("Rim_Right", coll, (2.2, 3.2, 2.2), (0, 0, 1.1), 30, (1.0, 0.82, 0.78), 1.4, rig, spread=40),
          area("Top_Sky", coll, (0.0, 0.8, 5.0), (0, 0, 1.4), 60, (0.78, 0.82, 0.95), 3.0, rig),
          area("Visor_Kick", coll, (0.3, -2.0, 1.75), (0, 0, 1.69), 4, (0.6, 0.75, 1.0), 0.5, rig)]
    if char is not None:
        for ob in lk:
            link_light(ob, char)
    return rig


# --- cameras -----------------------------------------------------------------------------------------------
def build_cameras(sc):
    coll = collection("Cameras")
    first = None
    for v, yaw in VIEW_YAW.items():
        cd = bpy.data.cameras.new("CAM_" + v)
        cd.lens = FOCAL
        cd.sensor_fit = "VERTICAL"
        cd.sensor_height = SENSOR
        cd.clip_start = 0.05
        cd.clip_end = 3000
        cd.dof.use_dof = True
        cd.dof.focus_distance = CAM_DIST
        cd.dof.aperture_fstop = 4.0
        ob = bpy.data.objects.new("CAM_" + v, cd)
        coll.objects.link(ob)
        a = math.radians(yaw)
        # camera sits on the view axis: FRONT at -Y, LEFT at +X (character's left), BACK at +Y, RIGHT at -X
        pos = Matrix.Rotation(a, 3, "Z") @ V((0.0, -CAM_DIST, CAM_Z))
        ob.location = pos
        tgt = V((0, 0, CAM_AIM_Z))
        ob.rotation_euler = (tgt - pos).to_track_quat("-Z", "Y").to_euler()
        first = first or ob
    sc.camera = first


# --- environment -------------------------------------------------------------------------------------------
def mat_dock(name="Dock_Concrete_Wet"):
    """Wet, worn concrete quay: expansion joints, cracks, puddles that mirror the sky and lamps."""
    m = new_mat(name)
    nb = NB(m)
    tc = nb.texcoord()
    obj = tc.outputs["Object"]
    br = nb.n("ShaderNodeTexBrick", (-900, 200))
    br.offset = 0.0
    br.inputs["Scale"].default_value = 0.25
    br.inputs["Mortar Size"].default_value = 0.004
    br.inputs["Brick Width"].default_value = 1.0
    br.inputs["Row Height"].default_value = 1.0
    br.inputs["Color1"].default_value = (0.040, 0.042, 0.046, 1)
    br.inputs["Color2"].default_value = (0.032, 0.034, 0.038, 1)
    br.inputs["Mortar"].default_value = (0.006, 0.006, 0.007, 1)
    nb.link(obj, br.inputs["Vector"])
    n = nb.noise(obj, 2.5, 10, 0.65)
    col = nb.mix(nb.ramp(n.outputs["Fac"], [(0.35, 0.0), (0.7, 1.0)]), br.outputs["Color"], (0.065, 0.068, 0.072))
    stain = nb.noise(obj, 0.6, 6, 0.6)
    col = nb.mix(nb.math("MULTIPLY", nb.ramp(stain.outputs["Fac"], [(0.5, 0.0), (0.7, 1.0)]), 0.7), col,
                 (0.020, 0.021, 0.024))
    cr = nb.noise(obj, 4.0, 12, 0.75, distortion=0.6)
    crack = nb.ramp(cr.outputs["Fac"], [(0.49, 0.0), (0.5, 1.0), (0.51, 0.0)])
    col = nb.mix(nb.math("MULTIPLY", crack, 0.8), col, (0.008, 0.008, 0.009))
    wet = nb.ramp(nb.noise(obj, 0.35, 5, 0.55).outputs["Fac"], [(0.44, 0.0), (0.54, 1.0)])  # mostly wet, dry islands
    col = nb.mix(nb.math("MULTIPLY", wet, 0.6), col, (0.010, 0.011, 0.013))
    ripple = nb.noise(obj, 3.0, 4, 0.6)
    rough = nb.mixf(wet, 0.55, nb.math("ADD", 0.05, nb.math("MULTIPLY", ripple.outputs["Fac"], 0.10)))
    grit = nb.noise(obj, 80.0, 6, 0.7)
    h = nb.math("ADD", nb.math("MULTIPLY", grit.outputs["Fac"], 0.3),
                nb.math("ADD", nb.math("MULTIPLY", br.outputs["Fac"], -0.6), nb.math("MULTIPLY", crack, -0.4)))
    bmp = nb.n("ShaderNodeBump", (-200, -300))
    nb.link(nb.math("MULTIPLY", nb.math("SUBTRACT", 1.0, wet), 0.6), bmp.inputs["Strength"])
    bmp.inputs["Distance"].default_value = 0.01
    nb.link(h, bmp.inputs["Height"])
    p = nb.principled(Base_Color=col, Roughness=rough, Coat_Roughness=0.02, Normal=bmp.outputs["Normal"])
    nb.link(wet, p.inputs["Coat Weight"])
    nb.output(p.outputs[0])
    return m


def mat_sea(name="Harbour_Water"):
    m = new_mat(name)
    nb = NB(m)
    tc = nb.texcoord()
    obj = tc.outputs["Object"]
    w1 = nb.noise(nb.mapping(obj, (0.25, 0.7, 1.0)), 0.5, 6, 0.6)      # long swells
    w2 = nb.noise(nb.mapping(obj, (1.0, 2.2, 1.0)), 1.6, 5, 0.6)       # chop
    w3 = nb.noise(obj, 9.0, 3, 0.5)
    h = nb.math("ADD", nb.math("ADD", w1.outputs["Fac"], nb.math("MULTIPLY", w2.outputs["Fac"], 0.5)),
                nb.math("MULTIPLY", w3.outputs["Fac"], 0.15))
    p = nb.principled(Base_Color=(0.004, 0.006, 0.009), Roughness=0.10, IOR=1.33,
                      Normal=nb.bump(h, 1.0, 0.12))
    nb.output(p.outputs[0])
    return m


def fog_wrap(mat, fog_col=(0.11, 0.13, 0.19), near=12.0, scale=240.0, max_fac=0.62, top=60.0):
    """Aerial perspective: exponential distance haze toward a cool blue-grey, thinner with height."""
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
    hr.inputs["From Max"].default_value = top
    hr.inputs["To Min"].default_value = 1.0
    hr.inputs["To Max"].default_value = 0.6
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


def mat_hull(name, base=(0.045, 0.050, 0.056), rough=0.55, rust=0.2, metal=0.3):
    """Painted steel: haze-grey paint, streaks and rust runs, darker boot-topping near the waterline."""
    m = new_mat(name)
    nb = NB(m)
    tc = nb.texcoord()
    obj = tc.outputs["Object"]
    st = nb.noise(nb.mapping(obj, (2.0, 2.0, 0.15)), 3.0, 6, 0.6)
    col = nb.mix(nb.ramp(st.outputs["Fac"], [(0.4, 0.0), (0.7, 1.0)]), base, tuple(c * 0.55 for c in base))
    rs = nb.noise(nb.mapping(obj, (3.0, 3.0, 0.3)), 6.0, 6, 0.7)
    col = nb.mix(nb.math("MULTIPLY", nb.ramp(rs.outputs["Fac"], [(0.62, 0.0), (0.75, 1.0)]), rust), col,
                 (0.06, 0.03, 0.018))
    sep = nb.n("ShaderNodeSeparateXYZ", (-1000, -400))
    nb.link(tc.outputs["Generated"], sep.inputs[0])
    p = nb.principled(Base_Color=col, Roughness=rough, Metallic=metal,
                      Normal=nb.bump(nb.noise(obj, 25.0, 4, 0.5).outputs["Fac"], 0.1, 0.02))
    nb.output(p.outputs[0])
    return m


def mat_emit(name, col, strength):
    m = new_mat(name)
    nb = NB(m)
    e = nb.n("ShaderNodeEmission", (0, 0))
    e.inputs["Color"].default_value = (*col, 1)
    e.inputs["Strength"].default_value = strength
    nb.output(e.outputs[0])
    return m


def mat_foam(name="Sea_Spray_Foam"):
    """Breaking surf along the quay edge: white foam streaks with a noisy alpha."""
    m = new_mat(name)
    nb = NB(m)
    tc = nb.texcoord()
    obj = tc.outputs["Object"]
    n = nb.noise(nb.mapping(obj, (0.6, 0.6, 2.0)), 3.0, 8, 0.7, distortion=0.6)
    a = nb.ramp(n.outputs["Fac"], [(0.52, 0.0), (0.70, 1.0)])
    sep = nb.n("ShaderNodeSeparateXYZ", (-1000, -400))
    nb.link(tc.outputs["UV"], sep.inputs[0])
    a = nb.math("MULTIPLY", a, nb.ramp(sep.outputs[1], [(0.0, 1.0), (1.0, 0.0)]))
    p = nb.principled(Base_Color=(0.55, 0.60, 0.70), Roughness=0.5, Subsurface_Weight=0.3,
                      Emission_Color=(0.35, 0.42, 0.55), Emission_Strength=0.25)
    tr = nb.n("ShaderNodeBsdfTransparent", (200, -300))
    mx = nb.n("ShaderNodeMixShader", (450, 0))
    nb.link(a, mx.inputs[0])
    nb.link(tr.outputs[0], mx.inputs[1])
    nb.link(p.outputs[0], mx.inputs[2])
    nb.output(mx.outputs[0])
    return m


def mat_mist(name, col=(0.16, 0.18, 0.24), dens=0.5):
    m = new_mat(name)
    nb = NB(m)
    tc = nb.texcoord()
    obj = tc.outputs["Object"]
    w = nb.ramp(nb.noise(nb.mapping(obj, (0.03, 0.03, 0.25)), 2.0, 6, 0.6, distortion=0.5).outputs["Fac"],
                [(0.35, 0.0), (0.70, 1.0)])
    su = nb.n("ShaderNodeSeparateXYZ", (-900, -300))
    nb.link(tc.outputs["UV"], su.inputs[0])
    band = nb.ramp(su.outputs[1], [(0.0, 0.0), (0.2, 1.0), (1.0, 0.0)])
    alpha = nb.math("MULTIPLY", nb.math("MULTIPLY", w, band), dens)
    em = nb.n("ShaderNodeEmission", (200, -100))
    em.inputs["Color"].default_value = (*col, 1)
    tr = nb.n("ShaderNodeBsdfTransparent", (200, 100))
    mx = nb.n("ShaderNodeMixShader", (400, 0))
    nb.link(alpha, mx.inputs[0])
    nb.link(tr.outputs[0], mx.inputs[1])
    nb.link(em.outputs[0], mx.inputs[2])
    nb.output(mx.outputs[0])
    return m


def at(gamma_deg, dist, z=0.0):
    """Env-local position that shows up at angle gamma (deg, + to the right) of the turnaround strip."""
    g = math.radians(gamma_deg)
    return V((dist * math.sin(g), dist * math.cos(g), z))


WATER_Z = -1.40
QUAY_R = 17.0


def hull_md(length, beam, depth, bow=0.30, stern=0.10, sheer=0.6, sub=False):
    """Ship hull along local +Y (bow at +Y): lofted sections, flared bow, transom stern, keel at z=0."""
    def fn(u, v, i, j):
        t = v                                    # 0 stern .. 1 bow
        y = lerp(-length / 2, length / 2, t)
        w = beam / 2 * (1 - (max(0.0, t - (1 - bow)) / bow) ** 1.8) * (1 - 0.25 * (max(0.0, stern - t) / stern) ** 2)
        if sub:
            r = beam / 2 * math.sqrt(max(0.0, 1 - (max(0.0, t - 0.88) / 0.12) ** 2)) * \
                math.sqrt(max(0.0, 1 - (max(0.0, 0.10 - t) / 0.10) ** 2) * 0.9 + 0.1)
            return V((r * math.sin(u), y, depth / 2 + r * math.cos(u) * (depth / beam)))
        a = u  # -pi/2 .. pi/2 around the hull section, 0 = keel
        x = w * math.sin(a)
        z = depth * (1 - math.cos(a) ** 1.5) + sheer * (t - 0.5) ** 2 * 2
        return V((x, y, z))

    if sub:
        return grid(fn, lin(0, TAU, 32), lin(0, 1, 40), closed_u=True)
    return grid(fn, lin(-math.pi / 2, math.pi / 2, 16), lin(0, 1, 30))


def build_environment(sc):
    coll = collection("Environment_Harbour")
    root = env_root()

    def put(name, md, mat, smooth_=True):
        return to_obj(name, md, mat, coll, smooth=smooth_, parent=root)

    dock = mat_dock()
    sea = fog_wrap(mat_sea())
    hull_grey = fog_wrap(mat_hull("Warship_Hull_Grey", base=(0.060, 0.066, 0.074)))
    deck_grey = fog_wrap(mat_hull("Warship_Superstructure", base=(0.075, 0.082, 0.090), rust=0.1))
    dark_boat = fog_wrap(mat_hull("Patrol_Boat_Dark", base=(0.020, 0.022, 0.026), rough=0.5))
    sub_black = fog_wrap(mat_hull("Submarine_Anechoic", base=(0.010, 0.011, 0.012), rough=0.35, rust=0.0, metal=0.1))
    heli_grey = fog_wrap(mat_hull("Helicopter_Grey", base=(0.30, 0.31, 0.32), rough=0.40, rust=0.0, metal=0.3),
                         max_fac=0.35)
    rock = fog_wrap(L.mat_simple("Mountain_Rock", (0.050, 0.055, 0.065), rough=0.9, var_col=(0.09, 0.10, 0.11),
                                 var_scale=0.02, bump_scale=0.05, bump_str=0.6), scale=900.0, max_fac=0.92, top=400.0)
    lamp_mat = mat_emit("Floodlight_Glow", (0.85, 0.90, 1.0), 25.0)
    curb = L.mat_simple("Quay_Curb_Concrete", (0.05, 0.052, 0.056), rough=0.6, var_col=(0.03, 0.03, 0.035),
                        bump_scale=6.0, bump_str=0.5)

    # ------------------------------------------------------------------ quay apron, edge curb, sea, surf
    put("Dock_Quay", grid(lambda u, v, i, j: (v * math.cos(u), v * math.sin(u), 0.0), lin(0, TAU, 160),
                          lin(0.0, QUAY_R, 40), closed_u=True), dock)
    put("Quay_Edge_Wall", grid(lambda u, v, i, j: ((QUAY_R + 0.05 * v) * math.cos(u), (QUAY_R + 0.05 * v) * math.sin(u),
                                                   lerp(0.12, WATER_Z - 0.5, v)), lin(0, TAU, 160), lin(0, 1, 3),
                               closed_u=True), curb)
    put("Harbour_Sea", grid(lambda u, v, i, j: (v * math.cos(u), v * math.sin(u), WATER_Z), lin(0, TAU, 128),
                            lin(QUAY_R - 0.2, 4000.0, 36), closed_u=True), sea)
    spray = MD()
    for (g0, g1, amp) in ((-16.0, -5.0, 1.0), (6.0, 15.0, 0.7)):
        def sf(u, v, i, j, g0=g0, g1=g1, amp=amp):
            g = lerp(g0, g1, u)
            r = QUAY_R + 0.4 + 2.5 * v
            crest = (0.5 + 0.5 * math.sin(u * 23.0 + 1.3) * math.sin(u * 9.0)) * amp
            p = at(g, r, 0.0)
            return V((p.x, p.y, WATER_Z + 0.2 + (1.9 * crest + 0.3) * (1 - v) ** 1.5))
        spray.add(grid(sf, lin(0, 1, 120), lin(0, 1, 5)))
    foam = put("Surf_Spray", spray, mat_foam())
    foam.visible_shadow = False

    # ------------------------------------------------------------------ submarine (far left, bow toward the camera)
    sub = MD()
    hull = hull_md(70.0, 8.6, 8.6, sub=True)
    sail = MD()

    def sl(u, v, i, j):
        ca, sa = math.cos(u), math.sin(u)
        w = 1.0 * (1 - 0.35 * v)
        ln = 4.5 * (1 - 0.2 * v)
        x = w * math.copysign(abs(sa) ** 0.5, sa)
        y = ln * math.copysign(abs(ca) ** 0.8, ca) - (1.2 if ca < 0 else 0) * abs(ca)
        return V((x, y, 8.0 + 4.2 * v))
    sail.add(grid(sl, lin(0, TAU, 28), lin(0, 1, 6), closed_u=True, pole_v1=True))
    for k, (dy, h) in enumerate(((1.6, 4.0), (0.4, 5.5), (-0.6, 3.0), (-1.6, 4.5))):
        sail.add(L.tube([V((0, dy, 11.8)), V((0, dy, 11.8 + h * 0.45))], 0.18 - 0.02 * k, 8))
    sail.add(L.box(5.5, 0.6, 0.15).translate((0, 2.0, 11.0)))  # sail planes
    sub.add(hull)
    sub.add(sail)
    m = Matrix.Translation(at(-13.5, 85.0, WATER_Z - 4.2)) @ Matrix.Rotation(math.radians(-(180 - 13.5 - 38)), 4, "Z")
    put("Submarine", sub.transform(m), sub_black)

    # ------------------------------------------------------------------ patrol boat (behind the FRONT/LEFT seam)
    pb = MD()
    pb.add(hull_md(26.0, 6.0, 3.2, bow=0.35, sheer=0.8))
    for (w, l, h, y0, z0) in ((4.8, 8.0, 2.6, -1.0, 3.2), (3.6, 5.0, 2.2, -1.5, 5.8), (2.4, 3.0, 1.6, -1.8, 8.0)):
        pb.add(L.box(w, l, h).translate((0, y0, z0 + h / 2)))
    pb.add(L.tube([V((0, -2.0, 9.6)), V((0, -2.2, 16.0))], 0.16, 8))
    for z in (12.0, 14.0):
        pb.add(L.box(2.6, 0.12, 0.12).translate((0, -2.1, z)))
    pb.add(L.box(1.2, 1.2, 0.8).translate((0, 6.5, 4.0)))      # bow gun mount
    pb.add(L.tube([V((0, 6.5, 4.3)), V((0, 9.0, 4.6))], 0.1, 6))
    m = Matrix.Translation(at(-3.4, 125.0, WATER_Z - 1.5)) @ Matrix.Rotation(math.radians(180 - 3.4 + 12), 4, "Z")
    put("Patrol_Boat", pb.transform(m), dark_boat, smooth_=False)

    # ------------------------------------------------------------------ warship (behind BACK/RIGHT), mast/crane
    ws = MD()
    ws.add(hull_md(120.0, 15.0, 7.5, bow=0.28, sheer=1.2))
    for (w, l, h, y0, z0) in ((12.0, 30.0, 3.0, -8.0, 7.5), (10.0, 18.0, 2.6, -6.0, 10.5), (7.0, 9.0, 2.4, -4.0, 13.1),
                              (11.0, 14.0, 2.6, 22.0, 7.5), (6.0, 6.0, 2.0, -30.0, 7.5)):
        ws.add(L.box(w, l, h).translate((0, y0, z0 + h / 2)))
    ws.add(L.tube([V((0, -4.0, 15.5)), V((0, -4.0, 24.0))], 0.4, 8, scale=lambda t: 1.0 - 0.6 * t))
    for z in (18.5, 21.0, 23.0):
        ws.add(L.box(6.0 - (z - 18.5) * 0.7, 0.25, 0.25).translate((0, -4.0, z)))
    ws.add(L.box(3.0, 4.0, 3.0).translate((0, 8.0, 11.0)))       # funnel
    ws.add(L.box(2.0, 2.0, 1.4).translate((0, 38.0, 10.0)))      # gun turret
    ws.add(L.tube([V((0, 38.5, 10.3)), V((0, 44.0, 10.6))], 0.15, 6))
    for k in range(10):  # railings / rigging verticals along the deck
        ws.add(L.tube([V((6.8, -40 + k * 9.0, 9.0)), V((6.8, -40 + k * 9.0, 10.2))], 0.05, 4))
    m = Matrix.Translation(at(9.5, 170.0, WATER_Z - 3.0)) @ Matrix.Rotation(math.radians(-72), 4, "Z")
    put("Warship", ws.transform(m.copy()), hull_grey, smooth_=False)
    # deck and window lights on the warship and the patrol boat
    dots = MD()
    for (x, y, z) in ((6.2, -14.0, 9.6), (6.2, -6.0, 9.6), (6.2, 2.0, 9.6), (5.1, -6.0, 12.0), (4.0, -4.0, 14.5),
                      (0.0, -4.0, 24.2), (6.2, 20.0, 9.8), (6.2, 27.0, 9.8), (-6.2, -10.0, 9.6), (5.0, 12.0, 10.4)):
        dots.add(L.uv_sphere(0.22, 8, 5).translate(m @ V((x, y, z))))
    mp = Matrix.Translation(at(-3.4, 125.0, WATER_Z - 1.5)) @ Matrix.Rotation(math.radians(180 - 3.4 + 12), 4, "Z")
    for (x, y, z) in ((0.0, -1.0, 6.4), (1.5, -1.0, 6.4), (-1.5, -1.0, 6.4), (0.0, -2.2, 16.0), (2.6, 3.0, 4.0)):
        dots.add(L.uv_sphere(0.18, 8, 5).translate(mp @ V((x, y, z))))
    put("Ship_Lights", dots, mat_emit("Ship_Light_Glow", (1.0, 0.92, 0.80), 30.0))
    # tall lattice mast / crane in front of the warship, under the helicopter
    crane = MD()
    base = at(3.6, 130.0, 0.0)
    crane.add(L.tube([base + V((0, 0, WATER_Z)), base + V((0, 0, 21.0))], 0.45, 10, scale=lambda t: 1.0 - 0.35 * t))
    crane.add(L.box(2.0, 2.0, 1.0).translate(base + V((0, 0, 21.5))))
    for z in (6.0, 11.0, 16.0):
        crane.add(L.box(1.6, 1.6, 0.4).translate(base + V((0, 0, z))))
    put("Harbour_Mast", crane, deck_grey, smooth_=False)

    # ------------------------------------------------------------------ helicopter (hovering above the BACK panel)
    heli = MD()

    def fus(u, v, i, j):
        t = v
        y = lerp(-6.0, 7.0, t)
        r = interp_smooth([(0.0, 0.15), (0.15, 0.9), (0.45, 1.25), (0.75, 1.15), (0.92, 0.8), (1.0, 0.1)], t)[0]
        rz = r * 1.25
        return V((r * math.sin(u), y, rz * math.cos(u) - (0.3 * (1 - t) if t < 0.3 else 0)))

    heli.add(grid(fus, lin(0, TAU, 24), lin(0, 1, 20), closed_u=True))
    heli.add(L.tube([V((0, -5.8, 0.6)), V((0, -15.5, 1.6))], 0.45, 10, scale=lambda t: 1.0 - 0.55 * t))
    heli.add(L.box(0.25, 2.2, 3.2).translate((0, -15.3, 2.8)))               # tail fin
    heli.add(L.box(0.06, 0.2, 3.4).translate((0.35, -15.6, 2.8)))            # tail rotor blur
    heli.add(L.box(1.6, 3.0, 0.9).translate((0, 1.0, 1.7)))                  # engine housing
    heli.add(L.tube([V((0, 1.0, 2.1)), V((0, 1.0, 2.9))], 0.25, 8))        # rotor mast
    for s in (-1, 1):
        heli.add(L.tube([V((s * 1.0, 3.0, -1.4)), V((s * 1.5, 3.0, -2.1))], 0.08, 6))  # gear struts
        heli.add(L.uv_sphere(0.35, 10, 6).translate((s * 1.5, 3.0, -2.3)))
        heli.add(L.box(0.6, 1.6, 0.6).translate((s * 1.45, 0.5, -0.6)))      # sponsons
    rotor = MD()
    rotor.add(grid(lambda u, v, i, j: (v * 8.2 * math.cos(u), v * 8.2 * math.sin(u), 2.95 + 0.25 * v),
                   lin(0, TAU, 48), lin(0.05, 1, 4), closed_u=True))
    blades = MD()
    for k in range(4):
        a = TAU * k / 4 + 0.4
        blades.add(L.box(8.0, 0.5, 0.08).transform(Matrix.Translation((4.0 * math.cos(a), 4.0 * math.sin(a), 3.05))
                                                   @ Matrix.Rotation(a, 4, "Z")))
    hm = Matrix.Translation(at(2.9, 205.0, 41.0)) @ Matrix.Rotation(math.radians(-38), 4, "Z") @ \
        Matrix.Rotation(math.radians(8), 4, "X") @ Matrix.Rotation(math.radians(-6), 4, "Y")
    put("Helicopter", heli.transform(hm), heli_grey)
    put("Helicopter_Blades", blades.transform(hm.copy()), heli_grey, smooth_=False)
    rd = put("Helicopter_Rotor_Blur", rotor.transform(hm.copy()), mat_mist("Rotor_Blur", (0.10, 0.11, 0.13), 0.35))
    rd.visible_shadow = False

    # ------------------------------------------------------------------ mountains (right) and low ridges (left)
    mts = MD()
    for (g0, g1, dist, hmax, seed) in ((4.0, 32.0, 1800.0, 260.0, 1), (-30.0, -6.0, 2600.0, 140.0, 2),
                                       (10.0, 40.0, 2600.0, 380.0, 3)):
        def mf(u, v, i, j, g0=g0, g1=g1, dist=dist, hmax=hmax, seed=seed):
            g = lerp(g0, g1, u)
            ridge = hmax * (0.45 + 0.55 * abs(math.sin(u * 7.3 + seed)) ** 1.5) * (0.6 + 0.4 * math.sin(u * 3.1 + seed * 2))
            ridge *= smooth(min(u, 1 - u) / 0.12)
            p = at(g, dist + 120.0 * v, WATER_Z)
            return V((p.x, p.y, WATER_Z + ridge * (1 - v) ** 0.5 + 15.0 * L.fbm(V((u * 9, v * 3, seed))) * (1 - v)))
        mts.add(grid(mf, lin(0, 1, 90), lin(0, 1, 8)))
    put("Mountains", mts, rock)

    # ------------------------------------------------------------------ floodlights at the water's edge + lamp posts
    lamps = MD()
    for li, (g, d_, h, r) in enumerate(((-13.6, 34.0, 0.15, 0.10), (-11.0, 40.0, 0.05, 0.08), (-3.4, 30.0, 0.10, 0.09),
                        (12.0, 17.6, 0.55, 0.16), (8.0, 45.0, 0.0, 0.10), (2.6, 60.0, -0.2, 0.10))):
        p = at(g, d_, h)
        lamps.add(L.uv_sphere(r, 16, 10).translate(p))
        ld = bpy.data.lights.new("Floodlight_%d" % li, "POINT")
        ld.energy = 250.0
        ld.color = (0.80, 0.88, 1.0)
        ld.shadow_soft_size = 0.3
        lo = bpy.data.objects.new(ld.name, ld)
        coll.objects.link(lo)
        lo.location = p + V((0, -0.4, 0.0))
        lo.parent = root
    put("Floodlight_Bulbs", lamps, lamp_mat)

    # ------------------------------------------------------------------ mist banks over the water
    for k, (dist, h, dens) in enumerate(((45.0, 6.0, 0.35), (110.0, 14.0, 0.45), (260.0, 40.0, 0.55))):
        card = grid(lambda u, v, i, j, dist=dist, h=h: tuple(at(lerp(-28, 28, u), dist, WATER_Z + v * h)),
                    lin(0, 1, 12), lin(0, 1, 4))
        ob = put(f"Mist_{k}", card, mat_mist(f"Mist_{k}", (0.14, 0.16, 0.22), dens))
        ob.visible_shadow = False
        ob.visible_diffuse = False
