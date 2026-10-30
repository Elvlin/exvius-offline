"""Offline Clash of Wills seasons and persisted original Fortuna reward draws."""
from copy import deepcopy
from functools import lru_cache
import json
from pathlib import Path
import secrets
import time

from player_state import _load_ndjson


@lru_cache(maxsize=1)
def policy():
    return json.loads(Path(__file__).with_name('content').joinpath('fortuna_rewards.json').read_text(encoding='utf8'))


@lru_cache(maxsize=1)
def level_rewards():
    return json.loads(Path(__file__).with_name('content').joinpath('clash_level_rewards.json').read_text(encoding='utf8'))['seasons']


def missions(dungeon):
    return sorted((r for r in _load_ndjson('F_MISSION_MST.ndjson', 'qo3PECw6').values()
                   if str(r.get('U9iHsau3')) == str(dungeon) and str(r.get('gQR24kST')) == '50'),
                  key=lambda r: int(r['Z0EN6jSh']))


def season_index(area):
    # The preserved Global cache has the first three and final two areas.
    # The thirty restored areas between them retain their archive IDs.
    aid = int(area)
    if 7100 <= aid <= 7102:
        return aid - 7100
    if 9500 <= aid <= 9529:
        return aid - 9500 + 3
    if 7103 <= aid <= 7104:
        return aid - 7103 + 33
    raise ValueError('unknown Clash of Wills area')


def season_id(area):
    season = str(7100000 + season_index(area))
    events = _load_ndjson('F_TFA_GAMBIT_EVENT_MST.ndjson', None)['__rows__']
    if not any(str(r['pvS5A4kE']) == season for r in events):
        raise ValueError('unknown Clash of Wills season')
    return season


def gambit_bonuses(area, tier, selected):
    event = season_id(area)
    rows = _load_ndjson('F_TFA_GAMBIT_EVENT_MST.ndjson', None)['__rows__']
    allowed = {i.strip() for row in rows if str(row['pvS5A4kE']) == event
               and int(row['d4d924eb']) <= int(tier) for i in str(row['i1kVPwjL']).split(',')}
    masters = _load_ndjson('F_TFA_GAMBIT_MST.ndjson', 'd1499fb3')
    if len(set(selected)) != len(selected) or any(i not in allowed or i not in masters for i in selected):
        raise ValueError('gambit is unavailable for this season or tier')
    # Native GambitMst getters: +0x68 score percent, +0x6c drop percent.
    return (1000 + 10 * sum(int(masters[i]['b9ee82af']) for i in selected),
            1000 + 10 * sum(int(masters[i]['eda4d200']) for i in selected))


def ensure(feature, dungeon):
    rows = missions(dungeon)
    if not rows:
        raise ValueError('unknown Clash of Wills dungeon')
    groups = feature.setdefault('groups', {})
    area = str(rows[0]['uv60hgDW'])
    season = season_id(area)
    events = groups.setdefault('L6XRZb0z', [])
    event = next((r for r in events if str(r.get('U9iHsau3')) == str(dungeon)), None)
    if event is None:
        # MonsterScaleMissionMstList's original six-column pipe codec:
        # dungeon-tier-mission-minimumLevel-maximumLevel-gradeInfo.
        scales = '|'.join(f"{dungeon}-{n}-{r['qo3PECw6']}-{1 if n == 1 else (n-1)*20}-{n*20-1}-0"
                          for n, r in enumerate(rows, 1))
        event = {'U9iHsau3': str(dungeon), 'pvS5A4kE': season, 'enkCGfPT': scales,
                 'L84eYzxv': str(710001 + season_index(area)), '9gAL7Bur': '1', 'CTnSr2yb': '1', 'RdD05iaE': '0',
                 'SM7fdQe1': '0', 'lJLXlueo': '1',
                 'VjJQ51uG': '2020-01-01 00:00:00', 'm8ivD4NX': '2037-12-31 23:59:59'}
        events.append(event)
    # Migrate seasons already saved with the old inactive event response.
    event['9gAL7Bur'] = '1'
    # All 35 original Global ranking tables are already in SumallyRewardMst.
    # The native ranking tab reads this ID, independently of the event key.
    event['pvS5A4kE'] = season
    event['L84eYzxv'] = str(710001 + season_index(area))
    feature.setdefault('dungeon', str(dungeon))
    groups.setdefault('x51bb135', [{'dc10ae96': '0', 'cEVau7d8': '1'}])
    groups.setdefault('Fs0sexp7', [{'mXQWZ5Ql': '', 'IX1hKI6g': '0',
                                  'bcd49985': f"0:{event['pvS5A4kE']}:{policy()['slots']}"}])
    for row in groups['Fs0sexp7']:
        parts = str(row.get('bcd49985', '')).split(':')
        if len(parts) == 3:
            parts[1] = season
            row['bcd49985'] = ':'.join(parts)
    if 'pass' in feature:
        parts = str(feature['pass']).split(':')
        if len(parts) == 3:
            parts[1] = season
            feature['pass'] = ':'.join(parts)
    groups.setdefault('AJb8pF71', [])
    return event


