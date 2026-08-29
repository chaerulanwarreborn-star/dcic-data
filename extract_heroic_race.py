#!/usr/bin/env python3
"""Build heroic_race.json for DCIC Heroic/Mythical Race Guide (Batch 1.3).

The extractor keeps exact reward IDs, preserves limited-time lap reward metadata,
and uses localization for display names. Heroic Race and Mythical Race share the
same source section in game_config, so the visible race type is derived from each
island's island_title_tid.
"""
from __future__ import annotations

import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "game_config.json"
LOCALIZATION_PATH = ROOT / "localization" / "dragon_city_localization_baseline_en.json"
OUTPUT_PATH = ROOT / "heroic_race.json"
LEGACY_DIR = ROOT / "legacy" / "heroic_races"
OVERRIDES_PATH = ROOT / "heroic_race_archive_overrides.json"

STATIC_BASE = "https://dci-static-s1.socialpointgames.com/static/dragoncity/"
DRAGON_BASE = STATIC_BASE + "mobile/ui/dragons/HD/"
CHEST_BASE = STATIC_BASE + "mobile/ui/chests/"
DCIC_ICON_BASE = "https://raw.githubusercontent.com/chaerulanwarreborn-star/dcic-assets/main/icons/"

RARITY_FILE = {
    "C": "c", "R": "r", "V": "vr", "VR": "vr", "E": "e", "L": "l", "M": "m", "H": "h"
}
RARITY_NAME = {
    "C": "Common", "R": "Rare", "V": "Very Rare", "VR": "Very Rare",
    "E": "Epic", "L": "Legendary", "M": "Mythical", "H": "Heroic"
}
RANK_COIN_FILE = {
    "common": "common", "rare": "rare", "veryrare": "veryrare", "very_rare": "veryrare",
    "epic": "epic", "legendary": "legendary", "mythical": "mythical", "heroic": "heroic"
}
RANK_COIN_LOC = {
    "common": "tid_ruc_common", "rare": "tid_ruc_rare", "veryrare": "tid_ruc_very_rare",
    "very_rare": "tid_ruc_very_rare", "epic": "tid_ruc_epic", "legendary": "tid_ruc_legendary",
    "mythical": "tid_ruc_mythical", "heroic": "tid_ruc_heroic"
}
STICKER_LOC = {
    "s": "tid_chest_name_sticker_pack_s", "m": "tid_chest_name_sticker_pack_m",
    "l": "tid_chest_name_sticker_pack_l", "xl": "tid_chest_name_sticker_pack_xl"
}
ACE_LOC = {
    "1": "tid_chest_name_sticker_ace_pack_1", "2": "tid_chest_name_sticker_ace_pack_2",
    "3": "tid_chest_name_sticker_ace_pack_3", "4": "tid_chest_name_sticker_ace_pack_4",
    "5": "tid_chest_name_sticker_ace_pack_5"
}
PET_LOC = {
    "s": "tid_pet_food_pack_s", "m": "tid_pet_food_pack_m",
    "l": "tid_pet_food_pack_l", "xl": "tid_pet_food_pack_xl"
}
RESOURCE_INFO = {
    "c": ("Gems", "resources/ic-gem.png"),
    "g": ("Gold", "resources/ic-gold.png"),
    "f": ("Food", "resources/ic-food.png"),
    "xp": ("XP", "resources/ic-experience-xp.png"),
}

TOKEN_INFO = {
    "f_token": ("fire", "tid_token_fire_resource"),
    "p_token": ("plant", "tid_token_plant_resource"),
    "e_token": ("earth", "tid_token_earth_resource"),
    "w_token": ("water", "tid_token_sea_resource"),
    "el_token": ("electric", "tid_token_electric_resource"),
    "i_token": ("ice", "tid_token_ice_resource"),
    "m_token": ("metal", "tid_token_metal_resource"),
    "d_token": ("dark", "tid_token_dark_resource"),
    "li_token": ("light", "tid_token_light_resource"),
    "wr_token": ("war", "tid_token_war_resource"),
    "pu_token": ("pure", "tid_token_pure_resource"),
    "pr_token": ("primal", "tid_token_primal_resource"),
    "wi_token": ("wind", "tid_token_wind_resource"),
    "l_token": ("legend", "tid_token_legend_resource"),
}


def load_json(path: Path) -> Any:
    if not path.exists():
        raise SystemExit(f"Missing required file: {path.relative_to(ROOT)}")
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def normalize_localization(raw: Any) -> Dict[str, str]:
    if isinstance(raw, dict):
        return {str(k): str(v) for k, v in raw.items() if v is not None}
    out: Dict[str, str] = {}
    if isinstance(raw, list):
        for row in raw:
            if isinstance(row, dict):
                for key, value in row.items():
                    if value is not None:
                        out[str(key)] = str(value)
    return out


def as_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def iso(ts: int) -> str:
    if ts <= 0:
        return ""
    return datetime.fromtimestamp(ts, timezone.utc).isoformat().replace("+00:00", "Z")


def unique(values: Iterable[str]) -> List[str]:
    out: List[str] = []
    seen = set()
    for value in values:
        value = str(value or "").strip()
        if value and value not in seen:
            seen.add(value)
            out.append(value)
    return out


def loc_text(loc: Dict[str, str], key: Any, fallback: str = "") -> str:
    value = str(loc.get(str(key or ""), "") or "").strip()
    return value or fallback


def clean_dragon_name(name: str) -> str:
    return re.sub(r"\s+Dragon$", "", str(name or "").strip(), flags=re.I)


def dragon_candidates(img_name: str) -> List[str]:
    raw = str(img_name or "").strip()
    if not raw:
        return []
    return unique([
        f"{DRAGON_BASE}thumb_{raw}_3.png",
        f"{STATIC_BASE}mobile/ui/dragons/ui_{raw}_3@2x.png",
        f"{STATIC_BASE}mobile/ui/dragons/ui_{raw}_3.png",
    ])


