#!/usr/bin/env python3
"""Build a compact DCIC dragons.json from Dragon City's game_config + EN localization.

Expected repository layout:
  game_config.json
  localization/dragon_city_localization_baseline_en.json
  extract_dragons.py

Output:
  dragons.json

The generated file intentionally contains the data required by DCIC's Newest Dragons
and All Dragons UIs while avoiding a ~29 MB game_config fetch in every visitor browser.
"""
from __future__ import annotations

import json
import math
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

ROOT = Path(__file__).resolve().parent
REPO_ROOT = ROOT.parent
DIST_DIR = REPO_ROOT / "dist"
OVERRIDES_DIR = REPO_ROOT / "overrides"
LOCALIZATION_DIR = REPO_ROOT / "localization"
RAW_DIR = Path(os.environ.get("DCIC_RAW_DIR", REPO_ROOT.parent / "the-void"))

CONFIG_PATH = RAW_DIR / "game_config.json"
LOCALIZATION_PATH = LOCALIZATION_DIR / "dragon_city_localization_baseline_en.json"
if not LOCALIZATION_PATH.exists():
    LOCALIZATION_PATH = REPO_ROOT / "dragon_city_localization_baseline_en.json"
OUTPUT_PATH = DIST_DIR / "dragons.json"
SKILL_DESCRIPTION_OVERRIDES_PATH = OVERRIDES_DIR / "skill_description_overrides.json"

DRAGON_CDN = "https://dci-static-s1.socialpointgames.com/static/dragoncity/mobile/ui/dragons/HD/"
DRAGON_FULL_BODY_CDN = "https://dci-static-s1.socialpointgames.com/static/dragoncity/mobile/ui/dragons/"
ASSET_ROOT = "icons/"

# Full-body image overrides for dragons whose default config asset is missing or unsuitable.
# Keep this keyed by Dragon ID so future overrides can be added without touching page code.
DRAGON_FULL_BODY_OVERRIDES: Dict[int, str] = {
    # Placeholder VIP has no img_name_mobile/img_name in game_config.
    9999: "https://raw.githubusercontent.com/chaerulanwarreborn-star/dcic-assets/main/override/ui_2191_dragon_default_3@2x.png",
    1113: "https://raw.githubusercontent.com/chaerulanwarreborn-star/dcic-assets/main/override/ui_1113_dragon_gaudi_3@2x.png",
    1144: "https://raw.githubusercontent.com/chaerulanwarreborn-star/dcic-assets/main/override/ui_1144_dragon_test_light_3@2x.png",
    1145: "https://raw.githubusercontent.com/chaerulanwarreborn-star/dcic-assets/main/override/ui_1145_dragon_test_war_3@2x.png",
    1146: "https://raw.githubusercontent.com/chaerulanwarreborn-star/dcic-assets/main/override/ui_1146_dragon_test_eternal_3@2x.png",
    1395: "https://raw.githubusercontent.com/chaerulanwarreborn-star/dcic-assets/main/override/ui_1395_flying_chest_3@2x.png",
    1396: "https://raw.githubusercontent.com/chaerulanwarreborn-star/dcic-assets/main/override/ui_1396_dragoonie_3@2x.png",
    1410: "https://raw.githubusercontent.com/chaerulanwarreborn-star/dcic-assets/main/override/ui_1410_deus_advisor_3@2x.png",
    1142: "https://raw.githubusercontent.com/chaerulanwarreborn-star/dcic-assets/main/override/ui_0000_dragon_placeholder_3@2x.png",
    # The config points to highhollowcrown, but the _b asset contains the complete body art.
    3504: f"{DRAGON_FULL_BODY_CDN}ui_3504_dragon_highhollowcrown_b_3@2x.png",
    2802: f"{DRAGON_FULL_BODY_CDN}ui_2802_dragon_gracekarma_c_3@2x.png",
    1416: f"{DRAGON_FULL_BODY_CDN}ui_1416_dragon_darkjaws_3@2x.png",
    2482: f"{DRAGON_FULL_BODY_CDN}ui_2482_dragon_positive_b_3@2x.png",
    2785: f"{DRAGON_FULL_BODY_CDN}ui_2785_dragon_courageouskarma_b_3@2x.png",
    2819: f"{DRAGON_FULL_BODY_CDN}ui_2819_dragon_focuskarma_b_3@2x.png",
    2836: f"{DRAGON_FULL_BODY_CDN}ui_2836_dragon_kungflowkarma_b_3@2x.png",
    2837: f"{DRAGON_FULL_BODY_CDN}ui_2837_dragon_ambitionkarma_b_3@2x.png",
    2854: f"{DRAGON_FULL_BODY_CDN}ui_2854_dragon_revivalkarma_b_3@2x.png",
    2906: f"{DRAGON_FULL_BODY_CDN}ui_2906_dragon_endurancekarma_b_3@2x.png",
    3278: f"{DRAGON_FULL_BODY_CDN}ui_3278_dragon_skeletalextractor_b_3@2x.png",
    3245: f"{DRAGON_FULL_BODY_CDN}ui_3245_dragon_serpentextractor_b_3@2x.png",
}

# Asset-name overrides are useful for pages that still construct the SocialPoint
# full-body URL from adult_asset instead of reading full_body_image directly.
DRAGON_ASSET_OVERRIDES: Dict[int, str] = {
    3504: "3504_dragon_highhollowcrown_b",
    2802: "2802_dragon_gracekarma_c",
    1416: "1416_dragon_darkjaws",
    2482: "2482_dragon_positive_b",
    2785: "2785_dragon_courageouskarma_b",
    2819: "2819_dragon_focuskarma_b",
    2836: "2836_dragon_kungflowkarma_b",
    2837: "2837_dragon_ambitionkarma_b",
    2854: "2854_dragon_revivalkarma_b",
    2906: "2906_dragon_endurancekarma_b",
    3278: "3278_dragon_skeletalextractor_b",
    3245: "3245_dragon_serpentextractor_b",
}

# Dragon IDs that should be treated as invalid/unreleased/non-dragon placeholders in DCIC.
# Maintain this list manually as discoveries change.
INVALID_DRAGON_IDS = {
    9999, 1113, 1144, 1145, 1146, 1395, 1396, 1410,
    2222, 1142, 1114, 1852, 1882, 1911, 1920, 1921,
}

# Display/sort ID overrides. These do not change the dragon's real ID.
# Autumn Dragon is a normal released dragon whose config ID is unusually high.
DRAGON_SORT_ID_OVERRIDES: Dict[int, int] = {
    9900: 2684,
}

RARITY_ORDER = ["C", "R", "V", "E", "L", "M", "H"]
RARITY_NAMES = {
    "C": "Common",
    "R": "Rare",
    "V": "Very Rare",
    "E": "Epic",
    "L": "Legendary",
    "M": "Mythical",
    "H": "Heroic",
}

