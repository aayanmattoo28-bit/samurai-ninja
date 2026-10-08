"""Navy SEAL set, built as the concept sheet's turnaround: ONE wide, low, level long-lens shot of the wet harbour
quay in which the same character stands four times (FRONT, LEFT, BACK, RIGHT), in front of one continuous dusk
panorama -- submarine, patrol boat, crane and breakwater, warship with its tall mast, a hovering helicopter, hazy
fjord mountains and a warm sunset glow -- with surf breaking on the quay edge and bollard lamps streaking the wet
dock.  Lights are world-fixed suns, so every figure is cool on its screen-left and warm on its screen-right edges.

Measurements (sheet px of the 1144 x 634 turnaround panel; 322.6 px/m on the figure plane) come from the concept.
A sheet point (x, y) seen d metres from the camera maps to world with sheet_pt(); every background element is
placed that way, at the distance chosen for it.
"""
import math
import os

import bpy
from mathutils import Matrix

import seal_lib as L
from seal_lib import MD, NB, TAU, V, collection, grid, interp_smooth, lerp, lin, new_mat, to_obj

HERE = os.path.dirname(os.path.abspath(__file__))
TEX_DIR = os.path.join(os.path.dirname(HERE), "textures")

# --- the turnaround shot ------------------------------------------------------------------------------------
SHEET_W, SHEET_H = 1144.0, 634.0
PX_M = 322.6                      # sheet px per metre on the figure plane
SOLE_Y, MID_X = 620.5, 572.0      # sheet row of the sole line, sheet column of the camera axis
CAM_D, EYE = 13.3, 0.37           # camera distance to the figure plane, eye height (just under the knee pads)
LENS, SENSOR_W, SHIFT_Y, FSTOP = 135.0, 36.0, 0.161, 8.0
RES = (2288, 1268)                # 2x the sheet panel
# view -> (figure X on the dock, rotation about Z)
# (the LEFT view is placed by its torso's mid-depth, sheet x 534, which the sheet draws 12 px behind the leg axis)
FIGURES = {"Front": (-0.852, 0.0), "Left": (-0.118, -90.0), "Back": (0.546, 180.0), "Right": (1.389, 90.0)}
# view -> panel columns (sheet px); the panels split at the gaps between the figures
PANELS = {"Front": (0, 441), "Left": (441, 632), "Back": (632, 897), "Right": (897, 1144)}

WATER_Z = -1.5
# far edge of the quay (world X, Y): it recedes to the right, as the sheet's surf line rises from y 547 to y 523
QUAY_EDGE = [(-80.0, 20.2), (-4.55, 20.8), (-0.85, 22.3), (0.67, 28.9), (4.30, 50.8), (9.29, 56.4), (80.0, 135.6)]

SKY_D = 8000.0                                # emission card with the sky (make_seal_sky.py)
SKY_WINDOW = (-200.0, -120.0, 1344.0, 640.0)  # sheet px covered by sky_backdrop.png
SKY_SCALE = 1.25                              # texture px per sheet px
SKY_GAIN, SKY_GAMMA = 2.0, 2.2                # linear radiance = SKY_GAIN * texture ** SKY_GAMMA


def sheet_pt(x, y, d):
    """World point that the camera sees at sheet pixel (x, y), d metres away."""
    k = d / CAM_D
    return V(((x - MID_X) / PX_M * k, d - CAM_D, EYE + ((SOLE_Y - y) / PX_M - EYE) * k))


def to_sheet(p):
    """Sheet pixel (x, y) of a world point."""
    k = (p[1] + CAM_D) / CAM_D
    return MID_X + PX_M * p[0] / k, SOLE_Y - PX_M * (EYE + (p[2] - EYE) / k)


def quay_y(x):
    pts = QUAY_EDGE
    if x <= pts[0][0]:
        return pts[0][1]
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        if x <= x1:
            return lerp(y0, y1, (x - x0) / (x1 - x0))
    return pts[-1][1]


def env_root():
    e = bpy.data.objects.get("Env_Root")
    if e is None:
        e = bpy.data.objects.new("Env_Root", None)
        collection("Environment_Harbour").objects.link(e)
        e.empty_display_size = 2.0
    return e


# --- render settings ---------------------------------------------------------------------------------------
def setup_render(sc, calib=False):
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
    cy.transparent_max_bounces = 32
    cy.caustics_reflective = False
    cy.caustics_refractive = False
    cy.blur_glossy = 0.5
    cy.sample_clamp_indirect = 6.0
    cy.filter_width = 1.1
    sc.render.resolution_x, sc.render.resolution_y = RES
    sc.render.resolution_percentage = 100
    # Standard view: the sheet's measured display colours are reproduced directly (lamps and speculars clip to white
    # and bloom in the compositor, as in the concept)
    sc.view_settings.view_transform = "Standard"
    sc.view_settings.look = "None"
    sc.view_settings.exposure = 0.0
    try:
        compositor(sc, calib)
    except Exception as e:  # pragma: no cover
        print("compositor skipped:", e)


def compositor(sc, calib=False):
    """Low-key dusk grade: fog-glow bloom on the lamps and visors, navy lift in the shadows, warm gain in the
    highlights, a little less saturation, and the sheet's vignette (corners and the bottom edge; vignette.png is
    written by make_seal_sky.py, which also divides it out of the sky).  calib=True leaves out the spatial effects
    so a flat ramp can be measured."""
    sc.use_nodes = True
    nt = sc.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    Lk = nt.links.new
    rl = nt.nodes.new("CompositorNodeRLayers")
    src = rl.outputs["Image"]
    if not calib:
        gl = nt.nodes.new("CompositorNodeGlare")
        gl.glare_type = "FOG_GLOW"
        gl.quality = "HIGH"
        gl.threshold = 1.0
        gl.size = 7
        gl.mix = -0.7
        Lk(src, gl.inputs["Image"])
        src = gl.outputs["Image"]
    cb = nt.nodes.new("CompositorNodeColorBalance")
    cb.correction_method = "LIFT_GAMMA_GAIN"
    cb.lift = (0.985, 0.99, 1.02)
    cb.gamma = (1.0, 1.0, 1.0)
    cb.gain = (1.03, 1.0, 0.96)
    Lk(src, cb.inputs["Image"])
    hs = nt.nodes.new("CompositorNodeHueSat")
    hs.inputs["Saturation"].default_value = 0.88
    Lk(cb.outputs["Image"], hs.inputs["Image"])
    src = hs.outputs["Image"]
    if not calib and os.path.exists(os.path.join(TEX_DIR, "vignette.png")):
        vi = nt.nodes.new("CompositorNodeImage")
        vi.image = L.image("vignette.png", "Non-Color")
        scl = nt.nodes.new("CompositorNodeScale")
        scl.space = "RENDER_SIZE"
        scl.frame_method = "STRETCH"
        Lk(vi.outputs["Image"], scl.inputs["Image"])
        mul = nt.nodes.new("CompositorNodeMixRGB")
        mul.blend_type = "MULTIPLY"
        mul.inputs["Fac"].default_value = 1.0
        Lk(src, mul.inputs[1])
        Lk(scl.outputs["Image"], mul.inputs[2])
        src = mul.outputs["Image"]
    comp = nt.nodes.new("CompositorNodeComposite")
    Lk(src, comp.inputs["Image"])


