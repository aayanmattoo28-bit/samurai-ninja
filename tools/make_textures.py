"""Generate the emblem / print / pattern textures used by the Kage Musha model.

All textures are grayscale masks (white = gold / print, black = base) so the
Blender materials can mix lacquer, cloth and gold however they need.

Fonts: brush kanji come from the SIL-OFL "Yuji Boku" and "Shippori Mincho B1"
fonts (fontsource npm packages).  Point KAGE_FONT_DIR at a folder holding the
unpacked packages (fontsource-yuji-boku-5.3.0/, fontsource-shippori-mincho-b1-5.3.0/).

    KAGE_FONT_DIR=/path/to/fonts python tools/make_textures.py
"""
import json
import math
import os
import random

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(os.path.dirname(HERE), "textures")
FONT_DIR = os.environ.get("KAGE_FONT_DIR", "fonts")
FONT_INDEX = json.load(open(os.path.join(HERE, "fontindex.json"), encoding="utf-8"))

os.makedirs(OUT, exist_ok=True)
rng = random.Random(7)
nrng = np.random.default_rng(7)


# ----------------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------------
def font_for(ch, size, family="yuji-boku"):
    rel = FONT_INDEX[family][ch]
    if family == "shippori-mincho-b1":
        parts = rel.split("-")
        parts[-2] = "800"
        rel = "-".join(parts)
    path = os.path.join(FONT_DIR, f"fontsource-{family}-5.3.0", "package", "files", rel)
    return ImageFont.truetype(path, size)


def glyph(ch, size, family="yuji-boku"):
    """Return a tight 'L' image of one kanji."""
    f = font_for(ch, size, family)
    im = Image.new("L", (int(size * 1.6), int(size * 1.6)), 0)
    ImageDraw.Draw(im).text((size * 0.2, size * 0.1), ch, font=f, fill=255)
    bb = im.getbbox()
    return im.crop(bb) if bb else im


def paste_center(dst, src, cx, cy, wrap=False):
    x = int(cx - src.width / 2)
    y = int(cy - src.height / 2)
    if not wrap:
        dst.paste(255, (x, y), src)
        return
    W, H = dst.size
    for ox in (-W, 0, W):
        for oy in (-H, 0, H):
            dst.paste(255, (x + ox, y + oy), src)