ELEMENT_ORDER = [
    "e", "f", "w", "p", "el", "i", "m", "d", "li", "wr", "pu", "l",
    "pr", "wd", "ti", "bt", "mg", "ch", "hp", "dr", "so",
]
ELEMENT_NAMES = {
    "e": "Terra",
    "f": "Flame",
    "p": "Nature",
    "w": "Sea",
    "el": "Electric",
    "i": "Ice",
    "m": "Metal",
    "d": "Dark",
    "li": "Light",
    "wr": "War",
    "pu": "Pure",
    "l": "Legend",
    "pr": "Primal",
    "wd": "Wind",
    "ti": "Time",
    "hp": "Happy",
    "so": "Soul",
    "ch": "Chaos",
    "mg": "Magic",
    "bt": "Beauty",
    "dr": "Dream",
}

# Old-symbol display overrides supplied by the DCIC project brief.
# These are DISPLAY icons only. Filtering always uses the dragon's current config attributes.
OLD_ELEMENT_OVERRIDES: Dict[int, List[str]] = {
    1073: ["0-pu-e"],
    1074: ["0-pu-f"],
    1075: ["0-pu-w"],
    1076: ["0-pu-p"],
    1077: ["0-pu-el"],
    1078: ["0-pu-i"],
    1079: ["0-pu-m"],
    1080: ["0-pu-d"],
    1111: ["0-eg", "e-0"],
    1133: ["0-eg", "f-0"],
    1134: ["0-eg", "d-0"],
    1136: ["0-dn", "f-0", "m-0"],
    1148: ["0-dn", "f-0", "e-0"],
    1155: ["0-ol"],
    1156: ["0-ol", "d-0"],
    1157: ["0-ol", "e-0", "p-0"],
    1182: ["wr-0", "0-vk"],
    1183: ["wr-0", "0-vk", "d-0"],
    1184: ["wr-0", "0-vk", "li-0"],
    1231: ["0-az", "f-0"],
    1232: ["0-az", "d-0"],
    1233: ["0-az", "el-0", "li-0"],
    2222: ["0-in"],
}

# For dragon 2222 there is no modern config attribute. The project explicitly wants 0-in displayed.
CURRENT_ELEMENT_OVERRIDES: Dict[int, List[str]] = {
    2222: ["0-in"],
}

FAMILY_ASSET_ALIASES = {
    # Some current config family icon filenames differ from the curated DCIC asset names.
    "icon2.png": "gr-family-badge-vampire.png",
    "icon4.png": "gr-family-badge-karma.png",
    "icon-eternal.png": "gr-family-badge-eternals.png",
    "icon-twd.png": "gr-family-badge-twd.png",
    "icon-strategist.png": "gr-family-badge-strategist.png",
    "icon-spikes.png": "gr-family-badge-spikes.png",
    "icon-silencer.png": "gr-family-badge-silencer.png",
    "icon-plasma.png": "gr-family-badge-plasma.png",
}

FAMILY_LABELS = {
    "apocalypse": "Apocalypse", "arcana": "Arcana", "armor": "Armor", "ascended": "Ascended",
    "astro": "Astro", "berserker": "Berserker", "corrupted": "Corrupted", "critical": "Critical",
    "doom": "Doom", "dual": "Dual", "eternals": "Eternals", "evader": "Evader", "extractor": "Extractor",
    "guard": "Guard", "karma": "Karma", "mecha": "Mecha", "mythical": "Mythical", "plasma": "Plasma",
    "quantum": "Quantum", "redemption": "Redemption", "risen": "Risen", "silencer": "Silencer",
    "spikes": "Spikes", "stained": "Stained", "strategist": "Strategist", "titans": "Titans",
    "twd": "TWD", "vampire": "Vampire", "vip": "VIP", "void": "Void", "youtuber": "Youtuber",
}


# Manual family filter order used by DCIC.
# Mythical first, then families roughly oldest -> newest, with VIP and Youtuber last.
FAMILY_ORDER = [
    "mythical",
    "titans",
    "vampire",
    "corrupted",
    "ascended",
    "karma",
    "redemption",
    "dual",
    "twd",
    "eternals",
    "arcana",
    "plasma",
    "quantum",
    "berserker",
    "guard",
    "spikes",
    "extractor",
    "strategist",
    "evader",
    "silencer",
    "risen",
    "mecha",
    "critical",
    "armor",
    "apocalypse",
    "doom",
    "astro",
    "void",
    "stained",
    "vip",
    "youtuber",
]

FAMILY_ORDER_INDEX = {key: index for index, key in enumerate(FAMILY_ORDER)}

FALLBACK_FAMILY_TAGS = {
    "VIP": ("vip", "family-badge/vip-badge.png"),
    "Youtuber": ("youtuber", "family-badge/youtuber-badge.png"),
    "Mythical": ("mythical", "family-badge/ic-vip-mythical-dragon.png"),
}
# More specific project labels first when tags overlap.
FALLBACK_FAMILY_PRIORITY = ["Youtuber", "Mythical", "VIP"]


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8-sig") as fh:
        return json.load(fh)


def localization_map(raw: Any) -> Dict[str, str]:
    if isinstance(raw, dict):
        return {str(k): str(v) for k, v in raw.items()}
    result: Dict[str, str] = {}
    if isinstance(raw, list):
        for row in raw:
            if isinstance(row, dict):
                for k, v in row.items():
                    if isinstance(v, (str, int, float)):
                        result[str(k)] = str(v)
    return result


def index_by_id(rows: Any, key: str = "id") -> Dict[int, Dict[str, Any]]:
    out: Dict[int, Dict[str, Any]] = {}
    if not isinstance(rows, list):
        return out
    for row in rows:
        if not isinstance(row, dict):
            continue
        try:
            rid = int(row.get(key))
        except (TypeError, ValueError):
            continue
        out[rid] = row
    return out


def safe_int(value: Any) -> Optional[int]:
    try:
        if value is None or value == "":
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def family_asset_from_remote(remote: Any) -> Optional[str]:
    if not remote:
        return None
    name = str(remote).replace("\\", "/").rsplit("/", 1)[-1]
    name = FAMILY_ASSET_ALIASES.get(name, name)
    return f"family-badge/{name}" if name else None


def family_key_from_asset(asset: Optional[str], fallback: str) -> str:
    if not asset:
        return fallback
    name = asset.rsplit("/", 1)[-1].rsplit(".", 1)[0]
    for prefix in ("gr-family-badge-", "dc-ui-family-insignia_", "dc-ui-family-insignia-", "ic-vip-"):
        if name.startswith(prefix):
            name = name[len(prefix):]
            break
    name = name.replace("-dragon", "").replace("_dragon", "")
    if name.startswith("icon-"):
        name = name[5:]
    return name or fallback


def skill_summary(ids: Iterable[Any], lookup: Dict[int, Dict[str, Any]], source: str) -> List[Dict[str, Any]]:
    result: List[Dict[str, Any]] = []
    for raw_id in ids or []:
        sid = safe_int(raw_id)
        if sid is None:
            continue
        rec = lookup.get(sid, {})
        row: Dict[str, Any] = {
            "id": sid,
            "source": source,
            "special_icon": safe_int(rec.get("special_icon")) or 0,
        }
        if rec.get("skill_id") is not None:
            row["skill_id"] = safe_int(rec.get("skill_id"))
        if rec.get("world_skill_id") is not None:
            row["world_skill_id"] = safe_int(rec.get("world_skill_id"))
        result.append(row)
    return result