# --- world (lighting / reflections only; the camera sees the sky card) -------------------------------------
def world(sc):
    """Overcast dusk dome (lighting and reflections only): slate zenith, blue-grey horizon, the peach glow toward
    the setting sun (+X +Y), dark below the horizon.  Camera rays see a plain dark studio grey."""
    w = bpy.data.worlds.new("Harbour_Dusk_Dome")
    sc.world = w
    nb = NB(w)
    tc = nb.n("ShaderNodeTexCoord", (-1200, 0))
    d = tc.outputs["Generated"]
    sep = nb.n("ShaderNodeSeparateXYZ", (-1000, 0))
    nb.link(d, sep.inputs[0])
    col = nb.ramp(sep.outputs[2], [(0.0, (0.010, 0.014, 0.020)), (0.02, (0.112, 0.162, 0.246)),
                                   (0.25, (0.050, 0.075, 0.120)), (1.0, (0.023, 0.042, 0.073))])
    dp = nb.n("ShaderNodeVectorMath", (-800, -300))
    dp.operation = "DOT_PRODUCT"
    nb.link(d, dp.inputs[0])
    dp.inputs[1].default_value = (0.75, 0.63, 0.21)
    glow = nb.math("POWER", nb.math("MAXIMUM", dp.outputs["Value"], 0.0), 6.0)
    col = nb.mix(nb.math("MULTIPLY", glow, nb.ramp(sep.outputs[2], [(-0.02, 0.0), (0.0, 1.0), (0.5, 0.2)])), col,
                 (0.479, 0.386, 0.392))
    bg = nb.n("ShaderNodeBackground", (200, 0))
    nb.link(col, bg.inputs["Color"])
    bg.inputs["Strength"].default_value = 0.55
    # the camera sees a plain dark studio grey; the dusk dome only lights and reflects on the character
    studio = nb.n("ShaderNodeBackground", (200, -200))
    studio.inputs["Color"].default_value = (0.020, 0.021, 0.024, 1)
    lp = nb.n("ShaderNodeLightPath", (0, 300))
    mx = nb.n("ShaderNodeMixShader", (400, 0))
    nb.link(lp.outputs["Is Camera Ray"], mx.inputs[0])
    nb.link(bg.outputs[0], mx.inputs[1])
    nb.link(studio.outputs[0], mx.inputs[2])
    o = nb.n("ShaderNodeOutputWorld", (600, 0))
    nb.link(mx.outputs[0], o.inputs["Surface"])


# --- lights ------------------------------------------------------------------------------------------------
def sun(coll, name, toward, strength, color, angle):
    ld = bpy.data.lights.new(name, "SUN")
    ld.energy = strength
    ld.color = color
    ld.angle = math.radians(angle)
    ob = bpy.data.objects.new(name, ld)
    coll.objects.link(ob)
    v = V(toward).normalized()
    ob.location = V((0.27, 0.0, 1.0)) + v * 4.0
    ob.rotation_euler = (-v).to_track_quat("-Z", "Y").to_euler()
    return ob


def build_lights(sc):
    """World-fixed sun rig measured from the sheet: warm-neutral key front-right-high, cool moonlit fill
    front-left, strong low peach rim from the sunset behind-right, blue sky rim behind-left."""
    coll = collection("Lighting")
    world(sc)
    sun(coll, "Key_Front_Right", (0.53, -0.63, 0.57), 2.0, (0.888, 0.761, 0.658), 12)
    sun(coll, "Fill_Moon_Front_Left", (-0.64, -0.64, 0.42), 0.4, (0.397, 0.503, 0.716), 30)
    sun(coll, "Rim_Sunset_Back_Right", (0.75, 0.63, 0.21), 3.0, (0.930, 0.571, 0.371), 6)
    sun(coll, "Rim_Sky_Back_Left", (-0.61, 0.61, 0.50), 2.0, (0.275, 0.397, 0.672), 10)


# --- camera and the four views -----------------------------------------------------------------------------
def build_cameras(sc):
    coll = collection("Cameras")
    cd = bpy.data.cameras.new("CAM_Turnaround")
    cd.lens = LENS
    cd.sensor_fit = "HORIZONTAL"
    cd.sensor_width = SENSOR_W
    cd.shift_y = SHIFT_Y
    cd.clip_start = 0.1
    cd.clip_end = 12000.0
    cd.dof.use_dof = True
    cd.dof.focus_distance = CAM_D
    cd.dof.aperture_fstop = FSTOP
    ob = bpy.data.objects.new("CAM_Turnaround", cd)
    coll.objects.link(ob)
    ob.location = (0.0, -CAM_D, EYE)
    ob.rotation_euler = (math.radians(90.0), 0.0, 0.0)
    sc.camera = ob
    return ob


def build_turnaround(sc):
    """The character itself is the FRONT figure; LEFT, BACK and RIGHT are linked instances of it, turned so their
    left side, back and right side face the camera."""
    char = bpy.data.collections.get("NavySeal_Character")
    root = bpy.data.objects.get("NavySeal_Root")
    if char is None or root is None:
        return
    fx = FIGURES["Front"][0]
    root.location = (fx, 0.0, 0.0)
    char.instance_offset = (fx, 0.0, 0.0)
    coll = collection("Turnaround_Views")
    # the sheet shows the carbine slung on the back in the LEFT, BACK and RIGHT views and in the right hand in the
    # FRONT view: the slung carbine is its own collection, excluded here and instanced by the three side/back views
    slung = bpy.data.collections.get("Carbine_Slung")
    if slung is not None:
        slung.instance_offset = (fx, 0.0, 0.0)
        lc = bpy.context.view_layer.layer_collection.children.get("Carbine_Slung")
        if lc is not None:
            lc.exclude = True
    for v in ("Left", "Back", "Right"):
        x, rot = FIGURES[v]
        for src, tag in ((char, "View"), (slung, "Carbine_Slung")):
            if src is None:
                continue
            e = bpy.data.objects.new("NavySeal_%s_%s" % (v, tag), None)
            e.instance_type = "COLLECTION"
            e.instance_collection = src
            e.location = (x, 0.0, 0.0)
            e.rotation_euler = (0.0, 0.0, math.radians(rot))
            e.empty_display_size = 0.3
            coll.objects.link(e)


# --- environment materials ---------------------------------------------------------------------------------
def fog_wrap(mat, fog_col=(0.150, 0.190, 0.255), near=30.0, scale=600.0, max_fac=0.75, top=600.0, top_keep=0.7):
    """Aerial perspective: exponential distance haze toward a cool blue-grey (about 50% at 500 m), thinner with
    height."""
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
    hr.inputs["To Max"].default_value = top_keep
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


def mat_sky():
    m = new_mat("Sky_Backdrop_Dusk")
    nb = NB(m)
    tc = nb.texcoord()
    L.image("sky_backdrop.png", "Non-Color")
    t = nb.img("sky_backdrop.png", tc.outputs["UV"], "EXTEND")
    pw = nb.n("ShaderNodeGamma", (-300, 0))
    nb.link(t.outputs["Color"], pw.inputs["Color"])
    pw.inputs["Gamma"].default_value = SKY_GAMMA
    em = nb.n("ShaderNodeEmission", (0, 0))
    nb.link(pw.outputs["Color"], em.inputs["Color"])
    em.inputs["Strength"].default_value = SKY_GAIN
    nb.output(em.outputs[0])
    return m


