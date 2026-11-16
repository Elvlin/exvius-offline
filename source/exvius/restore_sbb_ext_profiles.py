"""Restore the documented Global SBB EXT tiers through authored native bundles.

Guide values belong to the explicit EXT tab. Original SBB models, actions and
Global skill definitions supply the matching boss behavior, never a story boss.
Unpublished EXT fields remain identified in the source contract.
"""
from copy import deepcopy
import json
from pathlib import Path
import re
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'source/server'))
from battle_content import IndexSource, PARTS_TOKENS, PARTS_DEFAULTS

SOURCE = ROOT / 'source/server/content/sbb_ext_sources.json'
STAT_FIELDS = {'hp': 'fh31sk7B', 'mp': 'PC97pWQj', 'level': '7wV3QZ80',
               'atk': '9NBV1XCS', 'def': 'Pn5w9dfh', 'mag': '84FJM3PD', 'spr': 'T8xMDAZ4'}


def original_global_skills(base, set_ids):
    """Use the established datamine-to-native conversion for original GL skills."""
    sets = {}
    path = ROOT / 'data/mst_decoded/F_MONSTER_SKILL_SET_MST.ndjson'
    for line in path.read_text(encoding='utf-8').splitlines():
        row = json.loads(line)
        if row['A5x02C6a'] in set_ids:
            sets[row['A5x02C6a']] = row
    with zipfile.ZipFile(ROOT / 'repository snapshots/aEnigmatic__ffbe-95727376e82d.zip') as archive:
        raw = json.loads(archive.read(next(n for n in archive.namelist() if n.endswith('/monster_skills.json'))))
    native = {row['6E5u1xrs']: row for row in base.load('F_MONSTER_SKILL_MST')}
    templates = {kind: next(row for row in native.values()
                           if row['Isb1GDe2'] == kind and row.get('5w1o9DPV') == '0')
                 for kind in ('1', '2', '3', '4')}
    result = {}
    for set_id in set_ids:
        for sid in sets[set_id]['7qxLC5hP'].split(','):
            if not sid:
                continue
            if sid not in raw:
                if sid not in native:
                    raise ValueError('Missing original SBB skill ' + sid)
                result[sid] = deepcopy(native[sid])
                continue
            skill = raw[sid]
            kind = {'Physical': '1', 'Magic': '2', 'Hybrid': '3', 'None': '4'}[skill['attack_type']]
            row = deepcopy(templates[kind])
            effects = skill['effects_raw']
            row.update({'6E5u1xrs': sid, 'G4L0YIB2': skill['name'], '8cY9hejo': '0',
                        'oPD4yL58': '@'.join(str(e[0]) for e in effects),
                        'a4hXTIm0': '@'.join(str(e[1]) for e in effects),
                        '2kq0BpnD': '@'.join(str(e[2]) for e in effects),
                        'PI18xnkD': '@'.join('0' for e in effects),
                        'Ha9G5sCS': '@'.join(','.join(str(v) for v in e[3]) for e in effects),
                        '7irj9hAb': ','.join(str(int(flag)) for flag in skill['flags'])})
            desc = str(skill.get('effects', '')).casefold()
            row['Jn6BbR2P'] = ','.join('1' if re.search(r'\b' + element + r'\b[^.;]*damage', desc) else '0'
                                     for element in ('fire', 'ice', 'lightning', 'water', 'wind', 'earth', 'light', 'dark'))
            result[sid] = row
    return result