def chest_candidates(chest_id: int, img_name: str) -> List[str]:
    raw = str(img_name or "").strip()
    if not raw:
        return []
    clean = re.sub(r"^ui_", "", raw, flags=re.I)
    clean = re.sub(r"@2x(?:\.png)?$", "", clean, flags=re.I)
    clean = re.sub(r"\.png$", "", clean, flags=re.I)
    after_chest = re.sub(r"^chest_", "", clean, flags=re.I)
    after_basic = re.sub(r"^(?:basic_chest_|chest_)", "", clean, flags=re.I)
    return unique([
        f"{CHEST_BASE}ui_{chest_id}_{clean}@2x.png",
        f"{CHEST_BASE}ui_{chest_id}_{clean}.png",
        f"{CHEST_BASE}ui_{clean}@2x.png",
        f"{CHEST_BASE}ui_{clean}.png",
        f"{CHEST_BASE}{clean}.png",
        f"{CHEST_BASE}ui_basic_chest_{clean}@2x.png",
        f"{CHEST_BASE}ui_{after_chest}@2x.png",
        f"{CHEST_BASE}ui_basic_chest_{after_chest}@2x.png",
        f"{CHEST_BASE}ui_{after_basic}@2x.png",
        f"{CHEST_BASE}ui_basic_chest_{after_basic}@2x.png",
    ])


def habitat_candidates(img_name: str) -> List[str]:
    raw = str(img_name or "").strip()
    if not raw:
        return []
    clean = re.sub(r"^ui_", "", raw, flags=re.I)
    clean = re.sub(r"@2x(?:\\.png)?$", "", clean, flags=re.I)
    clean = re.sub(r"\\.png$", "", clean, flags=re.I)
    return unique([
        f"{STATIC_BASE}mobile/ui/habitats/ui_{clean}@2x.png",
        f"{STATIC_BASE}mobile/ui/habitats/ui_{clean}.png",
        f"{STATIC_BASE}mobile/ui/habitats/{clean}@2x.png",
        f"{STATIC_BASE}mobile/ui/habitats/{clean}.png",
    ])


def item_candidates(img_name: str) -> List[str]:
    raw = str(img_name or "").strip()
    if not raw:
        return []
    return unique([
        f"{STATIC_BASE}mobile/ui/decorations/ui_{raw}@2x.png",
        f"{STATIC_BASE}mobile/ui/decorations/{raw}@2x.png",
        f"{STATIC_BASE}mobile/ui/decorations/{raw}.png",
        f"{STATIC_BASE}mobile/ui/decorations/HD/{raw}.png",
        f"{STATIC_BASE}mobile/ui/buildings/ui_{raw}@2x.png",
        f"{STATIC_BASE}mobile/ui/buildings/{raw}@2x.png",
        f"{STATIC_BASE}mobile/ui/buildings/{raw}.png",
        f"{STATIC_BASE}mobile/ui/buildings/HD/{raw}.png",
    ])


def make_dragon(dragon_id: int, items: Dict[int, Dict[str, Any]], loc: Dict[str, str], *, amount: int = 1) -> Dict[str, Any]:
    item = items.get(dragon_id, {})
    name = loc_text(loc, f"tid_unit_{dragon_id}_name", str(item.get("name") or f"Dragon {dragon_id}"))
    desc = loc_text(loc, f"tid_unit_{dragon_id}_description", "")
    img = str(item.get("img_name_mobile") or item.get("img_name") or "")
    cands = dragon_candidates(img)
    return {
        "id": dragon_id, "dragon_id": dragon_id, "kind": "dragon", "asset_kind": "dragon",
        "name": name, "description": desc, "amount": amount,
        "dragon_rarity": str(item.get("dragon_rarity") or "").upper(),
        "img_name_mobile": img, "image_url": cands[0] if cands else "",
        "localization_name_key": f"tid_unit_{dragon_id}_name",
        "localization_description_key": f"tid_unit_{dragon_id}_description",
    }


def make_chest(chest_id: int, chests: Dict[int, Dict[str, Any]], loc: Dict[str, str], amount: int = 1) -> Dict[str, Any]:
    chest = chests.get(chest_id, {})
    name_key = str(chest.get("chest_name_key") or chest.get("type_name_key") or "")
    desc_key = str(chest.get("description_key") or "")
    name = loc_text(loc, chest.get("chest_name_key")) or loc_text(loc, chest.get("type_name_key")) or f"Chest {chest_id}"
    desc = loc_text(loc, desc_key)
    img = str(chest.get("img_name") or "")
    cands = chest_candidates(chest_id, img)
    return {
        "id": chest_id, "chest_id": chest_id, "source_chest_id": chest_id,
        "kind": "chest", "asset_kind": "chest", "name": name, "description": desc, "amount": amount,
        "img_name": img, "source_chest_img_name": img, "image_url": cands[0] if cands else "",
        "localization_name_key": name_key, "localization_description_key": desc_key,
    }


def make_item(item_id: int, items: Dict[int, Dict[str, Any]], loc: Dict[str, str], amount: int = 1) -> Dict[str, Any]:
    item = items.get(item_id, {})
    name_key = f"tid_building_{item_id}_name"
    desc_key = f"tid_building_{item_id}_description"
    name = loc_text(loc, name_key, str(item.get("name") or f"Item {item_id}"))
    desc = loc_text(loc, desc_key, "")
    img = str(item.get("img_name_mobile") or item.get("img_name") or "")
    group_type = str(item.get("group_type") or "").upper()

    # Habitat rewards use a dedicated CDN directory instead of the normal
    # decorations/buildings directories. Keep the exact building ID intact.
    is_habitat = group_type == "HABITAT" or item_id == 10119
    if item_id == 10119 and not img:
        img = "10119_habitat_rainbow"

    cands = habitat_candidates(img) if is_habitat else item_candidates(img)
    return {
        "id": item_id, "item_id": item_id,
        "kind": "item", "asset_kind": "habitat" if is_habitat else "item",
        "name": name, "description": desc, "amount": amount,
        "img_name_mobile": img, "image_url": cands[0] if cands else "",
        "localization_name_key": name_key, "localization_description_key": desc_key,
    }


