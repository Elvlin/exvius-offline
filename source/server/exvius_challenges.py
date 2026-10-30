"""Additional GL9 mission predicates, evaluated from the native battle report.

Wire channels are read from MissionChallengeLog::toJsonGroup in the pinned
library. Finishing-blow tuples are group@monster:parts@action-type:action-id.
No predicate grants credit merely because a condition was not recognized.
"""
from functools import lru_cache
import re

from ffbe_state import State
from player_state import _load_ndjson, unit_mst

CHANNELS = {'items': '4p6CrcGt', 'magic': 'i1yJ3hmT', 'special': 'Pqi5r1TZ',
            'lb': 's2rX7g0o', 'beasts': '9JBtk2LE', 'elements': 'qr5PoZ1W',
            'weak_elements': 'dHyXJC27', 'weak_elements_dv': 'qY8cL2yI',
            'weak_tribes': '7m5NDeaj', 'shift': 'JgNoS92t',
            'resisted_elements': '6xuo3nZj', 'overdrive': 'kTZ3yQf6'}


def _counts(ctx, kind):
    if not ctx.get('group_present'):
        return None
    raw = str(ctx.get('native_log', {}).get(CHANNELS[kind]) or '')
    counts = {}
    for entry in filter(None, raw.split(',')):
        parts = entry.split(':')
        if len(parts) != 2 or not all(p.isdigit() for p in parts):
            return None
        counts[parts[0]] = counts.get(parts[0], 0) + int(parts[1])
    return counts


def _total(ctx, kind):
    rows = _counts(ctx, kind)
    return None if rows is None else sum(rows.values())


def _used(ctx, kind, iid=None, minimum=1, maximum=None):
    rows = _counts(ctx, kind)
    if rows is None:
        return None
    count = sum(rows.values()) if iid is None else rows.get(str(iid), 0)
    return count <= maximum if maximum is not None else count >= minimum


def _party(ctx):
    roster = {str(u['instance_id']): u for u in State.player.data['roster']}
    party = State.player.battle_party(ctx.get('mission_id'))
    deck = next((d for d in party['decks'] if str(d['id']) == str(party['active_deck'])), {})
    result = [roster[str(m['instance_id'])] for m in deck.get('members', [])
              if str(m.get('instance_id')) in roster]
    helper = ctx.get('helper_master')
    if helper:
        result.append({'master_id': helper})
    return result


def _kill_rows(ctx):
    result = []
    for raw in filter(None, str(ctx.get('native_log', {}).get('73CfbLEx') or '').split(',')):
        match = re.fullmatch(r'(\d+)@(\d+):(\d+)@(\d+):(\d+)', raw)
        if not match:
            return None
        result.append(match.groups())
    return result


@lru_cache(maxsize=1)
def _action_ids():
    return {'magic': set(_load_ndjson('F_MAGIC_MST.ndjson', 'QV1HE7Wq')),
            'lb': set(_load_ndjson('F_LIMITBURST_MST.ndjson', 'PR2HIc71')),
            'items': set(_load_ndjson('F_ITEM_MST.ndjson', 'tL6G9egd'))}


def _finish(ctx, param, kind):
    fields = param.split(':')
    if len(fields) not in (3, 4) or not all(p.isdigit() for p in fields):
        return None
    rows = _kill_rows(ctx)
    if rows is None or not ctx.get('group_present'):
        return None
    for group, monster, parts, action_type, action in rows:
        if (group, monster, parts) != tuple(fields[:3]):
            continue
        # addKoLog's original action enum table: special=1, magic=2,
        # item=3, esper=4, LB=5. IDs alone overlap across these namespaces.
        if action_type != {'special': '1', 'magic': '2', 'items': '3', 'beasts': '4', 'lb': '5'}[kind]:
            continue
        if len(fields) == 4:
            if action == fields[3]:
                return True
            continue
        return True
    return False


def _timed_rows(ctx, key, columns):
    if not ctx.get('group_present'):
        return None
    rows = []
    for raw in filter(None, str(ctx.get('native_log', {}).get(key) or '').split(',')):
        parts = raw.split(':')
        if (len(parts) != columns or not parts[0].isdigit() or
                not all(p.isdigit() or p == '-1' for p in parts[1:])):
            return None
        rows.append(tuple(map(int, parts)))
    return rows


