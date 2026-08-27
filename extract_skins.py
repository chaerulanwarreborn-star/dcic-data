#!/usr/bin/env python3
"""Build DCIC skins.json from game_config + EN localization + generated dragons.json.

This extractor intentionally keeps browser logic light. It resolves Skin/Flair metadata,
modifier semantics, owner filters, composed Flair VFX layers, and the Original vs With Skin
comparison used by the global Skin Details popup.
"""
from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from extract_dragons import (
    attack_detail,
    build_stat_config,
    dragon_stat_profiles,
    index_by_id,
    load_json,
    localization_map,
    load_skill_description_overrides,
    logical_skill_details,
    safe_int,
)

ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "game_config.json"
LOCALIZATION_PATH = ROOT / "localization" / "dragon_city_localization_baseline_en.json"
if not LOCALIZATION_PATH.exists():
    LOCALIZATION_PATH = ROOT / "dragon_city_localization_baseline_en.json"
DRAGONS_PATH = ROOT / "dragons.json"
OUTPUT_PATH = ROOT / "skins.json"
IMAGE_OVERRIDES_PATH = ROOT / "skin_image_overrides.json"

DRAGON_FULL_BODY_CDN = "https://dci-static-s1.socialpointgames.com/static/dragoncity/mobile/ui/dragons/"
DRAGON_THUMB_CDN = "https://dci-static-s1.socialpointgames.com/static/dragoncity/mobile/ui/dragons/HD/"
ASSET_BASE = "https://raw.githubusercontent.com/chaerulanwarreborn-star/dcic-assets/main/icons/"
FLAIR_VFX_BASE = "https://raw.githubusercontent.com/chaerulanwarreborn-star/dcic-assets/main/bg-fg/flair/"

GAMEPLAY_ATTRIBUTES = {
    "base_life", "base_attack", "speed", "attacks", "trainable_attacks",
    "passive_skills", "post_skills",
}

EFFECT_TAG_ORDER = [
    "health", "damage", "speed", "basic_attacks", "trained_attacks", "active_skill",
    "passive_skill", "post_skill", "bg_vfx", "fg_vfx",
]

EFFECT_TAG_LABELS = {
    "health": "Health",
    "damage": "Damage",
    "speed": "Speed",
    "basic_attacks": "Basic Attacks",
    "trained_attacks": "Trained Attacks",
    "active_skill": "Active Skill",
    "passive_skill": "Passive Skill",
    "post_skill": "Post Skill",
    "bg_vfx": "BG VFX",
    "fg_vfx": "FG VFX",
}


