"""Shared materials for the Navy SEAL (every module may add its own on top of these)."""
import seal_lib as L
from seal_lib import NB, new_mat, _ao, _triplanar, _bevel, _hard_edges

M = {}


def tri_rgb(nb, name, obj, scale, extension="REPEAT"):
    """Colour-preserving triplanar lookup (`scale` tiles per metre).  Returns a vector socket (R, G, B)."""
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
    ws = [nb.math("POWER", nb.math("ABSOLUTE", n_), 4.0) for n_ in (nx, ny, nz)]
    tot = nb.math("ADD", nb.math("ADD", ws[0], ws[1]), nb.math("ADD", ws[2], 1e-4))
    acc = None
    for im_, w_ in zip((ix, iy, iz), ws):
        sc = nb.n("ShaderNodeVectorMath", (-500, 600))
        sc.operation = "SCALE"
        nb.link(im_, sc.inputs[0])
        nb.link(nb.math("DIVIDE", w_, tot), sc.inputs["Scale"])
        if acc is None:
            acc = sc.outputs[0]
        else:
            ad = nb.n("ShaderNodeVectorMath", (-400, 600))
            ad.operation = "ADD"
            nb.link(acc, ad.inputs[0])
            nb.link(sc.outputs[0], ad.inputs[1])
            acc = ad.outputs[0]
    return acc


def _wet(nb, obj, scale=1.6, lo=0.45, hi=0.62):
    """Patchy wetness mask (1 = wet): wet fabric/plastic darkens and turns glossy."""
    w = nb.noise(obj, scale, 5, 0.6)
    return nb.ramp(w.outputs["Fac"], [(lo, 0.0), (hi, 1.0)])


def mat_suit(name="Suit_Drysuit_Black", base=(0.0085, 0.0088, 0.0098), line=(0.095, 0.092, 0.096),
             blot=(0.020, 0.020, 0.023), tiles=1.25):
    """Black drysuit / combat suit: printed swirl linework camo, nylon weave, wet sheen in patches."""
    m = new_mat(name)
    nb = NB(m)
    tc = nb.texcoord()
    obj = tc.outputs["Object"]
    camo = tri_rgb(nb, "suit_camo.png", obj, tiles)
    sep = nb.n("ShaderNodeSeparateXYZ", (-700, 600))
    nb.link(camo, sep.inputs[0])
    lines, blots = sep.outputs[0], sep.outputs[1]
    col = nb.mix(nb.math("MULTIPLY", blots, 0.9), base, blot)
    col = nb.mix(nb.math("MULTIPLY", lines, 0.85), col, line)
    wet = _wet(nb, obj)
    col = nb.mix(nb.math("MULTIPLY", wet, 0.35), col, (0.006, 0.006, 0.007))
    ao = _ao(nb, 0.04)
    col = nb.mix(nb.math("SUBTRACT", 1.0, ao), col, (0.002, 0.002, 0.0025))
    rough = nb.mixf(wet, 0.36, 0.16)
    rough = nb.mixf(nb.math("MULTIPLY", lines, 0.8), rough, 0.30)  # the raised piping is glossier
    # weave + fine crinkle of coated nylon
    wv = nb.n("ShaderNodeTexWave", (-900, -600), wave_type="BANDS", bands_direction="DIAGONAL")
    wv.inputs["Scale"].default_value = 260.0
    wv.inputs["Distortion"].default_value = 1.2
    nb.link(obj, wv.inputs["Vector"])
    cr = nb.noise(obj, 90.0, 4, 0.6)
    h = nb.math("ADD", nb.math("MULTIPLY", wv.outputs["Fac"], 0.25), nb.math("MULTIPLY", cr.outputs["Fac"], 0.6))
    h = nb.math("ADD", h, nb.math("MULTIPLY", lines, 0.15))  # printed lines sit slightly proud
    p = nb.principled(Base_Color=col, Roughness=rough, Specular_IOR_Level=0.5, Sheen_Weight=0.2,
                      Sheen_Roughness=0.4, Sheen_Tint=(0.45, 0.5, 0.6), Coat_Weight=nb.math("MULTIPLY", wet, 0.35),
                      Coat_Roughness=0.12, Normal=nb.bump(h, 0.25, 0.0008))
    nb.output(p.outputs[0])
    m.diffuse_color = (*base, 1)
    return m


