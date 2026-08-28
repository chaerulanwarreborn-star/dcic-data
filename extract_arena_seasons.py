#!/usr/bin/env python3
"""Build compact arena_seasons.json for Dragon City Information Center.

Inputs:
  arena_config.json  - PVP Arenas config captured by DragonCity_GameDataHook_v6+
  game_config.json   - main Dragon City game config
  dragons.json       - generated DCIC dragon database
  localization/dragon_city_localization_baseline_en.json
  arena_overrides.json (optional rules/manual corrections)

Output:
  arena_seasons.json

The frontend never needs to download the large game_config/arena_config files.
Static Arenas (Beginner through Sea II) are stored once; seasonal Arenas are
stored under their Arena Season. Internal arena_level_id values remain in the
JSON for joining/sorting, but the DCIC UI intentionally does not display them.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent
ARENA_CONFIG_PATH = ROOT / "arena_config.json"
GAME_CONFIG_PATH = ROOT / "game_config.json"
DRAGONS_PATH = ROOT / "dragons.json"
LOCALIZATION_PATH = ROOT / "localization" / "dragon_city_localization_baseline_en.json"
OVERRIDES_PATH = ROOT / "arena_overrides.json"
OUTPUT_PATH = ROOT / "arena_seasons.json"

DEFAULT_SIGNATURES = {
    "L": {"health": 22500, "damage": 9000, "max_hatching_time": 10800},
    "M": {"health": 24750, "damage": 10950, "max_hatching_time": 10800},
    "H": {"health": 45000, "damage": 13350, "max_hatching_time": 10800},
}

ASSET_BASE = "https://raw.githubusercontent.com/chaerulanwarreborn-star/dcic-assets/main/icons/"


def load_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        if default is not None:
            return default
        raise SystemExit(f"Missing required file: {path.name}")
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def normalize_localization(raw: Any) -> Dict[str, str]:
    if isinstance(raw, dict):
        return {str(k): str(v) for k, v in raw.items() if v is not None}
    result: Dict[str, str] = {}
    if isinstance(raw, list):
        for row in raw:
            if isinstance(row, dict):
                for key, value in row.items():
                    if value is not None:
                        result[str(key)] = str(value)
    return result


def localize(localization: Dict[str, str], key: Any, fallback: str = "") -> str:
    value = str(localization.get(str(key or ""), "") or "").strip()
    return value or fallback


def remote_basename(value: Any) -> str:
    if isinstance(value, dict):
        value = value.get("remote")
    raw = str(value or "").replace("\\", "/").strip()
    name = raw.rsplit("/", 1)[-1] if raw else ""
    # The game source historically spells Beginner as "beginer" while the
    # curated dcic-assets filename uses the corrected spelling.
    return name.replace("ic-arena-beginer.png", "ic-arena-beginner.png")


def percent_map(raw: Any) -> List[Dict[str, Any]]:
    if not isinstance(raw, dict):
        return []
    result = []
    for element, value in raw.items():
        n = as_int(value)
        if not element or n == 0:
            continue
        result.append({
            "element": str(element),
            "percent": round(n / 10000, 4),  # 500000 -> 50
            "raw": n,
        })
    return result


def compact_restrictions(raw: Any) -> Dict[str, List[str]]:
    if not isinstance(raw, dict):
        return {}
    allowed_keys = (
        "banned_elements", "banned_rarities",
        "required_elements", "required_rarities",
        "allowed_elements", "allowed_rarities",
    )
    out: Dict[str, List[str]] = {}
    for key in allowed_keys:
        values = raw.get(key)
        if isinstance(values, list) and values:
            out[key] = [str(x) for x in values]

    # Older PVP Arena payloads used `elements` for the positive element
    # restriction. Normalize it into Required so the frontend can keep a
    # stable four-slot rules layout (Health, Attack, Banned, Required).
    legacy_elements = raw.get("elements")
    if isinstance(legacy_elements, list) and legacy_elements and "required_elements" not in out:
        out["required_elements"] = [str(x) for x in legacy_elements]
    return out


def compact_warrior_chest(chest_id: int, chest_index: Dict[int, Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    row = chest_index.get(chest_id)
    if not row:
        return None
    return {
        "id": chest_id,
        "gatcha_ids": [as_int(x) for x in row.get("gatcha_ids", []) if as_int(x) > 0],
        "image_file": remote_basename(row.get("ready_img") or row.get("growing_img")),
    }


def compact_arena(row: Dict[str, Any], localization: Dict[str, str], chest_index: Dict[int, Dict[str, Any]]) -> Dict[str, Any]:
    level_id = as_int(row.get("arena_level_id"))
    chest_id = as_int(row.get("warrior_chest_id"))
    out: Dict[str, Any] = {
        "id": as_int(row.get("id")),
        "arena_level_id": level_id,  # internal only; frontend does not display it
        "type": str(row.get("type") or ""),
        "position": as_int(row.get("position")),
        "name": localize(localization, row.get("tid_name"), str(row.get("tid_name") or f"Arena {level_id}")),
        "tid_name": str(row.get("tid_name") or ""),
        "trophies_to_enter": as_int(row.get("trophies_to_enter")),
        "trophies_to_drop": as_int(row.get("trophies_to_drop")),
        "combat_rewards_bonus": as_int(row.get("combat_rewards_bonus")),
        "arena_element": str(row.get("arena_element") or ""),
        "arena_icon_file": remote_basename(row.get("mobile_icon")),
        "restrictions": compact_restrictions(row.get("restrictions")),
        "attack_boosts": percent_map(row.get("elemental_attack_boost")),
        "hp_boosts": percent_map(row.get("elemental_hp_boost")),
        "recovery_timer_arena": as_int(row.get("recovery_timer_arena")),
        "warrior_chest_id": chest_id,
        "gatcha_id": as_int(row.get("gatcha_id")),
        "promotion_reward_id": as_int(row.get("promotion_reward_id")),
    }
    if "trophies_reset_value" in row:
        out["trophies_reset_value"] = as_int(row.get("trophies_reset_value"))
    if row.get("dragon_ai_level") is not None:
        out["dragon_ai_level"] = str(row.get("dragon_ai_level"))
    chest = compact_warrior_chest(chest_id, chest_index)
    if chest:
        out["warrior_chest"] = chest
    return out


def offer_egg_ids(offer: Dict[str, Any]) -> List[int]:
    ids: List[int] = []
    for resource in offer.get("resources", []):
        if not isinstance(resource, dict):
            continue
        egg = as_int(resource.get("egg"))
        if egg > 0 and egg not in ids:
            ids.append(egg)
    return ids


def find_normal_tributes(game_config: Dict[str, Any], season_windows: Dict[int, Tuple[int, int]]) -> Tuple[Dict[int, List[int]], Dict[int, str]]:
    candidates: List[Dict[str, Any]] = []
    for offer in game_config.get("offer_system", {}).get("offers", []):
        if not isinstance(offer, dict):
            continue
        analytics = str(offer.get("analytics") or "")
        low = analytics.lower()
        if "arena_tributes" not in low:
            continue
        eggs = offer_egg_ids(offer)
        if len(eggs) < 5:
            continue
        av = offer.get("availability") if isinstance(offer.get("availability"), dict) else {}
        start = as_int(av.get("from"))
        end = as_int(av.get("to"))
        if start <= 0:
            continue
        candidates.append({"analytics": analytics, "start": start, "end": end, "eggs": eggs[:5]})

    result: Dict[int, List[int]] = {}
    source: Dict[int, str] = {}
    for season_id, (start, end) in season_windows.items():
        exact = [c for c in candidates if c["start"] == start]
        if not exact:
            continue
        # Prefer the offer whose end is closest to the Arena season boundary.
        exact.sort(key=lambda c: (abs(c["end"] - end), abs(c["end"] - (end + 1)), c["analytics"]))
        best = exact[0]
        result[season_id] = list(best["eggs"])
        source[season_id] = str(best["analytics"])
    return result, source


def signatures_from_overrides(overrides: Dict[str, Any]) -> Dict[str, Dict[str, int]]:
    result = {k: dict(v) for k, v in DEFAULT_SIGNATURES.items()}
    raw = overrides.get("tribute_signatures")
    if isinstance(raw, dict):
        for rarity, values in raw.items():
            rarity = str(rarity).upper()
            if rarity not in result or not isinstance(values, dict):
                continue
            for key in ("health", "damage", "max_hatching_time"):
                if key in values:
                    result[rarity][key] = as_int(values[key], result[rarity][key])
    return result


def detect_vip_tributes(
    game_config: Dict[str, Any],
    dragons_payload: Dict[str, Any],
    known_normal_ids: Iterable[int],
    overrides: Dict[str, Any],
) -> Tuple[List[int], List[Dict[str, Any]]]:
    signatures = signatures_from_overrides(overrides)
    # A dragon explicitly listed by any known Arena Tribute offer must not be
    # inferred as VIP-Exclusive from the temporary stat signature. This is
    # intentionally archive-wide, because upcoming normal Tributes can already
    # carry the signature in the current game_config snapshot.
    normal = {as_int(x) for x in known_normal_ids}
    dragons = {as_int(d.get("id")): d for d in dragons_payload.get("dragons", []) if isinstance(d, dict)}
    raw_items = {as_int(x.get("id")): x for x in game_config.get("items", []) if isinstance(x, dict) and as_int(x.get("id")) in dragons}

    vip_config = overrides.get("vip_detection") if isinstance(overrides.get("vip_detection"), dict) else {}
    preferred_tags = {str(x).lower() for x in vip_config.get("preferred_tags_any", ["VIP", "Divinepass"])}
    require_preferred_tag = bool(vip_config.get("require_preferred_tag", False))

    found: List[Tuple[int, bool, Dict[str, Any]]] = []
    debug: List[Dict[str, Any]] = []
    for dragon_id, dragon in dragons.items():
        if dragon_id in normal:
            continue
        rarity = str(dragon.get("rarity") or "").upper()
        sig = signatures.get(rarity)
        item = raw_items.get(dragon_id)
        if not sig or not item:
            continue
        health = as_int(item.get("base_life"))
        damage = as_int(item.get("base_attack"))
        hatch = as_int(item.get("hatching_time"), 10**12)
        if health != as_int(sig.get("health")) or damage != as_int(sig.get("damage")):
            continue
        if hatch <= 0 or hatch > as_int(sig.get("max_hatching_time"), 10800):
            continue
        tags = [str(x) for x in item.get("tags", []) if x is not None]
        tag_match = bool({t.lower() for t in tags} & preferred_tags)
        if require_preferred_tag and not tag_match:
            continue
        detail = {
            "dragon_id": dragon_id,
            "rarity": rarity,
            "health": health,
            "damage": damage,
            "hatching_time": hatch,
            "tags": tags,
            "preferred_tag_match": tag_match,
        }
        found.append((dragon_id, tag_match, detail))
        debug.append(detail)

    # High-confidence candidates first, then deterministic ID order.
    found.sort(key=lambda x: (not x[1], x[0]))
    ids = [x[0] for x in found]

    manual_include = [as_int(x) for x in vip_config.get("manual_include", [])]
    manual_exclude = {as_int(x) for x in vip_config.get("manual_exclude", [])}
    for dragon_id in manual_include:
        if dragon_id > 0 and dragon_id not in ids:
            ids.append(dragon_id)
    ids = [x for x in ids if x not in manual_exclude]
    return ids, debug


def apply_season_override(season: Dict[str, Any], override: Any) -> None:
    if not isinstance(override, dict):
        return
    for key in ("tributes", "vip_exclusive_tributes"):
        if isinstance(override.get(key), list):
            season[key] = [as_int(x) for x in override[key] if as_int(x) > 0]
            season[key + "_source"] = "override"


def main() -> None:
    arena_config = load_json(ARENA_CONFIG_PATH)
    game_config = load_json(GAME_CONFIG_PATH)
    dragons_payload = load_json(DRAGONS_PATH)
    localization = normalize_localization(load_json(LOCALIZATION_PATH))
    overrides = load_json(OVERRIDES_PATH, default={})
    previous = load_json(OUTPUT_PATH, default={})

    arenas = arena_config.get("arenas", []) if isinstance(arena_config, dict) else []
    if not isinstance(arenas, list):
        raise SystemExit("arena_config.json: arenas must be an array")

    chest_index = {
        as_int(row.get("id")): row
        for row in arena_config.get("warrior_chests", [])
        if isinstance(row, dict) and as_int(row.get("id")) > 0
    }

    static_rows = [r for r in arenas if isinstance(r, dict) and as_int(r.get("arena_level_id")) in range(1, 8) and not as_int(r.get("arena_season_id"))]
    static_rows.sort(key=lambda r: as_int(r.get("arena_level_id")))
    static_arenas = [compact_arena(r, localization, chest_index) for r in static_rows]

    by_season: Dict[int, List[Dict[str, Any]]] = {}
    season_windows: Dict[int, Tuple[int, int]] = {}
    for row in arenas:
        if not isinstance(row, dict):
            continue
        season_id = as_int(row.get("arena_season_id"))
        if season_id <= 0:
            continue
        by_season.setdefault(season_id, []).append(row)
        av = row.get("availability") if isinstance(row.get("availability"), dict) else {}
        start, end = as_int(av.get("from")), as_int(av.get("to"))
        if start > 0 and end > start:
            season_windows.setdefault(season_id, (start, end))

    normal_tributes, normal_sources = find_normal_tributes(game_config, season_windows)
    previous_seasons = {
        as_int(s.get("id")): s for s in previous.get("seasons", [])
        if isinstance(s, dict) and as_int(s.get("id")) > 0
    }

    now = int(datetime.now(timezone.utc).timestamp())
    current_season_id = 0
    for sid, (start, end) in sorted(season_windows.items()):
        if start <= now <= end:
            current_season_id = sid
            break

    current_normal = normal_tributes.get(current_season_id, [])
    vip_config = overrides.get("vip_detection") if isinstance(overrides.get("vip_detection"), dict) else {}
    exclude_known_normal = bool(vip_config.get("exclude_any_known_normal_tribute", True))

    known_normal_ids = set()
    if exclude_known_normal:
        for ids in normal_tributes.values():
            known_normal_ids.update(as_int(x) for x in ids if as_int(x) > 0)
    else:
        known_normal_ids.update(as_int(x) for x in current_normal if as_int(x) > 0)

    vip_current, vip_debug = detect_vip_tributes(
        game_config,
        dragons_payload,
        known_normal_ids,
        overrides,
    )

    season_overrides = overrides.get("season_overrides") if isinstance(overrides.get("season_overrides"), dict) else {}
    seasons: List[Dict[str, Any]] = []
    for season_id in sorted(by_season):
        rows = by_season[season_id]
        rows.sort(key=lambda r: as_int(r.get("arena_level_id")))
        start, end = season_windows.get(season_id, (0, 0))
        compact_rows = [compact_arena(r, localization, chest_index) for r in rows]
        season: Dict[str, Any] = {
            "id": season_id,
            "start_ts": start,
            "end_ts": end,
            "tributes": list(normal_tributes.get(season_id, [])),
            "tributes_source": "offer_system" if season_id in normal_tributes else "unavailable",
            "vip_exclusive_tributes": [],
            "vip_exclusive_tributes_source": "unavailable",
            "arenas": compact_rows,
        }
        if season_id in normal_sources:
            season["tributes_offer_analytics"] = normal_sources[season_id]

        # Preserve previously observed VIP Tribute history. A current config snapshot
        # only tells us who is boosted now; the previous generated JSON is the archive.
        prev = previous_seasons.get(season_id, {})
        prev_vip = prev.get("vip_exclusive_tributes") if isinstance(prev, dict) else None
        if isinstance(prev_vip, list) and prev_vip:
            preserved_vip = [as_int(x) for x in prev_vip if as_int(x) > 0]
            if exclude_known_normal:
                preserved_vip = [x for x in preserved_vip if x not in known_normal_ids]
            season["vip_exclusive_tributes"] = preserved_vip
            season["vip_exclusive_tributes_source"] = str(prev.get("vip_exclusive_tributes_source") or "preserved_snapshot") if preserved_vip else "unavailable"

        if season_id == current_season_id:
            season["vip_exclusive_tributes"] = list(vip_current)
            season["vip_exclusive_tributes_source"] = "dragon_signature" if vip_current else "unavailable"

        apply_season_override(season, season_overrides.get(str(season_id)))
        seasons.append(season)

    payload = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "assets": {
            "base": ASSET_BASE,
            "arena_icons": ASSET_BASE + "pvp-arenas/",
            "dragon_stats": ASSET_BASE + "dragon-stats/",
            "element_flags": ASSET_BASE + "elements-flag/",
            "rarity_badges": ASSET_BASE + "rarity-badge/",
        },
        "meta": {
            "static_arena_count": len(static_arenas),
            "season_count": len(seasons),
            "seasonal_arena_count": sum(len(s["arenas"]) for s in seasons),
            "warrior_chest_count": len(chest_index),
            "current_season_at_build": current_season_id or None,
            "vip_excludes_known_normal_tributes": exclude_known_normal,
            "known_normal_tribute_id_count": len(known_normal_ids),
            "vip_signature_candidates_at_build": vip_debug,
        },
        "static_arenas": static_arenas,
        "seasons": seasons,
    }

    with OUTPUT_PATH.open("w", encoding="utf-8", newline="\n") as f:
        json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))
        f.write("\n")

    print(
        f"Wrote {OUTPUT_PATH.name}: {len(static_arenas)} static arenas, "
        f"{len(seasons)} seasons, current={current_season_id or 'none'}, "
        f"VIP candidates={vip_current or 'none'}"
    )


if __name__ == "__main__":
    main()
