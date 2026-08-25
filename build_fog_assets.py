#!/usr/bin/env python3
from __future__ import annotations

import base64
import json
import mimetypes
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List

ROOT = Path(__file__).resolve().parent
FOG_JSON = ROOT / "fog_island.json"
OUT_JSON = ROOT / "fog_assets.json"
UA = "Mozilla/5.0 DCIC-Fog-Asset-Builder/2.0"
STATIC_BASE = "https://dci-static-s1.socialpointgames.com/static/dragoncity/"
CHEST_BASE = STATIC_BASE + "mobile/ui/chests/"
DRAGON_BASE = STATIC_BASE + "mobile/ui/dragons/"


def load_json(path: Path):
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def unique(values: Iterable[str]) -> List[str]:
    out: List[str] = []
    seen = set()
    for value in values:
        value = str(value or "").strip()
        if value and value not in seen:
            seen.add(value)
            out.append(value)
    return out


def choose_island(islands):
    now = int(datetime.now(timezone.utc).timestamp())
    valid = [i for i in islands if int(i.get("start_ts", 0)) > 0 and int(i.get("end_ts", 0)) > int(i.get("start_ts", 0))]
    current = sorted([i for i in valid if int(i["start_ts"]) <= now < int(i["end_ts"])], key=lambda x: int(x["end_ts"]))
    if current:
        return current[0]
    upcoming = sorted([i for i in valid if int(i["start_ts"]) > now], key=lambda x: int(x["start_ts"]))
    if upcoming:
        return upcoming[0]
    return sorted(valid, key=lambda x: int(x["end_ts"]), reverse=True)[0] if valid else None


def asset_key(row: Dict[str, Any]) -> str:
    kind = str(row.get("asset_kind") or row.get("kind") or "").lower()
    if kind in {"dragon", "dragon_piece"}:
        value = row.get("dragon_id") or row.get("id")
        return f"dragon:{value}" if value else ""
    if kind in {"decoration", "building", "item"}:
        value = row.get("item_id") or row.get("id")
        return f"item:{value}" if value else ""
    if kind == "chest" or row.get("source_chest_id"):
        value = row.get("source_chest_id") or row.get("id")
        return f"chest:{value}" if value else ""
    return ""


def clean_asset_name(value: Any) -> str:
    raw = str(value or "").strip()
    raw = raw.removeprefix("ui_")
    if raw.lower().endswith("@2x.png"):
        raw = raw[:-7]
    elif raw.lower().endswith("@2x"):
        raw = raw[:-3]
    elif raw.lower().endswith(".png"):
        raw = raw[:-4]
    return raw


def dragon_candidates(row: Dict[str, Any]) -> List[str]:
    raw = clean_asset_name(row.get("img_name_mobile") or row.get("img_name"))
    if not raw:
        return []
    return unique([
        DRAGON_BASE + "HD/thumb_" + raw + "_3.png",
        DRAGON_BASE + "ui_" + raw + "_3@2x.png",
        DRAGON_BASE + "ui_" + raw + "_3.png",
    ])


def chest_candidates(row: Dict[str, Any]) -> List[str]:
    raw = clean_asset_name(row.get("source_chest_img_name") or row.get("img_name"))
    if not raw:
        return []
    chest_id = int(row.get("source_chest_id") or row.get("id") or 0)
    after_chest = raw[6:] if raw.lower().startswith("chest_") else raw
    after_basic = raw
    if after_basic.lower().startswith("basic_chest_"):
        after_basic = after_basic[12:]
    if after_basic.lower().startswith("chest_"):
        after_basic = after_basic[6:]
    return unique([
        CHEST_BASE + f"ui_{chest_id}_{raw}@2x.png" if chest_id else "",
        CHEST_BASE + f"ui_{chest_id}_{raw}.png" if chest_id else "",
        CHEST_BASE + "ui_" + raw + "@2x.png",
        CHEST_BASE + "ui_" + raw + ".png",
        CHEST_BASE + raw + ".png",
        CHEST_BASE + "ui_basic_chest_" + raw + "@2x.png",
        CHEST_BASE + "ui_" + after_chest + "@2x.png",
        CHEST_BASE + "ui_basic_chest_" + after_chest + "@2x.png",
        CHEST_BASE + "ui_" + after_basic + "@2x.png",
        CHEST_BASE + "ui_basic_chest_" + after_basic + "@2x.png",
    ])