def mat_dock(name="Dock_Concrete_Wet"):
    """Rain-soaked concrete quay: noise-mottled concrete with darker stains, a thin film of standing water (big
    mirror puddles, damp areas, a few dry patches), broad ripple bands parallel to the quay that stretch the lamp
    reflections into dashed vertical streaks, fine grit, scattered droplets, one expansion joint aimed at the
    camera between the BACK figure's feet."""
    m = new_mat(name)
    nb = NB(m)
    tc = nb.texcoord()
    obj = tc.outputs["Object"]
    n1 = nb.noise(obj, 0.8, 8, 0.62)
    col = nb.mix(nb.ramp(n1.outputs["Fac"], [(0.35, 0.0), (0.7, 1.0)]), (0.019, 0.023, 0.031), (0.028, 0.033, 0.043))
    stain = nb.ramp(nb.noise(obj, 0.35, 6, 0.6, distortion=0.8).outputs["Fac"], [(0.55, 0.0), (0.68, 1.0)])
    col = nb.mix(nb.math("MULTIPLY", stain, 0.8), col, (0.010, 0.013, 0.018))
    # expansion joint: the line through (0.57, 0.6) and (0.98, 10.4), aimed at the camera
    sx = nb.n("ShaderNodeSeparateXYZ", (-900, -500))
    nb.link(obj, sx.inputs[0])
    a0, b0 = V((0.57, 0.6, 0.0)), V((0.98, 10.4, 0.0))
    dv = (b0 - a0).normalized()
    dist = nb.math("ABSOLUTE", nb.math("SUBTRACT", nb.math("MULTIPLY", nb.math("SUBTRACT", sx.outputs[0], a0.x), dv.y),
                                       nb.math("MULTIPLY", nb.math("SUBTRACT", sx.outputs[1], a0.y), dv.x)))
    joint = nb.math("MULTIPLY", nb.math("LESS_THAN", dist, 0.009),
                    nb.math("MULTIPLY", nb.math("GREATER_THAN", sx.outputs[1], 0.3),
                            nb.math("LESS_THAN", sx.outputs[1], 20.0)))
    col = nb.mix(joint, col, (0.006, 0.007, 0.009))
    # water film: puddles (most of the quay, more toward the far edge), damp, a few dry patches
    wn = nb.noise(obj, 0.22, 5, 0.55)
    far = nb.math("MULTIPLY", nb.math("MAXIMUM", nb.math("SUBTRACT", sx.outputs[1], 2.0), 0.0), 0.003)
    pud2 = nb.noise(obj, 1.3, 4, 0.6)
    puddle = nb.ramp(nb.math("ADD", nb.math("ADD", wn.outputs["Fac"], far),
                             nb.math("MULTIPLY", nb.math("SUBTRACT", pud2.outputs["Fac"], 0.5), 0.35)),
                     [(0.50, 0.0), (0.56, 1.0)])
    dry = nb.ramp(nb.noise(obj, 0.5, 4, 0.6).outputs["Fac"], [(0.60, 0.0), (0.66, 1.0)])
    rough = nb.mixf(puddle, nb.mixf(dry, 0.42, 0.65), 0.09)
    drop = nb.ramp(nb.noise(obj, 260.0, 2, 0.5).outputs["Fac"], [(0.72, 0.0), (0.76, 1.0)])
    rough = nb.mixf(nb.math("MULTIPLY", drop, nb.math("SUBTRACT", 1.0, puddle)), rough, 0.03)
    rough = nb.mixf(joint, rough, 0.6)
    col = nb.mix(nb.math("MULTIPLY", puddle, 0.5), col, (0.012, 0.014, 0.019))
    # ripple bands parallel to the quay (crests along X, ~1 m apart) + grit
    wv = nb.n("ShaderNodeTexWave", (-900, -800), wave_type="BANDS", bands_direction="Y")
    wv.inputs["Scale"].default_value = 0.30
    wv.inputs["Distortion"].default_value = 6.0
    wv.inputs["Detail"].default_value = 4.0
    nb.link(obj, wv.inputs["Vector"])
    grit = nb.noise(obj, 40.0, 4, 0.6)
    rip = nb.noise(nb.mapping(obj, (0.6, 2.2, 1.0)), 1.2, 6, 0.65, distortion=1.5)
    band = nb.ramp(nb.math("ADD", nb.math("MULTIPLY", wv.outputs["Fac"], 0.4), nb.math("MULTIPLY", rip.outputs["Fac"], 0.6)),
                   [(0.40, 0.0), (0.62, 1.0)])
    rough = nb.mixf(nb.math("MULTIPLY", puddle, band), rough, 0.26)      # broken, dashed reflections
    h = nb.math("ADD", wv.outputs["Fac"], nb.math("MULTIPLY", grit.outputs["Fac"], nb.mixf(puddle, 0.6, 0.05)))
    h = nb.math("SUBTRACT", h, nb.math("MULTIPLY", joint, 0.8))
    h = nb.math("ADD", h, nb.math("MULTIPLY", drop, 0.3))
    # at these grazing angles any glossy surface mirrors the sky; the sheet's dock only mirrors in its puddles, so
    # the damp concrete is a rough, non-reflective layer and the puddles are a separate glossy water film
    nrm = nb.bump(h, 0.12, 0.01)
    wet = nb.principled(Base_Color=nb.mix(0.5, col, (0.006, 0.007, 0.010)),
                        Roughness=nb.mixf(band, 0.04, 0.18), Specular_IOR_Level=0.5, IOR=1.33, Normal=nrm)
    damp = nb.principled(Base_Color=col, Roughness=nb.mixf(dry, 0.55, 0.75), Specular_IOR_Level=0.0, Normal=nrm)
    p = nb.n("ShaderNodeMixShader", (400, 0))
    nb.link(nb.ramp(nb.math("MAXIMUM", nb.math("MULTIPLY", puddle, nb.math("SUBTRACT", 1.0, joint)),
                            nb.math("MULTIPLY", drop, 0.6)), [(0.0, 0.0), (1.0, 1.0)]), p.inputs[0])
    nb.link(damp.outputs[0], p.inputs[1])
    nb.link(wet.outputs[0], p.inputs[2])
    nb.output(p.outputs[0])
    return m


def mat_sea(name="Harbour_Water"):
    m = new_mat(name)
    nb = NB(m)
    tc = nb.texcoord()
    obj = tc.outputs["Object"]
    w1 = nb.noise(nb.mapping(obj, (0.08, 0.25, 1.0)), 0.6, 6, 0.6)     # long swells
    w2 = nb.noise(nb.mapping(obj, (0.6, 1.4, 1.0)), 1.6, 5, 0.6)       # chop
    w3 = nb.noise(obj, 6.0, 3, 0.5)
    h = nb.math("ADD", nb.math("ADD", w1.outputs["Fac"], nb.math("MULTIPLY", w2.outputs["Fac"], 0.5)),
                nb.math("MULTIPLY", w3.outputs["Fac"], 0.15))
    p = nb.principled(Base_Color=(0.004, 0.011, 0.017), Roughness=0.08, IOR=1.33, Normal=nb.bump(h, 0.6, 0.15))
    nb.output(p.outputs[0])
    return m


