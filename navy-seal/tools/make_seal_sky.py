"""Backdrop sky for the one-shot turnaround, colour-matched to the concept sheet's harbour panorama.

    python navy-seal/tools/make_seal_sky.py path/to/concept_sheet.png [--preview out.png]

The concept's turnaround panel (sheet px 0-1144 x 0-634) is the reference.  Everything that is modelled in 3D or is
not sky is masked out of it -- the four figures, the title/text overlay, the submarine, patrol boat, crane, warship,
helicopter, mountains and everything below the horizon -- and the holes are filled smoothly from the surrounding
sky (normalised convolution, coarse to fine), then the dark stormy slate is restored under the title block.  What
is left is the overcast dusk sky with its cloud masses, the low fog band and the peach glow, which the set shows on
an emission card 8 km behind the harbour (seal_scene.SKY_*).

The image is stored as the scene-linear radiance the renderer needs to reproduce the sheet's display colours:
the display -> linear curve is measured by rendering a grey ramp through the scene's own colour pipeline (AgX look,
colour balance; no glare or vignette), and the compositor vignette is divided out.  Values are written
gamma-encoded (Non-Color, linear = SKY_GAIN * texture ** SKY_GAMMA) so the darks keep their precision in 8 bits.
"""
import os
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
OUT = os.path.join(os.path.dirname(HERE), "textures")

PW, PH = 1144, 634                       # turnaround panel in sheet px
HORIZON = 505                            # sky rows end here (fog band included)
FIG_X = ((150, 440), (440, 636), (628, 876), (918, 1110))


def srgb_to_lin(c):
    c = np.clip(c, 0.0, 1.0)
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def lin_to_srgb(c):
    c = np.clip(c, 0.0, None)
    return np.where(c <= 0.0031308, c * 12.92, 1.055 * np.power(c, 1 / 2.4) - 0.055)


def box_blur(a, r, axis):
    """Box blur of radius r along an axis (edge-clamped), via cumulative sums."""
    if r < 1:
        return a
    pad = [(0, 0)] * a.ndim
    pad[axis] = (r + 1, r)
    p = np.pad(a, pad, mode="edge")
    c = np.cumsum(p, axis=axis)
    n = a.shape[axis]
    hi = np.take(c, np.arange(2 * r + 1, 2 * r + 1 + n), axis=axis)
    lo = np.take(c, np.arange(0, n), axis=axis)
    return (hi - lo) / (2 * r + 1)


def blur(a, r):
    """Approximate gaussian (three box passes per axis)."""
    r = int(max(1, round(r / 1.7)))
    for axis in (0, 1):
        for _ in range(3):
            a = box_blur(a, r, axis)
    return a


