#!/usr/bin/env python3
"""Build compact Event Collection data for Dragon City Information Center.

Source: game_config.json -> liveops_challenges
Output: event_collections.json

The extractor intentionally keeps the live config IDs and colors intact, while
normalizing rewards into a frontend-friendly shape. dragons.json and chests.json
are optional enrichments; the output still works without them.
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

ASSET_ICON_BASE = "https://raw.githubusercontent.com/chaerulanwarreborn-star/dcic-assets/main/icons/"
DRAGON_ASSET_BASE = "https://dci-static-s1.socialpointgames.com/static/dragoncity/mobile/ui/dragons/"

RARITY_NAMES = {
    "C": "Common",
    "R": "Rare",
    "V": "Very Rare",
    "VR": "Very Rare",
    "E": "Epic",
    "L": "Legendary",
    "M": "Mythical",
    "H": "Heroic",
}

RESOURCE_META = {
    "c": ("gems", "Gems", ASSET_ICON_BASE + "resources/ic-gem.png"),
    "f": ("food", "Food", ASSET_ICON_BASE + "resources/ic-food.png"),
    "g": ("gold", "Gold", ASSET_ICON_BASE + "resources/ic-gold.png"),
    "xp": ("xp", "XP", ASSET_ICON_BASE + "resources/ic-experience-xp.png"),
    "experience": ("xp", "XP", ASSET_ICON_BASE + "resources/ic-experience-xp.png"),
    "keys": ("keys", "Keys", ASSET_ICON_BASE + "text-icons/ic-key-massive.png"),
    "puzzle_move": ("puzzle_move", "Puzzle Moves", ASSET_ICON_BASE + "currency-icon/coin-puzzle.png"),
}

DURATION_RE = re.compile(r"(?P<value>\d+(?:\.\d+)?)(?P<unit>[dhms])", re.I)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Extract Dragon City Event Collections")
    p.add_argument("--game-config", default="game_config.json")
    p.add_argument("--localization", default="localization/dragon_city_localization_baseline_en.json")
    p.add_argument("--dragons", default="dragons.json")
    p.add_argument("--chests", default="chests.json")
    p.add_argument("--output", default="event_collections.json")
    return p.parse_args()


def load_json(path: Path, required: bool = True) -> Any:
    if not path.exists():
        if required:
            raise FileNotFoundError(path)
        return None
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def flatten_localization(data: Any) -> Dict[str, str]:
    """Supports either one dictionary or the list-of-single-dictionaries format."""
    out: Dict[str, str] = {}
    if isinstance(data, dict):
        for k, v in data.items():
            if isinstance(v, (str, int, float)):
                out[str(k)] = str(v)
        return out
    if isinstance(data, list):
        for row in data:
            if not isinstance(row, dict):
                continue
            for k, v in row.items():
                if isinstance(v, (str, int, float)):
                    out[str(k)] = str(v)
    return out


def loc_text(loc: Dict[str, str], value: Any, fallback: str = "") -> str:
    if value is None:
        return fallback
    s = str(value)
    if s in loc:
        return loc[s]
    # Some old configs store literal display text in *_tid fields.
    if not s.lower().startswith("tid_"):
        return s
    return fallback or humanize_tid(s)


def humanize_tid(value: str) -> str:
    s = re.sub(r"^tid_(?:lo_)?challenges_(?:title_|collect_)?", "", value, flags=re.I)
    s = re.sub(r"^tid_", "", s, flags=re.I)
    s = re.sub(r"_MS\d+$", "", s, flags=re.I)
    s = s.replace("_", " ")
    # Split a few common camel-case leftovers only when possible.
    s = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s.title() if s else value


def parse_config_datetime(value: Any) -> int:
    """Dragon City liveops strings are UTC, even though they have no suffix."""
    if value in (None, ""):
        return 0
    if isinstance(value, (int, float)):
        return int(value)
    s = str(value).strip()
    if not s:
        return 0
    if s.isdigit():
        return int(s)
    s = s.replace("Z", "+00:00")
    dt: Optional[datetime] = None
    for fmt in (None, "%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S"):
        try:
            dt = datetime.fromisoformat(s) if fmt is None else datetime.strptime(s, fmt)
            break
        except ValueError:
            continue
    if dt is None:
        raise ValueError(f"Unsupported liveops datetime: {value!r}")
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return int(dt.timestamp())


def parse_duration(value: Any) -> int:
    if value in (None, ""):
        return 0
    if isinstance(value, (int, float)):
        return int(value)
    s = str(value).strip().lower()
    if s.isdigit():
        return int(s)
    total = 0.0
    found = False
    unit_seconds = {"d": 86400, "h": 3600, "m": 60, "s": 1}
    for m in DURATION_RE.finditer(s):
        found = True
        total += float(m.group("value")) * unit_seconds[m.group("unit").lower()]
    if not found:
        raise ValueError(f"Unsupported duration: {value!r}")
    return int(round(total))


def availability_windows(challenge: Dict[str, Any]) -> List[Dict[str, int]]:
    out: List[Dict[str, int]] = []
    raw = challenge.get("availability") or []
    if isinstance(raw, dict):
        raw = [raw]
    for row in raw:
        if not isinstance(row, dict):
            continue
        start = parse_config_datetime(row.get("from"))
        end = parse_config_datetime(row.get("to")) if row.get("to") not in (None, "") else 0
        if not end and start:
            end = start + parse_duration(row.get("dur"))
        if start > 0 and end > start:
            out.append({"start_ts": start, "end_ts": end})
    out.sort(key=lambda x: (x["start_ts"], x["end_ts"]))
    return out


def first_number(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def unique_strings(values: Iterable[Any]) -> List[str]:
    out: List[str] = []
    seen = set()
    for value in values:
        if not value:
            continue
        s = str(value)
        if s not in seen:
            seen.add(s)
            out.append(s)
    return out


def build_dragon_index(payload: Any) -> Dict[int, Dict[str, Any]]:
    rows = payload.get("dragons", []) if isinstance(payload, dict) else []
    out: Dict[int, Dict[str, Any]] = {}
    for row in rows:
        if isinstance(row, dict) and first_number(row.get("id")):
            out[first_number(row.get("id"))] = row
    return out


def build_chest_index(payload: Any) -> Dict[int, Dict[str, Any]]:
    rows = payload.get("chests", []) if isinstance(payload, dict) else []
    grouped: Dict[int, List[Dict[str, Any]]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        cid = first_number(row.get("id"))
        if cid:
            grouped.setdefault(cid, []).append(row)
    out: Dict[int, Dict[str, Any]] = {}
    for cid, matches in grouped.items():
        out[cid] = next((x for x in matches if str(x.get("type")) == "generic"), matches[0])
    return out


def rarity_token(value: Any) -> Optional[str]:
    rarity = str(value or "").upper()
    return {"C": "c", "R": "r", "V": "vr", "VR": "vr", "E": "e", "L": "l", "M": "m", "H": "h"}.get(rarity)


def dragon_info(dragon_id: int, dragon_by_id: Dict[int, Dict[str, Any]]) -> Dict[str, Any]:
    row = dragon_by_id.get(dragon_id) or {}
    name = row.get("name") or f"Dragon {dragon_id}"
    rarity = str(row.get("rarity") or "").upper() or None
    raw = str(row.get("img_name_mobile") or row.get("img_name") or "").strip()

    detail = row.get("detail") if isinstance(row.get("detail"), dict) else {}
    images = detail.get("images") if isinstance(detail.get("images"), dict) else {}
    if not images and isinstance(row.get("images"), dict):
        images = row.get("images") or {}

    thumb_candidates = unique_strings([
        DRAGON_ASSET_BASE + f"HD/thumb_{raw}_3.png" if raw else None,
        row.get("thumbnail"),
        row.get("thumbnail_image"),
        DRAGON_ASSET_BASE + f"ui_{raw}_3@2x.png" if raw else None,
        DRAGON_ASSET_BASE + f"ui_{raw}_3.png" if raw else None,
        row.get("adult_image"),
        row.get("full_body_image"),
        row.get("image_url"),
    ])

    # Homepage dragon rewards intentionally use the BABY full-body stage (_1),
    # while Dragon Orbs use the framed thumbnail (_3).
    baby_candidates = unique_strings([
        DRAGON_ASSET_BASE + f"ui_{raw}_1@2x.png" if raw else None,
        DRAGON_ASSET_BASE + f"ui_{raw}_1.png" if raw else None,
        images.get("baby") if isinstance(images, dict) else None,
        row.get("baby_image"),
    ])

    token = rarity_token(rarity)
    orb_icon = ASSET_ICON_BASE + f"tree-of-life/ic-seed-{token}-mid-shadow.png" if token else None

    return {
        "dragon_name": name,
        "dragon_rarity": rarity,
        "rarity": rarity,
        "img_name_mobile": row.get("img_name_mobile"),
        "img_name": row.get("img_name"),
        "thumbnail_candidates": thumb_candidates,
        "baby_image_candidates": baby_candidates,
        "dragon_thumbnail": thumb_candidates[0] if thumb_candidates else None,
        "dragon_baby_image": baby_candidates[0] if baby_candidates else None,
        "orb_icon_url": orb_icon,
        # Keep the generic list for older frontend code. Put the thumbnail first
        # so a self-contained Event Collection card renders correctly immediately.
        "image_candidates": thumb_candidates,
    }


def chest_info(chest_id: int, chest_by_id: Dict[int, Dict[str, Any]]) -> Dict[str, Any]:
    row = chest_by_id.get(chest_id) or {}
    candidates = row.get("image_candidates") if isinstance(row.get("image_candidates"), list) else []
    candidates = unique_strings([row.get("image_url"), *candidates])
    name = row.get("name") or row.get("chest_name") or f"Chest {chest_id}"
    return {
        "chest_name": name,
        "chest_type": row.get("type") or "generic",
        "img_name": row.get("img_name"),
        "image_candidates": candidates,
    }


def reward_base(raw_type: str, name: str, amount: Any = None) -> Dict[str, Any]:
    out: Dict[str, Any] = {"type": raw_type, "resource": raw_type, "name": name}
    if amount is not None:
        out["amount"] = amount
    return out


def normalize_reward_object(
    obj: Dict[str, Any],
    dragon_by_id: Dict[int, Dict[str, Any]],
    chest_by_id: Dict[int, Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Normalize one object from liveops_challenges.rewards[].reward."""
    out: List[Dict[str, Any]] = []

    if "egg" in obj:
        did = first_number(obj.get("egg"))
        if did:
            d = dragon_info(did, dragon_by_id)
            item = reward_base("dragon_egg", d["dragon_name"], 1)
            item.update({"dragon_id": did, "asset_kind": "dragon", "popup": {"kind": "dragon", "id": did}})
            item.update(d)
            out.append(item)

    if "seeds" in obj and isinstance(obj.get("seeds"), list):
        for seed in obj.get("seeds") or []:
            if not isinstance(seed, dict):
                continue
            did = first_number(seed.get("id"))
            if not did:
                continue
            d = dragon_info(did, dragon_by_id)
            base_name = str(d["dragon_name"]).removesuffix(" Dragon")
            item = reward_base("dragon_orbs", f"{base_name} Orbs", seed.get("amount"))
            item.update({"dragon_id": did, "asset_kind": "dragon", "popup": {"kind": "dragon", "id": did}})
            item.update(d)
            out.append(item)

    if "chest" in obj:
        cid = first_number(obj.get("chest"))
        if cid:
            c = chest_info(cid, chest_by_id)
            item = reward_base("chest", c["chest_name"], 1)
            item.update({
                "chest_id": cid,
                "source_chest_id": cid,
                "asset_kind": "chest",
                "popup": {"kind": "chest", "id": cid, "type": c["chest_type"]},
            })
            item.update(c)
            out.append(item)

    if "skin" in obj:
        sid = first_number(obj.get("skin"))
        if sid:
            item = reward_base("skin", f"Dragon Skin {sid}", 1)
            item.update({
                "skin_id": sid,
                "popup": {"kind": "skin", "id": sid},
                "image_url": ASSET_ICON_BASE + "text-icons/ic-dragon-skin-badge.png",
            })
            out.append(item)

    if "rarity_seeds" in obj and isinstance(obj.get("rarity_seeds"), list):
        for row in obj.get("rarity_seeds") or []:
            if not isinstance(row, dict):
                continue
            rarity = str(row.get("rarity") or "").upper()
            item = reward_base("joker_orbs", f"{RARITY_NAMES.get(rarity, rarity)} Joker Orbs", row.get("amount"))
            item.update({"rarity": rarity, "image_url": ASSET_ICON_BASE + "tree-of-life/ic-joker-all.png"})
            out.append(item)

    if "perks" in obj and isinstance(obj.get("perks"), list):
        for row in obj.get("perks") or []:
            if not isinstance(row, dict):
                continue
            pid = first_number(row.get("id"))
            item = reward_base("perk", f"Perk {pid}" if pid else "Perk", row.get("quantity", row.get("amount", 1)))
            item.update({"perk_id": pid or None, "image_url": ASSET_ICON_BASE + "perks/ic-combat-perk.png"})
            out.append(item)

    if "trade_tickets" in obj and isinstance(obj.get("trade_tickets"), list):
        for row in obj.get("trade_tickets") or []:
            if not isinstance(row, dict):
                continue
            rarity = str(row.get("rarity") or "").upper()
            item = reward_base("trade_essence", f"{RARITY_NAMES.get(rarity, rarity)} Trade Essences", row.get("amount"))
            item.update({"rarity": rarity, "image_url": ASSET_ICON_BASE + "tree-of-life/ic-trade-orb-mid-generic.png"})
            out.append(item)

    consumed = {"egg", "seeds", "chest", "skin", "rarity_seeds", "perks", "trade_tickets"}
    for key, value in obj.items():
        if key in consumed:
            continue
        if key in RESOURCE_META and isinstance(value, (int, float)):
            typ, label, icon = RESOURCE_META[key]
            item = reward_base(typ, label, value)
            item["image_url"] = icon
            out.append(item)
            continue

        # Preserve otherwise unknown reward resources instead of silently dropping them.
        if isinstance(value, (int, float, str)):
            item = reward_base("raw_resource", str(key).replace("_", " ").title(), value)
            item.update({"raw_key": key, "raw_value": value})
            out.append(item)
        elif isinstance(value, list):
            for index, child in enumerate(value):
                item = reward_base("raw_resource", str(key).replace("_", " ").title())
                item.update({"raw_key": key, "raw_value": child, "raw_index": index})
                out.append(item)
        else:
            item = reward_base("raw_resource", str(key).replace("_", " ").title())
            item.update({"raw_key": key, "raw_value": value})
            out.append(item)

    for item in out:
        item["raw"] = obj
    return out


