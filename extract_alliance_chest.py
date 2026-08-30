#!/usr/bin/env python3
import argparse, json, math, time
from pathlib import Path
from datetime import datetime, timezone

WEEK=7*86400
DAY=86400
ASSET_RAW='https://raw.githubusercontent.com/chaerulanwarreborn-star/dcic-assets/main/'
CHEST_CDN='https://dci-static-s1.socialpointgames.com/static/dragoncity/mobile/ui/chests/'

ACTIVITY_META={
    'PVP_ARENAS': {'name':'Win Arena Battles','short':'Arenas','highlight':'gems'},
    'HATCHING': {'name':'Hatch Eggs','short':'Hatching','highlight':'food'},
    'PVP_LEAGUES': {'name':'Win League Battles','short':'Leagues','highlight':'joker_orbs'},
    'BREEDING': {'name':'Breed Dragons','short':'Breeding','highlight':'orbs'},
    'GROWING_FOOD': {'name':'Grow Food','short':'Growing Food','highlight':'food'},
    'LEVELING_UP': {'name':'Feed Dragons','short':'Feeding','highlight':'food'},
}

HIGHLIGHT_ICONS={
    'gems': ASSET_RAW+'icons/amount-rss/ic-gems-special.png',
    'food': ASSET_RAW+'icons/amount-rss/ic-food-special.png',
    'joker_orbs': ASSET_RAW+'icons/amount-rss/ic-rarity-orb-special.png',
}

RARITY_FILE={'C':'c','R':'r','V':'vr','VR':'vr','E':'e','L':'l','M':'m','H':'h'}
RARITY_NAMES={'C':'Common','R':'Rare','V':'Very Rare','VR':'Very Rare','E':'Epic','L':'Legendary','M':'Mythical','H':'Heroic'}


def load_json(path, default=None):
    p=Path(path)
    if not p.exists(): return default
    return json.loads(p.read_text(encoding='utf-8'))

def loc_map(path):
    rows=load_json(path,[]) or []
    out={}
    if isinstance(rows,dict): return rows
    for row in rows:
        if isinstance(row,dict): out.update(row)
    return out

def normalize_rarity(r):
    r=str(r or '').strip()
    return {'V':'vr','VR':'vr','vr':'vr'}.get(r,r)

def orb_icon(rarity):
    code=normalize_rarity(rarity) or 'L'
    return ASSET_RAW+f'icons/amount-rss/ic-amount-orbs-{code}.png'

def resolve_week_starts(weeks):
    resolved=[]; prev=None
    for row in weeks:
        row=dict(row)
        ts=row.get('start_ts')
        if ts:
            start=int(ts)
        elif prev is not None:
            start=prev+WEEK
        else:
            continue
        row['_start_ts']=start
        resolved.append(row); prev=start
    return resolved

def day_rows_from_weeks(weeks, source='config', cycle_repeat=0):
    names=['monday','tuesday','wednesday','thursday','friday','saturday','sunday']
    out=[]
    for w in weeks:
        ws=int(w['_start_ts'])
        for i,name in enumerate(names):
            out.append({'start_ts':ws+i*DAY,'end_ts':ws+(i+1)*DAY,'chest_id':int(w.get(name) or 0),
                        'week_id':w.get('id'),'weekday':name,'schedule_source':source,'cycle_repeat':cycle_repeat})
    return out

def merge_days(days):
    days=sorted(days,key=lambda x:x['start_ts'])
    out=[]
    for d in days:
        cid=d['chest_id']
        if not cid: continue
        if out and out[-1]['chest_id']==cid and out[-1]['end_ts']==d['start_ts'] and out[-1]['schedule_source']==d['schedule_source'] and out[-1]['cycle_repeat']==d['cycle_repeat']:
            out[-1]['end_ts']=d['end_ts']; out[-1]['week_ids'].append(d['week_id']); out[-1]['week_ids']=list(dict.fromkeys(out[-1]['week_ids']))
        else:
            out.append({'chest_id':cid,'start_ts':d['start_ts'],'end_ts':d['end_ts'],'week_ids':[d['week_id']],
                        'schedule_source':d['schedule_source'],'cycle_repeat':d['cycle_repeat']})
    return out

def chest_image_fallback(c, level=6):
    asset=str(c.get('asset_name') or '').replace('%d',str(level))
    if not asset: return []
    candidates=[]
    # Modern alliance assets follow ui_basic most often.
    for prefix in ('ui_basic_','ui_',''):
        candidates.append(CHEST_CDN+prefix+asset+'@2x.png')
    return candidates

