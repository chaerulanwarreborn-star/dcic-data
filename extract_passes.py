#!/usr/bin/env python3
"""Build passes.json for the DCIC homepage.

Divine Pass and Progression Pass data intentionally live in a separate feed from
regular Island/Race events.  This keeps the existing event-guide extractors and
page-specific JSON files untouched while allowing the homepage/menu to merge the
schedules at runtime.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "game_config.json"
LOCALIZATION_PATH = ROOT / "localization" / "dragon_city_localization_baseline_en.json"
OUTPUT_PATH = ROOT / "passes.json"

DRAGON_THUMB_BASE = "https://dci-static-s1.socialpointgames.com/static/dragoncity/mobile/ui/dragons/HD/"
RARITY_ORDER = {"H": 0, "M": 1, "L": 2, "E": 3, "V": 4, "R": 5, "C": 6}
PATH_ORDER = {"platinum": 0, "golden": 1, "gold": 1, "free": 2}


def load_json(path: Path) -> Any:
    if not path.exists():
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


def parse_time(value: Any) -> int:
    if isinstance(value, (int, float)):
        return int(value)
    text = str(value or "").strip()
    if not text:
        return 0
    if text.isdigit():
        return int(text)
    # Dragon City config timestamps in these pass sections are UTC strings.
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S"):
        try:
            return int(datetime.strptime(text, fmt).replace(tzinfo=timezone.utc).timestamp())
        except ValueError:
            pass
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return int(dt.timestamp())
    except ValueError:
        return 0


def availability_window(value: Any) -> Tuple[int, int]:
    rows = value if isinstance(value, list) else [value]
    starts: List[int] = []
    ends: List[int] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        start = parse_time(row.get("from"))
        end = parse_time(row.get("to"))
        if start > 0:
            starts.append(start)
        if end > start:
            ends.append(end)
    if not starts or not ends:
        return 0, 0
    return min(starts), max(ends)


def iso(ts: int) -> str:
    return datetime.fromtimestamp(ts, timezone.utc).isoformat().replace("+00:00", "Z")


def item_index(config: Dict[str, Any]) -> Dict[int, Dict[str, Any]]:
    return {
        as_int(row.get("id")): row
        for row in config.get("items", [])
        if isinstance(row, dict) and as_int(row.get("id")) > 0
    }


def extract_egg_ids(value: Any) -> List[int]:
    out: List[int] = []

    def visit(node: Any) -> None:
        if isinstance(node, dict):
            for key, val in node.items():
                if key == "egg":
                    if isinstance(val, list):
                        out.extend(as_int(x) for x in val if as_int(x) > 0)
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


def dragon_record(
    dragon_id: int,
    items: Dict[int, Dict[str, Any]],
    localization: Dict[str, str],
    *,
    path: str = "",
) -> Optional[Dict[str, Any]]:
    item = items.get(dragon_id, {})
    if not item or str(item.get("group_type") or "").upper() != "DRAGON":
        return None
    img_name = str(item.get("img_name_mobile") or item.get("img_name") or "").strip()
    record: Dict[str, Any] = {
        "id": dragon_id,
        "name": loc_text(localization, f"tid_unit_{dragon_id}_name", str(item.get("name") or f"Dragon {dragon_id}")),
        "rarity": str(item.get("dragon_rarity") or "").upper(),
        "img_name": img_name,
        "thumbnail": f"{DRAGON_THUMB_BASE}thumb_{img_name}_3.png" if img_name else "",
    }
    if path:
        record["path"] = path
    return record


def sorted_dragons(
    ids: Iterable[int],
    items: Dict[int, Dict[str, Any]],
    localization: Dict[str, str],
    *,
    path: str = "",
) -> List[Dict[str, Any]]:
    seen = set()
    rows: List[Dict[str, Any]] = []
    for raw_id in ids:
        did = as_int(raw_id)
        if did <= 0 or did in seen:
            continue
        seen.add(did)
        record = dragon_record(did, items, localization, path=path)
        if record:
            rows.append(record)
    rows.sort(key=lambda d: RARITY_ORDER.get(str(d.get("rarity") or "").upper(), 99))
    return rows


def slug(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(value or "").lower()).strip("_")


def divine_passes(config: Dict[str, Any], localization: Dict[str, str], items: Dict[int, Dict[str, Any]]) -> List[Dict[str, Any]]:
    section = config.get("battle_pass", {})
    nodes_by_id = {
        as_int(row.get("id")): row for row in section.get("nodes", []) if isinstance(row, dict)
    }
    rewards_by_id = {
        as_int(row.get("id")): row for row in section.get("rewards", []) if isinstance(row, dict)
    }
    out: List[Dict[str, Any]] = []

    for row in section.get("battle_pass", []):
        if not isinstance(row, dict):
            continue
        pass_id = as_int(row.get("id"))
        start_ts, end_ts = availability_window(row.get("availability"))
        if pass_id <= 0 or start_ts <= 0 or end_ts <= start_ts:
            continue

        premium_ids: List[int] = []
        for node_id in row.get("nodes", []) or []:
            node = nodes_by_id.get(as_int(node_id), {})
            reward_id = as_int(node.get("premium_reward"))
            if reward_id:
                premium_ids.extend(extract_egg_ids(rewards_by_id.get(reward_id, {}).get("reward")))
        featured = sorted_dragons(premium_ids, items, localization, path="premium")

        localized_title = loc_text(localization, row.get("name_tid"), "Divine Pass")
        localized_season = loc_text(localization, row.get("season_tid"), "")
        out.append({
            "key": f"divine_pass:{pass_id}",
            "id": pass_id,
            "type": "divine_pass",
            "variant": "divine_pass",
            "type_label": "Divine Pass",
            "title": localized_title,
            "subtitle": localized_season,
            "start_ts": start_ts,
            "end_ts": end_ts,
            "start_iso": iso(start_ts),
            "end_iso": iso(end_ts),
            "details": "/p/divine-pass.html",
            "source_section": "battle_pass.battle_pass",
            "featured_dragons": featured,
            "featured_dragon_count": len(featured),
        })
    return out


def progression_passes(config: Dict[str, Any], localization: Dict[str, str], items: Dict[int, Dict[str, Any]]) -> List[Dict[str, Any]]:
    pm = config.get("progression_milestones", {})
    unlock_rows = config.get("unlock_system", {}).get("unlocks", [])
    unlock_by_id = {
        str(row.get("id")): row for row in unlock_rows if isinstance(row, dict) and row.get("id") is not None
    }
    view_by_id = {
        as_int(row.get("id")): row for row in pm.get("view_templates_ui", []) if isinstance(row, dict)
    }
    progression_by_id = {
        as_int(row.get("id")): row for row in pm.get("ps_progressions", []) if isinstance(row, dict)
    }
    route_by_id = {
        as_int(row.get("id")): row for row in pm.get("ps_routes", []) if isinstance(row, dict)
    }
    path_by_id = {
        as_int(row.get("id")): row for row in pm.get("ps_paths", []) if isinstance(row, dict)
    }
    goal_by_id = {
        as_int(row.get("id")): row for row in pm.get("goals", []) if isinstance(row, dict)
    }
    reward_by_id = {
        as_int(row.get("id")): row for row in pm.get("rewards", []) if isinstance(row, dict)
    }

    out: List[Dict[str, Any]] = []
    for row in pm.get("progression_milestones", []):
        if not isinstance(row, dict) or not row.get("enabled", 1):
            continue
        pass_id = as_int(row.get("id"))
        unlock_id = str(row.get("unlock_system_availability") or "")
        unlock = unlock_by_id.get(unlock_id, {})
        start_ts, end_ts = availability_window(unlock.get("availability"))
        if pass_id <= 0 or start_ts <= 0 or end_ts <= start_ts:
            continue

        view = view_by_id.get(as_int(row.get("view_templates_ui_id")), {})
        title = loc_text(localization, view.get("title_tid"), str(row.get("analytics_tag") or "Progression Pass"))
        variant = slug(row.get("analytics_tag") or title or "progression_pass")

        progression = progression_by_id.get(as_int(row.get("ps_progression_id")), {})
        paths: List[Tuple[int, int, Dict[str, Any]]] = []
        seq = 0
        for route_id in progression.get("route_ids", []) or []:
            route = route_by_id.get(as_int(route_id), {})
            for path_id in route.get("path_ids", []) or []:
                path = path_by_id.get(as_int(path_id), {})
                path_name = str(path.get("name_tid") or "").strip().lower()
                paths.append((PATH_ORDER.get(path_name, 99), seq, path))
                seq += 1
        paths.sort(key=lambda x: (x[0], x[1]))

        featured: List[Dict[str, Any]] = []
        seen_dragons = set()
        for _, _, path in paths:
            path_name = str(path.get("name_tid") or "").strip().lower() or "unknown"
            ids: List[int] = []
            for goal_id in path.get("goal_ids", []) or []:
                goal = goal_by_id.get(as_int(goal_id), {})
                reward_id = as_int(goal.get("reward"))
                if reward_id:
                    ids.extend(extract_egg_ids(reward_by_id.get(reward_id, {}).get("reward")))
            for dragon in sorted_dragons(ids, items, localization, path=path_name):
                if dragon["id"] in seen_dragons:
                    continue
                seen_dragons.add(dragon["id"])
                featured.append(dragon)

        pass_record: Dict[str, Any] = {
            "key": f"progression_pass:{pass_id}",
            "id": pass_id,
            "type": "progression_pass",
            "variant": variant,
            "type_label": "Progression Pass",
            # Progression cards intentionally display the concrete pass name directly.
            "title": title,
            "subtitle": "",
            "start_ts": start_ts,
            "end_ts": end_ts,
            "start_iso": iso(start_ts),
            "end_iso": iso(end_ts),
            "details": "/p/progression-pass.html",
            "source_section": "progression_milestones.progression_milestones",
            "unlock_system_availability": unlock_id,
            "featured_dragons": featured,
            "featured_dragon_count": len(featured),
        }
        if row.get("player_segment_ids"):
            pass_record["player_segment_ids"] = [as_int(x) for x in row.get("player_segment_ids", []) if as_int(x) > 0]
        if row.get("player_segmentation_type"):
            pass_record["player_segmentation_type"] = str(row.get("player_segmentation_type"))
        out.append(pass_record)

    return out


def main() -> None:
    config = load_json(CONFIG_PATH)
    localization = normalize_localization(load_json(LOCALIZATION_PATH))
    items = item_index(config)

    passes = divine_passes(config, localization, items) + progression_passes(config, localization, items)
    dedup: Dict[str, Dict[str, Any]] = {row["key"]: row for row in passes}
    passes = sorted(dedup.values(), key=lambda p: (p["start_ts"], p["end_ts"], p["key"]))

    payload = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "source_file": CONFIG_PATH.name,
        "pass_count": len(passes),
        "passes": passes,
    }
    with OUTPUT_PATH.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(f"Wrote {OUTPUT_PATH.name}: {len(passes)} passes")


if __name__ == "__main__":
    main()
