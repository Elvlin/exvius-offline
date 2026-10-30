"""Offline raid progress. Battle stats and personal milestone thresholds are unchanged.
Original personal rewards use the native damage report and the served boss HP.
Shared HP budgets and target solo clears are authored local pacing choices.
"""
import copy
import json
import os
import threading
from pathlib import Path

_LOCK = threading.RLock()
_PERSONAL_EVENTS = None


def integer(value, name, minimum=1, maximum=10**15):
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError(name + ' is outside the supported integer range')
    return value


def validate_config(config):
    if not isinstance(config, dict) or config.get('version') != 1 or not isinstance(config.get('events'), list):
        raise ValueError('raid config must contain version 1 and events list')
    seen_events, seen_missions = set(), set()
    for event in config['events']:
        if not isinstance(event, dict):raise ValueError('event definition must be an object')
        if not isinstance(event.get('shared_milestones',[]),list):raise ValueError('shared milestones must be a list')
        eid = event.get('event_id')
        if type(eid) not in (str, int) or not str(eid).isdigit() or str(eid) in seen_events:
            raise ValueError('event IDs must be unique numeric source IDs')
        seen_events.add(str(eid))
        mids = event.get('mission_ids')
        if not isinstance(mids, list) or not mids or not all(type(x) in (str, int) and str(x).isdigit() for x in mids):
            raise ValueError('explicit numeric mission IDs are required')
        if len(set(map(str,mids))) != len(mids) or seen_missions.intersection(map(str,mids)):
            raise ValueError('a mission cannot belong to multiple configured raids')
        seen_missions.update(map(str,mids))
        integer(event.get('original_shared_goal'), 'original shared goal')
        integer(event.get('target_solo_clears'), 'authored target solo clears', maximum=1000000)
        if not isinstance(event.get('source'), str) or not event['source'].strip():
            raise ValueError('original event/goal source reference required')
        ids=set()
        for m in event.get('shared_milestones', []):
            if not isinstance(m,dict) or not str(m.get('id','')).strip() or str(m['id']) in ids:
                raise ValueError('unique shared milestone IDs required')
            ids.add(str(m['id']))
            integer(m.get('threshold'), 'shared milestone threshold', maximum=event['original_shared_goal'])
            if not isinstance(m.get('rewards'), list):raise ValueError('original shared reward list required')
            if m.get('scope') != 'shared':raise ValueError('only explicitly shared milestones may be scaled')
    return config


def local_threshold(event, original_threshold):
    """Ceiling preserves reachability/order without early fractional claims."""
    goal=event['original_shared_goal'];target=event['target_solo_clears']
    return (original_threshold*target+goal-1)//goal