def mat_nylon(name="Nylon_Cordura_Black", base=(0.016, 0.016, 0.018), light=(0.040, 0.041, 0.045), tiles=14.0):
    """500D Cordura / webbing: matte black with weave, scuffed lighter fibres, damp patches."""
    m = new_mat(name)
    nb = NB(m)
    tc = nb.texcoord()
    obj = tc.outputs["Object"]
    weave = _triplanar(nb, "webbing.png", obj, tiles)
    n1 = nb.noise(obj, 9.0, 6, 0.6)
    col = nb.mix(nb.ramp(n1.outputs["Fac"], [(0.45, 0.0), (0.8, 1.0)]), base, light)
    bv = _bevel(nb, 0.002)
    en = nb.noise(obj, 40.0, 4, 0.6)
    edge = nb.math("MULTIPLY", _hard_edges(nb, bv, 0.02, 0.12), nb.ramp(en.outputs["Fac"], [(0.4, 0.0), (0.6, 1.0)]))
    col = nb.mix(nb.math("MULTIPLY", edge, 0.6), col, (0.075, 0.076, 0.08))  # scuffed edges
    wet = _wet(nb, obj, 2.2)
    col = nb.mix(nb.math("MULTIPLY", wet, 0.4), col, (0.008, 0.008, 0.009))
    ao = _ao(nb, 0.02)
    col = nb.mix(nb.math("SUBTRACT", 1.0, ao), col, (0.003, 0.003, 0.003))
    p = nb.principled(Base_Color=col, Roughness=nb.mixf(wet, 0.72, 0.38), Specular_IOR_Level=0.4,
                      Sheen_Weight=0.4, Sheen_Roughness=0.5, Normal=nb.bump(weave, 0.35, 0.0006, normal=bv))
    nb.output(p.outputs[0])
    m.diffuse_color = (*base, 1)
    return m


def mat_nylon_camo(name="Nylon_Camo_Black", base=(0.020, 0.021, 0.022), blot1=(0.040, 0.042, 0.037),
                   blot2=(0.062, 0.062, 0.055), line=(0.11, 0.10, 0.085), tiles=3.0, line_amt=0.85,
                   edge_col=(0.16, 0.152, 0.135)):
    """Multicam-Black style printed Cordura for the plate carrier and pouches: charcoal ground, olive-grey
    blotches, pale grey-tan swirl linework and fleck print, weave, scuffed light edges and glossy damp patches."""
    m = new_mat(name)
    nb = NB(m)
    tc = nb.texcoord()
    obj = tc.outputs["Object"]
    camo = tri_rgb(nb, "suit_camo.png", obj, tiles)
    sep = nb.n("ShaderNodeSeparateXYZ", (-700, 600))
    nb.link(camo, sep.inputs[0])
    col = nb.mix(nb.math("MULTIPLY", sep.outputs[1], 0.9), base, blot1)
    n2 = nb.noise(obj, 22.0, 4, 0.6)
    col = nb.mix(nb.math("MULTIPLY", nb.ramp(n2.outputs["Fac"], [(0.55, 0.0), (0.72, 1.0)]), 0.8), col, blot2)
    # second, finer print layer (rotated tiling) so neighbouring pouches don't repeat the same swirl
    camo2 = tri_rgb(nb, "suit_camo.png", nb.mapping(obj, (1.0, 1.0, 1.0), loc=(0.37, 0.11, 0.23), rot=(0.0, 0.0, 0.9)), tiles * 2.3)
    sep2 = nb.n("ShaderNodeSeparateXYZ", (-700, 500))
    nb.link(camo2, sep2.inputs[0])
    ln = nb.math("MAXIMUM", sep.outputs[0], nb.math("MULTIPLY", sep2.outputs[0], 0.7))
    col = nb.mix(nb.math("MULTIPLY", ln, line_amt), col, line)
    fl = nb.noise(obj, 160.0, 3, 0.5)
    fleck = nb.ramp(fl.outputs["Fac"], [(0.60, 0.0), (0.68, 1.0)])
    col = nb.mix(nb.math("MULTIPLY", fleck, 0.45), col, tuple(c * 0.8 for c in line))
    weave = tri_rgb(nb, "webbing.png", obj, 16.0)
    wsep = nb.n("ShaderNodeSeparateXYZ", (-700, 400))
    nb.link(weave, wsep.inputs[0])
    bv = _bevel(nb, 0.003)
    en = nb.noise(obj, 40.0, 4, 0.6)
    edge = nb.math("MULTIPLY", _hard_edges(nb, bv, 0.02, 0.12), nb.ramp(en.outputs["Fac"], [(0.4, 0.0), (0.6, 1.0)]))
    col = nb.mix(nb.math("MULTIPLY", edge, 0.8), col, edge_col)
    wet = _wet(nb, obj, 2.6)
    col = nb.mix(nb.math("MULTIPLY", wet, 0.35), col, (0.010, 0.010, 0.011))
    ao = _ao(nb, 0.025)
    col = nb.mix(nb.math("SUBTRACT", 1.0, ao), col, (0.003, 0.003, 0.003))
    h = nb.math("ADD", wsep.outputs[0], nb.math("MULTIPLY", ln, 0.5))
    p = nb.principled(Base_Color=col, Roughness=nb.mixf(wet, 0.62, 0.30), Specular_IOR_Level=0.5,
                      Sheen_Weight=0.35, Coat_Weight=nb.math("MULTIPLY", wet, 0.4), Coat_Roughness=0.15,
                      Normal=nb.bump(h, 0.35, 0.0006, normal=bv))
    nb.output(p.outputs[0])
    m.diffuse_color = (*base, 1)
    return m