def make_orbs(dragon_id: int, amount: int, items: Dict[int, Dict[str, Any]], loc: Dict[str, str]) -> Dict[str, Any]:
    dragon = make_dragon(dragon_id, items, loc)
    rarity = str(dragon.get("dragon_rarity") or "").upper()
    token = RARITY_FILE.get(rarity, rarity.lower())
    dragon["kind"] = "dragon_orbs"
    dragon["asset_kind"] = "dragon_orbs"
    dragon["name"] = f"{clean_dragon_name(dragon['name'])} Orbs"
    dragon["amount"] = amount
    dragon["overlay_image_url"] = DCIC_ICON_BASE + f"tree-of-life/ic-seed-{token}-mid-shadow.png" if token else ""
    return dragon


def make_joker(rarity: str, amount: int, loc: Dict[str, str]) -> Dict[str, Any]:
    rarity = str(rarity or "").upper()
    token = RARITY_FILE.get(rarity, rarity.lower())
    name = loc_text(loc, f"tid_rarity_orbs_{rarity}_plural_lowercase", f"{RARITY_NAME.get(rarity, rarity)} Joker Orbs")
    return {
        "id": f"joker:{rarity}", "kind": "joker_orbs", "asset_kind": "joker_orbs",
        "name": name, "amount": amount, "rarity": rarity,
        "image_url": DCIC_ICON_BASE + f"tree-of-life/ic-joker-{token}.png",
    }


def make_trade_essence(rarity: str, amount: int, loc: Dict[str, str]) -> Dict[str, Any]:
    rarity = str(rarity or "").upper()
    token = RARITY_FILE.get(rarity, rarity.lower())
    name = loc_text(loc, f"tid_trade_ticket_{rarity}_plural_lowercase", f"{RARITY_NAME.get(rarity, rarity)} Trade Essences")
    return {
        "id": f"trade_essence:{rarity}", "kind": "trade_essence", "asset_kind": "trade_essence",
        "name": name, "amount": amount, "rarity": rarity,
        "image_url": DCIC_ICON_BASE + f"tree-of-life/ic-trade-orb-big-{token}.png",
    }


def make_skin(skin_id: int, skins: Dict[int, Dict[str, Any]], items: Dict[int, Dict[str, Any]], loc: Dict[str, str]) -> Dict[str, Any]:
    skin = skins.get(skin_id, {})
    dragon_id = as_int(skin.get("dragon_id"))
    dragon = items.get(dragon_id, {})
    name = loc_text(loc, skin.get("skin_name_tid"), f"Dragon Skin {skin_id}")
    desc = loc_text(loc, skin.get("skin_description_tid"), "")
    img = str(skin.get("img_name_mobile") or dragon.get("img_name_mobile") or dragon.get("img_name") or "")
    cands = dragon_candidates(img)
    return {
        "id": skin_id, "skin_id": skin_id, "dragon_id": dragon_id, "kind": "skin", "asset_kind": "skin",
        "name": name, "description": desc, "amount": 1,
        "dragon_rarity": str(dragon.get("dragon_rarity") or "").upper(),
        "img_name_mobile": img, "image_url": cands[0] if cands else "",
        "overlay_image_url": DCIC_ICON_BASE + "text-icons/ic-dragon-skin-badge.png",
        "localization_name_key": str(skin.get("skin_name_tid") or ""),
        "localization_description_key": str(skin.get("skin_description_tid") or ""),
    }


def make_sticker(key: str, amount: int, loc: Dict[str, str]) -> Dict[str, Any]:
    if key.startswith("album_pack_aces."):
        level = key.split(".", 1)[1]
        name = loc_text(loc, ACE_LOC.get(level), f"Shiny Sticker Pack - Rarity {level}")
        image = DCIC_ICON_BASE + f"stickers/ic_stickers_pack_ace_{level}_massive.png"
        subtype = f"ace_{level}"
    else:
        size = key.split(".", 1)[1] if "." in key else ""
        name = loc_text(loc, STICKER_LOC.get(size), f"{size.upper()} Sticker Pack")
        image = DCIC_ICON_BASE + f"stickers/ic_stickers_pack_{size}_massive.png"
        subtype = size
    return {
        "id": f"sticker:{subtype}", "kind": "sticker_pack", "asset_kind": "sticker_pack",
        "name": name, "amount": amount, "subtype": subtype, "image_url": image,
    }


def make_pet_food(key: str, amount: int, loc: Dict[str, str]) -> Dict[str, Any]:
    size = key.split(".", 1)[1] if "." in key else ""
    name = loc_text(loc, PET_LOC.get(size), f"{size.upper()} Pet Food Pack")
    return {
        "id": f"pet_food:{size}", "kind": "pet_food_pack", "asset_kind": "pet_food_pack",
        "name": name, "amount": amount, "subtype": size,
        "image_url": DCIC_ICON_BASE + f"pet-food/ui_chest_pet_food_{size}.png",
    }


def make_rank_coin(key: str, amount: int, loc: Dict[str, str]) -> Dict[str, Any]:
    rarity = key.split(".", 1)[1].lower() if "." in key else ""
    canonical = RANK_COIN_FILE.get(rarity, rarity)
    loc_key = RANK_COIN_LOC.get(rarity, f"tid_ruc_{rarity}")
    name = loc_text(loc, loc_key, f"{canonical.replace('_',' ').title()} Rank Up Coin")
    return {
        "id": f"rank_up_coin:{canonical}", "kind": "rank_up_coin", "asset_kind": "rank_up_coin",
        "name": name, "amount": amount, "rarity": canonical,
        "image_url": DCIC_ICON_BASE + f"rank-up-coins/ic-rank-up-coin-{canonical}.png",
    }


