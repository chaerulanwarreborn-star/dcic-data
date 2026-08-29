#!/usr/bin/env python3
"""Build maze_island.json for DCIC Maze Island Guide (hero + reward summary)."""
from __future__ import annotations
import json,re
from datetime import datetime,timezone
from pathlib import Path
from typing import Any,Dict,List,Iterable
ROOT=Path(__file__).resolve().parent
CFG=ROOT/'game_config.json'; LOC=ROOT/'localization'/'dragon_city_localization_baseline_en.json'; OUT=ROOT/'maze_island.json'
STATIC='https://dci-static-s1.socialpointgames.com/static/dragoncity/'
CHEST=STATIC+'mobile/ui/chests/'
EXCLUDED={"Wood Chest","Bamboo Chest","Common Orbs Chest","Rare Orbs Chest","Very Rare Orbs Chest","Bronze Chest","Epic Orbs Chest","Silver Chest","Legendary Orbs Chest","Gold Chest"}

# Chest-backed rewards that function as event items in Maze rewards summary.
# Keep them clickable as Generic Chests, but group them under Event Items.
EVENT_ITEM_CHEST_IDS={10238,14935,14936,16551,16552,16553,16554,16556,16557,16558,16559,16560,14937,13825,18127,17058,2659,10239}

# Ordinary/non-special chests that can appear on Maze paths but should not be
# promoted into the "Other Special Chests" summary.
ORDINARY_CHEST_IDS={10714,10710,4045,5013,7002,8147,10711}

def load(p): return json.load(open(p,encoding='utf-8'))
def dump(p,d): json.dump(d,open(p,'w',encoding='utf-8'),ensure_ascii=False,separators=(',',':'))
def ii(v):
 try:return int(v)
 except:return 0
def normloc(raw):
 if isinstance(raw,dict): return {str(k):str(v) for k,v in raw.items() if v is not None}
 out={}
 for r in raw if isinstance(raw,list) else []:
  if isinstance(r,dict): out.update({str(k):str(v) for k,v in r.items() if v is not None})
 return out
def lx(loc,k,fb=''): return str(loc.get(str(k or ''),'') or fb).strip()
def uniq(vals:Iterable[Any]):
 out=[]; seen=set()
 for v in vals:
  s=str(v)
  if v is not None and s not in seen: seen.add(s);out.append(v)
 return out
def iso(ts): return datetime.fromtimestamp(ii(ts),timezone.utc).isoformat().replace('+00:00','Z') if ii(ts)>0 else ''
def chest_cands(cid,img):
 raw=str(img or '').strip(); clean=re.sub(r'^ui_','',re.sub(r'@2x(?:\.png)?$|\.png$','',raw,flags=re.I),flags=re.I)
 return uniq([CHEST+f'ui_{cid}_{clean}@2x.png' if clean else '',CHEST+f'ui_{clean}@2x.png' if clean else '',CHEST+f'{clean}.png' if clean else ''])
def item_cands(img):
 raw=str(img or '').strip()
 return uniq([STATIC+f'mobile/ui/decorations/ui_{raw}@2x.png',STATIC+f'mobile/ui/decorations/{raw}.png',STATIC+f'mobile/ui/buildings/ui_{raw}@2x.png',STATIC+f'mobile/ui/buildings/{raw}.png']) if raw else []
def dragon_cands(img):
 raw=str(img or '').strip()
 return uniq([STATIC+f'mobile/ui/dragons/HD/thumb_{raw}_3.png',STATIC+f'mobile/ui/dragons/ui_{raw}_3@2x.png']) if raw else []

