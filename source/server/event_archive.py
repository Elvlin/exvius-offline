"""Browse recovered Vortex content without changing mission progress or rewards."""
from collections import defaultdict
from copy import deepcopy
import json
from pathlib import Path

GROUPS = (('all', 'All Events'), ('permanent', 'Permanent'),
          ('season1', 'Season 1'), ('season2', 'Season 2'),
          ('season3', 'Season 3'), ('season4', 'Season 4'),
          ('collaborations', 'Collab'), ('other', 'Other Events'))
_DOCUMENT = None


def document():
    global _DOCUMENT
    if _DOCUMENT is None:
        path = Path(__file__).with_name('event_archive.json')
        _DOCUMENT = json.loads(path.read_text(encoding='utf-8'))
    return _DOCUMENT


def events():
    return document()['events']


def area_ids():
    return [str(event['area']) for event in events()]


def listings():
    """One tile per published campaign, with every original area retained."""
    campaigns = {}
    for row in events():
        identity = (row.get('source_page'), row.get('banner_title'),
                    row.get('release'), row.get('group'))
        # Unidentified records must never collapse merely because fields are empty.
        if not identity[0] or not identity[1]:
            identity = ('area', str(row['area']))
        campaigns.setdefault(identity, []).append(row)
    return [(rows[0], [str(row['area']) for row in rows[1:]])
            for rows in campaigns.values()]


def menu(player, selection=''):
    if ':' in selection:
        return activate_mode(player, selection)
    members = defaultdict(list)
    campaigns = listings()
    rows = [row for row, _aliases in campaigns]
    permanent = [str(row['area']) for row in rows if row['group'] == 'permanent']
    for row in rows:
        members[row['group']].append(str(row['area']))
    groups = []
    for key, label in GROUPS:
        ids = [str(row['area']) for row in rows] if key == 'all' else members[key]
        if key not in ('all', 'permanent'):
            ids = list(dict.fromkeys(permanent + ids))
        groups.append({'id': key, 'label': label, 'ids': ids,
                       'count': len(rows) if key == 'all' else len(members[key]), 'tab': 0})
    if selection:
        if selection not in {row['id'] for row in groups}:
            raise ValueError('Unknown event season')
        if player.data.get('event_archive') != selection:
            player.data['event_archive'] = selection
            player.dirty = True
    selected = player.data.get('event_archive', 'season1') if player else 'season1'
    group = next((row for row in groups if row['id'] == selected), groups[0])
    from player_state import _load_ndjson
    missions = _load_ndjson('F_MISSION_MST.ndjson', 'qo3PECw6')
    modes = {str(row['area']): row['native_mode'] for row in events() if row.get('native_mode')}
    mode_dungeon_ids = sorted({str(m['U9iHsau3']) for m in missions.values()
                               if str(m.get('uv60hgDW')) in modes})
    dungeons = {str(m['U9iHsau3']): {'mode': modes[str(m['uv60hgDW'])], 'area': str(m['uv60hgDW'])}
                for m in missions.values() if str(m.get('uv60hgDW')) in modes
                and str(m.get('gQR24kST')) in ('12', '50')}
    names = {}
    from exvius_fortuna import level_rewards
    cow = level_rewards()
    dark = sorted((r for r in events() if r['name'] == 'Dark Visions'), key=lambda r: int(r['area']))
    numbered = {r['area']: n for n, r in enumerate(dark, 1)}
    for row in events():
        candidates = [did for did in row['dungeons'] if did in dungeons]
        if not candidates:
            continue
        entry = candidates[0]
        for did in candidates:
            dungeons[did]['entry'] = did == entry
        names[entry] = (cow[row['area']]['name'] if row.get('native_mode') == 'tfa' else
                        'Dark Visions ' + str(numbered[row['area']]) if row['area'] in numbered else row['name'])
    return {'groups': groups, 'selected': group, 'area_ids': area_ids(),
            'native_modes': modes, 'native_dungeons': dungeons, 'dungeon_names': names,
            'mode_dungeon_ids': mode_dungeon_ids,
            'area_aliases': {str(row['area']): aliases for row, aliases in campaigns if aliases}}


def activate_mode(player, selection):
    """Select a preserved season before the original native mode scene opens."""
    from exvius_actions_modes import _tfa, _parade
    from player_state import _load_ndjson
    mode, did = selection.split(':', 1)
    allowed = {str(row['area']): row.get('native_mode') for row in events()}
    rows = [r for r in _load_ndjson('F_MISSION_MST.ndjson', 'qo3PECw6').values()
            if str(r.get('U9iHsau3')) == did and str(r.get('gQR24kST')) in ('12', '50')]
    if (player is None or player.mode == 'frozen' or not rows or mode not in ('tfa', 'parade')
            or any(allowed.get(str(r.get('uv60hgDW'))) != mode for r in rows)):
        raise ValueError('Unknown event season')
    area = str(rows[0]['uv60hgDW'])
    feature = deepcopy(player.data.get('exvius_' + mode, {}))
    if feature.get('active'):
        raise ValueError('Finish or retire the current battle first')
    if mode == 'tfa':
        _tfa(feature, did)
        party_kind = '11'
    else:
        _parade(feature, area, player)
        party_kind = '8'
    player.data['exvius_' + mode] = feature
    player.dirty = True
    groups = deepcopy(feature['groups'])
    groups.update(player.special_party_groups(party_kind))
    groups['8PEB5o7G'] = [{'r21y0YzS': str(player.data['party']['active_deck']),
                          'b61ICxJk': str(player.special_party('8')['active_deck'])
                          if mode == 'parade' else '0', 'Isc1ga3G': '-1', 'igrz05CY': '-1'}]
    result = {'mode': mode, 'area': area, 'dungeon': did,
              'native_groups': groups, 'scene': 940000 if mode == 'tfa' else 'parade'}
    if mode == 'tfa':
        event = next(r for r in groups['L6XRZb0z'] if str(r['U9iHsau3']) == did)
        ranking_id = str(event['L84eYzxv'])
        result['ranking_id'] = int(ranking_id)
        result['ranking_rewards'] = [r for r in _load_ndjson('F_SUMALLY_REWARD_MST.ndjson')['__rows__']
                                     if str(r['L84eYzxv']) == ranking_id]
        if not result['ranking_rewards']:
            raise ValueError('Clash ranking rewards are missing')
    return result