def make_resource(key: str, amount: int) -> Dict[str, Any]:
    name, path = RESOURCE_INFO.get(key, (key.upper(), ""))
    return {
        "id": f"resource:{key}", "kind": "resource", "asset_kind": "resource",
        "name": name, "amount": amount, "resource_code": key,
        "image_url": DCIC_ICON_BASE + path if path else "",
    }


def make_element_token(key: str, amount: int, loc: Dict[str, str]) -> Dict[str, Any]:
    element, loc_key = TOKEN_INFO.get(key, (key.replace("_token", ""), ""))
    name = loc_text(loc, loc_key, f"{element.replace('_', ' ').title()} Tokens")
    return {
        "id": f"element_token:{element}", "kind": "element_token", "asset_kind": "element_token",
        "name": name, "amount": amount, "element": element, "resource_code": key,
        "image_url": DCIC_ICON_BASE + f"tokens/ic-token-{element}.png",
        "localization_name_key": loc_key,
    }


def asset_basename(value: Any) -> str:
    raw = str(value or "").strip().replace("\\", "/")
    if not raw:
        return ""
    return raw.rsplit("/", 1)[-1]


def build_perk_catalog(cfg: Dict[str, Any]) -> Dict[int, Dict[str, Any]]:
    root = cfg.get("perks") or {}
    if not isinstance(root, dict):
        return {}
    abilities = {
        as_int(row.get("id")): row
        for row in root.get("abilities", [])
        if isinstance(row, dict) and as_int(row.get("id")) > 0
    }
    out: Dict[int, Dict[str, Any]] = {}
    for row in root.get("perks", []):
        if not isinstance(row, dict):
            continue
        perk_id = as_int(row.get("id"))
        if perk_id <= 0:
            continue
        ability_rows = [abilities.get(as_int(aid), {}) for aid in (row.get("abilities") or [])]
        icon_files = unique(
            asset_basename((ability.get("asset") or {}).get("remote"))
            for ability in ability_rows
            if isinstance(ability, dict)
        )
        frame_file = asset_basename((row.get("asset") or {}).get("remote"))
        out[perk_id] = {
            "id": perk_id,
            "type": str(row.get("type") or ""),
            "name_tid": str(row.get("name_tid") or ""),
            "description_tid": str(row.get("description_tid") or ""),
            "rarity_level": as_int(row.get("rarity_level")),
            "frame_file": frame_file,
            "icon_files": icon_files,
            "ability_ids": [as_int(x) for x in (row.get("abilities") or []) if as_int(x) > 0],
            "ability_types": unique(str(a.get("type") or "") for a in ability_rows if isinstance(a, dict)),
        }
    return out


def make_perk(perk_id: int, amount: int, perks: Dict[int, Dict[str, Any]], loc: Dict[str, str]) -> Dict[str, Any]:
    spec = perks.get(perk_id, {})
    name_key = str(spec.get("name_tid") or "")
    desc_key = str(spec.get("description_tid") or "")
    name = loc_text(loc, name_key, f"Perk {perk_id}")
    desc = loc_text(loc, desc_key, "")
    frame_file = str(spec.get("frame_file") or "")
    icon_files = [str(x) for x in (spec.get("icon_files") or []) if str(x or "").strip()]
    icon_file = icon_files[0] if icon_files else ""
    return {
        "id": perk_id, "perk_id": perk_id, "kind": "perk", "asset_kind": "perk",
        "name": name, "description": desc, "amount": max(1, as_int(amount)),
        "perk_type": str(spec.get("type") or ""),
        "perk_rarity_level": as_int(spec.get("rarity_level")),
        "perk_frame_file": frame_file,
        "perk_icon_file": icon_file,
        "perk_icon_files": icon_files,
        "perk_ability_ids": spec.get("ability_ids") or [],
        "perk_ability_types": spec.get("ability_types") or [],
        "image_url": DCIC_ICON_BASE + f"perks/{frame_file}" if frame_file else "",
        "overlay_image_url": DCIC_ICON_BASE + f"perks/{icon_file}" if icon_file else "",
        "localization_name_key": name_key,
        "localization_description_key": desc_key,
    }


def classify_race_type(
    island: Dict[str, Any],
    featured: Dict[str, Any],
    items: Dict[int, Dict[str, Any]],
    loc: Dict[str, str],
) -> Tuple[str, str]:
    title_key = str(island.get("island_title_tid") or "")
    title_text = loc_text(loc, title_key, "").strip()
    key_low = title_key.lower()
    text_low = title_text.lower()

    building = items.get(as_int(island.get("building_id")), {})
    building_name = str(building.get("name") or "").strip()
    building_asset = str(building.get("img_name_mobile") or building.get("img_name") or "").lower()
    canvas_asset = str(island.get("canvas_assets_url") or "").lower()
    if "alliance race" in building_name.lower() or "ar_island" in building_asset or "alliance" in canvas_asset:
        return "Alliance Race", "alliance_race"

    if "mythicalmarathon" in key_low or "mythical marathon" in text_low:
        return "Mythical Marathon", "mythical_marathon"
    if "heroic_marathon" in key_low or "heroicmarathon" in key_low or "heroic marathon" in text_low:
        return "Heroic Marathon", "heroic_marathon"
    if "mythicalrace" in key_low or "mythical_race" in key_low or "mythical race" in text_low:
        return "Mythical Race", "mythical_race"
    if "heroic_race" in key_low or "heroic race" in text_low:
        return "Heroic Race", "heroic_race"

    rarity = str(featured.get("dragon_rarity") or "").upper()
    if "marathon" in key_low or "marathon" in text_low:
        if rarity == "M":
            return "Mythical Marathon", "mythical_marathon"
        if rarity == "H":
            return "Heroic Marathon", "heroic_marathon"
    if title_text:
        return title_text.title(), "race"
    if rarity == "M":
        return "Mythical Race", "mythical_race"
    return "Heroic Race", "heroic_race"


