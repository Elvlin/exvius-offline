"""Bind Global event missions to preserved encounters by identity, not ID alone.

Global and Memorial reuse numeric mission IDs. A matching ID is insufficient:
the original mission identity must agree. Unique translated name matches also
recover campaigns whose numeric IDs changed between editions. Global subtypes
and wave counts remain authoritative; adapted wave counts are recorded explicitly.
Unresolved encounters are recorded for source recovery rather than fabricated.
"""
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import re
import sys
import unicodedata
import zipfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'source/server'))
from battle_content import IndexSource, derive_mission, is_menu_resource_row, resolve_pool


def rows(directory, name):
    return [json.loads(line) for line in
            (ROOT / 'data' / directory / (name + '.ndjson')).read_text(encoding='utf-8').splitlines() if line]


def identity(value):
    value = unicodedata.normalize('NFKC', str(value)).casefold()
    return ''.join(char for char in value if char.isalnum() or char == '+')


def main():
    original = {row['qo3PECw6']: row for row in rows('mst_decoded', 'F_MISSION_MST')}
    memorial = {row['qo3PECw6']: row for row in rows('memorial_battle_decoded', 'F_MISSION_MST')}
    english = {row['key'].rsplit('_', 1)[-1]: row['v'][0]
               for row in rows('text_decoded', 'F_TEXT_MISSION')}
    with zipfile.ZipFile(ROOT / 'repository snapshots/aEnigmatic__ffbe-95727376e82d.zip') as archive:
        datamine = json.loads(archive.read(next(name for name in archive.namelist()
                                               if name.endswith('/missions.json'))))
    events = json.loads((ROOT / 'source/server/event_archive.json').read_text(encoding='utf-8'))['events']
    native_source = IndexSource()
    phases = defaultdict(list)
    pools = defaultdict(list)
    groups = defaultdict(list)
    parts = defaultdict(list)
    monsters = {r['xqartN26']: r for r in native_source.load('F_MONSTER_MST')}
    for row in native_source.load('F_MISSION_PHASE_MST'):
        if row.get('gou39JeI') == '2':
            phases[row['qo3PECw6']].append(row)
    for row in native_source.load('F_BATTLE_LOTTERY_MST'):
        pools[row['c2gnh6Jd']].append(row)
    for row in native_source.load('F_BATTLE_GROUP_MST'):
        groups[row['2fY1IomW']].append(row)
    for row in native_source.load('F_MONSTER_PARTS_MST'):
        parts[row['xqartN26']].append(row)
    source_parts = {}

    def encounter_parts(mid, waves):
        cache_key = (mid, waves)
        if cache_key not in source_parts:
            used = set()
            selected = sorted(phases[mid], key=lambda r: int(r['6v7y3QcJ']))[:waves]
            for phase in selected:
                target = phase.get('6uIYE15X', '')
                resolved = resolve_pool(pools[target], target)
                slots = groups[resolved[0]] if resolved else []
                if not slots or any(s['xqartN26'] not in monsters or
                                    not parts[s['xqartN26']] for s in slots):
                    source_parts[cache_key] = None
                    break
                used.update(s['xqartN26'] for s in slots)
            else:
                source_parts[cache_key] = used or None
        return source_parts[cache_key]

    counts = Counter(row['qo3PECw6'] for row in native_source.load('F_MISSION_PHASE_MST')
                     if row.get('gou39JeI') == '2')
    roster_cache = {}

    def roster(mid):
        if mid not in roster_cache:
            try:
                bundle = derive_mission(mid, native_source)
                roster_cache[mid] = tuple(sorted(row['V9j8wJcC'] for row in bundle['wbet57nF']))
            except (SystemExit, Exception):
                roster_cache[mid] = None
        return roster_cache[mid]
    by_name = defaultdict(set)
    for mid, row in memorial.items():
        if counts[mid]:
            by_name[identity(row['G4L0YIB2'])].add(mid)
    mapping, missing, totals = {}, [], Counter()
    resources = {mid: 'exploration' for mid, row in datamine.items()
                 if row.get('type') == 'EXPLORATION' and mid in original}
    for event in events:
        for mid in event['missions']:
            row = original[mid]
            waves = int(row['8xi6Xvyk'])
            if is_menu_resource_row(row):
                totals['original_menu_resource'] += 1
                resources[mid] = 'menu-resource'
                continue
            if resources.get(mid) == 'exploration':
                totals['original_exploration_resource'] += 1
                continue
            if not waves:
                totals['original_story'] += 1
                continue
            names = {identity(row['G4L0YIB2']), identity(english.get(mid, '')),
                     identity(datamine.get(mid, {}).get('name', ''))} - {''}
            same = memorial.get(mid)
            candidates = {candidate for name in names for candidate in by_name[name]
                          if counts[candidate] > 0 and
                          memorial[candidate].get('gQR24kST') == row.get('gQR24kST')}
            if (same and identity(same['G4L0YIB2']) in names and counts[mid] > 0):
                source, basis = mid, 'original_name_and_id'
            elif len(candidates) == 1:
                source, basis = next(iter(candidates)), 'unique_original_name'
            elif candidates and len({roster(candidate) for candidate in candidates}) == 1 and all(roster(candidate) for candidate in candidates):
                # Repeated releases can retain the exact mission name and
                # enemy graphics under new IDs. Use the earliest preserved
                # named counterpart; Global costs, rewards and unlocks stay
                # on the original mission. The tier choice is local policy.
                source, basis = min(candidates, key=int), 'same_roster_named_counterpart'
            elif (row.get('gQR24kST') == '6' and
                  'Equipment Enhancement Event' in english.get(mid, '') and
                  re.search(r'\b(\d+)F\b|Floor\s+(\d+)', english.get(mid, ''))):
                floor_match = re.search(r'\b(\d+)F\b|Floor\s+(\d+)', english[mid])
                floor = int(next(value for value in floor_match.groups() if value))
                source, basis = str(7860100 + floor), 'shared_item_world_floor'
                if floor not in range(1, 11) or counts[source] < 1:
                    source = None
            else:
                source = None
            if source and not encounter_parts(source, waves):
                source = None
            if source:
                if counts[source] != waves:
                    basis += '_local_wave_count'
                mapping[mid] = {'source': source, 'basis': basis, 'waves': waves}
                totals[basis] += 1
            else:
                missing.append({'area': event['area'], 'mission': mid,
                                'name': english.get(mid, row['G4L0YIB2']),
                                'page': event['source_page'], 'waves': waves,
                                'subtype': row.get('gQR24kST'), 'candidates': sorted(candidates)})
    # Memorial has a few JP-only variants. Keep Global model/AI counterparts
    # explicit instead of allowing null native master lookups.
    graphic_aliases = {'2120200': '2120210'}
    ai_aliases = {'205361000': '116', '305921002': '305921000'}
    native_names = {r['key'].removeprefix('MST_MONSTER_NAME_'): r['v'][0]
                    for r in rows('text_decoded', 'F_TEXT_MONSTER_NAME')}
    dictionary_names = {r['key'].rsplit('_', 1)[-1]: r['v'][0]
                        for r in rows('text_decoded', 'F_TEXT_MONSTER_DICTIONARY_NAME')}
    unit_names = {r['key'].rsplit('_', 1)[-1]: r['v'][0]
                  for r in rows('text_decoded', 'F_TEXT_UNITS_NAME')}
    translated_names = {
        '2059031': 'Thug', '3021330': 'Gluttonous Bird',
        '3031000': 'Dark Octopoda', '5110030': '5th Anniversary Super Gigantuar',
        '3055811': 'Hirono K.', '5110031': '5th Anniversary Super Dark Gigantuar',
    }
    english_by_original = defaultdict(set)
    for pid, monster in monsters.items():
        if native_names.get(pid):
            english_by_original[monster['G4L0YIB2']].add(native_names[pid])
    global_ai = {r['8a6gAwN9'] for r in rows('mst_decoded', 'F_AI_MST')}
    global_set_rows = {r['A5x02C6a']: r for r in rows('mst_decoded', 'F_MONSTER_SKILL_SET_MST')}
    global_sets = set(global_set_rows)
    source_sets = {r['A5x02C6a']: r for r in rows('memorial_battle_decoded', 'F_MONSTER_SKILL_SET_MST')}
    parts_by_graphic = defaultdict(list)
    for pid, profile in parts.items():
        parts_by_graphic[monsters[pid]['V9j8wJcC']].extend(profile)
    ai_counterparts = {}
    needed_sets, local_names, missing_names = set(), {}, []
    used_parts = set().union(*(encounter_parts(b['source'], b['waves']) for b in mapping.values()))
    for binding in mapping.values():
        mids = encounter_parts(binding['source'], binding['waves'])
        mon_overrides = {pid: {'V9j8wJcC': graphic_aliases[monsters[pid]['V9j8wJcC']]}
                         for pid in mids if monsters[pid]['V9j8wJcC'] in graphic_aliases}
        part_overrides = {}
        for pid in mids:
            for part in parts[pid]:
                ai = part.get('8a6gAwN9')
                if ai and ai != '0' and ai not in global_ai:
                    same_model = [p for p in parts_by_graphic[monsters[pid]['V9j8wJcC']]
                                  if p.get('8a6gAwN9') in global_ai]
                    counterpart = min(same_model, key=lambda p: (
                        abs(int(p.get('7wV3QZ80') or 1) - int(part.get('7wV3QZ80') or 1)),
                        int(p['xqartN26']))) if same_model else None
                    replacement = ai_aliases.get(ai) or (counterpart['8a6gAwN9'] if counterpart else '116')
                    assert replacement in global_ai
                    part_overrides[pid + ':' + part['6Yc4RkdM']] = {'8a6gAwN9': replacement}
                    ai_counterparts[pid] = {'original_ai': ai, 'global_ai': replacement,
                        'basis': 'Preserved Global same-model AI' if counterpart else 'Local standard attack AI'}
        if mon_overrides:
            binding['monster_overrides'] = mon_overrides
        if part_overrides:
            binding['part_overrides'] = part_overrides
    for pid in sorted(used_parts, key=int):
        graphic = monsters[pid]['V9j8wJcC']
        graphic = graphic_aliases.get(graphic, graphic)
        name = native_names.get(pid) or dictionary_names.get(graphic)
        if not name:
            name = next((native_names[p['xqartN26']] for p in parts_by_graphic[graphic]
                         if native_names.get(p['xqartN26'])), None)
        equivalents = english_by_original[monsters[pid]['G4L0YIB2']]
        if not name and len(equivalents) == 1:
            name = next(iter(equivalents))
        name = name or translated_names.get(graphic)
        if not name:
            name = next((unit_names.get(p.get('3HriTp6B')) for p in parts[pid]
                         if unit_names.get(p.get('3HriTp6B'))), None)
        if not name:
            missing_names.append({'part': pid, 'graphic': graphic,
                                  'original': monsters[pid]['G4L0YIB2']})
            continue
        local_names[pid] = name
        for part in parts[pid]:
            suffix = chr(64 + int(part['6Yc4RkdM']))
            local_names[pid + suffix] = (native_names.get(pid + suffix) or
                                        native_names.get(pid + '_' + suffix) or
                                        (name if suffix == 'A' else name + ' Part ' + part['6Yc4RkdM']))
            set_id = part.get('A5x02C6a')
            if set_id and set_id != '0' and set_id not in global_sets:
                needed_sets.add(set_id)
    if missing_names:
        (ROOT / 'source/build/event-missing-english-names-20261026.json').write_text(
            json.dumps(missing_names, ensure_ascii=False, indent=1), encoding='utf8')
        raise ValueError('Missing English monster identities: ' + str(len(missing_names)) +
                         '; see source/build/event-missing-english-names-20261026.json')
    used_sets = {part['A5x02C6a'] for pid in used_parts for part in parts[pid]
                if part.get('A5x02C6a') not in ('', '0', None)}
    set_overrides = [global_set_rows[sid] for sid in sorted(used_sets & global_sets)
                     if sid not in source_sets or
                     source_sets[sid]['7qxLC5hP'] != global_set_rows[sid]['7qxLC5hP']]
    available_skills = {r['6E5u1xrs'] for r in native_source.load('F_MONSTER_SKILL_MST')}
    incomplete_sets = {sid for sid in used_sets if
                       set(filter(None, (global_set_rows.get(sid) or source_sets[sid])['7qxLC5hP'].split(','))) - available_skills}
    recovered = []
    if incomplete_sets:
        # Reuse the already-proven original Global datamine conversion.
        from reconstruct_event_battles import Reconstruction
        reconstruction = Reconstruction()
        for sid in sorted(incomplete_sets):
            reconstruction.global_sets.setdefault(sid, source_sets[sid])
            reconstruction.recover_skills(sid, only_missing=True)
        recovered = [reconstruction.skill_rows[sid] for sid in sorted(reconstruction.recovered_skills)]
    document = {'version': 1, 'provenance': {
        'global': 'data/mst_decoded/F_MISSION_MST.ndjson',
        'memorial': 'data/memorial_battle_decoded/F_MISSION_MST.ndjson',
        'item_world': 'Original Steel Castle Melfikya floor encounters, shared across campaign dates',
        'global_sha256': hashlib.sha256((ROOT / 'data/mst_decoded/F_MISSION_MST.ndjson').read_bytes()).hexdigest()},
        'global_counterparts': {
            'graphics': graphic_aliases,
            'ai': ai_counterparts,
            'local_english_translations': translated_names,
            'policy': 'Global same-enemy AI where preserved; Dracobaltian uses local standard attack AI 116'},
        'missions': mapping, 'resource_missions': resources,
        'local_monster_names': local_names,
        'native_battle_support': {'F_MONSTER_SKILL_SET_MST': set_overrides,
                                  'F_MONSTER_SKILL_MST': recovered},
        'native_master_additions': {'F_MONSTER_SKILL_SET_MST': [source_sets[i] for i in sorted(needed_sets)]}}
    (ROOT / 'source/server/event_battles.json').write_text(
        json.dumps(document, ensure_ascii=False, separators=(',', ':')) + '\n', encoding='utf-8')
    (ROOT / 'source/build/event-battle-source-gaps-20261026.json').write_text(
        json.dumps(missing, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    print('Event encounter bindings:', dict(totals), '; unresolved:', len(missing))


if __name__ == '__main__':
    main()