def event_definition_hash(event):
    import hashlib
    return hashlib.sha256(json.dumps(event,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def record_completion(state, config, mission_id, completion_id, success):
    validate_config(config)
    if success is not True:return {'credited':False,'reason':'not a successful clear'}
    event=next((e for e in config['events'] if str(mission_id) in set(map(str,e['mission_ids']))),None)
    if event is None:return {'credited':False,'reason':'mission not mapped to a configured raid'}
    if not isinstance(completion_id,str) or not completion_id or len(completion_id)>200:
        raise ValueError('bounded nonempty completion ID required')
    with _LOCK:
        # Work on a private copy, so validation/definition mismatch never partly mutates state.
        ledger=copy.deepcopy(state.get('exvius_raid_progress',{'version':1,'events':{}}))
        if ledger.get('version')!=1:raise ValueError('unknown ledger version')
        eid=str(event['event_id']);definition=event_definition_hash(event)
        saved=ledger['events'].setdefault(eid,{'definition_sha256':definition,'clears':0,'completion_ids':[],'claimed_shared_milestones':[]})
        if saved['definition_sha256']!=definition:
            raise ValueError('raid definition changed; explicit migration/reset required, not silently rescaled')
        if completion_id in saved['completion_ids']:
            return {'credited':False,'reason':'duplicate completion','clears':saved['clears']}
        saved['clears']+=1;saved['completion_ids'].append(completion_id)
        state['exvius_raid_progress']=ledger
        return {'credited':True,'event_id':eid,**progress_view(event,saved)}


def progress_view(event,saved):
    clears=saved['clears'];goal=event['original_shared_goal'];target=event['target_solo_clears']
    return {'clears':clears,'target_solo_clears':target,
            'equivalent_shared_progress':min(goal,clears*goal//target),
            'eligible_shared_milestones':[str(m['id']) for m in event.get('shared_milestones',[])
                if clears>=local_threshold(event,m['threshold']) and str(m['id']) not in saved['claimed_shared_milestones']],
            'combat_modified':False,'personal_rewards_modified':False}


def claim_shared_milestone(state,config,event_id,milestone_id):
    """Explicit ledger-only claim returns ORIGINAL reward content, never credits inventory.
    A future server grant bridge must atomically grant and mark in the same save.
    This function is not wired into the client and is not a pretend wire response.
    """
    validate_config(config)
    with _LOCK:
        event=next((e for e in config['events'] if str(e['event_id'])==str(event_id)),None)
        saved=state.get('exvius_raid_progress',{}).get('events',{}).get(str(event_id))
        if event is None or saved is None:return []
        if saved['definition_sha256']!=event_definition_hash(event):raise ValueError('raid definition changed')
        m=next((m for m in event.get('shared_milestones',[]) if str(m['id'])==str(milestone_id)),None)
        if m is None or saved['clears']<local_threshold(event,m['threshold']) or str(milestone_id) in saved['claimed_shared_milestones']:return []
        rewards=copy.deepcopy(m['rewards'])
        saved['claimed_shared_milestones'].append(str(milestone_id))
        return rewards


def save_state(path,state):
    """Atomic standalone save; use one writer. Runtime uses upstream PlayerState save instead."""
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True);tmp=path.with_name(path.name+'.tmp')
    with tmp.open('w',encoding='utf-8') as f:
        json.dump(state,f,indent=2);f.flush();os.fsync(f.fileno())
    os.replace(tmp,path)


def credit_configured_raid(player,mission_id,completion_id,success,data_root):
    """Runtime seam after an accepted mission completion; disabled without explicit mapping."""
    if player.mode=='frozen' or not data_root:return False
    path=Path(data_root)/'state/exvius_raids.json'
    if not path.exists():return False
    config=json.loads(path.read_text(encoding='utf-8'))
    result=record_completion(player.data,config,mission_id,completion_id,success)
    if result['credited']:player.dirty=True
    return result['credited']


def personal_event(mission_id=None, dungeon_id=None):
    """Only events whose original reward table has been recovered are supported."""
    global _PERSONAL_EVENTS
    if _PERSONAL_EVENTS is None:
        missions, dungeons = {}, {}
        for filename in ('raid_rewards.json', 'raid_archive.json'):
            path = Path(__file__).with_name(filename)
            if not path.exists():
                continue
            for event in json.loads(path.read_text(encoding='utf-8')).get('events', []):
                for mid in event['mission_points']:
                    if str(mid) in missions:
                        raise ValueError('Raid mission belongs to multiple events')
                    missions[str(mid)] = event
                for did in {event['dungeon_id'], event['event_id'], *event.get('dungeon_ids', [])}:
                    dungeons[str(did)] = event
        _PERSONAL_EVENTS = missions, dungeons
    missions, dungeons = _PERSONAL_EVENTS
    return missions.get(str(mission_id)) if mission_id is not None else dungeons.get(str(dungeon_id))


def observe_personal_raid(player, mission_id, spec):
    """Keep the actual encounter HP, so scoring never assumes a different boss profile."""
    event = personal_event(mission_id=mission_id)
    if event is None:
        return
    parts = spec.get('bV34YIJQ', [])
    groups = spec.get('Bi6hVv34', [])
    profiles = {row['xqartN26']: row for row in parts}
    if not groups or any(row['xqartN26'] not in profiles for row in groups):
        raise ValueError('unsupported raid encounter shape')
    hp = sum(int(profiles[row['xqartN26']]['fh31sk7B']) for row in groups)
    if hp <= 0:
        raise ValueError('raid boss HP must be positive')
    attempt = player.data.get('exvius_repeat', {}).get('attempt', {})
    if attempt.get('mid') == str(mission_id) and attempt.get('status') == 'pending':
        attempt['raid_boss_hp'] = hp
        player.dirty = True


def _personal_state(player, event):
    return player.data.get('exvius_raid_progress', {}).get('personal_events', {}).get(event['event_id'], {})


def record_party_action(player, actor, skill, party):
    """Record distinct native actors for King Mog's original secret sequence.

    The ordinary mission report counts skills without actor identities, so it
    cannot establish that every party member performed the required action.
    This narrow bridge receives the actual battle party and native skill log.
    """
    if player is None or player.mode == 'frozen':
        return False
    attempt = player.data.get('exvius_repeat', {}).get('attempt', {})
    if attempt.get('status') != 'pending':
        return False
    event = personal_event(mission_id=attempt.get('mid'))
    unlock = (event or {}).get('special_unlock', {})
    abilities = unlock.get('abilities', [])
    if attempt.get('mid') != unlock.get('mission_id') or skill not in abilities:
        return False
    if (not isinstance(party, list) or not 1 <= len(party) <= 6 or
            any(not isinstance(i, str) or not i.isdigit() for i in party) or
            len(set(party)) != len(party) or actor not in party):
        return False
    from ffbe_friends import load_friends
    roster = {str(u['instance_id']) for u in player.data['roster']}
    friends = {str(f['instance_id']) for f in load_friends()}
    own = set(party) & roster
    if not own or set(party) - roster - friends or len(set(party) - roster) > 1:
        return False
    # The live party must match the selected deck, with at most one companion.
    deck = next(d for d in player.data['party']['decks']
                if d['id'] == player.data['party']['active_deck'])
    selected = {str(m['instance_id']) for m in deck['members']
                if str(m['instance_id']) in roster}
    if own != selected:
        return False
    ledger = attempt.get('king_mog_sequence')
    if ledger is None:
        if skill != abilities[0]:
            return False
        ledger = {'party': sorted(party), 'first': [], 'second': []}
        attempt['king_mog_sequence'] = ledger
    if ledger['party'] != sorted(party):
        return False
    phase = 'first' if skill == abilities[0] else 'second'
    if phase == 'second' and set(ledger['first']) != set(party):
        return False
    if actor in ledger[phase]:
        return False
    ledger[phase].append(actor)
    player.dirty = True
    return True


def complete_secret_unlock(player, mission_id):
    event = personal_event(mission_id=mission_id)
    unlock = (event or {}).get('special_unlock', {})
    attempt = player.data.get('exvius_repeat', {}).get('attempt', {})
    ledger = attempt.get('king_mog_sequence', {})
    party = set(ledger.get('party', []))
    # The original unlock also permits escaping after the sequence.
    if (str(mission_id) != unlock.get('mission_id') or attempt.get('mid') != str(mission_id) or
            attempt.get('status') != 'completed' or not party or
            set(ledger.get('first', [])) != party or set(ledger.get('second', [])) != party):
        return False
    from player_state import switch_position
    position = switch_position(unlock['switch_id'])
    if position is None:
        raise ValueError('Original King Mog unlock switch is missing')
    stype, index = position
    if int(index) in player.switches.get(str(stype), set()):
        return False
    player.grant_switch(stype, index)
    return True


def personal_menu_groups(player, event):
    saved = _personal_state(player, event)
    budget = int(event['solo_pacing']['shared_hp_per_level'])
    damage = int(saved.get('shared_damage', 0))
    level = damage // budget + 1
    return {
        'dg5ZV3kQ': [{'xfirgH86': event['name'] + ' (Solo)', 'R01Wz7fe': str(level),
                     '7DTnc2Lt': event['menu_background'],
                     'F4gkm9Rt': str((level - 1) * event['level_bonus_percent']),
                     'K3P1jcu7': str(damage % budget), 'Yc8Mm6y7': str(budget),
                     'Mmex5dU8': '2147483647'}],
        # GateMissionScene reads +0x24 for RAID_RANKING_VALUE, +0x28 for RAID_POINT_VALUE.
        '71ctQHWm': [{'52ibRBqw': '1', 'UbQ26oH4': str(saved.get('points', 0))}],
    }


def personal_raid_menu(spec, request):
    from ffbe_state import State
    rows = request.get('3uy7DzGB', [])
    event = personal_event(dungeon_id=rows[0].get('U9iHsau3')) if rows else None
    if event is None or State.player is None:
        return spec
    out = dict(spec)
    out.update(personal_menu_groups(State.player, event))
    return out


def apply_personal_raid_result(player, spec, mission_id, plaintext):
    """Credit native reported damage once per accepted attempt, and mail crossed milestones.

    ArchieveResultInfo::getTotalDamage uses TOTAL_DAMAGE. Its toJsonGroup emits
    nSG9Jb1s rows with NYb0Cri6 (metric name), 6gAX1BpC (plain integer value).
    A loss can earn points, as in the original raid. Overkill is capped at boss HP.
    """
    if player.mode == 'frozen':
        return spec
    event = personal_event(mission_id=mission_id)
    attempt = player.data.get('exvius_repeat', {}).get('attempt', {})
    if (event is None or attempt.get('mid') != str(mission_id) or
            attempt.get('status') != 'completed' or not attempt.get('raid_boss_hp')):
        return spec
    receipt_id = str(attempt['sequence'])
    saved = _personal_state(player, event)
    receipt = saved.get('receipts', {}).get(receipt_id)
    if receipt is None:
        request = json.JSONDecoder().raw_decode(plaintext)[0]
        reports = [r.get('6gAX1BpC') for r in request.get('nSG9Jb1s', [])
                   if r.get('NYb0Cri6') == 'TOTAL_DAMAGE']
        if len(reports) != 1 or not str(reports[0]).isdigit():
            return spec
        damage = int(reports[0])
        if damage > 2**63 - 1:
            raise ValueError('raid damage exceeds the native signed 64-bit range')
        with _LOCK:
            existing = _personal_state(player, event).get('receipts', {}).get(receipt_id)
            if existing is not None:
                return _personal_result_reply(player, event, spec, existing)
            before, dirty_before = copy.deepcopy(player.data), player.dirty
            try:
                ledger = player.data.setdefault('exvius_raid_progress', {'version': 1, 'events': {}})
                saved = ledger.setdefault('personal_events', {}).setdefault(event['event_id'], {
                    'points': 0, 'shared_damage': 0, 'receipts': {}, 'mailed_milestones': []})
                hp = int(attempt['raid_boss_hp'])
                effective = min(damage, hp)
                base = int(event['mission_points'][str(mission_id)]) * effective // hp
                budget = int(event['solo_pacing']['shared_hp_per_level'])
                level = saved['shared_damage'] // budget + 1
                rate = (level - 1) * int(event['level_bonus_percent'])
                bonus = base * rate // 100
                points = base + bonus
                coin = event.get('raid_coin')
                coins = points // int(event['points_per_coin']) if coin else 0
                if coins:
                    reward = {'kind': coin['kind'], 'id': coin['id'], 'count': coins}
                    if not player._can_credit(reward) or player._grant_items([reward]) != [reward]:
                        raise ValueError('raid coins cannot be projected')
                saved['points'] += points
                saved['shared_damage'] += effective
                for milestone in event['personal_milestones']:
                    threshold = milestone['points']
                    if threshold > saved['points'] or threshold in saved['mailed_milestones']:
                        continue
                    rewards = milestone.get('rewards') or [milestone['reward']]
                    if any(not player._can_credit(row) for row in rewards):
                        raise ValueError('raid milestone cannot be projected: ' + milestone['label'])
                    mail = player.deliver_mail(event['name'] + ': ' + str(threshold) + ' points',
                        [(row['kind'], row['id'], row['count']) for row in rewards], message=milestone['label'])
                    if mail is None:
                        raise ValueError('raid milestone mail could not be delivered')
                    saved['mailed_milestones'].append(threshold)
                receipt = {'damage': damage, 'base_points': base, 'bonus_points': bonus,
                           'bonus_percent': rate, 'coins': coins}
                saved['receipts'][receipt_id] = receipt
                player.dirty = True
            except Exception:
                player.data, player.dirty = before, dirty_before
                raise
    return _personal_result_reply(player, event, spec, receipt)


def _personal_result_reply(player, event, spec, receipt):
    out = copy.deepcopy(spec)
    for row in out.get('09HRWXDf', []):
        row.update({'7a1Ugx4e': str(receipt['base_points']), 'aK4k1PvY': str(receipt['bonus_points']),
                    'NCFk6Zv1': str(receipt['bonus_percent']), '42dKqYHe': str(receipt['damage'])})
        if receipt['coins']:
            coin = event['raid_coin']
            entry = '%s:%s:%s' % (coin['kind'], coin['id'], receipt['coins'])
            drops = str(row.get('xF9Sr1a6') or '')
            row['xF9Sr1a6'] = drops + (',' if drops else '') + entry
    out.update(personal_menu_groups(player, event))
    return out


def personal_rewards_page(player, dungeon_id):
    """Content for the original raid screen's embedded personal-reward panel."""
    from html import escape
    event = personal_event(dungeon_id=dungeon_id)
    if event is None or player is None:
        return None
    saved = _personal_state(player, event)
    mailed = set(saved.get('mailed_milestones', []))
    points = int(saved.get('points', 0))
    level = int(saved.get('shared_damage', 0)) // event['solo_pacing']['shared_hp_per_level'] + 1
    rows = ''.join('<tr class="%s"><td>%s</td><td>%s%s</td></tr>' % (
        'delivered' if m['points'] in mailed else '', format(m['points'], ','), escape(m['label']),
        '<small>Delivered to mailbox</small>' if m['points'] in mailed else '')
        for m in event['personal_milestones'])
    return ('''<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Raid Rewards</title>
<style>body{margin:0;padding:14px;background:#081d43;color:#fff;font:16px Arial,sans-serif}
h1{font-size:21px;color:#ffe398;margin:0 0 12px}p{line-height:1.5}strong{color:#ffe398}
table{border-collapse:collapse;width:100%;background:#0d2d58}th,td{text-align:left;padding:12px 9px;border:1px solid #4b6990}
th{background:#194875;color:#ffe398}td:first-child{white-space:nowrap}.delivered{background:#173f48}
small{display:block;color:#a9e9cb;margin-top:5px}</style></head><body><h1>''' +
        escape(event['name']) + '</h1><p>Personal points: <strong>' + format(points, ',') +
        '</strong><br>Solo raid level: <strong>' + str(level) +
        '</strong></p><p>Milestone rewards are delivered to your mailbox.</p>' +
        '<table><thead><tr><th>Points</th><th>Reward</th></tr></thead><tbody>' + rows +
        '</tbody></table></body></html>')