def mat_polymer(name="Polymer_Black", base=(0.020, 0.020, 0.022), rough=0.42, coat=0.0, grain=600.0):
    """Moulded polymer / composite: stippled grain, worn glossier edges, AO grime."""
    m = new_mat(name)
    nb = NB(m)
    tc = nb.texcoord()
    obj = tc.outputs["Object"]
    st = nb.noise(obj, grain, 3, 0.5)
    bv = _bevel(nb, 0.0015)
    edge = _hard_edges(nb, bv, 0.03, 0.15)
    col = nb.mix(nb.math("MULTIPLY", edge, 0.5), base, (0.06, 0.06, 0.065))
    ao = _ao(nb, 0.02)
    col = nb.mix(nb.math("SUBTRACT", 1.0, ao), col, (0.004, 0.004, 0.004))
    wet = _wet(nb, obj, 3.0, 0.5, 0.66)
    p = nb.principled(Base_Color=col, Roughness=nb.mixf(edge, nb.mixf(wet, rough, rough * 0.55), rough * 0.6),
                      Specular_IOR_Level=0.5, Coat_Weight=coat, Coat_Roughness=0.15,
                      Normal=nb.bump(st.outputs["Fac"], 0.12, 0.0004, normal=bv))
    nb.output(p.outputs[0])
    m.diffuse_color = (*base, 1)
    return m


def mat_rubber(name="Rubber_Gloss_Black", base=(0.010, 0.010, 0.011), rough=0.22):
    """Glossy wet rubber / TPU (knee caps, mask skirt, hoses)."""
    m = new_mat(name)
    nb = NB(m)
    tc = nb.texcoord()
    obj = tc.outputs["Object"]
    n = nb.noise(obj, 220.0, 3, 0.5)
    sm = nb.noise(obj, 6.0, 4, 0.6)
    ao = _ao(nb, 0.02)
    col = nb.mix(nb.math("SUBTRACT", 1.0, ao), base, (0.002, 0.002, 0.002))
    p = nb.principled(Base_Color=col, Roughness=nb.mixf(nb.ramp(sm.outputs["Fac"], [(0.4, 0.0), (0.7, 1.0)]),
                                                        rough, rough * 1.8),
                      Specular_IOR_Level=0.55, Coat_Weight=0.5, Coat_Roughness=0.08,
                      Normal=nb.bump(n.outputs["Fac"], 0.06, 0.0003))
    nb.output(p.outputs[0])
    m.diffuse_color = (*base, 1)
    return m


