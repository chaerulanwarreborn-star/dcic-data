#!/usr/bin/env python3
"""Build compact Wizards' Hollow homepage/page data for Dragon City Information Center.

Inputs (repository root by default):
  side_events_config.json
  game_config.json                         # optional fallback lookup; kept build-time only
  localization/dragon_city_localization_baseline_en.json
  dragons.json                             # optional, preferred dragon names/art
  extract_dragons.py                       # optional, shared full-body override source
  skins.json                               # optional, preferred skin names/art
  chests.json                              # optional, preferred chest names/art

Output:
  wizards_hollow.json

The frontend should fetch only wizards_hollow.json. Large source configs are never
needed by the browser.
"""
from __future__ import annotations

EXTRACTOR_BUILD = "2026-09-01-perk-stale-json-fallback-v9"

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

# Reuse the exact full-body overrides maintained by extract_dragons.py.
# dragons.json is still the preferred compact source; these mappings guarantee that
# Wizards' Hollow follows the same corrected art when an override exists.
try:
    from extract_dragons import (
        DRAGON_FULL_BODY_OVERRIDES as DCIC_DRAGON_FULL_BODY_OVERRIDES,
        DRAGON_ASSET_OVERRIDES as DCIC_DRAGON_ASSET_OVERRIDES,
    )
except Exception:
    DCIC_DRAGON_FULL_BODY_OVERRIDES = {}
    DCIC_DRAGON_ASSET_OVERRIDES = {}


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


def asset_basename(value: Any) -> str:
    raw = str(value or "").strip().replace("\\", "/")
    if not raw:
        return ""
    return raw.rsplit("/", 1)[-1]


def build_perk_catalog(cfg: Mapping[str, Any]) -> Dict[int, Dict[str, Any]]:
    fallback_specs: Dict[int, Dict[str, Any]] = {
        1: {
            "id": 1,
            "type": "character",
            "name_tid": "tid_name_increase_breeding_chances",
            "description_tid": "tid_perk_description_breeding_chances",
            "rarity_level": 1,
            "frame_file": "ic-character-perk-frame-basic.png",
            "icon_files": ["ic-breeding-boost-perk.png"],
            "ability_ids": [1],
            "ability_types": ["increase_breeding_chances"],
        },
        2: {
            "id": 2,
            "type": "combat",
            "name_tid": "tid_health_perk_name",
            "description_tid": "tid_health_perk_desc",
            "rarity_level": 1,
            "frame_file": "ic-combat-perk-frame-basic.png",
            "icon_files": ["ic-health-perk.png"],
            "ability_ids": [2],
            "ability_types": ["dragon_life_boost"],
        },
        3: {
            "id": 3,
            "type": "combat",
            "name_tid": "tid_damage_perk_name",
            "description_tid": "tid_damage_perk_desc",
            "rarity_level": 1,
            "frame_file": "ic-combat-perk-frame-basic.png",
            "icon_files": ["ic-combat-perk.png"],
            "ability_ids": [3],
            "ability_types": ["dragon_attack_boost"],
        },
        4: {
            "id": 4,
            "type": "combat",
            "name_tid": "tid_phoenix_perk_name",
            "description_tid": "tid_phoenix_perk_desc",
            "rarity_level": 3,
            "frame_file": "ic-combat-perk-frame-pro.png",
            "icon_files": ["ic-phoenix-perk.png"],
            "ability_ids": [4],
            "ability_types": ["phoenix_skill"],
        },
    }

    root = cfg.get("perks") or {}
    if not isinstance(root, dict):
        return fallback_specs
    abilities = {
        as_int(row.get("id")): row
        for row in list_rows(root.get("abilities"))
        if as_int(row.get("id")) > 0
    }
    out: Dict[int, Dict[str, Any]] = {
        perk_id: dict(spec) for perk_id, spec in fallback_specs.items()
    }
    for row in list_rows(root.get("perks")):
        perk_id = as_int(row.get("id"))
        if perk_id <= 0:
            continue
        ability_rows = [abilities.get(as_int(aid), {}) for aid in (row.get("abilities") or [])]
        icon_files = unique_strings(
            asset_basename((ability.get("asset") or {}).get("remote"))
            for ability in ability_rows
            if isinstance(ability, dict)
        )
        frame_file = asset_basename((row.get("asset") or {}).get("remote"))
        out[perk_id] = {
            "id": perk_id,
            "type": str(row.get("type") or ""),
            "name_tid": str(row.get("name_tid") or ""),
            "description_tid": str(row.get("description_tid") or ""),
            "rarity_level": as_int(row.get("rarity_level")),
            "frame_file": frame_file,
            "icon_files": icon_files,
            "ability_ids": [as_int(x) for x in (row.get("abilities") or []) if as_int(x) > 0],
            "ability_types": unique_strings(str(a.get("type") or "") for a in ability_rows if isinstance(a, dict)),
        }
    return out


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