def mat_paint(name, base, rough=0.5, metal=0.2, streak=0.35, rust=0.08):
    """Painted steel at a distance: base colour with vertical streaks and faint rust runs."""
    m = new_mat(name)
    nb = NB(m)
    tc = nb.texcoord()
    obj = tc.outputs["Object"]
    st = nb.noise(nb.mapping(obj, (1.0, 1.0, 0.08)), 0.6, 6, 0.6)
    col = nb.mix(nb.math("MULTIPLY", nb.ramp(st.outputs["Fac"], [(0.4, 0.0), (0.7, 1.0)]), streak), base,
                 tuple(c * 0.55 for c in base))
    rs = nb.noise(nb.mapping(obj, (1.0, 1.0, 0.2)), 1.5, 6, 0.7)
    col = nb.mix(nb.math("MULTIPLY", nb.ramp(rs.outputs["Fac"], [(0.64, 0.0), (0.75, 1.0)]), rust), col,
                 (0.05, 0.026, 0.016))
    p = nb.principled(Base_Color=col, Roughness=rough, Metallic=metal)
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


def mat_foam(name="Surf_Foam_Spray"):
    """Breaking surf and spray: frothy blue-white streaks with a noisy alpha, brighter crests."""
    m = new_mat(name)
    nb = NB(m)
    tc = nb.texcoord()
    obj = tc.outputs["Object"]
    n = nb.noise(nb.mapping(obj, (1.2, 1.2, 3.5)), 2.5, 10, 0.72, distortion=0.8)
    sep = nb.n("ShaderNodeSeparateXYZ", (-1000, -400))
    nb.link(tc.outputs["UV"], sep.inputs[0])
    v = sep.outputs[1]                                       # 0 at the base .. 1 at the crest
    a = nb.ramp(nb.math("SUBTRACT", n.outputs["Fac"], nb.math("MULTIPLY", v, 0.30)), [(0.22, 0.0), (0.38, 1.0)])
    a = nb.math("MULTIPLY", a, nb.ramp(v, [(0.0, 1.0), (0.85, 0.8), (1.0, 0.0)]))
    col = nb.mix(nb.ramp(nb.math("ADD", v, nb.math("MULTIPLY", n.outputs["Fac"], 0.6)), [(0.5, 0.0), (1.0, 1.0)]),
                 (0.060, 0.105, 0.160), (0.63, 0.73, 0.79))
    p = nb.principled(Base_Color=col, Roughness=0.55, Subsurface_Weight=0.3, Emission_Color=col,
                      Emission_Strength=0.9)
    tr = nb.n("ShaderNodeBsdfTransparent", (200, -300))
    mx = nb.n("ShaderNodeMixShader", (450, 0))
    nb.link(a, mx.inputs[0])
    nb.link(tr.outputs[0], mx.inputs[1])
    nb.link(p.outputs[0], mx.inputs[2])
    nb.output(mx.outputs[0])
    return m


def mat_rock(name="Mountain_Rock_Hazed"):
    """Steep fjord rock with vertical striations (seen through heavy haze)."""
    m = new_mat(name)
    nb = NB(m)
    tc = nb.texcoord()
    obj = tc.outputs["Object"]
    st = nb.noise(nb.mapping(obj, (0.02, 0.02, 0.0025)), 1.0, 8, 0.65)
    n2 = nb.noise(obj, 0.01, 6, 0.6)
    col = nb.mix(nb.ramp(st.outputs["Fac"], [(0.35, 0.0), (0.7, 1.0)]), (0.022, 0.026, 0.033), (0.055, 0.060, 0.070))
    col = nb.mix(nb.math("MULTIPLY", nb.ramp(n2.outputs["Fac"], [(0.5, 0.0), (0.7, 1.0)]), 0.5), col,
                 (0.012, 0.014, 0.018))
    geo = nb.n("ShaderNodeNewGeometry", (-900, -600))
    gz = nb.n("ShaderNodeSeparateXYZ", (-700, -600))
    nb.link(geo.outputs["Normal"], gz.inputs[0])
    ledge = nb.math("MULTIPLY", nb.ramp(gz.outputs[2], [(0.62, 0.0), (0.80, 1.0)]),
                    nb.ramp(nb.noise(obj, 0.02, 6, 0.6).outputs["Fac"], [(0.45, 0.0), (0.6, 1.0)]))
    col = nb.mix(nb.math("MULTIPLY", ledge, 0.8), col, (0.10, 0.11, 0.125))      # pale streaks on the ledges
    p = nb.principled(Base_Color=col, Roughness=0.9, Normal=nb.bump(st.outputs["Fac"], 0.8, 30.0))
    nb.output(p.outputs[0])
    return m


def mat_rotor_disc(name="Rotor_Blur_Disc"):
    """Semi-transparent motion-blur disc of the main rotor."""
    m = new_mat(name)
    nb = NB(m)
    em = nb.n("ShaderNodeEmission", (0, -100))
    em.inputs["Color"].default_value = (0.082, 0.084, 0.11, 1)
    tr = nb.n("ShaderNodeBsdfTransparent", (0, 100))
    mx = nb.n("ShaderNodeMixShader", (300, 0))
    mx.inputs[0].default_value = 0.07
    nb.link(tr.outputs[0], mx.inputs[1])
    nb.link(em.outputs[0], mx.inputs[2])
    nb.output(mx.outputs[0])
    return m


# --- environment geometry helpers --------------------------------------------------------------------------
def lathe_axis(profile, a, axis_dir, up=(0, 0, 1), n=32, nt=48):
    """Body of revolution: profile [(t, r)] along axis_dir from point a (t in metres)."""
    ax = V(axis_dir).normalized()
    side = ax.cross(V(up)).normalized()
    upv = side.cross(ax).normalized()
    t0, t1 = profile[0][0], profile[-1][0]

    def f(u, v, i, j):
        t = lerp(t0, t1, v)
        r = interp_smooth(profile, t)[0]
        return V(a) + ax * t + side * (r * math.cos(u)) + upv * (r * math.sin(u))
    return grid(f, lin(0, TAU, n), lin(0, 1, nt), closed_u=True)


def screen_box(x0, x1, y0, y1, d, depth):
    """Box whose camera-facing face covers sheet rect (x0..x1, y0..y1) at distance d, `depth` metres deep."""
    a, b = sheet_pt(x0, y1, d), sheet_pt(x1, y0, d)
    return L.box(b.x - a.x, depth, b.z - a.z).translate(((a.x + b.x) / 2, a.y + depth / 2, (a.z + b.z) / 2))


def screen_poly(outline, d, depth):
    """Prism from a sheet-space outline [(x, y)] at distance d, extruded `depth` metres away from the camera."""
    md = MD()
    pts = [sheet_pt(x, y, d) for x, y in outline]
    n = len(pts)
    md.v.extend(pts + [p + V((0, depth, 0)) for p in pts])
    cf = sum(pts, V()) / n
    md.v.extend([cf, cf + V((0, depth, 0))])
    for k in range(n):
        k2 = (k + 1) % n
        md.f.append((k, k2, n + k2, n + k))
        md.uv.append([(0, 0), (1, 0), (1, 1), (0, 1)])
        md.f.append((2 * n, k2, k))
        md.uv.append([(0.5, 0.5), (0, 0), (1, 0)])
        md.f.append((2 * n + 1, n + k, n + k2))
        md.uv.append([(0.5, 0.5), (0, 0), (1, 0)])
    md.mi = [0] * len(md.f)
    return md


def screen_post(x, y0, y1, d, w_px):
    """Thin vertical cylinder covering sheet column x, rows y0..y1, at distance d."""
    a, b = sheet_pt(x, y1, d), sheet_pt(x, y0, d)
    r = w_px / 2 / PX_M * d / CAM_D
    return L.tube([a, b], r, 8)


