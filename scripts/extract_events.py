#!/usr/bin/env python3
"""Build the compact homepage events feed from Dragon City's game_config.json.

This feed is intentionally separate from the detailed event-guide feeds
(fog_island.json, grid_island.json, tower_island.json, heroic_race.json).  It
contains only the schedule/card data needed by the site-wide Current/Upcoming
Events UI and menu indicators.
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
OVERRIDES_DIR = REPO_ROOT / "overrides"
LOCALIZATION_DIR = REPO_ROOT / "localization"
RAW_DIR = Path(os.environ.get("DCIC_RAW_DIR", REPO_ROOT.parent / "the-void"))

CONFIG_PATH = RAW_DIR / "game_config.json"
OVERRIDES_PATH = OVERRIDES_DIR / "event_overrides.json"
LOCALIZATION_PATH = LOCALIZATION_DIR / "dragon_city_localization_baseline_en.json"
OUTPUT_PATH = DIST_DIR / "events.json"

DRAGON_THUMB_BASE = "https://dci-static-s1.socialpointgames.com/static/dragoncity/mobile/ui/dragons/HD/"
RARITY_ORDER = {"H": 0, "M": 1, "L": 2, "E": 3, "V": 4, "R": 5, "C": 6}

GUIDES = {
    "heroic_race": "/p/heroic-race-guide.html",
    "maze_island": "/p/maze-island-guide.html",
    "fog_island": "/p/fog-island-guide.html",
    "grid_island": "/p/grid-island-guide.html",
    "puzzle_island": "/p/puzzle-island-guide.html",
    "tower_island": "/p/tower-island-guide.html",
    "event_island": "/p/event-island-guide.html",
}

SECTION_SPECS = [
    ("heroic_races", "heroic_race", "Heroic Race"),
    ("maze_island", "maze_island", "Maze Island"),
    ("fog_island", "fog_island", "Fog Island"),
    ("grid_island", "grid_island", "Grid Island"),
    ("puzzle_island", "puzzle_island", "Puzzle Island"),
    ("tower_island", "tower_island", "Tower Island"),
    ("event_island", "event_island", "Event Island"),
]


def guide_url(event_type: str, event_id: int) -> str:
    base = GUIDES[event_type]
    if event_type in {"fog_island", "grid_island", "maze_island", "tower_island", "heroic_race"} and event_id > 0:
        return f"{base}?id={event_id}"
    return base


def load_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        if default is not None:
            return default
        raise SystemExit(f"Missing required file: {path.name}")
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


def loc_text(localization: Dict[str, str], key: Any, fallback: str = "") -> str:
    value = str(localization.get(str(key or ""), "") or "").strip()
    return value or fallback


def as_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def item_index(config: Dict[str, Any]) -> Dict[int, Dict[str, Any]]:
    result: Dict[int, Dict[str, Any]] = {}
    for item in config.get("items", []):
        if isinstance(item, dict) and "id" in item:
            result[as_int(item.get("id"))] = item
    return result


HEROIC_RACE_GENERIC_ISLAND_URL = (
    "https://raw.githubusercontent.com/chaerulanwarreborn-star/dcic-assets/"
    "main/items/buildings/0837_heroic_island_generic.png"
)


def building_image_url(event_type: str, building_id: int, items: Dict[int, Dict[str, Any]]) -> str:
    """Resolve the background island/building artwork for an event card.

    Heroic Race and Mythical Race events (event_type == "heroic_race") always
    use the shared generic island artwork, since their actual in-game
    buildings vary and don't have a single representative asset.

    Otherwise: look up building_id in the items index, skip it if the match
    is a DRAGON-type item (wrong id collision) rather than a building, and
    read img_name_mobile to build the official static asset URL. Returns ""
    if no usable image can be resolved (caller can fall back to nothing, or
    a manual override can be supplied via event_overrides.json).
    """
    if event_type == "heroic_race":
        return HEROIC_RACE_GENERIC_ISLAND_URL
    if building_id <= 0:
        return ""
    item = items.get(building_id)
    if not item:
        return ""
    if str(item.get("group_type", "")).strip().upper() == "DRAGON":
        return ""
    img_name = str(item.get("img_name_mobile") or "").strip()
    if not img_name:
        return ""
    return (
        "https://dci-static-s1.socialpointgames.com/static/dragoncity/"
        f"mobile/ui/buildings/ui_{img_name}@2x.png"
    )


def timestamps(row: Dict[str, Any]) -> Tuple[int, int]:
    if "start_ts" in row or "end_ts" in row:
        return as_int(row.get("start_ts")), as_int(row.get("end_ts"))
    availability = row.get("availability")
    if isinstance(availability, dict):
        return as_int(availability.get("from")), as_int(availability.get("to"))
    return 0, 0


def clean_dragon_name(name: str) -> str:
    return re.sub(r"\s+Dragon$", "", name.strip(), flags=re.IGNORECASE)


def zip_theme(row: Dict[str, Any]) -> str:
    raw = str(row.get("zip_file") or "")
    if not raw:
        return ""
    stem = Path(raw).stem
    stem = re.sub(r"^(?:hr|mr|mi|fi|gi|ti|pi|ri)_", "", stem, flags=re.IGNORECASE)
    stem = re.sub(r"_[bcd]$", "", stem, flags=re.IGNORECASE)
    stem = re.sub(r"_(?:fog|grid|maze|tower|puzzle|runner)_?island$", "", stem, flags=re.IGNORECASE)
    stem = re.sub(r"_island$", "", stem, flags=re.IGNORECASE)
    words = [w for w in stem.split("_") if w and not w.isdigit()]
    if not words:
        return ""
    return " ".join(w.capitalize() for w in words)


def maze_theme(row: Dict[str, Any]) -> str:
    name = str(row.get("name") or "").strip()
    low = name.lower()
    if low.startswith("maze island - "):
        return name.split(" - ", 1)[1].strip()
    if low.endswith(" - maze"):
        return name.rsplit(" - ", 1)[0].strip()
    if name and low not in {"maze island", "maze"}:
        return name
    return zip_theme(row)


def full_event_title(theme: str, label: str) -> str:
    theme = str(theme or "").strip()
    label = str(label or "").strip()
    if not theme:
        return label
    if label.lower() in theme.lower():
        return theme
    return f"{theme} {label}".strip()


def race_variant(label: str) -> str:
    token = re.sub(r"[^a-z0-9]+", "_", str(label or "").lower()).strip("_")
    aliases = {
        "heroic_race": "heroic_race",
        "heroic_marathon": "heroic_marathon",
        "alliance_race": "alliance_race",
        "mythical_race": "mythical_race",
        "mythical_marathon": "mythical_marathon",
    }
    return aliases.get(token, token or "heroic_race")


def make_title(
    event_type: str,
    label: str,
    row: Dict[str, Any],
    items: Dict[int, Dict[str, Any]],
    localization: Dict[str, str],
) -> str:
    if event_type == "heroic_race":
        dragon_id = as_int(row.get("dragon_race_id"))
        dragon = items.get(dragon_id, {})
        dragon_name = clean_dragon_name(
            loc_text(localization, f"tid_unit_{dragon_id}_name", str(dragon.get("name") or ""))
        )
        return f"{dragon_name} {label}".strip() if dragon_name else label
    if event_type == "maze_island":
        return full_event_title(maze_theme(row), label)
    return full_event_title(zip_theme(row), label)


def load_overrides() -> Dict[str, Dict[str, Any]]:
    raw = load_json(OVERRIDES_PATH, default={})
    if not isinstance(raw, dict):
        return {}
    return {str(k): v for k, v in raw.items() if isinstance(v, dict)}


def path_end_fallback(config: Dict[str, Any], island: Dict[str, Any]) -> int:
    path_ids = set(island.get("paths") or [])
    if not path_ids:
        return 0
    ends: List[int] = []
    for path in config.get("maze_island", {}).get("paths", []):
        if path.get("id") not in path_ids:
            continue
        av = path.get("availability")
        if isinstance(av, dict):
            end = as_int(av.get("to"))
            if end > 0:
                ends.append(end)
    return max(ends) if ends else 0


def iso(ts: int) -> str:
    return datetime.fromtimestamp(ts, timezone.utc).isoformat().replace("+00:00", "Z")


def extract_egg_ids(value: Any) -> List[int]:
    """Collect direct deterministic egg IDs from nested reward structures."""
    out: List[int] = []

    def visit(node: Any) -> None:
        if isinstance(node, dict):
            for key, val in node.items():
                if key == "egg":
                    if isinstance(val, list):
                        for item in val:
                            did = as_int(item)
                            if did > 0:
                                out.append(did)
                    else:
                        did = as_int(val)
                        if did > 0:
                            out.append(did)
                else:
                    visit(val)
        elif isinstance(node, list):
            for item in node:
                visit(item)

    visit(value)
    return out


def dragon_record(dragon_id: int, items: Dict[int, Dict[str, Any]], localization: Dict[str, str]) -> Optional[Dict[str, Any]]:
    item = items.get(dragon_id, {})
    if not item or str(item.get("group_type") or "").upper() != "DRAGON":
        return None
    img_name = str(item.get("img_name_mobile") or item.get("img_name") or "").strip()
    name = loc_text(localization, f"tid_unit_{dragon_id}_name", str(item.get("name") or f"Dragon {dragon_id}"))
    rarity = str(item.get("dragon_rarity") or "").upper()
    return {
        "id": dragon_id,
        "name": name,
        "rarity": rarity,
        "img_name": img_name,
        "thumbnail": f"{DRAGON_THUMB_BASE}thumb_{img_name}_3.png" if img_name else "",
    }


def sort_featured(ids: Iterable[int], items: Dict[int, Dict[str, Any]], localization: Dict[str, str]) -> List[Dict[str, Any]]:
    seen = set()
    rows: List[Dict[str, Any]] = []
    for raw_id in ids:
        did = as_int(raw_id)
        if did <= 0 or did in seen:
            continue
        seen.add(did)
        row = dragon_record(did, items, localization)
        if row:
            rows.append(row)
    rows.sort(key=lambda d: RARITY_ORDER.get(str(d.get("rarity") or "").upper(), 99))
    return rows


def featured_dragon_ids(config: Dict[str, Any], event_type: str, row: Dict[str, Any]) -> List[int]:
    event_id = as_int(row.get("id"))
    ids: List[int] = []

    # Any explicit config list remains a useful fallback/primary source.
    if isinstance(row.get("featured_dragons"), list):
        ids.extend(as_int(x) for x in row.get("featured_dragons", []))

    if event_type == "heroic_race":
        featured = as_int(row.get("dragon_race_id"))
        if featured:
            ids.append(featured)
        reward_by_id = {
            as_int(r.get("id")): r
            for r in config.get("heroic_races", {}).get("rewards", [])
            if isinstance(r, dict)
        }
        # Final-position reward tables provide the authoritative race dragon set.
        for reward_id in row.get("rewards", []) or []:
            ids.extend(extract_egg_ids(reward_by_id.get(as_int(reward_id), {})))

    elif event_type == "fog_island":
        for reward in config.get("fog_island", {}).get("rewards", []):
            if isinstance(reward, dict) and as_int(reward.get("island_id")) == event_id:
                did = as_int(reward.get("reward_id"))
                if did:
                    ids.append(did)

    elif event_type == "grid_island":
        for square in config.get("grid_island", {}).get("squares", []):
            if not isinstance(square, dict) or as_int(square.get("island_id")) != event_id:
                continue
            if str(square.get("type") or "").upper() == "DRAGON":
                did = as_int(square.get("type_id"))
                if did:
                    ids.append(did)

    elif event_type == "maze_island":
        path_ids = {as_int(x) for x in row.get("paths", []) or []}
        for path in config.get("maze_island", {}).get("paths", []):
            if isinstance(path, dict) and as_int(path.get("id")) in path_ids:
                did = as_int(path.get("dragon_type"))
                if did:
                    ids.append(did)

    elif event_type == "tower_island":
        tower = config.get("tower_island", {})
        reward_by_id = {
            as_int(r.get("id")): r for r in tower.get("rewards", []) if isinstance(r, dict)
        }
        # Piece reward configs are deterministic featured dragons.
        for reward in tower.get("rewards", []):
            if isinstance(reward, dict) and as_int(reward.get("island_id")) == event_id:
                did = as_int(reward.get("dragon_reward_id"))
                if did:
                    ids.append(did)
        # Some final tower squares award an egg directly.
        for square in tower.get("squares", []):
            if not isinstance(square, dict) or as_int(square.get("island_id")) != event_id:
                continue
            ids.extend(extract_egg_ids(square.get("rewards_array")))
            reward_id = as_int(square.get("piece_reward_id"))
            if reward_id:
                did = as_int(reward_by_id.get(reward_id, {}).get("dragon_reward_id"))
                if did:
                    ids.append(did)

    elif event_type == "puzzle_island":
        # Modern Puzzle configs expose the highlighted dragons directly.
        ids.extend(as_int(x) for x in row.get("featured_dragons", []) or [])

    return [x for x in ids if as_int(x) > 0]


def build_events(
    config: Dict[str, Any],
    overrides: Dict[str, Dict[str, Any]],
    localization: Dict[str, str],
) -> Tuple[List[Dict[str, Any]], List[str]]:
    items = item_index(config)
    events: List[Dict[str, Any]] = []
    warnings: List[str] = []

    for section, event_type, label in SECTION_SPECS:
        islands = config.get(section, {}).get("islands", [])
        if not isinstance(islands, list):
            continue

        for row in islands:
            if not isinstance(row, dict):
                continue
            event_id = as_int(row.get("id"))
            if event_id <= 0:
                continue

            start_ts, end_ts = timestamps(row)
            key = f"{event_type}:{event_id}"
            override = overrides.get(key, {})
            override_used = False

            # Overrides are fallbacks only. Never overwrite a complete official
            # window when a newer game_config has fixed the schedule itself.
            if start_ts <= 0 and as_int(override.get("start_ts")) > 0:
                start_ts = as_int(override.get("start_ts"))
                override_used = True
            if (end_ts <= 0 or end_ts <= start_ts) and as_int(override.get("end_ts")) > start_ts:
                end_ts = as_int(override.get("end_ts"))
                override_used = True

            if start_ts <= 0 or end_ts <= start_ts:
                extra = ""
                if event_type == "maze_island":
                    child_end = path_end_fallback(config, row)
                    if child_end:
                        extra = f" Child paths indicate end_ts={child_end} ({iso(child_end)}), but start is missing."
                warnings.append(f"Skipped {key}: incomplete schedule start={start_ts}, end={end_ts}.{extra}")
                continue

            row_label = label
            variant = event_type
            if event_type == "heroic_race":
                row_label = loc_text(localization, row.get("island_title_tid"), label).title()
                variant = race_variant(row_label)

            title = make_title(event_type, row_label, row, items, localization)
            if override.get("title"):
                title = str(override.get("title"))
            featured = sort_featured(featured_dragon_ids(config, event_type, row), items, localization)
            event: Dict[str, Any] = {
                "key": key,
                "id": event_id,
                "type": event_type,
                "variant": variant,
                "type_label": row_label,
                "title": title,
                # Kept for backwards compatibility; homepage v2 intentionally renders only 2 title levels.
                "subtitle": "",
                "start_ts": start_ts,
                "end_ts": end_ts,
                "start_iso": iso(start_ts),
                "end_iso": iso(end_ts),
                "guide": guide_url(event_type, event_id),
                "schedule_source": "override" if override_used else "game_config",
                "source_section": section,
                "featured_dragons": featured,
                "featured_dragon_count": len(featured),
            }

            if row.get("building_id") is not None:
                event["building_id"] = as_int(row.get("building_id"))

            building_image = str(override.get("building_image_url") or "").strip()
            if not building_image:
                building_image = building_image_url(event_type, as_int(row.get("building_id")), items)
            if building_image:
                event["building_image"] = building_image

            if row.get("dragon_race_id") is not None:
                event["featured_dragon_id"] = as_int(row.get("dragon_race_id"))
            if row.get("zip_file"):
                event["asset_zip"] = str(row.get("zip_file"))
            if override_used and override.get("note"):
                event["schedule_note"] = str(override.get("note"))

            events.append(event)

    dedup: Dict[str, Dict[str, Any]] = {e["key"]: e for e in events}
    events = sorted(dedup.values(), key=lambda e: (e["start_ts"], e["end_ts"], e["key"]))
    return events, warnings


def main() -> None:
    config = load_json(CONFIG_PATH)
    overrides = load_overrides()
    localization = normalize_localization(load_json(LOCALIZATION_PATH))
    events, warnings = build_events(config, overrides, localization)

    payload = {
        "schema_version": 2,
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "source_file": CONFIG_PATH.name,
        "event_count": len(events),
        "events": events,
        "warnings": warnings,
    }

    with OUTPUT_PATH.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
        f.write("\n")

    print(f"Wrote {OUTPUT_PATH.name}: {len(events)} events, {len(warnings)} warning(s)")
    for warning in warnings:
        print("WARNING:", warning)


if __name__ == "__main__":
    main()
