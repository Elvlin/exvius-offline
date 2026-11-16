"""Author own-source combat dependencies for the omitted Global event routes.

Only the explicitly listed restoration scope is written. Existing native
assembly, source profiles, skills and attempt selection remain authoritative.
"""
import copy
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'source/server'), str(ROOT / 'source/exvius')]
CONTENT = ROOT / 'source/server/event_encounters.json'
REPORT = ROOT / 'logs/ffbe-restored-event-effective-dependencies-20261111.json'


def source_reader(document=None):
    from reconstruct_event_battles import Reconstruction, key
    reader = Reconstruction()
    path = ROOT / 'logs/reference/restored-event-rewards-wiki-20261111.json'
    if path.exists():
        for page in json.loads(path.read_text(encoding='utf8'))['query']['pages'].values():
            if page.get('revisions'):
                reader.pages[key(page['title'])] = page
    # The retained, source-pinned Defiance graph contains these exact enemies,
    # their original Global AI and summon variants. Reuse their own profiles.
    existing = document if document is not None else json.loads(CONTENT.read_text(encoding='utf8'))
    donor = existing['missions']['9960101']['bundle']
    by_actor = {}
    for part in donor['bV34YIJQ']:
        by_actor.setdefault(part['xqartN26'], []).append(part)
    for monster in donor['wbet57nF']:
        actor = monster['xqartN26']
        reader.monsters[actor] = copy.deepcopy(monster)
        reader.parts[actor] = copy.deepcopy(by_actor[actor])
        reader.names[actor] = monster['G4L0YIB2']
        for index, value in ((reader.by_name, key(monster['G4L0YIB2'])),
                             (reader.by_graphic, monster['V9j8wJcC'])):
            if actor not in index[value]:
                index[value].append(actor)
    reader.skill_rows.update({row['6E5u1xrs']: copy.deepcopy(row) for row in donor['Wp39QX52']})
    reader.defiance_dependencies = donor
    # The2017 guide supplies new HP/MP/level rows for these same original
    # Pumpkin bosses. Preserve their own earlier model/stat anchors rather
    # than borrowing an unrelated plant monster's profile or loot.
    for mid in ('9000201', '9000202', '9000203', '9000301', '9000302', '9000303'):
        bundle = existing['missions'][mid]['bundle']
        for monster in bundle['wbet57nF']:
            if monster['G4L0YIB2'] not in ('Pumpkin Kid', 'Pumpkin Rider'):
                continue
            actor = monster['xqartN26']
            reader.monsters[actor] = copy.deepcopy(monster)
            reader.parts[actor] = [copy.deepcopy(p) for p in bundle['bV34YIJQ']
                                   if p['xqartN26'] == actor]
            reader.names[actor] = monster['G4L0YIB2']
            if actor not in reader.by_name[key(monster['G4L0YIB2'])]:
                reader.by_name[key(monster['G4L0YIB2'])].append(actor)
            if actor not in reader.by_graphic[monster['V9j8wJcC']]:
                reader.by_graphic[monster['V9j8wJcC']].append(actor)
    # Preserve an already authored exact Darkside model/profile as the numeric
    # anchor; the current CoB page supplies its own100M HP/10K MP separately.
    for monster in existing['missions']['8630101']['bundle']['wbet57nF']:
        if monster['G4L0YIB2'] != 'Darkside':
            continue
        actor = monster['xqartN26']
        reader.monsters[actor] = copy.deepcopy(monster)
        reader.parts[actor] = [copy.deepcopy(p) for p in
            existing['missions']['8630101']['bundle']['bV34YIJQ'] if p['xqartN26'] == actor]
        reader.names[actor] = 'Darkside'
        reader.by_name[key('Darkside')].append(actor)
        reader.by_graphic[monster['V9j8wJcC']].append(actor)
    original = ROOT / 'data/web_sources/global_archive_mst_decoded/F_MONSTER_SKILL_MST.ndjson'
    reader.original_global_skills = {r['6E5u1xrs']: r for r in
        map(json.loads, original.read_text(encoding='utf8').splitlines())}
    return reader


