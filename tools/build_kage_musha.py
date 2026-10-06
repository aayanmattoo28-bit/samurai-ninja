"""Build the Kage Musha (shadow warrior) samurai-ninja and save samurai-ninja_claude.blend.

Run with Blender 4.2+:
    blender --background --python tools/build_kage_musha.py
or with the `bpy` Python module:
    python tools/build_kage_musha.py [--out path.blend] [--parts head,kasa,...] [--no-env]
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import bpy  # noqa: E402

import kage_lib  # noqa: E402
from kage_mats import M, build_materials  # noqa: E402

ROOT = os.path.dirname(HERE)


def reset_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    sc.unit_settings.system = "METRIC"
    sc.unit_settings.scale_length = 1.0
    kage_lib._COLLS.clear()
    kage_lib._IMAGES.clear()
    kage_lib._MATS.clear()
    return sc


def parse_args():
    argv = sys.argv
    if "--" in argv:
        argv = argv[argv.index("--") + 1:]
    else:
        argv = argv[1:]
    opts = {"out": os.path.join(ROOT, "samurai-ninja_claude.blend"), "parts": None, "env": True, "save": True}
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--out":
            opts["out"] = argv[i + 1]
            i += 1
        elif a == "--parts":
            opts["parts"] = set(argv[i + 1].split(","))
            i += 1
        elif a == "--no-env":
            opts["env"] = False
        elif a == "--no-save":
            opts["save"] = False
        i += 1
    return opts


def build(opts):
    import kage_body
    import kage_armor
    import kage_gear
    import kage_scene

    sc = reset_scene()
    build_materials()
    char = kage_lib.collection("KageMusha_Character")
    root = kage_lib.empty("KageMusha_Root", char, size=0.5)

    def want(name):
        return opts["parts"] is None or name in opts["parts"]

    C = lambda n: kage_lib.collection(n, char)  # noqa: E731
    if want("head"):
        kage_body.build_head(C("Head_Hood_Scarf"), root)
    if want("kasa"):
        kage_body.build_kasa(C("Kasa_Hat"), root)
    if want("torso"):
        kage_armor.build_torso(C("Torso_Do_Cuirass"), root)
    if want("sode"):
        kage_armor.build_sode(C("Sode_Shoulder_Guards"), root)
    if want("arms"):
        kage_armor.build_arms(C("Arms_Kote_Gloves"), root)
    if want("legs"):
        kage_armor.build_legs(C("Legs_Suneate_Boots"), root)
    if want("waist"):
        kage_gear.build_waist(C("Waist_Obi_Belts"), root)
    if want("skirt"):
        kage_gear.build_skirts(C("Skirt_Kusazuri_Apron"), root)
    if want("swords"):
        kage_gear.build_swords(C("Weapons_Katana_Wakizashi"), root)
    if want("gear"):
        kage_gear.build_gear(C("Gear_Gourds_Bombs_Pouches"), root)
    if want("back"):
        kage_gear.build_back(C("Back_Banner_Rope"), root)

    kage_scene.setup_render(sc)
    kage_scene.build_lights(sc)
    kage_scene.build_cameras(sc)
    if opts["env"]:
        kage_scene.build_environment(sc)
    if want("props"):
        kage_scene.build_props_showcase(sc)
    return sc


def save(opts):
    out = opts["out"]
    try:
        bpy.ops.file.pack_all()
    except Exception as e:  # pragma: no cover
        print("pack failed:", e)
    bpy.ops.wm.save_as_mainfile(filepath=out, compress=True)
    print("saved", out, os.path.getsize(out) / 1e6, "MB")


if __name__ == "__main__":
    o = parse_args()
    build(o)
    if o["save"]:
        save(o)
