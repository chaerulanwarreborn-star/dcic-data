#!/usr/bin/env python3
"""Build chest archive datasets for Dragon City Information Center.

Sources:
- game_config.json / chests.chests              -> Generic Chests
- game_config.json / alliance_chest.chests      -> Alliance Chests
- arena_config.json / warrior_chests             -> Arena Warrior's Chests

Outputs:
- chests.json          compact browse/search/filter index
- chest-details/*.json lazy normalized reward detail shards used by the global popup

Source IDs are preserved. Because IDs collide between namespaces, every record
also carries a stable `key` (`generic:2`, `alliance:2`, `warrior:102`).
"""
from __future__ import annotations

import json
import re
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
DETAIL_SHARD_SIZES = {"generic": 300, "alliance": 100, "warrior": 100}

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
    "ep":("xp","XP",ICON+"resources/ic-experience-xp.png"),
    "moves":("puzzle_move","Puzzle Moves",ICON+"currency-icon/coin-puzzle.png"),
    "en_runner":("flight_stamp","Flight Stamps",ICON+"currency-icon/coin-runner.png"),
    "gacha_event_tickets":("event_coin","Event Currency",ICON+"currency-icon/coin-mix.png"),
    "keys":("rescue_key","Dragon Rescue Keys",ICON+"text-icons/ic-key-massive.png"),
}
RANK_FILE = {"common":"common","rare":"rare","very_rare":"veryrare","veryrare":"veryrare","epic":"epic","legendary":"legendary","mythical":"mythical","heroic":"heroic"}
STICKER_PACK_FILES = {
    "s":"ic_stickers_pack_s_massive.png","m":"ic_stickers_pack_m_massive.png","l":"ic_stickers_pack_l_massive.png","xl":"ic_stickers_pack_xl_massive.png",
    "ace_1":"ic_stickers_pack_ace_1_massive.png","ace_2":"ic_stickers_pack_ace_2_massive.png","ace_3":"ic_stickers_pack_ace_3_massive.png",
    "ace_4":"ic_stickers_pack_ace_4_massive.png","ace_5":"ic_stickers_pack_ace_5_massive.png","ace_generic":"ic_stickers_pack_ace_generic_massive.png",
}
REWARD_TYPE_ICONS = {
    "gold":ICON+"resources/ic-gold.png","food":ICON+"resources/ic-food.png","gems":ICON+"resources/ic-gem.png","xp":ICON+"resources/ic-experience-xp.png",
    "dragon_egg":ICON+"text-icons/egg.png","empowered_dragon_egg":ICON+"text-icons/gr-enable-star.png","dragon_orbs":ICON+"text-icons/ic-hud-orb-shop.png","skin":ICON+"text-icons/ic-dragon-skin-badge.png",
    "joker_orbs":ICON+"tree-of-life/ic-joker-all.png","trade_essence":ICON+"tree-of-life/ic-trade-orb-mid-generic.png",
    "building":ICON+"text-icons/gr-category-buildings.png","habitat":ICON+"text-icons/gr-category-habitats.png","decoration":ICON+"text-icons/gr-category-decos.png",
    "elemental_token":ICON+"tokens/gr-category-tokens.png","special_token":ICON+"tokens/ic-token-neutral.png","perk":ICON+"perks/ic-combat-perk.png","rank_up_coin":ICON+"rank-up-coins/ic-rank-up-coin-common.png",
    "event_coin":ICON+"currency-icon/coin-mix.png","puzzle_move":ICON+"currency-icon/coin-puzzle.png","flight_stamp":ICON+"currency-icon/coin-runner.png","rescue_key":ICON+"text-icons/ic-key-massive.png",
    "pet_food":ICON+"pet-food/ui_chest_pet_food_xl.png","progression_pass_tier":ICON+"currency-icon/ic-dmp-point-massive.png","treasure_key":ICON+"currency-icon/gachakey_gold_silver_mds.png",
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
    if s.startswith("http://") or s.startswith("https://"): return s
    return STATIC+s.lstrip("/")

def chest_candidates(chest_id: int, img_name: str) -> List[str]:
    raw=str(img_name or "").strip().replace("\\","/").rsplit("/",1)[-1]
    if not raw: return [MISSING_CHEST]
    raw=re.sub(r"\.png$","",raw,flags=re.I); raw=re.sub(r"@2x$","",raw,flags=re.I)
    clean=re.sub(r"^ui_","",raw,flags=re.I)
    return uniq([
        STATIC+f"mobile/ui/chests/ui_{chest_id}_{clean}@2x.png",
        STATIC+f"mobile/ui/chests/ui_{clean}@2x.png",
        STATIC+f"mobile/ui/chests/{clean}.png",
        STATIC+f"mobile/ui/chests/ui_basic_chest_{clean}@2x.png",
        MISSING_CHEST,
    ])

def item_candidates(item: Dict[str,Any]) -> List[str]:
    raw=str(item.get("img_name_mobile") or item.get("img_name") or "").strip()
    if not raw: return []
    return uniq([
        STATIC+f"mobile/ui/decorations/ui_{raw}@2x.png", STATIC+f"mobile/ui/decorations/{raw}.png",
        STATIC+f"mobile/ui/buildings/ui_{raw}@2x.png", STATIC+f"mobile/ui/buildings/{raw}.png",
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
        row=self.eco_icons.get(key,{})
        return remote_url(row.get(variant) or row.get("massive") or row.get("regular") or "")

    def item(self,item_id:int)->Dict[str,Any]:
        row=self.items.get(item_id,{})
        name=loc(self.loc,f"tid_building_{item_id}_name",str(row.get("name") or f"Item {item_id}"))
        desc=loc(self.loc,f"tid_building_{item_id}_description",str(row.get("description") or ""))
        return {"id":item_id,"name":name,"description":desc,"group_type":str(row.get("group_type") or "").upper(),"image_candidates":item_candidates(row)}

    def reward_component(self,key:str,value:Any)->List[Dict[str,Any]]:
        out=[]
        # Main/simple resources.
        if key in RESOURCE_INFO:
            typ,name,img=RESOURCE_INFO[key]
            out.append({"type":typ,"raw_type":key,"name":name,"amount":i(value),"image":img})
            return out
        if key=="egg":
            d=self.dragon(i(value)); out.append({"type":"dragon_egg","raw_type":key,"name":d["name"]+" Egg","amount":1,"dragon_id":d["id"],"rarity":d["rarity"],"image":d["baby_image"],"open":{"kind":"dragon","id":d["id"]}}); return out
        if key=="seggs" and isinstance(value,list):
            for x in value:
                if not isinstance(x,dict): continue
                d=self.dragon(i(x.get("id"))); grade=i(x.get("grade")); level=x.get("level")
                out.append({"type":"empowered_dragon_egg","raw_type":key,"name":d["name"],"amount":i(x.get("amount")) or 1,"dragon_id":d["id"],"rarity":d["rarity"],"empowerment":grade,"rank":i(x.get("rank")),"level":i(level) if level is not None else None,"image":d["baby_image"],"mini_icon":ICON+"text-icons/gr-enable-star.png","open":{"kind":"dragon","id":d["id"]}})
            return out
        if key=="seeds" and isinstance(value,list):
            for x in value:
                if not isinstance(x,dict): continue
                d=self.dragon(i(x.get("id"))); token=RARITY_FILE.get(d["rarity"],d["rarity"].lower())
                out.append({"type":"dragon_orbs","raw_type":key,"name":d["name"]+" Orbs","amount":i(x.get("amount")),"dragon_id":d["id"],"rarity":d["rarity"],"image":d["adult_image"],"mini_icon":ICON+f"tree-of-life/ic-seed-{token}-mid-shadow.png" if token else "","open":{"kind":"dragon","id":d["id"]}})
            return out
        if key=="rarity_seeds" and isinstance(value,list):
            for x in value:
                r=str(x.get("rarity") or "").upper(); token=RARITY_FILE.get(r,r.lower())
                out.append({"type":"joker_orbs","raw_type":key,"name":RARITY_NAMES.get(r,r)+" Joker Orbs","amount":i(x.get("amount")),"rarity":r,"image":ICON+f"tree-of-life/ic-joker-{token}.png"})
            return out
        if key=="trade_tickets" and isinstance(value,list):
            for x in value:
                r=str(x.get("rarity") or "").upper(); token=RARITY_FILE.get(r,r.lower())
                out.append({"type":"trade_essence","raw_type":key,"name":RARITY_NAMES.get(r,r)+" Trade Essences","amount":i(x.get("amount")),"rarity":r,"image":ICON+f"tree-of-life/ic-trade-orb-big-{token}.png"})
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
            out.append({"type":"rank_up_coin","raw_type":key,"name":name,"amount":i(value),"rarity":rarity,"image":self.visual_icon(key) or ICON+f"rank-up-coins/ic-rank-up-coin-{fname}.png"}); return out
        if key in TOKEN_MAP:
            token,label=TOKEN_MAP[key]; out.append({"type":"elemental_token","raw_type":key,"name":label,"amount":i(value),"token":token,"image":ICON+f"tokens/ic-token-{token}.png"}); return out
        if key in SPECIAL_TOKEN_MAP:
            token,label=SPECIAL_TOKEN_MAP[key]; out.append({"type":"special_token","raw_type":key,"name":label,"amount":i(value),"token":token,"image":ICON+f"tokens/ic-token-{token}.png"}); return out
        if key=="battleground_keys" and isinstance(value,list):
            for x in value:
                if isinstance(x,dict): out.append({"type":"rescue_key","raw_type":key,"name":"Battleground Keys","amount":i(x.get("amount")) or 1,"battleground_id":i(x.get("battleground_id")),"key_id":i(x.get("key_id")),"image":ICON+"text-icons/ic-key-massive.png"})
            return out
        if key=="pet_food":
            out.append({"type":"pet_food","raw_type":key,"name":"Pet Food","amount":i(value),"image":ICON+"pet-food/ui_chest_pet_food_xl.png"}); return out
        if key.startswith("pet_food_pack."):
            size=key.split(".",1)[1].lower(); out.append({"type":"pet_food","raw_type":key,"name":size.upper()+" Pet Food Pack","amount":i(value),"subtype":size,"image":self.visual_icon(key,"massive") or ICON+f"pet-food/ui_chest_pet_food_{size}.png"}); return out
        if key.startswith("permanent_gacha."):
            tier=key.split(".",1)[1].lower(); file={"legendary":"silver","mythical":"gold","heroic":"mds"}.get(tier,tier)
            out.append({"type":"treasure_key","raw_type":key,"name":tier.title()+" Treasure Key","amount":i(value),"subtype":tier,"image":self.visual_icon(key,"massive") or ICON+f"currency-icon/ic-gachakey-{file}-special.png"}); return out
        if key.startswith("album_pack"):
            subtype=""
            if key.startswith("album_pack_aces."): subtype="ace_"+key.split(".",1)[1]
            elif key.startswith("album_pack."): subtype=key.split(".",1)[1]
            else: subtype=key.replace("album_pack_","")
            file=STICKER_PACK_FILES.get(subtype,"")
            out.append({"type":"sticker_pack","raw_type":key,"name":"Sticker Pack" if not subtype else subtype.replace("_"," ").title()+" Sticker Pack","amount":i(value),"subtype":subtype,"image":self.visual_icon(key,"massive") or (ICON+"stickers/"+file if file else ICON+"stickers/ic_stickers_pack_ace_generic_massive.png")}); return out
        if key.startswith("not_owned_sticker_rarity"):
            m=re.search(r"(?:ace_)?(\d+)$",key); rarity=i(m.group(1)) if m else 0; ace="ace_" in key
            filename=("sticker-ace-not-owned-rarity-" if ace else "sticker-not-owned-rarity-")+str(rarity)+".png"
            out.append({"type":"missing_sticker","raw_type":key,"name":("Shiny " if ace else "")+f"Missing Sticker Rarity {rarity}","amount":i(value),"rarity":rarity,"ace":ace,"image":self.visual_icon(key,"massive") or ICON+"stickers/"+filename}); return out
        if key.startswith("album_dust.") or key.startswith("album_ace_dust."):
            shiny=key.startswith("album_ace_dust."); out.append({"type":"sticker_diamond","raw_type":key,"name":"Shiny Diamond" if shiny else "Diamond","amount":i(value),"shiny":shiny,"image":self.visual_icon(key,"massive") or ICON+("stickers/ic-album-dust-aces-massive_c.png" if shiny else "stickers/ic-album-dust-massive_c.png")}); return out
        if key.startswith("dragon_mastery_pass_tickets") or key.startswith("temporary_sticker_set_pass_unlock."):
            out.append({"type":"progression_pass_tier","raw_type":key,"name":"Mastery Tickets" if key.startswith("dragon_mastery") else "Platinum Pass Unlock","amount":i(value),"image":self.visual_icon(key,"massive") or ICON+"currency-icon/ic-dmp-point-massive.png"}); return out
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
                cid=i(cidraw); ch=self.chests.get(cid,{}); name=loc(self.loc,ch.get("chest_name_key"),loc(self.loc,ch.get("type_name_key"),f"Chest {cid}"))
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

    def parse_resource(self,resource:Any)->List[Dict[str,Any]]:
        if not isinstance(resource,dict): return []
        out=[]
        for key,value in resource.items(): out.extend(self.reward_component(str(key),value))
        return out

    def parse_legacy_reward(self,reward:Any)->List[Dict[str,Any]]:
        if not isinstance(reward,dict): return []
        out=[]
        if isinstance(reward.get("resource"),dict): out.extend(self.parse_resource(reward["resource"]))
        if reward.get("seeds") is not None: out.extend(self.reward_component("seeds",reward.get("seeds")))
        if reward.get("eggs") is not None: out.extend(self.reward_component("eggs",reward.get("eggs")))
        if reward.get("buildings") is not None: out.extend(self.reward_component("buildings",reward.get("buildings")))
        return out

    def gatcha_groups(self,gids:Iterable[Any])->Tuple[List[Dict[str,Any]],List[Dict[str,Any]]]:
        guaranteed=[]; possible=[]; possible_index=0
        for gidraw in gids or []:
            gid=i(gidraw); spec=self.gspec.get(gid,{})
            static_entries=[]
            for row in self.gstatic.get(gid,[]):
                comps=self.parse_resource(row.get("resource"));
                if comps: static_entries.append({"source_id":i(row.get("id")),"components":comps})
            if static_entries:
                guaranteed.append({"gatcha_id":gid,"entries":static_entries})
            random_rows=self.grandom.get(gid,[])
            if random_rows:
                possible_index+=1; total=sum(max(0,i(x.get("weight"))) for x in random_rows)
                entries=[]
                for row in random_rows:
                    weight=max(0,i(row.get("weight"))); comps=self.parse_resource(row.get("resource"))
                    if comps: entries.append({"source_id":i(row.get("id")),"weight":weight,"odds":(weight/total*100 if total else None),"components":comps})
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


def main()->None:
    cfg=load(CONFIG_PATH); arena=load(ARENA_PATH); locmap=normalize_loc(load(LOC_PATH)); dragons=load(DRAGONS_PATH); skins=load(SKINS_PATH)
    cx=Context(cfg,arena,locmap,dragons,skins)
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
        name=loc(locmap,ch.get("chest_name_key"),loc(locmap,ch.get("type_name_key"),f"Chest {cid}"))
        desc=loc(locmap,ch.get("description_key"),"")
        if ch.get("gatcha_ids"):
            guar,poss=cx.gatcha_groups(ch.get("gatcha_ids") or []); mode="gatcha"
        else:
            mode="legacy"; guar=[]; poss=[]; rows=[]
            reward_rows=[legacy_reward_by_id.get(i(x)) for x in (ch.get("rewards") or [])]; reward_rows=[x for x in reward_rows if x]
            total=sum(max(0,i(x.get("weight"))) for x in reward_rows)
            for row in reward_rows:
                comps=cx.parse_legacy_reward((row or {}).get("reward")); weight=max(0,i((row or {}).get("weight")))
                if comps: rows.append({"source_id":i(row.get("id")),"weight":weight,"odds":weight/total*100 if total else None,"tier_multi":row.get("tier_multi"),"components":comps})
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
    # Detail shards are intentionally small enough for lazy browser loading.
    DETAIL_DIR.mkdir(exist_ok=True)
    for old in DETAIL_DIR.glob("*.json"):
        old.unlink()
    shard_map={}
    buckets=defaultdict(list)
    for d in details:
        dtype=str(d.get("type") or "generic")
        shard_size=DETAIL_SHARD_SIZES.get(dtype, 200)
        shard_no=int(d.get("config_order",0))//shard_size
        filename=f"{dtype}-{shard_no:02d}.json"
        shard_map[d["key"]]=filename
        buckets[filename].append(d)
    for filename, rows in buckets.items():
        dump(DETAIL_DIR / filename, {"schema_version":1,"generated_at":datetime.now(timezone.utc).isoformat().replace("+00:00","Z"),"details":rows})

    # Summaries / search/filter facets.
    type_counts=defaultdict(int)
    for d in details:
        comps=list(all_components(d)); types=uniq([x.get("type") for x in comps if x.get("type")]); names=uniq([x.get("name") for x in comps if x.get("name")]); opens=uniq([x.get("dragon_id") for x in comps if x.get("dragon_id")])
        type_counts[d["type"]]+=1
        availability=d.get("availability") or {}
        summaries.append({"key":d["key"],"type":d["type"],"id":d["id"],"config_order":d["config_order"],"name":d["name"],"image_candidates":d.get("image_candidates") or [MISSING_CHEST],"reward_types":types,"reward_names":names,"reward_dragon_ids":opens,"availability":availability,"detail_file":shard_map.get(d["key"],""),"activity":d.get("activity",""),"activity_name":d.get("activity_name","")})
    collision_rows={str(cid):types for cid,types in sorted(collisions.items()) if len(types)>1}
    now=datetime.now(timezone.utc).isoformat().replace("+00:00","Z")
    summary_payload={"schema_version":1,"generated_at":now,"meta":{"total":len(summaries),"counts":dict(type_counts),"page_size":200,"id_collisions":collision_rows},"assets":{"missing_chest":MISSING_CHEST,"reward_type_icons":REWARD_TYPE_ICONS},"reward_filter_groups":[
        {"id":"main_resources","label":"Main Resources","types":["gold","food","gems","xp"]},
        {"id":"dragons","label":"Dragons","types":["dragon_egg","empowered_dragon_egg","dragon_orbs","skin"]},
        {"id":"tree_of_life","label":"Tree of Life","types":["joker_orbs","trade_essence"]},
        {"id":"items","label":"Items","types":["building","habitat","decoration"]},
        {"id":"progression","label":"Progression","types":["elemental_token","special_token","perk","rank_up_coin"]},
        {"id":"currency","label":"Currency","types":["event_coin","puzzle_move","flight_stamp","rescue_key","pet_food","progression_pass_tier","treasure_key"]},
        {"id":"stickers","label":"Stickers","types":["sticker_pack","missing_sticker","sticker_diamond"]},
    ],"chests":summaries}
    dump(SUMMARY_PATH,summary_payload)
    print(f"Wrote {SUMMARY_PATH.name}: {len(summaries)} chests")
    print(f"Wrote {len(buckets)} lazy detail shards to {DETAIL_DIR.name}/")
    print("Counts:",dict(type_counts))
    print("ID collisions:",collision_rows)

if __name__=="__main__": main()