def dragon_full_body_candidates(row: Optional[Mapping[str, Any]], dragon_id: Optional[int] = None) -> List[str]:
    """Resolve full-body art using the same override priority as extract_dragons.py."""
    row = dict(row or {})
    did = as_int(dragon_id if dragon_id is not None else row.get("id"), -1)
    base = STATIC_DC + "mobile/ui/dragons/"
    candidates: List[str] = []

    # 1) dragons.json already contains extract_dragons.py's resolved full-body art.
    for key in ("full_body_image", "full_body", "fullbody", "full_image"):
        value = row.get(key)
        if isinstance(value, str) and value.strip():
            normalized = normalize_image_candidate(value, dragon=True)
            if normalized:
                candidates.append(normalized)

    # 2) Read the authoritative manual override dictionaries directly from extract_dragons.py.
    if did >= 0:
        override = DCIC_DRAGON_FULL_BODY_OVERRIDES.get(did)
        if override:
            candidates.append(str(override))
        asset_override = DCIC_DRAGON_ASSET_OVERRIDES.get(did)
        if asset_override:
            slug = str(asset_override).strip().replace("\\", "/").rsplit("/", 1)[-1]
            slug = re.sub(r"^ui_", "", slug, flags=re.I)
            slug = re.sub(r"_3(?:@2x)?(?:\.png)?$", "", slug, flags=re.I)
            candidates.extend([base + "ui_" + slug + "_3@2x.png", base + "ui_" + slug + "_3.png"])

    # 3) Canonical config/compact-row asset name.
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
    if raw:
        candidates.extend([base + "ui_" + raw + "_3@2x.png", base + "ui_" + raw + "_3.png"])

    # Only full-body candidates go first; generic image_candidates remain fallback elsewhere.
    return unique_strings(candidates)


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
    perks: Optional[Mapping[int, Mapping[str, Any]]] = None,
    localization: Optional[Mapping[str, str]] = None,
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
        full_body = dragon_full_body_candidates(drow, did)
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

    if key == "seeds":
        vals = value if isinstance(value, list) else []
        first = vals[0] if vals and isinstance(vals[0], dict) else {}
        did = as_int(first.get("id"), 0)
        amount = first.get("amount")
        drow = dragons.get(str(did)) if did else None
        rarity = str((drow or {}).get("rarity") or "L")
        token = {"C":"c","R":"r","V":"vr","VR":"vr","E":"e","L":"l","M":"m","H":"h"}.get(rarity.upper(), rarity.lower())
        name = str((drow or {}).get("name") or (f"Dragon #{did}" if did else "Dragon"))
        return {
            "reward_id": rid, "type": "orbs", "dragon_id": did or None,
            "amount": amount, "rarity": rarity,
            "name": name.removesuffix(" Dragon") + " Orbs",
            "image_url": ICON_RAW + f"amount-rss/ic-amount-orbs-{token}.png",
            "popup": ({"kind":"dragon","id":did} if did else None),
        }

    if key == "rarity_seeds":
        vals = value if isinstance(value, list) else []
        first = vals[0] if vals and isinstance(vals[0], dict) else {}
        rarity = str(first.get("rarity") or "L").upper()
        amount = first.get("amount")
        token = {"C":"c","R":"r","V":"vr","VR":"vr","E":"e","L":"l","M":"m","H":"h"}.get(rarity, rarity.lower())
        rarity_name = {"C":"Common","R":"Rare","V":"Very Rare","VR":"Very Rare","E":"Epic","L":"Legendary","M":"Mythical","H":"Heroic"}.get(rarity, rarity)
        return {
            "reward_id": rid, "type": "joker_orbs", "rarity": rarity, "amount": amount,
            "name": rarity_name + " Joker Orbs",
            "image_url": ICON_RAW + f"tree-of-life/ic-joker-{token}.png",
        }

    if key == "trade_tickets":
        vals = value if isinstance(value, list) else []
        first = vals[0] if vals and isinstance(vals[0], dict) else {}
        rarity = str(first.get("rarity") or "L").upper()
        amount = first.get("amount")
        token = {"C":"c","R":"r","V":"vr","VR":"vr","E":"e","L":"l","M":"m","H":"h"}.get(rarity, rarity.lower())
        rarity_name = {"C":"Common","R":"Rare","V":"Very Rare","VR":"Very Rare","E":"Epic","L":"Legendary","M":"Mythical","H":"Heroic"}.get(rarity, rarity)
        return {
            "reward_id": rid, "type": "trade_essence", "rarity": rarity, "amount": amount,
            "name": rarity_name + " Trade Essences",
            "image_url": ICON_RAW + f"tree-of-life/ic-trade-orb-big-{token}.png",
        }

    if key == "perks":
        vals = value if isinstance(value, list) else []
        first = vals[0] if vals and isinstance(vals[0], dict) else {}
        perk_id = as_int(first.get("id"), 0)
        quantity = first.get("quantity", first.get("amount"))
        spec = dict((perks or {}).get(perk_id, {}) or {})
        loc_table = localization or {}
        name_tid = str(spec.get("name_tid") or "")
        desc_tid = str(spec.get("description_tid") or "")
        frame_file = str(spec.get("frame_file") or "")
        icon_files = [str(x) for x in (spec.get("icon_files") or []) if str(x or "").strip()]
        icon_file = icon_files[0] if icon_files else ""
        return {
            "reward_id": rid,
            "type": "perk",
            "kind": "perk",
            "asset_kind": "perk",
            "perk_id": perk_id or None,
            "amount": quantity,
            "name": loc(loc_table, name_tid, f"Perk #{perk_id}" if perk_id else "Perk"),
            "description": loc(loc_table, desc_tid, ""),
            "perk_type": str(spec.get("type") or ""),
            "perk_rarity_level": as_int(spec.get("rarity_level")),
            "perk_frame_file": frame_file,
            "perk_icon_file": icon_file,
            "perk_icon_files": icon_files,
            "perk_ability_ids": list(spec.get("ability_ids") or []),
            "perk_ability_types": list(spec.get("ability_types") or []),
            "image_url": ICON_RAW + f"perks/{frame_file}" if frame_file else "",
            "overlay_image_url": ICON_RAW + f"perks/{icon_file}" if icon_file else "",
        }

    token_resources = {
        "l_token": ("Legend Tokens", "legend"),
        "pr_token": ("Primal Tokens", "primal"),
        "pu_token": ("Pure Tokens", "pure"),
        "wr_token": ("War Tokens", "war"),
        "wd_token": ("Wind Tokens", "wind"),
        "e_token": ("Terra Tokens", "earth"),
        "f_token": ("Flame Tokens", "fire"),
        "p_token": ("Nature Tokens", "plant"),
        "w_token": ("Sea Tokens", "water"),
        "el_token": ("Electric Tokens", "electric"),
        "i_token": ("Ice Tokens", "ice"),
        "m_token": ("Metal Tokens", "metal"),
        "d_token": ("Dark Tokens", "dark"),
        "li_token": ("Light Tokens", "light"),
        "kg_token": ("Kindergarten Tokens", "kindergarten"),
    }

    resource_names = {
        "c": "Gems", "g": "Gold", "f": "Food", "keys": "Rescue Keys",
        "silver_rune": "Stone Rune", "golden_rune": "Amber Rune",
    }
    resource_icons = {
        "c": ICON_RAW + "resources/ic-gem.png",
        "g": ICON_RAW + "resources/ic-gold.png",
        "f": ICON_RAW + "resources/ic-food.png",
        "keys": ICON_RAW + "text-icons/ic-key-massive.png",
        "silver_rune": WIZARD_ASSET_RAW + "ic-rune-silver-massive.png",
        "golden_rune": WIZARD_ASSET_RAW + "ic-rune-gold-massive.png",
    }

    resource_key = str(key)
    if resource_key in token_resources:
        token_name, token_asset_key = token_resources[resource_key]
        return {
            "reward_id": rid,
            "type": "resource",
            "resource": resource_key,
            "token_asset_key": token_asset_key,
            "amount": value,
            "name": token_name,
            "image_url": ICON_RAW + f"tokens/ic-token-{token_asset_key}.png",
        }

    result = {
        "reward_id": rid,
        "type": "resource",
        "resource": resource_key,
        "amount": value,
        "name": resource_names.get(resource_key, resource_key.replace("_", " ").title()),
    }
    if resource_key in resource_icons:
        result["image_url"] = resource_icons[resource_key]
    return result