def _is_attack_linked_skill(row: Dict[str, Any], special: Optional[int] = None) -> bool:
    """Return True only for a real skilled attack.

    Some normal attacks in game_config carry special_icon=1/2 for UI purposes even
    though they do not have a skill_id. Those must NOT be treated as Active/Mix
    skilled attacks.
    """
    if row.get("skill_id") is None:
        return False
    value = row.get("special_icon")
    if special is None:
        return value in (1, 2)
    return value == special


def classify_skill_filters(
    passive: List[Dict[str, Any]],
    post: List[Dict[str, Any]],
    attacks: List[Dict[str, Any]],
    trainable_attacks: List[Dict[str, Any]],
) -> List[str]:
    found = set()

    # Passive + Post blue icons are intentionally one filter category.
    if any(s.get("special_icon") == 1 for s in passive + post):
        found.add("passive")

    # Mix is a visual/behavior category and may come from Passive/Post OR a
    # real attack-linked skilled attack.
    if any(s.get("special_icon") == 2 for s in passive + post) or any(
        _is_attack_linked_skill(s, 2) for s in attacks + trainable_attacks
    ):
        found.add("mix")

    # Active means the dragon has a real skilled attack. A Mix attack is still
    # an active/skilled attack, so both special_icon 1 and 2 belong here.
    if any(_is_attack_linked_skill(s) for s in attacks + trainable_attacks):
        found.add("active")

    return [x for x in ("active", "passive", "mix") if x in found]


def classify_attack_skill_availability(
    attacks: List[Dict[str, Any]],
    trainable_attacks: List[Dict[str, Any]],
) -> List[str]:
    # This section applies ONLY to real attack-linked Active/Mix skills.
    # Passive/Post skills do not participate.
    has_default = any(_is_attack_linked_skill(s) for s in attacks)
    has_trained = any(_is_attack_linked_skill(s) for s in trainable_attacks)

    found: List[str] = []

    # ALL — a real skilled attack exists in default attacks, trainable attacks, or both.
    if has_default or has_trained:
        found.append("all")

    # Upgradable — the SAME SLOT has a real skilled attack in default + trainable,
    # and the attack IDs are different. Same ID means the existing skill cannot be
    # trained into another version and therefore is not an upgrade.
    slot_count = min(len(attacks), len(trainable_attacks))
    has_upgrade = any(
        _is_attack_linked_skill(attacks[i])
        and _is_attack_linked_skill(trainable_attacks[i])
        and str(attacks[i].get("id")) != str(trainable_attacks[i].get("id"))
        for i in range(slot_count)
    )
    if has_upgrade:
        found.append("upgradable")

    # Trained Only — no real skilled attack by default; one appears after training.
    if not has_default and has_trained:
        found.append("trained_only")

    return found


def representative_skill_icon(
    passive: List[Dict[str, Any]],
    post: List[Dict[str, Any]],
    attacks: List[Dict[str, Any]],
    trainable_attacks: List[Dict[str, Any]],
) -> str:

    # Priority:
    # Passive -> Post -> Default Skilled Attack -> Trainable Skilled Attack.
    # Passive/Post keep their existing behavior. Attack-linked icons require
    # skill_id so ordinary attacks with special_icon metadata are ignored.

    for s in passive:
        special = s.get("special_icon")

        if special == 1:
            return "skills-icon/ic-skills-passive-special-1.png"

        if special == 2:
            return "skills-icon/ic-skills-mix-special-1.png"

    for s in post:
        special = s.get("special_icon")

        if special == 1:
            return "skills-icon/ic-post-skills.png"

        if special == 2:
            return "skills-icon/ic-post-skills-mix-special.png"

    for source in (attacks, trainable_attacks):
        for s in source:
            if _is_attack_linked_skill(s, 1):
                return "skills-icon/ic-skills-special-1.png"

            if _is_attack_linked_skill(s, 2):
                return "skills-icon/ic-skills-mix-special-1.png"

    return "skills-icon/ic-skill-empty.png"