def mat_metal(name="Metal_Gunmetal", base=(0.055, 0.056, 0.060), rough=0.38, edge_col=(0.32, 0.32, 0.33)):
    """Cerakoted / parkerised steel and aluminium: dark, satin, bright worn edges."""
    m = new_mat(name)
    nb = NB(m)
    tc = nb.texcoord()
    obj = tc.outputs["Object"]
    bv = _bevel(nb, 0.0012)
    en = nb.noise(obj, 60.0, 4, 0.6)
    edge = nb.math("MULTIPLY", _hard_edges(nb, bv, 0.03, 0.15), nb.ramp(en.outputs["Fac"], [(0.4, 0.0), (0.6, 1.0)]))
    col = nb.mix(edge, base, edge_col)
    n = nb.noise(obj, 300.0, 3, 0.5)
    p = nb.principled(Base_Color=col, Metallic=nb.mixf(edge, 0.55, 1.0), Roughness=nb.mixf(edge, rough, 0.22),
                      Normal=nb.bump(n.outputs["Fac"], 0.05, 0.0003, normal=bv))
    nb.output(p.outputs[0])
    m.diffuse_color = (*base, 1)
    return m


def mat_visor(name="Visor_Blue", tint=(0.006, 0.040, 0.170), glow=0.35):
    """Blue mirrored / tinted dive-mask lens: strong glossy reflection, faint internal blue glow."""
    m = new_mat(name)
    nb = NB(m)
    tc = nb.texcoord()
    lw = nb.n("ShaderNodeLayerWeight", (-600, -200))
    lw.inputs["Blend"].default_value = 0.35
    col = nb.mix(lw.outputs["Facing"], (0.020, 0.090, 0.42), (0.10, 0.30, 0.75))
    gz = nb.n("ShaderNodeSeparateXYZ", (-600, -500))
    nb.link(tc.outputs["Generated"], gz.inputs[0])
    shade = nb.ramp(gz.outputs[2], [(0.0, 1.0), (0.55, 0.85), (1.0, 0.25)])      # dark band under the helmet brim
    col = nb.mix(nb.math("SUBTRACT", 1.0, shade), col, (0.004, 0.012, 0.035))
    # mirrored cobalt lens: fully metallic so every reflection (sky, sun) comes back tinted deep blue
    p = nb.principled(Base_Color=col, Metallic=1.0, Roughness=0.05, Coat_Weight=0.25, Coat_Roughness=0.03,
                      Emission_Color=(0.01, 0.06, 0.25), Emission_Strength=nb.math("MULTIPLY", shade, glow))
    nb.output(p.outputs[0])
    m.diffuse_color = (*tint, 1)
    return m


def mat_screen(name="Screen_Blue", col=(0.25, 0.65, 1.0), strength=3.0):
    m = new_mat(name)
    nb = NB(m)
    p = nb.principled(Base_Color=(0.01, 0.02, 0.04), Roughness=0.05, Coat_Weight=1.0, Emission_Color=col,
                      Emission_Strength=strength)
    nb.output(p.outputs[0])
    m.diffuse_color = (*col, 1)
    return m


def mat_screen_img(name, img, strength=0.4):
    """Glass-covered display: glossy dark glass over an emissive UI image."""
    L.image(img, "sRGB")
    m = new_mat(name)
    nb = NB(m)
    tc = nb.texcoord()
    t = nb.img(img, tc.outputs["UV"], "CLIP").outputs["Color"]
    p = nb.principled(Base_Color=(0.005, 0.014, 0.030), Roughness=0.04, Coat_Weight=1.0, Coat_Roughness=0.03,
                      Emission_Color=t, Emission_Strength=strength)
    nb.output(p.outputs[0])
    return m


