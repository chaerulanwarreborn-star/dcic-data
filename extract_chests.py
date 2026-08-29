#!/usr/bin/env python3
"""Build chest archive datasets for Dragon City Information Center.

Sources:
- game_config.json / chests.chests              -> Generic Chests
- game_config.json / alliance_chest.chests      -> Alliance Chests
- arena_config.json / warrior_chests             -> Arena Warrior's Chests

Outputs:
- chests.json          compact browse/search/filter index
- chest-details/<type>/<bucket>.json deterministic lazy reward-detail buckets used by the global popup

Source IDs are preserved. Because IDs collide between namespaces, every record
also carries a stable `key` (`generic:2`, `alliance:2`, `warrior:102`).

Detail files use fixed ID buckets (`chest_id % bucket_count`) rather than config
position, so adding a new chest never moves older chests between files. Existing
archive records that disappear from a later config are retained; same-ID content
is simply updated in place (no revision history).
"""
from __future__ import annotations

import json
import re
from fnmatch import fnmatchcase
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "game_config.json"
ARENA_PATH = ROOT / "arena_config.json"
LOC_PATH = ROOT / "localization" / "dragon_city_localization_baseline_en.json"
DRAGONS_PATH = ROOT / "dragons.json"
SKINS_PATH = ROOT / "skins.json"
SUMMARY_PATH = ROOT / "chests.json"
DETAIL_DIR = ROOT / "chest-details"
DETAIL_BUCKET_COUNTS = {"generic": 64, "alliance": 16, "warrior": 32}

STATIC = "https://dci-static-s1.socialpointgames.com/static/dragoncity/"
ICON = "https://raw.githubusercontent.com/chaerulanwarreborn-star/dcic-assets/main/icons/"
MISSING_CHEST = "https://raw.githubusercontent.com/chaerulanwarreborn-star/dcic-assets/main/override/ui_000_chest_diagram%402x.png"

RARITY_NAMES = {"C":"Common","R":"Rare","VR":"Very Rare","V":"Very Rare","E":"Epic","L":"Legendary","M":"Mythical","H":"Heroic"}
RARITY_FILE = {"C":"c","R":"r","VR":"vr","V":"vr","E":"e","L":"l","M":"m","H":"h"}
TOKEN_MAP = {
    "e_token":("earth","Terra Tokens"), "f_token":("fire","Flame Tokens"), "w_token":("water","Sea Tokens"),
    "p_token":("plant","Nature Tokens"), "el_token":("electric","Electric Tokens"), "i_token":("ice","Ice Tokens"),
    "m_token":("metal","Metal Tokens"), "d_token":("dark","Dark Tokens"), "li_token":("light","Light Tokens"),
    "wr_token":("war","War Tokens"), "pu_token":("pure","Pure Tokens"), "l_token":("legend","Legend Tokens"),
    "pr_token":("primal","Primal Tokens"), "wd_token":("wind","Wind Tokens"),
}
SPECIAL_TOKEN_MAP = {
    "n_token":("neutral","Rainbow Tokens"),
    "kg_token":("kindergarten","Kindergarten Tokens"),
    "oph_token":("oph","Divine Tokens"),
}
RESOURCE_INFO = {
    "g":("gold","Gold",ICON+"resources/ic-gold.png"),
    "f":("food","Food",ICON+"resources/ic-food.png"),
    "c":("gems","Gems",ICON+"resources/ic-gem.png"),
    "x":("xp","XP",ICON+"resources/ic-experience-xp.png"),
    "ep":("event_coin","Event Coins",ICON+"currency-icon/coin-mix.png"),
    "moves":("puzzle_move","Puzzle Moves",ICON+"currency-icon/coin-puzzle.png"),
    "en_runner":("flight_stamp","Flight Stamps",ICON+"currency-icon/coin-runner.png"),
    "gacha_event_tickets":("hollow_ticket","Hollow Tickets",ICON+"currency-icon/ic_ic_hollow_crown_massive.png"),
}
RANK_FILE = {"common":"common","rare":"rare","very_rare":"veryrare","veryrare":"veryrare","epic":"epic","legendary":"legendary","mythical":"mythical","heroic":"heroic"}
STICKER_PACK_FILES = {
    "s":"ic_stickers_pack_s_massive.png","m":"ic_stickers_pack_m_massive.png","l":"ic_stickers_pack_l_massive.png","xl":"ic_stickers_pack_xl_massive.png",
    "ace_1":"ic_stickers_pack_ace_1_massive.png","ace_2":"ic_stickers_pack_ace_2_massive.png","ace_3":"ic_stickers_pack_ace_3_massive.png",
    "ace_4":"ic_stickers_pack_ace_4_massive.png","ace_5":"ic_stickers_pack_ace_5_massive.png","ace_generic":"ic_stickers_pack_ace_generic_massive.png",
}
BATTLEGROUND_KEY_FALLBACKS = {
    # BG1-3 artwork is no longer available. Use the closest surviving BG4
    # equivalent for the known historical colors/shapes. BG3 was reconstructed
    # from Dragon Rescue footage dated 21 Feb 2019.
    (1, 3):(4, 1),   # yellow small
    (1, 4):(4, 3),   # blue/cyan small
    (2, 1):(4, 1),   # yellow small
    (2, 2):(4, 3),   # blue/cyan small
    (2, 3):(4, 2),   # red small
    (3, 1):(4,10),   # green small
    (3, 2):(4, 1),   # yellow small
    (3, 3):(4, 6),   # blue/cyan big
    (3, 4):(4, 2),   # red small
    (3, 5):(4, 5),   # red big
}

def battleground_key_icon(bg_id: int, key_id: int) -> Tuple[str,List[str],Optional[Tuple[int,int]]]:
    """Return the archive icon for a legacy battleground key.

    BG4+ assets are preserved in dcic-assets. BG1-3 were removed from the
    original game CDN, so known keys use a visually-equivalent BG4 fallback.
    """
    direct=ICON+f"battleground-keys/battleground_{bg_id}_key_{key_id}.png"
    fallback_ref=BATTLEGROUND_KEY_FALLBACKS.get((bg_id,key_id))
    if bg_id>=4:
        return direct,uniq([direct,ICON+"text-icons/ic-key-massive.png"]),None
    if fallback_ref:
        fbg,fkey=fallback_ref
        fallback=ICON+f"battleground-keys/battleground_{fbg}_key_{fkey}.png"
        return fallback,uniq([fallback,ICON+"text-icons/ic-key-massive.png"]),fallback_ref
    return ICON+"text-icons/ic-key-massive.png",[ICON+"text-icons/ic-key-massive.png"],None