def config_ratio(value: Any) -> float:
    """Decode config ratios stored either as decimals or millionths."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    return number / 1_000_000.0 if abs(number) > 10 else number


def stat_health_at_level(base_life: Optional[int], level: int) -> Optional[int]:
    if base_life is None:
        return None
    return math.floor(base_life * (level ** 1.25) / 50.0) + 10


def stat_damage_at_level(base_attack: Optional[int], level: int) -> Optional[int]:
    if base_attack is None:
        return None
    return math.floor(base_attack * ((level ** 1.5) + 10.0) / 250.0)


def build_stat_config(config: Dict[str, Any]) -> Dict[str, Any]:
    powerup = config.get("tree_of_life_powerup") or {}
    empower_by_rarity = {
        str(row.get("rarity") or "").upper(): config_ratio(row.get("stats_boost"))
        for row in (powerup.get("grades_by_rarity") or [])
        if isinstance(row, dict) and row.get("rarity")
    }
    empower_by_dragon = {
        int(row.get("dragon")): config_ratio(row.get("stats_boost"))
        for row in (powerup.get("grades_by_dragon") or [])
        if isinstance(row, dict) and safe_int(row.get("dragon")) is not None
    }
    max_empower = max(
        [safe_int(row.get("value")) or 0 for row in (powerup.get("parameters") or [])
         if isinstance(row, dict) and row.get("name") == "MAX_EMPOWER_GRADE"] or [5]
    )
    max_level = max(
        [safe_int(row.get("max_level")) or 0
         for row in ((config.get("max_dragon_levels") or {}).get("max_levels_by_grade") or [])
         if isinstance(row, dict)] or [70]
    )

    rank_rows = [
        row for row in ((config.get("dragon_rank_up") or {}).get("dragon_rank_up") or [])
        if isinstance(row, dict) and row.get("active") and row.get("new_system")
    ]
    max_rank_row = max(rank_rows, key=lambda row: safe_int(row.get("rank")) or 0, default={})
    max_rank = safe_int(max_rank_row.get("rank")) or 12
    max_rank_bonus = safe_int(max_rank_row.get("bonus")) or 70

    perks_cfg = config.get("perks") or {}
    ability_lookup = index_by_id(perks_cfg.get("abilities") or [])
    basic_perk_boosts: Dict[str, Dict[str, float]] = {"health": {}, "damage": {}}
    for perk in (perks_cfg.get("perks") or []):
        if not isinstance(perk, dict) or perk.get("type") != "combat":
            continue
        if perk.get("available_for_dragons"):
            continue
        if safe_int(perk.get("rarity_level")) != 1:
            continue
        max_by_rarity = {
            str(row.get("rarity") or "").upper(): safe_int(row.get("max")) or 0
            for row in (perk.get("max_perks") or []) if isinstance(row, dict)
        }
        for ability_id in (perk.get("abilities") or []):
            ability = ability_lookup.get(safe_int(ability_id) or -1, {})
            ability_type = str(ability.get("type") or "")
            key = "health" if ability_type == "dragon_life_boost" else "damage" if ability_type == "dragon_attack_boost" else None
            if not key:
                continue
            per_stack = (float((ability.get("parameters") or {}).get("value") or 0) / 100.0)
            for rarity, maximum in max_by_rarity.items():
                basic_perk_boosts[key][rarity] = max(basic_perk_boosts[key].get(rarity, 0.0), per_stack * maximum)

    battle = config.get("battle_parameters") or {}
    speed_by_rarity = {
        str(row.get("rarity") or "").upper(): row
        for row in (battle.get("speed") or []) if isinstance(row, dict) and row.get("rarity")
    }
    speed_overrides = {
        int(row.get("id")): row
        for row in (battle.get("speed_override") or [])
        if isinstance(row, dict) and safe_int(row.get("id")) is not None
    }

    return {
        "empower_by_rarity": empower_by_rarity,
        "empower_by_dragon": empower_by_dragon,
        "max_empower": max_empower,
        "max_level": max_level,
        "max_rank": max_rank,
        "max_rank_bonus": max_rank_bonus,
        "basic_perk_boosts": basic_perk_boosts,
        "speed_by_rarity": speed_by_rarity,
        "speed_overrides": speed_overrides,
    }


def dragon_stat_profiles(item: Dict[str, Any], rarity: str, stat_cfg: Dict[str, Any]) -> Dict[str, Any]:
    did = safe_int(item.get("id"))
    raw_health = safe_int(item.get("base_life"))
    raw_damage = safe_int(item.get("base_attack"))
    raw_speed = safe_int(item.get("speed"))

    # Level 1 Stats shown by Dragon Overview:
    # Level 1 with no stat-boosting attributes applied.
    level_1 = 1

    max_level = int(stat_cfg.get("max_level") or 70)
    max_empower = int(stat_cfg.get("max_empower") or 5)
    max_rank = int(stat_cfg.get("max_rank") or 12)
    max_rank_bonus = float(stat_cfg.get("max_rank_bonus") or 70) / 100.0
    empower_rate = stat_cfg.get("empower_by_dragon", {}).get(
        did, stat_cfg.get("empower_by_rarity", {}).get(rarity, 0.0)
    )

    level70_health = stat_health_at_level(raw_health, max_level)
    level70_damage = stat_damage_at_level(raw_damage, max_level)
    hp_perk = float(stat_cfg.get("basic_perk_boosts", {}).get("health", {}).get(rarity, 0.0))
    dmg_perk = float(stat_cfg.get("basic_perk_boosts", {}).get("damage", {}).get(rarity, 0.0))

    hp_multiplier = 1.0 + (empower_rate * max_empower) + max_rank_bonus + hp_perk
    dmg_multiplier = 1.0 + (empower_rate * max_empower) + max_rank_bonus + dmg_perk
    max_health = math.floor(level70_health * hp_multiplier) if level70_health is not None else None
    max_damage = math.floor(level70_damage * dmg_multiplier) if level70_damage is not None else None

    speed_rule = None
    speed_override_id = safe_int(item.get("speed_override"))
    if speed_override_id is not None:
        speed_rule = stat_cfg.get("speed_overrides", {}).get(speed_override_id)
    if not speed_rule:
        speed_rule = stat_cfg.get("speed_by_rarity", {}).get(rarity)
    level_1_speed = raw_speed
    if raw_speed is not None and speed_rule:
        level_1_speed = raw_speed + level_1 * (safe_int(speed_rule.get("level_bonus")) or 0)

    level_1_stats = {
        "health": stat_health_at_level(raw_health, level_1),
        "damage": stat_damage_at_level(raw_damage, level_1),
        "speed": level_1_speed,
    }

    max_speed = None
    if raw_speed is not None and speed_rule:
        max_speed = (
            raw_speed
            + max_level * (safe_int(speed_rule.get("level_bonus")) or 0)
            + max_empower * (safe_int(speed_rule.get("empower_bonus")) or 0)
            + max_rank * (safe_int(speed_rule.get("rank_bonus")) or 0)
        )

    return {
        "health": raw_health,
        "damage": raw_damage,
        "speed": raw_speed,
        "raw": {"health": raw_health, "damage": raw_damage, "speed": raw_speed},
        "level_1": level_1_stats,
        # Backward-compatible alias for older DCIC clients.
        # It now represents the same Level 1 / no-attributes profile.
        "in_game_base": level_1_stats,
        "in_game_max": {"health": max_health, "damage": max_damage, "speed": max_speed},
        "calculation": {
            "base_level": level_1,
            "level_1": level_1,
            "max_level": max_level,
            "max_empower": max_empower,
            "max_rank": max_rank,
            "max_rank_bonus_percent": int(round(max_rank_bonus * 100)),
            "empower_boost_per_grade": empower_rate,
            "basic_health_perk_boost": hp_perk,
            "basic_damage_perk_boost": dmg_perk,
        },
    }


def localized_value(loc: Dict[str, str], key: Any, fallback: str = "") -> str:
    if key is None:
        return fallback
    return str(loc.get(str(key)) or fallback or "")


def load_skill_description_overrides(path: Path = SKILL_DESCRIPTION_OVERRIDES_PATH) -> Dict[int, str]:
    """Load optional manual Skill Definition description corrections keyed by skill ID."""
    if not path.exists():
        return {}
    raw = load_json(path)
    if not isinstance(raw, dict):
        return {}
    out: Dict[int, str] = {}
    for raw_id, value in raw.items():
        sid = safe_int(raw_id)
        if sid is None:
            continue
        if isinstance(value, str):
            description = value.strip()
        elif isinstance(value, dict):
            description = str(value.get("description") or "").strip()
        else:
            description = ""
        if description:
            out[sid] = description
    return out


def resolved_skill_description(
    skill_def: Dict[str, Any],
    loc: Dict[str, str],
    overrides: Optional[Dict[int, str]] = None,
) -> str:
    """Resolve a display description while tolerating bad config localization pointers.

    Priority:
      1. Manual override by Skill Definition ID.
      2. Configured tid_description when it resolves to useful text.
      3. tid_skill_name_* -> tid_skill_description_* sibling localization.
      4. For trained/TR variants, the base skill description.
      5. Configured description as a final compatibility fallback.

    Dragon City occasionally points tid_description at tid_name. The automatic sibling
    lookup fixes those cases without hard-coding individual skills.
    """
    sid = safe_int(skill_def.get("id"))
    if sid is not None and overrides and overrides.get(sid):
        return str(overrides[sid]).strip()

    name_key = str(skill_def.get("tid_name") or "").strip()
    desc_key = str(skill_def.get("tid_description") or "").strip()
    name = localized_value(loc, name_key, "").strip()
    configured = localized_value(loc, desc_key, "").strip()

    configured_is_name = bool(configured and name and configured.casefold() == name.casefold())
    if configured and not configured_is_name:
        return configured

    if name_key.startswith("tid_skill_name_"):
        sibling_key = name_key.replace("tid_skill_name_", "tid_skill_description_", 1)
        sibling = localized_value(loc, sibling_key, "").strip()
        if sibling and (not name or sibling.casefold() != name.casefold()):
            return sibling

        # Trained variants do not always have their own description key. Reuse the
        # base description when the skill is the same mechanic with an upgraded name.
        base_key = re.sub(r"(?i)(?:_trained|_tr)$", "", sibling_key)
        if base_key != sibling_key:
            base_description = localized_value(loc, base_key, "").strip()
            if base_description and (not name or base_description.casefold() != name.casefold()):
                return base_description

    return configured


def price_entries(raw: Any) -> List[Dict[str, Any]]:
    if not isinstance(raw, dict):
        return []
    labels = {"c": "Gems", "g": "Gold", "f": "Food"}
    out: List[Dict[str, Any]] = []
    for currency, value in raw.items():
        amount = safe_int(value)
        if amount is None:
            continue
        out.append({
            "currency": str(currency),
            "label": labels.get(str(currency), str(currency)),
            "amount": amount,
        })
    return out


def attack_detail(
    ids: Iterable[Any],
    attack_lookup: Dict[int, Dict[str, Any]],
    skill_def_lookup: Dict[int, Dict[str, Any]],
    loc: Dict[str, str],
) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for raw_id in ids or []:
        aid = safe_int(raw_id)
        if aid is None:
            continue
        rec = attack_lookup.get(aid, {})
        skill_id = safe_int(rec.get("skill_id"))
        skill_def = skill_def_lookup.get(skill_id or -1, {}) if skill_id is not None else {}
        name = localized_value(loc, rec.get("name_key"), str(rec.get("name") or f"Attack {aid}"))
        if skill_def.get("tid_name"):
            name = localized_value(loc, skill_def.get("tid_name"), name)
        out.append({
            "id": aid,
            "name": name,
            "element": str(rec.get("element") or "ph"),
            "button_style": safe_int(rec.get("button_style")) or 1,
            "special_icon": safe_int(rec.get("special_icon")) or 0,
            "skill_id": skill_id,
            "cooldown": safe_int(skill_def.get("cooldown")) if skill_id is not None else None,
            "damage": safe_int(rec.get("ui_damage")) or safe_int(rec.get("damage")),
            "training_time": safe_int(rec.get("training_time")),
        })
    return out


def logical_skill_details(
    passive_ids: Iterable[Any],
    post_ids: Iterable[Any],
    attack_ids: Iterable[Any],
    trainable_attack_ids: Iterable[Any],
    passive_lookup: Dict[int, Dict[str, Any]],
    post_lookup: Dict[int, Dict[str, Any]],
    attack_lookup: Dict[int, Dict[str, Any]],
    skill_def_lookup: Dict[int, Dict[str, Any]],
    loc: Dict[str, str],
    skill_description_overrides: Optional[Dict[int, str]] = None,
) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    seen = set()

    def add_passive_or_post(record_id: int, rec: Dict[str, Any], source: str) -> None:
        sid = safe_int(rec.get("skill_id"))
        if sid is None:
            return
        special = safe_int(rec.get("special_icon")) or 0
        kind = "mix" if special == 2 else "passive"
        key = (source, record_id, kind)
        if key in seen:
            return
        seen.add(key)
        sdef = skill_def_lookup.get(sid, {})
        name = localized_value(loc, sdef.get("tid_name"), str(rec.get("name") or f"Skill {record_id}"))
        description = resolved_skill_description(sdef, loc, skill_description_overrides)
        out.append({
            "id": record_id,
            "skill_definition_id": sid,
            "name": name,
            "description": description,
            "type": kind,
            "source": source,
            "link_type": "passive_skill_id" if source == "passive" else "post_skill_id",
            "link_id": record_id,
        })

    for raw_id in passive_ids or []:
        rid = safe_int(raw_id)
        if rid is not None:
            add_passive_or_post(rid, passive_lookup.get(rid, {}), "passive")
    for raw_id in post_ids or []:
        rid = safe_int(raw_id)
        if rid is not None:
            add_passive_or_post(rid, post_lookup.get(rid, {}), "post")

    for raw_id in list(attack_ids or []) + list(trainable_attack_ids or []):
        aid = safe_int(raw_id)
        if aid is None:
            continue
        rec = attack_lookup.get(aid, {})
        sid = safe_int(rec.get("skill_id"))
        if sid is None:
            continue
        special = safe_int(rec.get("special_icon")) or 0
        if special not in (1, 2):
            continue
        kind = "mix" if special == 2 else "active"
        key = ("attack", aid, kind)
        if key in seen:
            continue
        seen.add(key)
        sdef = skill_def_lookup.get(sid, {})
        name = localized_value(loc, sdef.get("tid_name"), localized_value(loc, rec.get("name_key"), str(rec.get("name") or f"Attack {aid}")))
        description = resolved_skill_description(sdef, loc, skill_description_overrides)
        out.append({
            "id": aid,
            "attack_id": aid,
            "skill_definition_id": sid,
            "name": name,
            "description": description,
            "type": kind,
            "source": "attack",
            "link_type": "attack_id",
            "link_id": aid,
        })

    return out

def build_normal_breeding_lookup(rows: Any) -> Dict[int, Dict[str, Any]]:
    """Choose one canonical normal-breeding element recipe per dragon.

    The config stores results as dragon_id_1, dragon_id_2, ... within an element-pair row.
    Prefer an unempowered result, then the earliest result slot, then the earliest recipe row.
    """
    candidates: Dict[int, List[tuple]] = {}
    if not isinstance(rows, list):
        return {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        e1, e2 = row.get("element_one"), row.get("element_two")
        if not e1 or not e2:
            continue
        for key, value in row.items():
            if not str(key).startswith("dragon_id_"):
                continue
            try:
                slot = int(str(key).split("_")[-1])
            except ValueError:
                continue
            did = safe_int(value)
            if did is None:
                continue
            empower = safe_int(row.get(f"empower_{slot}")) or 0
            rank = (1 if empower else 0, slot, safe_int(row.get("id")) or 999999)
            candidates.setdefault(did, []).append((rank, {"elements": [str(e1), str(e2)], "recipe_id": safe_int(row.get("id"))}))
    out: Dict[int, Dict[str, Any]] = {}
    for did, values in candidates.items():
        values.sort(key=lambda x: x[0])
        out[did] = values[0][1]
    return out


def skin_details(
    rows: Iterable[Dict[str, Any]],
    loc: Dict[str, str],
) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        img_name = str(row.get("img_name_mobile") or row.get("img_name_canvas") or "")
        out.append({
            "id": safe_int(row.get("id")),
            "name": localized_value(loc, row.get("skin_name_tid"), f"Skin {row.get('id', '')}"),
            "description": localized_value(loc, row.get("skin_description_tid"), ""),
            # Dragon Details uses the compact portrait/thumbnail art for skin rows,
            # not the full-body UI asset.
            "image": f"{DRAGON_CDN}thumb_{img_name}_3.png" if img_name else "",
        })
    return out


def world_food_production(
    passive: List[Dict[str, Any]],
    post: List[Dict[str, Any]],
    world_skill_lookup: Dict[int, Dict[str, Any]],
    world_effect_lookup: Dict[int, Dict[str, Any]],
) -> Dict[str, Any]:
    total = 0
    intervals: List[int] = []
    for row in passive + post:
        wsid = safe_int(row.get("world_skill_id"))
        if wsid is None:
            continue
        world_skill = world_skill_lookup.get(wsid, {})
        for effect_id in world_skill.get("effects") or []:
            eid = safe_int(effect_id)
            effect = world_effect_lookup.get(eid or -1, {})
            if effect.get("effect_type") != "RESOURCE_PRODUCTION":
                continue
            params = effect.get("parameters") or {}
            resources = params.get("resource") or {}
            amount = safe_int(resources.get("f"))
            if amount is not None:
                total += amount
            interval = safe_int(effect.get("interval_time"))
            if interval:
                intervals.append(interval)
    return {
        "food_per_min": total if total > 0 else None,
        "food_collect_interval": min(intervals) if intervals else None,
    }


def main() -> None:
    config = load_json(CONFIG_PATH)
    loc = localization_map(load_json(LOCALIZATION_PATH))
    skill_description_overrides = load_skill_description_overrides()

    skills = config.get("skills") or {}
    passive_lookup = index_by_id(skills.get("passive") or [])
    post_lookup = index_by_id(skills.get("post") or [])
    attack_lookup = index_by_id(skills.get("attacks") or [])
    skill_def_lookup = index_by_id(skills.get("skills") or [])
    world_skill_lookup = index_by_id(skills.get("world_skills") or [])
    world_effect_lookup = index_by_id(skills.get("world_effects") or [])
    stat_cfg = build_stat_config(config)

    all_dragon_items = {
        int(row.get("id")): row
        for row in (config.get("items") or [])
        if isinstance(row, dict) and row.get("group_type") == "DRAGON" and safe_int(row.get("id")) is not None
    }

    breeding_cfg = config.get("breeding") or {}
    soulmate_lookup = {
        int(row.get("dragon_id")): row
        for row in (breeding_cfg.get("soulmates") or [])
        if isinstance(row, dict) and safe_int(row.get("dragon_id")) is not None
    }
    normal_breeding_lookup = build_normal_breeding_lookup(breeding_cfg.get("breeding") or [])

    sanctuary_lookup: Dict[int, Dict[str, Any]] = {}
    for level in ((config.get("sanctuary_breeding") or {}).get("upgrades_config") or []):
        if not isinstance(level, dict):
            continue
        for dragon_id in level.get("dragons_unlocked") or []:
            sid = safe_int(dragon_id)
            if sid is not None:
                sanctuary_lookup[sid] = {"level": safe_int(level.get("id")), "item_id": safe_int(level.get("item_id"))}

    skins_by_dragon: Dict[int, List[Dict[str, Any]]] = {}
    for skin in ((config.get("dragon_skins") or {}).get("dragon_skins") or []):
        if not isinstance(skin, dict):
            continue
        skin_did = safe_int(skin.get("dragon_id"))
        if skin_did is not None:
            skins_by_dragon.setdefault(skin_did, []).append(skin)

    family_boost = config.get("dragon_family_boost") or {}
    family_dragon_lookup = index_by_id(family_boost.get("dragons") or [])
    family_defs = {
        str(row.get("id")): row
        for row in (family_boost.get("families") or [])
        if isinstance(row, dict) and row.get("id") is not None
    }

    book_lookup = {
        int(row.get("dragon_id")): row
        for row in ((config.get("dragon_book") or {}).get("collection_numbers") or [])
        if isinstance(row, dict) and safe_int(row.get("dragon_id")) is not None
    }

    tol = config.get("tree_of_life") or {}
    summon_dragon_lookup = {
        int(row.get("dragon_id")): row
        for row in (tol.get("dragonid_summon_time") or [])
        if isinstance(row, dict) and safe_int(row.get("dragon_id")) is not None
    }
    summon_rarity_lookup = {
        str(row.get("rarity")): row
        for row in (tol.get("rarity_summon_time") or [])
        if isinstance(row, dict) and row.get("rarity") is not None
    }
    non_summonable = {
        int(row.get("dragon_id"))
        for row in (tol.get("non_summonable_dragons") or [])
        if (
                isinstance(row, dict)
                and safe_int(row.get("dragon_id")) is not None
                and not row.get("unlock_system_id")
            )
    }

    dragons: List[Dict[str, Any]] = []
    family_filter_defs: Dict[str, Dict[str, Any]] = {}

    for item_index, item in enumerate(config.get("items") or []):
        if not isinstance(item, dict) or item.get("group_type") != "DRAGON":
            continue
        did = safe_int(item.get("id"))
        if did is None:
            continue

        rarity = str(item.get("dragon_rarity") or "").upper()
        attrs = [str(x) for x in (item.get("attributes") or []) if x]
        localized_name = loc.get(f"tid_unit_{did}_name") or item.get("name") or f"Dragon {did}"

        passive = skill_summary(item.get("passive_skills") or [], passive_lookup, "passive")
        post = skill_summary(item.get("post_skills") or [], post_lookup, "post")
        attacks = skill_summary(item.get("attacks") or [], attack_lookup, "attack")
        trainable_attacks = skill_summary(item.get("trainable_attacks") or [], attack_lookup, "trainable_attack")
        skill_filters = classify_skill_filters(passive, post, attacks, trainable_attacks)
        attack_skill_availability = classify_attack_skill_availability(attacks, trainable_attacks)
        skill_icon = representative_skill_icon(passive, post, attacks, trainable_attacks)

        produces_food = any(s.get("world_skill_id") is not None for s in passive)
        production = "gold_food" if produces_food else "gold"
        production_icon = "resources/ic-gold-food.png" if produces_food else "resources/ic-gold.png"

        tags = [str(t) for t in (item.get("tags") or [])]
        normalized_tags = {str(t).strip().lower() for t in tags}

        # Primary family shown on the card. dragon_family_boost keeps visual priority.
        family: Optional[Dict[str, Any]] = None
        family_dragon = family_dragon_lookup.get(did)
        if family_dragon:
            fam_id = str(family_dragon.get("family") or "")
            fam_def = family_defs.get(fam_id, {})
            remote = ((fam_def.get("icon_asset") or {}).get("remote") if isinstance(fam_def.get("icon_asset"), dict) else None)
            asset = family_asset_from_remote(remote)
            key = family_key_from_asset(asset, fam_id)
            family = {
                "key": key,
                "id": fam_id,
                "label": localized_value(
                    loc,
                    fam_def.get("tid_name"),
                    FAMILY_LABELS.get(key, fam_id),
                ),
                "team": str(fam_def.get("icon_number") or ""),
                "asset": asset,
                "source": "family_boost",
            }
        else:
            for tag in FALLBACK_FAMILY_PRIORITY:
                if tag in tags:
                    key, asset = FALLBACK_FAMILY_TAGS[tag]
                    family = {
                        "key": key,
                        "id": tag,
                        "label": FAMILY_LABELS.get(key, tag),
                        "team": "",
                        "asset": asset,
                        "source": "tag",
                    }
                    break

        # Multiple family filters are allowed even though only the primary family
        # above is displayed on the card.
        family_filters: List[str] = []

        if family and family.get("asset") and family.get("asset") != "family-badge/ic-vip-twins.png":
            primary_key = str(family["key"])
            family_filters.append(primary_key)
            family_filter_defs.setdefault(
                primary_key,
                {
                    "key": primary_key,
                    "asset": family["asset"],
                    "label": FAMILY_LABELS.get(primary_key, family.get("id") or primary_key),
                },
            )

        # Tag-based family filters.
        # These are additional filters only and do not replace the family shown on the card.

        if "vip" in normalized_tags:
            vip_key, vip_asset = FALLBACK_FAMILY_TAGS["VIP"]

            if vip_key not in family_filters:
                family_filters.append(vip_key)

            family_filter_defs.setdefault(
                vip_key,
                {
                    "key": vip_key,
                    "asset": vip_asset,
                    "label": FAMILY_LABELS.get(vip_key, "VIP"),
                },
            )

        if "mythical" in normalized_tags:
            mythical_key, mythical_asset = FALLBACK_FAMILY_TAGS["Mythical"]

            if mythical_key not in family_filters:
                family_filters.append(mythical_key)

            family_filter_defs.setdefault(
                mythical_key,
                {
                    "key": mythical_key,
                    "asset": mythical_asset,
                    "label": FAMILY_LABELS.get(mythical_key, "Mythical"),
                },
            )

        book = book_lookup.get(did, {})
        summon_rec = summon_dragon_lookup.get(did) or summon_rarity_lookup.get(rarity) or {}
        summon_time = safe_int(summon_rec.get("summon_time_seconds"))
        summon_orbs = safe_int(item.get("seeds_to_summon"))

        if did in non_summonable:
            orb_filter = "non_summonable"
        elif summon_orbs is None:
            orb_filter = None
        elif summon_orbs > 500:
            orb_filter = "500+"
        elif summon_orbs in (100, 150, 200, 500):
            orb_filter = str(summon_orbs)
        else:
            orb_filter = str(summon_orbs)

        img_name = str(item.get("img_name_mobile") or item.get("img_name") or "")
        adult_asset = DRAGON_ASSET_OVERRIDES.get(did, img_name)
        adult_full_image = DRAGON_FULL_BODY_OVERRIDES.get(
            did,
            f"{DRAGON_FULL_BODY_CDN}ui_{adult_asset}_3@2x.png" if adult_asset else "",
        )
        adult_thumb_url = f"{DRAGON_CDN}thumb_{img_name}_3.png" if img_name else ""

        # If the config has no thumbnail at all (currently Placeholder VIP), use the
        # custom full-body override as a safe fallback for UIs that still read adult_image.
        if not adult_thumb_url and adult_full_image:
            adult_thumb_url = adult_full_image

        if did in CURRENT_ELEMENT_OVERRIDES:
            current_display = CURRENT_ELEMENT_OVERRIDES[did]
        else:
            current_display = [f"{code}-1" for code in attrs]
        old_display = OLD_ELEMENT_OVERRIDES.get(did, [f"{code}-0" for code in attrs])

        # Detail-popup data -------------------------------------------------
        # Invalid/unreleased placeholder dragons must use the asset declared by
        # game_config inside Overview. Custom DCIC image overrides remain available
        # elsewhere (e.g. All Dragons cards) but are intentionally ignored here.
        stage_base_asset = img_name
        detail_adult_image = (
            f"{DRAGON_FULL_BODY_CDN}ui_{stage_base_asset}_3@2x.png"
            if did in INVALID_DRAGON_IDS and stage_base_asset
            else adult_full_image
        )
        stage_images = {
            "egg": f"{DRAGON_FULL_BODY_CDN}ui_{stage_base_asset}_0@2x.png" if stage_base_asset else "",
            "baby": f"{DRAGON_FULL_BODY_CDN}ui_{stage_base_asset}_1@2x.png" if stage_base_asset else "",
            "adult": detail_adult_image,
        }

        # The popup uses the dragon's actual/current attributes. Old Symbols only
        # switches code-1 -> code-0; historical special-element overrides are not used here.
        detail_elements = list(attrs)

        food_prod = world_food_production(passive, post, world_skill_lookup, world_effect_lookup)

        soulmate = soulmate_lookup.get(did)
        sanctuary = sanctuary_lookup.get(did)
        normal_recipe = normal_breeding_lookup.get(did)
        breeding_sources: List[str] = []
        if bool(item.get("breedable")) or normal_recipe:
            breeding_sources.append("hybrid")
        if sanctuary:
            breeding_sources.append("sanctuary")
        if soulmate:
            breeding_sources.append("soulmate")

        breeding_type: Optional[str] = None
        breeding_formula_elements: List[str] = []
        breeding_parents: List[Dict[str, Any]] = []
        min_parent_level: Optional[int] = None

        # Keep one primary formula for the popup, while preserving every breeding
        # source in breeding_sources/types for filters and source-aware UIs.
        if soulmate:
            breeding_type = "soulmate"
            min_parent_level = safe_int(soulmate.get("level_parents"))
            for parent_key in ("parent_1_id", "parent_2_id"):
                parent_id = safe_int(soulmate.get(parent_key))
                if parent_id is None:
                    continue
                parent_item = all_dragon_items.get(parent_id, {})
                parent_img = str(parent_item.get("img_name_mobile") or parent_item.get("img_name") or "")
                breeding_parents.append({
                    "id": parent_id,
                    "name": loc.get(f"tid_unit_{parent_id}_name") or parent_item.get("name") or f"Dragon {parent_id}",
                    "image": f"{DRAGON_CDN}thumb_{parent_img}_3.png" if parent_img else "",
                })
        elif sanctuary:
            breeding_type = "sanctuary"
            breeding_formula_elements = list(attrs)
        elif "hybrid" in breeding_sources:
            breeding_type = "hybrid"
            if normal_recipe:
                breeding_formula_elements = list(normal_recipe.get("elements") or [])

        effective_breedable = bool(breeding_sources)

        detail_attacks = attack_detail(item.get("attacks") or [], attack_lookup, skill_def_lookup, loc)
        detail_trainable_attacks = attack_detail(item.get("trainable_attacks") or [], attack_lookup, skill_def_lookup, loc)
        detail_skills = logical_skill_details(
            item.get("passive_skills") or [],
            item.get("post_skills") or [],
            item.get("attacks") or [],
            item.get("trainable_attacks") or [],
            passive_lookup,
            post_lookup,
            attack_lookup,
            skill_def_lookup,
            loc,
            skill_description_overrides,
        )

        details = {
            "images": stage_images,
            "elements": detail_elements,
            "description": loc.get(f"tid_unit_{did}_description") or "",
            "income": {
                "gold_per_min": safe_int(item.get("starting_coins")),
                "food_per_min": food_prod.get("food_per_min"),
                "food_collect_interval": food_prod.get("food_collect_interval"),
            },
            "shop": {
                "in_shop": bool(item.get("in_store")),
                "price": price_entries(item.get("costs")),
            },
            "breeding": {
                "breedable": effective_breedable,
                "type": breeding_type,
                "types": breeding_sources,
                "formula_elements": breeding_formula_elements,
                "parents": breeding_parents,
                "min_parent_level": min_parent_level,
                "sanctuary_level": sanctuary.get("level") if sanctuary else None,
                "time": safe_int(item.get("breeding_time")),
            },
            "summoning": {
                "summonable": did not in non_summonable,
                "orbs": summon_orbs,
                "time": summon_time,
            },
            "hatching": {
                "time": safe_int(item.get("hatching_time")),
                "xp": safe_int(item.get("xp")),
                "sell": price_entries(item.get("sell_price")),
            },
            "skills": detail_skills,
            "attacks": {
                "basic": detail_attacks,
                "trained": detail_trainable_attacks,
            },
            "skins": skin_details(skins_by_dragon.get(did, []), loc),
        }

        dragon = {
            "id": did,
            "sort_id": DRAGON_SORT_ID_OVERRIDES.get(did, did),
            "is_invalid": did in INVALID_DRAGON_IDS,
            "item_index": item_index,
            "book_id": safe_int(book.get("number")) or safe_int(book.get("id")),
            "name": localized_name,
            "rarity": rarity,
            "tags": tags,
            "elements": attrs,
            "display_elements": {"current": current_display, "old": old_display},
            "adult_image": adult_thumb_url,
            "adult_asset": adult_asset,
            "full_body_image": adult_full_image,
            "production": production,
            "production_icon": production_icon,
            "breeding_sources": breeding_sources,
            "family": family,
            "family_filters": family_filters,
            "details": details,
            "skills": {
                "passive": passive,
                "post": post,
                "attacks": attacks,
                "trainable_attacks": trainable_attacks,
                "filters": skill_filters,
                "attack_availability": attack_skill_availability,
                "card_icon": skill_icon,
            },
            "orbs_to_summon": summon_orbs,
            "orb_filter": orb_filter,
            "summonable": did not in non_summonable,
            "times": {
                "hatching": safe_int(item.get("hatching_time")),
                "breeding": safe_int(item.get("breeding_time")),
                "summon": summon_time,
            },
            "stats": dragon_stat_profiles(item, rarity, stat_cfg),
        }
        dragons.append(dragon)

    # Newest means latest DRAGON entries by physical order in config.items, not highest numeric ID.
    newest_ids = [d["id"] for d in dragons[-20:]][::-1]

    present_elements = {el for d in dragons for el in d.get("elements", [])}
    element_filters = [
        {"code": code, "name": ELEMENT_NAMES.get(code, code)}
        for code in ELEMENT_ORDER
        if code in present_elements
    ]
    # Keep unknown future normal elements filterable rather than silently dropping them.
    for code in sorted(present_elements - set(ELEMENT_ORDER)):
        element_filters.append({"code": code, "name": ELEMENT_NAMES.get(code, code)})

    output = {
        "schema_version": 3,
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "meta": {
            "dragon_count": len(dragons),
            "valid_dragon_count": sum(1 for d in dragons if not d.get("is_invalid")),
            "invalid_dragon_count": sum(1 for d in dragons if d.get("is_invalid")),
            "newest_count": len(newest_ids),
            "level_1_stats_condition": {
                "level": 1,
                "attributes": "None",
            },
            "stats_display_condition": {
                "max_level": stat_cfg.get("max_level", 70),
                "max_empower": stat_cfg.get("max_empower", 5),
                "max_rank": stat_cfg.get("max_rank", 12),
                "rank_label": "Platinum III",
                "perks": "Max Basic Perks",
            },
        },
        "assets": {
            "base": "https://raw.githubusercontent.com/chaerulanwarreborn-star/dcic-assets/main/icons/",
            "rarity_dir": "rarity-badge/",
            "elements_dir": "elements-flag/",
        },
        "filters": {
            "rarities": [{"code": r, "name": RARITY_NAMES[r]} for r in RARITY_ORDER],
            "elements": element_filters,
            "skills": [
                {"key": "active", "label": "Active", "asset": "skills-icon/ic-skills-special-1.png"},
                {"key": "passive", "label": "Passive / Post", "asset": "skills-icon/ic-skills-passive-special-1.png"},
                {"key": "mix", "label": "Mix", "asset": "skills-icon/ic-skills-mix-special-1.png"},
            ],
            "active_skill_availability": [
                {"key": "all", "label": "ALL — Default & Trainable"},
                {"key": "upgradable", "label": "Upgradable"},
                {"key": "trained_only", "label": "Trained Only"},
            ],
            "invalid_dragons": [
                {"key": "hide", "label": "Hide Invalid Dragons"},
                {"key": "only", "label": "Only Show Invalid Dragons"},
            ],
            "families": sorted(
                family_filter_defs.values(),
                key=lambda x: (
                    FAMILY_ORDER_INDEX.get(str(x.get("key")), 999),
                    str(x.get("label", "")).lower(),
                ),
            ),
            "orbs": ["100", "150", "200", "500", "500+", "non_summonable"],
            "others": [
                {"key": "gold", "label": "Only Produce Gold", "asset": "resources/ic-gold.png"},
                {"key": "gold_food", "label": "Food Producers", "asset": "resources/ic-gold-food.png"},
                {"key": "breed_hybrid", "label": "Breedable — Hybrid", "asset": "source/ic-sourcebadge-breedable.png"},
                {"key": "breed_sanctuary", "label": "Breedable — Sanctuary", "asset": "source/ic-sourcebadge-breedingsanctuary.png"},
                {"key": "breed_soulmate", "label": "Breedable — Soulmates", "asset": "source/ic-sourcebadge-soulmates.png"},
                {"key": "shop", "label": "Available in Shop", "asset": "source/ic-sourcebadge-shop.png"},
                {"key": "has_skin", "label": "Has Skin", "asset": "text-icons/ic-dragon-skin-badge.png"},
            ],
            "production": [
                {"key": "gold", "label": "Only Produce Gold", "asset": "resources/ic-gold.png"},
                {"key": "gold_food", "label": "Food Producers", "asset": "resources/ic-gold-food.png"},
            ],
        },
        "newest_ids": newest_ids,
        "dragons": dragons,
    }

    OUTPUT_PATH.write_text(json.dumps(output, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"Wrote {OUTPUT_PATH.name}: {len(dragons)} dragons; newest={len(newest_ids)}")


if __name__ == "__main__":
    main()
