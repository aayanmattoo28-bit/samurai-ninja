"""Procedural textures for the Navy SEAL build (written to navy-seal/textures).

    python navy-seal/tools/make_seal_textures.py
"""
import os

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(os.path.dirname(HERE), "textures")


def save(arr_or_img, name):
    os.makedirs(OUT, exist_ok=True)
    img = arr_or_img
    if isinstance(arr_or_img, np.ndarray):
        img = Image.fromarray((np.clip(arr_or_img, 0, 1) * 255).astype(np.uint8))
    path = os.path.join(OUT, name)
    img.save(path)
    print("wrote", path, img.size)


def periodic_noise(S, cutoff, seed, power=2.0):
    """Tileable smooth noise: band-limited white noise via FFT (periodic by construction)."""
    rng = np.random.default_rng(seed)
    w = rng.standard_normal((S, S))
    f = np.fft.fft2(w)
    ky = np.fft.fftfreq(S)[:, None] * S
    kx = np.fft.fftfreq(S)[None, :] * S
    k = np.sqrt(kx * kx + ky * ky)
    filt = np.exp(-(k / cutoff) ** 2) if power is None else 1.0 / (1.0 + (k / cutoff) ** power)
    n = np.real(np.fft.ifft2(f * filt))
    n = (n - n.mean()) / (n.std() + 1e-9)
    return n


def make_suit_camo(S=2048):
    """Black 'tiger-line' camouflage of the drysuit: organic contour lines (R) and soft blotches (G).

    The concept suit is near-black with thin grey linework that follows wavy contours and breaks up,
    plus slightly lighter charcoal blotches."""
    # the texture tiles over ~0.8 m of fabric: contour spacing ~1-2.5 cm, line width ~3 mm
    base = periodic_noise(S, 5.0, 11, None)
    warp = periodic_noise(S, 11.0, 12, None)
    field = base + 0.30 * warp
    gy, gx = np.gradient(field)
    g = np.sqrt(gx * gx + gy * gy) + 1e-6
    f = field * 5.5
    d = np.abs(f - np.round(f)) / (g * 5.5)  # distance to the nearest contour in pixels
    lines = np.exp(-(d / 4.2) ** 2)
    # break the lines up so they read as printed linework, not a topographic map
    breakup = periodic_noise(S, 18.0, 13, None)
    lines *= np.clip((breakup + 0.6) * 1.2, 0, 1)
    fine = periodic_noise(S, 60.0, 14, 2.0)
    lines = np.clip(lines * (0.75 + 0.25 * fine), 0, 1)
    blot = periodic_noise(S, 5.0, 15, None)
    blot = np.clip((blot - 0.3) * 1.6, 0, 1)
    rgb = np.zeros((S, S, 3), np.float32)
    rgb[..., 0] = lines
    rgb[..., 1] = blot
    rgb[..., 2] = np.clip(fine * 0.5 + 0.5, 0, 1)
    save(rgb, "suit_camo.png")


def make_flag_subdued(W=600, H=396):
    """Subdued US flag patch as drawn on the concept: slate canton with dim stars, warm cream and brick stripes,
    dark merrowed border (sRGB colour image)."""
    cream, brick, slate, star, border = (173, 162, 155), (60, 41, 39), (43, 47, 58), (110, 112, 120), (21, 21, 26)
    im = Image.new("RGB", (W, H), border)
    d = ImageDraw.Draw(im)
    b = 10
    sh = (H - 2 * b) / 13
    for k in range(13):
        d.rectangle([b, b + k * sh, W - b, b + (k + 1) * sh], fill=brick if k % 2 == 0 else cream)
    cw, ch = (W - 2 * b) * 0.45, sh * 7
    d.rectangle([b, b, b + cw, b + ch], fill=slate)
    for r in range(9):
        n = 6 if r % 2 == 0 else 5
        for c in range(n):
            x = b + cw * (c + (0.5 if r % 2 == 0 else 1.0)) / 6.0
            y = b + ch * (r + 0.5) / 9.0
            rr = sh * 0.22
            d.ellipse([x - rr, y - rr, x + rr, y + rr], fill=star)
    im = im.filter(ImageFilter.GaussianBlur(1.0))
    os.makedirs(OUT, exist_ok=True)
    im.save(os.path.join(OUT, "flag_subdued.png"))
    print("wrote flag_subdued.png", im.size)


