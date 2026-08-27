# dcic-data

Generated data used by Dragon City Information Center.


## Dragon Skins pipeline

- `extract_skins.py` — resolves `dragon_skins`, attribute modifiers, Skin/Flair UI type, owner data, and Flair BG/FG VFX into a frontend-ready database.
- `skins.json` — frontend feed for `/p/all-dragon-skins.html` and the global `?skin_id=...` Skin Details popup.
- `dragons.json` remains the authoritative owner-dragon source for rarity, elements, families, images, skills, attacks, income, and DCIC stat profiles.

`skins.json` keeps official `ui_type` (Skin/Flair) separate from `effect_class` (Attribute Modifiers/Cosmetic-Flair). This preserves edge cases such as a Flair that also modifies gameplay attributes. Attack modifiers are classified semantically: normal attacks become Basic/Trained Attack tags, while attacks linked to a skill definition become Active Skill tags. Flair PNG layers are resolved through `dragon_vfx -> generic_spine` and point to the DCIC `bg-fg/flair` asset directory.

## Arena Season pipeline

- `arena_config.json` — raw PVP Arenas config captured from the game (static Arenas, seasonal Arenas, parameters, Warrior Chests).
- `game_config.json` — main game config used to resolve Arena Tribute offers and the dragon-side VIP Tribute signature.
- `dragons.json` — compact dragon database used for names, images, rarity, elements, and the shared Dragon Details popup.
- `arena_overrides.json` — configurable Tribute signatures and optional manual corrections.
- `extract_arena_seasons.py` — builds the compact frontend feed.
- `arena_seasons.json` — frontend feed for the homepage Arena section and `/p/arena-season.html?id=...`.

Static Arena levels are stored only once in `static_arenas`. Seasonal Arena records are grouped by Arena Season. `arena_level_id` is retained only as an internal sort/join key and is intentionally not displayed on the website.

Normal Arena Tributes are resolved from matching `offer_system` offers. VIP-Exclusive Tributes are detected from the configurable temporary stats/hatching signature in the dragon data, with previously observed season results preserved by subsequent extractor runs.

### Dragon stat profiles

`dragons.json` schema v3 adds `stats.level_1`, representing the dragon's Level 1
Health, Damage, and Speed with no stat-boosting attributes applied. The legacy
`stats.in_game_base` key is retained as a backward-compatible alias of the same
Level 1 profile. `stats.in_game_max` remains the Level 70 + Empower 5 +
Platinum III + maximum Basic Perks profile used by DCIC.

## Skin image overrides

`skin_image_overrides.json` stores manual full-body image corrections for skins whose config image code is legacy, broken, or missing. Keys are Skin IDs. `extract_skins.py` applies these overrides when regenerating `skins.json`, so manual corrections are not lost on future config updates.

