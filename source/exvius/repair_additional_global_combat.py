"""Author own-stage combat for the additional source-proven Global campaigns.

This helper returns entries for the encounter-data owner's scoped merge. It does
not write event_encounters.json or run the game. Source facts stay outside bundles.
"""
import copy
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'source/exvius'), str(ROOT / 'source/server')]

# Explicit assignments remain stable when another campaign is added later.
AREA_CODES = {
    '756': 1, '965': 2, '976': 3, '1037': 4, '1073': 5, '1084': 6,
    '1089': 7, '1090': 8, '3048': 9, '3049': 10, '3050': 11,
    '3051': 12, '3052': 13, '3110': 14, '3150': 15, '3162': 16,
    '3176': 17, '3197': 18, '3220': 19, '3234': 20, '3245': 21,
    '3261': 22, '3287': 23, '4172': 24, '4192': 25, '5011': 26,
    '5111': 27, '6112': 28, '6113': 29,
}


def sequence(area, mission):
    """Use the explicit area assignment and preserved source stage suffix."""
    suffix = int(mission) % 1000
    # Global moved later 965-prefixed intros into older or dedicated areas.
    # Their suffix must not collide with that area's original 756-prefixed row.
    if not str(mission).startswith(area):
        suffix += 500
    if suffix >= 1000:
        raise ValueError('Additional Global stage suffix needs an explicit assignment')
    return 50000 + AREA_CODES[area] * 1000 + suffix


def source_reader():
    from repair_omitted_global_combat import source_reader as existing_reader
    from reconstruct_event_battles import key
    reader = existing_reader()
    document = json.loads((ROOT / 'logs/reference/restored-event-rewards-wiki-20261111.json')
                          .read_text(encoding='utf8'))
    for row in document.get('query', {}).get('redirects', []):
        reader.redirects[key(row['from'])] = key(row['to'])
    return reader


def source_identities():
    return json.loads((ROOT / 'source/server/content/omitted_global_event_sources.json')
                      .read_text(encoding='utf8'))['events']


def own_missions():
    from build_event_archive import rows
    return {row['qo3PECw6']: row for row in rows('F_MISSION_MST')}


def stage_records(reader):
    """Join only published native stages to their own primary battle records."""
    from build_event_archive import rows
    identities = source_identities()
    dungeons = {r['U9iHsau3']: r['uv60hgDW'] for r in rows('F_DUNGEON_MST')}
    translated = {r['key'].rsplit('_', 1)[-1] for r in rows('F_TEXT_MISSION', True)}
    missions = own_missions()
    published = {}
    for mid, row in missions.items():
        area = dungeons.get(row['U9iHsau3'])
        if area in AREA_CODES and area in identities and mid in translated:
            published.setdefault(area, []).append(mid)
    titles = {
        '1037': 'The Steel Dummy', '1073': 'The Steel Dummy (2021)',
        '1084': 'Tomb Raider: Lost Valley',
        '3110': 'FFRK Equipment Enhancement Event', '3150': 'VS Specimen H0512',
        '3162': 'FFBE Season 1', '3176': 'VS Two-Headed Frost Dragon',
        '3197': "Seasons' Greetings", '3220': 'The Festival of Visions/Craft Material Quest',
        '3234': 'A Friend Like You/Craft Material Quest',
        '3245': "A Hero's Return/Craft Material Quest", '3261': 'Chosen by Auracite',
        '3287': 'Dominant Awakened', '4172': 'Final Fantasy X-2 Character Battle',
        '4192': 'Chrono Cross Character Battle', '5011': 'Guided by Conviction/Craft Material Quest',
        '5111': "The Destroyers' Journey/Craft Material Quest",
        '6112': 'DRAGON QUEST The Adventure of Dai Character Battle I',
        '6113': 'DRAGON QUEST The Adventure of Dai Character Battle II',
    }
    for area, esper in zip(('3048', '3049', '3050', '3051', '3052'),
                            ('Shiva', 'Odin', 'Tetra Sylphid', 'Alexander', 'Fenrir')):
        titles[area] = 'Genesis of Chaos -DARK VISIONS-/Rampaging ' + esper
    result = {}
    for area, mids in published.items():
        records = reader.records(titles[area])
        if area == '1084':
            records = [r for r in records if r['heading'] == 'Tomb Raider: Lost Valley - Daily']
        mids.sort(key=int)
        if len(records) not in (1, len(mids)):
            raise ValueError('Own additional stage source is ambiguous: ' + area)
        for index, mid in enumerate(mids):
            record = copy.deepcopy(records[0 if len(records) == 1 else index])
            record['fields'].setdefault('battle', missions[mid]['8xi6Xvyk'])
            result[mid] = area, record
    if len(result) != 181:
        raise ValueError('Published non-intro additional scope changed')
    return result


