# U.S. Navy SEAL — procedural Blender build

`navy_seal.blend` is the Navy SEAL combat diver from the concept sheet, built entirely from Python (no sculpting):
the character with everything he wears and carries. It holds the character only. The sheet's backdrop, side
panels (helmet/chest/arm/leg close-ups, weapon and gear cards, mission photos) and text were used only as reference
for shapes, details and colours; none of them is in the file.

The file is set up like the sheet's turnaround: one low, level 135 mm camera (`CAM_Turnaround`) sees the character
four times side by side — FRONT, LEFT, BACK, RIGHT — on a plain dark studio background, lit by a world-fixed sun rig
(warm key front-right, cool fill, peach rim behind-right, blue rim behind-left).

## Collections

- `NavySeal_Character` — the character itself (the FRONT figure)
  - `Body_Drysuit_Gloves` — drysuit torso, sleeves and trousers (swirl linework camo), neoprene hood, armoured gloves
  - `Head_Helmet_Mask_Rebreather` — high-cut helmet (rails, stowed NVG, comms cups, lights, antennas), twin-lobe
    cobalt goggle, faceted respirator and regulator, corrugated neck bellows with side canisters, breathing-hose loop
  - `Arms_Pockets_Pads_Gauntlets` — sleeve pockets with subdued flags, elbow pads, gauntlets, wrist computer
  - `Vest_PlateCarrier_Pouches` — plate carrier, printed mag/flap pouches with piping, dive computer, back case,
    cables, whip antenna
  - `Belt_Holster_Kneepads_Boots` — battle belt and pouches, drop-leg rigs, rope, pockets, knee pads, boots
  - `Weapons_Carried_Gear` — pistol in the holster, carbine mount tabs, and the gear stowed in the pouches (dive
    knife, flash-bang and frag canisters, folded drone, breaching charges, multi-tool)
- `Carbine_InHand_Front` — the carbine held muzzle-down in the right hand, as the sheet's FRONT view shows it
- `Carbine_Slung` — the carbine slung on the back with its loops and beaded strap, as the LEFT, BACK and RIGHT views
  show it (excluded from the view layer; the three side/back views instance it)
- `Turnaround_Views` — linked instances of the character (and the slung carbine) turned to show its left side, back
  and right side
- `Lighting`, `Cameras`

## Rebuild

Needs Blender 4.2 (or the `bpy` 4.2 module) plus numpy and Pillow:

```
python navy-seal/tools/make_seal_textures.py      # textures -> navy-seal/textures
python navy-seal/tools/seal_build.py              # -> navy-seal/navy_seal.blend (character only)
python navy-seal/tools/seal_render.py --scale 1 --samples 128   # turnaround + four panels -> navy-seal/renders
```

`seal_build.py --env --out other.blend` adds the old harbour backdrop (`seal_scene.build_environment`, sky made by
`make_seal_sky.py` from the concept sheet) for side-by-side comparison renders only; it is never saved into
`navy_seal.blend`.

The modules share the procedural-modelling helpers in `../tools/kage_lib.py` (through `tools/seal_lib.py`).
Conventions: metres, Z up, the character faces -Y, the character's left is +X.
