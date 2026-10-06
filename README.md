# Kage Musha (影武者): samurai-ninja Blender model

A Blender reconstruction of the *Kage Musha* concept sheet: a samurai-ninja with a lacquered kasa,
hooded mask, dragon sode, engraved do, kote, kusazuri, printed tattered cloth, suneate, a full
weapon kit, and the Japanese castle courtyard backdrop.

**Blend file:** [`samurai-ninja_claude.blend`](samurai-ninja_claude.blend) (Blender 4.2+, textures packed)

**Rendered sheet:** [`renders/kage_musha_sheet.jpg`](renders/kage_musha_sheet.jpg) (individual panels in
[`renders/sheet/`](renders/sheet): turnaround, detail close-ups, item and weapon shots)

## What's in the .blend

| Collection | Contents |
|---|---|
| `KageMusha_Character` | ~150 objects parented to `KageMusha_Root`, grouped by region: kasa (ribs, rim, finial, 7 tassels), head/eyes/hood mask/scarf/shawl, do cuirass with 影 mon and scrollwork, X bandoliers, dragon sode, sleeves, kote bracers, gloves with tekko and finger plates, obi and belts with red cords and gold charms, kusazuri, apron, gold-print panel, red strips, tattered skirt, back banner with crest, baggy pants, suneate with chain mail and red ties, strapped armored boots |
| `Weapons_Katana_Wakizashi` | Katana (left hip) and wakizashi (right hip): lacquered scabbards with engraved fittings, openwork tsuba, diamond-wrapped tsuka, sageo cords |
| `Gear_Gourds_Bombs_Pouches` | Hyōtan gourds, kanji smoke bombs, tooled leather pouches, engraved powder flask, kunai holster, rope hank and grappling hook |
| `Props_Showcase` | Every item from the sheet's item row on a black display, plus a sword stand, a drawn katana with hamon, and a tanegashima matchlock |
| `Environment_Courtyard` | Wet flagstone courtyard, railing, moat, castle hill with multi-tier keeps, red maples, pines, lanterns, nobori banners |
| `Lighting` / `Cameras` | Rotating light rig, dusk sky, turnaround cameras (`CAM_Front/Left/Right/Back`), detail cameras (`CAM_Detail_*`), and showcase cameras |

Rendering uses Cycles. The materials use AO and pointiness for grime and edge wear; EEVEE also
works but loses those effects. The scene compositor adds bloom, a grade and a vignette.

## Rebuilding from source

Everything is procedural, so the scripts regenerate the whole file:

```bash
pip install bpy==4.2.0 pillow numpy fonttools
# (optional) regenerate textures: needs the fontsource "yuji-boku" + "shippori-mincho-b1" npm packages
KAGE_FONT_DIR=/path/to/fonts python tools/make_textures.py
python tools/build_kage_musha.py                      # writes samurai-ninja_claude.blend
python tools/render_sheet_assets.py --blend samurai-ninja_claude.blend --out renders/sheet --samples 72
KAGE_FONT_DIR=/path/to/fonts python tools/make_sheet.py --assets renders/sheet --out renders/kage_musha_sheet.png
```

| Script | Purpose |
|---|---|
| `tools/kage_lib.py` | Geometry builders (parametric grids, lathes, sweeps, limbs) and node materials |
| `tools/kage_mats.py` | All materials |
| `tools/kage_body.py` | Body anchors, head, hood, scarf and kasa |
| `tools/kage_armor.py` | Do, straps, sode, arms, legs and boots |
| `tools/kage_gear.py` | Waist, skirts, gear, back items and showcase |
| `tools/kage_weapons.py` | Tsuba, blades, katana/wakizashi parts, matchlock and sword stand |
| `tools/kage_scene.py` | Render settings, lights, cameras, environment and compositor |
| `tools/make_textures.py` | Dragon, mon, kanji prints, scrollwork and other masks (`textures/`) |