def _evaluate(code, ctx, param):
    if not ctx.get('group_present'):
        return None
    if code == '0':
        return _used(ctx, 'items')
    if code in ('2', '3', '7', '8', '21', '22', '30'):
        kind = {'2': 'items', '3': 'items', '7': 'magic', '8': 'magic',
                '21': 'special', '22': 'special', '30': 'beasts'}[code]
        return _used(ctx, kind, param, maximum=0) if code in ('3', '8', '22') else _used(ctx, kind, param)
    if code in ('17', '20', '29'):
        return _used(ctx, {'17': 'lb', '20': 'special', '29': 'beasts'}[code], maximum=0)
    if code in ('4', '15', '18', '23', '32', '63', '65', '67'):
        return _finish(ctx, param, {'4': 'items', '15': 'magic', '18': 'lb',
                                   '23': 'special', '32': 'beasts', '63': 'special',
                                   '65': 'beasts', '67': 'lb'}[code])
    if code in ('12', '14'):
        counts = _counts(ctx, 'magic')
        if counts is None or not param.isdigit():
            return None
        spells = _load_ndjson('F_MAGIC_MST.ndjson', 'QV1HE7Wq')
        field = 'yjY4GK3X' if code == '12' else '6X0fxsdw'
        return not any(str(spells.get(iid, {}).get(field)) == param for iid in counts)
    if code in ('26', '59'):
        fields = param.split(':')
        if not all(x.isdigit() for x in fields) or len(fields) != (1 if code == '26' else 2):
            return None
        return _used(ctx, 'elements', fields[0], minimum=1 if code == '26' else int(fields[1]) + 1)
    if code == '35':
        return len(_party(ctx)) <= int(param) if param.isdigit() else None
    if code == '36':
        return any(str(u['master_id']) == param or str(u['master_id'])[:-1] == param[:-1] for u in _party(ctx))
    if code in ('45', '49', '50', '102'):
        if not param.isdigit():
            return None
        kind = {'45': 'beasts', '49': 'lb', '50': 'lb', '102': 'weak_elements'}[code]
        return _used(ctx, kind, maximum=int(param)) if code == '50' else _used(ctx, kind, minimum=int(param) + 1)
    if code == '69':
        return _used(ctx, 'special', param)
    if code == '71':
        # Escape is the native system-special action ID carried in this spec.
        return _used(ctx, 'special', param, maximum=0)
    if code in ('76', '77'):
        fields = param.split(':')
        if len(fields) != 2 or not all(x.isdigit() for x in fields):
            return None
        turns = ctx.get('battle_turns', {}).get(fields[0])
        if turns is None:
            return False
        return turns >= int(fields[1]) + 1 if code == '76' else turns <= int(fields[1])
    if code in ('122', '132'):
        if not param.isdigit():
            return None
        key = 'MAX_CHAIN_TURN' if code == '122' else 'MAX_ELEMENT_CHAIN_TURN'
        return int(ctx.get('achievements', {}).get(key, 0)) >= int(param) + 1
    if code in ('170', '171', '172', '173'):
        fields = param.split(':')
        if not all(x.isdigit() for x in fields):
            return None
        units = _party(ctx)
        if code in ('171', '172') and ctx.get('helper_master'):
            units = units[:-1]
        if not units:
            return False
        categories = [set(str((unit_mst(u['master_id']) or {}).get('GPUkhv72') or '').split(',')) for u in units]
        if code == '172':
            return len(fields) == 2 and sum(fields[1] in cats for cats in categories) >= int(fields[0])
        required = set(fields)
        return all(bool(required & cats) for cats in categories)
    if code == '1000':
        elapsed = ctx.get('elapsed_seconds')
        return None if elapsed is None or not param.isdigit() else elapsed <= int(param)
    if code in ('1001', '1002'):
        fields = param.split(':')
        if len(fields) != 3 or not all(x.isdigit() for x in fields):
            return None
        rows = _timed_rows(ctx, 'vMo5cnmx', 3)
        return None if rows is None else any(str(r[0]) == fields[2] and
                                             0 <= r[1 if code == '1001' else 2] <= int(fields[0]) for r in rows)
    if code == '1003':
        fields = param.split(':')
        if len(fields) != 2 or not all(x.isdigit() for x in fields):
            return None
        rows = _timed_rows(ctx, 'MyIhjd6W', 2)
        return None if rows is None else sum(r[1] <= int(fields[0]) for r in rows) >= int(fields[1])
    return None


def install(checks):
    codes = ('0 2 3 4 7 8 12 14 15 17 18 20 22 23 26 29 30 32 35 36 45 49 50 '
             '59 63 65 67 69 71 76 77 102 122 132 170 171 172 173 1000 1001 1002 1003').split()
    def predicate(code):
        def check(ctx, param):
            clauses = str(param).split(',')
            results = []
            for index, clause in enumerate(clauses):
                other, separator, value = clause.partition(':')
                if index and separator and other in checks:
                    results.append(checks[other](ctx, value))
                else:
                    results.append(_evaluate(code, ctx, clause))
            return None if any(r is None for r in results) else all(results)
        return check
    checks.update({code: predicate(code) for code in codes})