STICKER_THEME_FILES = {
    "sweet-surprise":"ic_stickers_pack_sweetsurprise_massive.png",
    "groovefest":"ic_stickers_pack_groovefest_massive.png",
    "liberation":"ic_stickers_pack_liberation_massive.png",
    "plungersprize":"ic_stickers_pack_plungersprize_massive.png",
    "saintvalentine":"ic_stickers_pack_saintvalentine_massive.png",
    "temporaryalbum":"ic_stickers_pack_temporaryalbum_massive.png",
    "temporaryblackfriday":"ic_stickers_pack_temporaryblackfriday_massive.png",
    "temporarynewyear":"ic_stickers_pack_temporarynewyear_massive.png",
}
REWARD_TYPE_ICONS = {
    "gold":ICON+"resources/ic-gold.png","food":ICON+"resources/ic-food.png","gems":ICON+"resources/ic-gem.png","xp":ICON+"resources/ic-experience-xp.png",
    "dragon_egg":ICON+"text-icons/egg.png","empowered_dragon_egg":ICON+"text-icons/gr-enable-star.png","dragon_orbs":ICON+"text-icons/ic-hud-orb-shop.png","skin":ICON+"text-icons/ic-dragon-skin-badge.png",
    "joker_orbs":ICON+"tree-of-life/ic-joker-all.png","trade_essence":ICON+"tree-of-life/ic-trade-orb-mid-generic.png",
    "building":ICON+"text-icons/gr-category-buildings.png","habitat":ICON+"text-icons/gr-category-habitats.png","decoration":ICON+"text-icons/gr-category-decos.png",
    "elemental_token":ICON+"tokens/gr-category-tokens.png","special_token":ICON+"tokens/ic-token-neutral.png","perk":ICON+"perks/ic-combat-perk.png","rank_up_coin":ICON+"rank-up-coins/ic-rank-up-coin-common.png",
    "event_coin":ICON+"currency-icon/coin-mix.png","hollow_ticket":ICON+"currency-icon/ic_ic_hollow_crown_massive.png","puzzle_move":ICON+"currency-icon/coin-puzzle.png","flight_stamp":ICON+"currency-icon/coin-runner.png","keys":ICON+"text-icons/ic-key-massive.png","old_rescue_keys":ICON+"battleground-keys/battleground_12_key_1.png","dragon_rescue_keys":ICON+"battleground-keys/battleground_12_key_1.png","power_tags":ICON+"battleground-keys/battleground_8_key_1.png",
    "pet_food":ICON+"currency-icon/ic-pet-food-massive_c.png","progression_pass_tier":ICON+"currency-icon/ic-dmp-point-massive.png","treasure_key":ICON+"currency-icon/gachakey_gold_silver_mds.png",
    "sticker_pack":ICON+"stickers/ic_stickers_pack_ace_generic_massive.png","missing_sticker":ICON+"stickers/sticker-not-owned-rarity-1.png","sticker_diamond":ICON+"stickers/ic-album-dust-massive_c.png",
    "chest":ICON+"text-icons/gold-chest.png","other":"",
}


