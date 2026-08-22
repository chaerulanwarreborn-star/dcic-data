#!/usr/bin/env python3
"""Build fog_island.json for Dragon City Information Center.

Reads the large game_config.json and writes a compact, browser-friendly Fog Island
dataset for the Blogger guide/simulator.

No third-party Python packages are required.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "game_config.json"
OUTPUT_PATH = ROOT / "fog_island.json"

DRAGON_BASE = "https://dci-static-s1.socialpointgames.com/static/dragoncity/mobile/ui/dragons/HD/"
CHEST_BASE = "https://dci-static-s1.socialpointgames.com/static/dragoncity/mobile/ui/chests/"
DECO_BASE = "https://dci-static-s1.socialpointgames.com/static/dragoncity/mobile/ui/decorations/"

# These generic Fog chests still appear on the map, but are excluded from
# Rewards Summary > Event Items.
SUMMARY_EXCLUDED_CHESTS = {7020, 7021, 7022}


def load_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        raise SystemExit(f"Missing required file: {path.name}")
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def as_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def iso(ts: int) -> str:
    if ts <= 0:
        return ""
    return datetime.fromtimestamp(ts, timezone.utc).isoformat().replace("+00:00", "Z")


def pretty_asset_name(raw: str) -> str:
    value = str(raw or "")
    value = re.sub(r"^(?:ui_)?", "", value, flags=re.I)
    value = re.sub(r"^(?:chest_|warriorschest_\d+_)", "", value, flags=re.I)
    value = value.replace("_", " ").strip()
    value = re.sub(r"\b([smlx]{1,2})\b", lambda m: m.group(1).upper(), value, flags=re.I)
    return " ".join(w.capitalize() if not w.isupper() else w for w in value.split()) or "Reward"


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


def main() -> None:
    config = load_json(CONFIG_PATH)
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
            key=lambda s: (as_int(s.get("y")), as_int(s.get("x")), as_int(s.get("id")))
        )

        # Resolve dragon rewards configured for this Fog Island.
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
            img_mobile = str(item.get("img_name_mobile") or item.get("img_name") or "")
            dragons.append({
                "id": dragon_id,
                "name": str(item.get("name") or f"Dragon {dragon_id}"),
                "rarity": item.get("rarity"),
                "img_name_mobile": img_mobile,
                "image_url": f"{DRAGON_BASE}thumb_{img_mobile}_3.png" if img_mobile else "",
                "reward_config_id": as_int(fr.get("id")),
                "num_pieces": as_int(fr.get("num_pieces")),
                "last_piece_cost": as_int(fr.get("last_piece_cost")),
            })

        # Resolve unique chest types used on the map.
        used_chest_ids = sorted({
            as_int(s.get("type_id"))
            for s in raw_squares
            if str(s.get("type") or "").upper() == "CHEST" and as_int(s.get("type_id")) > 0
        })

        event_items: List[Dict[str, Any]] = []
        for chest_id in used_chest_ids:
            if chest_id in SUMMARY_EXCLUDED_CHESTS:
                continue
            chest = chest_by_id.get(chest_id, {})
            img_name = str(chest.get("img_name") or "")
            event_items.append({
                "id": chest_id,
                "name": pretty_asset_name(img_name) if img_name else f"Chest {chest_id}",
                "img_name": img_name,
                "image_url": f"{CHEST_BASE}ui_{img_name}@2x.png" if img_name else "",
            })

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
                chest = chest_by_id.get(chest_id, {})
                img_name = str(chest.get("img_name") or "")
                out["reward"] = {
                    "kind": "chest",
                    "id": chest_id,
                    "name": pretty_asset_name(img_name) if img_name else f"Chest {chest_id}",
                    "img_name": img_name,
                    "image_url": f"{CHEST_BASE}ui_{img_name}@2x.png" if img_name else "",
                    "summary_excluded": chest_id in SUMMARY_EXCLUDED_CHESTS,
                }

            elif stype == "DRAGON_PIECE":
                reward_config_id = as_int(s.get("reward_id"))
                fr = fog_reward_by_id.get(reward_config_id, {})
                dragon_id = as_int(fr.get("reward_id"))
                item = item_by_id.get(dragon_id, {})
                img_mobile = str(item.get("img_name_mobile") or item.get("img_name") or "")
                out["reward"] = {
                    "kind": "dragon_piece",
                    "reward_config_id": reward_config_id,
                    "dragon_id": dragon_id,
                    "name": str(item.get("name") or f"Dragon {dragon_id}"),
                    "img_name_mobile": img_mobile,
                    "image_url": f"{DRAGON_BASE}thumb_{img_mobile}_3.png" if img_mobile else "",
                    "num_pieces": as_int(fr.get("num_pieces")),
                    "last_piece_cost": as_int(fr.get("last_piece_cost")),
                }

            elif stype == "RESOURCE":
                resource = s.get("resource") if isinstance(s.get("resource"), dict) else {}
                out["reward"] = {
                    "kind": "resource",
                    "resource": resource,
                    "name": "Special Resource",
                    "image_url": "",
                }

            squares_out.append(out)

        start_ts = as_int(island.get("start_ts"))
        end_ts = as_int(island.get("end_ts"))
        board = island.get("board_size") if isinstance(island.get("board_size"), list) else [15, 15]
        initial_square_id = as_int(island.get("initial_square_id"))

        islands_out.append({
            "id": island_id,
            "name": fog_theme(island),
            "title": "Fog Island",
            "start_ts": start_ts,
            "end_ts": end_ts,
            "start_iso": iso(start_ts),
            "end_iso": iso(end_ts),
            "board_size": [as_int(board[0]), as_int(board[1])] if len(board) >= 2 else [15, 15],
            "initial_square_id": initial_square_id,
            "initial_points": as_int(island.get("initial_points")),
            "pool_points": as_int(island.get("pool_points")),
            "pool_time": as_int(island.get("pool_time")),
            "currency_id": as_int(island.get("currency_id")),
            "asset_zip": str(island.get("zip_file") or ""),
            "rewards_summary": {
                "dragons": dragons,
                "event_items": event_items,
                "excluded_generic_chest_ids": sorted(SUMMARY_EXCLUDED_CHESTS),
            },
            "squares": squares_out,
        })

    islands_out.sort(key=lambda r: (r["start_ts"], r["end_ts"], r["id"]))

    payload = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "source_file": CONFIG_PATH.name,
        "island_count": len(islands_out),
        "islands": islands_out,
    }

    with OUTPUT_PATH.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
        f.write("\n")

    print(f"Wrote {OUTPUT_PATH.name}: {len(islands_out)} Fog Island map(s)")


if __name__ == "__main__":
    main()
