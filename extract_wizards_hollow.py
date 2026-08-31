#!/usr/bin/env python3
"""Build compact Wizards' Hollow homepage/page data for Dragon City Information Center.

Inputs (repository root by default):
  side_events_config.json
  game_config.json                         # optional fallback lookup; kept build-time only
  localization/dragon_city_localization_baseline_en.json
  dragons.json                             # optional, preferred dragon names/art
  skins.json                               # optional, preferred skin names/art
  chests.json                              # optional, preferred chest names/art

Output:
  wizards_hollow.json

The frontend should fetch only wizards_hollow.json. Large source configs are never
needed by the browser.
"""
from __future__ import annotations

import argparse
import json
import math
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

ROOT = Path(__file__).resolve().parent
ASSET_RAW = "https://raw.githubusercontent.com/chaerulanwarreborn-star/dcic-assets/main/"
ICON_RAW = ASSET_RAW + "icons/"
WIZARD_ASSET_RAW = ICON_RAW + "wizards-cave/"
STATIC_DC = "https://dci-static-s1.socialpointgames.com/static/dragoncity/"


def load_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        if default is not None:
            return default
        raise SystemExit(f"Missing required file: {path}")
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def norm_loc(raw: Any) -> Dict[str, str]:
    if isinstance(raw, dict):
        return {str(k): str(v) for k, v in raw.items() if v is not None}
    out: Dict[str, str] = {}
    if isinstance(raw, list):
        for row in raw:
            if isinstance(row, dict):
                for k, v in row.items():
                    if v is not None:
                        out[str(k)] = str(v)
    return out


def loc(table: Mapping[str, str], key: Any, fallback: str = "") -> str:
    value = str(table.get(str(key or ""), "") or "").strip()
    return value or fallback


def as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def list_rows(value: Any) -> List[Dict[str, Any]]:
    return [x for x in value if isinstance(x, dict)] if isinstance(value, list) else []


def by_id(rows: Iterable[Mapping[str, Any]]) -> Dict[int, Mapping[str, Any]]:
    result: Dict[int, Mapping[str, Any]] = {}
    for row in rows:
        try:
            result[int(row.get("id"))] = row
        except (TypeError, ValueError):
            pass
    return result