def mat_patch(name="Patch_Flag_Subdued", img="flag_subdued.png"):
    """Embroidered subdued flag patch (colour image) on a hook-and-loop backing: thread ridges, fuzzy sheen."""
    L.image(img, "sRGB")
    m = new_mat(name)
    nb = NB(m)
    tc = nb.texcoord()
    t = nb.img(img, tc.outputs["UV"], "CLIP").outputs["Color"]
    col = nb.mix(0.0, t, t)
    thr = nb.n("ShaderNodeTexWave", (-900, -400), wave_type="BANDS", bands_direction="X")
    thr.inputs["Scale"].default_value = 160.0
    nb.link(tc.outputs["UV"], thr.inputs["Vector"])
    n = nb.noise(tc.outputs["Object"], 500.0, 2, 0.5)
    p = nb.principled(Base_Color=col, Roughness=0.78, Sheen_Weight=0.45, Sheen_Roughness=0.4,
                      Normal=nb.bump(nb.math("ADD", nb.math("MULTIPLY", thr.outputs["Fac"], 0.6), n.outputs["Fac"]),
                                     0.3, 0.0005))
    nb.output(p.outputs[0])
    return m


def build_materials():
    M.clear()
    M["suit"] = mat_suit()
    M["suit_legs"] = mat_suit("Suit_Trousers_Black", base=(0.0068, 0.0070, 0.0078), line=(0.052, 0.050, 0.054),
                              blot=(0.013, 0.013, 0.015))
    M["suit_panel"] = mat_suit("Suit_Panel_Black", base=(0.009, 0.009, 0.010), line=(0.035, 0.036, 0.04), tiles=1.6)
    M["nylon"] = mat_nylon()
    M["nylon_dark"] = mat_nylon("Nylon_Webbing_Black", base=(0.010, 0.010, 0.011), light=(0.028, 0.028, 0.031),
                                tiles=20.0)
    M["polymer"] = mat_polymer()
    M["polymer_gloss"] = mat_polymer("Polymer_Gloss_Black", base=(0.014, 0.014, 0.016), rough=0.25, coat=0.4)
    M["rubber"] = mat_rubber()
    M["metal"] = mat_metal()
    M["metal_black"] = mat_metal("Metal_Black_Cerakote", base=(0.022, 0.022, 0.024), rough=0.45,
                                 edge_col=(0.20, 0.20, 0.21))
    M["visor"] = mat_visor()
    M["screen"] = mat_screen()
    M["patch_flag"] = mat_patch()
    M["helmet"] = mat_polymer("Helmet_Shell_Cover", base=(0.026, 0.027, 0.030), rough=0.55, grain=900.0)
    M["nylon_camo"] = mat_nylon_camo("Pouch_Print_Neutral", base=(0.008, 0.008, 0.008), blot1=(0.016, 0.015, 0.013),
                                     blot2=(0.040, 0.037, 0.031), line=(0.26, 0.24, 0.20), tiles=2.6, line_amt=0.75)
    M["camo_warm"] = mat_nylon_camo("Pouch_Print_Warm", base=(0.012, 0.010, 0.008), blot1=(0.024, 0.020, 0.016),
                                    blot2=(0.060, 0.051, 0.040), line=(0.30, 0.265, 0.205), tiles=2.6, line_amt=0.75)
    M["camo_cool"] = mat_nylon_camo("Pouch_Print_Cool", base=(0.007, 0.0075, 0.008), blot1=(0.013, 0.014, 0.015),
                                    blot2=(0.030, 0.031, 0.033), line=(0.20, 0.20, 0.19), tiles=2.6, line_amt=0.75)
    M["belt"] = mat_nylon_camo("Belt_Webbing_Print", base=(0.024, 0.022, 0.019), blot1=(0.042, 0.038, 0.032),
                               blot2=(0.075, 0.068, 0.058), line=(0.24, 0.22, 0.18), tiles=3.2, line_amt=0.7,
                               edge_col=(0.20, 0.19, 0.17))
    M["carrier"] = mat_nylon_camo("Carrier_Cordura_Print", base=(0.007, 0.007, 0.0072), blot1=(0.014, 0.0135, 0.012),
                                  blot2=(0.026, 0.025, 0.022), line=(0.070, 0.066, 0.056), tiles=2.2, line_amt=0.7,
                                  edge_col=(0.060, 0.058, 0.054))
    M["webbing"] = mat_nylon("Webbing_MOLLE", base=(0.012, 0.012, 0.013), light=(0.030, 0.028, 0.026), tiles=24.0)
    M["plastic_light"] = mat_polymer("Plastic_Light_Grey", base=(0.16, 0.15, 0.14), rough=0.45, grain=900.0)
    M["cable_grey"] = mat_rubber("Cable_Coiled_Grey", base=(0.10, 0.10, 0.105), rough=0.40)
    M["velcro"] = mat_nylon("Velcro_Loop_Black", base=(0.007, 0.0075, 0.009), light=(0.018, 0.018, 0.020), tiles=40.0)
    M["rail"] = mat_metal("Helmet_Rail_Gunmetal", base=(0.023, 0.024, 0.027), rough=0.35, edge_col=(0.25, 0.25, 0.26))
    M["lens_pale"] = mat_screen("Lens_Pale_Blue", col=(0.50, 0.60, 0.80), strength=0.3)
    M["lens_dark"] = mat_polymer("Lens_Dark_Glass", base=(0.004, 0.006, 0.008), rough=0.05, coat=1.0, grain=4000.0)
    M["boot"] = L.mat_leather("Boot_Leather_Black", base=(0.011, 0.011, 0.012), light=(0.030, 0.030, 0.033), rough=0.45,
                              scuff=0.6, dirt=0.25)
    M["rubber_sole"] = mat_rubber("Rubber_Sole", base=(0.012, 0.012, 0.012), rough=0.55)
    M["screen_dim"] = mat_screen_img("Screen_Dive_Computer", "dive_screen.png", strength=1.2)
    M["screen_hud"] = mat_screen_img("Screen_Wrist_HUD", "wrist_hud.png", strength=0.45)
    M["plastic_dark"] = mat_polymer("Plastic_Buckle_Dark", base=(0.027, 0.030, 0.033), rough=0.45, grain=800.0)
    M["kydex"] = mat_polymer("Kydex_Black", base=(0.008, 0.009, 0.010), rough=0.30, coat=0.2, grain=1500.0)
    M["led_red"] = mat_screen("LED_Red_Orange", col=(1.0, 0.25, 0.06), strength=4.0)
    M["rope"] = L.mat_rope("Rope_Coyote_Tan")
    M["kneecap"] = mat_polymer("Kneepad_Cap_Gloss", base=(0.016, 0.017, 0.019), rough=0.20, coat=0.6, grain=900.0)
    M["midsole"] = mat_polymer("Boot_Midsole_Grey", base=(0.068, 0.072, 0.078), rough=0.5, grain=700.0)
    M["gun_metal"] = mat_metal("Gun_Cerakote_Black", base=(0.020, 0.021, 0.023), rough=0.42, edge_col=(0.16, 0.16, 0.17))
    M["gun_polymer"] = mat_polymer("Gun_Polymer_Black", base=(0.015, 0.015, 0.016), rough=0.45, grain=1400.0)
    M["gun_rail"] = mat_metal("Gun_Rail_Maritime", base=(0.030, 0.031, 0.033), rough=0.36, edge_col=(0.22, 0.22, 0.23))
    M["glove"] = mat_polymer("Glove_Leather_Neoprene", base=(0.0044, 0.0052, 0.0065), rough=0.35, coat=0.45,
                             grain=1500.0)
    M["armour_gloss"] = mat_polymer("Armour_Hard_Gloss", base=(0.0103, 0.0116, 0.0144), rough=0.25, coat=0.5)
    M["pad_gloss"] = mat_polymer("Elbow_Pad_Gloss", base=(0.0048, 0.0056, 0.0070), rough=0.22, coat=0.6)
    M["gauntlet"] = mat_polymer("Gauntlet_Rubberised", base=(0.0060, 0.0070, 0.0084), rough=0.35, coat=0.4)
    M["bezel"] = mat_metal("Bezel_Steel", base=(0.147, 0.153, 0.168), rough=0.22, edge_col=(0.45, 0.45, 0.47))
    M["mask"] = mat_polymer("Mask_Respirator_Black", base=(0.016, 0.016, 0.018), rough=0.30, coat=0.35, grain=1200.0)
    return M