def reward_pool_rows(config: Mapping[str, Any]) -> List[Dict[str, Any]]:
    """Return the Wizards' Hollow pool table once, without duplicate heuristic matches."""
    candidates: List[Dict[str, Any]] = []
    seen_rows = set()
    for key in ("reward_pool", "reward_pools", "reward_pool_items", "pools", "pool"):
        for row in list_rows(config.get(key)):
            sig = (as_int(row.get("id"), -1), as_int(row.get("pool_id"), -1), as_int(row.get("reward_id"), -1))
            if sig not in seen_rows:
                seen_rows.add(sig); candidates.append(row)
    for key, value in config.items():
        if key in ("rewards", "stage", "cave", "ui_config", "reward_pool", "reward_pools", "reward_pool_items", "pools", "pool"):
            continue
        rows = list_rows(value)
        if rows and any("pool_id" in x and "reward_id" in x for x in rows[:10]):
            for row in rows:
                sig = (as_int(row.get("id"), -1), as_int(row.get("pool_id"), -1), as_int(row.get("reward_id"), -1))
                if sig not in seen_rows:
                    seen_rows.add(sig); candidates.append(row)
    return candidates


def pool_reward_id(config: Mapping[str, Any], pool_id: int) -> Optional[int]:
    matches = [x for x in reward_pool_rows(config) if as_int(x.get("pool_id"), -1) == pool_id and x.get("reward_id") is not None]
    if not matches:
        return None
    matches.sort(key=lambda x: as_int(x.get("id"), 10**9))
    return as_int(matches[0].get("reward_id"), -1)