def main():
 c=load(CFG); loc=normloc(load(LOC)); m=c.get('maze_island') or {}
 items={ii(x.get('id')):x for x in c.get('items',[]) if isinstance(x,dict)}
 chests={ii(x.get('id')):x for x in (c.get('chests') or {}).get('chests',[]) if isinstance(x,dict)}
 paths={ii(x.get('id')):x for x in m.get('paths',[]) if isinstance(x,dict)}
 rewards={ii(x.get('id')):x for x in m.get('rewards',[]) if isinstance(x,dict)}
 out=[]
 for isl in m.get('islands',[]):
  iid=ii(isl.get('id')); pathrows=[paths.get(ii(pid),{}) for pid in isl.get('paths',[])]; pathrows=[x for x in pathrows if x]
  dragons=[]
  for p in pathrows:
   did=ii(p.get('dragon_type')); d=items.get(did,{})
   if did<=0: continue
   name=lx(loc,f'tid_unit_{did}_name',f'Dragon {did}'); img=str(d.get('img_name_mobile') or d.get('img_name') or '')
   dragons.append({'id':did,'dragon_id':did,'kind':'dragon','name':name,'dragon_rarity':str(d.get('dragon_rarity') or '').upper(),'img_name_mobile':img,'image_candidates':dragon_cands(img),'path_id':ii(p.get('id'))})
  # Maze node reward IDs are the same IDs used by maze_island.rewards.
  node_ids=[]
  for p in pathrows: node_ids.extend(ii(x) for x in p.get('nodes',[]) if ii(x)>0)
  event_items={}; special_chests={}
  for nid in node_ids:
   rr=rewards.get(nid,{})
   for bundle in rr.get('reward',[]) if isinstance(rr.get('reward'),list) else []:
    if not isinstance(bundle,dict): continue
    if 'b' in bundle:
     vals=bundle['b'] if isinstance(bundle['b'],list) else [bundle['b']]
     for raw in vals:
      bid=ii(raw); b=items.get(bid,{})
      name=lx(loc,f'tid_building_{bid}_name',str(b.get('name') or f'Item {bid}')); img=str(b.get('img_name_mobile') or b.get('img_name') or '')
      rec=event_items.setdefault(bid,{'id':bid,'item_id':bid,'kind':'item','name':name,'group_type':str(b.get('group_type') or ''),'img_name_mobile':img,'image_candidates':item_cands(img),'tile_count':0});rec['tile_count']+=1
    if 'chest' in bundle:
     vals=bundle['chest'] if isinstance(bundle['chest'],list) else [bundle['chest']]
     for raw in vals:
      cid=ii(raw); ch=chests.get(cid,{})
      name=lx(loc,ch.get('chest_name_key'),lx(loc,ch.get('type_name_key'),f'Chest {cid}'))
      if name in EXCLUDED or cid in ORDINARY_CHEST_IDS: continue
      img=str(ch.get('img_name') or '')
      target=event_items if cid in EVENT_ITEM_CHEST_IDS else special_chests
      rec=target.setdefault(cid,{'id':cid,'chest_id':cid,'source_chest_id':cid,'kind':'chest','name':name,'img_name':img,'source_chest_img_name':img,'image_candidates':chest_cands(cid,img),'tile_count':0});rec['tile_count']+=1
  start=ii((isl.get('availability') or {}).get('from')); end=ii((isl.get('availability') or {}).get('to'))
  title=lx(loc,isl.get('tid_name'),'Maze Island')
  internal=str(isl.get('name') or '')
  # Internal name usually carries the event theme and is useful when generic localization says "Maze Island".
  display=internal.replace('Maze Island - ','').strip() if internal else title
  if display and 'maze' not in display.lower(): display += ' Maze Island'
  out.append({'id':iid,'name':display or title,'localization_title':title,'internal_name':internal,'start_ts':start,'end_ts':end,'start_iso':iso(start),'end_iso':iso(end),'currency_id':ii(isl.get('currency_id')),'initial_points':ii(isl.get('initial_points')),'pool_size':ii(isl.get('pool_size')),'pool_time':ii(isl.get('pool_time')),'min_level':ii(isl.get('min_level')),'path_count':len(pathrows),'rewards_summary':{'dragons':dragons,'event_items':list(event_items.values()),'special_chests':list(special_chests.values())}})
 out.sort(key=lambda x:(x['start_ts'],x['id']))
 payload={'schema_version':1,'generated_at':datetime.now(timezone.utc).isoformat().replace('+00:00','Z'),'meta':{'count':len(out)},'islands':out}
 dump(OUT,payload); print('Wrote',OUT.name,len(out),'islands')
if __name__=='__main__': main()