def fill(img, valid):
    """Fill invalid pixels smoothly (pull-push pyramid): average the valid sky down to coarse levels, then blend
    the coarse colours back up wherever a level had no valid pixels, so holes get a soft membrane-like fill."""
    levels = []
    c = img * valid[..., None]
    w = valid.astype(np.float32)
    while True:
        levels.append((c, w))
        if max(w.shape) <= 1:          # down to the global mean, so every cell has some colour
            break
        h2, w2 = (w.shape[0] + 1) // 2 * 2, (w.shape[1] + 1) // 2 * 2
        cp = np.pad(c, ((0, h2 - c.shape[0]), (0, w2 - c.shape[1]), (0, 0)), mode="edge")
        wp = np.pad(w, ((0, h2 - w.shape[0]), (0, w2 - w.shape[1])), mode="edge")
        c = cp.reshape(h2 // 2, 2, w2 // 2, 2, 3).sum(axis=(1, 3))
        w = wp.reshape(h2 // 2, 2, w2 // 2, 2).sum(axis=(1, 3))
    # normalise each level to mean colour + clipped coverage
    norm = [(cc / np.maximum(ww, 1e-6)[..., None], np.clip(ww, 0, 1)) for cc, ww in levels]
    up = norm[-1][0]
    for col, cov in reversed(norm[:-1]):
        H, W = cov.shape
        im = [Image.fromarray(np.ascontiguousarray(up[..., k], dtype=np.float32), mode="F").resize((W, H), Image.BILINEAR)
              for k in range(3)]
        upc = np.stack([np.asarray(t) for t in im], axis=-1)
        up = col * cov[..., None] + upc * (1 - cov[..., None])
    return np.where(valid[..., None], img, up)


def figure_mask(lum):
    """Dark figure silhouettes inside each figure's measured x-extent: threshold, close, fill holes, dilate."""
    m = np.zeros(lum.shape, bool)
    for x0, x1 in FIG_X:
        m[:626, x0:x1] |= lum[:626, x0:x1] < 0.115
    im = Image.fromarray((m * 255).astype(np.uint8))
    im = im.filter(ImageFilter.MaxFilter(9)).filter(ImageFilter.MinFilter(9))       # close small gaps
    ext = im.copy()
    ImageDraw.floodfill(ext, (600, 2), 128)                                          # outside (sky) region
    ext = np.asarray(ext)
    solid = ext != 128                                                               # figure + enclosed holes
    im = Image.fromarray((solid * 255).astype(np.uint8)).filter(ImageFilter.MaxFilter(11))
    return np.asarray(im) > 127


def object_mask():
    """Everything the set builds in 3D (or that is sheet graphics), as polygons in sheet px."""
    im = Image.new("L", (PW, PH), 0)
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, 272, 382], fill=255)                                          # title block + text panel
    for x0, x1, y1 in ((262, 360, 45), (366, 382, 130), (462, 590, 45), (598, 640, 75), (700, 800, 45),
                       (804, 818, 115), (985, 1102, 45)):                            # helmet tops, antennas, muzzle
        d.rectangle([x0, 0, x1, y1], fill=255)
    d.polygon([(8, 545), (8, 410), (40, 400), (80, 362), (96, 336), (116, 336), (126, 362), (140, 420),
               (176, 440), (180, 545)], fill=255)                                    # submarine
    d.rectangle([378, 352, 508, 548], fill=255)                                      # patrol boat + small craft
    d.rectangle([606, 426, 676, 528], fill=255)                                      # crane and block
    d.polygon([(706, 530), (706, 462), (760, 436), (830, 420), (884, 392), (884, 128), (916, 128), (916, 318),
               (1144, 316), (1144, 530)], fill=255)                                  # warship, mast, far ship
    d.polygon([(808, 0), (1012, 0), (1012, 110), (990, 160), (850, 165), (808, 120)], fill=255)  # helicopter
    ridge = [(846, 340), (852, 226), (860, 216), (870, 211), (880, 203), (885, 200), (910, 196), (920, 191),
             (928, 188), (1100, 182), (1104, 180), (1112, 183), (1120, 186), (1128, 182), (1136, 177),
             (1144, 176), (1144, 340)]
    d.polygon(ridge, fill=255)                                                       # mountains
    d.rectangle([0, HORIZON, PW, PH], fill=255)                                      # dock, sea, surf
    return np.asarray(im) > 127


def vignette(x, y):
    """The compositor vignette (multiplier), in sheet px; seal_scene writes the same function as vignette.png."""
    u = (x - 572.0) / 572.0
    w = (y - 317.0) / 317.0
    r = np.sqrt(u * u + (w / 0.95) ** 2)
    corner = 0.28 * np.clip((r - 0.75) / 0.70, 0, 1) ** 1.6
    bottom = 0.30 * np.clip((w - 0.62) / 0.38, 0, 1) ** 1.5
    return 1.0 - corner - bottom


def sky_display(concept_path, window, scale):
    """Display-referred sRGB sky over the sheet window (x0, y0, x1, y1) at `scale` px per sheet px."""
    src = Image.open(concept_path).convert("RGB").crop((0, 0, PW, PH))
    a = np.asarray(src).astype(np.float32) / 255.0
    lum = a @ np.array([0.2126, 0.7152, 0.0722], np.float32)
    bad = figure_mask(lum) | object_mask()
    lin = srgb_to_lin(a)
    lin = fill(lin, ~bad)
    # stormy slate under the title block and text panel (the sheet only shows it through a dark overlay there)
    yy, xx = np.mgrid[0:PH, 0:PW].astype(np.float32)
    k = np.clip(1 - xx / 300.0, 0, 1) ** 1.3 * np.clip(1 - (yy - 300.0) / 120.0, 0, 1)
    slate = srgb_to_lin(np.array([0x1c, 0x2b, 0x3a], np.float32) / 255.0)
    lin = lin * (1 - 0.65 * k[..., None]) + slate * (0.65 * k[..., None])
    # light cloud texture where the sky was filled in, so the fill is not flat
    rng = np.random.default_rng(7)
    n = blur(rng.standard_normal((PH, PW)).astype(np.float32), 18)
    n = n / (np.abs(n).max() + 1e-6)
    lin *= (1 + 0.35 * n * bad)[..., None]
    lin = blur(lin, 1.2)
    # extend over the texture window (beyond the frame edges and below the horizon)
    x0, y0, x1, y1 = (int(round(c)) for c in window)
    W, H = int(round((x1 - x0) * scale)), int(round((y1 - y0) * scale))
    big = np.zeros((int(y1 - y0), int(x1 - x0), 3), np.float32)
    ok = np.zeros(big.shape[:2], bool)
    big[-y0:-y0 + PH, -x0:-x0 + PW] = lin
    ok[-y0:-y0 + PH, -x0:-x0 + PW] = True
    ok[-y0 + HORIZON + 15:, :] = False
    big = fill(big, ok)
    img = Image.fromarray((np.clip(lin_to_srgb(big), 0, 1) * 255).astype(np.uint8)).resize((W, H), Image.BICUBIC)
    return img


