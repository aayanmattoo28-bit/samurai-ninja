"""Render every panel of the character sheet from samurai-ninja_claude.blend.

python tools/render_sheet_assets.py --blend samurai-ninja_claude.blend --out renders/sheet --samples 96 --scale 1.0
"""
import math
import os
import sys

import bpy
from mathutils import Euler, Vector

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

ITEMS = {
    # name: (target offset from showcase origin, camera offset, focal, resolution)
    "SmokeBombs": ((-1.04, 0.0, 0.95), (-1.04, -0.55, 1.10), 50, (520, 420)),
    "PowderFlask": ((-0.78, 0.0, 0.98), (-0.78, -0.45, 1.06), 50, (300, 420)),
    "UtilityPouch": ((-0.55, 0.0, 0.96), (-0.55, -0.42, 1.06), 50, (300, 420)),
    "ThrowingKnives": ((-0.25, 0.0, 1.02), (-0.25, -0.50, 1.08), 50, (300, 420)),
    "GrapplingHook": ((0.04, 0.0, 0.95), (0.04, -0.55, 1.22), 50, (420, 420)),
    "Katana": ((0.46, 0.17, 1.36), (0.46, -0.52, 1.36), 50, (700, 200)),
    "Wakizashi": ((0.60, 0.17, 1.19), (0.60, -0.40, 1.19), 50, (700, 200)),
    "Matchlock": ((0.20, -0.24, 0.96), (0.25, -0.75, 1.20), 45, (640, 300)),
    "DrawnKatana": ((0.70, -0.22, 0.92), (0.70, -1.05, 1.30), 40, (640, 260)),
}


def args():
    a = sys.argv[1:]
    o = {"blend": "samurai-ninja_claude.blend", "out": "renders/sheet", "samples": 96, "scale": 1.0, "only": None}
    i = 0
    while i < len(a):
        k = a[i].lstrip("-")
        o[k] = a[i + 1]
        i += 2
    return o


def cam(name, loc, target, focal):
    c = bpy.data.objects.get(name)
    if c is None:
        cd = bpy.data.cameras.new(name)
        c = bpy.data.objects.new(name, cd)
        bpy.context.scene.collection.objects.link(c)
    c.data.lens = focal
    c.data.sensor_fit = "VERTICAL"
    c.data.sensor_height = 24
    c.location = loc
    c.rotation_euler = (Vector(target) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
    return c


def render(sc, camobj, path, res, samples):
    sc.camera = camobj
    sc.render.resolution_x, sc.render.resolution_y = res
    sc.cycles.samples = samples
    sc.render.filepath = path
    bpy.ops.render.render(write_still=True)
    print("rendered", path)


def main():
    o = args()
    bpy.ops.wm.open_mainfile(filepath=o["blend"])
    sc = bpy.context.scene
    out = o["out"]
    os.makedirs(out, exist_ok=True)
    S = float(o["scale"])
    spp = int(o["samples"])
    only = set(o["only"].split(",")) if o["only"] else None
    import kage_scene

    def want(n):
        return only is None or n in only

    # 1. turnaround: square-on cameras, environment yawed to each panel's slice of one continuous backdrop
    for v in kage_scene.TURNAROUND:
        if not want(v):
            continue
        camo = kage_scene.place_turn(v)
        rx, ry = kage_scene.PANEL_RES[v]
        render(sc, camo, os.path.join(out, f"turn_{v}.png"), (int(rx * S), int(ry * S)), max(spp, 128) if spp >= 48 else spp)
    kage_scene.set_view(0.0)
    # 2. details (character close-ups): environment and lights turned to face the detail camera, raking key on
    key = bpy.data.objects.get("Key_Warm")
    fill = bpy.data.objects.get("Fill_Cool")
    for v in ("FrontWaist", "BackWaist", "Kasa", "Mask", "Armor", "Fabric", "LegArmor"):
        if not want(v):
            continue
        camo = bpy.data.objects["CAM_Detail_" + v]
        loc, tgt = kage_scene.DETAILS[v][0], kage_scene.DETAILS[v][1]
        kage_scene.set_view(kage_scene.view_yaw(Vector(tgt) - Vector(loc)))
        res = (int(700 * S), int(530 * S)) if "Waist" in v else (int(420 * S), int(500 * S))
        ff = bpy.data.objects.get("Face_Fill")
        rk = bpy.data.objects.get("Rake_" + v)
        saved = [(ob, ob.data.energy) for ob in (key, fill) if ob is not None]
        if ff is not None:
            ff.data.energy = 24 if v == "Mask" else 7
        if rk is not None:
            rk.hide_render = False
            for ob, e in saved:
                ob.data.energy = e * 0.5
        render(sc, camo, os.path.join(out, f"detail_{v}.png"), res, spp)
        if ff is not None:
            ff.data.energy = 7
        if rk is not None:
            rk.hide_render = True
        for ob, e in saved:
            ob.data.energy = e
    kage_scene.set_view(0.0)
    # 3. sword placement top view (hat hidden)
    if want("TopView"):
        hidden = []
        for ob in bpy.data.objects:
            if ob.name.startswith("Kasa_") or ob.type == "LIGHT" and False:
                hidden.append((ob, ob.hide_render))
                ob.hide_render = True
        env = bpy.data.collections.get("Environment_Courtyard")
        env_state = env.hide_render if env else None
        if env:
            env.hide_render = True
        c = cam("CAM_TopView", (0.0, 0.0, 6.0), (0.0, 0.0, 0.0), 120)
        c.rotation_euler = Euler((0, 0, 0))
        sc.render.film_transparent = True
        render(sc, c, os.path.join(out, "topview.png"), (int(560 * S), int(560 * S)), max(16, spp // 3))
        sc.render.film_transparent = False
        for ob, st in hidden:
            ob.hide_render = st
        if env:
            env.hide_render = env_state
    # 4. items (props showcase)
    origin = Vector((7.0, -7.0, 0.0))
    for name, (tgt, cpos, f, res) in ITEMS.items():
        if not want(name):
            continue
        c = cam("CAM_Item_" + name, origin + Vector(cpos), origin + Vector(tgt), f)
        if name in ("Katana", "Wakizashi"):
            c.data.type = "ORTHO"
            c.data.sensor_fit = "HORIZONTAL"
            c.data.ortho_scale = 0.46 if name == "Katana" else 0.40
        c.data.dof.use_dof = True
        c.data.dof.focus_distance = (Vector(cpos) - Vector(tgt)).length
        c.data.dof.aperture_fstop = 5.6
        hide = []
        if name in ("Katana", "Wakizashi"):
            other = "Showcase_Wakizashi" if name == "Katana" else "Showcase_Katana"
            for ob in bpy.data.objects:
                if ob.name == "Showcase_Sword_Stand" or ob.name.startswith(other):
                    hide.append(ob)
        for ob in hide:
            ob.hide_render = True
        render(sc, c, os.path.join(out, f"item_{name}.png"), (int(res[0] * S), int(res[1] * S)), spp)
        for ob in hide:
            ob.hide_render = False


main()