def fractal_noise(w, h, octaves=6, base=4, seed=0, persistence=0.55):
    g = np.random.default_rng(seed)
    acc = np.zeros((h, w), np.float32)
    amp, tot = 1.0, 0.0
    for o in range(octaves):
        n = base * 2 ** o
        small = g.random((n, n)).astype(np.float32)
        # tileable: wrap by repeating first row/col before resize
        small = np.vstack([small, small[:1]])
        small = np.hstack([small, small[:, :1]])
        im = Image.fromarray((small * 255).astype(np.uint8)).resize(
            (w + w // n, h + h // n), Image.BICUBIC)
        arr = np.asarray(im, np.float32)[: h, : w] / 255.0
        acc += arr * amp
        tot += amp
        amp *= persistence
    acc /= tot
    acc = (acc - acc.min()) / (acc.max() - acc.min() + 1e-6)
    return acc


def distress(img, amount=0.35, seed=1, scale=6):
    """Knock random holes / fading into a mask (worn print / worn gilding)."""
    w, h = img.size
    n = fractal_noise(w, h, 6, scale, seed)
    speck = nrng.random((h, w)).astype(np.float32)
    a = np.asarray(img, np.float32) / 255.0
    keep = np.clip((n - amount) * 3.0, 0, 1)
    keep *= np.where(speck < 0.06, 0.25, 1.0)
    out = a * (0.55 + 0.45 * keep) * np.clip(keep * 1.6, 0, 1)
    return Image.fromarray((np.clip(out, 0, 1) * 255).astype(np.uint8))


def save(img, name):
    p = os.path.join(OUT, name)
    img.save(p, optimize=True)
    print("wrote", p, img.size)


def catmull(points, steps=40):
    pts = [points[0]] + points + [points[-1]]
    out = []
    for i in range(1, len(pts) - 2):
        p0, p1, p2, p3 = pts[i - 1], pts[i], pts[i + 1], pts[i + 2]
        for s in range(steps):
            t = s / steps
            t2, t3 = t * t, t * t * t
            x = 0.5 * ((2 * p1[0]) + (-p0[0] + p2[0]) * t + (2 * p0[0] - 5 * p1[0] + 4 * p2[0] - p3[0]) * t2 + (-p0[0] + 3 * p1[0] - 3 * p2[0] + p3[0]) * t3)
            y = 0.5 * ((2 * p1[1]) + (-p0[1] + p2[1]) * t + (2 * p0[1] - 5 * p1[1] + 4 * p2[1] - p3[1]) * t2 + (-p0[1] + 3 * p1[1] - 3 * p2[1] + p3[1]) * t3)
            out.append((x, y))
    out.append(points[-1])
    return out


def stroke(draw, pts, w0, w1, fill=255):
    n = len(pts)
    for i, (x, y) in enumerate(pts):
        t = i / max(1, n - 1)
        r = (w0 + (w1 - w0) * t) / 2
        draw.ellipse([x - r, y - r, x + r, y + r], fill=fill)


def normals(pts):
    out = []
    for i in range(len(pts)):
        a = pts[max(0, i - 1)]
        b = pts[min(len(pts) - 1, i + 1)]
        dx, dy = b[0] - a[0], b[1] - a[1]
        l = math.hypot(dx, dy) or 1
        out.append((-dy / l, dx / l, dx / l, dy / l))
    return out


def cloud_swirl(draw, cx, cy, r, width=6, turns=1.6, fill=255, direction=1):
    pts = []
    for i in range(80):
        t = i / 79
        a = direction * t * turns * 2 * math.pi
        rr = r * (1 - 0.8 * t)
        pts.append((cx + rr * math.cos(a), cy + rr * math.sin(a)))
    stroke(draw, pts, width, width * 0.6, fill)


def ruyi_cloud(draw, cx, cy, s, fill=255, width=None):
    width = width or max(3, s * 0.12)
    cloud_swirl(draw, cx, cy, s * 0.5, width, 1.4, fill, 1)
    cloud_swirl(draw, cx + s * 0.75, cy + s * 0.1, s * 0.38, width * 0.9, 1.3, fill, -1)
    cloud_swirl(draw, cx - s * 0.7, cy + s * 0.15, s * 0.32, width * 0.8, 1.3, fill, 1)
    tail = catmull([(cx - s * 1.0, cy + s * 0.5), (cx, cy + s * 0.55), (cx + s * 1.2, cy + s * 0.45), (cx + s * 1.8, cy + s * 0.2)], 20)
    stroke(draw, tail, width, 1, fill)


def petal_flower(draw, cx, cy, r, petals=5, fill=255, inner=0, notch=True, rot=-90):
    for k in range(petals):
        a = math.radians(rot + k * 360 / petals)
        px, py = cx + math.cos(a) * r * 0.52, cy + math.sin(a) * r * 0.52
        pts = []
        for i in range(30):
            t = i / 29 * 2 * math.pi
            ex, ey = math.cos(t) * r * 0.48, math.sin(t) * r * 0.30
            pts.append((px + ex * math.cos(a) - ey * math.sin(a), py + ex * math.sin(a) + ey * math.cos(a)))
        draw.polygon(pts, fill=fill)
        if notch:
            nx, ny = cx + math.cos(a) * r * 1.0, cy + math.sin(a) * r * 1.0
            draw.ellipse([nx - r * 0.09, ny - r * 0.09, nx + r * 0.09, ny + r * 0.09], fill=inner)
    draw.ellipse([cx - r * 0.18, cy - r * 0.18, cx + r * 0.18, cy + r * 0.18], fill=inner)
    draw.ellipse([cx - r * 0.09, cy - r * 0.09, cx + r * 0.09, cy + r * 0.09], fill=fill)


# ----------------------------------------------------------------------------
# 1. Dragon emblem (shoulder guards) - coiled eastern dragon among clouds
# ----------------------------------------------------------------------------
def make_dragon(S=1024):
    im = Image.new("L", (S, S), 0)
    d = ImageDraw.Draw(im)
    s = S / 1000.0
    P = lambda pts: [(x * s, y * s) for x, y in pts]
    body = catmull(P([(640, 250), (560, 300), (430, 300), (330, 380), (320, 500),
                      (420, 580), (580, 560), (690, 600), (700, 720), (600, 800),
                      (450, 810), (330, 760), (250, 790), (200, 860)]), 30)
    n = len(body)
    widths = [max(14 * s, (130 - 112 * (i / n) ** 1.1) * s) for i in range(n)]
    nm = normals(body)
    # dorsal fin / spikes on one side
    for i in range(6, n - 10, 7):
        x, y = body[i]
        nx, ny, tx, ty = nm[i]
        w = widths[i]
        base1 = (x + nx * w * 0.45 - tx * w * 0.25, y + ny * w * 0.45 - ty * w * 0.25)
        base2 = (x + nx * w * 0.45 + tx * w * 0.25, y + ny * w * 0.45 + ty * w * 0.25)
        tip = (x + nx * w * 0.95 - tx * w * 0.35, y + ny * w * 0.95 - ty * w * 0.35)
        d.polygon([base1, tip, base2], fill=255)
    # body
    for i, (x, y) in enumerate(body):
        r = widths[i] / 2
        d.ellipse([x - r, y - r, x + r, y + r], fill=255)
    # scales: dark arcs along the body
    for i in range(4, n - 4, 6):
        x, y = body[i]
        nx, ny, tx, ty = nm[i]
        w = widths[i]
        for k in (-0.2, 0.12):
            cx, cy = x + nx * w * k, y + ny * w * k
            rr = w * 0.2
            ang = math.degrees(math.atan2(ty, tx))
            d.arc([cx - rr, cy - rr, cx + rr, cy + rr], ang - 80, ang + 80, fill=0, width=max(2, int(3 * s)))
    # belly line
    belly = [(x - nm[i][0] * widths[i] * 0.36, y - nm[i][1] * widths[i] * 0.36) for i, (x, y) in enumerate(body)]
    for i in range(0, n - 1, 3):
        x0, y0 = belly[i]
        x1, y1 = belly[min(n - 1, i + 2)]
        d.line([x0, y0, x1, y1], fill=0, width=max(2, int(3 * s)))
    # legs with claws
    for t_leg, side in ((0.18, -1), (0.38, 1), (0.62, -1), (0.80, 1)):
        i = int(t_leg * n)
        x, y = body[i]
        nx, ny, tx, ty = nm[i]
        w = widths[i]
        k = -side
        knee = (x + nx * w * 0.9 * k + tx * w * 0.6, y + ny * w * 0.9 * k + ty * w * 0.6)
        foot = (knee[0] + nx * w * 0.6 * k - tx * w * 0.5, knee[1] + ny * w * 0.6 * k - ty * w * 0.5)
        stroke(d, catmull([(x, y), knee, foot], 12), w * 0.42, w * 0.22)
        for c in range(4):
            a = math.atan2(ny * k, nx * k) + (c - 1.5) * 0.55
            cl = w * 0.45
            p1 = (foot[0] + math.cos(a) * cl, foot[1] + math.sin(a) * cl)
            p2 = (p1[0] + math.cos(a + 0.9) * cl * 0.45, p1[1] + math.sin(a + 0.9) * cl * 0.45)
            stroke(d, [foot, p1, p2], w * 0.12, 2 * s)
        # elbow flame tufts
        for f in range(3):
            a = math.atan2(-ty, -tx) + (f - 1) * 0.35
            p = (knee[0] + math.cos(a) * w * 0.55, knee[1] + math.sin(a) * w * 0.55)
            stroke(d, [knee, p], w * 0.14, 2 * s)
    # head
    hx, hy = body[0]
    head = P([(640, 250), (700, 200), (770, 185), (835, 205), (850, 235), (800, 250),
              (840, 268), (815, 300), (760, 290), (700, 300)])
    d.polygon(head, fill=255)
    d.ellipse([hx - 70 * s, hy - 60 * s, hx + 40 * s, hy + 45 * s], fill=255)
    # jaw gap / mouth
    d.line(P([(860, 250), (790, 262), (740, 262)]), fill=0, width=int(7 * s))
    # teeth
    for tx_ in range(745, 840, 18):
        d.polygon(P([(tx_, 255), (tx_ + 6, 270), (tx_ + 12, 255)]), fill=255)
    # eye
    ex, ey = 735 * s, 215 * s
    d.ellipse([ex - 16 * s, ey - 11 * s, ex + 16 * s, ey + 11 * s], fill=0)
    d.ellipse([ex - 6 * s, ey - 6 * s, ex + 6 * s, ey + 6 * s], fill=255)
    # horns
    stroke(d, catmull(P([(700, 200), (650, 140), (590, 110), (540, 120)]), 16), 22 * s, 6 * s)
    stroke(d, catmull(P([(725, 195), (700, 130), (660, 80), (610, 70)]), 16), 18 * s, 5 * s)
    # whiskers
    stroke(d, catmull(P([(850, 235), (900, 190), (930, 120), (900, 70), (860, 90)]), 20), 9 * s, 3 * s)
    stroke(d, catmull(P([(840, 275), (910, 320), (950, 400), (920, 450)]), 20), 9 * s, 3 * s)
    # mane flames
    for k in range(7):
        a = math.radians(150 + k * 22)
        base = (hx + 15 * s, hy + 10 * s)
        tip = (base[0] + math.cos(a) * 120 * s, base[1] + math.sin(a) * 120 * s)
        mid = (base[0] + math.cos(a + 0.3) * 60 * s, base[1] + math.sin(a + 0.3) * 60 * s)
        stroke(d, catmull([base, mid, tip], 12), 26 * s, 3 * s)
    # tail flame
    tx_, ty_ = body[-1]
    for k in range(5):
        a = math.radians(120 + k * 22)
        stroke(d, catmull([(tx_, ty_), (tx_ + math.cos(a) * 50 * s, ty_ + math.sin(a) * 40 * s + 30 * s),
                           (tx_ + math.cos(a) * 110 * s, ty_ + math.sin(a) * 70 * s + 60 * s)], 10), 22 * s, 3 * s)
    # flaming pearl
    d.ellipse(P([(880, 520), (960, 600)]), fill=255)
    d.ellipse(P([(898, 538), (942, 582)]), fill=0)
    d.ellipse(P([(908, 548), (932, 572)]), fill=255)
    for k in range(5):
        a = math.radians(-60 - k * 30)
        stroke(d, catmull(P([(920, 560), (920 + math.cos(a) * 70, 560 + math.sin(a) * 70),
                             (920 + math.cos(a + 0.4) * 110, 560 + math.sin(a + 0.4) * 110)]), 10), 14 * s, 2 * s)
    # clouds
    for (cx, cy, sc) in ((130, 230, 70), (160, 560, 60), (820, 820, 70), (520, 930, 55), (800, 420, 45)):
        ruyi_cloud(d, cx * s, cy * s, sc * s)
    im = im.filter(ImageFilter.GaussianBlur(1.2 * s)).point(lambda v: 255 if v > 110 else 0)
    im = im.filter(ImageFilter.GaussianBlur(0.8))
    save(im, "dragon_emblem.png")
    save(im.filter(ImageFilter.GaussianBlur(4 * s)), "dragon_emblem_height.png")


# ----------------------------------------------------------------------------
# 2. Mon crests
# ----------------------------------------------------------------------------
def ring(d, S, r_out, r_in):
    c = S / 2
    d.ellipse([c - r_out, c - r_out, c + r_out, c + r_out], fill=255)
    d.ellipse([c - r_in, c - r_in, c + r_in, c + r_in], fill=0)


def make_mon_kanji(S=1024):
    """Chest crest: ring + brush kanji 影 (kage)."""
    im = Image.new("L", (S, S), 0)
    d = ImageDraw.Draw(im)
    ring(d, S, S * 0.48, S * 0.405)
    ring(d, S, S * 0.385, S * 0.37)
    g = glyph("影", int(S * 0.62), "shippori-mincho-b1")
    paste_center(im, g, S / 2, S / 2)
    im = im.filter(ImageFilter.GaussianBlur(1.0))
    save(im, "mon_chest.png")


def make_mon_bird(S=1024):
    """Back-banner crest: ring + spread-winged hawk (in the style of a kamon)."""
    im = Image.new("L", (S, S), 0)
    d = ImageDraw.Draw(im)
    ring(d, S, S * 0.48, S * 0.43)
    c = S / 2

    def feather(cx, cy, ang, length, width):
        pts = []
        for i in range(40):
            t = i / 39
            w = width * math.sin(math.pi * min(1, t * 1.15)) * (1 - 0.3 * t)
            pts.append((t * length, w))
        pts += [(t, -w) for t, w in reversed(pts)]
        ca, sa = math.cos(ang), math.sin(ang)
        d.polygon([(cx + x * ca - y * sa, cy + x * sa + y * ca) for x, y in pts], fill=255)
        # quill line
        d.line([cx, cy, cx + length * 0.85 * ca, cy + length * 0.85 * sa], fill=0, width=max(2, int(S * 0.004)))

    # wings: two fans
    for side in (-1, 1):
        sx = c + side * S * 0.06
        sy = c - S * 0.02
        for k in range(6):
            a = math.radians(-90 + side * (35 + k * 17))
            feather(sx, sy, a, S * (0.33 - 0.022 * k), S * 0.045)
    # tail fan
    for k in range(5):
        a = math.radians(90 + (k - 2) * 14)
        feather(c, c + S * 0.08, a, S * 0.24, S * 0.035)
    # body + head
    d.ellipse([c - S * 0.075, c - S * 0.13, c + S * 0.075, c + S * 0.14], fill=255)
    d.ellipse([c - S * 0.05, c - S * 0.21, c + S * 0.05, c - S * 0.11], fill=255)
    d.polygon([(c - S * 0.012, c - S * 0.20), (c + S * 0.0, c - S * 0.25), (c + S * 0.03, c - S * 0.19)], fill=255)
    d.ellipse([c - S * 0.022, c - S * 0.18, c - S * 0.006, c - S * 0.164], fill=0)
    # breast feather marks
    for k in range(4):
        y = c - S * 0.06 + k * S * 0.045
        d.arc([c - S * 0.04, y - S * 0.02, c + S * 0.04, y + S * 0.02], 20, 160, fill=0, width=int(S * 0.006))
    im = distress(im.filter(ImageFilter.GaussianBlur(1.0)), 0.30, seed=11)
    save(im, "mon_bird.png")


def make_mon_flower(S=512):
    """Small kikyo (bellflower) crest used on hat finial, knee plates, pouch studs."""
    im = Image.new("L", (S, S), 0)
    d = ImageDraw.Draw(im)
    ring(d, S, S * 0.48, S * 0.42)
    petal_flower(d, S / 2, S / 2, S * 0.36, 5, 255, 0)
    im = im.filter(ImageFilter.GaussianBlur(0.8))
    save(im, "mon_flower.png")


# ----------------------------------------------------------------------------
# 3. Tileable faded gold print for black cloth
# ----------------------------------------------------------------------------
KANJI = list("影武者忠義生死守天闇静月風炎魂道誠勇仁礼忍隠")


def make_cloth_print(S=1024, name="cloth_print.png", density=1.0, seed=3, kanji_ratio=0.45):
    r = random.Random(seed)
    im = Image.new("L", (S, S), 0)
    d = ImageDraw.Draw(im)
    pts = []
    tries = 0
    count = int(26 * density)
    while len(pts) < count and tries < 5000:
        tries += 1
        x, y = r.random() * S, r.random() * S
        ok = True
        for (px, py) in pts:
            dx = min(abs(px - x), S - abs(px - x))
            dy = min(abs(py - y), S - abs(py - y))
            if dx * dx + dy * dy < (S * 0.15 / math.sqrt(density)) ** 2:
                ok = False
                break
        if ok:
            pts.append((x, y))
    for (x, y) in pts:
        kind = r.random()
        if kind < kanji_ratio:
            g = glyph(r.choice(KANJI), int(S * r.uniform(0.07, 0.11)))
            g = g.rotate(r.uniform(-12, 12), expand=True, resample=Image.BICUBIC)
            paste_center(im, g, x, y, wrap=True)
        elif kind < kanji_ratio + 0.25:
            tile = Image.new("L", (int(S * 0.2), int(S * 0.2)), 0)
            petal_flower(ImageDraw.Draw(tile), tile.width / 2, tile.height / 2, tile.width * r.uniform(0.25, 0.4),
                         r.choice((5, 5, 6, 8)), 255, 0, rot=r.uniform(0, 360))
            paste_center(im, tile, x, y, wrap=True)
        else:
            tile = Image.new("L", (int(S * 0.3), int(S * 0.2)), 0)
            ruyi_cloud(ImageDraw.Draw(tile), tile.width * 0.4, tile.height * 0.45, tile.width * 0.17)
            paste_center(im, tile, x, y, wrap=True)
    im = distress(im, 0.38, seed=seed + 100)
    save(im, name)


# ----------------------------------------------------------------------------
# 4. Front apron (maedare) panel artwork
# ----------------------------------------------------------------------------
def make_apron(W=512, H=1280):
    im = Image.new("L", (W, H), 0)
    d = ImageDraw.Draw(im)
    # double border lines
    for inset, w in ((10, 8), (30, 3)):
        d.rectangle([inset, inset, W - inset, H + 50], outline=255, width=w)
    g = glyph("忠", int(W * 0.5))
    paste_center(im, g, W / 2, H * 0.17)
    tile = Image.new("L", (W, W), 0)
    petal_flower(ImageDraw.Draw(tile), W / 2, W / 2, W * 0.33, 5, 255, 0)
    paste_center(im, tile, W / 2, H * 0.42)
    g = glyph("義", int(W * 0.46))
    paste_center(im, g, W / 2, H * 0.66)
    for k in range(3):
        cl = Image.new("L", (W, W // 2), 0)
        ruyi_cloud(ImageDraw.Draw(cl), W * 0.4, W * 0.22, W * 0.12)
        paste_center(im, cl, W / 2 + (k - 1) * W * 0.25, H * 0.84 + (k % 2) * 40)
    im = distress(im, 0.33, seed=21)
    save(im, "apron_print.png")


# ----------------------------------------------------------------------------
# 5. Back banner: bird crest on top + vertical kanji column
# ----------------------------------------------------------------------------
def make_banner(W=512, H=2048):
    im = Image.new("L", (W, H), 0)
    d = ImageDraw.Draw(im)
    crest = Image.open(os.path.join(OUT, "mon_bird.png")).resize((int(W * 0.80), int(W * 0.80)), Image.LANCZOS)
    crest = crest.point(lambda v: min(255, int(v * 1.6)))
    im.paste(crest, (int(W * 0.10), int(H * 0.27)))
    y = H * 0.58
    for ch in "影武者":
        g = glyph(ch, int(W * 0.48))
        paste_center(im, g, W * 0.5, y)
        y += W * 0.50
    # (no side rule lines: seen edge-on from the side views they read as a pale stripe)
    im = distress(im, 0.22, seed=31)
    save(im, "banner_print.png")


def make_fabric_panel(W=1024, H=1024):
    """Wide sash cloth seen in the 'Fabric & Pattern' detail: kanji column + big crest."""
    im = Image.new("L", (W, H), 0)
    y = H * 0.16
    for ch in "忠義生":
        g = glyph(ch, int(W * 0.16))
        paste_center(im, g, W * 0.13, y)
        y += W * 0.27
    crest = Image.open(os.path.join(OUT, "mon_bird.png")).resize((int(W * 0.64), int(W * 0.64)), Image.LANCZOS)
    im.paste(255, (int(W * 0.30), int(H * 0.18)), crest)
    im = distress(im, 0.28, seed=41)
    save(im, "fabric_panel.png")


def make_panel_print(W=512, H=1536):
    """Front-left hanging panel: big gilt flowers + scrollwork + border (as on the concept's front)."""
    im = Image.new("L", (W, H), 0)
    d = ImageDraw.Draw(im)
    d.rectangle([12, 12, W - 12, H + 40], outline=255, width=10)
    d.rectangle([34, 34, W - 34, H + 40], outline=255, width=3)
    r = random.Random(77)
    y = H * 0.10
    k = 0
    while y < H * 0.95:
        if k % 3 == 1:
            g = glyph(r.choice(KANJI), int(W * 0.42))
            paste_center(im, g, W / 2, y)
            y += W * 0.55
        else:
            tile = Image.new("L", (W, W), 0)
            td = ImageDraw.Draw(tile)
            petal_flower(td, W / 2, W / 2, W * 0.30, r.choice((5, 6, 8)), 255, 0, rot=r.uniform(0, 90))
            for q in range(4):
                a = q * math.pi / 2 + 0.6
                cloud_swirl(td, W / 2 + math.cos(a) * W * 0.33, W / 2 + math.sin(a) * W * 0.33, W * 0.08, 7, 1.5,
                            255, 1 if q % 2 else -1)
            paste_center(im, tile, W / 2, y)
            y += W * 0.85
        k += 1
    im = distress(im, 0.30, seed=88)
    save(im, "panel_print.png")


# ----------------------------------------------------------------------------
# 6. Lamellar row band (kusazuri / sode lower lames)
# ----------------------------------------------------------------------------
def make_lamellar(W=1024, H=192):
    im = Image.new("L", (W, H), 0)
    d = ImageDraw.Draw(im)
    n = 13
    r = random.Random(5)
    for i in range(n):
        cx = (i + 0.5) * W / n
        if i % 2 == 0:
            g = glyph(r.choice(KANJI), int(H * 0.38))
            paste_center(im, g, cx, H / 2)
        else:
            tile = Image.new("L", (int(H * 0.55), int(H * 0.55)), 0)
            petal_flower(ImageDraw.Draw(tile), tile.width / 2, tile.height / 2, tile.width * 0.36, 4, 255, 0, rot=45)
            paste_center(im, tile, cx, H / 2)
        # lacing holes (dark) along top & bottom
        for yy in (16, H - 22):
            d.ellipse([cx - 5, yy - 4, cx + 5, yy + 4], fill=0)
    im = distress(im, 0.30, seed=51)
    save(im, "lamellar_band.png")


# ----------------------------------------------------------------------------
# 7. Smoke bomb kanji wrap (equirectangular)
# ----------------------------------------------------------------------------
def make_smokebomb(W=1024, H=512):
    im = Image.new("L", (W, H), 0)
    d = ImageDraw.Draw(im)
    for i, ch in enumerate("煙雷爆"):
        g = glyph(ch, int(H * 0.42))
        g = g.resize((int(g.width * 0.75), g.height), Image.LANCZOS)
        paste_center(im, g, (i + 0.5) * W / 3, H * 0.53)
    d.rectangle([0, int(H * 0.08), W, int(H * 0.11)], fill=255)
    im = distress(im, 0.12, seed=61)
    save(im, "smokebomb_kanji.png")


# ----------------------------------------------------------------------------
# 8. Hat glyph marks (polar: u = angle, v = radius)
# ----------------------------------------------------------------------------
def make_hat(W=2048, H=512):
    im = Image.new("L", (W, H), 0)
    r = random.Random(9)
    ribs = 48
    for k in range(ribs):
        for row in range(3):
            if r.random() < 0.6:
                continue
            cx = (k + 0.5) * W / ribs
            cy = H * (0.35 + 0.22 * row) + r.uniform(-10, 10)
            g = glyph(r.choice(KANJI), int(W / ribs * 0.85))
            g = g.rotate(90, expand=True)
            paste_center(im, g, cx, cy, wrap=True)
    # concentric gilt rings
    d = ImageDraw.Draw(im)
    im = distress(im, 0.35, seed=71)
    save(im, "hat_glyphs.png")


# ----------------------------------------------------------------------------
# 9. Bracer (kote) panel ornament
# ----------------------------------------------------------------------------
def make_bracer(W=256, H=1024):
    im = Image.new("L", (W, H), 0)
    fil = Image.open(os.path.join(OUT, "filigree.png")).resize((W, W))
    for yy in range(0, H, W):
        im.paste(fil.point(lambda v: int(v * 0.8)), (0, yy))
    d = ImageDraw.Draw(im)
    d.rectangle([8, 8, W - 8, H - 8], outline=255, width=7)
    d.rectangle([22, 22, W - 22, H - 22], outline=255, width=2)
    dr = Image.open(os.path.join(OUT, "dragon_emblem.png")).rotate(90, expand=True).resize((int(W * 0.8), int(W * 0.8 * 1.0)))
    for k, cy in enumerate((0.25, 0.75)):
        tile = Image.new("L", (W, W), 0)
        petal_flower(ImageDraw.Draw(tile), W / 2, W / 2, W * 0.3, 8, 255, 0)
        paste_center(im, tile, W / 2, H * cy)
    g = glyph("忍", int(W * 0.5))
    paste_center(im, g, W / 2, H * 0.5)
    for y in range(60, H - 60, 64):
        d.ellipse([W / 2 - 4 - W * 0.36, y - 4, W / 2 + 4 - W * 0.36, y + 4], fill=255)
        d.ellipse([W / 2 - 4 + W * 0.36, y - 4, W / 2 + 4 + W * 0.36, y + 4], fill=255)
    im = distress(im, 0.28, seed=81)
    save(im, "bracer_panel.png")


# ----------------------------------------------------------------------------
# 10. Shin guard (suneate) splint ornament
# ----------------------------------------------------------------------------
def make_suneate(W=256, H=1024):
    im = Image.new("L", (W, H), 0)
    d = ImageDraw.Draw(im)
    d.rectangle([6, 6, W - 6, H - 6], outline=255, width=5)
    fil = Image.open(os.path.join(OUT, "filigree.png")).resize((W, W))
    for yy in range(0, H, W):
        im.paste(fil, (0, yy))
    r = random.Random(13)
    y = 120
    while y < H - 80:
        if r.random() < 0.5:
            g = glyph(r.choice(KANJI), int(W * 0.42))
            paste_center(im, g, W / 2, y)
        else:
            tile = Image.new("L", (W, W), 0)
            ruyi_cloud(ImageDraw.Draw(tile), W * 0.4, W * 0.45, W * 0.13)
            paste_center(im, tile, W / 2, y)
        y += 170
    im = distress(im, 0.22, seed=91)
    save(im, "suneate_panel.png")


# ----------------------------------------------------------------------------
# 11. Stitch / leather tooling for pouches
# ----------------------------------------------------------------------------
def make_pouch(S=512):
    im = Image.new("L", (S, S), 0)
    d = ImageDraw.Draw(im)
    for inset in (20,):
        for x in range(inset, S - inset, 14):
            d.line([x, inset, x + 7, inset], fill=255, width=3)
            d.line([x, S - inset, x + 7, S - inset], fill=255, width=3)
        for y in range(inset, S - inset, 14):
            d.line([inset, y, inset, y + 7], fill=255, width=3)
            d.line([S - inset, y, S - inset, y + 7], fill=255, width=3)
    tile = Image.new("L", (S // 2, S // 2), 0)
    ruyi_cloud(ImageDraw.Draw(tile), S * 0.18, S * 0.12, S * 0.07, width=6)
    paste_center(im, tile, S / 2, S * 0.30)
    save(im, "pouch_tooling.png")


# ----------------------------------------------------------------------------
# 12. Karakusa scrollwork (engraved gilt filigree for the cuirass / plates)
# ----------------------------------------------------------------------------
def make_filigree(S=1024, name="filigree.png", seed=17, density=1.7):
    r = random.Random(seed)
    big = Image.new("L", (S * 3, S * 3), 0)
    d = ImageDraw.Draw(big)
    centers = []
    n = int(14 * density)
    tries = 0
    while len(centers) < n and tries < 4000:
        tries += 1
        x, y = r.random() * S, r.random() * S
        if all(min(abs(x - a), S - abs(x - a)) ** 2 + min(abs(y - b), S - abs(y - b)) ** 2 > (S * 0.2) ** 2
               for a, b in centers):
            centers.append((x, y))
    elems = []
    for (x, y) in centers:
        rad = S * r.uniform(0.05, 0.08)
        dirn = r.choice((-1, 1))
        rot = r.uniform(0, math.tau)
        pts = []
        for i in range(70):
            t = i / 69
            a = rot + dirn * t * 2.4 * math.pi
            rr = rad * (1 - 0.85 * t)
            pts.append((x + rr * math.cos(a), y + rr * math.sin(a)))
        elems.append(("spiral", pts))
        # vine leaving the spiral toward a neighbour
        nb = min((c for c in centers if c != (x, y)),
                 key=lambda c: min(abs(c[0] - x), S - abs(c[0] - x)) ** 2 + min(abs(c[1] - y), S - abs(c[1] - y)) ** 2)
        tx = nb[0] if abs(nb[0] - x) < S / 2 else nb[0] + (S if nb[0] < x else -S)
        ty = nb[1] if abs(nb[1] - y) < S / 2 else nb[1] + (S if nb[1] < y else -S)
        sx, sy = pts[0]
        mx, my = (sx + tx) / 2 + r.uniform(-1, 1) * S * 0.06, (sy + ty) / 2 + r.uniform(-1, 1) * S * 0.06
        vine = catmull([(sx, sy), (mx, my), (tx, ty)], 30)
        elems.append(("vine", vine))
        # leaves along the vine
        for k in range(4, len(vine) - 4, 9):
            vx, vy = vine[k]
            ax, ay = vine[k + 1][0] - vine[k - 1][0], vine[k + 1][1] - vine[k - 1][1]
            l = math.hypot(ax, ay) or 1
            nx_, ny_ = -ay / l, ax / l
            side = 1 if (k // 9) % 2 else -1
            L = S * 0.03
            tip = (vx + nx_ * L * side + ax / l * L * 0.6, vy + ny_ * L * side + ay / l * L * 0.6)
            elems.append(("leaf", (vx, vy, tip)))
    for ox in (0, S, 2 * S):
        for oy in (0, S, 2 * S):
            for kind, data in elems:
                if kind == "spiral":
                    stroke(d, [(px + ox, py + oy) for px, py in data], S * 0.012, S * 0.005)
                elif kind == "vine":
                    stroke(d, [(px + ox, py + oy) for px, py in data], S * 0.008, S * 0.008)
                else:
                    vx, vy, tip = data
                    mx, my = (vx + tip[0]) / 2, (vy + tip[1]) / 2
                    dx, dy = tip[0] - vx, tip[1] - vy
                    d.polygon([(vx + ox, vy + oy), (mx - dy * 0.3 + ox, my + dx * 0.3 + oy), (tip[0] + ox, tip[1] + oy),
                               (mx + dy * 0.3 + ox, my - dx * 0.3 + oy)], fill=255)
    im = big.crop((S, S, 2 * S, 2 * S))
    im = distress(im, 0.30, seed=seed + 5)
    save(im, name)


if __name__ == "__main__":
    make_filigree()
    make_filigree(1024, "filigree_sparse.png", seed=23, density=0.6)
    make_dragon()
    make_mon_kanji()
    make_mon_bird()
    make_mon_flower()
    make_cloth_print()
    make_cloth_print(1024, "cloth_print_sparse.png", density=0.45, seed=4)
    make_apron()
    make_panel_print()
    make_banner()
    make_fabric_panel()
    make_lamellar()
    make_smokebomb()
    make_hat()
    make_bracer()  # needs filigree.png
    make_suneate()  # needs filigree.png (generated first)
    make_pouch()