def load(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f: return json.load(f)

def dump(path: Path, data: Any) -> None:
    with path.open("w", encoding="utf-8") as f: json.dump(data, f, ensure_ascii=False, separators=(",", ":"))

def i(v: Any) -> int:
    try: return int(v)
    except (TypeError, ValueError): return 0

def fnum(v: Any, default: float=0.0) -> float:
    try: return float(v)
    except (TypeError, ValueError): return default

def normalize_tier_multiplier(v: Any) -> float:
    """Normalize SP's two tier-multiplier encodings to a normal float.

    Older content commonly stores fixed-point values such as 1400000 (=1.4x),
    while newer gatcha rewards may store 1.4 directly. A zero override behaves
    like no scaling and is normalized to 1.0.
    """
    n=fnum(v,1.0)
    if n<=0: return 1.0
    if abs(n)>=100000: n/=1000000.0
    return n

def is_scaled_multiplier(v: Any) -> bool:
    return abs(normalize_tier_multiplier(v)-1.0)>1e-9

def uniq(values: Iterable[Any]) -> List[Any]:
    out=[]; seen=set()
    for v in values:
        marker=json.dumps(v,sort_keys=True,ensure_ascii=False) if isinstance(v,(dict,list)) else str(v)
        if v is not None and marker not in seen: seen.add(marker); out.append(v)
    return out

def normalize_loc(raw: Any) -> Dict[str,str]:
    if isinstance(raw,dict): return {str(k):str(v) for k,v in raw.items() if v is not None}
    out={}
    for row in raw if isinstance(raw,list) else []:
        if isinstance(row,dict):
            for k,v in row.items():
                if v is not None: out[str(k)]=str(v)
    return out

def loc(locmap: Dict[str,str], key: Any, fallback: str="") -> str:
    return str(locmap.get(str(key or ""),"") or fallback).strip()

def iso(ts: Any) -> str:
    n=i(ts)
    return datetime.fromtimestamp(n,timezone.utc).isoformat().replace("+00:00","Z") if n>0 else ""

def remote_url(value: Any) -> str:
    if isinstance(value,dict): value=value.get("remote") or value.get("url") or ""
    s=str(value or "").strip()
    if not s: return ""
    s=s.replace("$HDSD","HD")
    if s.startswith("http://") or s.startswith("https://"): return s
    return STATIC+s.lstrip("/")

def chest_candidates(chest_id: int, img_name: str) -> List[str]:
    """Resolve chest artwork across old/modern naming conventions."""
    raw=str(img_name or "").strip().replace("\\","/").rsplit("/",1)[-1]
    if not raw: return [MISSING_CHEST]
    raw=re.sub(r"\.png$","",raw,flags=re.I); raw=re.sub(r"@2x$","",raw,flags=re.I)
    bare=raw
    if bare.lower().startswith("ui_basic_"):
        bare=re.sub(r"^ui_basic_","",bare,flags=re.I)
    elif bare.lower().startswith("ui_"):
        bare=re.sub(r"^ui_","",bare,flags=re.I)

    # Known source names whose shipped artwork uses another canonical filename.
    bare=re.sub(r"^106_halloween_chest_[bc]$","106_halloween_chest",bare,flags=re.I)
    if bare.lower()=="290_chest_abyss_bag":
        bare="275_chest_bones_bag"
    m=re.match(r"^pet_food_chest_(s|m|l|xl)$",bare,flags=re.I)
    if m:
        bare="chest_pet_food_"+m.group(1).lower()

    candidates=[]
    if raw.lower().startswith(("ui_basic_","ui_")):
        candidates.append(STATIC+f"mobile/ui/chests/{raw}@2x.png")
    if bare.lower().startswith("alliancechest_"):
        candidates.extend([
            STATIC+f"mobile/ui/chests/ui_{bare}@2x.png",
            STATIC+f"mobile/ui/chests/ui_basic_{bare}@2x.png",
        ])
    else:
        candidates.extend([
            STATIC+f"mobile/ui/chests/ui_basic_{bare}@2x.png",
            STATIC+f"mobile/ui/chests/ui_{bare}@2x.png",
        ])
    candidates.extend([
        STATIC+f"mobile/ui/chests/{bare}@2x.png",
        STATIC+f"mobile/ui/chests/{bare}.png",
        MISSING_CHEST,
    ])
    return uniq(candidates)


def item_candidates(item: Dict[str,Any]) -> List[str]:
    raw=str(item.get("img_name_mobile") or item.get("img_name") or "").strip()
    if not raw: return []
    group=str(item.get("group_type") or "").upper()
    habitat=[
        STATIC+f"mobile/ui/habitats/ui_{raw}@2x.png", STATIC+f"mobile/ui/habitats/{raw}@2x.png",
        STATIC+f"mobile/ui/habitats/{raw}.png", STATIC+f"mobile/ui/habitats/HD/{raw}.png",
    ] if group in {"HABITAT","ORB_HABITAT"} else []
    return uniq(habitat+[
        STATIC+f"mobile/ui/decorations/ui_{raw}@2x.png", STATIC+f"mobile/ui/decorations/{raw}@2x.png",
        STATIC+f"mobile/ui/decorations/{raw}.png", STATIC+f"mobile/ui/decorations/HD/{raw}.png",
        STATIC+f"mobile/ui/buildings/ui_{raw}@2x.png", STATIC+f"mobile/ui/buildings/{raw}@2x.png",
        STATIC+f"mobile/ui/buildings/{raw}.png", STATIC+f"mobile/ui/buildings/HD/{raw}.png",
    ])

def slug_name(value: str) -> str:
    return re.sub(r"\s+"," ",str(value or "").strip())

class Context:
    def __init__(self,cfg:Dict[str,Any],arena:Dict[str,Any],locmap:Dict[str,str],dragons:Any,skins:Any):
        self.cfg=cfg; self.arena=arena; self.loc=locmap
        drows=(dragons.get("dragons") if isinstance(dragons,dict) else dragons) or []
        srows=(skins.get("skins") if isinstance(skins,dict) else skins) or []
        self.dragons={i(x.get("id")):x for x in drows if isinstance(x,dict)}
        self.skins={i(x.get("id")):x for x in srows if isinstance(x,dict)}
        self.items={i(x.get("id")):x for x in cfg.get("items",[]) if isinstance(x,dict)}
        self.chests={i(x.get("id")):x for x in (cfg.get("chests") or {}).get("chests",[]) if isinstance(x,dict)}
        self.perks={i(x.get("id")):x for x in (cfg.get("perks") or {}).get("perks",[]) if isinstance(x,dict)}
        self.abilities={i(x.get("id")):x for x in (cfg.get("perks") or {}).get("abilities",[]) if isinstance(x,dict)}
        self.eco_defs={str(x.get("id")):x for x in (cfg.get("economy_system") or {}).get("definitions",[]) if isinstance(x,dict)}
        self.eco_icons={str(x.get("id")):x for x in (cfg.get("economy_system") or {}).get("visual_icon",[]) if isinstance(x,dict)}
        self.gspec={i(x.get("id")):x for x in (cfg.get("gatcha") or {}).get("gatchas",[]) if isinstance(x,dict)}
        self.grandom=defaultdict(list); self.gstatic=defaultdict(list)
        for x in (cfg.get("gatcha") or {}).get("random_rewards",[]): self.grandom[i(x.get("gatcha_id"))].append(x)
        for x in (cfg.get("gatcha") or {}).get("static_rewards",[]): self.gstatic[i(x.get("gatcha_id"))].append(x)

    def dragon(self,did:int)->Dict[str,Any]:
        d=self.dragons.get(did,{})
        name=str(d.get("name") or loc(self.loc,f"tid_unit_{did}_name",f"Dragon {did}"))
        rarity=str(d.get("rarity") or "").upper()
        images=(d.get("details") or {}).get("images") or {}
        baby=str(images.get("baby") or d.get("full_body_image") or "")
        adult=str(d.get("adult_image") or "")
        return {"id":did,"name":name,"rarity":rarity,"baby_image":baby,"adult_image":adult,"img_name_mobile":str(d.get("adult_asset") or "")}

    def visual_icon(self,key:str,variant:str="regular")->str:
        # Prefer the exact economy-system entry. If SP only ships a wildcard
        # family definition (for example temporary_sticker_set_pass_unlock.*),
        # use it as a future-proof fallback instead of leaving the reward blank.
        row=self.eco_icons.get(key)
        if not row:
            for pattern,candidate in self.eco_icons.items():
                if "*" in pattern and fnmatchcase(key,pattern):
                    row=candidate
                    break
        row=row or {}
        return remote_url(row.get(variant) or row.get("massive") or row.get("regular") or "")

    def item(self,item_id:int)->Dict[str,Any]:
        row=self.items.get(item_id,{})
        name=loc(self.loc,f"tid_building_{item_id}_name",str(row.get("name") or f"Item {item_id}"))
        desc=loc(self.loc,f"tid_building_{item_id}_description",str(row.get("description") or ""))
        return {"id":item_id,"name":name,"description":desc,"group_type":str(row.get("group_type") or "").upper(),"image_candidates":item_candidates(row)}

    def reward_component(self,key:str,value:Any)->List[Dict[str,Any]]:
        out=[]
        # Main/simple resources.
        if key=="keys":
            out.append({"type":"keys","raw_type":key,"name":loc(self.loc,"tid_key_resource","Keys"),"amount":i(value),"image":ICON+"text-icons/ic-key-massive.png"})
            return out
        if key in RESOURCE_INFO:
            typ,name,img=RESOURCE_INFO[key]
            out.append({"type":typ,"raw_type":key,"name":name,"amount":i(value),"image":img})
            return out
        if key=="egg":
            d=self.dragon(i(value)); out.append({"type":"dragon_egg","raw_type":key,"name":d["name"],"amount":1,"dragon_id":d["id"],"rarity":d["rarity"],"image":d["baby_image"],"open":{"kind":"dragon","id":d["id"]}}); return out
        if key=="seggs" and isinstance(value,list):
            for x in value:
                if not isinstance(x,dict): continue
                d=self.dragon(i(x.get("id"))); grade=i(x.get("grade")); level=x.get("level")
                out.append({"type":"empowered_dragon_egg","raw_type":key,"name":d["name"],"amount":i(x.get("amount")) or 1,"dragon_id":d["id"],"rarity":d["rarity"],"empowerment":grade,"rank":i(x.get("rank")),"level":i(level) if level is not None else None,"image":d["baby_image"],"open":{"kind":"dragon","id":d["id"]}})
            return out
        if key=="seeds" and isinstance(value,list):
            for x in value:
                if not isinstance(x,dict): continue
                d=self.dragon(i(x.get("id"))); token=RARITY_FILE.get(d["rarity"],d["rarity"].lower())
                orb_base=re.sub(r"\s+Dragon$","",d["name"],flags=re.I); out.append({"type":"dragon_orbs","raw_type":key,"name":orb_base+" Orbs","amount":i(x.get("amount")),"dragon_id":d["id"],"rarity":d["rarity"],"image":d["adult_image"],"mini_icon":ICON+f"tree-of-life/ic-seed-{token}-mid-shadow.png" if token else "","old_mini_icon":ICON+"tree-of-life/ic-seed-h-old.png" if token=="h" else "","open":{"kind":"dragon","id":d["id"]}})
            return out
        if key=="rarity_seeds" and isinstance(value,list):
            for x in value:
                r=str(x.get("rarity") or "").upper(); token=RARITY_FILE.get(r,r.lower())
                out.append({"type":"joker_orbs","raw_type":key,"name":RARITY_NAMES.get(r,r)+" Joker Orbs","amount":i(x.get("amount")),"rarity":r,"image":ICON+f"tree-of-life/ic-joker-{token}.png"})
            return out
        if key=="trade_tickets" and isinstance(value,list):
            for x in value:
                r=str(x.get("rarity") or "").upper(); token=RARITY_FILE.get(r,r.lower())
                out.append({"type":"trade_essence","raw_type":key,"name":RARITY_NAMES.get(r,r)+" Trade Essences","amount":i(x.get("amount")),"rarity":r,"image":ICON+f"tree-of-life/ic-trade-orb-big-{token}.png","old_image":ICON+f"tree-of-life/ic-trade-orb-big-{token}-old.png" if token in {"l","h"} else ""})
            return out
        if key=="skin":
            sid=i(value); s=self.skins.get(sid,{})
            name=str(s.get("name") or loc(self.loc,f"tid_skin_{sid}_name",f"Dragon Skin {sid}"))
            out.append({"type":"skin","raw_type":key,"name":name,"amount":1,"skin_id":sid,"dragon_id":i(s.get("owner_id")),"image":str(s.get("thumbnail") or s.get("image") or ""),"mini_icon":ICON+"text-icons/ic-dragon-skin-badge.png","open":{"kind":"skin","id":sid}}); return out
        if key=="perks" and isinstance(value,list):
            for x in value:
                if not isinstance(x,dict): continue
                pid=i(x.get("id")); p=self.perks.get(pid,{})
                name=loc(self.loc,p.get("name_tid"),f"Perk {pid}")
                abilities=[self.abilities.get(i(a),{}) for a in (p.get("abilities") or [])]
                overlays=[]
                for a in abilities:
                    file=str(((a.get("asset") or {}).get("remote") or "")).replace("\\","/").rsplit("/",1)[-1]
                    if file: overlays.append(ICON+"perks/"+file)
                frame=str(((p.get("asset") or {}).get("remote") or "")).replace("\\","/").rsplit("/",1)[-1]
                out.append({"type":"perk","raw_type":key,"name":name,"amount":i(x.get("quantity")) or 1,"perk_id":pid,"perk_type":str(p.get("type") or ""),"perk_rarity_level":i(p.get("rarity_level")),"image":ICON+"perks/"+frame if frame else "","mini_icon":overlays[0] if overlays else "","mini_icons":overlays})
            return out
        if key.startswith("rank_up_coin."):
            rarity=key.split(".",1)[1].lower(); fname=RANK_FILE.get(rarity,rarity); name=loc(self.loc,(self.eco_defs.get(key) or {}).get("tid_name"),fname.replace("_"," ").title()+" Rank Up Coin")
            img=ICON+f"rank-up-coins/ic-rank-up-coin-{fname}.png"; out.append({"type":"rank_up_coin","raw_type":key,"name":name,"amount":i(value),"rarity":rarity,"image":img,"image_candidates":uniq([img,self.visual_icon(key)])}); return out
        if key in TOKEN_MAP:
            token,label=TOKEN_MAP[key]; out.append({"type":"elemental_token","raw_type":key,"name":label,"amount":i(value),"token":token,"image":ICON+f"tokens/ic-token-{token}.png","old_image":ICON+f"tokens/ic-token-{token}-0.png"}); return out
        if key in SPECIAL_TOKEN_MAP:
            token,label=SPECIAL_TOKEN_MAP[key]; out.append({"type":"special_token","raw_type":key,"name":label,"amount":i(value),"token":token,"image":ICON+f"tokens/ic-token-{token}.png"}); return out
        if key=="battleground_keys" and isinstance(value,list):
            for x in value:
                if not isinstance(x,dict):
                    continue
                bg_id=i(x.get("battleground_id")); key_id=i(x.get("key_id"))
                image,image_candidates,fallback_ref=battleground_key_icon(bg_id,key_id)
                is_power_tag=(bg_id==8)
                row={
                    "type":"old_rescue_keys",
                    "raw_type":key,
                    "name":"Power Tags" if is_power_tag else loc(self.loc,"tid_battleground_keys","Dragon Rescue Keys"),
                    "amount":i(x.get("amount")) or 1,
                    "battleground_id":bg_id,
                    "key_id":key_id,
                    "image":image,
                    "image_candidates":image_candidates,
                }
                if fallback_ref:
                    row["reconstructed_icon_from"]={"battleground_id":fallback_ref[0],"key_id":fallback_ref[1]}
                out.append(row)
            return out
        if key=="pet_food":
            out.append({"type":"pet_food","raw_type":key,"name":"Pet Food","amount":i(value),"image":ICON+"currency-icon/ic-pet-food-massive_c.png"}); return out
        if key.startswith("pet_food_pack."):
            size=key.split(".",1)[1].lower(); img=ICON+f"pet-food/ui_chest_pet_food_{size}.png"; out.append({"type":"pet_food","raw_type":key,"name":size.upper()+" Pet Food Pack","amount":i(value),"subtype":size,"image":img,"image_candidates":uniq([img,self.visual_icon(key,"massive")])}); return out
        if key.startswith("permanent_gacha."):
            tier=key.split(".",1)[1].lower(); file={"legendary":"silver","mythical":"gold","heroic":"mds"}.get(tier,tier)
            out.append({"type":"treasure_key","raw_type":key,"name":tier.title()+" Treasure Key","amount":i(value),"subtype":tier,"image":self.visual_icon(key,"massive") or ICON+f"currency-icon/ic-gachakey-{file}-special.png"}); return out
        if key.startswith("album_pack"):
            subtype=""
            if key.startswith("album_pack_aces."): subtype="ace_"+key.split(".",1)[1]
            elif key.startswith("album_pack."): subtype=key.split(".",1)[1]
            else: subtype=key.replace("album_pack_","")
            file=STICKER_PACK_FILES.get(subtype) or STICKER_THEME_FILES.get(subtype,"")
            fallback=ICON+"stickers/"+file if file else ICON+"stickers/ic_stickers_pack_ace_generic_massive.png"
            game_icon=self.visual_icon(key,"massive")
            out.append({"type":"sticker_pack","raw_type":key,"name":"Sticker Pack" if not subtype else subtype.replace("_"," ").title()+" Sticker Pack","amount":i(value),"subtype":subtype,"image":fallback if file else game_icon or fallback,"image_candidates":uniq([fallback if file else "",game_icon,fallback])}); return out
        if key.startswith("not_owned_sticker_rarity"):
            m=re.search(r"(?:ace_)?(\d+)$",key); rarity=i(m.group(1)) if m else 0; ace="ace_" in key
            filename=("sticker-ace-not-owned-rarity-" if ace else "sticker-not-owned-rarity-")+str(rarity)+".png"
            img=ICON+"stickers/"+filename
            out.append({"type":"missing_sticker","raw_type":key,"name":("Shiny " if ace else "")+f"Missing Sticker Rarity {rarity}","amount":i(value),"rarity":rarity,"ace":ace,"image":img,"image_candidates":uniq([img,self.visual_icon(key,"massive")])}); return out
        if key.startswith("album_dust.") or key.startswith("album_ace_dust."):
            shiny=key.startswith("album_ace_dust."); img=ICON+("stickers/ic-album-dust-aces-massive_c.png" if shiny else "stickers/ic-album-dust-massive_c.png")
            out.append({"type":"sticker_diamond","raw_type":key,"name":"Shiny Diamond" if shiny else "Diamond","amount":i(value),"shiny":shiny,"image":img,"image_candidates":uniq([img,self.visual_icon(key,"massive")])}); return out
        if key.startswith("dragon_mastery_pass_tickets") or key.startswith("temporary_sticker_set_pass_unlock."):
            is_mastery=key.startswith("dragon_mastery")
            # Temporary pass unlocks have date-specific economy-system artwork.
            # Resolve every exact key first, with the wildcard family entry as a
            # fallback for future dates, instead of hardcoding one known season.
            img=(ICON+"currency-icon/ic-dmp-point-massive.png") if is_mastery else self.visual_icon(key,"massive")
            out.append({"type":"progression_pass_tier","raw_type":key,"name":"Mastery Tickets" if is_mastery else "Platinum Pass Unlock","amount":i(value),"image":img,"image_candidates":[img] if img else []}); return out
        if key in {"b","buildings"}:
            values=value if isinstance(value,list) else [value]
            for raw in values:
                item=self.item(i(raw)); group=item["group_type"]
                typ="habitat" if group in {"HABITAT","ORB_HABITAT"} else "building" if group in {"BUILDING","FARM","BOOSTER","GD_TOWER","KINDERGARTEN"} else "decoration"
                out.append({"type":typ,"raw_type":key,"name":item["name"],"amount":1,"item_id":item["id"],"group_type":group,"image":item["image_candidates"][0] if item["image_candidates"] else "","image_candidates":item["image_candidates"]})
            return out
        if key=="chest":
            values=value if isinstance(value,list) else [value]
            for cidraw in values:
                cid=i(cidraw); ch=self.chests.get(cid,{}); raw_name_key=str(ch.get("chest_name_key") or ch.get("type_name_key") or "Unknown Chest"); name=loc(self.loc,ch.get("chest_name_key"),loc(self.loc,ch.get("type_name_key"),raw_name_key))
                out.append({"type":"chest","raw_type":key,"name":name,"amount":1,"chest_id":cid,"image_candidates":chest_candidates(cid,str(ch.get("img_name") or "")),"image":chest_candidates(cid,str(ch.get("img_name") or ""))[0],"open":{"kind":"chest","type":"generic","id":cid}})
            return out
        # Legacy helper keys can arrive here.
        if key=="eggs":
            vals=value if isinstance(value,list) else [value]
            for did in vals: out.extend(self.reward_component("egg",did))
            return out
        # Unknown economy resource: keep it, and use the game's own icon if available.
        name=loc(self.loc,(self.eco_defs.get(key) or {}).get("tid_name"),key.replace("_"," ").replace("."," ").title())
        out.append({"type":"other","raw_type":key,"name":name,"amount":i(value) if not isinstance(value,(dict,list)) else 1,"image":self.visual_icon(key,"massive")})
        return out

    def aggregate_components(self,components:List[Dict[str,Any]])->List[Dict[str,Any]]:
        """Merge repeated placeable rewards with the same item ID into one amount."""
        out=[]; positions={}
        for comp in components or []:
            if comp.get("type") in {"building","habitat","decoration"} and i(comp.get("item_id"))>0:
                marker=(str(comp.get("type")),i(comp.get("item_id")))
                if marker in positions:
                    target=out[positions[marker]]
                    target["amount"]=i(target.get("amount"))+max(1,i(comp.get("amount")))
                    continue
                positions[marker]=len(out)
            out.append(comp)
        return out

    def parse_resource(self,resource:Any)->List[Dict[str,Any]]:
        if not isinstance(resource,dict): return []
        out=[]
        for key,value in resource.items(): out.extend(self.reward_component(str(key),value))
        return self.aggregate_components(out)

    def parse_legacy_reward(self,reward:Any)->List[Dict[str,Any]]:
        if not isinstance(reward,dict): return []
        out=[]
        if isinstance(reward.get("resource"),dict): out.extend(self.parse_resource(reward["resource"]))
        if reward.get("seeds") is not None: out.extend(self.reward_component("seeds",reward.get("seeds")))
        if reward.get("eggs") is not None: out.extend(self.reward_component("eggs",reward.get("eggs")))
        if reward.get("buildings") is not None: out.extend(self.reward_component("buildings",reward.get("buildings")))
        return self.aggregate_components(out)

    def gatcha_groups(self,gids:Iterable[Any])->Tuple[List[Dict[str,Any]],List[Dict[str,Any]]]:
        guaranteed=[]; possible=[]; possible_index=0
        for gidraw in gids or []:
            gid=i(gidraw); spec=self.gspec.get(gid,{})
            static_entries=[]
            for row in self.gstatic.get(gid,[]):
                comps=self.parse_resource(row.get("resource"));
                if comps:
                    entry={"source_id":i(row.get("id")),"components":comps}
                    raw_tm=row.get("overwritten_tier_multi")
                    if raw_tm is not None and is_scaled_multiplier(raw_tm):
                        entry["tier_multi"]=raw_tm; entry["tier_multiplier"]=normalize_tier_multiplier(raw_tm)
                    static_entries.append(entry)
            if static_entries:
                guaranteed.append({"gatcha_id":gid,"entries":static_entries})
            random_rows=self.grandom.get(gid,[])
            if random_rows:
                possible_index+=1; total=sum(max(0,i(x.get("weight"))) for x in random_rows)
                entries=[]
                for row in random_rows:
                    weight=max(0,i(row.get("weight"))); comps=self.parse_resource(row.get("resource"))
                    if comps:
                        entry={"source_id":i(row.get("id")),"weight":weight,"odds":(weight/total*100 if total else None),"components":comps}
                        raw_tm=row.get("overwritten_tier_multi")
                        if raw_tm is not None and is_scaled_multiplier(raw_tm):
                            entry["tier_multi"]=raw_tm; entry["tier_multiplier"]=normalize_tier_multiplier(raw_tm)
                        entries.append(entry)
                possible.append({"index":possible_index,"gatcha_id":gid,"draw_min":i(spec.get("min_random")),"draw_max":i(spec.get("max_random")),"total_weight":total,"entries":entries})
        return guaranteed,possible


def all_components(detail:Dict[str,Any])->Iterable[Dict[str,Any]]:
    if detail.get("levels"):
        for lv in detail["levels"]:
            for g in lv.get("guaranteed",[]):
                for e in g.get("entries",[]): yield from e.get("components",[])
            for g in lv.get("possible",[]):
                for e in g.get("entries",[]): yield from e.get("components",[])
    else:
        for g in detail.get("guaranteed",[]):
            for e in g.get("entries",[]): yield from e.get("components",[])
        for g in detail.get("possible",[]):
            for e in g.get("entries",[]): yield from e.get("components",[])


def reward_groups(detail:Dict[str,Any])->Iterable[Dict[str,Any]]:
    """Yield every guaranteed/possible reward group from a chest detail."""
    if detail.get("levels"):
        for lv in detail.get("levels",[]):
            yield from lv.get("guaranteed",[])
            yield from lv.get("possible",[])
    else:
        yield from detail.get("guaranteed",[])
        yield from detail.get("possible",[])

def reward_entries(detail:Dict[str,Any])->Iterable[Dict[str,Any]]:
    for group in reward_groups(detail):
        for entry in group.get("entries",[]):
            if isinstance(entry,dict):
                yield entry

def special_rules(detail:Dict[str,Any])->List[str]:
    rules=[]
    # Player-level scaling exists in two reward generations:
    # - legacy chest rewards: tier_multi (normally fixed-point, e.g. 1400000)
    # - gatcha rewards: overwritten_tier_multi (fixed-point OR direct float)
    # Both are normalized into entry.tier_multiplier by the extractor.
    if any(is_scaled_multiplier(e.get("tier_multiplier",e.get("tier_multi",1))) for e in reward_entries(detail)):
        rules.append("level_scaled")
    if any(i(g.get("draw_max"))>1 for g in reward_groups(detail)):
        rules.append("multiple_draws")
    return rules

def add_special_rule_metadata(detail:Dict[str,Any], default_level_tiers:Optional[List[int]]=None, player_level_cap:int=0)->None:
    rules=special_rules(detail)
    detail["special_rules"]=rules
    if "level_scaled" in rules:
        tiers=[i(x) for x in (detail.get("level_tiers") or default_level_tiers or []) if i(x)>0]
        detail["level_scaling"]={
            "level_tiers":tiers,
            "player_level_cap":i(player_level_cap),
            "formula":"base_amount * tier_multiplier ^ tier_index",
            "rounding":"nearest_integer",
            "entry_specific_multiplier":True
        }
    else:
        detail.pop("level_scaling",None)


def load_existing_archive() -> Tuple[Dict[str,Dict[str,Any]], Dict[str,Dict[str,Any]], str]:
    """Load the previous generated archive, if one exists.

    Returns summary rows by stable key, detail rows by stable key, and the prior
    archive generation timestamp. Both the legacy flat shard layout and the new
    nested deterministic layout are supported so this is migration-safe.
    """
    summaries: Dict[str,Dict[str,Any]] = {}
    details: Dict[str,Dict[str,Any]] = {}
    previous_generated = ""
    if SUMMARY_PATH.exists():
        try:
            payload=load(SUMMARY_PATH)
            previous_generated=str(payload.get("generated_at") or "") if isinstance(payload,dict) else ""
            for row in (payload.get("chests") or []) if isinstance(payload,dict) else []:
                if isinstance(row,dict) and row.get("key"):
                    summaries[str(row["key"])]=row
        except Exception:
            pass
    if DETAIL_DIR.exists():
        for path in DETAIL_DIR.rglob("*.json"):
            try:
                payload=load(path)
            except Exception:
                continue
            for row in (payload.get("details") or []) if isinstance(payload,dict) else []:
                if isinstance(row,dict) and row.get("key"):
                    details[str(row["key"])]=row
    return summaries,details,previous_generated


def detail_bucket_filename(dtype: str, chest_id: int) -> str:
    count=DETAIL_BUCKET_COUNTS.get(dtype,32)
    bucket=(max(0,int(chest_id)) % count)
    return f"{dtype}/{bucket:02d}.json"


def main()->None:
    previous_summaries,previous_details,previous_generated=load_existing_archive()
    cfg=load(CONFIG_PATH); arena=load(ARENA_PATH); locmap=normalize_loc(load(LOC_PATH)); dragons=load(DRAGONS_PATH); skins=load(SKINS_PATH)
    cx=Context(cfg,arena,locmap,dragons,skins)
    # Canonical player-level tier boundaries are also used by Alliance rewards.
    # Current config exposes them through the Battle Pass LEVEL_TIERS row.
    default_player_level_tiers=[]
    for row in (cfg.get("battle_pass") or {}).get("rewards_tiers",[]):
        if str(row.get("name") or "").upper()=="LEVEL_TIERS" and isinstance(row.get("value"),list):
            default_player_level_tiers=[i(x) for x in row.get("value") if i(x)>0]
            break
    if not default_player_level_tiers:
        default_player_level_tiers=[5,11,17,21,28,35,41,49,74,99,150]
    player_level_cap=max([i(x.get("level")) for x in (cfg.get("levels") or []) if isinstance(x,dict)]+[200])
    details=[]; summaries=[]
    collisions=defaultdict(list)
    # References from Arena to Warrior chest availability/context.
    warrior_refs=defaultdict(list)
    for a in arena.get("arenas",[]):
        cid=i(a.get("warrior_chest_id"));
        if cid<=0: continue
        av=a.get("availability") or {}
        warrior_refs[cid].append({"arena_id":i(a.get("id")),"arena_level_id":i(a.get("arena_level_id")),"arena_season_id":i(a.get("arena_season_id")),"arena_type":str(a.get("type") or ""),"arena_element":str(a.get("arena_element") or ""),"from":i(av.get("from")),"to":i(av.get("to"))})
    # Alliance schedule appearances.
    alliance_days=defaultdict(list)
    day_names=["monday","tuesday","wednesday","thursday","friday","saturday","sunday"]
    for w in (cfg.get("alliance_chest") or {}).get("weeks",[]):
        base=i(w.get("start_ts"))
        for idx,day in enumerate(day_names):
            cid=i(w.get(day))
            if cid>0: alliance_days[cid].append(base+idx*86400)
    # Generic.
    legacy_reward_by_id={i(x.get("id")):x for x in (cfg.get("chests") or {}).get("rewards",[]) if isinstance(x,dict)}
    for order,ch in enumerate((cfg.get("chests") or {}).get("chests",[])):
        cid=i(ch.get("id")); key=f"generic:{cid}"; collisions[cid].append("generic")
        raw_name_key=str(ch.get("chest_name_key") or ch.get("type_name_key") or "Unknown Chest")
        name=loc(locmap,ch.get("chest_name_key"),loc(locmap,ch.get("type_name_key"),raw_name_key))
        # A second capitalization family exists in config without localization.
        # Keep the in-game Pet Food Basket names instead of exposing the raw TID.
        pet_key=str(ch.get("chest_name_key") or "")
        m_pet=re.fullmatch(r"tid_chest_name_petfood_(s|m|l|xl)",pet_key,flags=re.I)
        if m_pet:
            name={"s":"Small Pet Food Basket","m":"Medium Pet Food Basket","l":"Large Pet Food Basket","xl":"Extra Large Pet Food Basket"}[m_pet.group(1).lower()]
        desc=loc(locmap,ch.get("description_key"),"")
        if ch.get("gatcha_ids"):
            guar,poss=cx.gatcha_groups(ch.get("gatcha_ids") or []); mode="gatcha"
        else:
            mode="legacy"; guar=[]; poss=[]; rows=[]
            reward_rows=[legacy_reward_by_id.get(i(x)) for x in (ch.get("rewards") or [])]; reward_rows=[x for x in reward_rows if x]
            total=sum(max(0,i(x.get("weight"))) for x in reward_rows)
            for row in reward_rows:
                comps=cx.parse_legacy_reward((row or {}).get("reward")); weight=max(0,i((row or {}).get("weight")))
                if comps:
                    raw_tm=row.get("tier_multi",1)
                    entry={"source_id":i(row.get("id")),"weight":weight,"odds":weight/total*100 if total else None,"tier_multi":raw_tm,"components":comps}
                    if is_scaled_multiplier(raw_tm): entry["tier_multiplier"]=normalize_tier_multiplier(raw_tm)
                    rows.append(entry)
            if rows: poss=[{"index":1,"gatcha_id":None,"draw_min":1,"draw_max":i(ch.get("pool_size")) or 1,"total_weight":total,"entries":rows}]
        images=chest_candidates(cid,str(ch.get("img_name") or ""))
        detail={"key":key,"type":"generic","id":cid,"config_order":order,"name":name,"description":desc,"source_mode":mode,"image_candidates":images,"guaranteed":guar,"possible":poss,"level_tiers":ch.get("level_tiers") or [],"pool_size":i(ch.get("pool_size")),"raw":{"type":str(ch.get("type") or ""),"chest_name_key":str(ch.get("chest_name_key") or ""),"description_key":str(ch.get("description_key") or "")}}
        details.append(detail)
    # Alliance.
    level_rows=defaultdict(dict); reward_rows=defaultdict(dict)
    for r in (cfg.get("alliance_chest") or {}).get("level_sets",[]): level_rows[i(r.get("id"))][i(r.get("level"))]=r
    for r in (cfg.get("alliance_chest") or {}).get("reward_sets",[]): reward_rows[i(r.get("id"))][i(r.get("level"))]=r
    for order,ch in enumerate((cfg.get("alliance_chest") or {}).get("chests",[])):
        cid=i(ch.get("id")); key=f"alliance:{cid}"; collisions[cid].append("alliance")
        activity=str(ch.get("activity") or ""); activity_name=loc(locmap,ch.get("activity_name_tid"),activity.replace("_"," ").title())
        name=f"{activity_name} Alliance Chest" if "Alliance Chest" not in activity_name else activity_name
        desc=loc(locmap,ch.get("chest_claim_description_tid"),f"Complete {activity_name} activities with your Alliance to unlock better chest levels.")
        asset=str(ch.get("asset_name") or "")
        if asset and re.match(r"^alliancechest_%d_",asset,flags=re.I):
            # Legacy Alliance artwork has only three visual tiers:
            # levels 1-2 -> art 1, 3-4 -> art 2, 5-6 -> art 3.
            level_images={str(lv):chest_candidates(cid,asset.replace("%d",str(min(3,(lv+1)//2)))) for lv in range(1,7)}
        else:
            level_images={str(lv):chest_candidates(cid,asset.replace("%d",str(lv))) for lv in range(1,7)} if asset else {}
        images=level_images.get("6") or ([MISSING_CHEST] if not asset else chest_candidates(cid,asset.replace("%d","6")))
        levels=[]
        for lv in range(1,7):
            lr=level_rows[i(ch.get("level_set"))].get(lv,{})
            rr=reward_rows[i(ch.get("reward_set"))].get(lv,{})
            guar,poss=cx.gatcha_groups(rr.get("gatcha_ids") or [])
            levels.append({"level":lv,"points_required":i(lr.get("points_required")),"gatcha_ids":rr.get("gatcha_ids") or [],"guaranteed":guar,"possible":poss})
        appearances=sorted(alliance_days.get(cid,[]))
        detail={"key":key,"type":"alliance","id":cid,"config_order":order,"name":name,"description":desc,"activity":activity,"activity_name":activity_name,"image_candidates":images,"level_image_candidates":level_images,"levels":levels,"availability":{"first_known":iso(appearances[0]) if appearances else "","last_known":iso(appearances[-1]+86400) if appearances else "","appearance_count":len(appearances)},"raw":{"level_set":i(ch.get("level_set")),"reward_set":i(ch.get("reward_set")),"building_dragon":i(ch.get("building_dragon")),"chest_reward_asset":ch.get("chest_reward_asset")}}
        details.append(detail)
    # Warrior.
    for order,ch in enumerate(arena.get("warrior_chests",[])):
        cid=i(ch.get("id")); key=f"warrior:{cid}"; collisions[cid].append("warrior")
        refs=warrior_refs.get(cid,[])
        elements=uniq([x["arena_element"] for x in refs if x.get("arena_element")])
        seasons=uniq([x["arena_season_id"] for x in refs if x.get("arena_season_id")])
        types=uniq([x["arena_type"] for x in refs if x.get("arena_type")])
        name="Warrior's Chest"; desc="Arena-exclusive Warrior's Chest reward."
        remote=remote_url(ch.get("ready_img") or ch.get("growing_img") or ch.get("unavailable_img"))
        images=uniq([remote,MISSING_CHEST]) if remote else [MISSING_CHEST]
        guar,poss=cx.gatcha_groups(ch.get("gatcha_ids") or [])
        starts=[x["from"] for x in refs if x.get("from")]; ends=[x["to"] for x in refs if x.get("to")]
        detail={"key":key,"type":"warrior","id":cid,"config_order":order,"name":name,"description":desc,"image_candidates":images,"guaranteed":guar,"possible":poss,"arena_context":{"elements":elements,"season_ids":seasons,"arena_types":types,"references":refs},"availability":{"first_known":iso(min(starts)) if starts else "","last_known":iso(max(ends)) if ends else "","appearance_count":len(refs)},"raw":{"claim_animation_name":str(ch.get("claim_animation_name") or ""),"gatcha_ids":ch.get("gatcha_ids") or []}}
        details.append(detail)
    # Preserve chest definitions that disappeared from the latest source files.
    # Current source data wins for keys that still exist. Same-ID changes update
    # in place; revision history is intentionally not kept.
    current_keys={str(d.get("key")) for d in details}
    archived_added=0
    for key,old_detail in previous_details.items():
        if key not in current_keys:
            details.append(old_detail)
            archived_added+=1

    # Recompute derived metadata for current and archived records so the
    # browse index and popup use one consistent rule model.
    for d in details:
        add_special_rule_metadata(d,default_player_level_tiers,player_level_cap)

    # Deterministic detail buckets: namespace + (chest_id % fixed bucket count).
    # Do not include a per-run generated timestamp inside each bucket. Therefore
    # an extractor run that adds one chest only changes its target bucket (plus
    # chests.json), rather than rewriting every detail file.
    if DETAIL_DIR.exists():
        import shutil
        shutil.rmtree(DETAIL_DIR)
    DETAIL_DIR.mkdir(parents=True,exist_ok=True)
    shard_map={}
    buckets=defaultdict(list)
    for d in details:
        dtype=str(d.get("type") or "generic")
        filename=detail_bucket_filename(dtype,i(d.get("id")))
        shard_map[d["key"]]=filename
        # config_order belongs to the browse index and may shift when SP inserts
        # definitions. Keeping it out of detail buckets makes bucket contents
        # stable unless an actual chest definition changes.
        stored={k:v for k,v in d.items() if k!="config_order"}
        buckets[filename].append(stored)
    for filename,rows in buckets.items():
        rows.sort(key=lambda x:(i(x.get("id")),str(x.get("key") or "")))
        path=DETAIL_DIR / filename
        path.parent.mkdir(parents=True,exist_ok=True)
        dump(path,{"schema_version":2,"details":rows})

    # Summaries / search/filter facets. Current presence is tracked here rather
    # than inside shards, so periodic runs do not rewrite every detail bucket.
    type_counts=defaultdict(int); current_type_counts=defaultdict(int); merged_collisions=defaultdict(list)
    now=datetime.now(timezone.utc).isoformat().replace("+00:00","Z")
    for d in details:
        key=str(d.get("key") or ""); is_current=key in current_keys
        comps=list(all_components(d)); types=uniq([x.get("type") for x in comps if x.get("type")]); names=uniq([x.get("name") for x in comps if x.get("name")]); opens=uniq([x.get("dragon_id") for x in comps if x.get("dragon_id")])
        type_counts[d["type"]]+=1
        if is_current: current_type_counts[d["type"]]+=1
        merged_collisions[i(d.get("id"))].append(str(d.get("type") or ""))
        availability=d.get("availability") or {}
        old=previous_summaries.get(key,{})
        first_seen=str(old.get("first_seen") or previous_generated or now)
        last_seen=now if is_current else str(old.get("last_seen") or previous_generated or first_seen)
        summaries.append({"key":d["key"],"type":d["type"],"id":d["id"],"config_order":d.get("config_order",old.get("config_order",0)),"name":d["name"],"image_candidates":d.get("image_candidates") or [MISSING_CHEST],"reward_types":types,"reward_names":names,"reward_dragon_ids":opens,"special_rules":d.get("special_rules") or [],"availability":availability,"detail_file":shard_map.get(d["key"],""),"activity":d.get("activity",""),"activity_name":d.get("activity_name",""),"present_in_latest_config":is_current,"first_seen":first_seen,"last_seen":last_seen})
    summaries.sort(key=lambda x:(str(x.get("type") or ""),i(x.get("config_order")),i(x.get("id"))))
    collision_rows={str(cid):uniq(types) for cid,types in sorted(merged_collisions.items()) if len(uniq(types))>1}
    summary_payload={"schema_version":2,"generated_at":now,"meta":{"total":len(summaries),"current_total":len(current_keys),"archived_total":len(summaries)-len(current_keys),"counts":dict(type_counts),"current_counts":dict(current_type_counts),"page_size":200,"detail_bucket_counts":DETAIL_BUCKET_COUNTS,"id_collisions":collision_rows},"assets":{"missing_chest":MISSING_CHEST,"reward_type_icons":REWARD_TYPE_ICONS},"reward_filter_groups":[
        {"id":"main_resources","label":"Main Resources","types":["gold","food","gems","xp"]},
        {"id":"dragons","label":"Dragons","types":["dragon_egg","empowered_dragon_egg","dragon_orbs","skin"]},
        {"id":"tree_of_life","label":"Tree of Life","types":["joker_orbs","trade_essence"]},
        {"id":"items","label":"Items","types":["building","habitat","decoration"]},
        {"id":"progression","label":"Progression","types":["elemental_token","special_token","perk","rank_up_coin"]},
        {"id":"event_resources","label":"Event Resources","types":["event_coin","puzzle_move","flight_stamp","keys"]},
        {"id":"others","label":"Others","types":["old_rescue_keys","pet_food","progression_pass_tier","treasure_key","hollow_ticket"]},
        {"id":"stickers","label":"Stickers","types":["sticker_pack","missing_sticker","sticker_diamond"]},
    ],"chests":summaries}
    dump(SUMMARY_PATH,summary_payload)
    print(f"Wrote {SUMMARY_PATH.name}: {len(summaries)} chests")
    print(f"Wrote {len(buckets)} deterministic detail buckets to {DETAIL_DIR.name}/")
    print(f"Archive preserved: {archived_added} chest(s) not present in latest config")
    print("Counts:",dict(type_counts))
    print("ID collisions:",collision_rows)

if __name__=="__main__": main()