def norm_list(value: Any) -> List[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return list(value)
    return [value]


def clean_description_piece(value: Any) -> str:
    """Normalize one localized description fragment for display.

    Localization occasionally contains locked-description entries that are only
    punctuation (for example "." or ","). Those fragments are ignored. A real
    fragment receives a trailing period only when it has no terminal punctuation.
    """
    text = " ".join(str(value or "").split()).strip()
    if not text:
        return ""
    if not any(ch.isalnum() for ch in text):
        return ""
    if text[-1] not in ".!?,;:…":
        text += "."
    return text


def combined_description(primary: Any, locked: Any) -> str:
    parts: List[str] = []
    seen = set()
    for raw in (primary, locked):
        text = clean_description_piece(raw)
        key = text.casefold()
        if text and key not in seen:
            seen.add(key)
            parts.append(text)
    return " ".join(parts)


def multiply_config_value(current: Any, raw_multiplier: Any) -> Any:
    try:
        cur = float(current)
        mul = float(raw_multiplier)
    except (TypeError, ValueError):
        return current
    ratio = mul / 1_000_000.0 if abs(mul) > 10 else mul
    result = cur * ratio
    # Dragon base stats are integer config values.
    return int(round(result))


def apply_modifier(state: Dict[str, Any], mod: Dict[str, Any]) -> None:
    attribute = str(mod.get("attribute") or "")
    behaviour = str(mod.get("behaviour") or "").upper()
    value = deepcopy(mod.get("value"))

    if not attribute:
        return

    if behaviour == "MULTIPLY":
        if state.get(attribute) is not None:
            state[attribute] = multiply_config_value(state.get(attribute), value)
        return

    if behaviour == "REPLACE":
        state[attribute] = deepcopy(value)
        return

    if behaviour == "ADD_ARRAY":
        current = norm_list(state.get(attribute))
        current.extend(norm_list(value))
        state[attribute] = current
        return

    if behaviour == "REPLACE_BY_INDEX":
        current = norm_list(state.get(attribute))
        idx = safe_int(mod.get("index"))
        if idx is None:
            return
        # Config uses 1-based combat slot indexes.
        pos = max(0, idx - 1)
        while len(current) <= pos:
            current.append(None)
        current[pos] = deepcopy(value)
        state[attribute] = current


def changed_slots(before: Iterable[Any], after: Iterable[Any]) -> List[bool]:
    a, b = list(before or []), list(after or [])
    size = max(len(a), len(b))
    return [(a[i] if i < len(a) else None) != (b[i] if i < len(b) else None) for i in range(size)]


def resolve_vfx_asset(
    vfx_id: Any,
    vfx_lookup: Dict[int, Dict[str, Any]],
    generic_spine_lookup: Dict[int, Dict[str, Any]],
) -> Dict[str, Any]:
    vid = safe_int(vfx_id)
    if vid is None:
        return {}
    vfx = vfx_lookup.get(vid, {})
    asset_ids = vfx.get("asset_id") if isinstance(vfx.get("asset_id"), dict) else {}
    spine_id = None
    for stage in ("adult", "baby", "egg"):
        spine_id = safe_int(asset_ids.get(stage))
        if spine_id is not None:
            break
    generic = generic_spine_lookup.get(spine_id or -1, {}) if spine_id is not None else {}
    asset_name = str(generic.get("asset") or vfx.get("node_name") or "").strip()
    url = f"{FLAIR_VFX_BASE}{asset_name}.png" if asset_name else ""
    return {
        "vfx_id": vid,
        "generic_spine_id": spine_id,
        "asset": asset_name,
        "url": url,
        "node_name": str(vfx.get("node_name") or ""),
    }


def build_vfx_layers(
    values: Iterable[Any],
    vfx_lookup: Dict[int, Dict[str, Any]],
    generic_spine_lookup: Dict[int, Dict[str, Any]],
) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    seen = set()
    for raw in values or []:
        row = resolve_vfx_asset(raw, vfx_lookup, generic_spine_lookup)
        key = (row.get("vfx_id"), row.get("asset"))
        if row and key not in seen:
            seen.add(key)
            out.append(row)
    return out


def attack_is_skilled(attack_id: Any, attack_lookup: Dict[int, Dict[str, Any]]) -> bool:
    aid = safe_int(attack_id)
    return bool(aid is not None and attack_lookup.get(aid, {}).get("skill_id") is not None)


def modifier_effect_tags(
    mods: List[Dict[str, Any]],
    original: Dict[str, Any],
    modified: Dict[str, Any],
    attack_lookup: Dict[int, Dict[str, Any]],
) -> List[str]:
    found = set()
    for mod in mods:
        attr = str(mod.get("attribute") or "")
        if attr == "base_life":
            found.add("health")
        elif attr == "base_attack":
            found.add("damage")
        elif attr == "speed":
            found.add("speed")
        elif attr == "passive_skills":
            found.add("passive_skill")
        elif attr == "post_skills":
            found.add("post_skill")
        elif attr == "background_vfx":
            found.add("bg_vfx")
        elif attr == "foreground_vfx":
            found.add("fg_vfx")

    # Attack tags are semantic: normal attacks belong to Basic/Trained; attacks linked
    # to a skill_definition belong to Active Skill instead.
    for attr, normal_tag in (("attacks", "basic_attacks"), ("trainable_attacks", "trained_attacks")):
        before = norm_list(original.get(attr))
        after = norm_list(modified.get(attr))
        for i, changed in enumerate(changed_slots(before, after)):
            if not changed:
                continue
            aid = after[i] if i < len(after) else None
            if attack_is_skilled(aid, attack_lookup):
                found.add("active_skill")
            else:
                found.add(normal_tag)

    return [key for key in EFFECT_TAG_ORDER if key in found]


def activation_key(mods: List[Dict[str, Any]]) -> str:
    if not mods:
        return "no_modifier"
    flags = {bool(m.get("only_if_equipped")) for m in mods}
    if flags == {False}:
        return "always_active"
    if flags == {True}:
        return "equipped_only"
    return "mixed"


def owner_snapshot(dragon: Dict[str, Any]) -> Dict[str, Any]:
    details = dragon.get("details") or {}
    return {
        "id": dragon.get("id"),
        "name": dragon.get("name"),
        "book_id": dragon.get("book_id"),
        "image": dragon.get("full_body_image") or (details.get("images") or {}).get("adult") or dragon.get("adult_image"),
        "thumbnail": dragon.get("adult_image") or dragon.get("full_body_image") or (details.get("images") or {}).get("adult"),
        "rarity": dragon.get("rarity"),
        "elements": list(dragon.get("elements") or []),
        "display_elements": deepcopy(dragon.get("display_elements") or {}),
        "family": deepcopy(dragon.get("family")),
        "family_filters": list(dragon.get("family_filters") or []),
        "stats": deepcopy(dragon.get("stats") or {}),
        "skills": deepcopy(details.get("skills") or []),
        "attacks": deepcopy(details.get("attacks") or {}),
        "income": deepcopy(details.get("income") or {}),
    }


def compare_values(before: Dict[str, Any], after: Dict[str, Any], keys: Iterable[str]) -> Dict[str, bool]:
    return {key: before.get(key) != after.get(key) for key in keys}


def main() -> None:
    config = load_json(CONFIG_PATH)
    loc = localization_map(load_json(LOCALIZATION_PATH))
    skill_description_overrides = load_skill_description_overrides()
    dragons_payload = load_json(DRAGONS_PATH)
    dragons = dragons_payload.get("dragons") or []
    dragon_by_id = {safe_int(d.get("id")): d for d in dragons if safe_int(d.get("id")) is not None}

    image_overrides: Dict[str, Any] = {}
    if IMAGE_OVERRIDES_PATH.exists():
        raw_overrides = load_json(IMAGE_OVERRIDES_PATH)
        if isinstance(raw_overrides, dict):
            image_overrides = raw_overrides

    item_lookup = {
        safe_int(item.get("id")): item
        for item in (config.get("items") or [])
        if isinstance(item, dict) and item.get("group_type") == "DRAGON" and safe_int(item.get("id")) is not None
    }

    skin_cfg = config.get("dragon_skins") or {}
    skin_rows = skin_cfg.get("dragon_skins") or []
    modifier_lookup = index_by_id(skin_cfg.get("items_units_attribute_modifiers") or [])
    skin_ui_lookup = index_by_id(skin_cfg.get("skin_ui") or [])

    skills_cfg = config.get("skills") or {}
    attack_lookup = index_by_id(skills_cfg.get("attacks") or [])
    passive_lookup = index_by_id(skills_cfg.get("passive") or [])
    post_lookup = index_by_id(skills_cfg.get("post") or [])
    skill_def_lookup = index_by_id(skills_cfg.get("skills") or [])

    dragon_vfx = config.get("dragon_vfx") or {}
    vfx_lookup = index_by_id(dragon_vfx.get("vfx") or [])
    generic_spine_lookup = index_by_id(dragon_vfx.get("generic_spine") or [])

    stat_cfg = build_stat_config(config)

    output_skins: List[Dict[str, Any]] = []

    for skin in skin_rows:
        if not isinstance(skin, dict):
            continue
        sid = safe_int(skin.get("id"))
        owner_id = safe_int(skin.get("dragon_id"))
        if sid is None or owner_id is None:
            continue
        owner = dragon_by_id.get(owner_id)
        owner_item = item_lookup.get(owner_id)
        if not owner or not owner_item:
            continue

        mod_ids = [safe_int(x) for x in (skin.get("items_units_attribute_modifiers_ids") or [])]
        mod_ids = [x for x in mod_ids if x is not None]
        mods = [deepcopy(modifier_lookup[mid]) for mid in mod_ids if mid in modifier_lookup]

        state_before = {
            "base_life": owner_item.get("base_life"),
            "base_attack": owner_item.get("base_attack"),
            "speed": owner_item.get("speed"),
            "attacks": deepcopy(owner_item.get("attacks") or []),
            "trainable_attacks": deepcopy(owner_item.get("trainable_attacks") or []),
            "passive_skills": deepcopy(owner_item.get("passive_skills") or []),
            "post_skills": deepcopy(owner_item.get("post_skills") or []),
            "background_vfx": deepcopy(owner_item.get("background_vfx") or []),
            "foreground_vfx": deepcopy(owner_item.get("foreground_vfx") or []),
        }
        state_after = deepcopy(state_before)
        for mod in mods:
            apply_modifier(state_after, mod)

        tags = modifier_effect_tags(mods, state_before, state_after, attack_lookup)
        has_gameplay_modifier = any(str(m.get("attribute") or "") in GAMEPLAY_ATTRIBUTES for m in mods)
        effect_class = "attribute_modifiers" if has_gameplay_modifier else "cosmetic_flair"

        skin_ui_id = safe_int(skin.get("skin_ui_id")) or 1
        ui_type = "flair" if skin_ui_id == 2 else "skin"
        type_tid = skin_ui_lookup.get(skin_ui_id, {}).get("type_tid")
        ui_type_label = loc.get(str(type_tid)) or ("Flair" if ui_type == "flair" else "Skin")

        img_name = str(skin.get("img_name_mobile") or skin.get("img_name_canvas") or "")
        full_body = f"{DRAGON_FULL_BODY_CDN}ui_{img_name}_3@2x.png" if img_name else ""
        thumb = f"{DRAGON_THUMB_CDN}thumb_{img_name}_3.png" if img_name else ""

        # Manual image overrides are intentionally kept outside generated data so
        # known legacy/missing skin art mappings survive future config updates.
        image_override = image_overrides.get(str(sid)) or image_overrides.get(sid)
        if isinstance(image_override, str):
            full_body = image_override.strip() or full_body
        elif isinstance(image_override, dict):
            full_body = str(image_override.get("image") or full_body).strip()
            thumb = str(image_override.get("thumbnail") or thumb).strip()

        # The selected skin visual uses the owner/skin body plus VFX introduced by the skin.
        bg_values = []
        fg_values = []
        for mod in mods:
            attr = str(mod.get("attribute") or "")
            if attr == "background_vfx":
                bg_values.extend(norm_list(mod.get("value")))
            elif attr == "foreground_vfx":
                fg_values.extend(norm_list(mod.get("value")))

        background_layers = build_vfx_layers(bg_values, vfx_lookup, generic_spine_lookup)
        foreground_layers = build_vfx_layers(fg_values, vfx_lookup, generic_spine_lookup)
        cosmetic_tags = []
        if background_layers or foreground_layers:
            cosmetic_tags.append("bg_fg_flair")
        if not mods or (not has_gameplay_modifier and not background_layers and not foreground_layers):
            cosmetic_tags.append("cosmetic_only")

        rarity = str(owner_item.get("dragon_rarity") or owner.get("rarity") or "").upper()
        modified_item = deepcopy(owner_item)
        for key in ("base_life", "base_attack", "speed", "attacks", "trainable_attacks", "passive_skills", "post_skills"):
            modified_item[key] = deepcopy(state_after.get(key))

        with_stats = dragon_stat_profiles(modified_item, rarity, stat_cfg)
        with_basic = attack_detail(state_after.get("attacks") or [], attack_lookup, skill_def_lookup, loc)
        with_trained = attack_detail(state_after.get("trainable_attacks") or [], attack_lookup, skill_def_lookup, loc)
        with_skills = logical_skill_details(
            state_after.get("passive_skills") or [],
            state_after.get("post_skills") or [],
            state_after.get("attacks") or [],
            state_after.get("trainable_attacks") or [],
            passive_lookup,
            post_lookup,
            attack_lookup,
            skill_def_lookup,
            loc,
            skill_description_overrides,
        )

        original = owner_snapshot(owner)
        with_skin = {
            "id": owner_id,
            "name": owner.get("name"),
            "image": full_body or original.get("image"),
            "rarity": owner.get("rarity"),
            "elements": list(owner.get("elements") or []),
            "display_elements": deepcopy(owner.get("display_elements") or {}),
            "family": deepcopy(owner.get("family")),
            "stats": with_stats,
            "skills": with_skills,
            "attacks": {"basic": with_basic, "trained": with_trained},
            "income": deepcopy((owner.get("details") or {}).get("income") or {}),
        }

        original_stats = original.get("stats") or {}
        changed = {
            "rarity": original.get("rarity") != with_skin.get("rarity"),
            "elements": original.get("elements") != with_skin.get("elements"),
            "raw_stats": compare_values(original_stats.get("raw") or {}, with_stats.get("raw") or {}, ("health", "damage", "speed")),
            "level_1_stats": compare_values(original_stats.get("level_1") or {}, with_stats.get("level_1") or {}, ("health", "damage", "speed")),
            "level_max_stats": compare_values(original_stats.get("in_game_max") or {}, with_stats.get("in_game_max") or {}, ("health", "damage", "speed")),
            "skills": original.get("skills") != with_skills,
            "basic_attacks": changed_slots(
                [x.get("id") for x in ((original.get("attacks") or {}).get("basic") or [])],
                [x.get("id") for x in with_basic],
            ),
            "trained_attacks": changed_slots(
                [x.get("id") for x in ((original.get("attacks") or {}).get("trained") or [])],
                [x.get("id") for x in with_trained],
            ),
            "income": original.get("income") != with_skin.get("income"),
        }

        primary_description = loc.get(str(skin.get("skin_description_tid"))) or ""
        locked_description = loc.get(str(skin.get("skin_locked_description_tid"))) or ""
        display_description = combined_description(primary_description, locked_description)

        raw_mods = []
        for mod in mods:
            raw_mods.append({
                "id": safe_int(mod.get("id")),
                "behaviour": mod.get("behaviour"),
                "attribute": mod.get("attribute"),
                "value": deepcopy(mod.get("value")),
                "index": safe_int(mod.get("index")),
                "only_if_equipped": bool(mod.get("only_if_equipped")),
            })

        output_skins.append({
            "id": sid,
            "name": loc.get(str(skin.get("skin_name_tid"))) or f"Skin {sid}",
            "description": primary_description,
            "locked_description": locked_description,
            "description_combined": display_description,
            "owner_id": owner_id,
            "owner_name": owner.get("name") or f"Dragon {owner_id}",
            "owner_thumbnail": owner.get("adult_image") or owner.get("full_body_image") or ((owner.get("details") or {}).get("images") or {}).get("adult"),
            "owner_book_id": safe_int(owner.get("book_id")),
            "owner_rarity": owner.get("rarity"),
            "owner_elements": list(owner.get("elements") or []),
            "family": deepcopy(owner.get("family")),
            "family_filters": list(owner.get("family_filters") or []),
            "ui_type": ui_type,
            "ui_type_label": ui_type_label,
            "effect_class": effect_class,
            "type_label": "Attribute Modifiers" if effect_class == "attribute_modifiers" else "Cosmetic/Flair",
            "skin_ui_id": skin_ui_id,
            "image": full_body,
            "thumbnail": thumb,
            "image_asset": img_name,
            "effect_tags": tags,
            "cosmetic_tags": cosmetic_tags,
            "activation": activation_key(mods),
            "start_ts": safe_int(skin.get("start_ts")),
            "modifier_ids": mod_ids,
            "modifiers": raw_mods,
            "flair": {
                "background_vfx": background_layers,
                "foreground_vfx": foreground_layers,
            },
            "effects": {
                "original": original,
                "with_skin": with_skin,
                "changed": changed,
            },
        })

    families = deepcopy((dragons_payload.get("filters") or {}).get("families") or [])
    rarities = deepcopy((dragons_payload.get("filters") or {}).get("rarities") or [])

    counts = {
        "skin_count": len(output_skins),
        "attribute_modifiers_count": sum(1 for s in output_skins if s["effect_class"] == "attribute_modifiers"),
        "cosmetic_flair_count": sum(1 for s in output_skins if s["effect_class"] == "cosmetic_flair"),
        "official_skin_count": sum(1 for s in output_skins if s["ui_type"] == "skin"),
        "official_flair_count": sum(1 for s in output_skins if s["ui_type"] == "flair"),
    }

    output = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "meta": {
            **counts,
            "level_1_stats_condition": {"level": 1, "attributes": "None"},
            "stats_display_condition": deepcopy((dragons_payload.get("meta") or {}).get("stats_display_condition") or {}),
        },
        "assets": {
            "base": ASSET_BASE,
            "flair_vfx_base": FLAIR_VFX_BASE,
            "attribute_modifiers_badge": "text-icons/ic-dragon-skin-attribute-modifiers-badge.png",
            "skin_badge": "text-icons/ic-dragon-skin-badge.png",
            "flair_badge": "text-icons/ic-dragon-flair-badge.png",
            "effect_tag_icons": {
                "health": "dragon-stats/ic-health.png",
                "damage": "dragon-stats/ic-damage.png",
                "speed": "dragon-stats/ic-speed.png",
                "basic_attacks": "text-icons/ic-hud-pvp.png",
                "trained_attacks": "text-icons/gr-train.png",
                "active_skill": "skills-icon/ic-skills-special-1.png",
                "passive_skill": "skills-icon/ic-skills-passive-special-1.png",
                "post_skill": "skills-icon/ic-skills-passive-special-1.png",
                "bg_vfx": "text-icons/ic-dragon-flair-badge.png",
                "fg_vfx": "text-icons/ic-dragon-flair-badge.png",
                "bg_fg_flair": "text-icons/ic-dragon-flair-badge.png",
                "cosmetic_only": "text-icons/ic-dragon-skin-badge.png"
            },
            "comparison_arrow": "feature-icon/gr-arrow.png",
        },
        "filters": {
            "skin_types": [
                {"key": "attribute_modifiers", "label": "Attribute Modifiers", "glow": "cyan"},
                {"key": "cosmetic_flair", "label": "Cosmetic/Flair", "glow": "magenta"},
            ],
            "effect_tags": [{"key": k, "label": EFFECT_TAG_LABELS[k]} for k in EFFECT_TAG_ORDER],
            "cosmetic_tags": [
                {"key": "bg_fg_flair", "label": "BG/FG Flair"},
                {"key": "cosmetic_only", "label": "Cosmetic Only"},
            ],
            "rarities": rarities,
            "families": families,
            "activation": [
                {"key": "", "label": "Show All"},
                {"key": "always_active", "label": "Always Active"},
                {"key": "equipped_only", "label": "Equipped Only"},
            ],
        },
        "skins": output_skins,
    }

    with OUTPUT_PATH.open("w", encoding="utf-8") as fh:
        json.dump(output, fh, ensure_ascii=False, separators=(",", ":"))

    print(
        f"Wrote {OUTPUT_PATH.name}: {counts['skin_count']} entries "
        f"({counts['attribute_modifiers_count']} Attribute Modifiers, "
        f"{counts['cosmetic_flair_count']} Cosmetic/Flair)."
    )


if __name__ == "__main__":
    main()
