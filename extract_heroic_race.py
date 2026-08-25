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
    cands = item_candidates(img)
    return {
        "id": item_id, "item_id": item_id, "kind": "item", "asset_kind": "item",
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


def parse_reward_refs(refs: Any, *, items: Dict[int, Dict[str, Any]], chests: Dict[int, Dict[str, Any]], skins: Dict[int, Dict[str, Any]], loc: Dict[str, str]) -> List[Dict[str, Any]]:
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


def main() -> None:
    cfg = load_json(CONFIG_PATH)
    loc = normalize_localization(load_json(LOCALIZATION_PATH))
    hr = cfg.get("heroic_races") or {}

    items = {as_int(r.get("id")): r for r in cfg.get("items", []) if isinstance(r, dict) and as_int(r.get("id")) > 0}
    chests = {as_int(r.get("id")): r for r in (cfg.get("chests") or {}).get("chests", []) if isinstance(r, dict) and as_int(r.get("id")) > 0}
    skins = {as_int(r.get("id")): r for r in (cfg.get("dragon_skins") or {}).get("dragon_skins", []) if isinstance(r, dict) and as_int(r.get("id")) > 0}
    final_by_id = {as_int(r.get("id")): r for r in hr.get("rewards", []) if isinstance(r, dict)}
    lap_by_island = {as_int(r.get("id")): r.get("lap_rewards", {}) for r in hr.get("lap_rewards", []) if isinstance(r, dict)}

    islands_out: List[Dict[str, Any]] = []
    for island in hr.get("islands", []):
        if not isinstance(island, dict):
            continue
        iid = as_int(island.get("id"))
        if iid <= 0:
            continue
        title_key = str(island.get("island_title_tid") or "")
        race_type = loc_text(loc, title_key, "HEROIC RACE").title()
        featured_id = as_int(island.get("dragon_race_id"))
        featured = make_dragon(featured_id, items, loc) if featured_id else {}
        race_name = f"{clean_dragon_name(featured.get('name', ''))} {race_type}".strip() if featured else race_type

        final_prizes: List[Dict[str, Any]] = []
        for rid in island.get("rewards", []) or []:
            row = final_by_id.get(as_int(rid), {})
            positions = [as_int(x) for x in row.get("positions", []) if as_int(x) > 0]
            final_prizes.append({
                "id": as_int(row.get("id")),
                "positions": positions,
                "label": positions_label(positions),
                "rewards": parse_reward_refs(row.get("rewards", []), items=items, chests=chests, skins=skins, loc=loc),
            })

        laps: List[Dict[str, Any]] = []
        lap_map = lap_by_island.get(iid, {})
        for lap_no in sorted((as_int(k) for k in lap_map.keys() if as_int(k) > 0)):
            row = lap_map.get(str(lap_no), {})
            laps.append({
                "id": as_int(row.get("id")), "lap": lap_no,
                "reward_cell_type": str(row.get("reward_cell_type") or ""),
                "wait_until_race_ends": as_int(row.get("wait_until_race_ends")),
                "omit_if_winner": as_int(row.get("omit_if_winner")),
                "limited_time": as_int(row.get("limited_time")),
                "multiplier": as_int(row.get("multiplier")),
                "rewards": parse_reward_refs(row.get("reward", []), items=items, chests=chests, skins=skins, loc=loc),
                "limited_rewards": parse_reward_refs(row.get("limited_reward", []), items=items, chests=chests, skins=skins, loc=loc),
            })

        start_ts, end_ts = as_int(island.get("start_ts")), as_int(island.get("end_ts"))
        islands_out.append({
            "id": iid,
            "race_type": race_type,
            "race_type_key": title_key,
            "name": race_name,
            "featured_dragon_id": featured_id,
            "featured_dragon": featured,
            "start_ts": start_ts, "end_ts": end_ts,
            "start_iso": iso(start_ts), "end_iso": iso(end_ts),
            "min_level": as_int(island.get("min_level")),
            "min_qualifying_laps": as_int(island.get("min_qualifying_laps")),
            "spinner_enabled": as_int(island.get("spinner_enabled")),
            "spin_cooldown": as_int(island.get("spin_cooldown")),
            "buy_spin_price": as_int(island.get("buy_spin_price")),
            "lap_count": len(laps),
            "final_prizes": final_prizes,
            "lap_rewards": laps,
            "zip_file": str(island.get("zip_file") or ""),
        })

    payload = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "source_file": CONFIG_PATH.name,
        "localization_file": str(LOCALIZATION_PATH.relative_to(ROOT)).replace("\\", "/"),
        "island_count": len(islands_out),
        "assets": {"dcic_icons_base": DCIC_ICON_BASE, "static_base": STATIC_BASE},
        "islands": islands_out,
    }
    with OUTPUT_PATH.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))
    print(f"Wrote {OUTPUT_PATH.name}: {len(islands_out)} races")
    for row in islands_out:
        print(f"  ID {row['id']}: {row['name']} | {row['lap_count']} laps | {len(row['final_prizes'])} final prize groups")


if __name__ == "__main__":
    main()
