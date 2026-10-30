"""Offline Arena battles against the configured local support units.

Wire layouts are from the GL 9 client. Scoring, streaks and medals follow
https://exvius.fandom.com/wiki/Arena. Local rivals have a neutral 1.00 ratio.
There is no online leaderboard or weekly placement reward in an offline game.
At the turn limit equal surviving counts are settled by damage inflicted, then
defeat on an exact tie. The original server's hidden tie-break is unavailable.
"""
import copy
from decimal import Decimal, ROUND_HALF_UP
import secrets
import time

from exvius_actions import _node, _mst, _refresh
from ffbe_state import State, _note
from ffbe_friends import load_friends, _reinforce_row
from player_state import unit_stats, limit_burst


def _model():
    from exvius_actions_arena import _arena
    model = _arena()
    model.setdefault('active', None)
    model.setdefault('matched', None)
    model.setdefault('daily', {})
    model.setdefault('groups', [])
    if not model['groups']:
        ids = sorted(_mst('F_RB_TRADE_BOARD_MST.ndjson', '6m4Rn5jd'), key=int)
        model['groups'] = [{'CIE1rky2': '1', '35iR6h0V': ','.join(ids)}]
    return model


def _save(model):
    State.player.data['exvius_arena'] = model
    State.player.dirty = True


def _season(req, model):
    node = _node(req, 'yT12twnc') or {}
    if any(str(node.get(k)) != model['season_id'] for k in ('S3rek7hC', 'o8RDmSI9')):
        raise ValueError('Arena season does not match the loaded offline season')


def _friend(target):
    return next((f for f in load_friends() if str(f['friend_id']) == target), None)


def _party():
    player = State.player
    party = player.data['party']
    deck = next(d for d in party['decks'] if d['id'] == party['active_deck'])
    roster = {str(u['instance_id']): u for u in player.data['roster']}
    return [roster[str(m['instance_id'])] for m in deck['members']
            if str(m['instance_id']) in roster][:5]


def _rival(friend):
    unit = friend['unit']
    source = _reinforce_row(friend)
    patterns = list(_mst('F_RB_AI_PATTERN_MST.ndjson', 'UE3vKA5y').values())
    total = sum(int(row['ixDq7yJ8']) for row in patterns)
    draw = secrets.randbelow(total)
    for row in patterns:
        draw -= int(row['ixDq7yJ8'])
        if draw < 0:
            pattern = row['UE3vKA5y']
            break
    # Member type 0 is the leader, order is zero based. Optional esper fields
    # are empty, so this local rival does not equip a support-list esper.
    fields = [friend['instance_id'], str(unit['master_id']), str(unit['master_id']),
              str(unit['level']), *[str(v) + '-0' for v in unit_stats(unit['master_id'], unit['level'])],
              str(unit['lb_level']), source['93Y6evuT'], source['80NUYFMJ'], '', '', '0', '0', pattern]
    return ':'.join(fields)


def _versus(model, state):
    battle = model.get('active') or model.get('matched')
    if not battle:
        return {'DW0rgk3C': [{'uC8E0opI': str(state), 'QX42tjRY': '1'}]}
    # Repair an already-started legacy snapshot in the reply without changing
    # its battle, opponent, AI pattern, initiative or orb charge.
    rival = battle['rival'].split(':')
    if len(rival) == 18 and rival[10] == '0' and limit_burst(rival[1]):
        rival[10] = '1'
    return {'N7Bd3IuL': [copy.deepcopy(battle['summary'])],
            'DW0rgk3C': [{'uC8E0opI': str(state), 'Jc4udh7x': ':'.join(rival),
                          'QX42tjRY': battle['initiative']}]}


def _reply(spec, model, state=0):
    from exvius_actions_arena import _arena_rows
    out = _refresh(spec)
    out.update(_arena_rows(model))
    out.update(_versus(model, state))
    out['H54XvPis'] = copy.deepcopy(model['groups'])
    # GL's Arena temporarily selects equipment list 2. Its native clear-and-add
    # response tag is IqkX0gV1 (factory 0x1918ae4), separate from normal list 1.
    out['IqkX0gV1'] = State.player._equip_rows()
    return out


def matching(spec, req):
    def run(model):
        _season(req, model)
        target = str((_node(req, 'N7Bd3IuL') or {}).get('fP8Nv0KZ', ''))
        friend = _friend(target)
        if friend is None:
            raise ValueError('Unknown local Arena rival')
        if model['active']:
            if model['active']['target'] != target:
                raise ValueError('Finish the pending Arena battle first')
            return _reply(spec, model, 2)
        model['matched'] = {'target': target, 'rival': _rival(friend),
            'summary': {'cw4ho9eY': str(friend['unit']['master_id']), 'P2w9myrI': '0',
                        'fP8Nv0KZ': target, 'IgS2Mi9Y': friend['display_name'],
                        'Bc43fupe': 'Local Arena opponent'},
            'initiative': ','.join(str(1 + secrets.randbelow(2)) for _ in range(10))}
        _save(model)
        return _reply(spec, model, 1)
    return _transaction(spec, run)


