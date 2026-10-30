"""Native Colosseum lifecycle with original rewards and labelled local Advanced rounds.

The original rules are 100 points per win, 50 lost on an ordinary defeat,
and a boss at the round's master threshold. Boss defeats retain the threshold.
Only a recorded start can settle, and a repeated End never pays twice.
"""
import copy
from functools import lru_cache
import json
from pathlib import Path
import secrets

from exvius_actions import _node, _refresh, _mst
from ffbe_state import State, _note


@lru_cache(maxsize=1)
def _encounters():
    document = json.loads(Path(__file__).with_name('colosseum_encounters.json').read_text(encoding='utf8'))
    if document.get('version') != 1:
        raise ValueError('Unsupported Colosseum encounter format')
    return document['rounds']


def _state():
    saved = State.player.data.get('exvius_colosseum')
    if saved is not None:
        return copy.deepcopy(saved)
    first = min(_mst('F_CLSM_PROGRESS_MST.ndjson', 'i5pd8xr3'), key=int)
    model = {'highest': first, 'unlocked': [first], 'rounds': {}, 'sequence': 0, 'active': None}
    _progress(model, first)
    return model


def _progress(model, progress):
    return model['rounds'].setdefault(progress, {
        'points': 0, 'battles': 0, 'wins': 0, 'boss_wins': 0, 'selection': None})


def _masters(progress):
    source = _mst('F_CLSM_PROGRESS_MST.ndjson', 'i5pd8xr3').get(progress)
    round_row = _mst('F_CLSM_ROUND_MST.ndjson', 'LiQ36UFf').get((source or {}).get('LiQ36UFf'))
    if source is None or round_row is None:
        raise ValueError('Unknown Colosseum round')
    return source, round_row


def _available(progress):
    encounter = _encounters().get(str(progress)) or {}
    return bool(encounter.get('normal') and encounter.get('boss'))


def _selection(progress, selection):
    if selection is None:
        return None
    kind = 'boss' if selection['boss'] else 'normal'
    return next(group for group in _encounters()[progress][kind]
                if group['group_id'] == selection['group_id'])


def _battle_row(active):
    source, _round = _masters(active['progress'])
    group = _selection(active['progress'], active)
    return {'n1R4BpZY': str(active['id']), 'i5pd8xr3': active['progress'],
            'LiQ36UFf': source['LiQ36UFf'], 'JV8AIH3n': str(group['group_type']) if group else '0',
            '2fY1IomW': group['group_id'] if group else '0', 'gb7AyuM3': str(active['before']),
            'QxW6NpJ3': str(active['win_points']), 'Zv7wzi36': str(active['lose_points'])}


def _groups(model, battle=None):
    rows = []
    for progress, saved in model['rounds'].items():
        group = _selection(progress, saved['selection'])
        rows.append({'i5pd8xr3': progress, '4jbAtD7f': str(saved['points']),
                     'Bi5akb1o': str(saved['battles']), 'Wdr3T4pe': str(saved['wins']),
                     'qBYxcC92': str(saved['boss_wins']),
                     'JV8AIH3n': str(group['group_type']) if group else '0',
                     '2fY1IomW': group['group_id'] if group else '0',
                     'g35y6a4N': group['enemy_info'] if group else '',
                     '6w4xiIsS': group['bgm'] if group else '0',
                     'DYTx1Is3': group['background'] if group else '0'})
    active = model.get('active')
    out = {'r6I9k7WR': [{'i5pd8xr3': model['highest']}], 'p9ortU42': rows,
           'fng74EXV': [{'n1R4BpZY': str(active['id']), 'i5pd8xr3': active['progress'],
                         'LiQ36UFf': _masters(active['progress'])[0]['LiQ36UFf']}]
                        if active else [{'n1R4BpZY': '0', 'i5pd8xr3': '0', 'LiQ36UFf': '0'}]}
    selected_battle = battle or active or model.get('last_battle')
    if selected_battle is None:
        source, _round = _masters(model['highest'])
        out['pZY6Vw70'] = [{'n1R4BpZY': '0', 'i5pd8xr3': model['highest'],
            'LiQ36UFf': source['LiQ36UFf'], 'JV8AIH3n': '0', '2fY1IomW': '0',
            'gb7AyuM3': '0', 'QxW6NpJ3': '100', 'Zv7wzi36': '0'}]
    else:
        out['pZY6Vw70'] = [_battle_row(selected_battle)]
    return out


def project(spec):
    """Replace the login carrier's stale progress with this campaign's state."""
    if State.player is None or not isinstance(spec, dict) or 'r6I9k7WR' not in spec:
        return spec
    out = dict(spec)
    out.update(_groups(_state()))
    return out


def entry(spec, req):
    if State.player is None:
        return spec
    return _reply(spec, _state())


def _reply(spec, model, battle=None, encounter=None):
    out = _refresh(spec)
    if encounter is not None:
        out.update(copy.deepcopy(encounter['bundle']))
    out.update(_groups(model, battle))
    return out


