#!/usr/bin/env python3
import argparse, json, math, time
from pathlib import Path
from datetime import datetime, timezone, timedelta

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

# Historical Alliance Chest archive corrections. The live config is mutable: old
# schedule blocks can be removed when a newer cycle is inserted, and old Breeding
# reward references can be overwritten. Keep corrections narrow and evidence-based.
DC_ARCHIVE_TZ=timezone(timedelta(hours=7))

def archive_ts(value):
    # Archive dates below are written in the same UTC+7 wall-clock time used by DCIC.
    return int(datetime.fromisoformat(value).replace(tzinfo=DC_ARCHIVE_TZ).timestamp())

HISTORICAL_REPEAT_WINDOWS=[
    # Apr 2019-Mar 2020: the 2-week Week 39-40 block repeated continuously until
    # the next explicit anchor on Mar 30, 2020. This is strongly corroborated by
    # contemporary screenshots throughout 2019 (Hatch/Arena/League/Breed dates).
    # Unlike the shorter windows below, this one tiles the whole source block.
    {'source_start':archive_ts('2019-04-01T23:00:00'),'source_end':archive_ts('2019-04-15T23:00:00'),
     'target_start':archive_ts('2019-04-15T23:00:00'),'target_end':archive_ts('2020-03-30T23:00:00'),
     'repeat_pattern':True,'archive_cycle':'2019_classic_repeat'},
    # Cycle 3 repeated after its first block and was cut when Cycle 4 arrived.
    {'source_start':archive_ts('2021-02-01T23:00:00'),'source_end':archive_ts('2021-05-31T23:00:00'),
     'target_start':archive_ts('2021-05-31T23:00:00'),'target_end':archive_ts('2021-06-08T23:00:00'),'archive_cycle':3},
    # Cycle 5 repeated until Cycle 6 replaced it.
    {'source_start':archive_ts('2021-10-04T23:00:00'),'source_end':archive_ts('2022-01-31T23:00:00'),
     'target_start':archive_ts('2022-01-31T23:00:00'),'target_end':archive_ts('2022-02-08T23:00:00'),'archive_cycle':5},
    # The first Cycle 12 block continued through the gap before the next configured block.
    {'source_start':archive_ts('2024-01-22T23:00:00'),'source_end':archive_ts('2024-05-20T23:00:00'),
     'target_start':archive_ts('2024-05-20T23:00:00'),'target_end':archive_ts('2024-06-18T23:00:00'),'archive_cycle':12},
]

HISTORICAL_BREEDING_ORB_OVERRIDES=[
    # June 2025 still used the Cycle 15 featured dragons. Preserve the current
    # chest IDs/economy and replace only the featured Breeding dragon reward.
    {'start_ts':archive_ts('2025-06-01T00:00:00'),'end_ts':archive_ts('2025-07-01T00:00:00'),'archive_cycle':15,
     'dragons':{
         'E':{'dragon_id':2055,'name':'Frilled Dragon','rarity':'E'},
         'L':{'dragon_id':3099,'name':'Duo-Damp Dragon','rarity':'L'},
     }},
]

# Resource reward history is also mutable in the live config.  The 2021 snapshot
# preserves the older Food / Trade Essence / Joker Orb economy, while Mythical
# rewards are known to have been added to Alliance Chests only in late May 2024.
LEGACY_RESOURCE_REWARD_END=archive_ts('2023-01-31T23:00:00')
MYTHICAL_ALLIANCE_START=archive_ts('2024-05-25T23:00:00')


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

