#!/usr/bin/env python3
"""Build fog_island.json for Dragon City Information Center.

Reads game_config.json + English localization and writes a compact,
browser-friendly Fog Island dataset for the Blogger guide/simulator.

Display names/descriptions are resolved from localization. game_config names are
used only as internal asset identifiers, never as the preferred display text.

No third-party Python packages are required.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "game_config.json"
OUTPUT_PATH = ROOT / "fog_island.json"

DRAGON_BASE = "https://dci-static-s1.socialpointgames.com/static/dragoncity/mobile/ui/dragons/HD/"
CHEST_BASE = "https://dci-static-s1.socialpointgames.com/static/dragoncity/mobile/ui/chests/"
STATIC_BASE = "https://dci-static-s1.socialpointgames.com/static/dragoncity/"

# Generic Fog chests remain on the map but are excluded from Rewards Summary.
# Classification is localization-name based so future alternate chest IDs are
# handled correctly without merging different IDs into one reward card.
SUMMARY_EXCLUDED_CHEST_NAMES = {"Bronze Chest", "Silver Chest", "Gold Chest"}
SUMMARY_EXCLUDED_CHEST_IDS_LEGACY = {7020, 7021, 7022}


def load_json(path: Path) -> Any:
    if not path.exists():
        raise SystemExit(f"Missing required file: {path.name}")
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def find_localization_path() -> Path:
    # DCIC repository canonical location. Keep the existing repository layout:
    #   localization/dragon_city_localization_baseline_en.json
    canonical = ROOT / "localization" / "dragon_city_localization_baseline_en.json"
    if canonical.exists():
        return canonical

    # Backward-compatible fallbacks are only for local/manual testing. They do
    # not change the repository convention and are not required by the workflow.
    fallbacks = [
        ROOT / "dragon_city_localization_baseline_en.json",
    ]
    for path in fallbacks:
        if path.exists():
            return path

    matches = sorted((ROOT / "localization").glob("*localization*en*.json")) if (ROOT / "localization").exists() else []
    if matches:
        return matches[0]

    raise SystemExit(
        "Missing English localization JSON: "
        "localization/dragon_city_localization_baseline_en.json"
    )


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


def fog_theme(island: Dict[str, Any]) -> str:
    raw = str(island.get("zip_file") or "")
    stem = Path(raw).stem
    stem = re.sub(r"^fi_", "", stem, flags=re.I)
    stem = re.sub(r"_[a-z]$", "", stem, flags=re.I)
    stem = re.sub(r"_island$", "", stem, flags=re.I)
    words = [w for w in stem.split("_") if w]
    if not words:
        return f"Fog Island {as_int(island.get('id'))}"
    return " ".join(w.capitalize() for w in words)


def dragon_display(item_id: int, localization: Dict[str, str]) -> Tuple[str, str]:
    return (
        loc_text(localization, f"tid_unit_{item_id}_name", f"Dragon {item_id}"),
        loc_text(localization, f"tid_unit_{item_id}_description", ""),
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
    name = loc_text(localization, name_key)
    if not name:
        name = loc_text(localization, type_key)
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
        # Modern/common convention: ui_{chest_id}_{internal_name}@2x.png
        f"{CHEST_BASE}ui_{chest_id}_{clean}@2x.png",
        f"{CHEST_BASE}ui_{chest_id}_{clean}.png",
        # Some configs already contain the complete internal name without id.
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
    """Return broad Socialpoint static candidates for DECO/building-style items.

    Dragon City has used multiple directories/naming variants over time, so the
    browser and fog asset builder try these in order instead of hard-coding one.
    """
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
    """Resolve wrappers whose gatcha consistently points to one building/deco item."""
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


def make_dragon_record(
    dragon_id: int,
    item: Dict[str, Any],
    localization: Dict[str, str],
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    name, description = dragon_display(dragon_id, localization)
    img_mobile = str(item.get("img_name_mobile") or item.get("img_name") or "")
    candidates = dragon_candidates(img_mobile)
    out: Dict[str, Any] = {
        "id": dragon_id,
        "kind": "dragon",
        "asset_kind": "dragon",
        "name": name,
        "description": description,
        "dragon_rarity": str(item.get("dragon_rarity") or "").upper(),
        "rarity": item.get("rarity"),
        "img_name_mobile": img_mobile,
        "image_url": candidates[0] if candidates else "",
    }
    if extra:
        out.update(extra)
    return out


def make_chest_record(
    chest_id: int,
    chest: Dict[str, Any],
    localization: Dict[str, str],
    gatcha_rows: Dict[int, List[Dict[str, Any]]],
    item_by_id: Dict[int, Dict[str, Any]],
) -> Dict[str, Any]:
    """Create display metadata for the chest itself.

    Never replace a chest with one of its gatcha contents: a gatcha can contain
    multiple reward types, and preserving the exact chest ID is required for
    future chest-detail popups.
    """
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


def is_summary_excluded_chest(
    chest_id: int,
    chest: Dict[str, Any],
    localization: Dict[str, str],
) -> bool:
    name, _description, _key = chest_display(chest_id, chest, localization)
    names = {normalized_name(x) for x in SUMMARY_EXCLUDED_CHEST_NAMES}
    return normalized_name(name) in names or chest_id in SUMMARY_EXCLUDED_CHEST_IDS_LEGACY

def main() -> None:
    config = load_json(CONFIG_PATH)
    localization_path = find_localization_path()
    localization = normalize_localization(load_json(localization_path))
    fog = config.get("fog_island") or {}

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
    fog_reward_by_id = {
        as_int(row.get("id")): row
        for row in fog.get("rewards", [])
        if isinstance(row, dict) and as_int(row.get("id")) > 0
    }

    squares_by_island: Dict[int, List[Dict[str, Any]]] = {}
    for square in fog.get("squares", []):
        if not isinstance(square, dict):
            continue
        iid = as_int(square.get("island_id"))
        if iid > 0:
            squares_by_island.setdefault(iid, []).append(square)

    rewards_by_island: Dict[int, List[Dict[str, Any]]] = {}
    for reward in fog.get("rewards", []):
        if not isinstance(reward, dict):
            continue
        iid = as_int(reward.get("island_id"))
        if iid > 0:
            rewards_by_island.setdefault(iid, []).append(reward)

    islands_out: List[Dict[str, Any]] = []

    for island in fog.get("islands", []):
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
        dragon_seen = set()
        for fr in rewards_by_island.get(island_id, []):
            if str(fr.get("type") or "").upper() != "DRAGON_PIECE":
                continue
            dragon_id = as_int(fr.get("reward_id"))
            item = item_by_id.get(dragon_id, {})
            if str(item.get("group_type") or "").upper() != "DRAGON":
                continue
            if dragon_id in dragon_seen:
                continue
            dragon_seen.add(dragon_id)
            dragons.append(make_dragon_record(
                dragon_id,
                item,
                localization,
                {
                    "reward_config_id": as_int(fr.get("id")),
                    "num_pieces": as_int(fr.get("num_pieces")),
                    "last_piece_cost": as_int(fr.get("last_piece_cost")),
                },
            ))

        used_chest_ids = sorted({
            as_int(s.get("type_id"))
            for s in raw_squares
            if str(s.get("type") or "").upper() == "CHEST" and as_int(s.get("type_id")) > 0
        })

        event_items: List[Dict[str, Any]] = []
        for chest_id in used_chest_ids:
            chest = chest_by_id.get(chest_id, {})
            if is_summary_excluded_chest(chest_id, chest, localization):
                continue
            event_items.append(make_chest_record(
                chest_id, chest, localization, gatcha_rows, item_by_id,
            ))

        squares_out: List[Dict[str, Any]] = []
        for s in raw_squares:
            stype = str(s.get("type") or "NONE").upper()
            out: Dict[str, Any] = {
                "id": as_int(s.get("id")),
                "x": as_int(s.get("x")),
                "y": as_int(s.get("y")),
                "type": stype,
                "claim_cost": as_int(s.get("claim_cost")),
                "come_back_cost": as_int(s.get("come_back_cost")) or 5,
                "highlight": as_int(s.get("highlight")),
            }

            if stype == "CHEST":
                chest_id = as_int(s.get("type_id"))
                reward = make_chest_record(
                    chest_id,
                    chest_by_id.get(chest_id, {}),
                    localization,
                    gatcha_rows,
                    item_by_id,
                )
                reward["summary_excluded"] = is_summary_excluded_chest(chest_id, chest_by_id.get(chest_id, {}), localization)
                # Keep map rows compact: descriptions/localization keys live in
                # Rewards Summary; the shared theme resolver rebuilds image
                # candidates from asset_kind + img_name when needed.
                reward.pop("description", None)
                reward.pop("localization_name_key", None)
                reward.pop("localization_description_key", None)
                out["reward"] = reward

            elif stype == "DRAGON_PIECE":
                reward_config_id = as_int(s.get("reward_id"))
                fr = fog_reward_by_id.get(reward_config_id, {})
                dragon_id = as_int(fr.get("reward_id"))
                item = item_by_id.get(dragon_id, {})
                reward = make_dragon_record(
                    dragon_id,
                    item,
                    localization,
                    {
                        "kind": "dragon_piece",
                        "asset_kind": "dragon",
                        "reward_config_id": reward_config_id,
                        "dragon_id": dragon_id,
                        "num_pieces": as_int(fr.get("num_pieces")),
                        "last_piece_cost": as_int(fr.get("last_piece_cost")),
                    },
                )
                reward.pop("description", None)
                out["reward"] = reward

            elif stype == "RESOURCE":
                resource = s.get("resource") if isinstance(s.get("resource"), dict) else {}
                out["reward"] = {
                    "kind": "resource",
                    "asset_kind": "resource",
                    "resource": resource,
                    "name": "Special Resource",
                    "description": "",
                    "image_url": "",
                }

            squares_out.append(out)

        start_ts = as_int(island.get("start_ts"))
        end_ts = as_int(island.get("end_ts"))
        board = island.get("board_size") if isinstance(island.get("board_size"), list) else [15, 15]

        islands_out.append({
            "id": island_id,
            "name": fog_theme(island),
            "title": "Fog Island",
            "start_ts": start_ts,
            "end_ts": end_ts,
            "start_iso": iso(start_ts),
            "end_iso": iso(end_ts),
            "board_size": [as_int(board[0]), as_int(board[1])] if len(board) >= 2 else [15, 15],
            "initial_square_id": as_int(island.get("initial_square_id")),
            "initial_points": as_int(island.get("initial_points")),
            "pool_points": as_int(island.get("pool_points")),
            "pool_time": as_int(island.get("pool_time")),
            "currency_id": as_int(island.get("currency_id")),
            "asset_zip": str(island.get("zip_file") or ""),
            "rewards_summary": {
                "dragons": dragons,
                "event_items": event_items,
                "excluded_generic_chest_names": sorted(SUMMARY_EXCLUDED_CHEST_NAMES),
                "excluded_generic_chest_ids_legacy": sorted(SUMMARY_EXCLUDED_CHEST_IDS_LEGACY),
            },
            "squares": squares_out,
        })

    islands_out.sort(key=lambda r: (r["start_ts"], r["end_ts"], r["id"]))

    payload = {
        "schema_version": 3,
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "source_file": CONFIG_PATH.name,
        "localization_file": localization_path.name,
        "display_text_source": "localization",
        "island_count": len(islands_out),
        "islands": islands_out,
    }

    with OUTPUT_PATH.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
        f.write("\n")

    print(f"Wrote {OUTPUT_PATH.name}: {len(islands_out)} Fog Island map(s)")
    print(f"Display names/descriptions: {localization_path.name}")


if __name__ == "__main__":
    main()
