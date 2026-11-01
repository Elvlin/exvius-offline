"""The original five-star unit/prism selector and its shipped ticket prices."""
import copy
from datetime import datetime

from exvius_actions import _node, _mst, _refresh
from ffbe_state import State, _note


def entry(spec, req):
    # Unit and prism choices are in the original cached F_GACHA_SELECT_* tables.
    from exvius_shop_catalogue import entry as shop_entry
    return shop_entry(spec, req)


def _execute(spec, req, prism=False):
    from ffbe_gacha import all_banners, _award_str
    from player_state import effect_pattern_for, unit_mst
    player = State.player
    tag = 'tCq8mcNo' if prism else 'u9jY6hQJ'
    def decline():
        out = _refresh(spec)
        out[tag] = [{'UJz5QED2': '', 'oY0vAuE9': '0', 'zoU5J3Kq': '1',
                     'X1IuZnj2': '0', 'nqzG3b2v': '0', 'zJ1A6HXm': '0', '2RtVPS3b': '0'}]
        return out
    if player is None or player.mode == 'frozen':
        return decline()
    node = _node(req, tag) or {}
    banner = next((b for b in all_banners() if str(b['id']) == str(node.get('X1IuZnj2')) and
                   b.get('selection')), None)
    if banner is None or str(node.get('nqzG3b2v')) != str(banner['detail_id']):
        _note('Select summon: unknown banner or detail')
        return decline()
    iid = str(node.get('tL6G9egd' if prism else '3HriTp6B', ''))
    table = _mst('F_GACHA_SELECT_PRISM_MST.ndjson' if prism else 'F_GACHA_SELECT_UNIT_MST.ndjson',
                 'tL6G9egd' if prism else '3HriTp6B')
    row = table.get(iid)
    today = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    first, last = ('Tx6MGkJ1', '2CL6pZmE') if prism else ('VjJQ51uG', 'm8ivD4NX')
    if row is None or not row[first] <= today <= row[last]:
        _note('Select summon: selected reward is not in the original available master')
        return decline()
    cost = int(row['e4mG8jTc'])
    reward = {'kind': 20 if prism else 10, 'id': int(iid), 'count': 1}
    if cost < 1 or not player._can_credit(reward):
        return decline()
    before, dirty = copy.deepcopy(player.data), player.dirty
    if not player.spend_item(23, 260, cost):
        _note('Select summon: insufficient five-star select tickets')
        return decline()
    try:
        if prism:
            if player._grant_items([reward]) != [reward]:
                raise ValueError('Selected prism could not be granted')
            result = {'UJz5QED2': '20:' + iid + ':1'}
        else:
            unit = player.grant_unit(iid, granted_rarity=5)
            award = {'unit_id': iid, 'instance_id': unit['instance_id'], 'level': unit['level']}
            result = {'X1IuZnj2': str(banner['id']), 'nqzG3b2v': str(banner['detail_id']),
                      'UJz5QED2': _award_str(award), 'zJ1A6HXm': '1', '2RtVPS3b': '0',
                      'zoU5J3Kq': str(effect_pattern_for(int(unit_mst(iid)['9fW0TePj']), banner['id'])),
                      'oY0vAuE9': '1'}
        out = _refresh(spec)
        out[tag] = [result]
        return out
    except Exception:
        player.data, player.dirty = before, dirty
        raise


def select_unit(spec, req):
    return _execute(spec, req)


def select_prism(spec, req):
    return _execute(spec, req, prism=True)


from exvius_shop_catalogue import purchase as shop_purchase
HANDLERS = {'6nTcSp4R': entry, 'xio14KrL': select_unit, 'bgast6dR': select_prism,
            'W58vo4Hp': shop_purchase}