def decoration_candidates(row: Dict[str, Any]) -> List[str]:
    raw = clean_asset_name(row.get("img_name_mobile") or row.get("img_name"))
    if not raw:
        return []
    return unique([
        STATIC_BASE + "mobile/ui/decorations/ui_" + raw + "@2x.png",
        STATIC_BASE + "mobile/ui/decorations/" + raw + "@2x.png",
        STATIC_BASE + "mobile/ui/decorations/" + raw + ".png",
        STATIC_BASE + "mobile/ui/decorations/HD/" + raw + ".png",
        STATIC_BASE + "mobile/ui/buildings/ui_" + raw + "@2x.png",
        STATIC_BASE + "mobile/ui/buildings/" + raw + "@2x.png",
        STATIC_BASE + "mobile/ui/buildings/" + raw + ".png",
        STATIC_BASE + "mobile/ui/buildings/HD/" + raw + ".png",
    ])


def row_candidates(row: Dict[str, Any]) -> List[str]:
    values: List[str] = []
    if isinstance(row.get("image_candidates"), list):
        values.extend(str(v) for v in row["image_candidates"])
    if row.get("image_url"):
        values.append(str(row["image_url"]))

    kind = str(row.get("asset_kind") or row.get("kind") or "").lower()
    if kind in {"decoration", "building", "item"} or row.get("item_id"):
        values.extend(decoration_candidates(row))
        # Historical event-item wrappers may store their icon in chests/.
        values.extend(chest_candidates(row))
    elif kind in {"dragon", "dragon_piece"} or row.get("img_name_mobile") or row.get("dragon_id"):
        values.extend(dragon_candidates(row))
    elif kind == "chest" or row.get("source_chest_id") or row.get("img_name"):
        values.extend(chest_candidates(row))
    return unique(values)


def download_as_data_url(urls: List[str]):
    for url in urls:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=25) as r:
                if getattr(r, "status", 200) != 200:
                    continue
                data = r.read()
                if not data:
                    continue
                ctype = r.headers.get_content_type() or mimetypes.guess_type(url)[0] or "image/png"
                return f"data:{ctype};base64," + base64.b64encode(data).decode("ascii"), url
        except Exception as exc:
            print("candidate failed:", url, "-", exc)
    return "", ""


def main():
    payload = load_json(FOG_JSON)
    island = choose_island(payload.get("islands", []))
    if not island:
        raise SystemExit("No Fog Island with a valid schedule found.")

    jobs: Dict[str, List[str]] = {}

    summary = island.get("rewards_summary") or {}
    for row in list(summary.get("dragons") or []) + list(summary.get("event_items") or []):
        if not isinstance(row, dict):
            continue
        key = asset_key(row)
        urls = row_candidates(row)
        if key and urls:
            jobs[key] = urls

    # Map-only chests/items may not be in Rewards Summary (e.g. generic Fog chests).
    for square in island.get("squares", []):
        reward = square.get("reward") or {}
        if not isinstance(reward, dict):
            continue
        key = asset_key(reward)
        urls = row_candidates(reward)
        if key and urls and key not in jobs:
            jobs[key] = urls

    assets = {}
    resolved = {}
    failed = []

    for key, urls in sorted(jobs.items()):
        data_url, resolved_url = download_as_data_url(urls)
        if data_url:
            assets[key] = data_url
            resolved[key] = resolved_url
            print("cached", key, "from", resolved_url)
        else:
            failed.append({"key": key, "candidates": urls})
            print("FAILED", key)

    out = {
        "schema_version": 2,
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "island_id": island.get("id"),
        "island_name": island.get("name"),
        "asset_count": len(assets),
        "assets": assets,
        "resolved_urls": resolved,
        "failed": failed,
    }

    with OUT_JSON.open("w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
        f.write("\n")

    print(f"Wrote {OUT_JSON.name}: {len(assets)} asset(s), {len(failed)} failed")


if __name__ == "__main__":
    main()