def repeat_occurrence_window(occurrences, spec):
    """Restore an evidence-backed historical repeat into a removed config gap.

    By default the source block is copied once. If ``repeat_pattern`` is true, the
    complete source interval is tiled repeatedly until ``target_end``. Only the
    schedule/chest IDs are copied; reward metadata is resolved later from the copied
    chest ID so the historical chest economy is preserved.
    """
    source_start=int(spec['source_start']); source_end=int(spec['source_end'])
    target_start=int(spec['target_start']); target_end=int(spec['target_end'])
    if source_end<=source_start or target_end<=target_start:
        return []

    source_rows=[x for x in sorted(occurrences,key=lambda x:x['start_ts'])
                 if source_start <= int(x['start_ts']) < source_end]
    if not source_rows:
        return []

    pattern_len=source_end-source_start
    tile=bool(spec.get('repeat_pattern'))
    repeat_starts=[]
    if tile:
        cycle_start=target_start
        while cycle_start < target_end:
            repeat_starts.append(cycle_start)
            cycle_start += pattern_len
    else:
        repeat_starts=[target_start]

    out=[]
    for repeat_index,cycle_start in enumerate(repeat_starts,1):
        shift=cycle_start-source_start
        for original in source_rows:
            ns=int(original['start_ts'])+shift
            ne=int(original['end_ts'])+shift
            if ns>=target_end:
                continue
            # Do not manufacture partial missions at the end of a reconstructed
            # window. A mission is copied only when its full historical duration fits
            # before the next confirmed anchor.
            if ne>target_end or ne<=target_start or ns<target_start:
                continue
            row=dict(original)
            row['start_ts']=ns; row['end_ts']=ne
            row['schedule_source']='historical_repeat'
            row['cycle_repeat']=repeat_index
            row['archive_cycle']=spec.get('archive_cycle')
            row['historical_source_start_ts']=int(original['start_ts'])
            row['historical_source_end_ts']=int(original['end_ts'])
            if tile:
                row['historical_repeat_index']=repeat_index
            out.append(row)
    return out


