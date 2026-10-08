"""Build the U.S. Navy SEAL character and its harbour turnaround set; save navy-seal/navy_seal.blend.

    python navy-seal/tools/seal_build.py [--out path.blend] [--parts body,head,vest,lower,weapons] [--no-env] [--no-save]
(run with the `bpy` module, or `blender --background --python navy-seal/tools/seal_build.py`)
"""
import importlib
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import bpy  # noqa: E402

import seal_lib as L  # noqa: E402

SEAL_ROOT = os.path.dirname(HERE)

# module name -> (part key, collection name)
MODULES = [
    ("seal_body", "body", "Body_Drysuit_Gloves"),
    ("seal_head", "head", "Head_Helmet_Mask_Rebreather"),
    ("seal_arms", "arms", "Arms_Pockets_Pads_Gauntlets"),
    ("seal_vest", "vest", "Vest_PlateCarrier_Pouches"),
    ("seal_lower", "lower", "Belt_Holster_Kneepads_Boots"),
    ("seal_weapons", "weapons", "Weapons_Carried_Gear"),
]


def parse_args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
    o = {"out": os.path.join(SEAL_ROOT, "navy_seal.blend"), "parts": None, "env": True, "save": True}
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--out":
            o["out"] = argv[i + 1]
            i += 1
        elif a == "--parts":
            o["parts"] = set(argv[i + 1].split(","))
            i += 1
        elif a == "--no-env":
            o["env"] = False
        elif a == "--no-save":
            o["save"] = False
        i += 1
    return o


def build(o):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    sc.unit_settings.system = "METRIC"
    L.reset_state()
    import seal_mats
    seal_mats.build_materials()
    char = L.collection("NavySeal_Character")
    root = L.empty("NavySeal_Root", char, size=0.5)
    for mod_name, key, coll_name in MODULES:
        if o["parts"] is not None and key not in o["parts"]:
            continue
        if not os.path.exists(os.path.join(HERE, mod_name + ".py")):
            print("module not written yet:", mod_name)
            continue
        mod = importlib.import_module(mod_name)
        mod.build(L.collection(coll_name, char), root)
    import seal_scene
    seal_scene.setup_render(sc)
    seal_scene.build_lights(sc)
    seal_scene.build_cameras(sc)
    seal_scene.build_turnaround(sc)
    if o["env"]:
        seal_scene.build_environment(sc)
    return sc


def save(o):
    try:
        bpy.ops.file.pack_all()
    except Exception as e:  # pragma: no cover
        print("pack failed:", e)
    bpy.ops.wm.save_as_mainfile(filepath=o["out"], compress=True)
    print("saved", o["out"], round(os.path.getsize(o["out"]) / 1e6, 2), "MB")


if __name__ == "__main__":
    opts = parse_args()
    build(opts)
    if opts["save"]:
        save(opts)