def railing(pts, h=1.0, gap=1.2, r=0.03, n=6):
    """Ship railing along a polyline: posts every `gap` metres, a top rail and a mid rail."""
    md = MD()
    path = L.resample(pts, max(2, int(L.path_length(pts) / gap) + 1))
    for q in path:
        md.add(L.tube([q, q + V((0, 0, h))], r, n, cap0=False))
    for f in (1.0, 0.5):
        md.add(L.tube([q + V((0, 0, h * f)) for q in pts], r * 0.8, n))
    return md


def patrol_boat_parts():
    """Harbour patrol boat / tug in local coordinates (x starboard, y forward, z up, waterline at z = 0): flared V
    hull with sheer and a raised bow bulwark, two-level deckhouse with a window band, bridge with a wide windscreen
    and a railed top, exhaust stack, mast with yard and radar bar, foredeck posts.  ~22 m long, 4.5 m beam."""
    P = {k: MD() for k in ("hull", "house", "glass", "rails")}
    Lh = 22.0

    def hull(u, v, i, j):
        y = lerp(-Lh / 2, Lh / 2, v)                                   # stern .. bow
        t = (y + Lh / 2) / Lh
        half = 2.25 * (1 - max(0.0, (t - 0.60) / 0.40) ** 1.7) * (1 - 0.12 * max(0.0, (0.12 - t) / 0.12))
        deck = 3.3 + 0.7 * max(0.0, t - 0.7) ** 1.3 * 3
        a = u                                                           # -pi/2 (port deck) .. pi/2 (starboard deck)
        x = half * math.sin(a) * (0.85 + 0.15 * abs(math.sin(a)))      # flare toward the deck
        z = lerp(-1.6 * (1 - 0.5 * t), deck, abs(math.sin(a)) ** 1.6)
        return V((x, y, z))
    P["hull"].add(grid(hull, lin(-math.pi / 2, math.pi / 2, 18), lin(0, 1, 28)))
    P["hull"].add(grid(lambda u, v, i, j: V((lerp(-2.2, 2.2, u) * (1 - max(0.0, (v - 0.60) / 0.40) ** 1.7),
                                               lerp(-Lh / 2, Lh / 2, v), 3.3 + 2.1 * max(0.0, v - 0.7) ** 1.3)),
                       lin(0, 1, 2), lin(0, 1, 28)))                    # deck
    bow = [V((s * 2.2 * (1 - max(0.0, (t - 0.60) / 0.40) ** 1.7), lerp(-Lh / 2, Lh / 2, t),
              3.3 + 2.1 * max(0.0, t - 0.7) ** 1.3)) for s in (-1, 1) for t in lin(0.62, 0.99, 6)]
    P["rails"].add(railing(bow[:6], 1.0, 1.0, 0.035))
    P["rails"].add(railing(bow[6:], 1.0, 1.0, 0.035))
    # deckhouse (two levels) and bridge
    for (w, y0, y1, z0, z1) in ((4.0, -7.0, 2.2, 3.3, 5.0), (3.5, -5.0, 1.4, 5.0, 6.1)):
        P["house"].add(L.box(w, y1 - y0, z1 - z0).translate((0.0, (y0 + y1) / 2, (z0 + z1) / 2)))
    for k in range(5):                                                  # front window band of the lower deckhouse
        P["glass"].add(L.box(0.55, 0.06, 0.45).translate((-1.4 + 0.7 * k, 2.23, 4.45)))
    for s in (-1, 1):
        for k in range(4):
            P["glass"].add(L.box(0.06, 0.6, 0.45).translate((s * 2.03, -5.8 + 1.8 * k, 4.45)))
    P["glass"].add(L.box(3.1, 0.06, 0.55).translate((0.0, 1.43, 5.65)))  # bridge windscreen
    for s in (-1, 1):
        P["glass"].add(L.box(0.06, 2.4, 0.5).translate((s * 1.78, -0.6, 5.65)))
    top = [V((-1.75, 1.4, 6.1)), V((1.75, 1.4, 6.1)), V((1.75, -5.0, 6.1)), V((-1.75, -5.0, 6.1)), V((-1.75, 1.4, 6.1))]
    P["rails"].add(railing(top, 0.9, 1.0, 0.03))
    P["house"].add(L.tube([V((0, -6.2, 5.0)), V((0, -6.3, 7.3))], 0.42, 12))   # exhaust stack
    P["house"].add(L.tube([V((0, -2.4, 6.1)), V((0, -2.5, 8.25))], 0.10, 8))   # mast
    P["house"].add(L.box(1.8, 0.10, 0.10).translate((0, -2.45, 7.2)))         # yard
    P["house"].add(L.box(1.3, 0.25, 0.12).translate((0, -2.45, 7.75)))        # radar bar
    P["house"].add(L.box(0.6, 0.6, 0.5).translate((1.1, -3.6, 6.35)))         # searchlight / box
    for xp in (-1.0, 1.0):                                                    # foredeck posts
        P["house"].add(L.tube([V((xp, 6.5, 3.35)), V((xp, 6.5, 5.0))], 0.08, 6))
    return P