def draw(tier, multiplier=1000):
    pool = policy()['tiers'][str(max(1, min(5, int(tier))))]
    available = list(pool)
    result = []
    for _ in range(min(3, len(available))):
        number = secrets.randbelow(sum(r['weight'] for r in available))
        for row in available:
            number -= row['weight']
            if number < 0:
                kind, iid, count = row['reward'].split(':')
                result.append(f'{kind}:{iid}:{max(1, int(count) * int(multiplier) // 1000)}-{int(row["rare"])}')
                available.remove(row)
                break
    return ','.join(result)


def sync_personal_ranking(player, feature):
    """Project the witnessed personal best into the native self-ranking cache."""
    did = str(feature.get('dungeon', ''))
    uid = str(player.data['identity']['user_id'])
    rows = feature.get('ranking_details', {}).get(did, {}).get(uid, [])
    best = int(feature.get('best_score', 0))
    row = deepcopy(rows[0]) if rows else {}
    leader = str(row.get('ZNunWB3u', '0:0')).split(',')[0].split(':')
    feature.setdefault('groups', {})['cBHNnXQZ'] = [{
        '3HbFrqo5': '1', '8s9wNSpd': '1', '52ibRBqw': '1' if best else '0',
        '23qt9g1x': ':'.join((leader + ['0', '0'])[:2]),
        **row, 'UbQ26oH4': str(best)}]