def _save(model):
    State.player.data['exvius_colosseum'] = model
    State.player.dirty = True


def _run(spec, req, action):
    player = State.player
    if player is None or player.mode == 'frozen':
        return spec
    before, dirty = copy.deepcopy(player.data), player.dirty
    try:
        node = _node(req, 'wPBq3it9') or {}
        progress = str(node.get('i5pd8xr3', ''))
        model = _state()
        if progress not in model['unlocked']:
            raise ValueError('Colosseum round is not unlocked')
        source, round_row = _masters(progress)
        saved = _progress(model, progress)
        active = model.get('active')
        if action == 'lottery':
            if not _available(progress):
                raise ValueError('Encounter data for this Colosseum round is unavailable')
            if active and active['progress'] != progress:
                raise ValueError('Another Colosseum battle is pending')
            if saved['selection'] is None:
                boss = saved['points'] >= int(round_row['sCd0L6Ka'])
                choices = _encounters()[progress]['boss' if boss else 'normal']
                total = sum(int(group['weight']) for group in choices)
                pick = secrets.randbelow(total)
                chosen = None
                for group in choices:
                    pick -= int(group['weight'])
                    if pick < 0:
                        chosen = group
                        break
                if chosen is None:
                    raise ValueError('No sourced Colosseum enemy')
                saved['selection'] = {'boss': boss, 'group_id': chosen['group_id']}
            _save(model)
            return _reply(spec, model, encounter=_selection(progress, saved['selection']))
        if action == 'start':
            restart = str(node.get('Jnt7cCV5', '0')) == '1'
            if active:
                if active['progress'] != progress:
                    raise ValueError('Another Colosseum battle is pending')
                return _reply(spec, model, encounter=_selection(progress, active))
            if restart:
                raise ValueError('No Colosseum battle to resume')
            selected = saved['selection']
            if selected is None:
                raise ValueError('Select a Colosseum enemy before starting')
            if not player.spend_orbs('clsm', int(round_row['xDm19iGS'])):
                raise ValueError('Insufficient Colosseum orbs')
            model['sequence'] += 1
            threshold = int(round_row['sCd0L6Ka'])
            active = {'id': model['sequence'], 'progress': progress, **selected,
                      'before': saved['points'],
                      'win_points': min(threshold, saved['points'] + 100),
                      'lose_points': saved['points'] if selected['boss'] else max(0, saved['points'] - 50)}
            model['active'] = active
            _save(model)
            return _reply(spec, model, encounter=_selection(progress, active))
        result = str(node.get('VR3DuS2M', ''))
        if result not in ('1', '2'):
            raise ValueError('Invalid Colosseum battle result')
        if active is None:
            previous = model.get('last_battle')
            return _reply(spec, model, battle=previous if previous and previous['progress'] == progress else None)
        if active['progress'] != progress:
            raise ValueError('Colosseum result does not match the pending battle')
        win = result == '2'
        player.record_archive({'CLSM_BATTLE_CNT': 1, 'CLSM_WIN_CNT': int(win),
                               'CLSM_TOTAL_GET_POINT': max(0, active['win_points'] - saved['points']) if win else 0})
        saved['battles'] += 1
        saved['wins'] += int(win)
        saved['points'] = active['win_points'] if win else active['lose_points']
        if win and active['boss']:
            reward_text = round_row['1x4bG2J8' if saved['boss_wins'] == 0 else 'dX6cor8j']
            rewards = []
            for text in reward_text.split(','):
                fields = text.split(':')
                if len(fields) == 4 and fields[-1] == '100':
                    fields.pop()  # Every shipped round reward has a guaranteed 100 percent rate.
                if len(fields) != 3 or not all(value.isdigit() for value in fields):
                    raise ValueError('Unsupported original Colosseum reward')
                kind, iid, count = map(int, fields)
                rewards.append({'kind': kind, 'id': iid, 'count': count})
            if any(not player._can_credit(reward) for reward in rewards):
                raise ValueError('Original Colosseum reward has no inventory projection')
            if player._grant_items(rewards) != rewards:
                raise ValueError('Colosseum reward was not granted completely')
            saved['boss_wins'] += 1
            following = source.get('ewPqs8h6')
            if (following in _mst('F_CLSM_PROGRESS_MST.ndjson', 'i5pd8xr3') and
                    _available(following) and following not in model['unlocked']):
                model['unlocked'].append(following)
                model['highest'] = following
                _progress(model, following)
        saved['selection'] = None
        model['active'] = None
        model['last_battle'] = active
        _save(model)
        return _reply(spec, model, battle=active)
    except (ValueError, KeyError, StopIteration, OSError) as error:
        player.data, player.dirty = before, dirty
        _note('Colosseum refused: ' + str(error))
        return spec


def lottery(spec, req):
    return _run(spec, req, 'lottery')


def start(spec, req):
    return _run(spec, req, 'start')


def end(spec, req):
    return _run(spec, req, 'end')