def grade_curve():
    """Measure display value vs scene-linear grey through the scene's colour pipeline (needs bpy)."""
    import bpy
    import seal_scene as S
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    S.setup_render(sc, calib=True)
    vals = np.geomspace(1e-4, 32.0, 96).astype(np.float32)
    im = bpy.data.images.new("ramp", len(vals), 1, float_buffer=True)
    px = np.ones((1, len(vals), 4), np.float32)
    px[0, :, :3] = vals[:, None]
    im.pixels.foreach_set(px.ravel())
    m = bpy.data.materials.new("ramp")
    m.use_nodes = True
    nt = m.node_tree
    for nd in list(nt.nodes):
        nt.nodes.remove(nd)
    tx = nt.nodes.new("ShaderNodeTexImage")
    tx.image = im
    tx.interpolation = "Closest"
    em = nt.nodes.new("ShaderNodeEmission")
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    nt.links.new(tx.outputs["Color"], em.inputs["Color"])
    nt.links.new(em.outputs[0], out.inputs["Surface"])
    bpy.ops.mesh.primitive_plane_add(size=2.0)
    pl = bpy.context.active_object
    pl.data.materials.append(m)
    cam = bpy.data.objects.new("c", bpy.data.cameras.new("c"))
    sc.collection.objects.link(cam)
    cam.data.type = "ORTHO"
    cam.data.ortho_scale = 2.0
    cam.location = (0, 0, 2)
    sc.camera = cam
    sc.render.resolution_x, sc.render.resolution_y = len(vals) * 8, 8
    sc.cycles.samples = 1
    sc.cycles.use_denoising = False
    sc.render.filter_size = 0.01
    sc.world = None
    path = os.path.join(OUT, "_grade_ramp.png")
    sc.render.filepath = path
    bpy.ops.render.render(write_still=True)
    r = np.asarray(Image.open(path).convert("RGB")).astype(np.float32) / 255.0
    os.remove(path)
    disp = r[4, 4::8, :]                                   # centre of each patch, per channel
    return vals, disp


def to_linear(display_srgb, curve, sat=0.88):
    """Invert the measured pipeline per channel; pre-compensate the compositor saturation."""
    vals, disp = curve
    out = np.empty_like(display_srgb)
    for c in range(3):
        d = np.maximum.accumulate(disp[:, c])
        out[..., c] = np.interp(display_srgb[..., c], d, vals)
    lum = out @ np.array([0.2126, 0.7152, 0.0722], np.float32)
    return np.clip(lum[..., None] + (out - lum[..., None]) / sat, 0.0, None)


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
    if not argv:
        print(__doc__)
        return
    concept = argv[0]
    preview = argv[argv.index("--preview") + 1] if "--preview" in argv else None
    import seal_scene as S
    x0, y0, x1, y1 = S.SKY_WINDOW
    disp = sky_display(concept, S.SKY_WINDOW, S.SKY_SCALE)
    if preview:
        disp.save(preview)
    d = np.asarray(disp).astype(np.float32) / 255.0
    H, W = d.shape[:2]
    ys = y0 + (np.arange(H) + 0.5) / S.SKY_SCALE
    xs = x0 + (np.arange(W) + 0.5) / S.SKY_SCALE
    vg = np.clip(vignette(xs[None, :], ys[:, None]), 0.4, 1.0)
    curve = grade_curve()
    lin = to_linear(d, curve) / vg[..., None]
    enc = np.clip(lin / S.SKY_GAIN, 0, 1) ** (1.0 / S.SKY_GAMMA)
    os.makedirs(OUT, exist_ok=True)
    Image.fromarray((enc * 255 + 0.5).astype(np.uint8)).save(os.path.join(OUT, "sky_backdrop.png"))
    v = vignette(*np.meshgrid(np.linspace(0, PW, 286), np.linspace(0, PH, 159)))
    Image.fromarray((np.clip(v, 0, 1) * 255 + 0.5).astype(np.uint8)).save(os.path.join(OUT, "vignette.png"))
    print("wrote sky_backdrop.png", (W, H), "lin range", float(lin.min()), float(lin.max()))


if __name__ == "__main__":
    main()