def complete(player, mid, sequence, context):
    row = _load_ndjson('F_MISSION_MST.ndjson', 'qo3PECw6').get(str(mid))
    if not row or str(row.get('gQR24kST')) != '50' or context.get('cleared') is not True:
        return
    f = deepcopy(player.data.get('exvius_tfa', {}))
    did = str(row['U9iHsau3'])
    # Do not discard selections when the user returns to an older season.
    if f.get('dungeon') and str(f['dungeon']) != did:
        f.setdefault('seasons', {})[str(f['dungeon'])] = {k: deepcopy(v) for k, v in f.items() if k != 'seasons'}
        history = f.get('seasons', {})
        f = {**deepcopy(history.get(did, {})), 'seasons': history}
    event = ensure(f, did)
    f['dungeon'] = did
    key = str(mid) + ':' + str(sequence)
    if key in f.get('settlements', []):
        return
    if f.get('claimed'):
        f.update(slots='', last_choice='', candidate_queue=[], claimed=False)
    tier = next((n for n, r in enumerate(missions(did), 1) if str(r['qo3PECw6']) == str(mid)), 1)
    active = f.get('active') or {}
    score_bonus, drop_bonus = gambit_bonuses(row['uv60hgDW'], tier,
                                            list(filter(None, active.get('gambits', '').split(','))))
    if f.get('pending') and f.get('candidates'):
        f.setdefault('candidate_queue', []).append(draw(tier, drop_bonus))
    else:
        f.update(candidates=draw(tier, drop_bonus), pending=True, claimed=False, selection=True)
    f.setdefault('settlements', []).append(key)
    level = int((f.get('active') or {}).get('boss_level', 1 if tier == 1 else (tier - 1) * 20))
    source = level_rewards()[str(row['uv60hgDW'])]
    previous_level = int(f.get('rewarded_level', 0))
    awarded = []
    for cleared_level in range(previous_level + 1, level + 1):
        rewards = source['levels'][str(cleared_level)]
        paid = player._grant_items(deepcopy(rewards['rewards']))
        if paid != rewards['rewards']:
            raise ValueError('Clash level reward could not be credited')
        for emblem in rewards['emblems']:
            if not player.grant_emblem(emblem) and emblem not in player.owned_emblem_ids():
                raise ValueError('Clash emblem could not be credited')
        awarded.extend(paid)
    if level > previous_level:
        f['rewarded_level'] = level
        f['last_level_rewards'] = awarded
        player.deliver_mail(source['name'] + ': Level Rewards', [],
                            message=f'Rewards for levels {previous_level + 1} to {level} have been added to your inventory.')
    event['RdD05iaE'] = str(max(int(event.get('RdD05iaE', 0)), level))
    event['CTnSr2yb'] = str(min(99, int(event['RdD05iaE']) + 1))
    f['groups']['x51bb135'] = [{'dc10ae96': '1', 'cEVau7d8': '1'}]
    f['groups']['Fs0sexp7'][0]['IX1hKI6g'] = '1'
    metrics = context.get('achievements', {})
    # Local season ranking uses witnessed metrics. No remote opponent scores.
    score = tier * 10000 + min(30000, int(metrics.get('MAX_DAMAGE_TURN', 0)) // 100000)
    score += 10000 if context.get('dead_count') == 0 else 0
    score = score * score_bonus // 1000
    f['best_score'] = max(int(f.get('best_score', 0)), score)
    archive = {'9Tbns0eI': str(player.data['identity']['user_id']), 'L9IAY8iW': event['pvS5A4kE'],
               'qo3PECw6': str(mid), 'pvS5A4kE': event['pvS5A4kE'], '6DuiWx05': '0',
               '7HSK9eBV': str(score), 'cH15BhQ0': str(tier), 'qf9S3TLg': str(tier * 10000),
               'wF5Ac6ey': '', 'km0aS4b1': time.strftime('%Y%m%d', time.gmtime()),
               'Apfj8IT2': time.strftime('%Y%m%d%H%M%S', time.gmtime()), '6d9x1vIU': '1',
               '5EWcu4M8': '', 'UTRQvH1q': event['RdD05iaE'], 'SM7fdQe1': event['RdD05iaE'],
               'BBNgJ3OB': str(tier * 10000), '8jlksFkb': '1000', 'oTkEXt1u': '0', 'lFPpGAYz': '0'}
    f['groups']['AJb8pF71'] = [archive]
    if score >= f['best_score']:
        f['groups']['XHnyfiwg'] = [deepcopy(archive)]
        party = player.battle_party(mid)
        deck = next((d for d in party['decks'] if str(d['id']) == str(party['active_deck'])), {})
        roster = {str(u['instance_id']): u for u in player.data['roster']}
        members = {int(m['disp_order']): roster.get(str(m['instance_id'])) for m in deck.get('members', [])}
        units = ','.join(f"{u['master_id']}:{u['level']}:{int(u.get('nv_ex_level', 0))}:0" if u else '0:0:0:0'
                         for u in (members.get(n) for n in range(6)))
        linked = party.get('beast_decks', {}).get(str(party['active_deck']), [0] * 6)
        beasts = []
        for eid in (linked + [0] * 6)[:6]:
            beast = player.beast_entry(eid) if eid else None
            beasts.append(f"{eid}:{beast.get('rarity', 1)}:{beast.get('level', 1)}" if beast else '0:0:0')
        rank = {'UbQ26oH4': str(score), 'cH15BhQ0': str(tier), '8jlksFkb': '1000',
                'oTkEXt1u': '0', 'lFPpGAYz': '0', '7dkQA0K4': event['RdD05iaE'],
                'wF5Ac6ey': '', 'ZNunWB3u': units, 'UijrbCse': ','.join(beasts),
                'i1kVPwjL': active.get('gambits', '')}
        f.setdefault('ranking_details', {}).setdefault(did, {})[str(player.data['identity']['user_id'])] = [rank]
    f['groups']['Fs0sexp7'][0]['mXQWZ5Ql'] = f.get('slots', '')
    sync_personal_ranking(player, f)
    player.data['exvius_tfa'] = f
    player.dirty = True


def project(player, spec, mid):
    row = _load_ndjson('F_MISSION_MST.ndjson', 'qo3PECw6').get(str(mid))
    if not row or str(row.get('gQR24kST')) != '50':
        return spec
    feature = player.data.get('exvius_tfa', {})
    out = deepcopy(spec)
    for tag, rows in feature.get('groups', {}).items():
        out[tag] = deepcopy(rows)
    if feature.get('pending') and feature.get('candidates'):
        out['u9jY6hQJ'] = [{'UJz5QED2': feature['candidates']}]
    return out


def preview(tier=None, unit_bonus=1000, gambit_bonus=1000):
    # TfaUtil::parseBonusRewardsList: tier@kind:id:rate:category:quantity,
    # with '-' between items. The native parser divides rate by 1000.
    multiplier = max(0, int(unit_bonus)) * max(0, int(gambit_bonus))
    tiers = range(1, 6) if tier is None else [max(1, min(5, int(tier)))]
    groups = []
    for echelon in tiers:
        items = []
        for row in policy()['tiers'][str(echelon)]:
            kind, iid, count = row['reward'].split(':')
            count = max(1, int(count) * multiplier // 1000000)
            items.append(f"{kind}:{iid}:{row['weight']}:{int(row['rare'])}:{count}")
        groups.append(str(echelon) + '@' + '-'.join(items))
    return ','.join(groups)


def claim_token(player):
    import hashlib
    feature = player.data.get('exvius_tfa', {})
    if (player.mode == 'frozen' or feature.get('active') or feature.get('pending')
            or feature.get('claimed') or not feature.get('slots')):
        return ''
    identity = [feature.get('dungeon'), feature['slots'], feature.get('settlements', [])]
    return hashlib.sha256(json.dumps(identity, separators=(',', ':')).encode('utf8')).hexdigest()


def claim_selected(player, token):
    from ffbe_state import State
    if player is None:
        return False
    expected = claim_token(player)
    if player is not State.player or not expected or not secrets.compare_digest(expected, str(token)):
        return False
    from exvius_actions_modes import tfa_fix
    tfa_fix({}, {'e262323b': [{'U9iHsau3': player.data['exvius_tfa']['dungeon'], 'z4EhuqEN': ''}]})
    return bool(player.data['exvius_tfa'].get('claimed'))


def rewards_page(player, ranking=False):
    from html import escape
    from gacha_rates import reward_name
    from player_state import emblem_mst
    if player is None:
        return None
    feature = player.data.get('exvius_tfa', {})
    dungeon = feature.get('dungeon')
    if not dungeon:
        return None
    source = level_rewards()[str(missions(dungeon)[0]['uv60hgDW'])]
    title = 'Ranking Rewards' if ranking else 'Completion Rewards'
    body = '<h1>' + title + '</h1><p>' + escape(source['name']) + '</p>'
    if ranking:
        rows = [(r['rank'], '<br>'.join(escape(label) for label in r['rewards']), False)
                for r in source['ranking']]
        heading = 'Rank'
    else:
        token = claim_token(player)
        if token:
            body += '<p><a class="claim" href="/exvius/clash-rewards.html?claim=' + token + '">Collect selected Fortuna rewards</a></p>'
        elif feature.get('claimed'):
            body += '<p class="received">Selected Fortuna rewards collected.</p>'
        body += '<p>Level rewards are added automatically when you clear each level.</p>'
        rows = []
        for level, entry in sorted(source['levels'].items(), key=lambda item: int(item[0])):
            labels = [escape(reward_name(r)) + ' x ' + format(r['count'], ',') for r in entry['rewards']]
            labels.extend(escape(emblem_mst(i)['G4L0YIB2']) for i in entry['emblems'])
            obtained = int(level) <= int(feature.get('rewarded_level', 0))
            rows.append((level, '<br>'.join(labels) + ('<small>Received</small>' if obtained else ''), obtained))
        heading = 'Level'
    return ('<!doctype html><html lang="en"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1"><title>' + title + '</title>'
            '<style>body{margin:0;padding:14px;background:#081d43;color:white;font:16px Arial,sans-serif}'
            'h1{font-size:21px;color:#ffe398}table{width:100%;border-collapse:collapse}'
            'td,th{padding:12px 9px;border:1px solid #4b6990;text-align:left}'
            'th{background:#194875;color:#ffe398}.received,small{color:#a9e9cb}'
            'small{display:block;margin-top:5px}.obtained{background:#173f48}'
            '.claim{display:block;padding:14px;background:#125e8d;color:white;text-align:center;border:1px solid #a0dfff}</style>'
            '</head><body>' + body + '<table><tr><th>' + heading + '</th><th>Rewards</th></tr>' +
            ''.join('<tr' + (' class="obtained"' if obtained else '') + '><td>' + escape(label) + '</td><td>' + rewards + '</td></tr>'
                    for label, rewards, obtained in rows) + '</table></body></html>')