def build_outcome_pool(
    pool_id: int, pool_rows: Sequence[Mapping[str, Any]], reward_by_id: Mapping[int, Mapping[str, Any]],
    dragons: Mapping[Any, Dict[str, Any]], skins: Mapping[Any, Dict[str, Any]],
    chests: Mapping[Any, Dict[str, Any]], game_config: Any,
    perks: Mapping[int, Mapping[str, Any]], localization: Mapping[str, str],
) -> Dict[str, Any]:
    rows = [x for x in pool_rows if as_int(x.get("pool_id"), -1) == pool_id and x.get("reward_id") is not None]
    rows.sort(key=lambda x: (-as_int(x.get("weight"), 0), -as_int(x.get("visual_weight"), 0), as_int(x.get("id"), 10**9)))
    outcomes: List[Dict[str, Any]] = []
    seen = set()
    for row in rows:
        rid = as_int(row.get("reward_id"), -1)
        reward = normalize_reward(
            rid, reward_by_id, dragons, skins, chests, game_config,
            perks=perks, localization=localization
        )
        if not reward:
            continue
        # A reward id is unique in the pool table; keep one normalized entry even if a malformed config duplicates it.
        if rid in seen:
            continue
        seen.add(rid)
        item = dict(reward)
        item["pool_entry_id"] = as_int(row.get("id"), 0) or None
        item["weight"] = row.get("weight")
        item["visual_weight"] = row.get("visual_weight")
        outcomes.append(item)
    return {"pool_id": pool_id, "outcome_count": len(outcomes), "rewards": outcomes}