# --- environment -------------------------------------------------------------------------------------------
def build_environment(sc):
    coll = collection("Environment_Harbour")
    root = env_root()

    def put(name, md, mat, smooth_=True, shadow=True, diffuse=True):
        ob = to_obj(name, md, mat, coll, smooth=smooth_, parent=root)
        ob.visible_shadow = shadow
        ob.visible_diffuse = diffuse
        return ob

    # ------------------------------------------------------------------ sky card (8 km)
    x0, y0, x1, y1 = SKY_WINDOW
    card = MD()
    card.v.extend([sheet_pt(x0, y1, SKY_D), sheet_pt(x1, y1, SKY_D), sheet_pt(x1, y0, SKY_D), sheet_pt(x0, y0, SKY_D)])
    card.f.append((0, 1, 2, 3))
    card.uv.append([(0, 0), (1, 0), (1, 1), (0, 1)])
    card.mi = [0]
    sky = put("Sky_Backdrop", card, mat_sky(), smooth_=False, shadow=False, diffuse=False)
    sky.visible_transmission = False
    sky.visible_volume_scatter = False

    # ------------------------------------------------------------------ wet quay, quay wall, sea
    xs = sorted(set([round(x, 3) for x in lin(-60.0, 60.0, 241)] + [p[0] for p in QUAY_EDGE[1:-1]]))
    dock = grid(lambda u, v, i, j: V((u, lerp(-12.0, quay_y(u), v), 0.0)), xs, lin(0, 1, 60))
    put("Dock_Quay", dock, mat_dock(), smooth_=False)
    wall = grid(lambda u, v, i, j: V((u, quay_y(u) + 0.04 * v, lerp(0.0, WATER_Z - 1.5, v))), xs, lin(0, 1, 3),
                flip=True)
    put("Quay_Wall", wall, L.mat_simple("Quay_Wall_Concrete", (0.020, 0.022, 0.026), rough=0.4, bump_scale=3.0,
                                        bump_str=0.5), smooth_=False)
    sea = grid(lambda u, v, i, j: V((u, lerp(18.0, SKY_D - 200.0, v ** 2.2), WATER_Z)), lin(-3000, 3000, 41),
               lin(0, 1, 60))
    put("Harbour_Sea", sea, fog_wrap(mat_sea(), scale=900.0, max_fac=0.55), smooth_=False)

    # ------------------------------------------------------------------ surf and spray along the quay edge
    surf = MD()
    for (xa, xb, hmin, hmax, seed) in ((-9.0, -0.85, 0.15, 0.27, 1.3), (-0.85, 2.4, 0.02, 0.06, 2.1),
                                       (2.4, 14.0, 0.28, 0.42, 3.7)):
        def sf(u, v, i, j, xa=xa, xb=xb, hmin=hmin, hmax=hmax, seed=seed):
            x = lerp(xa, xb, u)
            crest = hmin + (hmax - hmin) * (0.5 + 0.5 * math.sin(x * 2.3 + seed) * math.sin(x * 0.7 + 2 * seed))
            if xa < -1.0:                                     # spray plumes at sheet x ~15 and ~150
                crest += sum(0.12 * math.exp(-((x - px) / 0.25) ** 2) for px in (-4.45, -3.36))
            y = quay_y(x) + 0.15 + 1.6 * v
            z = lerp(-0.4, crest, (1 - v) ** 0.4) + 0.02 * L.fbm(V((x * 3, v * 4, seed)))
            return V((x, y, z))
        surf.add(grid(sf, lin(0, 1, int((xb - xa) * 14) + 2), lin(0, 1, 6), uv_fn=lambda u, v, i, j: (u, 1 - v)))
    sp = put("Surf_Spray", surf, mat_foam(), shadow=False)
    sp.visible_diffuse = False

    # ------------------------------------------------------------------ quay lamps (bollard lights on the edge)
    lamps, warm = MD(), MD()
    for name, (x, y, z), r, power, col in (
            ("L1", (-4.39, 20.9, 0.17), 0.032, 20, (0.80, 0.87, 0.91)),
            ("L2", (-4.00, 21.0, 0.19), 0.040, 25, (0.80, 0.87, 0.91)),
            ("L3", (-3.30, 21.2, 0.15), 0.030, 15, (0.80, 0.87, 0.91)),
            ("L4", (-2.59, 21.6, 0.14), 0.024, 12, (0.80, 0.87, 0.91)),
            ("L6", (0.61, 28.6, 0.13), 0.035, 18, (0.92, 0.88, 0.82)),
            ("L7", (1.91, 36.4, 0.09), 0.035, 18, (0.92, 0.88, 0.82)),
            ("L8", (5.88, 52.6, 0.39), 0.090, 60, (0.80, 0.87, 0.91)),
            ("L9", (7.96, 54.9, 0.55), 0.160, 120, (0.92, 0.88, 0.82))):
        lamps.add(L.uv_sphere(r, 16, 10, rz=r * (1.4 if name == "L2" else 1.0)).translate((x, y, z)))
        ld = bpy.data.lights.new("Quay_Lamp_" + name, "POINT")
        ld.energy = power
        ld.color = col
        ld.shadow_soft_size = r
        lo = bpy.data.objects.new(ld.name, ld)
        coll.objects.link(lo)
        lo.location = (x, y - r * 1.5, z)
        lo.parent = root
    for (sx, sy, d, r) in ((648, 530, 34.0, 0.02), (720, 515, 40.0, 0.02)):
        warm.add(L.uv_sphere(r, 10, 6).translate(sheet_pt(sx, sy, d)))
    put("Quay_Lamp_Glow", lamps, mat_emit("Quay_Lamp_Cool_White", (0.85, 0.92, 0.96), 3.5), shadow=False)
    put("Quay_Lamp_Warm_Dots", warm, mat_emit("Quay_Lamp_Warm", (0.92, 0.80, 0.62), 4.0), shadow=False)

    # ------------------------------------------------------------------ materials of the vessels (hazed)
    sub_black = fog_wrap(mat_paint("Submarine_Anechoic_Black", (0.0018, 0.0028, 0.0045), rough=0.5, metal=0.0,
                                   streak=0.3, rust=0.0), max_fac=0.10)
    boat_dark = fog_wrap(mat_paint("Patrol_Boat_Hull", (0.010, 0.012, 0.015), rough=0.5), max_fac=0.22)
    boat_house = fog_wrap(mat_paint("Patrol_Boat_Superstructure", (0.050, 0.058, 0.066), rough=0.5, streak=0.3),
                          max_fac=0.22)
    boat_glass = fog_wrap(mat_paint("Patrol_Boat_Windows", (0.004, 0.005, 0.007), rough=0.08, metal=0.0, streak=0.0,
                                    rust=0.0), max_fac=0.22)
    ship_hull = fog_wrap(mat_paint("Warship_Hull_Haze_Grey", (0.008, 0.011, 0.014), rough=0.5), max_fac=0.14)
    ship_super = fog_wrap(mat_paint("Warship_Superstructure", (0.060, 0.075, 0.088), rough=0.5, streak=0.25),
                          max_fac=0.18)
    ship_dark = fog_wrap(mat_paint("Warship_Mast_Dark", (0.010, 0.012, 0.018), rough=0.5, streak=0.1), max_fac=0.18)
    ship_glass = fog_wrap(mat_paint("Warship_Window_Glass", (0.003, 0.004, 0.006), rough=0.1, metal=0.0, streak=0.0,
                                    rust=0.0), max_fac=0.18)
    crane_mat = fog_wrap(mat_paint("Crane_Breakwater_Dark", (0.008, 0.011, 0.016), rough=0.6, streak=0.1),
                         max_fac=0.20)
    heli_mat = fog_wrap(mat_paint("Helicopter_Navy_Grey", (0.15, 0.17, 0.20), rough=0.34, metal=0.3,
                                  streak=0.15, rust=0.0), max_fac=0.25)
    windows = mat_emit("Ship_Window_Amber", (0.53, 0.25, 0.11), 2.0)

    # ------------------------------------------------------------------ submarine (left), nearly bow-on
    # fitted to the sheet: bow-dome edge x 167, hull top y 428, sail x 82-122 to y 370, stern fins at x 25-60
    a = math.radians(12.0)
    back = V((-math.sin(a), math.cos(a), 0.0))         # from the bow toward the stern
    bow_c = V((-24.6, 216.7, 1.3))
    R = 2.9
    hull_prof = [(-R, 0.0), (-R * 0.85, R * 0.53), (-R * 0.5, R * 0.87), (0.0, R), (40.0, R), (50.0, R * 0.82),
                 (56.0, R * 0.5), (60.0, 0.3)]
    sub = MD()
    sub.add(lathe_axis(hull_prof, bow_c, back))
    s_c = bow_c + back * 12.0 + V((0, 0, R - 0.3))
    side = back.cross(V((0, 0, 1))).normalized()
    heading = math.atan2(back.y, back.x)

    def sl(u, v, i, j):
        ca, sa = math.cos(u), math.sin(u)
        ln = 3.0 * (1 - 0.10 * v)
        w = 1.05 * (1 - 0.12 * v)
        t = ln * math.copysign(abs(ca) ** 0.7, ca) * (1.0 if ca > 0 else 1.2)
        return s_c + back * t + side * (w * math.copysign(abs(sa) ** 0.6, sa)) + V((0, 0, 3.8 * v))
    sub.add(grid(sl, lin(0, TAU, 32), lin(0, 1, 6), closed_u=True, pole_v1=True))
    for dt in (-1.3, 1.0):                                       # two rounded periscope fairings on the sail
        p0 = s_c + back * dt + V((0, 0, 3.7))
        sub.add(L.lathe([(0.0, 0.0), (0.55, 0.0), (0.55, 0.85), (0.42, 1.08), (0.0, 1.15)], 20).translate(p0))
    p0 = s_c + back * -1.3 + V((0, 0, 4.85))
    sub.add(L.tube([p0, p0 + V((0, 0, 1.4))], 0.09, 8))         # thin mast
    sub.add(L.box(3.0, 0.8, 0.12).transform(Matrix.Translation(s_c + back * -1.2 + V((0, 0, 2.6))) @
                                            Matrix.Rotation(heading + math.pi / 2, 4, "Z")))   # sail planes
    st = bow_c + back * 52.0
    sub.add(L.box(0.5, 4.5, 4.0).transform(Matrix.Translation(st + V((0, 0, R * 0.6 + 1.6))) @
                                           Matrix.Rotation(heading - math.pi / 2, 4, "Z")))     # upper rudder
    sub.add(L.box(13.0, 3.2, 0.35).transform(Matrix.Translation(st) @
                                             Matrix.Rotation(heading + math.pi / 2, 4, "Z")))   # stern planes
    put("Submarine", sub, sub_black)
    glint = MD()
    glint.add(L.uv_sphere(0.18, 10, 6).translate(bow_c + V((1.9, -1.6, 1.5))))
    put("Submarine_Bow_Glint", glint, mat_emit("Sub_Bow_Light", (0.85, 0.78, 0.74), 18.0), shadow=False)

    # ------------------------------------------------------------------ patrol boat / tug (between FRONT and LEFT), bow-on
    parts = patrol_boat_parts()
    pm = Matrix.Translation((-6.5, 187.0, WATER_Z)) @ Matrix.Rotation(math.radians(195.0), 4, "Z")
    for key, mat, sm in (("hull", boat_dark, False), ("house", boat_house, False), ("glass", boat_glass, False),
                         ("rails", boat_dark, False)):
        put("Patrol_Boat_" + key.capitalize(), parts[key].transform(pm), mat, smooth_=sm)
    sc2 = MD()
    sc2.add(L.box(1.4, 6.0, 3.0).translate((-4.05, 189.0, 0.0)))          # second small craft's dark bow
    sc2.add(L.box(1.0, 3.0, 1.2).translate((-4.0, 190.5, 2.0)))
    put("Small_Craft", sc2, boat_dark, smooth_=False)
    bl = MD()
    bl.add(L.uv_sphere(0.25, 12, 8).translate((-6.15, 186.7, -0.88)))
    put("Patrol_Boat_Bow_Light", bl, mat_emit("Bow_Light_Cool", (0.90, 0.96, 0.97), 8.0), shadow=False)
    ld = bpy.data.lights.new("Patrol_Boat_Bow_Lamp", "POINT")
    ld.energy = 600.0
    ld.color = (0.85, 0.92, 0.96)
    lo = bpy.data.objects.new(ld.name, ld)
    coll.objects.link(lo)
    lo.location = (-6.15, 185.5, -0.6)
    lo.parent = root

    # ------------------------------------------------------------------ crane, dark block and breakwater (middle)
    cr = MD()
    cr.add(L.box(7.4, 0.3, 0.3).translate((9.7, 587.0, 9.2)))
    cr.add(L.tube([V((11.2, 587.0, WATER_Z)), V((11.2, 587.0, 9.2))], 0.25, 8))
    cr.add(L.box(3.1, 4.0, 4.9).translate((11.05, 590.0, 0.9)))
    cr.add(L.box(42.0, 6.0, 1.2).translate((19.3, 600.0, WATER_Z + 0.5)))
    for k in range(8):
        cr.add(L.tube([V((2.0 + k * 5.0, 597.0, WATER_Z + 1.0)), V((2.0 + k * 5.0, 597.0, WATER_Z + 2.4))], 0.15, 6))
    for (bx_, bw, bh_) in ((24.0, 6.0, 2.2), (33.0, 4.0, 1.6)):
        cr.add(L.box(bw, 4.0, bh_).translate((bx_, 603.0, WATER_Z + 1.0 + bh_ / 2)))
    put("Crane_Breakwater", cr, crane_mat, smooth_=False)

    # ------------------------------------------------------------------ warship (BACK / RIGHT), mast, far-right ship
    D = 650.0
    deck = [(712, 474), (720, 468), (760, 452), (830, 432), (900, 412), (970, 398), (1050, 392), (1144, 388),
            (1260, 386)]
    put("Warship_Hull", screen_poly(deck + [(1260, 516), (735, 516)], D, 18.0), ship_hull, smooth_=False)
    # superstructure tiers (screen boxes at slightly different depths so their side faces catch the rims)
    sup, glass, rails, dark = MD(), MD(), MD(), MD()
    tiers = ((838, 1010, 372, 404, D - 6.0, 14.0), (850, 985, 350, 372, D - 8.0, 11.0), (868, 960, 333, 350, D - 9.0, 9.0),
             (900, 948, 322, 333, D - 10.0, 7.0), (1000, 1092, 345, 393, D - 6.0, 12.0), (790, 835, 408, 432, D - 5.0, 8.0))
    for (xa, xb, ya, yb, dd, dep) in tiers:
        sup.add(screen_box(xa, xb, ya, yb, dd, dep))
        for xr in range(int(xa) + 1, int(xb), 3):                      # railing posts + top rail on each tier
            rails.add(screen_post(xr, ya - 2.4, ya, dd - 0.2, 0.35))
        rails.add(screen_box(xa, xb, ya - 2.6, ya - 2.2, dd - 0.2, 0.2))
        h_ = yb - ya
        rows = [ya + h_ * f for f in ((0.35,) if h_ < 20 else (0.3, 0.65))]
        for yw in rows:                                                  # window rows
            for xw in range(int(xa) + 3, int(xb) - 3, 5):
                glass.add(screen_box(xw, xw + 2.2, yw, yw + 2.4, dd - 0.15, 0.1))
    dark.add(screen_box(960, 985, 314, 350, D - 12.0, 6.0))             # funnel
    dark.add(screen_box(958, 987, 312, 316, D - 12.2, 6.4))
    for (xl_, yl_) in ((858, 396), (938, 396), (1012, 386)):            # lifeboats under davits
        sup.add(screen_box(xl_, xl_ + 20, yl_, yl_ + 6, D - 6.6, 2.5))
    put("Warship_Superstructure", sup, ship_super, smooth_=False)
    put("Warship_Windows_Dark", glass, ship_glass, smooth_=False)
    put("Warship_Railings", rails, ship_dark, smooth_=False)
    put("Warship_Funnel", dark, ship_dark, smooth_=False)
    band = MD()                                                          # lighter sheer band under the deck edge
    for (xa, ya), (xb, yb) in zip(deck, deck[1:]):
        band.add(screen_poly([(xa, ya + 1.0), (xb, yb + 1.0), (xb, yb + 4.0), (xa, ya + 4.0)], D - 0.3, 0.2))
    put("Warship_Sheer_Band", band, ship_super, smooth_=False)
    dk = MD()
    dk.add(screen_post(899, 140, 330, D - 2.0, 12.5))
    dk.add(screen_box(884, 914, 148, 154, D - 2.0, 3.0))           # platform
    dk.add(screen_box(890, 908, 183, 187, D - 2.0, 2.0))           # bracket
    dk.add(screen_box(872, 926, 203, 205, D - 2.0, 1.0))           # yardarm
    dk.add(screen_box(886, 912, 238, 243, D - 2.0, 3.0))           # lower platform
    dk.add(screen_box(890, 908, 138, 145, D - 2.5, 2.0))           # radar
    for (xa_, ya_, yb_) in ((893, 120, 140), (905, 126, 140), (930, 296, 322), (940, 300, 322)):
        dk.add(screen_post(xa_, ya_, yb_, D - 2.0, 1.2))               # antennas
    for xk in (748, 761):
        dk.add(screen_post(xk, 407, 466, D - 30.0, 2.5))
    dk.add(screen_box(746, 763, 427, 430, D - 30.0, 1.0))
    for xr in range(724, 1144, 4):                                  # deck railing posts
        yr = [y for (x, y) in deck if x <= xr][-1]
        dk.add(screen_post(xr, yr - 3.5, yr, D - 6.0, 0.6))
    put("Warship_Mast_Kingposts", dk, ship_dark, smooth_=False)
    far = MD()
    far.add(screen_box(1085, 1300, 400, 512, 620.0, 16.0))
    far.add(screen_box(1085, 1300, 330, 400, 624.0, 10.0))
    far.add(screen_post(1107, 318, 332, 622.0, 3.0))
    put("Far_Ship", far, ship_hull, smooth_=False)
    far_lit = MD()
    far_lit.add(screen_box(1088, 1300, 334, 398, 622.0, 6.0))
    put("Far_Ship_Superstructure", far_lit, ship_super, smooth_=False)
    win = MD()
    for (wx, wy, d_) in ((867, 336, D - 9.0), (872, 374, D - 9.0), (880, 376, D - 9.0), (1104, 368, 619.0),
                         (930, 366, D - 9.0), (960, 366, D - 9.0), (985, 388, D - 9.0)):
        win.add(L.uv_sphere(0.35, 8, 5).translate(sheet_pt(wx, wy, d_)))
    put("Ship_Windows", win, windows, shadow=False)

    # ------------------------------------------------------------------ helicopter hovering top right (nose-up flare)
    Dh = 185.0
    hm = Matrix.Translation(sheet_pt(915, 92, Dh)) @ Matrix.Rotation(math.radians(-84), 4, "Z") @ \
        Matrix.Rotation(math.radians(-16), 4, "Y") @ Matrix.Rotation(math.radians(12), 4, "X") @ \
        Matrix.Diagonal((1.0, 1.18, 1.18, 1.0))
    heli = MD()

    def fus(u, v, i, j):
        t = v
        x = lerp(-11.0, 5.2, t)
        r = interp_smooth([(0.0, 0.25), (0.40, 0.42), (0.55, 1.15), (0.70, 1.35), (0.86, 1.25), (0.96, 0.8),
                           (1.0, 0.1)], t)[0]
        zc = interp_smooth([(0.0, 0.6), (0.5, 0.5), (0.7, 0.0), (1.0, -0.2)], t)[0]
        return V((x, r * 0.95 * math.sin(u), zc + r * 1.25 * math.cos(u)))
    heli.add(grid(fus, lin(0, TAU, 24), lin(0, 1, 28), closed_u=True))
    heli.add(L.box(1.6, 0.3, 2.6).translate((-10.6, 0.0, 1.6)))                  # fin
    heli.add(L.box(2.8, 1.4, 0.9).translate((0.2, 0.0, 1.85)))                   # engine housing
    heli.add(L.tube([V((0.3, 0.0, 2.2)), V((0.3, 0.0, 2.9))], 0.22, 8))          # rotor mast
    for s in (1, -1):
        heli.add(L.tube([V((1.5, s * 0.9, -1.3)), V((1.6, s * 1.2, -2.1))], 0.08, 6))
        heli.add(L.uv_sphere(0.32, 10, 6).translate((1.6, s * 1.2, -2.2)))
        heli.add(L.box(2.2, 0.5, 0.6).translate((-0.8, s * 1.3, -0.7)))
    blades = MD()
    for k in range(4):
        a_ = TAU * k / 4 + 0.5
        blades.add(L.box(7.8, 0.30, 0.06).transform(Matrix.Translation((0.3 + 3.9 * math.cos(a_), 3.9 * math.sin(a_),
                                                                         2.95)) @ Matrix.Rotation(a_, 4, "Z")))
    disc = grid(lambda u, v, i, j: (0.3 + v * 8.0 * math.cos(u), v * 8.0 * math.sin(u), 3.0 + 0.2 * v),
                lin(0, TAU, 48), lin(0.05, 1, 4), closed_u=True)
    put("Helicopter", heli.transform(hm), heli_mat)
    put("Helicopter_Blades", blades.transform(hm.copy()), heli_mat, smooth_=False)
    put("Helicopter_Rotor_Blur", disc.transform(hm.copy()), mat_rotor_disc(), shadow=False, diffuse=False)
    nl = MD()
    nl.add(L.uv_sphere(0.16, 10, 6).translate(hm @ V((5.15, 0.0, -0.3))))
    put("Helicopter_Nose_Light", nl, mat_emit("Heli_Nose_Light", (0.85, 0.72, 0.69), 12.0), shadow=False)

    # ------------------------------------------------------------------ fjord mountains (right), 5 km
    # a real heightfield (slopes, buttresses and gullies that take the sun rig) whose crest projects exactly onto the
    # sheet's ridge line; the left flank runs down to the water behind the BACK figure
    Dm = 5000.0
    km = Dm / CAM_D
    ridge = [(760, 505), (790, 470), (812, 380), (830, 300), (846, 236), (852, 226), (860, 218), (870, 213),
             (880, 205), (885, 202), (910, 198), (920, 193), (928, 190), (960, 192), (1000, 188), (1040, 190),
             (1070, 186), (1100, 184), (1104, 182), (1112, 185), (1120, 188), (1128, 184), (1136, 179), (1144, 178),
             (1200, 172), (1300, 176), (1420, 168), (1600, 180)]

    def ry(x):
        if x <= ridge[0][0]:
            return 510.0
        for (xa, ya), (xb, yb) in zip(ridge, ridge[1:]):
            if x <= xb:
                return lerp(ya, yb, (x - xa) / (xb - xa))
        return ridge[-1][1]

    def crest(X):
        x = MID_X + PX_M * X / km
        jag = 55.0 * abs(L.fbm(V((X / 38.0, 0.5, 3.0)), 4)) - 20.0 * L.fbm(V((X / 11.0, 1.5, 5.0)), 2)
        return max(WATER_Z, EYE + ((SOLE_Y - ry(x)) / PX_M - EYE) * km - jag)

    yc = Dm - CAM_D

    def terrain(u, v, i, j):
        X, Y = u, v
        H = crest(X) - WATER_Z
        dy = Y - yc
        prof = math.exp(-(dy / 950.0) ** 2) if dy < 0 else math.exp(-(dy / 700.0) ** 2)
        gul = abs(L.fbm(V((X / 55.0, Y / 260.0, 2.0)), 5))                 # gullies running down the slopes
        bump = L.fbm(V((X / 180.0, Y / 180.0, 7.0)), 4)
        z = H * prof * (1.0 - 0.45 * gul * (1 - prof) ** 0.5) + 0.10 * H * bump * (1 - prof)
        return V((X, Y, WATER_Z + max(0.0, z)))
    mts = grid(terrain, lin(150.0, 1350.0, 420), lin(yc - 2600.0, yc + 1500.0, 110))
    put("Mountains", mts, fog_wrap(mat_rock(), fog_col=(0.105, 0.130, 0.175), scale=2400.0, max_fac=0.55, top=3000.0,
                                   top_keep=0.85))
