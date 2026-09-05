#!/usr/bin/env python3
"""Build grid_island.json for Dragon City Information Center.

Reads game_config.json + the repository's canonical English localization and
writes a compact, browser-friendly Grid Island dataset.

Batch 1.1 exposes schedule + Rewards Summary in Blogger. The compact square
metadata is also retained so the future Grid map/path simulator can be added
without replacing the data format.

Display names/descriptions always come from localization where a localization
key exists. game_config names are used only as internal identifiers/assets.
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent
REPO_ROOT = ROOT.parent
DIST_DIR = REPO_ROOT / "dist"
LOCALIZATION_DIR = REPO_ROOT / "localization"
RAW_DIR = Path(os.environ.get("DCIC_RAW_DIR", REPO_ROOT.parent / "the-void"))

CONFIG_PATH = RAW_DIR / "game_config.json"
LOCALIZATION_PATH = LOCALIZATION_DIR / "dragon_city_localization_baseline_en.json"
OUTPUT_PATH = DIST_DIR / "grid_island.json"

STATIC_BASE = "https://dci-static-s1.socialpointgames.com/static/dragoncity/"
DRAGON_BASE = STATIC_BASE + "mobile/ui/dragons/HD/"
CHEST_BASE = STATIC_BASE + "mobile/ui/chests/"

# Grid chest filtering is intentionally name-based. Dragon City frequently has
# multiple chest IDs with the same localized name/description.
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

OTHER_SPECIAL_CHEST_NAMES = {
    "Key Chest",
    "Lucky Legendary Chest",
    "Flame Chest",
    "Diamond Chest",
    "Titan Chest",
    "Black Chest",
    "Lucky Break Chest",
    # Classification is name-based, but each chest ID remains a separate
    # summary record so future chest-detail popups can target the exact ID.
    "VIP Chest",
    "Mythical Egg Chest",
    "Corrupted Chest",
    "Heroic Egg Chest",
}

PET_FOOD_RESOURCE_TO_CHEST_NAME = {
    "pet_food_pack.s": "Small Pet Food Basket",
    "pet_food_pack.m": "Medium Pet Food Basket",
    "pet_food_pack.l": "Large Pet Food Basket",
}


def load_json(path: Path) -> Any:
    if not path.exists():
        raise SystemExit(f"Missing required file: {path.relative_to(ROOT) if path.is_absolute() else path}")
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


def grid_theme(island: Dict[str, Any]) -> str:
    raw = str(island.get("zip_file") or "")
    stem = Path(raw).stem
    stem = re.sub(r"^gi_", "", stem, flags=re.I)
    stem = re.sub(r"_[a-z]$", "", stem, flags=re.I)
    stem = re.sub(r"_island$", "", stem, flags=re.I)
    words = [w for w in stem.split("_") if w]
    if not words:
        return f"Grid Island {as_int(island.get('id'))}"
    label = " ".join(w.capitalize() for w in words)
    return f"{label} Grid Island"


def dragon_display(dragon_id: int, localization: Dict[str, str]) -> Tuple[str, str]:
    return (
        loc_text(localization, f"tid_unit_{dragon_id}_name", f"Dragon {dragon_id}"),
        loc_text(localization, f"tid_unit_{dragon_id}_description", ""),
    )


def building_display(item_id: int, localization: Dict[str, str]) -> Tuple[str, str]:
    return (
        loc_text(localization, f"tid_building_{item_id}_name", f"Item {item_id}"),
        loc_text(localization, f"tid_building_{item_id}_description", ""),
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


def decoration_candidates(img_name: str) -> List[str]:
    raw = str(img_name or "").strip()
    if not raw:
        return []
    clean = re.sub(r"^ui_", "", raw, flags=re.I)
    clean = re.sub(r"@2x(?:\.png)?$", "", clean, flags=re.I)
    clean = re.sub(r"\.png$", "", clean, flags=re.I)
    return unique([
        f"{STATIC_BASE}mobile/ui/decorations/ui_{clean}@2x.png",
        f"{STATIC_BASE}mobile/ui/decorations/{clean}@2x.png",
        f"{STATIC_BASE}mobile/ui/decorations/{clean}.png",
        f"{STATIC_BASE}mobile/ui/decorations/HD/{clean}.png",
        f"{STATIC_BASE}mobile/ui/buildings/ui_{clean}@2x.png",
        f"{STATIC_BASE}mobile/ui/buildings/{clean}@2x.png",
        f"{STATIC_BASE}mobile/ui/buildings/{clean}.png",
        f"{STATIC_BASE}mobile/ui/buildings/HD/{clean}.png",
    ])


def collect_gatcha_rows(config: Dict[str, Any]) -> Dict[int, List[Dict[str, Any]]]:
    out: Dict[int, List[Dict[str, Any]]] = {}
    gatcha = config.get("gatcha") or {}
    for bucket in (gatcha.get("random_rewards") or [], gatcha.get("static_rewards") or []):
        for row in bucket:
            if not isinstance(row, dict):
                continue
            gid = as_int(row.get("gatcha_id"))
            if gid > 0:
                out.setdefault(gid, []).append(row)
    return out


def resolve_single_building_reward(
    chest: Dict[str, Any],
    gatcha_rows: Dict[int, List[Dict[str, Any]]],
    item_by_id: Dict[int, Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    building_ids = set()
    for gid_raw in chest.get("gatcha_ids") or []:
        gid = as_int(gid_raw)
        for reward_row in gatcha_rows.get(gid, []):
            resource = reward_row.get("resource") if isinstance(reward_row.get("resource"), dict) else {}
            buildings = resource.get("b")
            if isinstance(buildings, list):
                for item_id in buildings:
                    iid = as_int(item_id)
                    if iid > 0:
                        building_ids.add(iid)
            elif buildings is not None:
                iid = as_int(buildings)
                if iid > 0:
                    building_ids.add(iid)
    if len(building_ids) != 1:
        return None
    item = item_by_id.get(next(iter(building_ids)))
    if not item:
        return None
    group = str(item.get("group_type") or "").upper()
    if group not in {"DECO", "BUILDING", "HABITAT"}:
        return None
    return item


def make_dragon_record(dragon_id: int, item: Dict[str, Any], localization: Dict[str, str]) -> Dict[str, Any]:
    name, description = dragon_display(dragon_id, localization)
    img_mobile = str(item.get("img_name_mobile") or item.get("img_name") or "")
    candidates = dragon_candidates(img_mobile)
    return {
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


def make_building_record(item_id: int, item: Dict[str, Any], localization: Dict[str, str]) -> Dict[str, Any]:
    name, description = building_display(item_id, localization)
    img_name = str(item.get("img_name_mobile") or item.get("img_name") or "")
    candidates = decoration_candidates(img_name)
    return {
        "id": item_id,
        "item_id": item_id,
        "kind": "decoration",
        "asset_kind": "decoration",
        "group_type": str(item.get("group_type") or ""),
        "name": name,
        "description": description,
        "img_name": img_name,
        "img_name_mobile": img_name,
        "image_url": candidates[0] if candidates else "",
        "localization_name_key": f"tid_building_{item_id}_name",
        "localization_description_key": f"tid_building_{item_id}_description",
    }


def make_chest_record(
    chest_id: int,
    chest: Dict[str, Any],
    localization: Dict[str, str],
    gatcha_rows: Dict[int, List[Dict[str, Any]]],
    item_by_id: Dict[int, Dict[str, Any]],
    resolve_wrapped_building: bool = False,
) -> Dict[str, Any]:
    """Return the chest itself, never a gatcha reward hidden inside it.

    A chest can contain multiple reward types and its chest ID is important for
    future detail popups, so event summaries must preserve chest identity.
    """
    chest_name, chest_description, chest_name_key = chest_display(chest_id, chest, localization)
    img_name = str(chest.get("img_name") or "")
    candidates = chest_candidates(chest_id, img_name)
    return {
        "id": chest_id,
        "chest_id": chest_id,
        "source_chest_id": chest_id,
        "kind": "chest",
        "asset_kind": "chest",
        "name": chest_name,
        "description": chest_description,
        "img_name": img_name,
        "source_chest_img_name": img_name,
        "image_url": candidates[0] if candidates else "",
        "localization_name_key": chest_name_key,
        "localization_description_key": str(chest.get("description_key") or ""),
    }

def merge_summary_record(target: Dict[str, Dict[str, Any]], key: str, row: Dict[str, Any], count: int = 1) -> None:
    if key not in target:
        copied = dict(row)
        copied["tile_count"] = 0
        if copied.get("source_chest_id"):
            copied["source_chest_ids"] = []
        target[key] = copied
    rec = target[key]
    rec["tile_count"] = as_int(rec.get("tile_count")) + max(0, count)
    source_id = as_int(row.get("source_chest_id"))
    if source_id:
        ids = rec.setdefault("source_chest_ids", [])
        if source_id not in ids:
            ids.append(source_id)


def resource_record(
    resource: Dict[str, Any],
    item_by_id: Dict[int, Dict[str, Any]],
    chest_by_name: Dict[str, Dict[str, Any]],
    localization: Dict[str, str],
    gatcha_rows: Dict[int, List[Dict[str, Any]]],
) -> Optional[Dict[str, Any]]:
    buildings = resource.get("b")
    building_ids: List[int] = []
    if isinstance(buildings, list):
        building_ids = [as_int(x) for x in buildings if as_int(x) > 0]
    elif buildings is not None and as_int(buildings) > 0:
        building_ids = [as_int(buildings)]
    if building_ids and len(set(building_ids)) == 1:
        item_id = building_ids[0]
        item = item_by_id.get(item_id)
        if item:
            return make_building_record(item_id, item, localization)

    for resource_key, chest_name in PET_FOOD_RESOURCE_TO_CHEST_NAME.items():
        if resource_key not in resource:
            continue
        chest = chest_by_name.get(normalized_name(chest_name))
        if chest:
            cid = as_int(chest.get("id"))
            return make_chest_record(cid, chest, localization, gatcha_rows, item_by_id, resolve_wrapped_building=False)
        return {
            "id": resource_key,
            "kind": "resource",
            "asset_kind": "resource",
            "name": chest_name,
            "description": "",
            "image_url": "",
            "resource_key": resource_key,
        }
    return None


def main() -> None:
    config = load_json(CONFIG_PATH)
    localization = normalize_localization(load_json(LOCALIZATION_PATH))
    grid = config.get("grid_island") or {}

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
    gatcha_rows = collect_gatcha_rows(config)

    chest_by_name: Dict[str, Dict[str, Any]] = {}
    for cid, chest in chest_by_id.items():
        name, _desc, _key = chest_display(cid, chest, localization)
        chest_by_name.setdefault(normalized_name(name), chest)

    episodes_by_island: Dict[int, List[Dict[str, Any]]] = {}
    for episode in grid.get("episodes", []):
        if isinstance(episode, dict):
            episodes_by_island.setdefault(as_int(episode.get("island_id")), []).append(episode)

    squares_by_island: Dict[int, List[Dict[str, Any]]] = {}
    for square in grid.get("squares", []):
        if isinstance(square, dict):
            iid = as_int(square.get("island_id"))
            if iid > 0:
                squares_by_island.setdefault(iid, []).append(square)

    excluded_norm = {normalized_name(x) for x in SUMMARY_EXCLUDED_CHEST_NAMES}
    special_norm = {normalized_name(x) for x in OTHER_SPECIAL_CHEST_NAMES}

    islands_out: List[Dict[str, Any]] = []

    for island in grid.get("islands", []):
        if not isinstance(island, dict):
            continue
        island_id = as_int(island.get("id"))
        if island_id <= 0:
            continue

        raw_squares = sorted(
            squares_by_island.get(island_id, []),
            key=lambda s: (as_int(s.get("x")), as_int(s.get("y")), as_int(s.get("id"))),
        )

        dragons_summary: Dict[str, Dict[str, Any]] = {}
        items_summary: Dict[str, Dict[str, Any]] = {}
        special_summary: Dict[str, Dict[str, Any]] = {}
        squares_out: List[Dict[str, Any]] = []

        for s in raw_squares:
            stype = str(s.get("type") or "NONE").upper()
            out: Dict[str, Any] = {
                "id": as_int(s.get("id")),
                "x": as_int(s.get("x")),
                "y": as_int(s.get("y")),
                "type": stype,
                "type_id": as_int(s.get("type_id")),
                "claim_cost": as_int(s.get("claim_cost")),
                "highlight": as_int(s.get("highlight")),
            }
            if s.get("wall"):
                out["wall"] = str(s.get("wall"))
            if s.get("wall_suffix"):
                out["wall_suffix"] = str(s.get("wall_suffix"))

            if stype == "DRAGON":
                dragon_id = as_int(s.get("type_id"))
                item = item_by_id.get(dragon_id, {})
                if dragon_id > 0 and str(item.get("group_type") or "").upper() == "DRAGON":
                    reward = make_dragon_record(dragon_id, item, localization)
                    merge_summary_record(dragons_summary, f"dragon:{dragon_id}", reward, 1)
                    compact = dict(reward)
                    compact.pop("description", None)
                    compact.pop("localization_name_key", None)
                    compact.pop("localization_description_key", None)
                    out["reward"] = compact

            elif stype == "CHEST":
                chest_id = as_int(s.get("type_id"))
                chest = chest_by_id.get(chest_id, {})
                chest_name, _desc, _name_key = chest_display(chest_id, chest, localization)
                chest_name_norm = normalized_name(chest_name)
                reward = make_chest_record(chest_id, chest, localization, gatcha_rows, item_by_id)

                if chest_name_norm in special_norm:
                    # Classification follows the localized name, but the output is
                    # keyed by chest ID so equal names never merge together.
                    special_reward = make_chest_record(
                        chest_id, chest, localization, gatcha_rows, item_by_id,
                        resolve_wrapped_building=False,
                    )
                    merge_summary_record(special_summary, f"chest:{chest_id}", special_reward, 1)
                    classification = "other_special_chest"
                elif chest_name_norm in excluded_norm:
                    classification = "excluded_generic_chest"
                else:
                    summary_key = f"chest:{chest_id}"
                    merge_summary_record(items_summary, summary_key, reward, 1)
                    classification = "event_item"

                compact = dict(reward)
                compact["summary_classification"] = classification
                compact.pop("description", None)
                compact.pop("localization_name_key", None)
                compact.pop("localization_description_key", None)
                out["reward"] = compact

            elif stype == "RESOURCE":
                resource = s.get("resource") if isinstance(s.get("resource"), dict) else {}
                reward = resource_record(resource, item_by_id, chest_by_name, localization, gatcha_rows)
                if reward:
                    if reward.get("item_id"):
                        summary_key = f"item:{reward.get('item_id')}"
                    elif reward.get("source_chest_id"):
                        summary_key = f"chest:{as_int(reward.get('source_chest_id'))}"
                    else:
                        summary_key = f"resource:{reward.get('resource_key') or reward.get('name')}"
                    merge_summary_record(items_summary, summary_key, reward, 1)
                    compact = dict(reward)
                    compact.pop("description", None)
                    compact.pop("localization_name_key", None)
                    compact.pop("localization_description_key", None)
                    out["reward"] = compact
                out["resource"] = resource

            squares_out.append(out)

        # Dict insertion order follows the left-to-right square scan above, so the
        # summary naturally mirrors the event's progression instead of sorting by
        # internal IDs/names.
        dragons = list(dragons_summary.values())
        event_items = list(items_summary.values())
        other_special_chests = list(special_summary.values())

        episodes = episodes_by_island.get(island_id, [])
        episode = episodes[0] if episodes else {}
        board = island.get("board_size") if isinstance(island.get("board_size"), list) else episode.get("board_size")
        if not isinstance(board, list) or len(board) < 2:
            board = [60, 5]

        initial_square_id = as_int(island.get("initial_square_id")) or as_int(episode.get("initial_square_id"))
        final_square_id = as_int(episode.get("final_square_id"))
        start_ts = as_int(island.get("start_ts"))
        end_ts = as_int(island.get("end_ts"))

        islands_out.append({
            "id": island_id,
            "name": grid_theme(island),
            "title": "Grid Island",
            "start_ts": start_ts,
            "end_ts": end_ts,
            "start_iso": iso(start_ts),
            "end_iso": iso(end_ts),
            "board_size": [as_int(board[0]), as_int(board[1])],
            "initial_square_id": initial_square_id,
            "final_square_id": final_square_id,
            "initial_points": as_int(island.get("initial_points")),
            "pool_points": as_int(island.get("pool_points")),
            "pool_time": as_int(island.get("pool_time")),
            "currency_id": as_int(island.get("currency_id")),
            "asset_zip": str(island.get("zip_file") or ""),
            "rewards_summary": {
                "dragons": dragons,
                "event_items": event_items,
                "other_special_chests": other_special_chests,
                "excluded_chest_names": sorted(SUMMARY_EXCLUDED_CHEST_NAMES),
                "other_special_chest_names": sorted(OTHER_SPECIAL_CHEST_NAMES),
            },
            "squares": squares_out,
        })

    islands_out.sort(key=lambda r: (r["start_ts"], r["end_ts"], r["id"]))

    payload = {
        "schema_version": 2,
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

    print(f"Wrote {OUTPUT_PATH.name}: {len(islands_out)} Grid Island map(s)")
    print(f"Display names/descriptions: {LOCALIZATION_PATH.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
