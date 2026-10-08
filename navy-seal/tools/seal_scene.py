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
FIGURES = {"Front": (-0.852, 0.0), "Left": (-0.155, -90.0), "Back": (0.546, 180.0), "Right": (1.389, 90.0)}
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
    """Overcast dusk dome: slate zenith, blue-grey horizon, the peach glow toward the setting sun (+X +Y), dark
    below the horizon."""
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
    bg.inputs["Strength"].default_value = 1.0
    o = nb.n("ShaderNodeOutputWorld", (400, 0))
    nb.link(bg.outputs[0], o.inputs["Surface"])


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
    sun(coll, "Key_Front_Right", (0.53, -0.63, 0.57), 1.4, (0.888, 0.761, 0.658), 12)
    sun(coll, "Fill_Moon_Front_Left", (-0.64, -0.64, 0.42), 0.5, (0.397, 0.503, 0.716), 30)
    sun(coll, "Rim_Sunset_Back_Right", (0.75, 0.63, 0.21), 2.2, (0.930, 0.571, 0.371), 6)
    sun(coll, "Rim_Sky_Back_Left", (-0.61, 0.61, 0.50), 1.4, (0.275, 0.397, 0.672), 10)


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
    far = nb.math("MULTIPLY", nb.math("MAXIMUM", nb.math("SUBTRACT", sx.outputs[1], 2.0), 0.0), 0.02)
    puddle = nb.ramp(nb.math("ADD", wn.outputs["Fac"], far), [(0.40, 0.0), (0.47, 1.0)])
    dry = nb.ramp(nb.noise(obj, 0.5, 4, 0.6).outputs["Fac"], [(0.66, 0.0), (0.72, 1.0)])
    rough = nb.mixf(puddle, nb.mixf(dry, 0.36, 0.60), 0.09)
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
    band = nb.ramp(wv.outputs["Fac"], [(0.35, 0.0), (0.65, 1.0)])
    rough = nb.mixf(nb.math("MULTIPLY", puddle, band), rough, 0.26)      # broken, dashed reflections
    h = nb.math("ADD", wv.outputs["Fac"], nb.math("MULTIPLY", grit.outputs["Fac"], nb.mixf(puddle, 0.6, 0.05)))
    h = nb.math("SUBTRACT", h, nb.math("MULTIPLY", joint, 0.8))
    h = nb.math("ADD", h, nb.math("MULTIPLY", drop, 0.3))
    p = nb.principled(Base_Color=col, Roughness=rough, Specular_IOR_Level=0.5, IOR=1.33,
                      Normal=nb.bump(h, 0.2, 0.01))
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
    mx.inputs[0].default_value = 0.25
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
    sub_black = fog_wrap(mat_paint("Submarine_Anechoic_Black", (0.002, 0.004, 0.006), rough=0.30, metal=0.1,
                                   streak=0.2, rust=0.0), max_fac=0.10)
    boat_dark = fog_wrap(mat_paint("Patrol_Boat_Hull", (0.010, 0.012, 0.015), rough=0.5), max_fac=0.22)
    boat_house = fog_wrap(mat_paint("Patrol_Boat_Wheelhouse", (0.030, 0.035, 0.040), rough=0.5), max_fac=0.22)
    ship_hull = fog_wrap(mat_paint("Warship_Hull_Haze_Grey", (0.008, 0.011, 0.014), rough=0.5), max_fac=0.14)
    ship_super = fog_wrap(mat_paint("Warship_Superstructure", (0.060, 0.075, 0.088), rough=0.5, streak=0.25),
                          max_fac=0.18)
    ship_dark = fog_wrap(mat_paint("Warship_Mast_Dark", (0.010, 0.012, 0.018), rough=0.5, streak=0.1), max_fac=0.18)
    crane_mat = fog_wrap(mat_paint("Crane_Breakwater_Dark", (0.008, 0.011, 0.016), rough=0.6, streak=0.1),
                         max_fac=0.20)
    heli_mat = fog_wrap(mat_paint("Helicopter_Navy_Grey", (0.11, 0.13, 0.16), rough=0.36, metal=0.25,
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
    for (dt, h, rr) in ((-1.4, 1.2, 0.16), (0.2, 1.8, 0.14), (1.6, 0.9, 0.2)):     # periscopes and masts
        p0 = s_c + back * dt * 0.7 + V((0, 0, 3.75))
        sub.add(L.tube([p0, p0 + V((0, 0, h))], rr, 8))
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

    # ------------------------------------------------------------------ patrol boat (between FRONT and LEFT), bow-on
    pb = MD()
    pbc = V((-6.5, 187.0, 0.0))
    yaw = math.radians(15.0)
    fwd = V((math.sin(yaw), -math.cos(yaw), 0.0))      # bow direction: toward the camera, slightly right
    sd = fwd.cross(V((0, 0, 1))).normalized()
    for sgn in (1, -1):
        pb.add(grid(lambda u, v, i, j, sgn=sgn: pbc + fwd * (22.0 * (v - 0.5)) +
                    sd * (sgn * 2.25 * (1 - max(0.0, (v - 0.62) / 0.38) ** 1.6) * math.cos(u) ** 0.7) +
                    V((0, 0, lerp(-1.6, 1.82 + 0.6 * max(0.0, v - 0.7), math.sin(u)))),
                    lin(0.0, math.pi / 2, 6), lin(0, 1, 16), flip=(sgn < 0)))
    whc = pbc + fwd * 1.0
    for (w_, l_, z0, z1) in ((4.0, 6.0, 1.82, 3.0), (3.6, 4.8, 3.0, 4.62)):
        pb.add(L.box(w_, l_, z1 - z0).transform(Matrix.Translation(whc + V((0, 0, (z0 + z1) / 2))) @
                                                Matrix.Rotation(yaw, 4, "Z")))
    pb.add(L.tube([whc + V((0, 0, 4.62)), whc + V((0, 0, 6.72))], 0.12, 8))
    pb.add(L.box(1.6, 0.1, 0.1).transform(Matrix.Translation(whc + V((0, 0, 5.23))) @ Matrix.Rotation(yaw, 4, "Z")))
    for xpost in (-7.88, -6.06):
        pb.add(L.tube([V((xpost, 186.0, 1.8)), V((xpost, 186.0, 5.1))], 0.08, 6))
    pb.add(L.box(1.4, 6.0, 3.0).translate((-4.05, 189.0, 0.0)))          # second small craft's dark bow
    put("Patrol_Boat", pb, boat_dark, smooth_=False)
    pw = MD()
    for k in range(5):
        pw.add(L.box(0.5, 0.05, 0.5).transform(Matrix.Translation(whc + fwd * 2.42 + sd * (-1.5 + 0.75 * k) +
                                                                  V((0, 0, 3.35))) @ Matrix.Rotation(yaw, 4, "Z")))
    put("Patrol_Boat_Windows", pw, boat_house, smooth_=False)
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
    sup = MD()
    for (xa, xb, ya, yb) in ((830, 1050, 375, 402), (845, 1010, 352, 376), (870, 962, 330, 353), (905, 945, 318, 331),
                             (1000, 1092, 345, 393), (790, 830, 410, 436)):
        sup.add(screen_box(xa, xb, ya, yb, D - 4.0, 10.0))
    put("Warship_Superstructure", sup, ship_super, smooth_=False)
    dk = MD()
    dk.add(screen_post(899, 140, 330, D - 2.0, 12.5))
    dk.add(screen_box(884, 914, 148, 154, D - 2.0, 3.0))           # platform
    dk.add(screen_box(890, 908, 183, 187, D - 2.0, 2.0))           # bracket
    for xk in (748, 761):
        dk.add(screen_post(xk, 407, 466, D - 30.0, 2.5))
    dk.add(screen_box(746, 763, 427, 430, D - 30.0, 1.0))
    for xr in range(724, 1144, 7):                                  # deck railing posts
        yr = [y for (x, y) in deck if x <= xr][-1]
        dk.add(screen_post(xr, yr - 5, yr, D - 6.0, 0.8))
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
        win.add(L.uv_sphere(0.6, 8, 5).translate(sheet_pt(wx, wy, d_)))
    put("Ship_Windows", win, windows, shadow=False)

    # ------------------------------------------------------------------ helicopter hovering top right (nose-up flare)
    Dh = 300.0
    hm = Matrix.Translation(sheet_pt(925, 88, Dh)) @ Matrix.Rotation(math.radians(-62), 4, "Z") @ \
        Matrix.Rotation(math.radians(-18), 4, "Y") @ Matrix.Rotation(math.radians(12), 4, "X")
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
        blades.add(L.box(7.8, 0.45, 0.08).transform(Matrix.Translation((0.3 + 3.9 * math.cos(a_), 3.9 * math.sin(a_),
                                                                         2.95)) @ Matrix.Rotation(a_, 4, "Z")))
    disc = grid(lambda u, v, i, j: (0.3 + v * 8.0 * math.cos(u), v * 8.0 * math.sin(u), 3.0 + 0.2 * v),
                lin(0, TAU, 48), lin(0.05, 1, 4), closed_u=True)
    put("Helicopter", heli.transform(hm), heli_mat)
    put("Helicopter_Blades", blades.transform(hm.copy()), heli_mat, smooth_=False)
    put("Helicopter_Rotor_Blur", disc.transform(hm.copy()), mat_rotor_disc(), shadow=False, diffuse=False)
    nl = MD()
    nl.add(L.uv_sphere(0.35, 10, 6).translate(hm @ V((5.1, 0.0, -0.3))))
    put("Helicopter_Nose_Light", nl, mat_emit("Heli_Nose_Light", (0.85, 0.72, 0.69), 30.0), shadow=False)

    # ------------------------------------------------------------------ fjord mountains (right), 5 km
    Dm = 5000.0
    ridge = [(780, 470), (812, 380), (830, 300), (846, 236), (852, 226), (860, 218), (870, 213), (880, 205),
             (885, 202), (910, 198), (920, 193), (928, 190), (960, 192), (1000, 188), (1040, 190), (1070, 186),
             (1100, 184), (1104, 182), (1112, 185), (1120, 188), (1128, 184), (1136, 179), (1144, 178),
             (1200, 172), (1300, 176), (1420, 168)]

    def ry(x):
        for (xa, ya), (xb, yb) in zip(ridge, ridge[1:]):
            if x <= xb:
                return lerp(ya, yb, (x - xa) / (xb - xa))
        return ridge[-1][1]

    def mtn(u, v, i, j):
        y = lerp(ry(u) + 1.5 * L.fbm(V((u * 0.15, 0.3, 1.0))), 508.0, v)
        d = Dm + 220.0 * (1 - v) + 120.0 * L.fbm(V((u * 0.05, v * 2.0, 4.0)))
        return sheet_pt(u, y, d)
    put("Mountains", grid(mtn, lin(780, 1420, 220), lin(0, 1, 18)),
        fog_wrap(mat_rock(), scale=2400.0, max_fac=0.72, top=3000.0, top_keep=0.85))
