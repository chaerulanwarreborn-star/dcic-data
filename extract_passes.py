#!/usr/bin/env python3
"""Build passes.json for Dragon City Information Center.

Source of truth:
- Divine Pass: side_events_config.json -> battle_pass
- Progression Passes: side_events_config.json -> progression_milestones

The output intentionally remains a single passes.json file.  It contains the
small homepage fields plus the Divine Pass detail payload used by
/p/divine-pass.html.  No per-pass shards and no permanent archive are created.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "side_events_config.json"
LOCALIZATION_PATH = ROOT / "localization" / "dragon_city_localization_baseline_en.json"
DRAGONS_PATH = ROOT / "dragons.json"
SKINS_PATH = ROOT / "skins.json"
CHESTS_PATH = ROOT / "chests.json"
OUTPUT_PATH = ROOT / "passes.json"

DRAGON_THUMB_BASE = "https://dci-static-s1.socialpointgames.com/static/dragoncity/mobile/ui/dragons/HD/"
SOCIALPOINT_STATIC_BASE = "https://dcw-static-s1.socialpointgames.com/static/dragoncity"
DCIC_ICON_BASE = "https://raw.githubusercontent.com/chaerulanwarreborn-star/dcic-assets/main/icons/"

RARITY_ORDER = {"H": 0, "M": 1, "L": 2, "E": 3, "V": 4, "R": 5, "C": 6}
PATH_ORDER = {"platinum": 0, "golden": 1, "gold": 1, "premium": 1, "free": 2}

RESOURCE_LABELS = {
    "c": "Gems",
    "g": "Gold",
    "f": "Food",
    "x": "XP",
    "xp": "XP",
    "pp": "Divine Points",
    "oph_token": "Divine Orbs Habitat Tokens",
    "prestige_points": "Prestige Points",
    "gacha_event_tickets": "Event Tickets",
    "permanent_gacha.heroic": "Heroic Orbs",
    "permanent_gacha.mythical": "Mythical Orbs",
    "permanent_gacha.legendary": "Legendary Orbs",
}

RESOURCE_ICONS = {
    "c": DCIC_ICON_BASE + "resources/ic-gem.png",
    "g": DCIC_ICON_BASE + "resources/ic-gold.png",
    "f": DCIC_ICON_BASE + "resources/ic-food.png",
    "x": DCIC_ICON_BASE + "resources/ic-experience-xp.png",
    "xp": DCIC_ICON_BASE + "resources/ic-experience-xp.png",
    "pp": DCIC_ICON_BASE + "pass/ic-pass-points-massive.png",
}

# Same public reward type names used by the site's shared DCICRewardUI.
THEME_RESOURCE_TYPES = {
    "c": "gems",
    "g": "gold",
    "f": "food",
    "x": "xp",
    "xp": "xp",
    "pp": "divine_points",
}

GOAL_ICON_MAP = {
    "FEED": "pass/ic-gl-feed.png",
    "COMBAT_ARENA": "pass/ic-gl-arenas.png",
    "ARENA": "pass/ic-gl-arenas.png",
    "BREED": "pass/ic-gl-breed.png",
    "WIZARD": "pass/ic-wizard-hollow.png",
}

GOAL_LABEL_RULES = [
    ("COMBAT_ARENA", "Arena Battle"),
    ("ARENA", "Arena Battle"),
    ("FEED", "Feed a dragon"),
    ("BREED", "Breed dragons"),
    ("HATCH", "Hatch dragons"),
    ("WATCH", "Watch a Dragon TV video"),
    ("VIDEO", "Watch a Dragon TV video"),
    ("MAZE", "Spend Maze Coins"),
    ("GRID", "Spend Grid Coins"),
    ("FOG", "Spend Fog Coins"),
    ("TOWER", "Spend Tower Coins"),
    ("RUNNER", "Play Runner Island"),
    ("PUZZLE", "Play Puzzle Island"),
    ("WIZARD", "Play Wizards' Hollow"),
    ("LEAGUE", "League Battle"),
    ("QUEST", "Complete a Quest"),
]


def load_json(path: Path) -> Any:
    if not path.exists():
        raise SystemExit(f"Missing required file: {path.name}")
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def load_optional_json(path: Path) -> Any:
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


def unwrap_config(raw: Any) -> Dict[str, Any]:
    """Accept raw config, {config:{...}}, or {game_data:{config:{...}}}."""
    if not isinstance(raw, dict):
        return {}
    game_data = raw.get("game_data")
    if isinstance(game_data, dict) and isinstance(game_data.get("config"), dict):
        return game_data["config"]
    if isinstance(raw.get("config"), dict):
        return raw["config"]
    return raw


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


def as_number(value: Any) -> Any:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return value
    if number.is_integer():
        return int(number)
    return number


def parse_time(value: Any) -> int:
    if isinstance(value, (int, float)):
        return int(value)
    text = str(value or "").strip()
    if not text:
        return 0
    if text.isdigit():
        return int(text)
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


def duration_seconds(value: Any) -> int:
    text = str(value or "").strip().lower()
    if not text:
        return 0
    if text.isdigit():
        return int(text)
    total = 0
    for amount, unit in re.findall(r"(\d+(?:\.\d+)?)\s*([dhms])", text):
        n = float(amount)
        total += int(n * {"d": 86400, "h": 3600, "m": 60, "s": 1}[unit])
    return total


def availability_window(value: Any) -> Tuple[int, int]:
    rows = value if isinstance(value, list) else [value]
    starts: List[int] = []
    ends: List[int] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        start = parse_time(row.get("from"))
        end = parse_time(row.get("to"))
        if start > 0 and end <= start:
            dur = duration_seconds(row.get("dur"))
            if dur > 0:
                end = start + dur
        if start > 0:
            starts.append(start)
        if end > start:
            ends.append(end)
    if not starts or not ends:
        return 0, 0
    return min(starts), max(ends)


def iso(ts: int) -> str:
    return datetime.fromtimestamp(ts, timezone.utc).isoformat().replace("+00:00", "Z")


def humanize_key(value: Any) -> str:
    text = str(value or "").strip()
    text = text.replace(".", " ").replace("_", " ").replace("-", " ")
    text = re.sub(r"\s+", " ", text).strip()
    return text.title() if text else "Reward"


def slug(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(value or "").lower()).strip("_")


def first_image(row: Dict[str, Any]) -> str:
    for key in ("thumbnail", "image_url", "icon_url", "image", "img_url"):
        value = row.get(key)
        if isinstance(value, str) and value.startswith(("http://", "https://")):
            return value
    for key in ("image_candidates", "thumbnail_candidates", "images"):
        value = row.get(key)
        if isinstance(value, list):
            for item in value:
                if isinstance(item, str) and item.startswith(("http://", "https://")):
                    return item
    return ""


def obvious_collection(payload: Any, names: Iterable[str]) -> List[Dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    for name in names:
        rows = payload.get(name)
        if isinstance(rows, list):
            return [row for row in rows if isinstance(row, dict)]
    data = payload.get("data")
    if isinstance(data, dict):
        for name in names:
            rows = data.get(name)
            if isinstance(rows, list):
                return [row for row in rows if isinstance(row, dict)]
    return []


def id_index(rows: Iterable[Dict[str, Any]], id_keys: Tuple[str, ...] = ("id",)) -> Dict[int, Dict[str, Any]]:
    out: Dict[int, Dict[str, Any]] = {}
    for row in rows:
        for key in id_keys:
            rid = as_int(row.get(key))
            if rid > 0:
                out[rid] = row
                break
    return out


def support_indexes() -> Tuple[Dict[int, Dict[str, Any]], Dict[int, Dict[str, Any]], Dict[int, Dict[str, Any]]]:
    dragons_raw = load_optional_json(DRAGONS_PATH)
    skins_raw = load_optional_json(SKINS_PATH)
    chests_raw = load_optional_json(CHESTS_PATH)

    dragons = id_index(
        obvious_collection(dragons_raw, ("dragons", "items", "rows")),
        ("id", "dragon_id"),
    )
    skins = id_index(
        obvious_collection(skins_raw, ("skins", "items", "rows")),
        ("id", "skin_id"),
    )
    chests = id_index(
        obvious_collection(chests_raw, ("chests", "items", "rows")),
        ("id", "chest_id", "source_chest_id"),
    )
    return dragons, skins, chests


def dragon_record(
    dragon_id: int,
    dragons: Dict[int, Dict[str, Any]],
    localization: Dict[str, str],
    *,
    path: str = "",
) -> Dict[str, Any]:
    row = dragons.get(dragon_id, {})
    img_name = str(
        row.get("img_name_mobile")
        or row.get("img_name")
        or row.get("image_name")
        or ""
    ).strip()
    thumbnail = first_image(row)
    if not thumbnail and img_name:
        thumbnail = f"{DRAGON_THUMB_BASE}thumb_{img_name}_3.png"

    record: Dict[str, Any] = {
        "id": dragon_id,
        "name": loc_text(
            localization,
            f"tid_unit_{dragon_id}_name",
            str(row.get("name") or f"Dragon {dragon_id}"),
        ),
        "rarity": str(row.get("rarity") or row.get("dragon_rarity") or "").upper(),
        "img_name": img_name,
        "thumbnail": thumbnail,
    }
    if path:
        record["path"] = path
    return record


def sorted_dragons(
    ids: Iterable[int],
    dragons: Dict[int, Dict[str, Any]],
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
        rows.append(dragon_record(did, dragons, localization, path=path))
    rows.sort(key=lambda d: RARITY_ORDER.get(str(d.get("rarity") or "").upper(), 99))
    return rows


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


def make_popup(kind: str, item_id: int) -> Dict[str, Any]:
    if kind not in {"dragon", "dragon_orbs", "skin", "chest"} or item_id <= 0:
        return {}
    return {"kind": kind, "id": item_id}


def normalize_reward(
    reward_id: Any,
    reward_by_id: Dict[int, Dict[str, Any]],
    dragons: Dict[int, Dict[str, Any]],
    skins: Dict[int, Dict[str, Any]],
    chests: Dict[int, Dict[str, Any]],
    localization: Dict[str, str],
) -> Optional[Dict[str, Any]]:
    rid = as_int(reward_id)
    if rid <= 0:
        return None
    row = reward_by_id.get(rid, {})
    raw = row.get("reward") if isinstance(row.get("reward"), list) else []
    items: List[Dict[str, Any]] = []

    def add_resource(key: str, amount: Any, values: Any = None) -> None:
        label = RESOURCE_LABELS.get(key, humanize_key(key))
        theme_type = THEME_RESOURCE_TYPES.get(key, "resource")
        item = {
            "kind": "resource",
            "type": theme_type,
            "resource": theme_type,
            "key": key,
            "name": label,
            "amount": as_number(amount),
            "image_url": RESOURCE_ICONS.get(key, ""),
        }
        if values is not None:
            item["values"] = values
        items.append(item)

    for entry in raw:
        if not isinstance(entry, dict):
            continue
        for key, value in entry.items():
            if key == "egg":
                values = value if isinstance(value, list) else [value]
                for raw_id in values:
                    did = as_int(raw_id)
                    if did <= 0:
                        continue
                    dragon = dragon_record(did, dragons, localization)
                    items.append({
                        "kind": "dragon",
                        "type": "dragon_egg",
                        "asset_kind": "dragon",
                        "id": did,
                        "dragon_id": did,
                        "name": dragon["name"],
                        "amount": 1,
                        "img_name_mobile": dragon.get("img_name", ""),
                        "image_url": dragon.get("thumbnail", ""),
                        "popup": make_popup("dragon", did),
                    })
                continue

            if key == "seeds":
                values = value if isinstance(value, list) else []
                for seed in values:
                    if not isinstance(seed, dict):
                        continue
                    did = as_int(seed.get("id"))
                    amount = as_int(seed.get("amount"))
                    if did <= 0:
                        continue
                    dragon = dragon_record(did, dragons, localization)
                    items.append({
                        "kind": "dragon_orbs",
                        "type": "dragon_orbs",
                        "asset_kind": "dragon",
                        "id": did,
                        "dragon_id": did,
                        "name": f"{dragon['name']} Orbs",
                        "amount": amount,
                        "dragon_rarity": dragon.get("rarity", ""),
                        "img_name_mobile": dragon.get("img_name", ""),
                        "image_url": dragon.get("thumbnail", ""),
                        "popup": make_popup("dragon_orbs", did),
                    })
                continue

            if key == "rarity_seeds":
                values = value if isinstance(value, list) else []
                for seed in values:
                    if not isinstance(seed, dict):
                        continue
                    rarity = str(seed.get("rarity") or "").upper()
                    amount = as_int(seed.get("amount"))
                    items.append({
                        "kind": "resource",
                        "type": "joker_orbs",
                        "resource": "joker_orbs",
                        "key": "rarity_seeds",
                        "name": f"{rarity or 'Rarity'} Joker Orbs",
                        "amount": amount,
                        "rarity": rarity,
                        "image_url": "",
                    })
                continue

            if key == "chest":
                values = value if isinstance(value, list) else [value]
                for raw_id in values:
                    cid = as_int(raw_id)
                    if cid <= 0:
                        continue
                    meta = chests.get(cid, {})
                    chest_type = str(meta.get("type") or meta.get("chest_type") or "generic")
                    chest_img = str(
                        meta.get("source_chest_img_name")
                        or meta.get("img_name")
                        or meta.get("image_name")
                        or ""
                    ).strip()
                    image_candidates = meta.get("image_candidates") if isinstance(meta.get("image_candidates"), list) else []
                    items.append({
                        "kind": "chest",
                        "type": "chest",
                        "asset_kind": "chest",
                        "id": cid,
                        "chest_id": cid,
                        "source_chest_id": cid,
                        "source_chest_img_name": chest_img,
                        "img_name": chest_img,
                        "chest_type": chest_type,
                        "name": str(meta.get("name") or meta.get("title") or f"Chest #{cid}"),
                        "amount": 1,
                        "image_url": first_image(meta),
                        "image_candidates": image_candidates,
                        "popup": {"kind": "chest", "id": cid, "type": chest_type},
                    })
                continue

            if key == "skin":
                values = value if isinstance(value, list) else [value]
                for raw_id in values:
                    sid = as_int(raw_id)
                    if sid <= 0:
                        continue
                    meta = skins.get(sid, {})
                    items.append({
                        "kind": "skin",
                        "type": "skin",
                        "asset_kind": "skin",
                        "id": sid,
                        "skin_id": sid,
                        "name": str(meta.get("name") or meta.get("skin_name") or f"Skin #{sid}"),
                        "amount": 1,
                        "image_url": first_image(meta),
                        "image_candidates": meta.get("image_candidates") if isinstance(meta.get("image_candidates"), list) else [],
                        "popup": make_popup("skin", sid),
                    })
                continue

            # "b" is the compact Dragon City reward key for building IDs.
            # A scalar is one building; a repeated list means multiple copies.
            if key == "b":
                values = value if isinstance(value, list) else [value]
                ids = [as_int(v) for v in values if as_int(v) > 0]
                if ids:
                    same = len(set(ids)) == 1
                    items.append({
                        "kind": "building",
                        "type": "building",
                        "asset_kind": "building",
                        "id": ids[0],
                        "item_id": ids[0],
                        "name": f"Building #{ids[0]}" if same else "Buildings",
                        "amount": len(ids),
                        "values": ids,
                        "image_url": DCIC_ICON_BASE + "text-icons/gr-category-buildings.png",
                    })
                continue

            # Keep the most common pack families readable even before a
            # dedicated popup exists for them.
            if key.startswith("album_pack"):
                items.append({
                    "kind": "resource",
                    "type": "sticker_pack",
                    "resource": "sticker_pack",
                    "key": key,
                    "name": "Sticker Pack",
                    "amount": as_number(value),
                    "image_url": DCIC_ICON_BASE + "stickers/ic_stickers_pack_ace_generic_massive.png",
                })
                continue
            if key.startswith("pet_food_pack"):
                items.append({
                    "kind": "resource",
                    "type": "pet_food",
                    "resource": "pet_food",
                    "key": key,
                    "name": "Pet Food Pack",
                    "amount": as_number(value),
                    "image_url": DCIC_ICON_BASE + "currency-icon/ic-pet-food-massive_c.png",
                })
                continue

            if isinstance(value, list):
                if all(not isinstance(v, (dict, list)) for v in value):
                    add_resource(key, len(value), value)
                else:
                    add_resource(key, len(value), value)
                continue

            if isinstance(value, dict):
                amount = value.get("amount", 1)
                add_resource(key, amount, value)
                continue

            add_resource(key, value)

    first = items[0] if items else {}
    label = str(first.get("name") or f"Reward #{rid}")
    if len(items) > 1:
        label += f" +{len(items) - 1}"

    return {
        "reward_id": rid,
        "name": label,
        "amount": first.get("amount", 1) if first else 0,
        "kind": first.get("kind", "unknown") if first else "unknown",
        "image_url": first.get("image_url", "") if first else "",
        "popup": first.get("popup", {}) if first else {},
        "rarity": first.get("rarity", "") if first else "",
        "items": items,
        "raw": raw,
    }


def reward_points(reward: Optional[Dict[str, Any]]) -> int:
    if not reward:
        return 0
    for item in reward.get("items", []) or []:
        if str(item.get("key") or "") == "pp":
            return as_int(item.get("amount"))
    return 0


def economy_visual_icon_index(config: Dict[str, Any]) -> Tuple[Dict[str, Dict[str, Any]], List[Tuple[str, Dict[str, Any]]]]:
    """Index economy_system.visual_icon from side_events_config."""
    rows = config.get("economy_system", {}).get("visual_icon", [])
    exact: Dict[str, Dict[str, Any]] = {}
    wildcards: List[Tuple[str, Dict[str, Any]]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        key = str(row.get("id") or "").strip()
        if not key:
            continue
        exact[key] = row
        if key.endswith("*"):
            wildcards.append((key[:-1], row))
    wildcards.sort(key=lambda pair: len(pair[0]), reverse=True)
    return exact, wildcards


def resolve_currency_icon(
    currency_id: str,
    exact_icons: Dict[str, Dict[str, Any]],
    wildcard_icons: List[Tuple[str, Dict[str, Any]]],
) -> Dict[str, str]:
    """Resolve the regular Socialpoint icon declared by side_events_config."""
    currency_id = str(currency_id or "").strip()
    if not currency_id:
        return {}

    row = exact_icons.get(currency_id)
    matched_id = currency_id if row else ""
    if row is None:
        for prefix, candidate in wildcard_icons:
            if currency_id.startswith(prefix):
                row = candidate
                matched_id = str(candidate.get("id") or "")
                break
    if not isinstance(row, dict):
        return {}

    regular = row.get("regular")
    remote = str(regular.get("remote") if isinstance(regular, dict) else "").strip()
    if not remote:
        return {}

    resolved_remote = remote.replace("$HDSD", "HD")
    if resolved_remote.startswith(("http://", "https://")):
        url = resolved_remote
    else:
        url = SOCIALPOINT_STATIC_BASE.rstrip("/") + "/" + resolved_remote.lstrip("/")

    return {
        "currency_id": currency_id,
        "visual_icon_id": matched_id,
        "icon_remote": remote,
        "icon_url": url,
    }


def goal_label(action_type: str) -> str:
    upper = str(action_type or "").upper()
    for token, label in GOAL_LABEL_RULES:
        if token in upper:
            return label
    return humanize_key(action_type or "Goal")


def goal_icon(action_type: str) -> str:
    upper = str(action_type or "").upper()
    for token, rel in GOAL_ICON_MAP.items():
        if token in upper:
            return DCIC_ICON_BASE + rel
    return DCIC_ICON_BASE + "pass/ic-pass-points-massive.png"


def resolve_goal_text(
    goal: Dict[str, Any],
    actions: List[Dict[str, Any]],
    localization: Dict[str, str],
) -> str:
    for obj in [goal] + actions:
        for key in ("name_tid", "title_tid", "description_tid", "text_tid"):
            tid = obj.get(key)
            if tid:
                value = loc_text(localization, tid, "")
                if value:
                    return value
    types = [str(a.get("type") or "").strip() for a in actions if str(a.get("type") or "").strip()]
    if not types:
        return "Divine Pass Goal"
    labels: List[str] = []
    for action_type in types:
        label = goal_label(action_type)
        if label not in labels:
            labels.append(label)
    return " / ".join(labels)


def build_goal(
    goal_id: Any,
    goal_by_id: Dict[int, Dict[str, Any]],
    action_by_id: Dict[int, Dict[str, Any]],
    reward_by_id: Dict[int, Dict[str, Any]],
    dragons: Dict[int, Dict[str, Any]],
    skins: Dict[int, Dict[str, Any]],
    chests: Dict[int, Dict[str, Any]],
    localization: Dict[str, str],
) -> Optional[Dict[str, Any]]:
    gid = as_int(goal_id)
    goal = goal_by_id.get(gid)
    if not isinstance(goal, dict):
        return None

    action_ids = [as_int(x) for x in goal.get("collectible_actions", []) or [] if as_int(x) > 0]
    actions = [action_by_id[x] for x in action_ids if x in action_by_id]
    action_type = str(actions[0].get("type") or "") if actions else ""
    targets = [as_int(a.get("amount")) for a in actions if as_int(a.get("amount")) > 0]
    target = max(targets) if targets else 0

    reward = normalize_reward(
        goal.get("reward"),
        reward_by_id,
        dragons,
        skins,
        chests,
        localization,
    )

    eligibility = goal.get("eligibility") if isinstance(goal.get("eligibility"), dict) else {}
    week = as_int(eligibility.get("week"))

    return {
        "id": gid,
        "title": resolve_goal_text(goal, actions, localization),
        "week": week,
        "action_type": action_type,
        "target": target,
        "divine_points": reward_points(reward),
        "icon_url": goal_icon(action_type),
        "reward": reward,
        "collectible_actions": [
            {
                "id": as_int(a.get("id")),
                "type": str(a.get("type") or ""),
                "amount": as_int(a.get("amount")),
                "rules": a.get("rules") if isinstance(a.get("rules"), dict) else {},
            }
            for a in actions
        ],
    }


def divine_passes(
    config: Dict[str, Any],
    localization: Dict[str, str],
    dragons: Dict[int, Dict[str, Any]],
    skins: Dict[int, Dict[str, Any]],
    chests: Dict[int, Dict[str, Any]],
) -> List[Dict[str, Any]]:
    section = config.get("battle_pass", {})
    if not isinstance(section, dict):
        return []

    node_by_id = {
        as_int(row.get("id")): row
        for row in section.get("nodes", [])
        if isinstance(row, dict) and as_int(row.get("id")) > 0
    }
    extra_by_id = {
        as_int(row.get("id")): row
        for row in section.get("extra_nodes", [])
        if isinstance(row, dict) and as_int(row.get("id")) > 0
    }
    reward_by_id = {
        as_int(row.get("id")): row
        for row in section.get("rewards", [])
        if isinstance(row, dict) and as_int(row.get("id")) > 0
    }
    goal_by_id = {
        as_int(row.get("id")): row
        for row in section.get("goals", [])
        if isinstance(row, dict) and as_int(row.get("id")) > 0
    }
    action_by_id = {
        as_int(row.get("id")): row
        for row in section.get("collectible_actions", [])
        if isinstance(row, dict) and as_int(row.get("id")) > 0
    }
    parameter_map = {
        str(row.get("name") or ""): row.get("value")
        for row in section.get("parameters", [])
        if isinstance(row, dict) and str(row.get("name") or "").strip()
    }

    out: List[Dict[str, Any]] = []
    for row in section.get("battle_pass", []):
        if not isinstance(row, dict):
            continue

        pass_id = as_int(row.get("id"))
        start_ts, end_ts = availability_window(row.get("availability"))
        if pass_id <= 0 or start_ts <= 0 or end_ts <= start_ts:
            continue

        nodes: List[Dict[str, Any]] = []
        premium_dragon_ids: List[int] = []
        main_reward_node = as_int(row.get("main_reward_node"))

        for node_id in row.get("nodes", []) or []:
            node = node_by_id.get(as_int(node_id), {})
            if not node:
                continue
            premium = normalize_reward(
                node.get("premium_reward"),
                reward_by_id, dragons, skins, chests, localization,
            )
            free = normalize_reward(
                node.get("free_reward"),
                reward_by_id, dragons, skins, chests, localization,
            )
            if premium:
                premium_dragon_ids.extend(extract_egg_ids(premium.get("raw")))
            nodes.append({
                "id": as_int(node.get("id")),
                "completion_score": as_int(node.get("completion_score")),
                "premium_reward": premium,
                "free_reward": free,
                "is_main_reward": as_int(node.get("id")) == main_reward_node,
                "limit_bp_discount": bool(node.get("limit_bp_discount", False)),
            })

        nodes.sort(key=lambda n: (as_int(n.get("completion_score")), as_int(n.get("id"))))

        # Put the main reward dragon first when it is a dragon, then the rest by rarity.
        main_dragon_ids: List[int] = []
        if main_reward_node in node_by_id:
            main_reward = normalize_reward(
                node_by_id[main_reward_node].get("premium_reward"),
                reward_by_id, dragons, skins, chests, localization,
            )
            if main_reward:
                main_dragon_ids = extract_egg_ids(main_reward.get("raw"))
        ordered_featured_ids = main_dragon_ids + [x for x in premium_dragon_ids if x not in main_dragon_ids]
        featured = sorted_dragons(ordered_featured_ids, dragons, localization, path="premium")
        if main_dragon_ids:
            featured.sort(key=lambda d: (0 if as_int(d.get("id")) in main_dragon_ids else 1,
                                         RARITY_ORDER.get(str(d.get("rarity") or "").upper(), 99)))

        extra_id = as_int(row.get("extra_node"))
        extra_node = extra_by_id.get(extra_id, {})
        extra_reward = None
        if extra_node:
            extra_reward = {
                "id": extra_id,
                "iteration_score": as_int(extra_node.get("iteration_score")),
                "free_reward": normalize_reward(
                    extra_node.get("free_reward"),
                    reward_by_id, dragons, skins, chests, localization,
                ),
                "premium_reward": normalize_reward(
                    extra_node.get("premium_reward"),
                    reward_by_id, dragons, skins, chests, localization,
                ),
                "elite_reward": normalize_reward(
                    extra_node.get("elite_reward"),
                    reward_by_id, dragons, skins, chests, localization,
                ),
            }

        daily_goals: List[Dict[str, Any]] = []
        for goal_id in row.get("daily_goals", []) or []:
            goal = build_goal(
                goal_id, goal_by_id, action_by_id, reward_by_id,
                dragons, skins, chests, localization,
            )
            if goal:
                daily_goals.append(goal)

        weekly: Dict[str, List[Dict[str, Any]]] = {f"week_{i}": [] for i in range(1, 5)}
        weekly_unassigned: List[Dict[str, Any]] = []
        for goal_id in row.get("weekly_goals", []) or []:
            goal = build_goal(
                goal_id, goal_by_id, action_by_id, reward_by_id,
                dragons, skins, chests, localization,
            )
            if not goal:
                continue
            week = as_int(goal.get("week"))
            key = f"week_{week}"
            if key in weekly:
                weekly[key].append(goal)
            else:
                weekly_unassigned.append(goal)

        localized_title = loc_text(localization, row.get("name_tid"), "Divine Pass")
        localized_season = loc_text(localization, row.get("season_tid"), "")
        localized_description = loc_text(localization, row.get("description_tid"), "")

        elite_extra = normalize_reward(
            row.get("elite_extra_reward"),
            reward_by_id, dragons, skins, chests, localization,
        )
        purchased_elite_extra = normalize_reward(
            row.get("purchased_elite_extra_reward"),
            reward_by_id, dragons, skins, chests, localization,
        )
        purchased_premium_extra = normalize_reward(
            row.get("purchased_premium_extra_reward"),
            reward_by_id, dragons, skins, chests, localization,
        )
        booster_parameters = {
            key: value
            for key, value in parameter_map.items()
            if "BOOST" in key.upper() or "MULTIPLIER" in key.upper()
        }

        out.append({
            "key": f"divine_pass:{pass_id}",
            "id": pass_id,
            "type": "divine_pass",
            "variant": "divine_pass",
            "type_label": "Divine Pass",
            "title": localized_title,
            "subtitle": localized_season,
            "description": localized_description,
            "start_ts": start_ts,
            "end_ts": end_ts,
            "start_iso": iso(start_ts),
            "end_iso": iso(end_ts),
            "details": f"/p/divine-pass.html?id={pass_id}",
            "source_section": "battle_pass.battle_pass",
            "featured_dragons": featured,
            "featured_dragon_count": len(featured),
            "divine_pass": {
                "main_reward_node": main_reward_node,
                "node_count": len(nodes),
                "nodes": nodes,
                "extra_reward": extra_reward,
                "goals": {
                    "daily": daily_goals,
                    **weekly,
                    "unassigned": weekly_unassigned,
                },
                "elite": {
                    "enabled": bool(as_int(parameter_map.get("ELITE_PASS_ENABLED", 1))),
                    "orbs_producing_habitat_id": as_int(row.get("orbs_producing_habitat_id")),
                    "elite_extra_reward": elite_extra,
                    "purchased_elite_extra_reward": purchased_elite_extra,
                    "purchased_premium_extra_reward": purchased_premium_extra,
                    "booster_parameters": booster_parameters,
                },
                "asset": str(row.get("asset") or ""),
                "sound_tag": str(row.get("sound_tag") or ""),
                "icon_id": str(row.get("icon_id") or ""),
            },
        })

    return out


def progression_passes(
    config: Dict[str, Any],
    localization: Dict[str, str],
    dragons: Dict[int, Dict[str, Any]],
) -> List[Dict[str, Any]]:
    pm = config.get("progression_milestones", {})
    if not isinstance(pm, dict):
        return []

    unlock_rows = config.get("unlock_system", {}).get("unlocks", [])
    unlock_by_id = {
        str(row.get("id")): row
        for row in unlock_rows
        if isinstance(row, dict) and row.get("id") is not None
    }
    view_by_id = {
        as_int(row.get("id")): row
        for row in pm.get("view_templates_ui", [])
        if isinstance(row, dict)
    }
    progression_by_id = {
        as_int(row.get("id")): row
        for row in pm.get("ps_progressions", [])
        if isinstance(row, dict)
    }
    route_by_id = {
        as_int(row.get("id")): row
        for row in pm.get("ps_routes", [])
        if isinstance(row, dict)
    }
    path_by_id = {
        as_int(row.get("id")): row
        for row in pm.get("ps_paths", [])
        if isinstance(row, dict)
    }
    goal_by_id = {
        as_int(row.get("id")): row
        for row in pm.get("goals", [])
        if isinstance(row, dict)
    }
    reward_by_id = {
        as_int(row.get("id")): row
        for row in pm.get("rewards", [])
        if isinstance(row, dict)
    }
    exact_icons, wildcard_icons = economy_visual_icon_index(config)

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
        title = loc_text(
            localization,
            view.get("title_tid"),
            str(row.get("analytics_tag") or "Progression Pass"),
        )
        variant = slug(row.get("analytics_tag") or title or "progression_pass")

        progression = progression_by_id.get(as_int(row.get("ps_progression_id")), {})
        route_rows = [
            route_by_id.get(as_int(route_id), {})
            for route_id in progression.get("route_ids", []) or []
        ]

        currencies: List[str] = []
        for route in route_rows:
            currency = str(route.get("currency") or "").strip() if isinstance(route, dict) else ""
            if currency and currency not in currencies:
                currencies.append(currency)

        icon_meta: Dict[str, str] = {}
        for currency in currencies:
            icon_meta = resolve_currency_icon(currency, exact_icons, wildcard_icons)
            if icon_meta:
                break

        paths: List[Tuple[int, int, Dict[str, Any]]] = []
        seq = 0
        for route in route_rows:
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
            for dragon in sorted_dragons(ids, dragons, localization, path=path_name):
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
            "title": title,
            "subtitle": "",
            "start_ts": start_ts,
            "end_ts": end_ts,
            "start_iso": iso(start_ts),
            "end_iso": iso(end_ts),
            "details": f"/p/progression-pass.html?id={pass_id}",
            "source_section": "progression_milestones.progression_milestones",
            "unlock_system_availability": unlock_id,
            "featured_dragons": featured,
            "featured_dragon_count": len(featured),
        }
        if currencies:
            pass_record["currency_ids"] = currencies
        if icon_meta:
            pass_record.update(icon_meta)

        hud_asset = str(view.get("hud_button_asset") or "").strip()
        if hud_asset:
            pass_record["hud_button_asset"] = hud_asset
        if row.get("player_segment_ids"):
            pass_record["player_segment_ids"] = [
                as_int(x) for x in row.get("player_segment_ids", []) if as_int(x) > 0
            ]
        if row.get("player_segmentation_type"):
            pass_record["player_segmentation_type"] = str(row.get("player_segmentation_type"))

        out.append(pass_record)

    return out


def keep_current_and_upcoming(passes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """No archive yet: remove passes that have already ended."""
    now_ts = int(datetime.now(timezone.utc).timestamp())
    return [row for row in passes if as_int(row.get("end_ts")) >= now_ts]


def main() -> None:
    config = unwrap_config(load_json(CONFIG_PATH))
    localization = normalize_localization(load_json(LOCALIZATION_PATH))
    dragons, skins, chests = support_indexes()

    passes = divine_passes(config, localization, dragons, skins, chests)
    passes += progression_passes(config, localization, dragons)
    passes = keep_current_and_upcoming(passes)

    dedup: Dict[str, Dict[str, Any]] = {row["key"]: row for row in passes}
    passes = sorted(
        dedup.values(),
        key=lambda p: (as_int(p.get("start_ts")), as_int(p.get("end_ts")), str(p.get("key"))),
    )

    payload = {
        "schema_version": 3,
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "source_file": CONFIG_PATH.name,
        "archive_enabled": False,
        "pass_count": len(passes),
        "divine_pass_count": sum(1 for p in passes if p.get("type") == "divine_pass"),
        "progression_pass_count": sum(1 for p in passes if p.get("type") == "progression_pass"),
        "passes": passes,
    }

    with OUTPUT_PATH.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
        f.write("\n")

    print(
        f"Wrote {OUTPUT_PATH.name}: {len(passes)} active/upcoming passes "
        f"from {CONFIG_PATH.name}"
    )


if __name__ == "__main__":
    main()