def character_source(reader):
    """Restore missing player-model NPCs through the retained character path."""
    from reconstruct_event_battles import key
    from restore_event_battles import ReconstructionSource
    ids = ('999075700', '999076700', '999077700', '999078700', '999079700',
           '999081700', '999093700', '999094700', '999095700')
    prototype = reader.parts['999089700'][0]
    if prototype['3HriTp6B'] == '0' or prototype['8a6gAwN9'] != '109':
        raise ValueError('Preserved character-battle NPC source changed')
    added_monsters, added_parts, sets = [], [], []
    notes = {}
    for actor in ids:
        name = reader.names[actor]
        units = [u for u in reader.unit_names[key(name)] if int(u) % 100 < 10]
        if len(set(units)) != 1:
            raise ValueError('Own original Global character form is ambiguous: ' + name)
        unit = reader.units[units[0]]
        part = copy.deepcopy(prototype)
        part.update(xqartN26=actor, G4L0YIB2=name, **{'3HriTp6B': unit['3HriTp6B'],
            '8a6gAwN9': '109', 'A5x02C6a': actor if actor in reader.global_sets else '0',
            'B6H34Mea': '0', '7UR4J2SE': '0', 'e56NZY42': '0'})
        for token in ('5A8SmwyC', 'a9DvZ70c', '7KYufEd5', 'w04FtZqB', 'rtw4F6hn', 'rB70Ls63'):
            if token in unit:
                part[token] = unit[token]
        for token in ('9BetM2Ds', 'MZn8LC6H', 'g4voc2Aw', 'Vf5DGw07'):
            part[token] = ''
        if actor in reader.global_sets:
            reader.recover_skills(actor, only_missing=True)
            sets.append(reader.global_sets[actor])
        added_monsters.append({'xqartN26': actor, 'G4L0YIB2': name,
                               'V9j8wJcC': str(int(actor) // 100)})
        added_parts.append(part)
        notes[actor] = {'enemy': name, 'global_unit': unit['3HriTp6B'],
            'own_original_monster_skillset': actor if actor in reader.global_sets else None,
            'reconstructed': 'Own original Global unit model/passives and preserved '
                'character-battle NPC AI109. Unpublished HP50000/MP500/level45 '
                'and remaining combat stats use the retained same-family NPC profile. '
                'Kid has no retained monster skill set; zero uses the native no-set sentinel.'}
    def merged(table, additions, token):
        replace = {r[token]: r for r in additions}
        base = reader.base.load(table)
        return [replace.pop(r[token], r) for r in base] + list(replace.values())
    source = ReconstructionSource(reader.base, {
        'F_MONSTER_MST': merged('F_MONSTER_MST', added_monsters, 'xqartN26'),
        'F_MONSTER_PARTS_MST': reader.base.load('F_MONSTER_PARTS_MST') + added_parts,
        'F_MONSTER_SKILL_SET_MST': merged('F_MONSTER_SKILL_SET_MST', sets, 'A5x02C6a'),
        'F_MONSTER_SKILL_MST': list(reader.skill_rows.values()),
    })
    return source, notes


def _source_names(text):
    from reconstruct_event_battles import linked_enemies, key
    aliases = {'belmeraslackey': 'belmeralackey', 'archaeodemon': 'archeodemon'}
    result = {}
    for match in re.finditer(r'\[\[([^\]]+)\]\](?:\s*\((\d+)\))?', text):
        pair = linked_enemies(match[0])
        if not pair:
            continue
        title, name = pair[0]
        normalized = aliases.get(key(name), key(name))
        result.setdefault(normalized, {'title': title, 'name': name, 'count': 0})
        result[normalized]['count'] += int(match[2] or 1)
    return result


def retained_stage(reader, source, area, mid, mission, record, character_notes):
    """Keep an identity-checked retained graph; project only its own outcomes."""
    from battle_content import derive_mission
    from reconstruct_event_battles import key, numeric
    from repair_omitted_global_combat import own_item_drops
    bundle = derive_mission(mid, source)
    old_monsters = {r['xqartN26']: r for r in bundle['wbet57nF']}
    old_parts = {}
    for row in bundle['bV34YIJQ']:
        old_parts.setdefault(row['xqartN26'], []).append(row)
    raw_parts = {(r['xqartN26'], r['6Yc4RkdM']): r
                 for r in source.load('F_MONSTER_PARTS_MST')}
    old_groups = {}
    for row in bundle['Bi6hVv34']:
        old_groups.setdefault(row['2fY1IomW'], []).append(row)
    expected = _source_names(record['fields'].get('monster', '') + record['fields'].get('boss', ''))
    aliases = {'belmeraslackey': 'belmeralackey', 'archaeodemon': 'archeodemon'}
    actual = {}
    occurrences = []
    for phase in bundle['an6TB4WS']:
        if phase['gou39JeI'] != '2':
            raise ValueError('Unexpected story phase in own additional combat: ' + mid)
        slots = sorted(old_groups[phase['2fY1IomW']], key=lambda r: int(r['Z0EN6jSh']))
        for slot in slots:
            actor = slot['xqartN26']
            name = reader.names.get(actor) or reader.dictionary_labels.get(old_monsters[actor]['V9j8wJcC'])
            normalized = aliases.get(key(name or ''), key(name or ''))
            if normalized not in expected:
                raise ValueError('Unrelated numeric-ID enemy in own stage: ' + mid + ':' + str(name))
            actual[normalized] = actual.get(normalized, 0) + 1
            occurrences.append((phase, slot, actor, name or expected[normalized]['name']))
    if actual != {n: r['count'] for n, r in expected.items()}:
        raise ValueError('Own published formation counts differ: ' + mid + ':' + str(actual))
    count = len(occurrences)
    serial = sequence(area, mid)
    actor_base, group_base = 1840000000 + serial * 100, 1910000000 + serial * 10
    result = {k: copy.deepcopy(v) for k, v in bundle.items()
              if k not in ('an6TB4WS', 'Bi6hVv34', 'wbet57nF', 'bV34YIJQ', 'y35YvQjZ')}
    for k in ('an6TB4WS', 'Bi6hVv34', 'wbet57nF', 'bV34YIJQ', 'y35YvQjZ'):
        result[k] = []
    actors, bodies, provenance = [], [], []
    for number, (phase, slot, old_actor, name) in enumerate(occurrences, 1):
        actor = str(actor_base + number)
        group = str(group_base + int(phase['6v7y3QcJ']))
        if not any(p['6v7y3QcJ'] == phase['6v7y3QcJ'] for p in result['an6TB4WS']):
            result['an6TB4WS'].append(dict(phase, **{'2fY1IomW': group}))
        result['Bi6hVv34'].append(dict(slot, xqartN26=actor, **{'2fY1IomW': group}))
        result['wbet57nF'].append(dict(old_monsters[old_actor], xqartN26=actor, G4L0YIB2=name))
        for old_part in old_parts[old_actor]:
            part = dict(old_part, xqartN26=actor, G4L0YIB2=name)
            result['bV34YIJQ'].append(part)
            if part['6Yc4RkdM'] == '1':
                bodies.append(part)
            raw = raw_parts[(old_actor, part['6Yc4RkdM'])]
            result['y35YvQjZ'].append({'qo3PECw6': mid, '6v7y3QcJ': phase['6v7y3QcJ'],
                'pIHCrf40': '1', '2fY1IomW': group, 'xqartN26': actor,
                'Z0EN6jSh': slot['Z0EN6jSh'], '6Yc4RkdM': part['6Yc4RkdM'],
                **{k: raw.get(k, '') for k in ('9BetM2Ds', 'MZn8LC6H', 'g4voc2Aw',
                    'Vf5DGw07', '3frn4ILX', 'IRf10dwx', 'ATM35pjf', 'e5xoiC84')}})
        if old_actor in character_notes:
            provenance.append(character_notes[old_actor])
        actors.append(old_actor)
    totals = {}
    for field, token in (('gil', '7UR4J2SE'), ('unit-exp', 'B6H34Mea')):
        total = numeric(record['fields'].get(field, ''))
        current = sum(int(p[token]) for p in bodies)
        if total is None:
            total = current + (int(mission['7UR4J2SE']) if field == 'gil' else 0)
        # Preserve original per-enemy allocation where possible. The native
        # client does not add the mission's server-side base gil itself.
        delta = total - current
        if int(bodies[-1][token]) + delta >= 0:
            bodies[-1][token] = str(int(bodies[-1][token]) + delta)
        else:
            for i, part in enumerate(bodies):
                part[token] = str(total // count + (i < total % count))
        totals[field] = total
    text = record['fields'].get('drop', '')
    points = re.search(r"'''([\d,]+) event points'''", text)
    cleaned = re.sub(r"'''[\d,]+ event points'''(?:<br\s*/?>)?", '', text)
    cleaned = cleaned.replace('{{Currency|', '{{Item|')
    explicit = bool(re.search(r'\{\{Item\|[^{}|]+\|[\d,-]+\}\}|\]\]\s*\(\d+\)', cleaned))
    drop_notes = []
    if explicit:
        drops, drop_notes = own_item_drops(cleaned)
        for row in result['y35YvQjZ']:
            for channel in ('9BetM2Ds', 'MZn8LC6H', 'g4voc2Aw', 'Vf5DGw07'):
                row[channel] = ''
        result['y35YvQjZ'][-1].update(drops)
    result['1IfDqR4n'] = [copy.deepcopy(mission)]
    entry = {'bundle': result, 'source_page': record['page']['title'],
        'source_revision': record['page']['revisions'][0].get('revid'),
        'additional_global_source': {'area': area, 'mission': mid,
            'source_heading': record['heading'], 'battle_fields': copy.deepcopy(record['fields']),
            'retained_phase_source': record.get('retained_phase_source', mid),
            'retained_own_actors': actors, 'documented_totals': totals,
            'documented_event_points': int(points[1].replace(',', '')) if points else 0,
            'character_profiles': provenance, 'drop_notes': drop_notes,
            'projection': 'Preserved own identity-checked native formations, profiles, '
                'skills and per-slot drop carriers. Explicit published item amounts '
                'are attached once to the final own enemy. Whole-stage EXP/gil are '
                'projected onto the actual own actors; original mission rows stay intact. '
                'Unpublished crafting quantities retain their own indexed carrier values.'}}
    labels = {r['xqartN26']: r['G4L0YIB2'] for r in result['wbet57nF']}
    labels.update({r['xqartN26'] + chr(64 + int(r['6Yc4RkdM'])): r['G4L0YIB2']
                   for r in result['bV34YIJQ']})
    return entry, labels


def new_source_stage(reader, area, mid, mission, record):
    """Build the documented single-wave stages absent from the retained graph."""
    from reconstruct_event_battles import linked_enemies, key, fields, numeric, ELEMENTS
    from build_raid_archive import templates
    from repair_omitted_global_combat import (
        assemble_owned_stage, own_item_drops, own_published_profiles)
    record = copy.deepcopy(record)
    foes = linked_enemies(record['fields'].get('monster', '') + record['fields'].get('boss', ''))
    if mission['8xi6Xvyk'] != '1' or not foes:
        raise ValueError('Own missing stage needs a documented bounded formation: ' + mid)
    if area in ('3162', '3197'):
        from battle_content import resolve_pool
        donors = {}
        for phase in reader.source_phases[mid]:
            target = phase['6uIYE15X']
            group = resolve_pool(reader.source_pools[target], target)[0]
            for slot in reader.source_groups[group]:
                actor = slot['xqartN26']
                if actor in reader.parts:
                    donors[reader.names[actor]] = actor
        if not all(name in donors for _, name in foes):
            raise ValueError('Own original CoB tier profile is incomplete: ' + mid)
        record['native_donor_by_name'] = donors
    if area in ('1037', '1073'):
        record['native_enemy_overrides'] = {'Steel Dummy':
            {'part_id': '900010878', 'ai': '900010878'}}
    elif area == '1084':
        record['native_enemy_overrides'] = {'T-Rex':
            {'part_id': '900011083', 'ai': '900011083'}}
    contract = {'source_heading': record['heading'],
                'source_page': 'https://exvius.fandom.com/wiki/' + record['page']['title'].replace(' ', '_')}
    own_published_profiles(reader, record, contract, foes)
    if area in ('3162', '3197') and record['heading'].endswith('ADV'):
        target = 'Pegasus' if area == '3162' else 'Fenice'
        strong = {'Dagger', 'Great Sword'} if area == '3162' else {'Sword', 'Staff', 'Bow'}
        order = ('Dagger', 'Sword', 'Great Sword', 'Katana', 'Staff', 'Rod', 'Bow',
                 'Axe', 'Hammer', 'Spear', 'Instrument', 'Whip', 'Throwing', 'Gun', 'Mace', 'Fist')
        text = reader.text(record['page'])
        broken = None
        for offset, block in templates(text, 'Boss Infobox'):
            spec = fields(block)
            tabs = re.findall(r'(?:<tabber>|\|-\|)\s*([^=\n]+)=', text[:offset])
            if spec.get('name') == target and tabs and tabs[-1].strip().casefold() == 'broken':
                broken = spec
        if broken is None:
            raise ValueError('Own documented broken form is absent: ' + mid)
        record['own_break'] = {
            'break_hp': 3000, 'break_hp_after_first': 3000, 'turns': 3, 'broken': None,
            'RHe5r72C': ','.join('100' if w in strong else '2000' for w in order),
            'EwZ40mt3': ','.join('1' if w in strong else '0' for w in order),
            'resists': {'hn42BL3Q': ','.join(str(numeric(broken.get(w, '')) or 0)
                                            for w in ELEMENTS) + ',0'},
            'source': contract['source_page'],
            'reconstructed': 'Own guide documents3turns, exact strong-weapon group '
                'and exact Base/Broken elemental changes, but leaves gauge HP, '
                'growth and strong damage uncertain.3000HP/no growth follows the '
                'retained same-era Global CoB gauge reconstruction. Strong100/other5 '
                'and unchanged unpublished combat stats are explicit local values.'}
    drop, notes = own_item_drops(record['fields'].get('drop', '').replace('{{Currency|', '{{Item|'))
    owner = next((i for i, (_, name) in enumerate(foes, 1)
                  if name == ('Pegasus' if area == '3162' else 'Fenice')), len(foes))
    entry, labels = assemble_owned_stage(reader, mid, mission, record, [foes],
        sequence(area, mid), drops={(1, owner): drop} if drop else None)
    # The FFBE S1 gauge belongs to Pegasus, not its two elemental attendants.
    if area == '3162' and record.get('own_break'):
        bundle = entry['bundle']
        keep = {r['xqartN26'] for r in bundle['wbet57nF'] if r['G4L0YIB2'] == 'Pegasus'}
        for part in bundle['bV34YIJQ']:
            if part['xqartN26'] not in keep:
                part['e56NZY42'] = '0'
        bundle['BJ6A0KTt'] = [r for r in bundle.get('BJ6A0KTt', []) if r['e56NZY42'] in keep]
        bundle['7KCkJd1E'] = [r for r in bundle.get('7KCkJd1E', []) if r['e56NZY42'] in keep]
    entry['additional_global_source'] = {
        'area': area, 'mission': mid, 'source_heading': record['heading'],
        'battle_fields': copy.deepcopy(record['fields']), 'drop_notes': notes,
        'profile_note': 'Own retained Global model/dictionary and native AI are used. '
            'Published stage totals and drops are exact; unavailable historical '
            'presentation/stat details remain explicitly reconstructed.'}
    return entry, labels


def checked_ids(entries, base, current):
    """Reject a source-authoring identity collision outside this exact scope."""
    actors = {row['xqartN26'] for row in base.load('F_MONSTER_MST')}
    groups = {row['2fY1IomW'] for row in base.load('F_BATTLE_GROUP_MST')}
    for mid, entry in current.items():
        if mid in entries:
            continue
        actors.update(row['xqartN26'] for row in entry['bundle'].get('wbet57nF', []))
        groups.update(row['2fY1IomW'] for row in entry['bundle'].get('Bi6hVv34', []))
    authored_actors, authored_groups = set(), set()
    for mid, entry in entries.items():
        bundle = entry['bundle']
        for row in bundle['wbet57nF']:
            value = row['xqartN26']
            if value in actors or value in authored_actors or not 0 < int(value) < 2147483647:
                raise ValueError('Additional Global actor identity collision: ' + mid)
            authored_actors.add(value)
        for value in {row['2fY1IomW'] for row in bundle['Bi6hVv34']}:
            if value in groups or value in authored_groups or not 0 < int(value) < 2147483647:
                raise ValueError('Additional Global group identity collision: ' + mid)
            authored_groups.add(value)


def build_entries(reader=None, document=None):
    reader = reader or source_reader()
    records, missions = stage_records(reader), own_missions()
    source, character_notes = character_source(reader)
    entries, labels = {}, {}
    for mid, (area, record) in records.items():
        if area in ('1037', '1073', '1084', '3162', '3197'):
            entry, names = new_source_stage(reader, area, mid, missions[mid], record)
        else:
            own_source = source
            if not reader.source_phases[mid] and area in (
                    '3220', '3234', '3245', '5011', '5111', '4172', '4192', '6112', '6113'):
                from restore_event_battles import ReconstructionSource
                siblings = [other for other, (a, r) in records.items()
                            if a == area and reader.source_phases[other]
                            and r['page']['title'] == record['page']['title']]
                if not siblings:
                    raise ValueError('Own daily campaign blueprint is unavailable: ' + mid)
                original = min(siblings, key=int)
                for token in ('B6kyCQ9M', '8xi6Xvyk', 'B6H34Mea'):
                    if missions[mid][token] != missions[original][token]:
                        raise ValueError('Own dated daily stage contract differs: ' + mid)
                phases = [dict(p, qo3PECw6=mid) for p in reader.source_phases[original]]
                own_source = ReconstructionSource(source, {'F_MISSION_PHASE_MST': phases})
                record['retained_phase_source'] = original
            entry, names = retained_stage(reader, own_source, area, mid, missions[mid], record, character_notes)
        entries[mid] = entry
        labels.update(names)
    document = document or json.loads((ROOT / 'source/server/event_encounters.json')
                                      .read_text(encoding='utf8'))
    current = document['missions']
    checked_ids(entries, reader.base, current)
    return entries, labels


def build(document=None):
    return build_entries(document=document)


def write_report():
    """Inspect effective authored native data, without starting a game or build."""
    import hashlib
    from collections import Counter
    from build_event_archive import rows
    from reconstruct_event_battles import numeric
    reader = source_reader()
    definitions, missions = stage_records(reader), own_missions()
    document = json.loads((ROOT / 'source/server/event_encounters.json').read_text(encoding='utf8'))
    responses = json.loads((ROOT / 'source/server/responses.json').read_text(encoding='utf8'))
    items = {r['tL6G9egd'] for r in rows('F_ITEM_MST')}
    points = json.loads((ROOT / 'source/server/raid_archive.json').read_text(encoding='utf8'))['events']
    point_missions = {str(mid): (event, amount) for event in points
                      if event.get('point_mode') == 'clear'
                      for mid, amount in event.get('mission_points', {}).items()}
    areas = {}
    for mid, (area, record) in definitions.items():
        summary = areas.setdefault(area, {'area': area,
            'name': source_identities()[area]['canonical_name'], 'missions': [],
            'routes': [], 'blockers': []})
        summary['missions'].append(mid)
        entry = document['missions'].get(mid, {})
        bundle = responses.get('jnw49dUq@' + mid, entry.get('bundle', {}))
        errors = []
        if not entry.get('additional_global_source'):
            errors.append('Scoped own-source projection has not been merged')
        phases = [p for p in bundle.get('an6TB4WS', []) if p.get('gou39JeI') == '2']
        if len(phases) != int(missions[mid]['8xi6Xvyk']):
            errors.append('Own Global combat wave count is incomplete')
        parts = {(r['xqartN26'], r['6Yc4RkdM']): r for r in bundle.get('bV34YIJQ', [])}
        monsters = {r['xqartN26']: r for r in bundle.get('wbet57nF', [])}
        slots = {(p['6v7y3QcJ'], g['2fY1IomW'], g['xqartN26'], g['Z0EN6jSh'])
                 for p in phases for g in bundle.get('Bi6hVv34', [])
                 if g['2fY1IomW'] == p['2fY1IomW']}
        for phase in phases:
            group = [g for g in bundle.get('Bi6hVv34', []) if g['2fY1IomW'] == phase['2fY1IomW']]
            if not group:
                errors.append('Combat phase has no own formation')
            for slot in group:
                actor = slot['xqartN26']
                part = parts.get((actor, '1'))
                if actor not in monsters or not part or int(part.get('fh31sk7B') or 0) <= 0:
                    errors.append('Own enemy/model/body profile is incomplete')
                if part and part.get('3HriTp6B', '0') not in ('', '0') and part['3HriTp6B'] not in reader.units:
                    errors.append('Own Global player-model NPC form is missing')
        actual_items = Counter()
        for row in bundle.get('y35YvQjZ', []):
            owner = tuple(row.get(k) for k in ('6v7y3QcJ', '2fY1IomW', 'xqartN26', 'Z0EN6jSh'))
            if owner not in slots or (row['xqartN26'], row['6Yc4RkdM']) not in parts:
                errors.append('Drop carrier does not belong to its actual own slot/part')
            for channel in ('9BetM2Ds', 'MZn8LC6H', 'g4voc2Aw', 'Vf5DGw07'):
                for value in row.get(channel, '').split(','):
                    if not value:
                        continue
                    values = value.split(':')
                    try:
                        kind, iid, quantity, rate = int(values[0]), values[1], int(values[2]), float(values[3])
                        if quantity <= 0 or not 0 <= rate <= 100:
                            raise ValueError('quantity/rate')
                        if kind == 20 and iid not in items:
                            raise ValueError('original Global item')
                        if kind == 10 and iid not in reader.units:
                            raise ValueError('original Global capture unit')
                        if kind == 20:
                            actual_items[iid] += quantity
                    except (ValueError, IndexError):
                        errors.append('Invalid or unresolved own native reward tuple: ' + value)
        totals = {field: sum(int(p[token]) for p in parts.values() if p['6Yc4RkdM'] == '1')
                  for field, token in (('gil', '7UR4J2SE'), ('unit-exp', 'B6H34Mea'))}
        for field in totals:
            expected = numeric(record['fields'].get(field, ''))
            if expected is not None and totals[field] != expected:
                errors.append('Own published ' + field + ' total differs')
        requested_points = entry.get('additional_global_source', {}).get('documented_event_points', 0)
        if requested_points:
            event, amount = point_missions.get(mid, ({}, None))
            if amount != requested_points or event.get('raid_coin') is not None or not event.get('personal_milestones'):
                errors.append('Own event-point parent/milestones are incomplete')
        route = {'mission': mid, 'source_page': record['page']['title'],
            'source_revision': record['page']['revisions'][0].get('revid'),
            'source_heading': record['heading'], 'native_totals': totals,
            'documented_drop': record['fields'].get('drop', ''),
            'item_totals_per_selected_stage': dict(actual_items),
            'own_actor_slots': len(slots), 'own_drop_carriers': len(bundle.get('y35YvQjZ', [])),
            'documented_event_points': requested_points, 'blockers': list(dict.fromkeys(errors)),
            'bundle_sha256': hashlib.sha256(json.dumps(bundle, sort_keys=True).encode('utf8')).hexdigest()}
        summary['routes'].append(route)
        summary['blockers'].extend(mid + ': ' + error for error in route['blockers'])
    for area, row in areas.items():
        row['route_count'] = len(row['missions'])
        row['status'] = ('source_graph_ready_no_known_core_gap' if not row['blockers']
                         else 'blocked_own_source_dependency')
    report = {'date': '2026-11-11', 'scope': {'areas': 24, 'routes': 181,
        'area_ids': list(areas), 'excluded': 'User excluded all98 unit intros; '
            'three untranslated32200115/116/117 variants remain outside the published archive.'},
        'meaning': 'Static effective native graph and own reward inspection. '
            'This does not claim runtime testing or exact recovery of explicitly '
            'unpublished NPC stats and Break gauge parameters.',
        'sources': ['source/server/content/omitted_global_event_sources.json',
                    'logs/reference/restored-event-rewards-wiki-20261111.json'],
        'areas': list(areas.values()),
        'summary': dict(Counter(r['status'] for r in areas.values()))}
    path = ROOT / 'logs/ffbe-additional-event-source-graph-20261111.json'
    temp = path.with_name(path.name + '.writing')
    temp.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    temp.replace(path)
    return report