def make_webbing(S=512):
    """Nylon webbing weave (tileable): fine basket weave with a few ribs, used as bump/colour variation."""
    y, x = np.mgrid[0:S, 0:S] / S
    warp = 0.5 + 0.5 * np.sin(x * 2 * np.pi * 96)
    weft = 0.5 + 0.5 * np.sin(y * 2 * np.pi * 64)
    chk = (np.floor(x * 96) + np.floor(y * 64)) % 2
    v = np.where(chk > 0, warp, weft) * 0.8 + 0.2 * periodic_noise(S, 40.0, 21, 2.0) * 0.5
    save((v - v.min()) / (v.max() - v.min()), "webbing.png")


def make_wrist_hud(W=512, H=410):
    """Wrist-computer HUD: navy-teal screen, battery capsule, 4-bar graph with a label block, right glyph column,
    divider at 2/3 height, a bottom row of dashes and a bright dot at the top-right."""
    bg, fg = (43, 71, 96), (166, 202, 233)
    im = Image.new("RGB", (W, H), bg)
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([30, 60, 110, 230], radius=22, outline=fg, width=8)
    d.rectangle([58, 44, 82, 60], fill=fg)
    for k, frac in enumerate((0.3, 0.55, 0.75, 0.95)):
        d.rectangle([60, 230 - int(160 * frac * 0.95) + 10, 80, 220], fill=fg) if k == 3 else None
    for k, hgt in enumerate((60, 110, 85, 140)):
        x0 = 165 + k * 50
        d.rectangle([x0, 250 - hgt, x0 + 32, 250], fill=fg)
    d.rectangle([165, 40, 330, 70], fill=fg)
    d.rectangle([370, 50, 392, 110], fill=fg)
    d.rectangle([370, 110, 420, 130], fill=fg)
    for k in range(3):
        d.ellipse([380, 160 + k * 40, 398, 178 + k * 40], fill=fg)
    d.ellipse([462, 22, 486, 46], fill=(220, 240, 255))
    d.line([20, 275, W - 20, 275], fill=fg, width=4)
    for k in range(7):
        d.rectangle([30 + k * 66, 310, 30 + k * 66 + 40 + (k % 3) * 6, 330], fill=fg)
    d.rectangle([30, 352, 260, 368], fill=fg)
    im = im.filter(ImageFilter.GaussianBlur(1.2))
    os.makedirs(OUT, exist_ok=True)
    im.save(os.path.join(OUT, "wrist_hud.png"))
    print("wrote wrist_hud.png", im.size)


def make_dive_screen(W=480, H=400):
    """Chest dive-computer readout: dark glass with two rows of dim pixel glyphs (reads like 'PSS' and numerals)."""
    im = Image.new("RGB", (W, H), (18, 24, 31))
    d = ImageDraw.Draw(im)
    fg = (196, 215, 231)
    font = {"P": ["111", "101", "111", "100", "100"], "S": ["111", "100", "111", "001", "111"],
            "1": ["010", "110", "010", "010", "111"], "2": ["111", "001", "111", "100", "111"],
            "7": ["111", "001", "010", "010", "010"], "4": ["101", "101", "111", "001", "001"],
            "0": ["111", "101", "101", "101", "111"], ".": ["000", "000", "000", "000", "010"]}

    def text(s, x, y, px):
        for ch in s:
            for r, row in enumerate(font[ch]):
                for c, bit in enumerate(row):
                    if bit == "1":
                        d.rectangle([x + c * px, y + r * px, x + c * px + px - 2, y + r * px + px - 2], fill=fg)
            x += 4 * px

    text("PSS", 40, 70, 22)
    text("12.47", 40, 230, 18)
    d.rectangle([340, 90, 440, 110], fill=(120, 150, 175))
    im = im.filter(ImageFilter.GaussianBlur(1.0))
    im.save(os.path.join(OUT, "dive_screen.png"))
    print("wrote dive_screen.png", im.size)


if __name__ == "__main__":
    make_suit_camo()
    make_flag_subdued()
    make_webbing()
    make_wrist_hud()
    make_dive_screen()
