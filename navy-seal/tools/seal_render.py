"""Render the turnaround (one shot: FRONT, LEFT, BACK, RIGHT side by side) and cut it into the four panels.

    python navy-seal/tools/seal_render.py [--blend navy-seal/navy_seal.blend] [--out navy-seal/renders]
                                          [--scale 1.0] [--samples 128] [--compare concept_sheet.png]
At scale 1 the frame is 2288 x 1268 (2x the concept sheet's 1144 x 634 turnaround panel).  Writes turnaround.png,
turn_Front/Left/Back/Right.png and, with --compare, compare.png (render above, concept panel below).
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import bpy  # noqa: E402


def args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
    root = os.path.dirname(HERE)
    o = {"blend": os.path.join(root, "navy_seal.blend"), "out": os.path.join(root, "renders"), "scale": 1.0,
         "samples": 128, "compare": None}
    i = 0
    while i < len(argv):
        k = argv[i].lstrip("-")
        if k in o:
            v = argv[i + 1]
            o[k] = float(v) if k == "scale" else int(v) if k == "samples" else v
            i += 1
        i += 1
    return o


def main():
    o = args()
    bpy.ops.wm.open_mainfile(filepath=o["blend"])
    import seal_scene as S
    from PIL import Image
    sc = bpy.context.scene
    os.makedirs(o["out"], exist_ok=True)
    W, H = int(round(S.RES[0] * o["scale"])), int(round(S.RES[1] * o["scale"]))
    sc.render.resolution_x, sc.render.resolution_y = W, H
    sc.render.resolution_percentage = 100
    sc.cycles.samples = o["samples"]
    sc.camera = bpy.data.objects["CAM_Turnaround"]
    full = os.path.join(o["out"], "turnaround.png")
    sc.render.filepath = full
    bpy.ops.render.render(write_still=True)
    im = Image.open(full).convert("RGB")
    k = W / S.SHEET_W
    for v, (x0, x1) in S.PANELS.items():
        im.crop((int(round(x0 * k)), 0, int(round(x1 * k)), H)).save(os.path.join(o["out"], f"turn_{v}.png"))
    if o["compare"]:
        ref = Image.open(o["compare"]).convert("RGB").crop((0, 0, int(S.SHEET_W), int(S.SHEET_H))).resize((W, H))
        both = Image.new("RGB", (W, H * 2))
        both.paste(im, (0, 0))
        both.paste(ref, (0, H))
        both.save(os.path.join(o["out"], "compare.png"))
    print("rendered", W, H)


if __name__ == "__main__":
    main()
