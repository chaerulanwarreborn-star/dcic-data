#!/usr/bin/env python3
from __future__ import annotations

import base64
import json
import mimetypes
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List

ROOT = Path(__file__).resolve().parent
FOG_JSON = ROOT / "fog_island.json"
OUT_JSON = ROOT / "fog_assets.json"
UA = "Mozilla/5.0 DCIC-Fog-Asset-Builder/1.0"


def load_json(path: Path):
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def choose_island(islands):
    now = int(datetime.now(timezone.utc).timestamp())
    valid = [i for i in islands if int(i.get("start_ts",0)) > 0 and int(i.get("end_ts",0)) > int(i.get("start_ts",0))]
    current = sorted([i for i in valid if int(i["start_ts"]) <= now < int(i["end_ts"])], key=lambda x:int(x["end_ts"]))
    if current:
        return current[0]
    upcoming = sorted([i for i in valid if int(i["start_ts"]) > now], key=lambda x:int(x["start_ts"]))
    if upcoming:
        return upcoming[0]
    return sorted(valid, key=lambda x:int(x["end_ts"]), reverse=True)[0] if valid else None


def chest_candidates(img_name: str) -> List[str]:
    base = "https://dci-static-s1.socialpointgames.com/static/dragoncity/mobile/ui/chests/"
    raw = (img_name or "").strip()
    if not raw:
        return []

    clean = raw
    if clean.lower().startswith("ui_"):
        clean = clean[3:]
    if clean.lower().endswith("@2x"):
        clean = clean[:-3]
    if clean.lower().endswith(".png"):
        clean = clean[:-4]

    after_chest = clean[6:] if clean.lower().startswith("chest_") else clean
    after_basic = clean
    if after_basic.lower().startswith("basic_chest_"):
        after_basic = after_basic[12:]
    if after_basic.lower().startswith("chest_"):
        after_basic = after_basic[6:]

    urls = []
    def add(u):
        if u and u not in urls:
            urls.append(u)

    add(base + raw)
    add(base + "ui_" + clean + "@2x.png")
    add(base + "ui_basic_chest_" + clean + "@2x.png")
    add(base + "ui_" + after_chest + "@2x.png")
    add(base + "ui_basic_chest_" + after_chest + "@2x.png")
    add(base + "ui_" + after_basic + "@2x.png")
    add(base + "ui_basic_chest_" + after_basic + "@2x.png")
    return urls


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

    for dragon in island.get("rewards_summary", {}).get("dragons", []):
        dragon_id = int(dragon.get("id",0))
        if dragon_id and dragon.get("image_url"):
            jobs[f"dragon:{dragon_id}"] = [dragon["image_url"]]

    for sq in island.get("squares", []):
        reward = sq.get("reward") or {}
        if reward.get("kind") != "chest":
            continue
        chest_id = int(reward.get("id",0))
        if chest_id and f"chest:{chest_id}" not in jobs:
            jobs[f"chest:{chest_id}"] = chest_candidates(str(reward.get("img_name") or ""))

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
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00","Z"),
        "island_id": island.get("id"),
        "island_name": island.get("name"),
        "asset_count": len(assets),
        "assets": assets,
        "resolved_urls": resolved,
        "failed": failed,
    }

    with OUT_JSON.open("w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",",":"))
        f.write("\n")

    print(f"Wrote {OUT_JSON.name}: {len(assets)} asset(s), {len(failed)} failed")


if __name__ == "__main__":
    main()
