"""Compose the Kage Musha character sheet (same layout as the concept) from rendered panels.

    KAGE_FONT_DIR=/path/to/fonts python tools/make_sheet.py --assets renders/sheet --out renders/kage_musha_sheet.png
"""
import json
import os
import sys

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
FONT_DIR = os.environ.get("KAGE_FONT_DIR", "fonts")
IDX = json.load(open(os.path.join(HERE, "fontindex.json"), encoding="utf-8"))
K = 2  # scale relative to the 1024x1536 concept


def latin(size, weight=500):
    p = os.path.join(FONT_DIR, "fontsource-shippori-mincho-b1-5.3.0", "package", "files",
                     f"shippori-mincho-b1-latin-{weight}-normal.woff")
    return ImageFont.truetype(p, size)


def kanji_font(ch, size, fam="yuji-boku"):
    rel = IDX[fam][ch]
    return ImageFont.truetype(os.path.join(FONT_DIR, f"fontsource-{fam}-5.3.0", "package", "files", rel), size)


def text_c(d, xy, txt, font, fill=(200, 190, 175), spacing=0):
    if spacing:
        w = sum(font.getlength(c) for c in txt) + spacing * (len(txt) - 1)
        x = xy[0] - w / 2
        for c in txt:
            d.text((x, xy[1]), c, font=font, fill=fill, anchor="lm")
            x += font.getlength(c) + spacing
    else:
        d.text(xy, txt, font=font, fill=fill, anchor="mm")


def vert_kanji(d, x, y, txt, size, fill, fam="yuji-boku", step=1.05):
    for c in txt:
        f = kanji_font(c, size, fam)
        d.text((x, y), c, font=f, fill=fill, anchor="mt")
        y += size * step
    return y


def panel(img, box, src, crop_center=(0.5, 0.5), zoom=1.0, border=(70, 62, 52)):
    x0, y0, x1, y1 = [v * K for v in box]
    w, h = x1 - x0, y1 - y0
    im = Image.open(src).convert("RGB")
    sw, sh = im.size
    scale = max(w / sw, h / sh) * zoom
    im = im.resize((int(sw * scale), int(sh * scale)), Image.LANCZOS)
    cx = int(im.width * crop_center[0] - w / 2)
    cy = int(im.height * crop_center[1] - h / 2)
    cx = max(0, min(im.width - w, cx))
    cy = max(0, min(im.height - h, cy))
    img.paste(im.crop((cx, cy, cx + w, cy + h)), (x0, y0))
    d = ImageDraw.Draw(img)
    d.rectangle([x0, y0, x1 - 1, y1 - 1], outline=border, width=2)


def seal(d, cx, cy, r, txt="影"):
    d.rectangle([cx - r, cy - r, cx + r, cy + r], fill=(120, 18, 16))
    f = kanji_font(txt, int(r * 1.4), "shippori-mincho-b1")
    d.text((cx, cy), txt, font=f, fill=(20, 8, 8), anchor="mm")