def build_floor_layout(cave: Mapping[str, Any], stages: Mapping[int, Mapping[str, Any]]) -> List[Dict[str, Any]]:
    stage_ids = cave.get("stage_ids") if isinstance(cave.get("stage_ids"), list) else []
    floors: List[Dict[str, Any]] = []
    for index, raw_stage_id in enumerate(stage_ids, 1):
        stage_id = as_int(raw_stage_id, -1)
        stage = stages.get(stage_id, {})
        kind = str(stage.get("type") or ("final" if index == len(stage_ids) else "regular"))
        floors.append({
            "floor": index,
            "stage_id": stage_id if stage_id >= 0 else None,
            "type": kind,
            "pool_id": as_int(stage.get("pool_id"), -1) if stage else None,
            "wizards": max(0, as_int(stage.get("wizards"), 0)),
            "silver_runes": max(0, as_int(stage.get("silver_runes"), 0)),
            "silver_rune_pool_id": as_int(stage.get("silver_rune_pool_id"), -1) if stage.get("silver_rune_pool_id") is not None else None,
            "golden_runes": max(0, as_int(stage.get("golden_runes"), 0)),
            "golden_rune_pool_id": as_int(stage.get("golden_rune_pool_id"), -1) if stage.get("golden_rune_pool_id") is not None else None,
            "fixed_rewards": bool(as_int(stage.get("fixed_rewards"), 0)),
            "extra_selection_cost_ids": list(stage.get("extra_selection_cost_ids") or []) if isinstance(stage.get("extra_selection_cost_ids"), list) else [],
        })
    return floors


def find_goal_rows(config: Mapping[str, Any]) -> List[Dict[str, Any]]:
    for key in ("goal", "goals"):
        if isinstance(config.get(key), list):
            return list_rows(config.get(key))
    return []


def goal_collectible_ids(goal: Mapping[str, Any]) -> List[int]:
    for key in ("collectible_actions", "collectibles", "collectible_ids", "actions", "action_ids"):
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


def action_required_amount(action: Mapping[str, Any]) -> int:
    """Resolve the rune target from a collectible-action row across config generations."""
    for key in ("amount", "required_amount", "target", "quantity", "count", "value"):
        n = as_int(action.get(key), 0)
        if n > 0:
            return n
    return 0


