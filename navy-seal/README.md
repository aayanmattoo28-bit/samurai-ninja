# U.S. Navy SEAL — procedural Blender build

`navy_seal.blend` is the Navy SEAL combat diver from the concept sheet, built entirely from Python (no sculpting):
the character with everything he wears and carries, plus the night-harbour set used for the turnaround views.
The concept's side panels (helmet/chest/arm/leg close-ups, weapon and gear cards, mission photos) were used only as
reference for shapes and details; they are not objects in the file.

## Collections

- `NavySeal_Character`
  - `Body_Drysuit_Gloves` — drysuit torso, sleeves and trousers (swirl linework camo), neoprene hood, armoured gloves
  - `Head_Helmet_Mask_Rebreather` — high-cut helmet (rails, NVG, comms cups, lights, antenna boxes), panoramic blue
    goggle, faceted respirator and regulator, neck manifold and the corrugated breathing-hose loop
  - `Arms_Pockets_Pads_Gauntlets` — sleeve pockets with subdued flags, elbow pads, gauntlets, wrist computer
  - `Vest_PlateCarrier_Pouches` — plate carrier, mag/flap pouches, dive computer, back case, cables, whip antenna
  - `Belt_Holster_Kneepads_Boots` — battle belt and pouches, drop-leg rigs, rope, pockets, knee pads, boots
  - `Weapons_Carried_Gear` — rifle, pistol and the carried tactical gear
- `Environment_Harbour` — wet quay, sea and surf, submarine, patrol boat, warship, mast, helicopter, mountains, lamps
- `Lighting`, `Cameras` — moonlit rig and the four turnaround cameras (FRONT, LEFT, BACK, RIGHT)

## Rebuild

Needs Blender 4.2 (or the `bpy` 4.2 module) plus numpy and Pillow:

```
python navy-seal/tools/make_seal_textures.py      # textures -> navy-seal/textures
python navy-seal/tools/seal_build.py              # -> navy-seal/navy_seal.blend
python navy-seal/tools/seal_render.py --scale 1 --samples 96   # turnaround panels -> navy-seal/renders
```

The modules share the procedural-modelling helpers in `../tools/kage_lib.py` (through `tools/seal_lib.py`).
Conventions: metres, Z up, the character faces -Y, the character's left is +X.