def normalize_reward_row(
    reward_row: Dict[str, Any],
    dragon_by_id: Dict[int, Dict[str, Any]],
    chest_by_id: Dict[int, Dict[str, Any]],
) -> List[Dict[str, Any]]:
    values = reward_row.get("reward") or []
    if isinstance(values, dict):
        values = [values]
    out: List[Dict[str, Any]] = []
    for obj in values:
        if isinstance(obj, dict):
            out.extend(normalize_reward_object(obj, dragon_by_id, chest_by_id))
    return out


def build_collection(
    challenge: Dict[str, Any],
    goal_by_id: Dict[int, Dict[str, Any]],
    reward_by_id: Dict[int, Dict[str, Any]],
    loc: Dict[str, str],
    dragon_by_id: Dict[int, Dict[str, Any]],
    chest_by_id: Dict[int, Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    cid = first_number(challenge.get("id"))
    if not cid:
        return None
    windows = availability_windows(challenge)
    if not windows:
        return None

    title_tid = challenge.get("title_tid")
    name = loc_text(loc, title_tid, f"Event Collection {cid}")
    milestone_rows: List[Dict[str, Any]] = []

    for position, goal_id_raw in enumerate(challenge.get("goals") or [], start=1):
        goal_id = first_number(goal_id_raw)
        goal = goal_by_id.get(goal_id) or {}
        reward_id = first_number(goal.get("rewards"), goal_id)
        reward_row = reward_by_id.get(reward_id) or {}
        title = loc_text(loc, goal.get("title_tid"), f"Milestone {position}")
        reward_items = normalize_reward_row(reward_row, dragon_by_id, chest_by_id)
        milestone_rows.append({
            "index": position,
            "id": goal_id,
            "title": title,
            "title_tid": goal.get("title_tid"),
            "reward_id": reward_id,
            "claim_limit": goal.get("claim_limit"),
            "collectible_ids": [first_number(x) for x in (goal.get("collectibles") or []) if first_number(x)],
            "rewards": reward_items,
        })

    displayed_id = first_number(challenge.get("displayed_reward"))
    displayed = next(
        (m for m in milestone_rows if m["reward_id"] == displayed_id or m["id"] == displayed_id),
        milestone_rows[-1] if milestone_rows else None,
    )

    return {
        "id": cid,
        "name": name,
        "title_tid": title_tid,
        "availability": windows,
        "start_ts": min(x["start_ts"] for x in windows),
        "end_ts": max(x["end_ts"] for x in windows),
        "goal_ids": [first_number(x) for x in (challenge.get("goals") or []) if first_number(x)],
        "milestone_count": len(milestone_rows),
        "milestones": milestone_rows,
        "displayed_reward_id": displayed_id,
        "displayed_reward": displayed,
        "colors": {
            "title": challenge.get("title_color") or "#0077be",
            "awning": challenge.get("awning_color") or challenge.get("title_color") or "#0077be",
            "icon": challenge.get("icon_color") or challenge.get("title_color") or "#0077be",
            "ribbon": challenge.get("ribbon_color") or challenge.get("title_color") or "#0077be",
        },
        "background": challenge.get("background"),
        "hud_icon_tid": challenge.get("hud_icon_tid"),
        "weight": challenge.get("weight"),
        "user_min_level": challenge.get("user_min_level"),
    }


def main() -> None:
    args = parse_args()
    config_path = Path(args.game_config)
    loc_path = Path(args.localization)
    dragons_path = Path(args.dragons)
    chests_path = Path(args.chests)
    out_path = Path(args.output)

    config = load_json(config_path, required=True)
    loc = flatten_localization(load_json(loc_path, required=False) or {})
    dragon_by_id = build_dragon_index(load_json(dragons_path, required=False) or {})
    chest_by_id = build_chest_index(load_json(chests_path, required=False) or {})

    liveops = config.get("liveops_challenges") if isinstance(config, dict) else None
    if not isinstance(liveops, dict):
        raise KeyError("game_config.json does not contain liveops_challenges")

    challenges = [x for x in (liveops.get("challenges") or []) if isinstance(x, dict)]
    goals = [x for x in (liveops.get("goals") or []) if isinstance(x, dict)]
    rewards = [x for x in (liveops.get("rewards") or []) if isinstance(x, dict)]
    goal_by_id = {first_number(x.get("id")): x for x in goals if first_number(x.get("id"))}
    reward_by_id = {first_number(x.get("id")): x for x in rewards if first_number(x.get("id"))}

    collections: List[Dict[str, Any]] = []
    for challenge in challenges:
        row = build_collection(challenge, goal_by_id, reward_by_id, loc, dragon_by_id, chest_by_id)
        if row:
            collections.append(row)
    collections.sort(key=lambda x: (x["start_ts"], x["id"]))

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "meta": {
            "collection_count": len(collections),
            "source": "game_config.liveops_challenges",
            "time_zone": "UTC",
            "enriched_with_dragons": bool(dragon_by_id),
            "enriched_with_chests": bool(chest_by_id),
        },
        "collections": collections,
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))
        f.write("\n")

    print(f"Built {out_path} with {len(collections)} Event Collections")


if __name__ == "__main__":
    main()
