"""Render turnaround / detail views from a built scene.

python tools/render_views.py --blend samurai-ninja_claude.blend --views Front,Left --out renders/ --samples 64 --res 600
"""
import math
import os
import sys

import bpy

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)


def main():
    argv = sys.argv[1:]
    opts = {"blend": None, "views": "Front,Left,Right,Back", "out": os.path.join(os.path.dirname(HERE), "renders"),
            "samples": 64, "res": 600, "build": None, "prefix": "", "noenv": False, "aspect": 2.0}
    i = 0
    while i < len(argv):
        k = argv[i].lstrip("-")
        if k in ("noenv",):
            opts[k] = True
        else:
            opts[k] = argv[i + 1]
            i += 1
        i += 1
    if opts["build"]:
        import build_kage_musha as B
        o = {"out": None, "parts": set(opts["build"].split(",")) if opts["build"] != "all" else None,
             "env": not opts["noenv"], "save": False}
        sc = B.build(o)
    else:
        bpy.ops.wm.open_mainfile(filepath=opts["blend"])
        sc = bpy.context.scene
    sc.cycles.samples = int(opts["samples"])
    os.makedirs(opts["out"], exist_ok=True)
    rig = bpy.data.objects.get("Light_Rig")
    import kage_scene
    for v in opts["views"].split(","):
        cam = bpy.data.objects.get("CAM_" + v) or bpy.data.objects.get("CAM_Detail_" + v)
        if cam is None:
            print("no camera", v)
            continue
        sc.camera = cam
        res = int(opts["res"])
        if v in kage_scene.TURNAROUND:
            sc.render.resolution_x = res
            sc.render.resolution_y = int(res * float(opts["aspect"]))
            if rig:
                rig.rotation_euler[2] = math.radians(kage_scene.TURNAROUND[v][2])
        else:
            sc.render.resolution_x = res
            sc.render.resolution_y = int(res * 0.75)
            if rig:
                rig.rotation_euler[2] = 0.0
        sc.render.filepath = os.path.join(opts["out"], opts["prefix"] + v + ".png")
        bpy.ops.render.render(write_still=True)
        print("rendered", sc.render.filepath)


main()
