#!/usr/bin/env python3
"""Build tower_island.json for Dragon City Information Center.

Batch 1.2 exposes Tower Island schedule, How to Play support data, and Rewards
Summary. Exact chest IDs are preserved: different IDs with the same localized
name are never merged. Chests also remain chests and are never replaced by one
of their gatcha contents.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "game_config.json"
LOCALIZATION_PATH = ROOT / "localization" / "dragon_city_localization_baseline_en.json"
OUTPUT_PATH = ROOT / "tower_island.json"

STATIC_BASE = "https://dci-static-s1.socialpointgames.com/static/dragoncity/"
DRAGON_BASE = STATIC_BASE + "mobile/ui/dragons/HD/"
CHEST_BASE = STATIC_BASE + "mobile/ui/chests/"

# Generic/basic rewards are omitted from the highlighted Rewards Summary.
SUMMARY_EXCLUDED_CHEST_NAMES = {
    "Wood Chest",
    "Bamboo Chest",
    "Common Orbs Chest",
    "Rare Orbs Chest",
    "Very Rare Orbs Chest",
    "Bronze Chest",
    "Epic Orbs Chest",
    "Silver Chest",
    "Legendary Orbs Chest",
    "Gold Chest",
}

# Classification is name-based so future chest IDs are recognized, but each
# exact ID remains a separate card and keeps its own image.
OTHER_SPECIAL_CHEST_NAMES = {
    "Lucky Break Chest",
    "Key Chest",
    "Lucky Legendary Chest",
    "Flame Chest",
    "Diamond Chest",
    "Titan Chest",
    "Black Chest",
    "VIP Chest",
    "Mythical Egg Chest",
    "Corrupted Chest",
    "Heroic Egg Chest",
    "Legendary Tower Chest",
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


def loc_text(localization: Dict[str, str], key: Any, fallback: str = "") -> str:
    value = localization.get(str(key or ""), "")
    value = str(value or "").strip()
    return value or fallback


def normalized_name(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip()).casefold()


def tower_theme(island: Dict[str, Any]) -> str:
    stem = Path(str(island.get("zip_file") or "")).stem
    stem = re.sub(r"^ti_", "", stem, flags=re.I)
    stem = re.sub(r"_[a-z]$", "", stem, flags=re.I)
    replacements = {
        "norsegods": "Norse Gods",
        "energysource": "Energy Source",
        "wooden_tower": "Wooden Tower",
    }
    key = stem.casefold()
    if key in replacements:
        label = replacements[key]
    else:
        label = " ".join(w.capitalize() for w in stem.split("_") if w)
    if not label:
        return f"Tower Island {as_int(island.get('id'))}"
    if label.casefold().endswith("tower"):
        return f"{label} Island"
    return f"{label} Tower Island"


def dragon_display(dragon_id: int, localization: Dict[str, str]) -> Tuple[str, str]:
    return (
        loc_text(localization, f"tid_unit_{dragon_id}_name", f"Dragon {dragon_id}"),
        loc_text(localization, f"tid_unit_{dragon_id}_description", ""),
    )


def chest_display(chest_id: int, chest: Dict[str, Any], localization: Dict[str, str]) -> Tuple[str, str, str]:
    name_key = str(chest.get("chest_name_key") or "")
    type_key = str(chest.get("type_name_key") or "")
    desc_key = str(chest.get("description_key") or "")
    name = loc_text(localization, name_key) or loc_text(localization, type_key)
    desc = loc_text(localization, desc_key)
    return name or f"Chest {chest_id}", desc, name_key or type_key


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


def make_dragon_record(
    dragon_id: int,
    item: Dict[str, Any],
    localization: Dict[str, str],
    **extra: Any,
) -> Dict[str, Any]:
    name, description = dragon_display(dragon_id, localization)
    img_mobile = str(item.get("img_name_mobile") or item.get("img_name") or "")
    candidates = dragon_candidates(img_mobile)
    out: Dict[str, Any] = {
        "id": dragon_id,
        "dragon_id": dragon_id,
        "kind": "dragon",
        "asset_kind": "dragon",
        "name": name,
        "description": description,
        "dragon_rarity": str(item.get("dragon_rarity") or "").upper(),
        "rarity": item.get("rarity"),
        "img_name_mobile": img_mobile,
        "image_url": candidates[0] if candidates else "",
        "localization_name_key": f"tid_unit_{dragon_id}_name",
        "localization_description_key": f"tid_unit_{dragon_id}_description",
    }
    out.update(extra)
    return out


def make_chest_record(chest_id: int, chest: Dict[str, Any], localization: Dict[str, str]) -> Dict[str, Any]:
    name, description, name_key = chest_display(chest_id, chest, localization)
    img_name = str(chest.get("img_name") or "")
    candidates = chest_candidates(chest_id, img_name)
    return {
        "id": chest_id,
        "chest_id": chest_id,
        "source_chest_id": chest_id,
        "kind": "chest",
        "asset_kind": "chest",
        "name": name,
        "description": description,
        "img_name": img_name,
        "source_chest_img_name": img_name,
        "image_url": candidates[0] if candidates else "",
        "localization_name_key": name_key,
        "localization_description_key": str(chest.get("description_key") or ""),
    }


def add_count(summary: Dict[str, Dict[str, Any]], key: str, row: Dict[str, Any], count: int = 1) -> None:
    if key not in summary:
        rec = dict(row)
        rec["tile_count"] = 0
        summary[key] = rec
    summary[key]["tile_count"] = as_int(summary[key].get("tile_count")) + max(0, count)


def main() -> None:
    config = load_json(CONFIG_PATH)
    localization = normalize_localization(load_json(LOCALIZATION_PATH))
    tower = config.get("tower_island") or {}

    item_by_id = {
        as_int(row.get("id")): row
        for row in config.get("items", [])
        if isinstance(row, dict) and as_int(row.get("id")) > 0
    }
    chest_by_id = {
        as_int(row.get("id")): row
        for row in (config.get("chests") or {}).get("chests", [])
        if isinstance(row, dict) and as_int(row.get("id")) > 0
    }

    rewards_by_id = {
        as_int(row.get("id")): row
        for row in tower.get("rewards", [])
        if isinstance(row, dict) and as_int(row.get("id")) > 0
    }
    rewards_by_island: Dict[int, List[Dict[str, Any]]] = {}
    for row in tower.get("rewards", []):
        if isinstance(row, dict):
            rewards_by_island.setdefault(as_int(row.get("island_id")), []).append(row)

    squares_by_island: Dict[int, List[Dict[str, Any]]] = {}
    for row in tower.get("squares", []):
        if isinstance(row, dict):
            squares_by_island.setdefault(as_int(row.get("island_id")), []).append(row)

    floors_by_island: Dict[int, List[Dict[str, Any]]] = {}
    for row in tower.get("floors", []):
        if isinstance(row, dict):
            floors_by_island.setdefault(as_int(row.get("island_id")), []).append(row)

    excluded_norm = {normalized_name(x) for x in SUMMARY_EXCLUDED_CHEST_NAMES}
    special_norm = {normalized_name(x) for x in OTHER_SPECIAL_CHEST_NAMES}

    islands_out: List[Dict[str, Any]] = []

    for island in tower.get("islands", []):
        if not isinstance(island, dict):
            continue
        island_id = as_int(island.get("id"))
        if island_id <= 0:
            continue

        raw_squares = sorted(
            squares_by_island.get(island_id, []),
            key=lambda s: (as_int(s.get("y")), as_int(s.get("x")), as_int(s.get("id"))),
        )

        dragons: List[Dict[str, Any]] = []
        seen_piece_rewards = set()
        final_dragon_ids = set()
        items_summary: Dict[str, Dict[str, Any]] = {}
        special_summary: Dict[str, Dict[str, Any]] = {}
        squares_out: List[Dict[str, Any]] = []

        for s in raw_squares:
            stype = str(s.get("type") or "EMPTY").upper()
            out: Dict[str, Any] = {
                "id": as_int(s.get("id")),
                "x": as_int(s.get("x")),
                "y": as_int(s.get("y")),
                "type": stype,
                "highlight": as_int(s.get("highlight")),
            }
            if s.get("wall"):
                out["wall"] = str(s.get("wall"))
            if s.get("catapult_destination_square_id") is not None:
                out["catapult_destination_square_id"] = as_int(s.get("catapult_destination_square_id"))

            if stype == "SINGLE_DRAGON_PIECE":
                reward_config_id = as_int(s.get("piece_reward_id"))
                reward_cfg = rewards_by_id.get(reward_config_id, {})
                dragon_id = as_int(reward_cfg.get("dragon_reward_id"))
                item = item_by_id.get(dragon_id, {})
                if dragon_id > 0 and str(item.get("group_type") or "").upper() == "DRAGON":
                    if reward_config_id not in seen_piece_rewards:
                        seen_piece_rewards.add(reward_config_id)
                        dragons.append(make_dragon_record(
                            dragon_id, item, localization,
                            reward_type="dragon_piece",
                            reward_config_id=reward_config_id,
                            num_pieces=as_int(reward_cfg.get("num_pieces")),
                            last_piece_cost=as_int(reward_cfg.get("last_piece_cost")),
                            is_final_dragon=False,
                        ))
                    compact = make_dragon_record(
                        dragon_id, item, localization,
                        reward_type="dragon_piece",
                        reward_config_id=reward_config_id,
                        num_pieces=as_int(reward_cfg.get("num_pieces")),
                        is_final_dragon=False,
                    )
                    compact.pop("description", None)
                    compact.pop("localization_name_key", None)
                    compact.pop("localization_description_key", None)
                    out["reward"] = compact

            elif stype == "FINAL_DRAGON_SQUARE":
                rewards_array = s.get("rewards_array") if isinstance(s.get("rewards_array"), list) else []
                for reward_ref in rewards_array:
                    if not isinstance(reward_ref, dict) or "egg" not in reward_ref:
                        continue
                    dragon_id = as_int(reward_ref.get("egg"))
                    item = item_by_id.get(dragon_id, {})
                    if dragon_id <= 0 or str(item.get("group_type") or "").upper() != "DRAGON":
                        continue
                    if dragon_id not in final_dragon_ids:
                        final_dragon_ids.add(dragon_id)
                        dragons.append(make_dragon_record(
                            dragon_id, item, localization,
                            reward_type="egg",
                            num_pieces=0,
                            is_final_dragon=True,
                        ))
                    compact = make_dragon_record(
                        dragon_id, item, localization,
                        reward_type="egg",
                        num_pieces=0,
                        is_final_dragon=True,
                    )
                    compact.pop("description", None)
                    compact.pop("localization_name_key", None)
                    compact.pop("localization_description_key", None)
                    out["reward"] = compact
                    break

            elif stype == "SINGLE_REWARD":
                rewards_array = s.get("rewards_array") if isinstance(s.get("rewards_array"), list) else []
                compact_rewards: List[Dict[str, Any]] = []
                for reward_ref in rewards_array:
                    if not isinstance(reward_ref, dict) or "chest" not in reward_ref:
                        continue
                    chest_id = as_int(reward_ref.get("chest"))
                    chest = chest_by_id.get(chest_id, {})
                    reward = make_chest_record(chest_id, chest, localization)
                    name_norm = normalized_name(str(reward.get("name") or ""))
                    if name_norm in special_norm:
                        add_count(special_summary, f"chest:{chest_id}", reward, 1)
                        classification = "other_special_chest"
                    elif name_norm in excluded_norm:
                        classification = "excluded_generic_chest"
                    else:
                        add_count(items_summary, f"chest:{chest_id}", reward, 1)
                        classification = "event_item"
                    compact = dict(reward)
                    compact["summary_classification"] = classification
                    compact.pop("description", None)
                    compact.pop("localization_name_key", None)
                    compact.pop("localization_description_key", None)
                    compact_rewards.append(compact)
                if compact_rewards:
                    out["rewards"] = compact_rewards
                    if len(compact_rewards) == 1:
                        out["reward"] = compact_rewards[0]

            squares_out.append(out)

        # Fallback: include any piece reward config not represented by a square.
        for reward_cfg in rewards_by_island.get(island_id, []):
            rid = as_int(reward_cfg.get("id"))
            if rid in seen_piece_rewards:
                continue
            dragon_id = as_int(reward_cfg.get("dragon_reward_id"))
            item = item_by_id.get(dragon_id, {})
            if dragon_id > 0 and str(item.get("group_type") or "").upper() == "DRAGON":
                seen_piece_rewards.add(rid)
                dragons.append(make_dragon_record(
                    dragon_id, item, localization,
                    reward_type="dragon_piece",
                    reward_config_id=rid,
                    num_pieces=as_int(reward_cfg.get("num_pieces")),
                    last_piece_cost=as_int(reward_cfg.get("last_piece_cost")),
                    is_final_dragon=False,
                ))

        floors_out = []
        for floor in sorted(floors_by_island.get(island_id, []), key=lambda f: as_int(f.get("y"))):
            floors_out.append({
                "id": as_int(floor.get("id")),
                "y": as_int(floor.get("y")),
                "area": as_int(floor.get("area")),
                "x_flip": as_int(floor.get("x_flip")),
                "floor_image": str(floor.get("floor_image") or ""),
                "roll_die_price": floor.get("roll_die_price") if isinstance(floor.get("roll_die_price"), dict) else {},
            })

        start_ts = as_int(island.get("start_ts"))
        end_ts = as_int(island.get("end_ts"))
        tower_size = island.get("tower_size") if isinstance(island.get("tower_size"), list) else [7, 40]
        if len(tower_size) < 2:
            tower_size = [7, 40]

        islands_out.append({
            "id": island_id,
            "name": tower_theme(island),
            "title": "Tower Island",
            "start_ts": start_ts,
            "end_ts": end_ts,
            "start_iso": iso(start_ts),
            "end_iso": iso(end_ts),
            "initial_square_id": as_int(island.get("initial_square_id")),
            "initial_points": as_int(island.get("initial_points")),
            "pool_size": as_int(island.get("pool_size")),
            "pool_time": as_int(island.get("pool_time")),
            "currency_id": as_int(island.get("currency_id")),
            "max_die_roll": as_int(island.get("max_die_roll")) or 3,
            "tower_size": [as_int(tower_size[0]), as_int(tower_size[1])],
            "asset_zip": str(island.get("zip_file") or ""),
            "rewards_summary": {
                "dragons": dragons,
                "event_items": list(items_summary.values()),
                "other_special_chests": list(special_summary.values()),
                "excluded_chest_names": sorted(SUMMARY_EXCLUDED_CHEST_NAMES),
                "other_special_chest_names": sorted(OTHER_SPECIAL_CHEST_NAMES),
            },
            "floors": floors_out,
            "squares": squares_out,
        })

    islands_out.sort(key=lambda r: (r["start_ts"], r["end_ts"], r["id"]))
    payload = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "source_file": CONFIG_PATH.name,
        "localization_file": str(LOCALIZATION_PATH.relative_to(ROOT)).replace("\\", "/"),
        "display_text_source": "localization",
        "island_count": len(islands_out),
        "islands": islands_out,
    }
    with OUTPUT_PATH.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(f"Wrote {OUTPUT_PATH.name}: {len(islands_out)} Tower Island map(s)")
    print(f"Display names/descriptions: {LOCALIZATION_PATH.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
