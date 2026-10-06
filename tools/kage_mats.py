"""All materials for the Kage Musha character (built once, shared by parts)."""
from kage_lib import (mat_cast_iron, mat_cloth, mat_decal, mat_eye, mat_forged, mat_gold, mat_gourd, mat_lacquer,
                      mat_leather, mat_leather_tooled, mat_mail, mat_metal_engraved, mat_rope, mat_simple, mat_tsuka)

M = {}


def build_materials():
    # --- metals --------------------------------------------------------------
    M["gold"] = mat_gold("Gold_Trim", (0.44, 0.30, 0.13), 0.42, 0.85)
    M["gold_dark"] = mat_gold("Gold_Antique", (0.30, 0.19, 0.08), 0.52, 0.9)
    M["bronze_rib"] = mat_gold("Bronze_Kasa_Rib", (0.12, 0.072, 0.032), 0.62, 0.6)
    M["bronze"] = mat_gold("Bronze_Patina", (0.42, 0.25, 0.11), 0.4, 0.7)
    M["iron"] = mat_simple("Iron_Dark", (0.035, 0.032, 0.03), rough=0.42, metal=0.9, var_col=(0.13, 0.06, 0.03),
                           var_scale=12.0, bump_scale=120.0, bump_str=0.15, dirt=0.3)
    M["steel"] = mat_simple("Steel_Blade", (0.62, 0.62, 0.63), rough=0.28, metal=1.0, var_col=(0.30, 0.27, 0.25),
                            var_scale=18.0, bump_scale=200.0, bump_str=0.05)
    # --- lacquer (urushi) ---------------------------------------------------
    M["lacquer"] = mat_lacquer("Lacquer_Black")
    M["lacquer_dragon_L"] = mat_lacquer("Lacquer_Dragon_L", "dragon_emblem.png", extension="CLIP", relief=0.5,
                                        wear=0.15, gold_tint=(0.70, 0.49, 0.22), disp=0.0016)
    M["lacquer_dragon_R"] = mat_lacquer("Lacquer_Dragon_R", "dragon_emblem.png", extension="CLIP", relief=0.5,
                                        wear=0.15, flip_u=True, gold_tint=(0.70, 0.49, 0.22), disp=0.0016)
    M["lacquer_lamellar"] = mat_lacquer("Lacquer_Lamellar", "lamellar_band.png", uv_scale=(1.0, 1.0), wear=0.6,
                                        gold_tint=(0.28, 0.18, 0.075), relief=0.2, coat=0.12, disp=0.0004)
    M["lacquer_engraved"] = mat_lacquer("Lacquer_Engraved", "filigree.png", uv_scale=(3.0, 1.15), wear=0.4,
                                        relief=0.25, gold_tint=(0.58, 0.40, 0.17), disp=0.0005)
    M["lacquer_engraved_s"] = mat_lacquer("Lacquer_Engraved_Sparse", "filigree_sparse.png", uv_scale=(2.0, 2.0),
                                          wear=0.5, relief=0.2, gold_tint=(0.55, 0.37, 0.15))
    M["lacquer_bracer"] = mat_lacquer("Lacquer_Bracer", "bracer_panel.png", extension="CLIP", wear=0.45,
                                      gold_tint=(0.55, 0.38, 0.16), disp=0.0008)
    M["cloth_sleeve"] = mat_cloth("Cloth_Sleeve", print_img="cloth_print.png", mapping="TRI", print_scale=(3.0, 3.0),
                                  print_strength=0.6, print_col=(0.32, 0.21, 0.10), dust=0.2)
    M["lacquer_suneate"] = mat_lacquer("Lacquer_Suneate", "suneate_panel.png", extension="CLIP", wear=0.5,
                                       gold_tint=(0.52, 0.36, 0.15), disp=0.0008)
    M["mail"] = mat_mail("Chainmail_Iron")
    M["lacquer_hat"] = mat_lacquer("Lacquer_Kasa", "hat_glyphs.png", uv_scale=(1.0, 1.0), wear=0.6, straw=True,
                                   base=(0.022, 0.016, 0.012), relief=0.15, coat=0.08, stone=0.0,
                                   gold_tint=(0.45, 0.30, 0.12))
    M["kasa_rib"] = mat_lacquer("Lacquer_Kasa_Rib", base=(0.016, 0.012, 0.009), dust=0.45, coat=0.08, stone=0.3,
                                edge_col=(0.20, 0.10, 0.045))
    M["lacquer_saya"] = mat_lacquer("Lacquer_Saya", "filigree_sparse.png", uv_scale=(1.0, 2.6), wear=0.35,
                                    relief=0.15, dust=0.12, gold_tint=(0.62, 0.42, 0.18), stone=0.25)
    # --- cloth ----------------------------------------------------------------
    M["cloth"] = mat_cloth("Cloth_Black", print_img="cloth_print_sparse.png", mapping="TRI", print_scale=(2.2, 2.2),
                           print_strength=0.55, print_col=(0.30, 0.20, 0.09))
    M["cloth_plain"] = mat_cloth("Cloth_Black_Plain")
    M["cloth_hood"] = mat_cloth("Cloth_Hood", base=(0.017, 0.016, 0.016), fade=(0.040, 0.035, 0.032), dust=0.10,
                                sheen=0.85, folds=0.15, print_img="cloth_print_sparse.png", mapping="TRI", print_scale=(3.5, 3.5),
                                print_strength=0.45, print_col=(0.30, 0.20, 0.09))
    M["cloth_print"] = mat_cloth("Cloth_Gold_Print", print_img="cloth_print.png", mapping="TRI", print_scale=(2.2, 2.2),
                                 print_strength=1.0, print_col=(0.40, 0.27, 0.12))
    M["cloth_skirt"] = mat_cloth("Cloth_Skirt", print_img="cloth_print.png", mapping="TRI", print_scale=(2.2, 2.2),
                                 print_strength=0.65, dust=0.30, print_col=(0.32, 0.21, 0.10), fray=0.045)
    M["cloth_skirt_under"] = mat_cloth("Cloth_Skirt_Under", base=(0.016, 0.015, 0.014), print_img="cloth_print_sparse.png",
                                       mapping="TRI", print_scale=(2.2, 2.2), print_strength=0.3, dust=0.45, fray=0.045)
    M["cloth_skirt_top"] = mat_cloth("Cloth_Skirt_Top", print_img="cloth_print_dense.png", mapping="TRI",
                                     print_scale=(2.0, 2.0), print_strength=0.95, print_col=(0.36, 0.25, 0.12), dust=0.35,
                                     fray=0.045)
    M["cloth_apron"] = mat_cloth("Cloth_Apron", print_img="apron_print.png", print_scale=(1, 1),
                                 extension="CLIP", print_strength=0.85, print_col=(0.36, 0.25, 0.12), fray=0.045)
    M["cloth_panel"] = mat_cloth("Cloth_Panel_Gold", print_img="panel_print.png", print_scale=(1, 1),
                                 extension="CLIP", print_strength=1.0, print_col=(0.40, 0.28, 0.14), fray=0.045)
    M["cloth_banner"] = mat_cloth("Cloth_Banner", print_img="banner_print.png", print_scale=(1, 1),
                                  extension="CLIP", print_strength=1.0, print_col=(0.44, 0.31, 0.16), fray=0.04, rot=0.16)
    M["cloth_pants"] = mat_cloth("Cloth_Pants", print_img="cloth_print_sparse.png", mapping="TRI", print_scale=(2.5, 2.5),
                                 print_strength=0.5, dust=0.40, print_col=(0.30, 0.20, 0.09))
    M["cloth_red"] = mat_cloth("Cloth_Crimson", base=(0.085, 0.014, 0.011), fade=(0.17, 0.05, 0.035), dust=0.45,
                               mapping="TRI", print_img="cloth_print_sparse.png", print_scale=(3, 3), print_strength=0.3,
                               print_col=(0.40, 0.22, 0.09), sheen_tint=(0.65, 0.32, 0.28), fray=0.045)
    M["obi"] = mat_cloth("Cloth_Obi", base=(0.05, 0.010, 0.010), fade=(0.09, 0.02, 0.017), dust=0.2, weave=400,
                         sheen_tint=(0.6, 0.3, 0.28))
    M["cloth_thread"] = mat_simple("Cloth_Thread", (0.030, 0.026, 0.022), rough=0.9, sheen=0.5)
    # --- cords / leather / organics ------------------------------------------
    M["cord_red"] = mat_simple("Cord_Red", (0.15, 0.010, 0.009), rough=0.62, sheen=0.12, var_col=(0.18, 0.012, 0.01),
                               wave="BANDS", wave_scale=60.0, wave_str=0.8, bump_str=0.5)
    M["cord_dark"] = mat_simple("Cord_Black", (0.02, 0.018, 0.017), rough=0.65, sheen=0.12,
                                wave="BANDS", wave_scale=60.0, wave_str=0.8, bump_str=0.5)
    M["tassel"] = mat_simple("Tassel_Silk", (0.16, 0.08, 0.028), rough=0.5, sheen=0.15, var_col=(0.12, 0.045, 0.015),
                             wave="BANDS", wave_dir="X", wave_scale=180.0, wave_str=0.9, bump_str=0.4)
    M["leather"] = mat_leather("Leather_Brown", base=(0.032, 0.016, 0.008), light=(0.070, 0.036, 0.018))
    M["leather_tooled"] = mat_leather_tooled("Leather_Pouch_Tooled", base=(0.030, 0.012, 0.006),
                                             light=(0.085, 0.036, 0.016))
    M["leather_dark"] = mat_leather("Leather_Black", base=(0.012, 0.010, 0.009), light=(0.030, 0.024, 0.020),
                                    rough=0.55)
    M["boot"] = mat_leather("Leather_Boot", base=(0.014, 0.011, 0.009), light=(0.034, 0.026, 0.020), rough=0.7,
                            scuff=0.7, dirt=0.55)
    M["gourd"] = mat_gourd("Gourd_Calabash")
    M["rope"] = mat_rope("Rope_Hemp")
    M["straw"] = mat_simple("Straw_Sandal", (0.035, 0.025, 0.016), rough=0.85, var_col=(0.08, 0.05, 0.03),
                            wave="BANDS", wave_dir="X", wave_scale=200.0, wave_str=1.0, bump_str=0.5, dirt=0.5)
    M["skin"] = mat_simple("Skin", (0.16, 0.090, 0.060), rough=0.5, sss=0.3, var_col=(0.12, 0.065, 0.045),
                           var_scale=30.0, bump_scale=300.0, bump_str=0.05)
    M["eye"] = mat_eye("Eye")
    M["tsuka"] = mat_tsuka("Tsuka_Wrap_Red", same=(0.36, 0.035, 0.025))
    M["tsuka_gold"] = mat_tsuka("Tsuka_Wrap_Gold", same=(0.45, 0.30, 0.12))
    M["wood"] = mat_simple("Wood_Dark", (0.07, 0.035, 0.02), rough=0.6, var_col=(0.12, 0.06, 0.03),
                           wave="BANDS", wave_dir="Z", wave_coord="Object", wave_scale=12.0, wave_str=0.3)
    # --- decals ---------------------------------------------------------------
    M["decal_mon_chest"] = mat_decal("Decal_Mon_Chest", "mon_chest.png", wear=0.25)
    M["decal_mon_flower"] = mat_decal("Decal_Mon_Flower", "mon_flower.png", wear=0.2)
    M["decal_smoke"] = mat_decal("Decal_SmokeBomb_Kanji", "smokebomb_kanji.png", wear=0.35, tint=(0.46, 0.36, 0.20),
                                 rough=0.55)
    M["bronze_engraved"] = mat_metal_engraved("Bronze_Engraved_Flask", tint=(0.22, 0.14, 0.07), uv_scale=(2.0, 1.5),
                                              rough=0.5)
    M["bomb_iron"] = mat_cast_iron("Iron_Cast_Bomb")
    M["forged"] = mat_forged("Steel_Forged")
    M["decal_dragon_L"] = mat_decal("Decal_Dragon_L", "dragon_emblem.png", wear=0.25)
    M["decal_mask_flower"] = mat_decal("Decal_Mask_Flower", "mon_flower.png", wear=0.6, tint=(0.17, 0.11, 0.05),
                                       metal=0.2, rough=0.6)
    M["decal_dragon_R"] = mat_decal("Decal_Dragon_R", "dragon_emblem.png", wear=0.25, flip_u=True)
    return M