def start(spec, req):
    def run(model):
        _season(req, model)
        target = str((_node(req, 'N7Bd3IuL') or {}).get('fP8Nv0KZ', ''))
        if model['active']:
            if model['active']['target'] != target:
                raise ValueError('Different Arena battle is pending')
            return _reply(spec, model, 2)
        selected = model['matched']
        if selected is None or selected['target'] != target:
            raise ValueError('Load a local Arena opponent before starting')
        own = _party()
        if not own:
            raise ValueError('Arena party is empty')
        all_orbs = str((_node(req, 'yT12twnc') or {}).get('Q03VHyjm', '0'))
        if all_orbs not in ('0', '1'):
            raise ValueError('Invalid Arena orb selection')
        orbs = State.player.orb_view('clsm')[0] if all_orbs == '1' else 1
        if not State.player.spend_orbs('clsm', orbs):
            raise ValueError('Insufficient Arena orbs')
        selected['orbs'] = orbs
        selected['own'] = {str(u['instance_id']): str(u['master_id']) for u in own}
        selected['bonus'] = _unit_bonus(model, own)
        model['active'] = copy.deepcopy(selected)
        model.pop('last_result', None)
        _save(model)
        return _reply(spec, model, 2)
    return _transaction(spec, run)


def _unit_bonus(model, units):
    season = _mst('F_RB_SS_MST.ndjson', '6Z9DxQFf')[model['season_id']]
    # GL receives these group definitions from the server, not an F_RB table.
    # Missing original groups do not imply that every unit of a rarity qualifies.
    definitions = []
    for payload in State.replies.values():
        if isinstance(payload, dict):
            definitions.extend(payload.get('6ePjU3Nw', []))
    best = 0
    owned = {str(u['master_id']) for u in units}
    for entry in season.get('uo0xmn8b', '').split(','):
        fields = entry.split(':')
        if len(fields) == 2:
            for row in definitions:
                if str(row.get('42B7MGIU')) != fields[0]:
                    continue
                if str(row.get('peF96w8R', '0')) != '0' and str(row.get('4z5vDrRK')) != model['season_id']:
                    continue
                if str(row.get('6W7n8ryb')) == '3' and str(row.get('86JmXL41')) in owned:
                    best = max(best, int(fields[1]))
    return best


def _results(text, expected):
    rows = []
    seen = set()
    for packed in str(text or '').split(','):
        fields = packed.split(':')
        if len(fields) != 4 or not all(f.isdigit() for f in fields):
            raise ValueError('Invalid Arena result unit record')
        master, iid, hp, dead = fields
        if iid not in expected or expected[iid] != master or iid in seen or dead not in ('0', '1'):
            raise ValueError('Arena result unit does not match the started party')
        if int(hp) == 0 and dead != '1':
            raise ValueError('Arena result reports a surviving unit with zero HP')
        seen.add(iid)
        rows.append(fields)
    if seen != set(expected):
        raise ValueError('Arena result is missing party members')
    return rows


def _round(value):
    return int(Decimal(value).quantize(Decimal('1'), rounding=ROUND_HALF_UP))


def reward_entries(text):
    """Original item triples and the shipped level-1 unit reward descriptors."""
    rewards = []
    for packed in str(text or '').split(','):
        if not packed:
            continue
        fields = packed.split(':')
        if len(fields) == 5 and fields[0] == '10' and fields[3:] == ['0', '1']:
            fields = fields[:3]
        if len(fields) != 3 or not all(f.isdigit() for f in fields) or int(fields[2]) < 1:
            raise ValueError('Unsupported Arena reward descriptor')
        kind, iid, count = map(int, fields)
        rewards.append({'kind': kind, 'id': iid, 'count': count})
    return rewards