def main():
    a = sys.argv[1:]
    o = {"assets": "renders/sheet", "out": "renders/kage_musha_sheet.png"}
    for i in range(0, len(a), 2):
        o[a[i].lstrip("-")] = a[i + 1]
    A = o["assets"]
    W, H = 1024 * K, 1536 * K
    img = Image.new("RGB", (W, H), (16, 14, 13))
    d = ImageDraw.Draw(img)
    gold = (196, 170, 128)
    grey = (205, 196, 182)

    # --- turnaround strip ---------------------------------------------------
    views = [("Front", (88, 0, 318, 712)), ("Left", (318, 0, 528, 712)), ("Right", (528, 0, 738, 712)),
             ("Back", (738, 0, 960, 712))]
    for v, box in views:
        panel(img, box, os.path.join(A, f"turn_{v}.png"), (0.5, 0.47), border=(16, 14, 13))
    # darkened side columns
    d.rectangle([0, 0, 88 * K, 712 * K], fill=(14, 12, 11))
    d.rectangle([960 * K, 0, W, 712 * K], fill=(14, 12, 11))
    # bottom fade + labels
    lab = latin(13 * K)
    for v, box in views:
        cx = (box[0] + box[2]) / 2 * K
        name = {"Left": "LEFT SIDE", "Right": "RIGHT SIDE"}.get(v, v.upper())
        text_c(d, (cx, 702 * K), name, lab, grey, spacing=3 * K)
    # left column: 影武者, seal, KAGE MUSHA, motto
    vert_kanji(d, 44 * K, 14 * K, "影武者", 60 * K, (215, 205, 190), "yuji-boku", 1.0)
    seal(d, 44 * K, 240 * K, 13 * K)
    text_c(d, (44 * K, 293 * K), "KAGE", latin(15 * K), grey, spacing=1 * K)
    text_c(d, (44 * K, 312 * K), "MUSHA", latin(15 * K), grey, spacing=1 * K)
    for k, line in enumerate(("SHADOWS", "SERVE", "A HIGHER", "PURPOSE")):
        text_c(d, (44 * K, (336 + k * 11) * K), line, latin(8 * K), (170, 162, 150))
    # right column: 忠義に生き、影に死す + motto + Tenshu-shu crest
    y = vert_kanji(d, 992 * K, 20 * K, "忠義に生き、", 30 * K, (205, 195, 180), "yuji-boku", 1.0)
    vert_kanji(d, 992 * K, y, "影に死す", 30 * K, (205, 195, 180), "yuji-boku", 1.0)
    for k, line in enumerate(("LIVE", "BY", "LOYALTY", "DIE", "IN", "SHADOWS")):
        text_c(d, (992 * K, (382 + k * 12) * K), line, latin(8 * K), (170, 162, 150))
    d.rectangle([958 * K, 555 * K, 1022 * K, 658 * K], fill=(10, 9, 9), outline=(60, 54, 46), width=2)
    mon = Image.open(os.path.join(os.path.dirname(HERE), "textures", "mon_flower.png")).resize((44 * K, 44 * K))
    img.paste((200, 192, 178), (968 * K, 563 * K), mon)
    for k, ch in enumerate("天守衆"):
        d.text(((966 + k * 17) * K, 625 * K), ch, font=kanji_font(ch, 16 * K, "shippori-mincho-b1"), fill=grey,
               anchor="lm")
    text_c(d, (990 * K, 646 * K), "TENSHU-SHU", latin(6 * K), (170, 162, 150))

    # --- middle row ------------------------------------------------------------
    panel(img, (14, 727, 366, 995), os.path.join(A, "detail_FrontWaist.png"))
    panel(img, (657, 727, 1014, 995), os.path.join(A, "detail_BackWaist.png"))
    # sword placement diagram
    d.rectangle([368 * K, 727 * K, 655 * K, 995 * K], fill=(18, 16, 15))
    text_c(d, (511 * K, 742 * K), "SWORD PLACEMENT (TOP VIEW)", latin(11 * K), grey, spacing=1 * K)
    tv = Image.open(os.path.join(A, "topview.png")).convert("RGBA").resize((190 * K, 190 * K), Image.LANCZOS)
    alpha = tv.split()[3]
    alpha = alpha.filter(ImageFilter.GaussianBlur(2 * K))
    lum = ImageEnhance.Brightness(tv.convert("L")).enhance(1.6).filter(ImageFilter.GaussianBlur(1))
    lum = Image.eval(lum, lambda v: int(70 + v * 0.45))
    col = Image.merge("RGB", (lum, lum, lum))
    img.paste(col, (416 * K, 760 * K), Image.eval(alpha, lambda v: int(v * 0.55)))
    d.ellipse([496 * K, 840 * K, 526 * K, 870 * K], outline=(150, 146, 140), width=1)
    d.arc([430 * K, 860 * K, 592 * K, 960 * K], 10, 170, fill=(200, 196, 188), width=2 * K)
    for sx in (-1, 1):
        x0, y0 = (511 + sx * 18) * K, 860 * K
        x1, y1 = (511 + sx * 110) * K, 905 * K
        d.line([x0, y0, x1, y1], fill=(210, 206, 198), width=2 * K)
        d.polygon([(x1, y1), (x1 - sx * 9 * K, y1 - 9 * K), (x1 - sx * 2 * K, y1 - 13 * K)], fill=(210, 206, 198))
    text_c(d, (409 * K, 841 * K), "WAKIZASHI", latin(9 * K), grey)
    text_c(d, (409 * K, 854 * K), "(LEFT SIDE)", latin(7 * K), (170, 162, 150))
    text_c(d, (613 * K, 841 * K), "KATANA", latin(9 * K), grey)
    text_c(d, (613 * K, 854 * K), "(RIGHT SIDE)", latin(7 * K), (170, 162, 150))
    text_c(d, (511 * K, 922 * K), "180°", latin(22 * K), (230, 225, 215))
    text_c(d, (190 * K, 1005 * K), "FRONT WAIST (RIGHT SWORD)", latin(10 * K), grey, spacing=1 * K)
    text_c(d, (835 * K, 1005 * K), "BACK WAIST", latin(10 * K), grey, spacing=1 * K)

    # --- item row ----------------------------------------------------------------
    items = [("SmokeBombs", (12, 1018, 208, 1178), "SMOKE BOMBS"), ("PowderFlask", (212, 1018, 310, 1178), "POWDER FLASK"),
             ("UtilityPouch", (314, 1018, 432, 1178), "UTILITY POUCH"),
             ("ThrowingKnives", (436, 1018, 566, 1178), "THROWING KNIVES"),
             ("GrapplingHook", (570, 1018, 736, 1178), "GRAPPLING HOOK & ROPE")]
    for name, box, label in items:
        panel(img, box, os.path.join(A, f"item_{name}.png"))
        text_c(d, ((box[0] + box[2]) / 2 * K, (box[3] - 12) * K), label, latin(9 * K), grey)
    panel(img, (740, 1020, 1004, 1096), os.path.join(A, "item_Katana.png"))
    text_c(d, (938 * K, 1082 * K), "KATANA (RIGHT SIDE)", latin(8 * K), grey)
    panel(img, (740, 1100, 1004, 1176), os.path.join(A, "item_Wakizashi.png"))
    text_c(d, (938 * K, 1162 * K), "WAKIZASHI (LEFT SIDE)", latin(8 * K), grey)

    # --- detail row --------------------------------------------------------------
    details = [("Kasa", (5, 1200, 220, 1442), "HELMET / KASA DETAIL"), ("Mask", (225, 1200, 420, 1442), "MASK DETAIL"),
               ("Armor", (428, 1200, 622, 1442), "ARMOR DETAIL"),
               ("Fabric", (628, 1200, 835, 1442), "FABRIC & PATTERN"),
               ("LegArmor", (840, 1200, 1018, 1442), "LEG ARMOR")]
    for name, box, label in details:
        panel(img, box, os.path.join(A, f"detail_{name}.png"))
        text_c(d, ((box[0] + box[2]) / 2 * K, 1455 * K), label, latin(10 * K), grey, spacing=1 * K)

    # --- footer --------------------------------------------------------------------
    text_c(d, (480 * K, 1499 * K), "“THE SHADOW DOES NOT SEEK GLORY, ONLY COMPLETION.”", latin(12 * K),
           (150, 142, 132), spacing=3 * K)
    seal(d, 822 * K, 1499 * K, 9 * K, "衆")
    if o["out"].lower().endswith((".jpg", ".jpeg")):
        img.save(o["out"], quality=92, optimize=True, progressive=True)
    else:
        img.save(o["out"], optimize=True)
    print("wrote", o["out"], img.size)


main()
