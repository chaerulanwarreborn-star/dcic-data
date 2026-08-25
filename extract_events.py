#!/usr/bin/env python3
"""Build a small events.json from Dragon City's large game_config.json.

Designed for the dcic-data GitHub repository. Uses only Python's standard library.
The Blogger frontend reads events.json instead of downloading the full game_config.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "game_config.json"
OVERRIDES_PATH = ROOT / "event_overrides.json"
OUTPUT_PATH = ROOT / "events.json"

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
    """Return the guide URL for an event.

    Fog Island has historical maps addressable by ID, so its guide link must keep
    the event ID. Other guides retain their existing shared URL for now.
    """
    base = GUIDES[event_type]
    if event_type == "fog_island" and event_id > 0:
        return f"{base}?id={event_id}"
    return base


def load_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        if default is not None:
            return default
        raise SystemExit(f"Missing required file: {path.name}")
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


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
    """Best-effort theme from asset filename; display-only, never used for schedule."""
    raw = str(row.get("zip_file") or "")
    if not raw:
        return ""
    stem = Path(raw).stem
    stem = re.sub(r"^(?:hr|mr|mi|fi|gi|ti|pi)_", "", stem, flags=re.IGNORECASE)
    stem = re.sub(r"_[bcd]$", "", stem, flags=re.IGNORECASE)
    stem = re.sub(r"_island$", "", stem, flags=re.IGNORECASE)
    words = [w for w in stem.split("_") if w and not w.isdigit()]
    if not words:
        return ""
    return " ".join(w.capitalize() for w in words)


def maze_subtitle(row: Dict[str, Any]) -> str:
    name = str(row.get("name") or "").strip()
    low = name.lower()
    if low.startswith("maze island - "):
        return name.split(" - ", 1)[1].strip()
    if low.endswith(" - maze"):
        return name.rsplit(" - ", 1)[0].strip()
    if name and low not in {"maze island", "maze"}:
        return name
    return zip_theme(row)


def make_title(event_type: str, label: str, row: Dict[str, Any], items: Dict[int, Dict[str, Any]]) -> Tuple[str, str]:
    if event_type == "heroic_race":
        dragon_id = as_int(row.get("dragon_race_id"))
        dragon = items.get(dragon_id, {})
        dragon_name = clean_dragon_name(str(dragon.get("name") or ""))
        if dragon_name:
            return f"{dragon_name} Heroic Race", ""
        return label, zip_theme(row)
    if event_type == "maze_island":
        return label, maze_subtitle(row)
    return label, zip_theme(row)


def load_overrides() -> Dict[str, Dict[str, Any]]:
    raw = load_json(OVERRIDES_PATH, default={})
    if not isinstance(raw, dict):
        return {}
    return {str(k): v for k, v in raw.items() if isinstance(v, dict)}


def path_end_fallback(config: Dict[str, Any], island: Dict[str, Any]) -> int:
    """For diagnostics only: infer a missing Maze *end* from timed child paths.

    We intentionally do NOT fabricate a start time. If the config omits the island
    start, use event_overrides.json for that event.
    """
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


def build_events(config: Dict[str, Any], overrides: Dict[str, Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[str]]:
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
            schedule_source = "game_config"

            if override:
                if as_int(override.get("start_ts")) > 0:
                    start_ts = as_int(override.get("start_ts"))
                    schedule_source = "override"
                if as_int(override.get("end_ts")) > 0:
                    end_ts = as_int(override.get("end_ts"))
                    schedule_source = "override"

            if start_ts <= 0 or end_ts <= start_ts:
                extra = ""
                if event_type == "maze_island":
                    child_end = path_end_fallback(config, row)
                    if child_end:
                        extra = f" Child paths indicate end_ts={child_end} ({iso(child_end)}), but start is missing."
                warnings.append(f"Skipped {key}: incomplete schedule start={start_ts}, end={end_ts}.{extra}")
                continue

            title, subtitle = make_title(event_type, label, row, items)
            event: Dict[str, Any] = {
                "key": key,
                "id": event_id,
                "type": event_type,
                "type_label": label,
                "title": title,
                "subtitle": subtitle,
                "start_ts": start_ts,
                "end_ts": end_ts,
                "start_iso": iso(start_ts),
                "end_iso": iso(end_ts),
                "guide": guide_url(event_type, event_id),
                "schedule_source": schedule_source,
                "source_section": section,
            }

            if row.get("building_id") is not None:
                event["building_id"] = as_int(row.get("building_id"))
            if row.get("dragon_race_id") is not None:
                did = as_int(row.get("dragon_race_id"))
                event["featured_dragon_id"] = did
                dragon = items.get(did)
                if dragon:
                    event["featured_dragon_name"] = str(dragon.get("name") or "")
                    event["featured_dragon_img_name"] = str(dragon.get("img_name") or "")
            if isinstance(row.get("featured_dragons"), list):
                event["featured_dragon_ids"] = [as_int(x) for x in row.get("featured_dragons", []) if as_int(x) > 0]
            if row.get("zip_file"):
                event["asset_zip"] = str(row.get("zip_file"))
            if override.get("note"):
                event["schedule_note"] = str(override.get("note"))

            events.append(event)

    # Deduplicate by key, then sort chronologically.
    dedup: Dict[str, Dict[str, Any]] = {e["key"]: e for e in events}
    events = sorted(dedup.values(), key=lambda e: (e["start_ts"], e["end_ts"], e["key"]))
    return events, warnings


def main() -> None:
    config = load_json(CONFIG_PATH)
    overrides = load_overrides()
    events, warnings = build_events(config, overrides)

    payload = {
        "schema_version": 1,
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