def build(args):
    cfg=load_json(args.game_config,{}) or {}
    ac=cfg.get('alliance_chest') or {}
    g=cfg.get('gatcha') or {}
    loc=loc_map(args.localization)
    chest_index=load_json(args.chests,{}) or {}
    dragons_payload=load_json(args.dragons,{}) or {}
    dragon_by_id={int(x.get('id')):x for x in (dragons_payload.get('dragons') or []) if x.get('id') is not None}
    summary_by_id={int(x.get('id')):x for x in (chest_index.get('chests') or []) if x.get('type')=='alliance' and x.get('id') is not None}

    chests={int(x['id']):x for x in (ac.get('chests') or [])}
    level_sets={}
    for x in ac.get('level_sets') or []: level_sets.setdefault(int(x['id']),[]).append(x)
    reward_sets={}
    for x in ac.get('reward_sets') or []: reward_sets.setdefault(int(x['id']),[]).append(x)
    gatchas={int(x['id']):x for x in (g.get('gatchas') or [])}
    static_by={}
    for x in g.get('static_rewards') or []: static_by.setdefault(int(x['gatcha_id']),[]).append(x)

    def highest_level(c):
        ls=level_sets.get(int(c.get('level_set') or 0),[])
        return max([int(x.get('level') or 0) for x in ls] or [6])

    def gatcha_ids_for_level(c, level):
        rows=reward_sets.get(int(c.get('reward_set') or 0),[])
        row=next((x for x in rows if int(x.get('level') or 0)==level),None)
        return [int(x) for x in ((row or {}).get('gatcha_ids') or [])]

    def find_static(c, pred):
        lv=highest_level(c)
        for gid in gatcha_ids_for_level(c,lv):
            for row in static_by.get(gid,[]):
                res=row.get('resource') or {}
                val=pred(res,row)
                if val is not None: return val,row,gid
        return None,None,None

    def highlight(c):
        activity=str(c.get('activity') or '')
        typ=(ACTIVITY_META.get(activity) or {}).get('highlight') or 'food'
        result={'type':typ,'label':{'gems':'Gems','food':'Food','joker_orbs':'Joker Orbs','orbs':'Orbs'}.get(typ,typ.replace('_',' ').title()),
                'amount':None,'image_url':HIGHLIGHT_ICONS.get(typ),'level_scaled':False,'dragon_id':None,'rarity':None,'reference_tier_index':2}
        if typ=='gems':
            found,row,gid=find_static(c,lambda res,row: res.get('c') if 'c' in res else None)
            if found is not None: result['amount']=found
        elif typ=='food':
            found,row,gid=find_static(c,lambda res,row: res.get('f') if 'f' in res else None)
            if found is not None:
                result['amount']=found
                result['level_scaled']=bool(row.get('overwritten_tier_multi') not in (None,1,1.0))
                if row.get('overwritten_tier_multi') is not None:
                    raw=row.get('overwritten_tier_multi')
                    result['tier_multiplier_raw']=raw
                    result['tier_multiplier']=(float(raw)/1000000.0 if float(raw)>1000 else float(raw))
        elif typ=='joker_orbs':
            def joker(res,row):
                vals=res.get('rarity_seeds') or []
                return vals[0] if vals else None
            found,row,gid=find_static(c,joker)
            if found:
                result['amount']=found.get('amount')
                result['rarity']=found.get('rarity')
            # Per the game-facing homepage pattern requested by DCIC, use the generic
            # Joker Orb highlight even when a newer reward-set revision has no JO row.
        elif typ=='orbs':
            def seeds(res,row):
                vals=res.get('seeds') or []
                return vals[0] if vals else None
            found,row,gid=find_static(c,seeds)
            if found:
                did=int(found.get('id') or 0); result['dragon_id']=did or None; result['amount']=found.get('amount')
                dragon=dragon_by_id.get(did) or {}
                rarity=dragon.get('rarity')
                result['rarity']=rarity
                result['dragon_name']=dragon.get('name')
                result['dragon_image']=dragon.get('adult_image') or dragon.get('thumbnail') or dragon.get('full_body_image')
                result['image_url']=orb_icon(rarity)
        if not result.get('image_url'):
            result['image_url']=HIGHLIGHT_ICONS['food']
        return result

    def preview_rewards(c, highlighted):
        """Compact Level-VI reward preview for the homepage card.

        The first entry is always the game-facing highlighted reward. Remaining
        entries are actual static rewards from the featured Alliance Chest level.
        This intentionally does not replace Chest Details; it is only a preview.
        """
        out=[]
        first=dict(highlighted or {})
        first['role']='highlighted'
        out.append(first)
        lv=highest_level(c)
        seen=set()

        def add(row):
            if not row or not row.get('image_url'): return
            # Resource identity deliberately excludes the display label. The highlighted
            # Breeding reward may be named simply 'Orbs' while the same static row is
            # later resolved to '<Dragon> Orbs'; those are still the same reward.
            key=(row.get('type'),row.get('rarity'),row.get('dragon_id'),row.get('amount'))
            hk=(first.get('type'),first.get('rarity'),first.get('dragon_id'),first.get('amount'))
            if key==hk: return
            if key in seen: return
            seen.add(key); row['role']='other'; out.append(row)

        for gid in gatcha_ids_for_level(c,lv):
            for sr in static_by.get(gid,[]):
                res=sr.get('resource') or {}
                scaled=bool(sr.get('overwritten_tier_multi') not in (None,1,1.0))
                raw_multi=sr.get('overwritten_tier_multi')
                common_scale={}
                if scaled:
                    common_scale={'level_scaled':True,'reference_tier_index':2}
                    if raw_multi is not None:
                        common_scale['tier_multiplier_raw']=raw_multi
                        common_scale['tier_multiplier']=(float(raw_multi)/1000000.0 if float(raw_multi)>1000 else float(raw_multi))
                if 'c' in res:
                    add({'type':'gems','label':'Gems','amount':res.get('c'),'image_url':HIGHLIGHT_ICONS['gems'],**common_scale})
                if 'f' in res:
                    add({'type':'food','label':'Food','amount':res.get('f'),'image_url':HIGHLIGHT_ICONS['food'],**common_scale})
                if 'keys' in res:
                    add({'type':'keys','label':'Keys','amount':res.get('keys'),'image_url':ASSET_RAW+'icons/text-icons/ic-key-massive.png',**common_scale})
                for x in (res.get('rarity_seeds') or []):
                    r=str(x.get('rarity') or '').upper(); token=RARITY_FILE.get(r,r.lower())
                    add({'type':'joker_orbs','label':RARITY_NAMES.get(r,r)+' Joker Orbs','amount':x.get('amount'),'rarity':r,'image_url':ASSET_RAW+f'icons/tree-of-life/ic-joker-{token}.png'})
                for x in (res.get('trade_tickets') or []):
                    r=str(x.get('rarity') or '').upper(); token=RARITY_FILE.get(r,r.lower())
                    add({'type':'trade_essence','label':RARITY_NAMES.get(r,r)+' Trade Essences','amount':x.get('amount'),'rarity':r,'image_url':ASSET_RAW+f'icons/tree-of-life/ic-trade-orb-big-{token}.png'})
                for x in (res.get('seeds') or []):
                    did=int(x.get('id') or 0); dragon=dragon_by_id.get(did) or {}; rarity=dragon.get('rarity') or (highlighted or {}).get('rarity') or 'L'
                    name=str(dragon.get('name') or 'Dragon').removesuffix(' Dragon')+' Orbs'
                    add({'type':'orbs','label':name,'amount':x.get('amount'),'dragon_id':did or None,'dragon_name':dragon.get('name'),'dragon_image':dragon.get('adult_image') or dragon.get('thumbnail') or dragon.get('full_body_image'),'rarity':rarity,'image_url':orb_icon(rarity)})
        return out

    meta_by_id={}
    for cid,c in chests.items():
        lv=highest_level(c)
        levels=[]
        for lr in sorted(level_sets.get(int(c.get('level_set') or 0),[]),key=lambda x:int(x.get('level') or 0)):
            level=int(lr.get('level') or 0)
            rr=next((x for x in reward_sets.get(int(c.get('reward_set') or 0),[]) if int(x.get('level') or 0)==level),{})
            levels.append({'level':level,'points_required':int(lr.get('points_required') or 0),'gatcha_ids':[int(x) for x in rr.get('gatcha_ids') or []]})
        sm=summary_by_id.get(cid,{})
        candidates=sm.get('image_candidates') or chest_image_fallback(c,lv)
        am=ACTIVITY_META.get(str(c.get('activity') or ''),{})
        activity_name=loc.get(c.get('activity_name_tid')) or sm.get('activity_name') or am.get('name') or str(c.get('activity') or '').replace('_',' ').title()
        hi=highlight(c)
        meta_by_id[cid]={
            'chest_id':cid,'activity':c.get('activity'),'mission_name':activity_name,'mission_short':am.get('short') or activity_name,
            'featured_level':lv,'levels':levels,'featured_points':next((x['points_required'] for x in levels if x['level']==lv),0),
            'chest_name':sm.get('name') or f'{activity_name} Alliance Chest','chest_image_candidates':candidates,
            'highlighted_reward':hi,'preview_rewards':preview_rewards(c,hi),'asset_name':c.get('asset_name'),'reward_set':c.get('reward_set'),'level_set':c.get('level_set')
        }

    resolved=resolve_week_starts(ac.get('weeks') or [])
    days=day_rows_from_weeks(resolved)
    occurrences=merge_days(days)

    # Last explicitly anchored block is the cycle the live game reuses when no newer
    # Alliance Chest cycle is present.  Repeat the whole block after its configured end.
    explicit_indices=[i for i,w in enumerate(resolved) if w.get('start_ts')]
    if explicit_indices:
        last_anchor_i=explicit_indices[-1]
        block=resolved[last_anchor_i:]
        if block:
            base_start=int(block[0]['_start_ts']); block_len=len(block)*WEEK; config_end=base_start+block_len
            # Only generate one fallback repeat of the latest configured cycle.
            # This keeps a single predicted cycle available when no newer config
            # exists, without projecting repeated schedules far into the future.
            repeat_num=1
            cycle_start=config_end
            repeated=[]
            for idx,w in enumerate(block):
                nr=dict(w); nr['_start_ts']=cycle_start+idx*WEEK; repeated.append(nr)
            occurrences.extend(merge_days(day_rows_from_weeks(repeated,'repeated_cycle',repeat_num)))
        else:
            base_start=config_end=block_len=None
    else:
        base_start=config_end=block_len=None

    occurrences=sorted(occurrences,key=lambda x:(x['start_ts'],x['end_ts'],x['chest_id']))
    # remove exact duplicate schedule segments if a future config anchor overlaps a prior inferred week
    uniq=[];seen=set()
    for o in occurrences:
        key=(o['chest_id'],o['start_ts'],o['end_ts'])
        if key in seen: continue
        seen.add(key); uniq.append(o)
    occurrences=uniq

    enriched=[]
    for i,o in enumerate(occurrences):
        m=meta_by_id.get(int(o['chest_id']))
        if not m: continue
        item=dict(o); item.update({k:v for k,v in m.items() if k!='chest_id'})
        item['duration_seconds']=int(item['end_ts']-item['start_ts'])
        # The user-facing Alliance Chest highlight pattern is Arenas=Gems,
        # Hatching=Food, Leagues=Joker Orbs, Breeding=Dragon Orbs.  Some recent
        # Leagues reward sets no longer expose a Joker-Orb row, so preserve the
        # game-facing highlight using the established duration amounts from the
        # Alliance Chest family (2d=3, 3d=4, 4d=6) instead of showing a blank.
        hr=item.get('highlighted_reward') or {}
        if item.get('activity')=='PVP_LEAGUES' and hr.get('amount') is None:
            hr=dict(hr); hr['amount']={2:3,3:4,4:6}.get(max(1,round(item['duration_seconds']/DAY))); item['highlighted_reward']=hr
        item['occurrence_id']=f"{item['start_ts']}-{item['chest_id']}"
        enriched.append(item)

    payload={
        'schema_version':2,
        'generated_at':datetime.now(timezone.utc).isoformat().replace('+00:00','Z'),
        'meta':{
            'mission_occurrences':len(enriched),
            'alliance_chests':len(chests),
            'latest_cycle_start_ts':base_start,
            'latest_config_end_ts':config_end,
            'repeat_cycle_weeks':(block_len//WEEK if block_len else 0),
            'repeat_rule':'Repeat the latest configured Alliance Chest cycle once when no newer cycle is available.',
            'min_user_level':next((int(x.get('value')) for x in ac.get('parameters',[]) if x.get('name')=='MIN_USER_LEVEL' and isinstance(x.get('value'),(int,float))),16),
            'player_level_tiers':next((x.get('value') for x in g.get('parameters',[]) if x.get('name') in ('REWARDS_TIERS','LEVEL_TIERS') and isinstance(x.get('value'),list)),[5,11,17,21,28,35,41,49,74,99,150]),
            'player_level_cap':200,
        },
        'assets':{
            'alliance_grove':ASSET_RAW+'items/buildings/alliance-grove.png',
            'highlight_gems':HIGHLIGHT_ICONS['gems'],
            'highlight_food':HIGHLIGHT_ICONS['food'],
            'highlight_joker_orbs':HIGHLIGHT_ICONS['joker_orbs'],
            'highlight_orbs_base':ASSET_RAW+'icons/amount-rss/ic-amount-orbs-{rarity}.png',
        },
        'activities':ACTIVITY_META,
        'missions':enriched,
    }
    Path(args.output).write_text(json.dumps(payload,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
    return payload

if __name__=='__main__':
    ap=argparse.ArgumentParser()
    ap.add_argument('--game-config',default='game_config.json')
    ap.add_argument('--localization',default='localization/dragon_city_localization_baseline_en.json')
    ap.add_argument('--chests',default='chests.json')
    ap.add_argument('--dragons',default='dragons.json')
    ap.add_argument('--output',default='alliance_chest.json')
    ap.add_argument('--future-days',type=int,default=370)
    ap.add_argument('--now',type=int,default=None)
    args=ap.parse_args()
    p=build(args)
    print(f"Wrote {args.output}: {len(p['missions'])} mission occurrences, latest cycle {p['meta']['repeat_cycle_weeks']} weeks")