def parse_reward_refs(refs: Any, *, items: Dict[int, Dict[str, Any]], chests: Dict[int, Dict[str, Any]], skins: Dict[int, Dict[str, Any]], perks: Dict[int, Dict[str, Any]], loc: Dict[str, str]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    if not isinstance(refs, list):
        refs = [refs] if isinstance(refs, dict) else []
    for ref in refs:
        if not isinstance(ref, dict):
            continue
        for key, value in ref.items():
            if key == "egg":
                ids = value if isinstance(value, list) else [value]
                for did in ids:
                    if as_int(did) > 0:
                        out.append(make_dragon(as_int(did), items, loc))
            elif key == "chest":
                if as_int(value) > 0:
                    out.append(make_chest(as_int(value), chests, loc))
            elif key == "seeds" and isinstance(value, list):
                for row in value:
                    if isinstance(row, dict) and as_int(row.get("id")) > 0:
                        out.append(make_orbs(as_int(row.get("id")), as_int(row.get("amount")), items, loc))
            elif key == "rarity_seeds" and isinstance(value, list):
                for row in value:
                    if isinstance(row, dict):
                        out.append(make_joker(str(row.get("rarity") or ""), as_int(row.get("amount")), loc))
            elif key == "trade_tickets" and isinstance(value, list):
                for row in value:
                    if isinstance(row, dict):
                        out.append(make_trade_essence(str(row.get("rarity") or ""), as_int(row.get("amount")), loc))
            elif key == "skin":
                if as_int(value) > 0:
                    out.append(make_skin(as_int(value), skins, items, loc))
            elif key == "perks" and isinstance(value, list):
                for row in value:
                    if isinstance(row, dict) and as_int(row.get("id")) > 0:
                        out.append(make_perk(as_int(row.get("id")), as_int(row.get("quantity")) or 1, perks, loc))
            elif key == "b":
                ids = value if isinstance(value, list) else [value]
                counts = Counter(as_int(x) for x in ids if as_int(x) > 0)
                for iid, amount in counts.items():
                    out.append(make_item(iid, items, loc, amount))
            elif key.startswith("album_pack"):
                out.append(make_sticker(key, as_int(value), loc))
            elif key.startswith("pet_food_pack."):
                out.append(make_pet_food(key, as_int(value), loc))
            elif key.startswith("rank_up_coin."):
                out.append(make_rank_coin(key, as_int(value), loc))
            elif key in RESOURCE_INFO:
                out.append(make_resource(key, as_int(value)))
            elif key in TOKEN_INFO or key.endswith("_token"):
                out.append(make_element_token(key, as_int(value), loc))
            else:
                # Preserve unknown future rewards instead of dropping them.
                out.append({
                    "id": f"unknown:{key}", "kind": "unknown", "asset_kind": "unknown",
                    "name": key, "amount": as_int(value) if not isinstance(value, (list, dict)) else 1,
                    "raw_key": key, "raw_value": value,
                })
    return out


def positions_label(positions: List[int]) -> str:
    if positions == [1]:
        return "1st Place"
    if positions == [2, 3]:
        return "2nd - 3rd Place"
    if positions == [4, 5, 6, 7, 8]:
        return "4th - 8th Place"
    if not positions:
        return "Final Prize"
    return f"{min(positions)}th - {max(positions)}th Place" if len(positions) > 1 else f"{positions[0]}th Place"


def reward_variant_fingerprint(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def canonical_final_variants(raw_rewards: Any) -> Tuple[List[Dict[str, Any]], List[Tuple[int, Dict[str, Any]]]]:
    """Return one canonical reward variant plus unique tier variants when they differ."""
    variants = [x for x in (raw_rewards or []) if isinstance(x, dict)]
    if not variants:
        return [], []
    seen: Dict[str, int] = {}
    unique_variants: List[Tuple[int, Dict[str, Any]]] = []
    for idx, variant in enumerate(variants):
        fp = reward_variant_fingerprint(variant)
        if fp in seen:
            continue
        seen[fp] = idx
        unique_variants.append((idx, variant))
    canonical = [unique_variants[0][1]]
    return canonical, unique_variants if len(unique_variants) > 1 else []


def source_freshness(hr: Dict[str, Any]) -> int:
    return max((as_int(x.get("end_ts")) for x in hr.get("islands", []) if isinstance(x, dict)), default=0)


def source_snapshot_timestamp(source_name: str, hr: Dict[str, Any]) -> int:
    """Best-known timestamp for a legacy snapshot.

    Prefer an explicit date embedded in filenames such as
    heroic_races_2023-10-06.json. Older undated archive files fall back to
    the latest event end timestamp contained in that snapshot.
    """
    name = str(source_name or "")
    match = re.search(r"(?<!\d)(20\d{2})[-_.](\d{2})[-_.](\d{2})(?!\d)", name)
    if match:
        try:
            dt = datetime(
                int(match.group(1)), int(match.group(2)), int(match.group(3)),
                tzinfo=timezone.utc,
            )
            return int(dt.timestamp())
        except ValueError:
            pass

    # Also accept archive names that retained the original DD.MM.YYYY date.
    match = re.search(r"(?<!\d)(\d{2})[._-](\d{2})[._-](20\d{2})(?!\d)", name)
    if match:
        try:
            dt = datetime(
                int(match.group(3)), int(match.group(2)), int(match.group(1)),
                tzinfo=timezone.utc,
            )
            return int(dt.timestamp())
        except ValueError:
            pass

    return source_freshness(hr)


def load_archive_overrides() -> Dict[str, Any]:
    default = {
        "duplicates": {}, "aliases": {}, "exclude": [], "notes": {},
        "source_preferences": {},
    }
    if not OVERRIDES_PATH.exists():
        return default

    raw = OVERRIDES_PATH.read_text(encoding="utf-8-sig").strip()
    if not raw:
        return default

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SystemExit(
            f"Invalid JSON in {OVERRIDES_PATH.name}: "
            f"line {exc.lineno}, column {exc.colno}: {exc.msg}"
        ) from exc

    if not isinstance(data, dict):
        return default

    merged = dict(default)
    merged.update(data)
    return merged


def normalize_source(
    hr: Dict[str, Any],
    *,
    source_name: str,
    historical: bool,
    source_order: int,
    source_timestamp: int,
    items: Dict[int, Dict[str, Any]],
    chests: Dict[int, Dict[str, Any]],
    skins: Dict[int, Dict[str, Any]],
    perks: Dict[int, Dict[str, Any]],
    loc: Dict[str, str],
) -> List[Dict[str, Any]]:
    final_by_id = {as_int(r.get("id")): r for r in hr.get("rewards", []) if isinstance(r, dict)}
    lap_by_island = {as_int(r.get("id")): r.get("lap_rewards", {}) for r in hr.get("lap_rewards", []) if isinstance(r, dict)}
    out: List[Dict[str, Any]] = []

    for island in hr.get("islands", []):
        if not isinstance(island, dict):
            continue
        iid = as_int(island.get("id"))
        if iid <= 0:
            continue

        title_key = str(island.get("island_title_tid") or "")
        featured_id = as_int(island.get("dragon_race_id"))
        featured = make_dragon(featured_id, items, loc) if featured_id else {}
        race_type, race_variant = classify_race_type(island, featured, items, loc)
        race_name = f"{clean_dragon_name(featured.get('name', ''))} {race_type}".strip() if featured else race_type

        final_prizes: List[Dict[str, Any]] = []
        for rid in island.get("rewards", []) or []:
            row = final_by_id.get(as_int(rid), {})
            if not row:
                continue
            positions = [as_int(x) for x in row.get("positions", []) if as_int(x) > 0]
            canonical_refs, different_variants = canonical_final_variants(row.get("rewards", []))
            group: Dict[str, Any] = {
                "id": as_int(row.get("id")),
                "positions": positions,
                "label": positions_label(positions),
                "rewards": parse_reward_refs(canonical_refs, items=items, chests=chests, skins=skins, perks=perks, loc=loc),
                "canonicalized_identical_level_tiers": int(bool(row.get("rewards")) and not different_variants and len(row.get("rewards", [])) > 1),
            }
            if different_variants:
                level_tiers = island.get("level_tiers", []) or []
                group["level_tier_variants"] = [
                    {
                        "variant_index": idx + 1,
                        "level_tier": as_int(level_tiers[idx]) if idx < len(level_tiers) else 0,
                        "rewards": parse_reward_refs([variant], items=items, chests=chests, skins=skins, perks=perks, loc=loc),
                    }
                    for idx, variant in different_variants
                ]
            final_prizes.append(group)

        final_prize_status = "available" if final_prizes else "none"
        unverified_final_prizes: List[Dict[str, Any]] = []
        if historical and featured_id and final_prizes:
            first_group = next((g for g in final_prizes if 1 in (g.get("positions") or [])), None)
            first_dragon_ids = {
                as_int(r.get("dragon_id"))
                for r in (first_group or {}).get("rewards", [])
                if r.get("kind") == "dragon" and as_int(r.get("dragon_id")) > 0
            }
            # A Race/Marathon 1st-place group that contains dragons should include
            # its featured dragon. If it does not, the shared reward-table row was
            # almost certainly reused/overwritten by a later event. This validation
            # intentionally also covers rerun dragons where dragon_is_new == 0.
            if first_group and first_dragon_ids and featured_id not in first_dragon_ids:
                # Some very old snapshots retain old islands but their shared reward-table
                # rows were overwritten by a later Race. Never present those stale prizes
                # as historical fact; preserve them only as unverified source data.
                final_prize_status = "unverified"
                unverified_final_prizes = final_prizes
                final_prizes = []

        lap_map = lap_by_island.get(iid, {})
        if not isinstance(lap_map, dict):
            lap_map = {}
        lap_keys = sorted(as_int(k) for k in lap_map.keys() if as_int(k) > 0)
        # Current and later legacy snapshots explicitly enumerate reward-lap indices.
        # For the earliest snapshots, where lap_rewards did not exist yet, the
        # island's lap-template count is the only finite span available.
        max_lap_index = max(lap_keys, default=0)
        if max_lap_index <= 0:
            max_lap_index = len(island.get("laps", []) or [])

        laps: List[Dict[str, Any]] = []
        for lap_no in range(1, max_lap_index + 1):
            row = lap_map.get(str(lap_no)) or lap_map.get(lap_no) or {}
            has_row = isinstance(row, dict) and bool(row)
            has_reward_field = has_row and "reward" in row
            parsed_rewards = parse_reward_refs(row.get("reward", []), items=items, chests=chests, skins=skins, perks=perks, loc=loc) if has_row else []
            parsed_limited = parse_reward_refs(row.get("limited_reward", []), items=items, chests=chests, skins=skins, perks=perks, loc=loc) if has_row else []
            reward_status = "available" if parsed_rewards else ("unavailable" if has_row and not has_reward_field else "none")
            laps.append({
                "id": as_int(row.get("id")) if has_row else 0,
                "lap": lap_no,
                "reward_status": reward_status,
                "reward_declared": int(has_reward_field),
                "reward_cell_type": str(row.get("reward_cell_type") or "") if has_row else "",
                "wait_until_race_ends": as_int(row.get("wait_until_race_ends")) if has_row else 0,
                "omit_if_winner": as_int(row.get("omit_if_winner")) if has_row else 0,
                "limited_time": as_int(row.get("limited_time")) if has_row else 0,
                "multiplier": as_int(row.get("multiplier")) if has_row else 0,
                "rewards": parsed_rewards,
                "limited_rewards": parsed_limited,
            })

        start_ts, end_ts = as_int(island.get("start_ts")), as_int(island.get("end_ts"))
        available_lap_rewards = sum(1 for x in laps if x.get("reward_status") == "available")
        unavailable_lap_rewards = sum(1 for x in laps if x.get("reward_status") == "unavailable")
        out.append({
            "id": iid,
            "race_type": race_type,
            "race_variant": race_variant,
            "race_scope": "alliance" if race_variant == "alliance_race" else "individual",
            "race_type_key": title_key,
            "name": race_name,
            "featured_dragon_id": featured_id,
            "featured_dragon": featured,
            "start_ts": start_ts,
            "end_ts": end_ts,
            "start_iso": iso(start_ts),
            "end_iso": iso(end_ts),
            "min_level": as_int(island.get("min_level")),
            "min_qualifying_laps": as_int(island.get("min_qualifying_laps")),
            "spinner_enabled": as_int(island.get("spinner_enabled")),
            "spin_cooldown": as_int(island.get("spin_cooldown")),
            "buy_spin_price": as_int(island.get("buy_spin_price")),
            "lap_count": len(laps),
            "lap_template_count": len(island.get("laps", []) or []),
            "available_lap_reward_count": available_lap_rewards,
            "unavailable_lap_reward_count": unavailable_lap_rewards,
            "final_prize_status": final_prize_status,
            "final_prizes": final_prizes,
            "unverified_final_prizes": unverified_final_prizes,
            "lap_rewards": laps,
            "zip_file": str(island.get("zip_file") or ""),
            "canvas_assets_url": str(island.get("canvas_assets_url") or ""),
            "sound_tag": str(island.get("sound_tag") or ""),
            "active_platforms": island.get("active_platforms") if isinstance(island.get("active_platforms"), dict) else {},
            "historical": bool(historical),
            "source_generation": "legacy" if historical else "current",
            "source_snapshot": source_name,
            "source_snapshots": [source_name],
            "_source_order": source_order,
            "_source_timestamp": source_timestamp,
        })
    return out


def candidate_quality(row: Dict[str, Any]) -> Tuple[int, int, int, int, int, int]:
    """Quality score independent of snapshot age/order.

    This is intentionally evaluated before temporal preference. A newer snapshot
    may repair a stale reward pointer from an older one (for example a featured
    dragon mismatch), while an older equally-complete snapshot is safer when both
    candidates are valid because shared config tables can be reused later.
    """
    final_status = str(row.get("final_prize_status") or "")
    final_rank = {"available": 2, "none": 1, "unverified": 0}.get(final_status, 0)
    return (
        final_rank,
        len(row.get("final_prizes", []) or []),
        as_int(row.get("available_lap_reward_count")),
        as_int(row.get("lap_count")),
        1 if as_int(row.get("featured_dragon_id")) > 0 else 0,
        1 if as_int(row.get("end_ts")) > as_int(row.get("start_ts")) > 0 else 0,
    )


def candidate_snapshot_distance(row: Dict[str, Any]) -> int:
    source_ts = as_int(row.get("_source_timestamp"))
    event_ts = as_int(row.get("end_ts")) or as_int(row.get("start_ts"))
    if source_ts <= 0 or event_ts <= 0:
        return 10**18
    return abs(source_ts - event_ts)


def source_matches_preference(source_name: str, preference: Any) -> bool:
    if not str(preference or "").strip():
        return False
    pref = str(preference).strip()
    source = str(source_name or "").strip()
    return source == pref or Path(source).stem == Path(pref).stem


def choose_candidate(
    rows: List[Dict[str, Any]],
    *,
    preferred_source: Any = "",
) -> Tuple[Dict[str, Any], str]:
    if not rows:
        raise ValueError("choose_candidate() requires at least one row")

    # Manual archive preference is the explicit authority for known collisions.
    preferred = [
        row for row in rows
        if source_matches_preference(str(row.get("source_snapshot") or ""), preferred_source)
    ]
    if preferred:
        chosen = preferred[0]
        return chosen, "manual_source_preference"

    # Current game_config remains authoritative for IDs it actively contains.
    current = [row for row in rows if not row.get("historical")]
    pool = current or rows
    if current:
        reason = "current_game_config"
    else:
        reason = "best_historical_snapshot"

    # IMPORTANT: quality/completeness first. Only after candidates are equally
    # useful do we prefer the snapshot closest to the event, then the older
    # snapshot. This prevents both kinds of archive damage:
    #   * an old stale/invalid pointer beating a later repaired copy; and
    #   * a much later snapshot beating an older equally-valid copy after a
    #     shared table (rewards/encounters/etc.) has been reused.
    chosen = max(
        pool,
        key=lambda row: (
            candidate_quality(row),
            -candidate_snapshot_distance(row),
            -as_int(row.get("_source_timestamp")),
            -as_int(row.get("_source_order")),
        ),
    )
    return chosen, reason


def candidate_identity(row: Dict[str, Any]) -> Tuple[Any, ...]:
    return (
        as_int(row.get("featured_dragon_id")),
        as_int(row.get("start_ts")),
        as_int(row.get("end_ts")),
        str(row.get("race_variant") or ""),
        str(row.get("canvas_assets_url") or ""),
    )


def main() -> None:
    cfg = load_json(CONFIG_PATH)
    loc = normalize_localization(load_json(LOCALIZATION_PATH))
    current_hr = cfg.get("heroic_races") or {}

    items = {as_int(r.get("id")): r for r in cfg.get("items", []) if isinstance(r, dict) and as_int(r.get("id")) > 0}
    chests = {as_int(r.get("id")): r for r in (cfg.get("chests") or {}).get("chests", []) if isinstance(r, dict) and as_int(r.get("id")) > 0}
    skins = {as_int(r.get("id")): r for r in (cfg.get("dragon_skins") or {}).get("dragon_skins", []) if isinstance(r, dict) and as_int(r.get("id")) > 0}
    perks = build_perk_catalog(cfg)

    overrides = load_archive_overrides()
    source_preferences = overrides.get("source_preferences", {})
    if not isinstance(source_preferences, dict):
        source_preferences = {}

    sources: List[Tuple[int, str, bool, int, Dict[str, Any]]] = []
    if LEGACY_DIR.exists():
        legacy_rows: List[Tuple[int, int, str, Dict[str, Any]]] = []
        for path in sorted(LEGACY_DIR.glob("*.json")):
            try:
                data = load_json(path)
            except Exception as exc:
                print(f"WARNING: skipping {path.name}: {exc}")
                continue
            if not isinstance(data, dict) or not isinstance(data.get("islands"), list):
                print(f"WARNING: skipping {path.name}: not a heroic_races snapshot")
                continue
            snapshot_ts = source_snapshot_timestamp(path.name, data)
            legacy_rows.append((snapshot_ts, source_freshness(data), path.name, data))

        # Stable chronological ordering is useful for provenance/logging only.
        # Candidate selection itself does NOT use last-file-wins semantics.
        legacy_rows.sort(key=lambda x: (x[0], x[1], x[2]))
        for order, (snapshot_ts, _, name, data) in enumerate(legacy_rows, start=1):
            sources.append((order, name, True, snapshot_ts, data))

    current_order = len(sources) + 1000
    current_snapshot_ts = int(datetime.now(timezone.utc).timestamp())
    sources.append((current_order, CONFIG_PATH.name, False, current_snapshot_ts, current_hr))

    candidates: Dict[int, List[Dict[str, Any]]] = {}
    seen_sources: Dict[int, List[str]] = {}
    for order, source_name, historical, snapshot_ts, hr in sources:
        rows = normalize_source(
            hr,
            source_name=source_name,
            historical=historical,
            source_order=order,
            source_timestamp=snapshot_ts,
            items=items,
            chests=chests,
            skins=skins,
            perks=perks,
            loc=loc,
        )
        for row in rows:
            iid = as_int(row.get("id"))
            candidates.setdefault(iid, []).append(row)
            seen_sources.setdefault(iid, [])
            if source_name not in seen_sources[iid]:
                seen_sources[iid].append(source_name)

    merged: Dict[int, Dict[str, Any]] = {}
    for iid, rows in candidates.items():
        preference = source_preferences.get(str(iid), source_preferences.get(iid, ""))
        chosen, selection_reason = choose_candidate(rows, preferred_source=preference)
        chosen["source_snapshots"] = seen_sources.get(iid, [chosen.get("source_snapshot")])
        chosen["source_selection_reason"] = selection_reason
        merged[iid] = chosen

        historical_rows = [row for row in rows if row.get("historical")]
        identities = {candidate_identity(row) for row in historical_rows}
        if len(identities) > 1:
            print(
                f"WARNING: ID {iid} has conflicting historical identities across "
                f"{len(historical_rows)} snapshots; chose {chosen.get('source_snapshot')}"
            )

    excluded = {as_int(x) for x in overrides.get("exclude", []) if as_int(x) > 0}
    redirect_map: Dict[int, int] = {}
    for section in ("duplicates", "aliases"):
        mapping = overrides.get(section, {})
        if isinstance(mapping, dict):
            for old, new in mapping.items():
                old_id, new_id = as_int(old), as_int(new)
                if old_id > 0 and new_id > 0 and old_id != new_id:
                    redirect_map[old_id] = new_id

    notes = overrides.get("notes", {}) if isinstance(overrides.get("notes", {}), dict) else {}
    for key, note in notes.items():
        iid = as_int(key)
        if iid in merged and str(note or "").strip():
            merged[iid]["archive_note"] = str(note).strip()

    aliases_out: Dict[str, int] = {}
    for old_id, target_id in redirect_map.items():
        if old_id in merged and target_id in merged:
            aliases_out[str(old_id)] = target_id
            target = merged[target_id]
            target.setdefault("alternate_ids", [])
            if old_id not in target["alternate_ids"]:
                target["alternate_ids"].append(old_id)
            target["source_snapshots"] = unique((target.get("source_snapshots") or []) + (merged[old_id].get("source_snapshots") or []))
            del merged[old_id]

    for iid in excluded:
        merged.pop(iid, None)

    islands_out = sorted(merged.values(), key=lambda r: (as_int(r.get("start_ts")), as_int(r.get("id"))))
    for row in islands_out:
        row.pop("_source_order", None)
        row.pop("_source_timestamp", None)

    historical_count = sum(1 for row in islands_out if row.get("historical"))
    payload = {
        "schema_version": 3,
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "source_file": CONFIG_PATH.name,
        "localization_file": str(LOCALIZATION_PATH.relative_to(ROOT)).replace("\\", "/"),
        "legacy_directory": str(LEGACY_DIR.relative_to(ROOT)).replace("\\", "/"),
        "archive_overrides_file": OVERRIDES_PATH.name,
        "island_count": len(islands_out),
        "historical_island_count": historical_count,
        "current_island_count": len(islands_out) - historical_count,
        "aliases": aliases_out,
        "assets": {"dcic_icons_base": DCIC_ICON_BASE, "static_base": STATIC_BASE, "perk_icons_base": DCIC_ICON_BASE + "perks/"},
        "islands": islands_out,
    }
    with OUTPUT_PATH.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))

    print(f"Wrote {OUTPUT_PATH.name}: {len(islands_out)} races ({historical_count} historical, {len(islands_out)-historical_count} current)")
    for row in islands_out:
        print(
            f"  ID {row['id']}: {row['name']} | {row['lap_count']} lap slots | "
            f"{row['available_lap_reward_count']} with rewards | {len(row['final_prizes'])} final prize groups | {row['source_snapshot']}"
        )


if __name__ == "__main__":
    main()