def proposals(document):
    """Return only five owned entries. The caller coordinates the shared merge."""
    contract = json.loads(SOURCE.read_text(encoding='utf-8'))
    base = IndexSource()
    parts = {row['xqartN26']: row for row in base.load('F_MONSTER_PARTS_MST')}
    monsters = {row['xqartN26']: row for row in base.load('F_MONSTER_MST')}
    set_ids = {actor['behavior_source']['skill_set'] for stage in contract['missions'].values()
               for actor in stage['waves']}
    skills = original_global_skills(base, set_ids)
    source_sets = {json.loads(line)['A5x02C6a']: json.loads(line)
                   for line in (ROOT / 'data/mst_decoded/F_MONSTER_SKILL_SET_MST.ndjson').read_text(encoding='utf-8').splitlines()}
    result = {}
    for mid, stage in contract['missions'].items():
        entry = deepcopy(document['missions'][mid])
        old = entry['bundle']
        if len(old['an6TB4WS']) != stage['contract']['waves']:
            raise ValueError('Original EXT wave contract changed: ' + mid)
        old_parts = {r['xqartN26']: r for r in old['bV34YIJQ'] if r['6Yc4RkdM'] == '1'}
        phases, placements, profiles, actors, carriers = [], [], [], [], []
        passive_sets, passive_skills = [], []
        donor_totals = {token: sum(int(parts[a['donor']].get(token) or 0) for a in stage['waves'])
                        for token in ('B6H34Mea', '7UR4J2SE')}
        allocated = {'B6H34Mea': 0, '7UR4J2SE': 0}
        for index, actor in enumerate(stage['waves'], 1):
            donor, pid = actor['donor'], actor['local_actor']
            phase = deepcopy(old['an6TB4WS'][index - 1])
            old_gid = phase['2fY1IomW']
            old_slot = next(r for r in old['Bi6hVv34'] if r['2fY1IomW'] == old_gid and r['WJdBp9f0'] == '1')
            old_profile = old_parts[old_slot['xqartN26']]
            gid = actor['original_challenge_group']
            phase.update({'6uIYE15X': gid, '2fY1IomW': gid})
            phases.append(phase)
            slot = deepcopy(old_slot)
            slot.update({'2fY1IomW': gid, 'xqartN26': pid, 'Z0EN6jSh': '1'})
            placements.append(slot)
            profile = {token: parts[donor].get(token, PARTS_DEFAULTS.get(token, '')) for token in PARTS_TOKENS}
            profile.update({'xqartN26': pid, 'G4L0YIB2': actor['name'],
                            '8a6gAwN9': actor['behavior_source']['ai'],
                            'A5x02C6a': actor['behavior_source']['skill_set']})
            for field, value in actor['published_base_stats'].items():
                if value is not None:
                    profile[STAT_FIELDS[field]] = str(value)
            for token, value in actor['published_resistance_fields'].items():
                profile[token] = value
            native_passive = actor.get('native_published_passive')
            if native_passive:
                profile['jmKe42Yg'] = native_passive['set_id']
                passive_sets.append({'jmKe42Yg': native_passive['set_id'],
                                     '4kVnNws6': native_passive['skill_id']})
                passive_skills.append({'6oWt9bL3': native_passive['skill_id'],
                                       '2kq0BpnD': native_passive['effects'],
                                       'Ha9G5sCS': native_passive['arguments']})
            else:
                # A dangling Normal-tier set does not establish EXT passives.
                profile['jmKe42Yg'] = '0'
            # This lane preserves the coordinated reward owner's per-wave values.
            for token in ('B6H34Mea', '7UR4J2SE', 'ATM35pjf', '9BetM2Ds', 'MZn8LC6H', 'g4voc2Aw', 'Vf5DGw07',
                          '3frn4ILX', 'IRf10dwx', 'e5xoiC84', 'm28pD1GM'):
                profile[token] = old_profile.get(token, '')
            for token, total in (('B6H34Mea', stage['reward_totals']['unit_exp']),
                                 ('7UR4J2SE', stage['reward_totals']['gil'])):
                amount = (total - allocated[token] if index == len(stage['waves']) else
                          total * int(parts[donor].get(token) or 0) // donor_totals[token])
                profile[token] = str(amount)
                allocated[token] += amount
            profiles.append(profile)
            actors.append({'xqartN26': pid, 'G4L0YIB2': actor['name'], 'V9j8wJcC': monsters[donor]['V9j8wJcC']})
            drop = deepcopy(next(r for r in old['y35YvQjZ'] if r['6v7y3QcJ'] == str(index)))
            drop.update({'2fY1IomW': gid, 'xqartN26': pid, 'Z0EN6jSh': '1', '6Yc4RkdM': '1'})
            carriers.append(drop)
        new_sets = {a['behavior_source']['skill_set'] for a in stage['waves']}
        new_skills = {sid for sidset in new_sets for sid in source_sets[sidset]['7qxLC5hP'].split(',') if sid}
        old.update({'an6TB4WS': phases, 'Bi6hVv34': placements, 'bV34YIJQ': profiles,
                    'wbet57nF': actors, 'y35YvQjZ': carriers,
                    'Wp39QX52': [skills[sid] for sid in sorted(new_skills, key=int)],
                    '8CoiSdu4': passive_sets, 'MLj0dJa8': passive_skills})
        entry['sbb_ext_source'] = deepcopy(stage)
        entry['source_page'] = stage['source']['title']
        entry['source_revision'] = stage['source']['revision']
        entry['source_url'] = stage['source']['url']
        entry['identity_source'] = 'Own Global EXT mission contract and explicit EXT guide tab'
        entry['enemies'] = [{'enemy': actor['name'], 'donor': actor['donor'],
                             'published_stats': actor['published_base_stats'],
                             'behavior_source': actor['behavior_source'],
                             'remaining_unpublished_fields': actor['remaining_unpublished_fields']}
                            for actor in stage['waves']]
        result[mid] = entry
    return result


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    document = json.loads((ROOT / 'source/server/event_encounters.json').read_text(encoding='utf-8'))
    result = proposals(document)
    args.output.write_text(json.dumps({'missions': result}, ensure_ascii=False, separators=(',', ':')) + '\n', encoding='utf-8')
    print('Prepared ' + str(len(result)) + ' scoped SBB EXT entries: ' + str(args.output))