def end(spec, req):
    def run(model):
        _season(req, model)
        active = model['active']
        if active is None:
            out = _reply(spec, model, 3)
            if model.get('last_result'):
                out['g3JFd0y7'] = [copy.deepcopy(model['last_result'])]
            return out
        node = _node(req, 'g3JFd0y7') or {}
        retired = str(node.get('g9t7dBCH', '0')) == '1'
        if retired:
            own_text = ','.join(master + ':' + iid + ':0:1' for iid, master in active['own'].items())
            rival_fields = active['rival'].split(':')
            enemy_text = rival_fields[1] + ':' + rival_fields[0] + ':' + rival_fields[4].split('-')[0] + ':0'
        else:
            own_text, enemy_text = node.get('GA1D6XIC'), node.get('Pch7J9Ty')
        own = _results(own_text, active['own'])
        rival_fields = active['rival'].split(':')
        enemies = _results(enemy_text, {rival_fields[0]: rival_fields[1]})
        live = sum(row[3] == '0' for row in own)
        enemy_live = sum(row[3] == '0' for row in enemies)
        turns = int(node.get('z8uj9TAU', '0'))
        if turns < 0 or turns > 10:
            raise ValueError('Arena turn count is outside the original ten-turn limit')
        if not retired and live and enemy_live and turns < 10:
            raise ValueError('Arena battle ended before either party was defeated')
        win = not retired and live > 0 and (enemy_live == 0 or live > enemy_live or
            (live == enemy_live and int(node.get('3S8pMym0', '0')) > int(node.get('bB69ZWQY', '0'))))
        user = model['user']
        streak = int(user['5svT7qLR']) + 1 if win else 0
        base = 100 if win else 10
        streak_gain = _round(Decimal(base) * Decimal(min(18, streak + 8)) / 100) if streak > 1 else 0
        bonus = _round(Decimal(base + streak_gain) * Decimal(active['bonus']) / 100) if win else 0
        # Original 2021-11-30 notice, preserved at r/FFBEblog/r5izr1:
        # wins consume all reserved orbs; losses cost one; streak rises once.
        reserved = int(active.get('orbs', 1))
        consumed = reserved if win else 1
        medals = _round(Decimal(base + streak_gain) / Decimal('12.5')) * consumed
        base, streak_gain, bonus = (value * consumed for value in (base, streak_gain, bonus))
        gain = base + streak_gain + bonus
        State.player.record_archive({'ARENA_BATTLE_CNT': consumed, 'ARENA_WIN_CNT': consumed * int(win),
            'ARENA_TOTAL_GET_RANKING_POINT': gain, 'ARENA_MAX_CONSECUTIVE_WIN': streak})
        today = time.strftime('%Y-%m-%d', time.gmtime())
        count = model['daily'].get(today, 0)
        season = _mst('F_RB_SS_MST.ndjson', '6Z9DxQFf')[model['season_id']]
        daily = season.get('dJ1g6p8h', '').split(',')
        daily_text = ','.join(daily[count:count + consumed])
        rewards = reward_entries(daily_text)
        if any(not State.player._can_credit(r) for r in rewards):
            raise ValueError('Arena daily reward cannot be projected into inventory')
        if State.player._grant_items(rewards) != rewards:
            raise ValueError('Arena daily reward was not granted completely')
        if not win and reserved > 1:
            # Add back only the reservation, retaining any regeneration tick
            # or later spend instead of restoring an old orb-state snapshot.
            row = State.player.data['orbs']['clsm']
            cap = State.player.orb_view('clsm')[1]
            row['point'] = min(cap, int(row['point']) + reserved - 1)
        before, trade = int(user['UbQ26oH4']), int(user['mRY52Tib'])
        result = {'GA1D6XIC': own_text, 'Pch7J9Ty': enemy_text, '2q7sZreS': '1' if win else '2',
                  '42GLsTok': f'{before},{base},{streak_gain},{bonus}',
                  'PDi5wos8': f'{trade},{medals}', 'k9pWH78Z': daily_text if rewards else '',
                  '7SPHKY1j': user['52ibRBqw']}
        user.update(UbQ26oH4=str(before + gain), mRY52Tib=str(trade + medals),
                    egayI1s4=str(max(int(user['egayI1s4']), streak)), **{'5svT7qLR': str(streak),
                    'p6H4CNw8': str(int(user['p6H4CNw8']) + consumed),
                    'Ka0Pbz5N': str(int(user['Ka0Pbz5N']) + consumed * int(win))})
        model['daily'] = {today: count + consumed}
        model['active'] = model['matched'] = None
        model['last_result'] = result
        _save(model)
        out = _reply(spec, model, 3)
        out['g3JFd0y7'] = [result]
        return out
    return _transaction(spec, run)


def restart(spec, req):
    def run(model):
        _season(req, model)
        state = 2 if model['active'] else 1 if model['matched'] else 0
        out = _reply(spec, model, state)
        out['KMwJ3s6W'] = [{'S3rek7hC': model['season_id'], 'o8RDmSI9': model['season_id'],
                           'uC8E0opI': str(state)}]
        return out
    return _transaction(spec, run)


def _transaction(spec, run):
    player = State.player
    if player is None or player.mode == 'frozen':
        return spec
    before, dirty = copy.deepcopy(player.data), player.dirty
    try:
        return run(_model())
    except (ValueError, KeyError, StopIteration, OSError) as error:
        player.data, player.dirty = before, dirty
        _note('Arena refused: ' + str(error))
        return spec