def parse_duration(value: Any) -> int:
    """Parse compact DC duration strings such as 70h, 153d, 3672h."""
    if isinstance(value, (int, float)):
        return int(value)
    s = str(value or "").strip().lower()
    if not s:
        return 0
    total = 0.0
    for number, unit in re.findall(r"([0-9]+(?:\.[0-9]+)?)\s*([smhdw])", s):
        n = float(number)
        total += n * {"s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800}[unit]
    if total:
        return int(total)
    try:
        return int(float(s))
    except ValueError:
        return 0


def parse_game_time(value: Any) -> Optional[int]:
    """Dragon City config timestamps are treated as UTC, matching other DCIC extractors."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return int(value)
    s = str(value).strip()
    if not s or s == "0":
        return None
    if s.isdigit():
        return int(s)
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return int(datetime.strptime(s, fmt).replace(tzinfo=timezone.utc).timestamp())
        except ValueError:
            pass
    return None


def unwrap_wizards(raw: Any) -> Dict[str, Any]:
    if not isinstance(raw, dict):
        return {}
    w = raw.get("wizards_cave")
    if isinstance(w, dict):
        c = w.get("config")
        return c if isinstance(c, dict) else w
    c = raw.get("config")
    if isinstance(c, dict) and any(k in c for k in ("cave", "stage", "ui_config")):
        return c
    return raw


def flatten_entities(raw: Any) -> List[Dict[str, Any]]:
    if isinstance(raw, list):
        return [x for x in raw if isinstance(x, dict)]
    if not isinstance(raw, dict):
        return []
    for key in ("dragons", "skins", "chests", "items", "data", "rows"):
        if isinstance(raw.get(key), list):
            return [x for x in raw[key] if isinstance(x, dict)]
    return []


def index_entities(raw: Any, *, type_key: Optional[str] = None) -> Dict[Any, Dict[str, Any]]:
    out: Dict[Any, Dict[str, Any]] = {}
    for row in flatten_entities(raw):
        rid = row.get("id")
        if rid is None:
            continue
        if type_key:
            out[(str(row.get(type_key) or ""), str(rid))] = row
        out[str(rid)] = row
    return out


def unique_strings(values: Iterable[Any]) -> List[str]:
    seen = set()
    out: List[str] = []
    for v in values:
        s = str(v or "").strip()
        if not s or s in seen:
            continue
        seen.add(s)
        out.append(s)
    return out


def image_values(obj: Any, depth: int = 0) -> List[str]:
    """Harvest already-resolved image URLs/files from compact DB rows without assuming one schema."""
    if depth > 4:
        return []
    out: List[str] = []
    if isinstance(obj, str):
        s = obj.strip()
        if s.lower().endswith((".png", ".webp", ".jpg", ".jpeg")) or s.startswith("http"):
            out.append(s)
    elif isinstance(obj, list):
        for x in obj:
            out.extend(image_values(x, depth + 1))
    elif isinstance(obj, dict):
        priority = (
            "full_body", "fullbody", "full_image", "image", "image_url", "image_candidates",
            "art", "artwork", "icon", "icon_url", "thumbnail", "thumb", "img_name_mobile",
            "remote", "asset", "filename"
        )
        keys = list(obj.keys())
        keys.sort(key=lambda k: (priority.index(k) if k in priority else len(priority), str(k)))
        for k in keys:
            if k in priority or any(token in str(k).lower() for token in ("image", "icon", "thumb", "asset", "art", "img")):
                out.extend(image_values(obj.get(k), depth + 1))
    return unique_strings(out)


def normalize_image_candidate(value: str, *, dragon: bool = False) -> Optional[str]:
    s = str(value or "").strip().replace("\\", "/")
    if not s:
        return None
    if s.startswith("http://") or s.startswith("https://"):
        return s
    if s.startswith("mobile/"):
        return STATIC_DC + s
    if "/mobile/" in s:
        return STATIC_DC + s.split("/mobile/", 1)[1].join(["mobile/", ""])
    name = s.rsplit("/", 1)[-1]
    if dragon and name.startswith("ui_"):
        return STATIC_DC + "mobile/ui/dragons/" + name
    if name.lower().endswith((".png", ".webp", ".jpg", ".jpeg")):
        return ICON_RAW + name
    return None


def compact_entity(row: Optional[Mapping[str, Any]], rid: Any, fallback_name: str = "") -> Dict[str, Any]:
    row = dict(row or {})
    name = str(row.get("name") or row.get("title") or row.get("display_name") or fallback_name or "").strip()
    result: Dict[str, Any] = {"id": as_int(rid, as_int(row.get("id"), 0))}
    if name:
        result["name"] = name
    imgs = []
    for raw in image_values(row):
        n = normalize_image_candidate(raw, dragon=True)
        if n:
            imgs.append(n)
    imgs = unique_strings(imgs)
    if imgs:
        result["image_candidates"] = imgs[:8]
    for k in ("img_name_mobile", "rarity", "type", "asset", "filename"):
        if row.get(k) not in (None, ""):
            result[k] = row[k]
    return result


def dragon_full_body_candidates(row: Optional[Mapping[str, Any]]) -> List[str]:
    """Build canonical full-body Dragon City artwork URLs, never HD thumbnail crops."""
    row = dict(row or {})
    raw = str(row.get("img_name_mobile") or row.get("img_name") or "").strip().replace("\\", "/")
    raw = raw.rsplit("/", 1)[-1]
    raw = re.sub(r"\.png$", "", raw, flags=re.I)
    raw = re.sub(r"@2x$", "", raw, flags=re.I)
    raw = re.sub(r"^ui_", "", raw, flags=re.I)
    raw = re.sub(r"_3$", "", raw, flags=re.I)

    # If compact DB only exposed a thumb URL, recover the dragon asset slug from it.
    if not raw:
        for candidate in image_values(row):
            m = re.search(r"/HD/thumb_(.+?)_3(?:@2x)?\.png(?:\?.*)?$", str(candidate), flags=re.I)
            if m:
                raw = m.group(1)
                break
            m = re.search(r"/ui/(?:dragons/)?ui_(.+?)_3(?:@2x)?\.png(?:\?.*)?$", str(candidate), flags=re.I)
            if m:
                raw = m.group(1)
                break
    if not raw:
        return []
    base = STATIC_DC + "mobile/ui/dragons/"
    return [base + "ui_" + raw + "_3@2x.png", base + "ui_" + raw + "_3.png"]


def search_dragon_in_game_config(raw: Any, dragon_id: int) -> Optional[Dict[str, Any]]:
    """Best-effort fallback; bounded recursive traversal to avoid depending on one main-config schema."""
    if not isinstance(raw, dict):
        return None
    likely_keys = ("dragons", "dragon", "dragon_data", "dragon_templates")
    for key in likely_keys:
        rows = raw.get(key)
        if isinstance(rows, list):
            for row in rows:
                if isinstance(row, dict) and as_int(row.get("id"), -1) == dragon_id:
                    return row
    # Known configs often nest feature sections. Limit to 3 levels and only scan lists whose rows look dragon-ish.
    frontier: List[Tuple[Any, int]] = [(raw, 0)]
    while frontier:
        node, depth = frontier.pop()
        if depth > 3:
            continue
        if isinstance(node, dict):
            for k, v in node.items():
                kl = str(k).lower()
                if isinstance(v, list) and "dragon" in kl:
                    for row in v:
                        if isinstance(row, dict) and as_int(row.get("id"), -1) == dragon_id:
                            return row
                elif isinstance(v, dict) and depth < 3:
                    frontier.append((v, depth + 1))
    return None


def reward_payload(row: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
    if not row:
        return {}
    r = row.get("reward")
    if isinstance(r, list) and r:
        return r[0] if isinstance(r[0], dict) else {}
    return r if isinstance(r, dict) else {}


def normalize_reward(
    reward_id: Any,
    reward_by_id: Mapping[int, Mapping[str, Any]],
    dragons: Mapping[Any, Dict[str, Any]],
    skins: Mapping[Any, Dict[str, Any]],
    chests: Mapping[Any, Dict[str, Any]],
    game_config: Any,
) -> Optional[Dict[str, Any]]:
    rid = as_int(reward_id, -1)
    row = reward_by_id.get(rid)
    if not row:
        return None
    payload = reward_payload(row)
    if not payload:
        return {"reward_id": rid, "type": "unknown", "raw": row.get("reward")}

    def dragon_result(did: int) -> Dict[str, Any]:
        drow = dragons.get(str(did))
        if not drow:
            drow = search_dragon_in_game_config(game_config, did)
        ent = compact_entity(drow, did, f"Dragon #{did}")
        full_body = dragon_full_body_candidates(drow)
        if full_body:
            ent["full_body_image"] = full_body[0]
            ent["image_candidates"] = unique_strings(full_body + list(ent.get("image_candidates") or []))[:10]
        ent.update({"reward_id": rid, "type": "dragon", "popup": {"kind": "dragon", "id": did}})
        return ent

    if "egg" in payload:
        return dragon_result(as_int(payload.get("egg")))
    if "dragon" in payload:
        return dragon_result(as_int(payload.get("dragon")))
    if "skin" in payload:
        sid = as_int(payload.get("skin"))
        ent = compact_entity(skins.get(str(sid)), sid, f"Skin #{sid}")
        ent.update({"reward_id": rid, "type": "skin", "popup": {"kind": "skin", "id": sid}})
        return ent
    if "chest" in payload:
        cid = as_int(payload.get("chest"))
        crow = chests.get(("generic", str(cid))) or chests.get(str(cid))
        ent = compact_entity(crow, cid, f"Chest #{cid}")
        ctype = str((crow or {}).get("type") or "generic")
        ent.update({"reward_id": rid, "type": "chest", "chest_type": ctype, "popup": {"kind": "chest", "id": cid, "type": ctype}})
        return ent

    # Single-key currencies/resources and structured resources.
    key, value = next(iter(payload.items()))
    if key in ("seeds", "rarity_seeds", "trade_tickets", "perks"):
        return {"reward_id": rid, "type": key, "value": value, "name": key.replace("_", " ").title()}

    resource_names = {
        "c": "Gems", "g": "Gold", "f": "Food", "keys": "Rescue Keys",
        "silver_rune": "Stone Rune", "golden_rune": "Amber Rune",
    }
    return {
        "reward_id": rid,
        "type": "resource",
        "resource": str(key),
        "amount": value,
        "name": resource_names.get(str(key), str(key).replace("_", " ").title()),
    }


def pool_reward_id(config: Mapping[str, Any], pool_id: int) -> Optional[int]:
    # Wizards' Hollow has historically used reward_pool / reward_pools / pool / rewards_weights-like tables.
    candidates: List[Dict[str, Any]] = []
    for key in ("reward_pool", "reward_pools", "reward_pool_items", "pools", "pool"):
        candidates.extend(list_rows(config.get(key)))
    # Heuristic discovery of any direct table carrying pool_id + reward_id.
    for key, value in config.items():
        if key in ("rewards", "stage", "cave", "ui_config"):
            continue
        rows = list_rows(value)
        if rows and any("pool_id" in x and "reward_id" in x for x in rows[:10]):
            candidates.extend(rows)
    matches = [x for x in candidates if as_int(x.get("pool_id"), -1) == pool_id and x.get("reward_id") is not None]
    if not matches:
        return None
    # Final pools are deterministic in captured config (weight 1), but choosing the first is also safe for display.
    matches.sort(key=lambda x: as_int(x.get("id"), 10**9))
    return as_int(matches[0].get("reward_id"), -1)


def find_goal_rows(config: Mapping[str, Any]) -> List[Dict[str, Any]]:
    for key in ("goal", "goals"):
        if isinstance(config.get(key), list):
            return list_rows(config.get(key))
    return []


def goal_collectible_ids(goal: Mapping[str, Any]) -> List[int]:
    for key in ("collectibles", "collectible_ids", "actions", "action_ids"):
        v = goal.get(key)
        if isinstance(v, list):
            return [as_int(x, -1) for x in v if as_int(x, -1) >= 0]
    for key in ("collectible", "collectible_id", "action", "action_id"):
        if goal.get(key) is not None:
            return [as_int(goal.get(key), -1)]
    return []


def goal_reward_id(goal: Mapping[str, Any]) -> Optional[int]:
    for key in ("rewards", "reward_id", "reward"):
        v = goal.get(key)
        if isinstance(v, (int, float, str)) and str(v).lstrip("-").isdigit():
            return as_int(v, -1)
        if isinstance(v, list) and v and isinstance(v[0], (int, float, str)):
            return as_int(v[0], -1)
    return None


def resolve_rune_goal(
    config: Mapping[str, Any], goal_id: Any, ui_reward_id: Any,
    reward_by_id: Mapping[int, Mapping[str, Any]], dragons: Mapping[Any, Dict[str, Any]],
    skins: Mapping[Any, Dict[str, Any]], chests: Mapping[Any, Dict[str, Any]], game_config: Any,
) -> Dict[str, Any]:
    gid = as_int(goal_id, -1)
    goals = by_id(find_goal_rows(config))
    actions = by_id(list_rows(config.get("collectible_actions")))
    goal = goals.get(gid, {})
    required: Optional[int] = None
    action_type = ""
    for aid in goal_collectible_ids(goal):
        action = actions.get(aid)
        if not action:
            continue
        amount = as_int(action.get("amount"), 0)
        if amount > 0 and (required is None or amount > required):
            required = amount
        if action.get("type"):
            action_type = str(action.get("type"))
    # Some config generations put the amount directly on the goal.
    if required is None:
        for key in ("required_amount", "amount", "target", "quantity"):
            n = as_int(goal.get(key), 0)
            if n > 0:
                required = n
                break
    # ui_config reward ids are the display rewards used by the official Hollow news/start UI.
    # Prefer them, but keep goal reward as a documented fallback.
    display_reward_id = as_int(ui_reward_id, -1)
    if display_reward_id < 0:
        gr = goal_reward_id(goal)
        display_reward_id = gr if gr is not None else -1
    reward = normalize_reward(display_reward_id, reward_by_id, dragons, skins, chests, game_config) if display_reward_id >= 0 else None
    return {
        "goal_id": gid if gid >= 0 else None,
        "required": required,
        "action_type": action_type or None,
        "reward": reward,
    }


def occurrence_windows(cave: Mapping[str, Any], now: int, horizon_end: int, history_days: int = 7) -> List[Tuple[int, int]]:
    out: List[Tuple[int, int]] = []
    min_start = now - history_days * 86400
    for av in list_rows(cave.get("availability")):
        start0 = parse_game_time(av.get("from"))
        if start0 is None:
            continue
        dur = parse_duration(av.get("dur"))
        to = parse_game_time(av.get("to"))
        if dur <= 0 and to is not None:
            dur = max(0, to - start0)
        if dur <= 0:
            continue
        cycle = parse_duration(av.get("cycle"))
        if cycle <= 0:
            end = start0 + dur
            if end >= min_start and start0 <= horizon_end:
                out.append((start0, end))
            continue
        # Jump close to the requested window instead of iterating from 2023 one cycle at a time.
        k = math.floor((min_start - start0) / cycle)
        k = max(0, k)
        while start0 + k * cycle + dur < min_start:
            k += 1
        while True:
            start = start0 + k * cycle
            if start > horizon_end:
                break
            end = start + dur
            if end >= min_start:
                out.append((start, end))
            k += 1
    return out


def build(args: argparse.Namespace) -> Dict[str, Any]:
    side_raw = load_json(Path(args.side_events))
    config = unwrap_wizards(side_raw)
    if not config:
        raise SystemExit("wizards_cave config not found in side_events_config.json")

    game_config = load_json(Path(args.game_config), {}) if args.game_config else {}
    localization = norm_loc(load_json(Path(args.localization), {}))
    dragons = index_entities(load_json(Path(args.dragons), {})) if args.dragons else {}
    skins = index_entities(load_json(Path(args.skins), {})) if args.skins else {}
    chests = index_entities(load_json(Path(args.chests), {}), type_key="type") if args.chests else {}

    caves = list_rows(config.get("cave"))
    stages = by_id(list_rows(config.get("stage")))
    uis = by_id(list_rows(config.get("ui_config")))
    rewards = by_id(list_rows(config.get("rewards")))

    now = int(args.now if args.now is not None else time.time())
    horizon_end = now + int(args.future_days) * 86400
    occurrences: List[Dict[str, Any]] = []

    for cave in caves:
        cid = as_int(cave.get("id"), -1)
        ui = uis.get(as_int(cave.get("ui_config_id"), cid), {})
        title_tid = ui.get("title") or ui.get("title_tid") or "tid_wizardshollow_gameplay_screen_title"
        subtitle_tid = ui.get("subtitle") or ui.get("subtitle_tid")
        name = loc(localization, subtitle_tid, str(subtitle_tid or f"Wizards' Hollow #{cid}"))
        title = loc(localization, title_tid, "WIZARDS' HOLLOW")

        stage_ids = cave.get("stage_ids") if isinstance(cave.get("stage_ids"), list) else []
        final_stage_id = as_int(stage_ids[-1], -1) if stage_ids else -1
        final_stage = stages.get(final_stage_id, {})
        main_reward_id: Optional[int] = None
        if final_stage:
            main_reward_id = pool_reward_id(config, as_int(final_stage.get("pool_id"), final_stage_id))
        main_reward = normalize_reward(main_reward_id, rewards, dragons, skins, chests, game_config) if main_reward_id is not None else None

        goal_ids = cave.get("goal_ids") if isinstance(cave.get("goal_ids"), list) else []
        silver_goal_id = goal_ids[0] if len(goal_ids) >= 1 else None
        golden_goal_id = goal_ids[1] if len(goal_ids) >= 2 else None
        silver = resolve_rune_goal(config, silver_goal_id, ui.get("left_reward_id_popup"), rewards, dragons, skins, chests, game_config)
        golden = resolve_rune_goal(config, golden_goal_id, ui.get("right_reward_id_popup"), rewards, dragons, skins, chests, game_config)

        for start, end in occurrence_windows(cave, now, horizon_end, args.history_days):
            occurrences.append({
                "cave_id": cid,
                "ui_config_id": as_int(cave.get("ui_config_id"), cid),
                "title": title,
                "name": name,
                "subtitle_tid": subtitle_tid,
                "start_ts": start,
                "end_ts": end,
                "duration_seconds": end - start,
                "final_stage_id": final_stage_id if final_stage_id >= 0 else None,
                "main_reward": main_reward,
                "rune_rewards": {"silver": silver, "golden": golden},
            })

    occurrences.sort(key=lambda x: (as_int(x.get("start_ts")), as_int(x.get("cave_id"))))
    # Build enough for current + five future cards, but keep a wider window for the full page/archive.
    current = next((x for x in occurrences if as_int(x.get("start_ts")) <= now < as_int(x.get("end_ts"))), None)
    future = [x for x in occurrences if as_int(x.get("end_ts")) > now]
    current_id = current.get("cave_id") if current else None
    next_obj = next((x for x in future if as_int(x.get("start_ts")) > now), None)

    payload = {
        "generated_at": int(time.time()),
        "meta": {
            "source": "side_events_config.json:wizards_cave",
            "future_days": int(args.future_days),
            "occurrence_count": len(occurrences),
            "current_cave_id": current_id,
            "next_cave_id": next_obj.get("cave_id") if next_obj else None,
            "frontend_max_cards": 5,
            "game_config_role": "build-time fallback only",
        },
        "labels": {
            "title": loc(localization, "tid_wizardshollow_gameplay_screen_title", "WIZARDS' HOLLOW"),
            "silver_rune": loc(localization, "tid_silver_rune_resource", "Stone Rune"),
            "golden_rune": loc(localization, "tid_golden_rune_resource", "Amber Rune"),
            "unavailable": loc(localization, "tid_teaser_wizards_hollow", "The entrance to the Hollow will open soon..."),
        },
        "assets": {
            "wizard_popup": WIZARD_ASSET_RAW + "wizard-popup.png",
            "wizard_unavailable": WIZARD_ASSET_RAW + "wizard-unavailable.png",
            "silver_rune": WIZARD_ASSET_RAW + "ic-rune-silver-massive.png",
            "golden_rune": WIZARD_ASSET_RAW + "ic-rune-gold-massive.png",
        },
        "hollows": occurrences,
    }
    Path(args.output).write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return payload


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--side-events", default="side_events_config.json")
    ap.add_argument("--game-config", default="game_config.json")
    ap.add_argument("--localization", default="localization/dragon_city_localization_baseline_en.json")
    ap.add_argument("--dragons", default="dragons.json")
    ap.add_argument("--skins", default="skins.json")
    ap.add_argument("--chests", default="chests.json")
    ap.add_argument("--output", default="wizards_hollow.json")
    ap.add_argument("--future-days", type=int, default=370)
    ap.add_argument("--history-days", type=int, default=7)
    ap.add_argument("--now", type=int, default=None)
    args = ap.parse_args()
    payload = build(args)
    print(f"Wrote {args.output}: {len(payload['hollows'])} Hollow occurrences")


if __name__ == "__main__":
    main()
