"""Render the four turnaround panels (FRONT, LEFT, BACK, RIGHT) of navy_seal.blend and assemble the strip.

    python navy-seal/tools/seal_render.py [--blend navy-seal/navy_seal.blend] [--out navy-seal/renders]
                                          [--scale 1.0] [--samples 96] [--only Front,Back] [--compare concept.png]
Each panel is rendered centred on the figure, wide enough for its slice of the sheet, then cropped so the four
slices butt together into one continuous backdrop exactly like the concept's turnaround strip.
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
         "samples": 96, "only": None, "compare": None}
    i = 0
    while i < len(argv):
        k = argv[i].lstrip("-")
        if k in o:
            v = argv[i + 1]
            o[k] = float(v) if k == "scale" else int(v) if k == "samples" else set(v.split(",")) if k == "only" else v
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
    H = int(round(S.SHEET_H * 2 * o["scale"]))  # 2x the sheet's strip height at scale 1
    k = H / S.SHEET_H
    sc.cycles.samples = o["samples"]
    sc.render.resolution_percentage = 100
    crops = {}
    for v in ("Front", "Left", "Back", "Right"):
        if o["only"] and v not in o["only"]:
            continue
        a, c, b = S.PANELS[v]
        half = max(c - a, b - c)
        W = int(round(2 * half * k))
        cam = S.place_view(v)
        sc.camera = cam
        sc.render.resolution_x, sc.render.resolution_y = W, H
        full = os.path.join(o["out"], f"full_{v}.png")
        sc.render.filepath = full
        bpy.ops.render.render(write_still=True)
        im = Image.open(full)
        x0 = int(round((half - (c - a)) * k))
        x1 = int(round((half + (b - c)) * k))
        crop = im.crop((x0, 0, x1, H))
        crop.save(os.path.join(o["out"], f"turn_{v}.png"))
        crops[v] = crop
        print("rendered", v, crop.size)
    if len(crops) == 4:
        Wt = sum(cp.width for cp in crops.values())
        strip = Image.new("RGB", (Wt, H))
        x = 0
        for v in ("Front", "Left", "Back", "Right"):
            strip.paste(crops[v].convert("RGB"), (x, 0))
            x += crops[v].width
        strip.save(os.path.join(o["out"], "turnaround_strip.png"))
        if o["compare"]:
            ref = Image.open(o["compare"]).convert("RGB").crop((0, 0, 1145, 630)).resize((Wt, H))
            both = Image.new("RGB", (Wt, H * 2))
            both.paste(strip, (0, 0))
            both.paste(ref, (0, H))
            both.save(os.path.join(o["out"], "compare_strip.png"))


if __name__ == "__main__":
    main()
