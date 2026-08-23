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
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "game_config.json"
LOCALIZATION_PATH = ROOT / "localization" / "dragon_city_localization_baseline_en.json"
OUTPUT_PATH = ROOT / "dragons.json"

DRAGON_CDN = "https://dci-static-s1.socialpointgames.com/static/dragoncity/mobile/ui/dragons/HD/"
DRAGON_FULL_BODY_CDN = "https://dci-static-s1.socialpointgames.com/static/dragoncity/mobile/ui/dragons/"
ASSET_ROOT = "icons/"

# Full-body image overrides for dragons whose default config asset is missing or unsuitable.
# Keep this keyed by Dragon ID so future overrides can be added without touching page code.
DRAGON_FULL_BODY_OVERRIDES: Dict[int, str] = {
    # Placeholder VIP has no img_name_mobile/img_name in game_config.
    9999: "https://raw.githubusercontent.com/chaerulanwarreborn-star/dcic-assets/main/override/ui_2191_dragon_default_3@2x.png",
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


def classify_skill_filters(passive: List[Dict[str, Any]], post: List[Dict[str, Any]], attacks: List[Dict[str, Any]]) -> List[str]:
    found = set()
    # Passive + post blue icons are intentionally one filter category.
    if any(s.get("special_icon") == 1 for s in passive + post):
        found.add("passive")
    # Any mix special (passive/post/attack) belongs to the same Mix filter.
    if any(s.get("special_icon") == 2 for s in passive + post + attacks):
        found.add("mix")
    if any(s.get("special_icon") == 1 for s in attacks):
        found.add("active")
    return [x for x in ("active", "passive", "mix") if x in found]


def representative_skill_icon(passive: List[Dict[str, Any]], post: List[Dict[str, Any]], attacks: List[Dict[str, Any]]) -> str:
    # Project rule: passive takes visual priority, then post, then skilled attacks.
    if passive:
        s = passive[0]
        if s.get("special_icon") == 1:
            return "skills-icon/ic-skills-passive-special-1.png"
        if s.get("special_icon") == 2:
            return "skills-icon/ic-skills-mix-special-1.png"
        return "skills-icon/ic-skill-empty.png"
    if post:
        s = post[0]
        if s.get("special_icon") == 1:
            return "skills-icon/ic-post-skills.png"
        if s.get("special_icon") == 2:
            return "skills-icon/ic-post-skills-mix-special.png"
        return "skills-icon/ic-skill-empty.png"
    for s in attacks:
        if s.get("special_icon") == 1:
            return "skills-icon/ic-skills-special-1.png"
        if s.get("special_icon") == 2:
            return "skills-icon/ic-skills-mix-special-1.png"
    return "skills-icon/ic-skill-empty.png"


def main() -> None:
    config = load_json(CONFIG_PATH)
    loc = localization_map(load_json(LOCALIZATION_PATH))

    skills = config.get("skills") or {}
    passive_lookup = index_by_id(skills.get("passive") or [])
    post_lookup = index_by_id(skills.get("post") or [])
    attack_lookup = index_by_id(skills.get("attacks") or [])

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
        if isinstance(row, dict) and safe_int(row.get("dragon_id")) is not None
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
        skill_filters = classify_skill_filters(passive, post, attacks)
        skill_icon = representative_skill_icon(passive, post, attacks)

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
        if summon_orbs is None:
            orb_filter = None
        elif summon_orbs > 500:
            orb_filter = "500+"
        elif summon_orbs in (100, 200, 250, 500):
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

        dragon = {
            "id": did,
            "item_index": item_index,
            "book_id": safe_int(book.get("number")) or safe_int(book.get("id")),
            "name": localized_name,
            "rarity": rarity,
            "elements": attrs,
            "display_elements": {"current": current_display, "old": old_display},
            "adult_image": adult_thumb_url,
            "adult_asset": adult_asset,
            "full_body_image": adult_full_image,
            "production": production,
            "production_icon": production_icon,
            "family": family,
            "family_filters": family_filters,
            "skills": {
                "passive": passive,
                "post": post,
                "attacks": attacks,
                "filters": skill_filters,
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
            "stats": {
                "health": safe_int(item.get("base_life")),
                "damage": safe_int(item.get("base_attack")),
                "speed": safe_int(item.get("speed")),
            },
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
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "meta": {
            "dragon_count": len(dragons),
            "newest_count": len(newest_ids),
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
            "families": sorted(
                family_filter_defs.values(),
                key=lambda x: (
                    FAMILY_ORDER_INDEX.get(str(x.get("key")), 999),
                    str(x.get("label", "")).lower(),
                ),
            ),
            "orbs": ["100", "200", "250", "500", "500+"],
            "production": [
                {"key": "gold", "label": "Gold", "asset": "resources/ic-gold.png"},
                {"key": "gold_food", "label": "Gold + Food", "asset": "resources/ic-gold-food.png"},
            ],
        },
        "newest_ids": newest_ids,
        "dragons": dragons,
    }

    OUTPUT_PATH.write_text(json.dumps(output, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"Wrote {OUTPUT_PATH.name}: {len(dragons)} dragons; newest={len(newest_ids)}")


if __name__ == "__main__":
    main()