def assemble_owned_stage(reader, mid, mission, record, layouts, sequence, drops=None,
                         ai_by_name=None):
    """Use explicit own rosters and one reward carrier per actual enemy part."""
    from reconstruct_event_battles import key, numeric
    from battle_content import derive_mission
    from restore_event_battles import ReconstructionSource

    if len(layouts) != int(mission['8xi6Xvyk']):
        raise ValueError('Own documented stage wave count differs: ' + mid)
    # A stable isolated range keeps other completed reconstructions untouched.
    actor_base, group_base = 1840000000 + sequence * 100, 1910000000 + sequence * 10
    names = list(dict.fromkeys(foe for wave in layouts for foe in wave))
    prototypes, evidence = {}, []
    reader.counter = 40000000 + sequence * 100
    for title, name in names:
        # Prefer the preserved exact enemy model. New character bosses retain
        # their own original Global dictionary/unit art and original AI below.
        monster, parts, basis = reader.enemy(title, name, record,
            [record['heading']], record['page']['title'], mid)
        if ai_by_name and name in ai_by_name:
            ai = ai_by_name[name]
            if ai not in reader.global_ai:
                raise ValueError('Own original Global enemy AI missing: ' + name)
            for part in parts:
                part['8a6gAwN9'] = ai
                part['A5x02C6a'] = ai if ai in reader.global_sets else '0'
            if ai in reader.global_sets:
                reader.recover_skills(ai, only_missing=True)
            basis['own_original_ai'] = ai
        prototypes[(title, name)] = monster, parts
        evidence.append(basis)
    groups, monsters, parts, phases, lotteries, carriers = [], [], [], [], [], []
    breaks = {}
    count = sum(map(len, layouts))
    exp = numeric(record['fields'].get('unit-exp', ''))
    gil = numeric(record['fields'].get('gil', ''))
    if exp is None or gil is None or not count:
        raise ValueError('Own published EXP/gil totals missing: ' + mid)
    occurrence = 0
    for wave_index, wave in enumerate(layouts, 1):
        gid = str(group_base + wave_index)
        phases.append({'qo3PECw6': mid, '6v7y3QcJ': str(wave_index), 'gou39JeI': '2',
            '6uIYE15X': gid, 'T03qgLWA': '1', 'i2ar9yXM': '0', '5LZN8C9I': '0',
            'YS9kfCX7': mission.get('6w4xiIsS', '400005'),
            'DYTx1Is3': mission.get('DYTx1Is3', '100741'), 'V2mCH5UR': ''})
        lotteries.append({'c2gnh6Jd': gid, '2fY1IomW': gid, 'ixDq7yJ8': '1'})
        for slot_index, foe in enumerate(wave, 1):
            source_monster, source_parts = prototypes[foe]
            actor = str(actor_base + occurrence + 1)
            monster = copy.deepcopy(source_monster)
            monster.update(xqartN26=actor, G4L0YIB2=foe[1])
            monsters.append(monster)
            groups.append({'2fY1IomW': gid, 'xqartN26': actor,
                'Z0EN6jSh': str(slot_index), 'MxLFKZ13': str(180 if slot_index % 2 else 100)
                    + ',' + str(210 + slot_index * 65),
                '3t7pZM5V': '0', 'WJdBp9f0': '1', 'm9BvFk2X': '1'})
            for original in source_parts:
                part = copy.deepcopy(original)
                part.update(xqartN26=actor, G4L0YIB2=foe[1])
                body = part['6Yc4RkdM'] == '1'
                part['B6H34Mea'] = str(exp // count + (occurrence < exp % count)) if body else '0'
                part['7UR4J2SE'] = str(gil // count + (occurrence < gil % count)) if body else '0'
                if body and record.get('own_break'):
                    part['e56NZY42'] = actor
                    breaks[actor] = copy.deepcopy(record['own_break'])
                    if breaks[actor].get('broken') is None:
                        breaks[actor]['broken'] = {name: int(part[token]) for name, token in
                            zip(('atk', 'def', 'mag', 'spr'),
                                ('9NBV1XCS', 'Pn5w9dfh', '84FJM3PD', 'T8xMDAZ4'))}
                for channel in ('9BetM2Ds', 'MZn8LC6H', 'g4voc2Aw', 'Vf5DGw07'):
                    part[channel] = ''
                parts.append(part)
                reward = {'qo3PECw6': mid, '6v7y3QcJ': str(wave_index), 'pIHCrf40': '1',
                    '2fY1IomW': gid, 'xqartN26': actor, 'Z0EN6jSh': str(slot_index),
                    '6Yc4RkdM': part['6Yc4RkdM'], '9BetM2Ds': '', 'MZn8LC6H': '',
                    'g4voc2Aw': '', 'Vf5DGw07': '', '3frn4ILX': '', 'IRf10dwx': '',
                    'ATM35pjf': '', 'e5xoiC84': ''}
                if body and drops:
                    reward.update(copy.deepcopy(drops.get((wave_index, slot_index), {})))
                carriers.append(reward)
            occurrence += 1
    tables = {'F_MISSION_PHASE_MST': phases, 'F_BATTLE_LOTTERY_MST': lotteries,
              'F_BATTLE_GROUP_MST': groups, 'F_MONSTER_MST': monsters,
              'F_MONSTER_PARTS_MST': parts,
              'F_MONSTER_SKILL_SET_MST': list(reader.global_sets.values()),
              'F_MONSTER_SKILL_MST': list(reader.skill_rows.values())}
    bundle = derive_mission(int(mid), ReconstructionSource(reader.base, tables),
                            break_status=breaks if breaks else None)
    bundle['Wp39QX52'] = [copy.deepcopy(reader.original_global_skills.get(row['6E5u1xrs'], row))
                         for row in bundle['Wp39QX52']]
    bundle['y35YvQjZ'] = carriers
    bundle['1IfDqR4n'] = [copy.deepcopy(mission)]
    entry = {'bundle': bundle, 'source_page': record['page']['title'],
        'source_revision': record['page']['revisions'][0].get('revid'),
        'identity_source': 'Own primary stage roster and user-approved documented reconstruction',
        'enemies': evidence,
        'omitted_global_combat_source': {
            'heading': record['heading'], 'battle_fields': copy.deepcopy(record['fields']),
            'formations': [[foe[1] for foe in wave] for wave in layouts],
            'unit_exp': exp, 'gil': gil,
            'reward_ownership': 'Only the listed native enemy/part carriers earn their '
                'stage rewards. Original first-clear/challenge rewards remain separate.',
            'reconstructed': 'Server formations and coordinates are not retained. '
                'Explicit own documented enemy counts and wave order are used where '
                'published; otherwise each named regular species occurs in a balanced '
                'own-stage layout. Published battle EXP/gil totals are allocated across '
                'the actual own actors, with integer remainder on the first actors. '
                'Unpublished stats/presentation use the retained same-enemy model or '
                'original Global dictionary/unit art with separately recorded profile '
                'reconstruction. No donor item pool is inherited.'}}
    if record.get('own_break'):
        entry['omitted_global_combat_source']['own_break'] = copy.deepcopy(record['own_break'])
    labels = {monster['xqartN26']: monster['G4L0YIB2'] for monster in monsters}
    labels.update({part['xqartN26'] + chr(64 + int(part['6Yc4RkdM'])): part['G4L0YIB2']
                   for part in parts})
    return entry, labels


def own_published_profiles(reader, record, contract, bosses):
    """Separate explicitly published Base/Broken forms before applying stats."""
    from reconstruct_event_battles import fields, key, numeric
    from build_raid_archive import templates
    text = reader.text(record['page'])
    boxes = []
    for offset, block in templates(text, 'Boss Infobox'):
        spec = fields(block)
        tabs = re.findall(r'(?:<tabber>|\|-\|)\s*([^=\n]+)=', text[:offset])
        boxes.append((tabs[-1].strip() if tabs else '', spec))
    advanced = bool(re.search(r'\bADV\s*$', contract['source_heading']))
    profiles = {}
    for title, name in bosses:
        candidates = [(variant, spec) for variant, spec in boxes if key(spec.get('name', '')) == key(name)]
        bases = [spec for variant, spec in candidates if variant.casefold() == 'base']
        if advanced and len(bases) == 1:
            profiles[key(name)] = bases[0]
        elif len(candidates) == 1:
            profiles[key(name)] = candidates[0][1]
    if profiles:
        record['season_scoped'] = True
        record['published_profiles'] = profiles
    base_forms = [spec for variant, spec in boxes if variant.casefold() == 'base']
    broken_forms = [spec for variant, spec in boxes if variant.casefold() == 'broken']
    gauge = re.search(r'! Break HP !! Duration\s*\|-\s*\| ([\d,]+)<br>\(\+0 after first Break\) \|\| (\d+) turns', text)
    if advanced and gauge and len(base_forms) == len(broken_forms) == 1:
        weapon_order = ('Dagger', 'Sword', 'Great Sword', 'Katana', 'Staff', 'Rod',
                        'Bow', 'Axe', 'Hammer', 'Spear', 'Instrument', 'Whip',
                        'Throwing', 'Gun', 'Mace', 'Fist')
        damage = {}
        start = text.find('! Weapons !! Break Damage')
        table = text[start:text.find('|}', start)]
        for weapons, value in re.findall(r'\|\s*((?:\{\{Equip\|.*?)+?)\s*\|\|\s*(\d+)\s*(?=\n)', table, re.S):
            for weapon in re.findall(r'\{\{Equip\|([^}]+)\}\}', weapons):
                damage[weapon] = int(value)
        if set(damage) != set(weapon_order):
            raise ValueError('Own original Break weapon table is incomplete')
        broken = {stat: numeric(broken_forms[0][stat]) for stat in ('atk', 'def', 'mag', 'spr')}
        if any(value is None for value in broken.values()):
            raise ValueError('Own original broken-form statistics are incomplete')
        record['own_break'] = {'break_hp': int(gauge[1].replace(',', '')),
            'break_hp_after_first': int(gauge[1].replace(',', '')), 'turns': int(gauge[2]),
            'broken': broken,
            'RHe5r72C': ','.join(str(10000 // damage[w]) for w in weapon_order),
            'EwZ40mt3': ','.join('1' if damage[w] == max(damage.values()) else '0' for w in weapon_order),
            'source': contract['source_page'],
            'source_note': 'Own original3000HP, no increase,3turns, exact Base/Broken '
                           'stats and weapon damage table. Relationship fields use '
                           'the existing native inverse damage representation.'}
    elif advanced and record['page']['title'] == 'Let Your Heart Be the Guiding Key':
        # This guide explicitly leaves the gauge HP and strong-weapon value
        # unknown. Preserve its documented mechanic and light/dark change,
        # recording the same-era3000HP gauge as an approved reconstruction.
        order = ('Dagger', 'Sword', 'Great Sword', 'Katana', 'Staff', 'Rod', 'Bow',
                 'Axe', 'Hammer', 'Spear', 'Instrument', 'Whip', 'Throwing', 'Gun', 'Mace', 'Fist')
        strong = {'Dagger', 'Sword', 'Great Sword'}
        record['own_break'] = {'break_hp': 3000, 'break_hp_after_first': 3000,
            'turns': 3, 'broken': None,
            'resists': {'hn42BL3Q': '99,99,99,99,99,99,-50,-50,0'},
            'RHe5r72C': ','.join('100' if w in strong else '2000' for w in order),
            'EwZ40mt3': ','.join('1' if w in strong else '0' for w in order),
            'source': contract['source_page'],
            'reconstructed': 'Own guide gives3turns and the specific strong weapons '
                'but leaves gauge HP, post-break growth and strong-weapon damage '
                'uncertain.3000HP/no growth uses retained same-era Elena/Itachi '
                'CoB gauge contracts; strong100/other5 follows the own guide '
                'weapon grouping. These are explicit local values, not recovered '
                'retail percentages. Unpublished combat statistics retain the '
                'same Darkside profile in both forms; documented light/dark '
                'resistance changes from+60 to-50 are applied exactly.'}


def simple_native_stages(reader):
    """Own dated Craft quests and three explicit three-Dive-Talon Aerith quests."""
    from build_event_archive import rows
    missions = {r['qo3PECw6']: r for r in rows('F_MISSION_MST')}
    records = reader.records('Fundamental Forces: Researcher Arc/Craft Material Quest')
    output, labels = {}, {}
    for day in range(1, 15):
        mid = str(10740100 + day)
        matches = [record for record in records
                   if day in [int(v) for v in re.findall(r'\d+', record['heading'])]]
        if len(matches) != 1:
            raise ValueError('Own dated Craft quest source is ambiguous: ' + mid)
        record = matches[0]
        layouts = [[('Desert Baretta', 'Desert Baretta'), ('Red Claw', 'Red Claw')]]
        entry, names = assemble_owned_stage(reader, mid, missions[mid], record, layouts, day)
        entry['omitted_global_combat_source']['reconstructed_roster_count'] = (
            'The own stage names both species without individual counts; one of each '
            'is an explicit local formation, not a recovered original server row.')
        output[mid] = entry
        labels.update(names)
    records = reader.records('Cetra Descendant Aerith Enhancement Quests')
    for number in range(1, 4):
        mid = str(10750100 + number)
        record = next(record for record in records if record['heading'] == 'Quest ' + str(number))
        if record['fields']['monster'] != '[[Dive Talon]] (3)':
            raise ValueError('Original Aerith three-bird roster changed')
        entry, names = assemble_owned_stage(reader, mid, missions[mid], record,
            [[('Dive Talon', 'Dive Talon')] * 3], 20 + number)
        output[mid] = entry
        labels.update(names)
    return output, labels


def own_item_drops(text):
    """Resolve only this stage's named items and explicit amount ranges."""
    import itertools
    from build_event_archive import rows
    names = {r['v'][0]: r['key'].rsplit('_', 1)[-1]
             for r in rows('F_TEXT_ITEM_NAME', text=True)}
    items = {r['tL6G9egd'] for r in rows('F_ITEM_MST')}
    if not text.strip():
        return {}, []
    choices, notes = [], []
    patterns = r'\{\{Item\|([^}|]+)(?:\|([^}]+))?\}\}|\[\[([^]|]+)(?:\|[^]]+)?\]\](?:\s*\((\d+)\))?'
    for match in re.finditer(patterns, text):
        name = match[1] or match[3]
        quantity = match[2] or match[4]
        if name not in names or names[name] not in items:
            raise ValueError('Own documented drop has no original item identity: ' + name)
        if quantity is None:
            quantity = '1'
            notes.append('The source names ' + name + ' without a count/rate. '
                'One selected item is a local minimum-quantity reconstruction, '
                'not a recovered historical percentage.')
        if re.fullmatch(r'\d+', quantity):
            amounts = [int(quantity)]
        elif re.fullmatch(r'\d+-\d+', quantity):
            lower, upper = map(int, quantity.split('-'))
            amounts = list(range(lower, upper + 1))
            notes.append('Own published ' + name + ' range' + quantity + ' retained. '
                'Equal amount weights are reconstructed; retail distribution is unpreserved.')
        else:
            raise ValueError('Unresolved own stage drop quantity: ' + quantity)
        choices.append(['20:' + names[name] + ':' + str(amount) + ':100' for amount in amounts])
    remainder = re.sub(patterns, '', text)
    if re.sub(r'<br\s*/?>|[\s,]', '', remainder, flags=re.I) or not choices:
        raise ValueError('Own stage drop syntax requires explicit handling: ' + text)
    possibilities = [','.join(values) for values in itertools.product(*choices)]
    if len(possibilities) == 1:
        return {'9BetM2Ds': possibilities[0]}, notes
    return {'_drop_choices': [{'weight': 1, 'drop': value} for value in possibilities]}, notes


def published_combat_stages(reader, areas=None):
    """Build only each retained primary contract's own combat stage."""
    from build_event_archive import rows
    from reconstruct_event_battles import key, linked_enemies
    from urllib.parse import unquote
    definitions = json.loads((ROOT / 'source/server/content/omitted_global_event_sources.json')
                             .read_text(encoding='utf8'))['events']
    missions = {r['qo3PECw6']: r for r in rows('F_MISSION_MST')}
    all_areas = ('908', '919', '940', '958', '997', '998', '999', '1032', '1035',
                 '1078', '1079', '1080', '3204', '3253')
    ordered = [contract['mission'] for aid in all_areas
               for contract in definitions[aid]['published_stage_contracts']]
    sequence_ids = {mid: 101 + index for index, mid in enumerate(ordered)}
    target_areas = [aid for aid in all_areas if areas is None or aid in areas]
    output, labels, missing = {}, {}, []
    for aid in target_areas:
        for contract in definitions[aid]['published_stage_contracts']:
            mid = contract['mission']
            sequence = sequence_ids[mid]
            title = unquote(contract['source_page'].split('/wiki/')[-1]).replace('_', ' ')
            page = reader.page(title)
            if page is None:
                # The original Lunar New Year cache stores its raw page text.
                raw = json.loads((ROOT / 'logs/reference/field-scenario-wiki-20261109.json')
                                  .read_text(encoding='utf8'))['pages'].get(title)
                if raw is not None:
                    page = {'title': title, 'revisions': [{'revid': contract['source_revision'],
                            'slots': {'main': {'*': raw}}}]}
            if page is None:
                raise ValueError('Own primary stage page is not retained: ' + title)
            record = {'heading': contract['source_heading'], 'page': page,
                      'fields': {k: v for k, v in contract.items()
                                 if k not in ('mission', 'source_page', 'source_revision', 'source_heading')}}
            full = [r for r in reader.records(title) if r['heading'] == contract['source_heading']
                    and r['fields'].get('boss', '') == contract.get('boss', '')]
            if len(full) == 1:
                record['fields'] = dict(full[0]['fields'], **record['fields'])
            ordinary = linked_enemies(contract.get('monster', ''))
            bosses = linked_enemies(contract.get('boss', ''))
            waves = int(contract['battle'])
            if aid == '999':
                layouts = [[('Essence of Despair', 'Essence of Despair')],
                           [('Maw of Malice', 'Maw of Malice')],
                           [('Blue Wisp', 'Blue Sigil'), ('Red Wisp', 'Red Sigil'),
                            ('Tel-Fulsanis', 'Tel-Fulsanis')]]
            elif bosses:
                if waves != 1:
                    layouts = [[ordinary[(i - 1) % len(ordinary)]] for i in range(1, waves)] + [bosses]
                else:
                    layouts = [bosses]
            else:
                raise ValueError('Own stage needs a bounded documented formation: ' + mid)
            own_published_profiles(reader, record, contract, bosses)
            if aid == '919':
                # Ordinary2017 stat rows are partly absent. Use the own tier's
                # published boss level as a bounded same-species profile anchor,
                # rather than choosing a level1 tutorial monster by default.
                record['original_difficulty'] = {'9190001': 10, '9190002': 20, '9190003': 60}[mid]
            if aid in ('1078', '1079', '1080'):
                # No2021 event-specific numeric profile survives in its own
                # guide. Retain the same Esper's level99 native profile rather
                # than selecting its unrelated level1 tutorial version.
                record['original_difficulty'] = 99
            if aid in ('997', '998', '999'):
                # Exact own boss profiles, resistances, HP locks, skills and
                # original AI were preserved in the original9960101 datamine.
                record['profile_overrides'] = copy.deepcopy(reader.source_profiles['9960101'])
            ai = {}
            for _, name in ordinary + bosses:
                matches = [actor for actor, label in reader.names.items()
                           if label == name and actor in reader.global_ai]
                if len(matches) == 1:
                    ai[name] = matches[0]
            if aid == '1035':
                ai['Itachi'] = '900010868' if mid.endswith('01') else '900010869'
            if aid == '1032' and mid.startswith('103201'):
                ai['Starlight Elena'] = '900010859' if mid.endswith('01') else '900010862'
            if aid == '3204':
                ai['Darkside'] = '408041001'
            if aid == '3253':
                ai['Scar'] = '305971000'
            try:
                raid = aid in ('940', '958')
                selected, notes = ({}, []) if raid else own_item_drops(contract.get('drop', ''))
                drops = {(waves, len(layouts[-1])): selected} if selected else None
                entry, names = assemble_owned_stage(reader, mid, missions[mid], record,
                    layouts, sequence, drops, ai)
                entry['omitted_global_combat_source']['drop_limits'] = notes
                entry['omitted_global_combat_source']['primary_contract'] = copy.deepcopy(contract)
                if aid in ('1078', '1079', '1080'):
                    entry['omitted_global_combat_source']['esper_stat_limit'] = (
                        'Own2021 guide supplies the exact named Esper and repeat '
                        'drops but no event-specific combat stats. The preserved '
                        'same-Esper level99 native profile is an explicit playable '
                        'reconstruction, not a claim of recovered2021 tier stats.')
                if raid:
                    entry['omitted_global_combat_source']['raid_reward_owner'] = (
                        'Native raid result settlement owns the documented capped raid '
                        'points/coins and damage/bonus calculation. No duplicate enemy '
                        'item coin grant is authored here.')
                if aid in ('997', '998', '999'):
                    for tag in ('wbet57nF', 'bV34YIJQ', 'Wp39QX52'):
                        present = {r['6E5u1xrs'] if tag == 'Wp39QX52' else
                                   (r['xqartN26'], r.get('6Yc4RkdM'))
                                   for r in entry['bundle'][tag]}
                        for row in reader.defiance_dependencies[tag]:
                            identity = row['6E5u1xrs'] if tag == 'Wp39QX52' else \
                                       (row['xqartN26'], row.get('6Yc4RkdM'))
                            if identity not in present:
                                copied = copy.deepcopy(row)
                                if tag == 'bV34YIJQ':
                                    copied['B6H34Mea'], copied['7UR4J2SE'] = '0', '0'
                                entry['bundle'][tag].append(copied)
                    entry['omitted_global_combat_source']['defiance_profile_limit'] = (
                        'Own original9960101 datamine profiles/AI are retained for the '
                        'same named bosses and every required summon variant. Missing '
                        'edition-specific numeric changes are not claimed as recovered. '
                        'Only actual stage actors carry the published run EXP/gil; '
                        'dependency-only summon profiles do not add a second payout.')
                if aid == '999':
                    # Sigils remain alive when Tel-Fulsanis ends the battle.
                    # Give the three defeated bosses the published total;
                    # making the unkillable adds own a share loses rewards.
                    actors = {row['xqartN26']: row['G4L0YIB2']
                              for row in entry['bundle']['wbet57nF']}
                    active = {row['xqartN26'] for row in entry['bundle']['Bi6hVv34']}
                    totals = {'Essence of Despair': (2000, 500),
                              'Maw of Malice': (2000, 500),
                              'Tel-Fulsanis': (10000, 25000),
                              'Blue Sigil': (0, 0), 'Red Sigil': (0, 0)}
                    for part in entry['bundle']['bV34YIJQ']:
                        if part['xqartN26'] in active:
                            exp, gil = totals[actors[part['xqartN26']]]
                            part['B6H34Mea'], part['7UR4J2SE'] = str(exp), str(gil)
                    entry['omitted_global_combat_source']['reward_allocation'] = (
                        'The original Essence/Maw monster pages publish2000EXP/500gil '
                        'each. Whole-run14000EXP/26000gil leaves10000EXP/25000gil '
                        'for Tel-Fulsanis. This residual allocation is explicit '
                        'reconstruction; unkillable active sigils and all summon '
                        'variants own0EXP/0gil, so surviving adds do not remove '
                        'part of the published clear payout.')
                output[mid] = entry
                labels.update(names)
            except (ValueError, SystemExit) as error:
                missing.append({'area': aid, 'mission': mid, 'reason': str(error)})
    return output, labels, missing


def nyc_entries(document):
    """Use the NYC guide's own two waves and reward totals, not Vault gil."""
    from repair_global_vault_encounters import build, load_contract
    from reconstruct_event_battles import Reconstruction, fields
    from build_raid_archive import templates
    from build_event_archive import rows

    reader = Reconstruction()
    page = reader.page('NYC Livestream Lapis Giveaway')
    text = reader.text(page)
    expected_drop = ('Random Pot<br>2 Random Colored Megacite<br>2 [[Gallean Tins]]'
                     '<br>[[King Gil Snapper]]<br>[[King Metal Minituar]]')
    stages = [fields(block) for _, block in templates(text, 'Battle Infobox')]
    if not stages or any((s.get('battle'), s.get('gil'), s.get('unit-exp'), s.get('drop')) !=
                         ('2', '124', '140', expected_drop) for s in stages):
        raise ValueError('Original NYC giveaway battle reward evidence changed')
    contract = copy.deepcopy(load_contract())
    contract['documented'] = {
        'campaign': page['title'], 'waves': 2, 'unit_exp': 140, 'gil': 124,
        'roster': 'One random normal stat Pot, then King Gil Snapper and King Metal Minituar.',
        'drops': expected_drop,
        'clear_rewards': 'Giveaway ticket clear bonuses remain on the first-clear path.'}
    contract['reconstructed'] = {
        'formation': 'Own two-wave roster with original same-enemy native profiles and unit captures.',
        'weights': 'Equal six-Pot and eight-colour weights are explicit local distributions. '
                   'Original retail probabilities are not retained.',
        'experience': 'Pot50 plus KGS20 plus KMM70 reproduces the documented140 EXP.',
        'gil': 'Own KGS104 plus KMM20 reproduces the documented124 gil. The original '
               'mission header100 is retained and is not granted a second time.',
        'loot_ownership': 'Each phase2 enemy owns one Tin and one random-colour Megacite, '
                          'and its own native unit capture. The Pot owns its own capture. '
                          'Selected colours/roster persist through the existing attempt mechanism.'}
    for actor in contract['actors']:
        if actor['name'] == 'King Gil Snapper':
            actor['served_gil'] = 104
    missions = {r['qo3PECw6']: r for r in rows('F_MISSION_MST')}
    source = {'page': page['title'], 'revision': page['revisions'][0]['revid'],
              'source_file': 'logs/reference/event-battles-wiki-20261026.json',
              'url': 'https://exvius.fandom.com/wiki/NYC_Livestream_Lapis_Giveaway',
              'page_sha256': hashlib.sha256(text.encode('utf8')).hexdigest()}
    contract['missions'] = {}
    for mid in ('9900101', '9900102', '9900103', '9900104', '9900105'):
        mission = missions[mid]
        header = {key: mission[key] for key in ('8xi6Xvyk', '7UR4J2SE', 'B6H34Mea', 'C2Hani5g')}
        if header != {'8xi6Xvyk': '2', '7UR4J2SE': '100', 'B6H34Mea': '100', 'C2Hani5g': '0'}:
            raise ValueError('Original NYC mission header changed: ' + mid)
        contract['missions'][mid] = {
            'mission': mid, 'matching_method': 'own_NYC_campaign_and_identical_documented_stage_reward_contract',
            'original_challenge_rewards': [], 'documented_drop_text': expected_drop,
            'source_records': [copy.deepcopy(source)], 'original_mission_header': header}
    return build(document=document, contract=contract)


def write_entries(entries, labels):
    document = json.loads(CONTENT.read_text(encoding='utf8'))
    document['missions'].update(entries)
    document.setdefault('local_monster_names', {}).update(labels)
    pending = ROOT / 'build/scratch/omitted-event-combat-write.json'
    pending.parent.mkdir(parents=True, exist_ok=True)
    try:
        with pending.open('w', encoding='utf8') as stream:
            json.dump(document, stream, ensure_ascii=False, separators=(',', ':'))
            stream.write('\n')
        pending.replace(CONTENT)
    finally:
        pending.unlink(missing_ok=True)
    from build_turn_challenge_bindings import build as build_turn_bindings, write as write_turn_bindings
    write_turn_bindings(build_turn_bindings(document))


def mark_source_ready(area, missions, evidence):
    report = json.loads(REPORT.read_text(encoding='utf8'))
    row = next(r for r in report['areas'] if r['area'] == area)
    if set(row['missions']) != set(missions):
        raise ValueError('Partial campaign repair must not release the whole area: ' + area)
    row['previous_dependency_blockers'] = row.get('previous_dependency_blockers', row['blockers'])
    row['blockers'] = []
    row['status'] = 'source_graph_ready_no_known_core_gap'
    row['source_repair'] = evidence
    summary = report['summary']
    summary['ready_areas'] = [r['area'] for r in report['areas']
                              if r['status'] == 'source_graph_ready_no_known_core_gap']
    summary['withhold_areas'] = [r['area'] for r in report['areas']
                                 if r['status'] != 'source_graph_ready_no_known_core_gap']
    summary['unresolved_combat_routes'] = sum(sum('mission' in p for p in r['blockers'])
                                               for r in report['areas'])
    pending = REPORT.with_name(REPORT.name + '.pending')
    try:
        pending.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
        pending.replace(REPORT)
    finally:
        pending.unlink(missing_ok=True)


def build(document=None):
    """Return this explicit campaign scope without writing or changing menus."""
    document = document if document is not None else json.loads(CONTENT.read_text(encoding='utf8'))
    entries, labels = nyc_entries(document)
    reader = source_reader(document)
    simple, simple_labels = simple_native_stages(reader)
    published, published_labels, missing = published_combat_stages(reader)
    if missing:
        raise ValueError('Own primary combat source authoring incomplete: ' + json.dumps(missing))
    entries.update(simple)
    entries.update(published)
    labels.update(simple_labels)
    labels.update(published_labels)
    return entries, labels


def main():
    entries, labels = build()
    published = {mid: entry for mid, entry in entries.items()
                 if mid.startswith(('94001', '95801'))}
    write_entries(entries, labels)
    mark_source_ready('990', [mid for mid in entries if mid.startswith('99001')], {
        'author': 'source/exvius/repair_omitted_global_combat.py::nyc_entries',
        'source': 'NYC Livestream Lapis Giveaway revision285880',
        'restored': 'Own two waves, random normal Pot and native unit, KGS and KMM '
                    'own unit captures, two Tins, two random-colour Megacites, '
                    '140 EXP and124 gil. Original clear rewards remain separate.',
        'reconstruction': 'Stage-owned formations and equal Pot/colour weights. '
                          'Existing native attempt selection persists the actual roster and colours.',
        'runtime_validation': 'Not run. Source/data authoring only.'})
    for aid in ('908', '919', '997', '998', '999', '1032', '1035', '1074', '1075',
                '1078', '1079', '1080', '3204', '3253'):
        definition = json.loads((ROOT / 'source/server/content/omitted_global_event_sources.json')
                                 .read_text(encoding='utf8'))['events'][aid]
        mids = [contract['mission'] for contract in definition['published_stage_contracts']]
        mark_source_ready(aid, mids, {
            'author': 'source/exvius/repair_omitted_global_combat.py',
            'primary_sources': sorted({contract['source_page'] for contract in
                                      definition['published_stage_contracts']}),
            'restored': 'Each own published stage roster, explicit waves, per-enemy '
                'item/unit reward carriers, complete profiles/AI/skills and published '
                'whole-battle EXP/gil. Own clear/challenge rewards remain separate.',
            'numeric_limits': 'Unpublished numeric profiles, server formations and '
                'drop distributions retain the explicit per-entry reconstruction '
                'notes. Esper event stats are reconstructed from the same Esper '
                'level99 native profile. Darkside Break HP/weights are documented '
                'local reconstructions; Elena/Itachi Base/Broken fields are sourced.',
            'runtime_validation': 'Not run. Source/data authoring only.'})
    raids = json.loads((ROOT / 'source/server/raid_archive.json').read_text(encoding='utf8'))['events']
    ready_raids = set()
    for aid in ('940', '958'):
        raid = next((row for row in raids if str(row['event_id']) == aid), None)
        mids = [mid for mid in published if mid.startswith(aid + '01')]
        if (raid and raid.get('raid_coin') and raid.get('personal_milestones')
                and set(mids) <= set(raid.get('mission_points', {}))):
            mark_source_ready(aid, mids, {
                'author': 'source/exvius/repair_omitted_global_combat.py and '
                          'source/exvius/restore_omitted_global_raids.py',
                'restored': 'Own four-tier Incarnation of Hatred HP/MP/level, '
                    'EXP/gil, original named boss AI/skills and native raid '
                    'coin/point/milestone settlement. Own summon pool/link '
                    'restored by the raid metadata author.',
                'runtime_validation': 'Not run. Source/data only.'})
            ready_raids.add(aid)
    report = json.loads(REPORT.read_text(encoding='utf8'))
    for aid in ('940', '958'):
        if aid in ready_raids:
            continue
        row = next(r for r in report['areas'] if r['area'] == aid)
        row['previous_dependency_blockers'] = row.get('previous_dependency_blockers', row['blockers'])
        row['blockers'] = [{'kind': 'raid_metadata_settlement_pending',
            'missions': row['missions'],
            'combat_source_ready': True,
            'reason': 'All own four-tier Incarnation of Hatred combat profiles and '
                'source EXP/gil are authored. Native raid archive coin/point metadata '
                'must be supplied by the separate category/raid restoration lane. '
                'No duplicate direct enemy coin drop is authored.'}]
    report['summary']['unresolved_combat_routes'] = sum(sum('mission' in p for p in r['blockers'])
                                                       for r in report['areas'])
    pending = REPORT.with_name(REPORT.name + '.pending')
    try:
        pending.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
        pending.replace(REPORT)
    finally:
        pending.unlink(missing_ok=True)
    print('CHECKPOINT authored own documented combat stages', len(entries))


if __name__ == '__main__':
    main()