def build_dragon_reward_history(missions):
    """Derive modern Epic + Legendary featured-dragon periods from Breeding missions.

    The archive mission list is already corrected for evidence-backed historical
    repeats/overrides, so history should be derived from those mission rewards rather
    than duplicating dragon names or cycle tables in the webpage.
    """
    rows=[]
    current=None
    for item in sorted(missions,key=lambda x:(int(x.get('start_ts') or 0),int(x.get('end_ts') or 0))):
        if str(item.get('activity') or '')!='BREEDING':
            continue
        reward=item.get('highlighted_reward') or {}
        if reward.get('type')!='orbs':
            continue
        dragon_id=int(reward.get('dragon_id') or 0)
        rarity=str(reward.get('rarity') or '').upper()
        if not dragon_id or rarity not in ('E','L'):
            continue
        start_ts=int(item.get('start_ts') or 0)
        end_ts=int(item.get('end_ts') or start_ts)

        # Modern Alliance Chest rotations introduce the Epic member first. A new
        # Epic ID therefore marks the next featured pair. Older pre-modern rows that
        # only contain Legendary rewards are naturally ignored.
        if rarity=='E':
            if current is None:
                current={'start_ts':start_ts,'end_ts':end_ts,'epic_dragon_id':dragon_id,'legendary_dragon_id':None}
            elif int(current.get('epic_dragon_id') or 0)!=dragon_id:
                if current.get('epic_dragon_id') and current.get('legendary_dragon_id'):
                    rows.append(current)
                current={'start_ts':start_ts,'end_ts':end_ts,'epic_dragon_id':dragon_id,'legendary_dragon_id':None}
            else:
                current['end_ts']=max(int(current.get('end_ts') or 0),end_ts)
        elif current is not None:
            current_legendary=int(current.get('legendary_dragon_id') or 0)
            if current_legendary in (0,dragon_id):
                current['legendary_dragon_id']=dragon_id
                current['end_ts']=max(int(current.get('end_ts') or 0),end_ts)

    if current and current.get('epic_dragon_id') and current.get('legendary_dragon_id'):
        rows.append(current)

    for row in rows:
        row['source']='derived_from_breeding_rewards'
    return list(reversed(rows))

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
    reward_history=load_json(args.reward_history,{}) or {}
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
    historical_static_by={}
    for x in reward_history.get('static_rewards') or []:
        historical_static_by.setdefault(int(x['gatcha_id']),[]).append(x)

    def highest_level(c):
        ls=level_sets.get(int(c.get('level_set') or 0),[])
        return max([int(x.get('level') or 0) for x in ls] or [6])

    def gatcha_ids_for_level(c, level):
        rows=reward_sets.get(int(c.get('reward_set') or 0),[])
        row=next((x for x in rows if int(x.get('level') or 0)==level),None)
        return [int(x) for x in ((row or {}).get('gatcha_ids') or [])]

    def find_static(c, pred, static_provider=None):
        lv=highest_level(c)
        provider=static_provider or (lambda gid: static_by.get(gid,[]))
        for gid in gatcha_ids_for_level(c,lv):
            for row in provider(gid):
                res=row.get('resource') or {}
                val=pred(res,row)
                if val is not None: return val,row,gid
        return None,None,None

    def highlight(c, static_provider=None):
        activity=str(c.get('activity') or '')
        typ=(ACTIVITY_META.get(activity) or {}).get('highlight') or 'food'
        result={'type':typ,'label':{'gems':'Gems','food':'Food','joker_orbs':'Joker Orbs','orbs':'Orbs'}.get(typ,typ.replace('_',' ').title()),
                'amount':None,'image_url':HIGHLIGHT_ICONS.get(typ),'level_scaled':False,'dragon_id':None,'rarity':None,'reference_tier_index':2}
        if typ=='gems':
            found,row,gid=find_static(c,lambda res,row: res.get('c') if 'c' in res else None,static_provider)
            if found is not None: result['amount']=found
        elif typ=='food':
            found,row,gid=find_static(c,lambda res,row: res.get('f') if 'f' in res else None,static_provider)
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
            found,row,gid=find_static(c,joker,static_provider)
            if found:
                result['amount']=found.get('amount')
                result['rarity']=found.get('rarity')
            # Per the game-facing homepage pattern requested by DCIC, use the generic
            # Joker Orb highlight even when a newer reward-set revision has no JO row.
        elif typ=='orbs':
            def seeds(res,row):
                vals=res.get('seeds') or []
                return vals[0] if vals else None
            found,row,gid=find_static(c,seeds,static_provider)
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

    def preview_rewards(c, highlighted, static_provider=None):
        """Compact Level-VI reward preview for the homepage card.

        The first entry is always the game-facing highlighted reward. Remaining
        entries are actual static rewards from the featured Alliance Chest level.
        This intentionally does not replace Chest Details; it is only a preview.
        """
        out=[]
        provider=static_provider or (lambda gid: static_by.get(gid,[]))
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
            for sr in provider(gid):
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

    # Restore only historically confirmed repeat windows that have disappeared from
    # the mutable current config. These are deliberately explicit rather than a
    # blanket gap filler, because older Alliance Chest history contains real gaps.
    configured_occurrences=list(occurrences)
    for spec in HISTORICAL_REPEAT_WINDOWS:
        occurrences.extend(repeat_occurrence_window(configured_occurrences,spec))

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

    def apply_historical_breeding_orb_override(item):
        if item.get('activity')!='BREEDING':
            return item
        for spec in HISTORICAL_BREEDING_ORB_OVERRIDES:
            if not (int(spec['start_ts']) <= int(item['start_ts']) < int(spec['end_ts'])):
                continue
            current=item.get('highlighted_reward') or {}
            rarity=str(current.get('rarity') or '').upper()
            target=(spec.get('dragons') or {}).get(rarity)
            if not target:
                return item
            did=int(target['dragon_id'])
            # If the current config already carries the historically correct dragon,
            # leave it as config-sourced instead of marking a no-op as an override.
            if int(current.get('dragon_id') or 0)==did:
                item['featured_reward_source']='config'
                return item
            dragon=dragon_by_id.get(did) or {}
            name=dragon.get('name') or target.get('name') or f'Dragon {did}'
            target_rarity=dragon.get('rarity') or target.get('rarity') or rarity
            dragon_image=dragon.get('adult_image') or dragon.get('thumbnail') or dragon.get('full_body_image')

            # Preserve amount, chest ID, required points and all non-dragon rewards.
            hi=dict(current)
            hi.update({'dragon_id':did,'dragon_name':name,'dragon_image':dragon_image,
                       'rarity':target_rarity,'image_url':orb_icon(target_rarity)})
            item['highlighted_reward']=hi

            preview=[]
            for reward in item.get('preview_rewards') or []:
                r=dict(reward)
                if r.get('type')=='orbs':
                    r.update({'dragon_id':did,'dragon_name':name,'dragon_image':dragon_image,
                              'rarity':target_rarity,'image_url':orb_icon(target_rarity),
                              'label':str(name).removesuffix(' Dragon')+' Orbs'})
                preview.append(r)
            item['preview_rewards']=preview
            item['featured_reward_source']='historical_override'
            item['archive_cycle']=spec.get('archive_cycle')
            return item
        item['featured_reward_source']='config'
        return item

    def apply_historical_resource_rewards(item):
        """Resolve time-correct Food/Essence/Joker rewards for an occurrence.

        The live config mutates shared gatcha IDs, so old occurrences otherwise inherit
        today's quantities.  Before the Jan-31-2023 Alliance Chest overhaul, prefer
        static reward rows preserved in alliance_chest_reward_history.json (derived
        from the Mar-21-2021 config snapshot) whenever the same gatcha ID existed there.  Missing snapshot rows (typically featured-dragon
        gatchas created later) fall back to the current config so dragon identity is
        preserved.  Mythical rewards are removed before the reconstructed May-25-2024
        Alliance-Chest introduction boundary.
        """
        start_ts=int(item.get('start_ts') or 0)
        cid=int(item.get('chest_id') or 0)
        c=chests.get(cid)
        if not c:
            return item

        used_snapshot=False
        if start_ts < LEGACY_RESOURCE_REWARD_END and historical_static_by:
            def provider(gid):
                nonlocal used_snapshot
                old_rows=historical_static_by.get(int(gid)) or []
                if old_rows:
                    used_snapshot=True
                    return old_rows
                return static_by.get(int(gid),[])
            hi=highlight(c,provider)
            # Keep an already-correct featured Breeding dragon if the snapshot does
            # not know that later cycle; provider() falls back to current for it.
            item['highlighted_reward']=hi
            item['preview_rewards']=preview_rewards(c,hi,provider)
            if used_snapshot:
                item['resource_reward_source']='historical_snapshot_2021-03-21'
            else:
                item['resource_reward_source']='current_config'
        else:
            item['resource_reward_source']='current_config'

        if start_ts < MYTHICAL_ALLIANCE_START:
            before=len(item.get('preview_rewards') or [])
            item['preview_rewards']=[r for r in (item.get('preview_rewards') or [])
                                     if str(r.get('rarity') or '').upper()!='M']
            after=len(item.get('preview_rewards') or [])
            if after!=before:
                item['mythical_reward_cutoff_applied']=True
                if item.get('resource_reward_source')=='current_config':
                    item['resource_reward_source']='current_config_without_mythical'
        return item

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
        item=apply_historical_resource_rewards(item)
        item=apply_historical_breeding_orb_override(item)
        item['occurrence_id']=f"{item['start_ts']}-{item['chest_id']}"
        enriched.append(item)

    dragon_reward_history=build_dragon_reward_history(enriched)

    payload={
        'schema_version':5,
        'generated_at':datetime.now(timezone.utc).isoformat().replace('+00:00','Z'),
        'meta':{
            'mission_occurrences':len(enriched),
            'alliance_chests':len(chests),
            'latest_cycle_start_ts':base_start,
            'latest_config_end_ts':config_end,
            'repeat_cycle_weeks':(block_len//WEEK if block_len else 0),
            'repeat_rule':'Repeat the latest configured Alliance Chest cycle once when no newer cycle is available.',
            'historical_repeat_windows':len(HISTORICAL_REPEAT_WINDOWS),
            'historical_reward_overrides':len(HISTORICAL_BREEDING_ORB_OVERRIDES),
            'legacy_resource_reward_end_ts':LEGACY_RESOURCE_REWARD_END,
            'historical_reward_dataset':Path(args.reward_history).name,
            'legacy_resource_snapshot':'2021-03-21',
            'mythical_alliance_start_ts':MYTHICAL_ALLIANCE_START,
            'resource_reward_rule':'Use the compact historical reward dataset derived from the 2021 snapshot for matching legacy resource gatchas before the 2023 overhaul; remove Mythical Alliance rewards before May 25, 2024.',
            'dragon_reward_history_pairs':len(dragon_reward_history),
            'archive_rule':'Restore only evidence-backed historical repeats and reward overrides; do not blanket-fill uncertain transition gaps.',
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
        'dragon_reward_history':dragon_reward_history,
        'missions':enriched,
    }
    Path(args.output).write_text(json.dumps(payload,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
    return payload

if __name__=='__main__':
    ap=argparse.ArgumentParser()
    ap.add_argument('--game-config',default='game_config.json')
    ap.add_argument('--reward-history',default='alliance_chest_reward_history.json')
    ap.add_argument('--localization',default='localization/dragon_city_localization_baseline_en.json')
    ap.add_argument('--chests',default='chests.json')
    ap.add_argument('--dragons',default='dragons.json')
    ap.add_argument('--output',default='alliance_chest.json')
    ap.add_argument('--future-days',type=int,default=370)
    ap.add_argument('--now',type=int,default=None)
    args=ap.parse_args()
    p=build(args)
    print(f"Wrote {args.output}: {len(p['missions'])} mission occurrences, latest cycle {p['meta']['repeat_cycle_weeks']} weeks")