def resolve_rune_goal(
    config: Mapping[str, Any], goal_id: Any, ui_reward_id: Any,
    reward_by_id: Mapping[int, Mapping[str, Any]], dragons: Mapping[Any, Dict[str, Any]],
    skins: Mapping[Any, Dict[str, Any]], chests: Mapping[Any, Dict[str, Any]], game_config: Any,
    perks: Optional[Mapping[int, Mapping[str, Any]]] = None,
    localization: Optional[Mapping[str, str]] = None,
) -> Dict[str, Any]:
    gid = as_int(goal_id, -1)
    goals = by_id(find_goal_rows(config))
    actions = by_id(list_rows(config.get("collectible_actions")))
    goal = goals.get(gid, {})
    collectible_ids = goal_collectible_ids(goal)
    required: Optional[int] = None
    action_type = ""

    for aid in collectible_ids:
        action = actions.get(aid)
        if not action:
            continue
        amount = action_required_amount(action)
        if amount > 0 and (required is None or amount > required):
            required = amount
        if action.get("type"):
            action_type = str(action.get("type"))

    # Some config generations put the target directly on the goal instead.
    if required is None:
        for key in ("required_amount", "amount", "target", "quantity", "count", "value"):
            n = as_int(goal.get(key), 0)
            if n > 0:
                required = n
                break

    # The goal row is authoritative for the reward tied to this rune target.
    # ui_config left/right are only visual-placement fallbacks.
    gr = goal_reward_id(goal)
    display_reward_id = gr if gr is not None and gr >= 0 else as_int(ui_reward_id, -1)
    reward = normalize_reward(
        display_reward_id, reward_by_id, dragons, skins, chests, game_config,
        perks=perks, localization=localization
    ) if display_reward_id >= 0 else None

    return {
        "goal_id": gid if gid >= 0 else None,
        "collectible_action_ids": collectible_ids,
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
    perks = build_perk_catalog(game_config if isinstance(game_config, dict) else {})
    missing_core_perks = [
        perk_id for perk_id in (1, 2, 3, 4)
        if not perks.get(perk_id, {}).get("frame_file")
        or not perks.get(perk_id, {}).get("icon_files")
    ]
    if missing_core_perks:
        raise SystemExit(
            "Core perk icon metadata could not be resolved: "
            + ", ".join(str(x) for x in missing_core_perks)
        )

    dragons = index_entities(load_json(Path(args.dragons), {})) if args.dragons else {}
    skins = index_entities(load_json(Path(args.skins), {})) if args.skins else {}
    chests = index_entities(load_json(Path(args.chests), {}), type_key="type") if args.chests else {}

    caves = list_rows(config.get("cave"))
    stages = by_id(list_rows(config.get("stage")))
    uis = by_id(list_rows(config.get("ui_config")))
    rewards = by_id(list_rows(config.get("rewards")))
    pool_rows = reward_pool_rows(config)

    # Normalize each reward pool only once. Hollows reference these compact catalogs by pool_id.
    used_pool_ids = set()
    for cave in caves:
        for raw_stage_id in (cave.get("stage_ids") if isinstance(cave.get("stage_ids"), list) else []):
            stage = stages.get(as_int(raw_stage_id, -1), {})
            pid = as_int(stage.get("pool_id"), -1)
            if pid >= 0:
                used_pool_ids.add(pid)
    outcome_pools = {
        str(pid): build_outcome_pool(
            pid, pool_rows, rewards, dragons, skins, chests, game_config,
            perks, localization
        )
        for pid in sorted(used_pool_ids)
    }

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
        main_reward = normalize_reward(
            main_reward_id, rewards, dragons, skins, chests, game_config,
            perks=perks, localization=localization
        ) if main_reward_id is not None else None

        goal_ids = cave.get("goal_ids") if isinstance(cave.get("goal_ids"), list) else []
        silver_goal_id = goal_ids[0] if len(goal_ids) >= 1 else None
        golden_goal_id = goal_ids[1] if len(goal_ids) >= 2 else None
        silver = resolve_rune_goal(
            config, silver_goal_id, ui.get("left_reward_id_popup"),
            rewards, dragons, skins, chests, game_config,
            perks=perks, localization=localization
        )
        golden = resolve_rune_goal(
            config, golden_goal_id, ui.get("right_reward_id_popup"),
            rewards, dragons, skins, chests, game_config,
            perks=perks, localization=localization
        )

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
                "floors": build_floor_layout(cave, stages),
            })

    # Never silently publish a '?' rune requirement again. Every configured rune goal
    # used by a Hollow must resolve to a positive collectible-action amount.
    missing_requirements = []
    for row in occurrences:
        for rune_kind in ("silver", "golden"):
            goal = (row.get("rune_rewards") or {}).get(rune_kind) or {}
            if goal.get("goal_id") is not None and as_int(goal.get("required"), 0) <= 0:
                missing_requirements.append((row.get("cave_id"), rune_kind, goal.get("goal_id"), goal.get("collectible_action_ids")))
    if missing_requirements:
        sample = ", ".join(str(x) for x in missing_requirements[:8])
        raise SystemExit("Unresolved Wizards' Hollow rune requirements: " + sample)

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
            "extractor_build": EXTRACTOR_BUILD,
            "future_days": int(args.future_days),
            "occurrence_count": len(occurrences),
            "current_cave_id": current_id,
            "next_cave_id": next_obj.get("cave_id") if next_obj else None,
            "frontend_max_cards": 10,
            "game_config_role": "build-time fallback only",
            "dragon_art_source": "dragons.json + extract_dragons.py full-body overrides",
            "floor_outcomes": True,
            "outcome_pool_count": len(outcome_pools),
            "reward_pool_entry_count": len(pool_rows),
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
            "wizard_outcome": WIZARD_ASSET_RAW + "gr-emoji-smile.png",
        },
        "outcome_pools": outcome_pools,
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
