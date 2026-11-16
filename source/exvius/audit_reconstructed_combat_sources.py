"""Inspect every authored/reconstructed combat row against retained own sources.

This is source authoring inspection, not a runtime test. It records unresolved
fields instead of equating a model match or an ID match with original stats.
"""
from collections import Counter, defaultdict
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'source/exvius'), str(ROOT / 'source/server')]
from build_event_archive import rows
from reconstruct_event_battles import Reconstruction, key, fields, templates, numeric, linked_enemies

EXCLUDED_AREAS = {'756', '965', '976', '1089', '1090'}
STATS = {'level': '7wV3QZ80', 'hp': 'fh31sk7B', 'mp': 'PC97pWQj',
         'atk': '9NBV1XCS', 'def': 'Pn5w9dfh', 'mag': '84FJM3PD', 'spr': 'T8xMDAZ4'}


def read(path):
    return json.loads((ROOT / path).read_text(encoding='utf-8'))


def base_stat(value):
    direct = numeric(value)
    if direct is not None:
        return direct
    split = re.fullmatch(r'\s*([\d,]+)\s*\+\s*([\d,]+)\s*', value)
    return int(split[1].replace(',', '')) if split else None


def inspect():
    document = read('source/server/event_encounters.json')
    responses = read('source/server/responses.json')
    bindings = read('source/server/event_battles.json').get('missions', {})
    missions = {r['qo3PECw6']: r for r in rows('F_MISSION_MST')}
    dungeon_areas = {r['U9iHsau3']: r['uv60hgDW'] for r in rows('F_DUNGEON_MST')}
    translated = {r['key'].rsplit('_', 1)[-1]: r['v'][0] for r in rows('F_TEXT_MISSION', True)}
    reader = Reconstruction()
    extra = read('logs/reference/restored-event-rewards-wiki-20261111.json')
    for page in extra['query']['pages'].values():
        if page.get('revisions'):
            reader.pages[key(page['title'])] = page
    for redirect in extra['query'].get('redirects', []):
        reader.redirects[key(redirect['from'])] = key(redirect['to'])
    result, corrections, excluded = [], {}, []
    for mid, entry in document['missions'].items():
        mission = missions.get(mid, {})
        name = translated.get(mid) or mission.get('G4L0YIB2', '')
        area = dungeon_areas.get(mission.get('U9iHsau3'))
        if area in EXCLUDED_AREAS or re.search(r'unit intro', name, re.I):
            excluded.append(mid)
            continue
        authored = responses.get('jnw49dUq@' + mid)
        effective = authored if isinstance(authored, dict) else entry['bundle']
        profiles = effective.get('bV34YIJQ', [])
        actor_names = {r['xqartN26']: r['G4L0YIB2'] for r in effective.get('wbet57nF', [])}
        declared = {a.get('enemy'): a for a in entry.get('enemies', []) if isinstance(a, dict)}
        page = reader.page(entry.get('source_page', ''))
        specs = defaultdict(list)
        single_own_battle = None
        documented_count_differences = []
        if page:
            slot = page['revisions'][0].get('slots', {}).get('main', {})
            text = re.sub(r'<!--.*?-->', '', slot.get('*', slot.get('content', '')), flags=re.S)
            battle_specs = [fields(block) for _, block in templates(text, 'Battle Infobox')]
            stage_contract = tuple(numeric(mission.get(token, '')) for token in ('B6kyCQ9M', '8xi6Xvyk', 'B6H34Mea'))
            exact = [spec for spec in battle_specs if tuple(numeric(spec.get(token, ''))
                                                           for token in ('energy', 'battle', 'rank-exp')) == stage_contract]
            if len(battle_specs) == len(exact) == 1 and all(value is not None for value in stage_contract):
                single_own_battle = exact[0]
            if len(exact) == 1 and stage_contract[1] == 1:
                # Only explicit quantities establish the whole one-wave boss
                # count; a mere bestiary list is not a formation contract.
                expected = Counter(key(name) for _, name in linked_enemies(exact[0].get('boss', '')))
                actual = Counter(key(actor_names.get(r['xqartN26'], '')) for r in effective.get('Bi6hVv34', [])
                                 if r.get('WJdBp9f0') == '1')
                documented_count_differences = [{'actor': actor, 'published': count, 'effective': actual[actor]}
                                                for actor, count in expected.items() if count > 1 and count != actual[actor]]
            for pos, block in templates(text, 'Boss Infobox'):
                spec = fields(block)
                tabs = re.findall(r'(?:<tabber>|\|-\|)\s*([^=\n]+)=', text[:pos])
                spec['_variant'] = tabs[-1].strip() if tabs else ''
                specs[key(spec.get('name', ''))].append(spec)
        rows_out, changes = [], []
        for part in profiles:
            actor = actor_names.get(part['xqartN26'], part.get('G4L0YIB2', ''))
            evidence = declared.get(actor, {})
            original = evidence.get('original_datamine')
            spec, basis = {}, None
            if original and str(original.get('part_id')) == part['xqartN26']:
                # The original source record explicitly names this actor and
                # its own mission was selected by the reconstruction author.
                spec, basis = original, 'declared_own_datamine_profile'
            elif len(specs[key(actor)]) == 1:
                spec, basis = specs[key(actor)][0], 'unique_boss_infobox_in_declared_own_page'
                if single_own_battle and sum(key(n) == key(actor) for _, n in
                                             linked_enemies(single_own_battle.get('boss', ''))) == 1:
                    basis = 'unique_own_battle_contract_and_boss_infobox'
            elif specs[key(actor)]:
                tier = next((t for t in ('EXT', 'SVG', 'LGD', 'ELT', 'PRO', 'ADV', 'INT', 'BGN')
                             if re.search(r'\b' + t + r'\b', name)), 'Normal')
                own = [s for s in specs[key(actor)] if key(s['_variant']) == key(tier)]
                if len(own) == 1:
                    spec, basis = own[0], 'explicit_own_tier_tab_in_declared_source_page'
            values, mismatches = {}, []
            for label, token in STATS.items():
                published = base_stat(spec.get(label, ''))
                values[label] = {'effective': part.get(token), 'source': published}
                if published is not None and str(published) != str(part.get(token)):
                    mismatches.append({'field': token, 'label': label, 'effective': part.get(token), 'source': str(published)})
            # A multipart boss infobox is a total, never each limb's HP.
            body_count = sum(r['xqartN26'] == part['xqartN26'] for r in profiles)
            exact_datamine = basis == 'declared_own_datamine_profile'
            own_tier = basis in ('explicit_own_tier_tab_in_declared_source_page',
                                 'unique_own_battle_contract_and_boss_infobox')
            repairable = body_count == 1 and (exact_datamine or own_tier) and not entry.get('clash_scale')
            if repairable:
                changes.extend({'actor': part['xqartN26'], 'part': part['6Yc4RkdM'], **r,
                                'basis': basis, 'source_page': entry.get('source_page'),
                                'source_revision': entry.get('source_revision')} for r in mismatches)
            rows_out.append({'actor': part['xqartN26'], 'part': part['6Yc4RkdM'], 'name': actor,
                             'values': values, 'evidence': basis,
                             'ai': part.get('8a6gAwN9'), 'skill_set': part.get('A5x02C6a'),
                             'passive_set': part.get('jmKe42Yg'), 'break_id': part.get('e56NZY42'),
                             'debuff_resistance': part.get('Rcqa1Zt7'),
                             'original_datamine': original,
                             'donor': evidence.get('donor'),
                             'missing_source_fields': [f for f, v in values.items() if v['source'] is None],
                             'mismatches': mismatches, 'repairable': repairable})
        result.append({'mission': mid, 'name': name, 'area': area,
                       'effective_path': 'authored_response' if authored else 'event_encounters',
                       'source_page': entry.get('source_page'), 'source_revision': entry.get('source_revision'),
                       'source_url': entry.get('source_url'), 'source_sha256': entry.get('source_sha256'),
                       'formation_source': entry.get('preserved_formation_source'),
                       'level_scaling': entry.get('clash_scale'),
                       'reconstruction_flags': [k for k in entry if k not in {'bundle', 'enemies'} and
                                                any(w in k for w in ('reconstruction', 'source', 'scoped'))],
                       'phase_groups': [r.get('2fY1IomW') for r in effective.get('an6TB4WS', [])],
                       'documented_enemy_count_differences': documented_count_differences,
                       'actors': rows_out})
        if changes:
            corrections[mid] = {'effective_path': 'authored_response' if authored else 'event_encounters', 'changes': changes}
    # Inspect the remaining native bindings and authored captures as separate
    # effective paths. An unchanged downloaded capture is stronger evidence than
    # the JP same-ID fallback that an encounter entry may replace.
    native_phases, native_pools, native_groups = defaultdict(list), defaultdict(list), defaultdict(list)
    native_parts, native_monsters = defaultdict(list), {}
    for row in reader.base.load('F_MISSION_PHASE_MST'):
        native_phases[row['qo3PECw6']].append(row)
    for row in reader.base.load('F_BATTLE_LOTTERY_MST'):
        native_pools[row['c2gnh6Jd']].append(row)
    for row in reader.base.load('F_BATTLE_GROUP_MST'):
        native_groups[row['2fY1IomW']].append(row)
    for row in reader.base.load('F_MONSTER_PARTS_MST'):
        native_parts[row['xqartN26']].append(row)
    native_monsters = {r['xqartN26']: r for r in reader.base.load('F_MONSTER_MST')}
    original_native_missions = {r['qo3PECw6']: r for r in reader.base.load('F_MISSION_MST')}
    binding_audit = []
    for mid, binding in bindings.items():
        if not isinstance(binding, dict):
            continue
        mission = missions.get(mid, {})
        name = translated.get(mid) or mission.get('G4L0YIB2', '')
        area = dungeon_areas.get(mission.get('U9iHsau3'))
        if area in EXCLUDED_AREAS or re.search(r'unit intro', name, re.I):
            continue
        source = str(binding['source'])
        active = ('authored_response' if 'jnw49dUq@' + mid in responses else
                  'event_encounters' if mid in document['missions'] else 'native_binding')
        phase_rows = sorted(native_phases[source], key=lambda r: int(r['6v7y3QcJ']))
        graph, actors = [], set()
        for phase in phase_rows:
            if phase['gou39JeI'] != '2':
                continue
            pools = native_pools[phase['6uIYE15X']]
            choices = []
            for pool in pools:
                group = pool['2fY1IomW']
                own = [dict(actor=r['xqartN26'], slot=r['Z0EN6jSh']) for r in native_groups[group]]
                actors.update(r['actor'] for r in own)
                choices.append({'group': group, 'weight': pool['ixDq7yJ8'], 'actors': own})
            graph.append({'phase': phase['6v7y3QcJ'], 'pool': phase['6uIYE15X'], 'choices': choices})
        binding_audit.append({'mission': mid, 'name': name, 'area': area, 'effective_path': active,
                              'binding': binding,
                              'global_contract': {k: mission.get(k) for k in
                                                  ('B6kyCQ9M', '8xi6Xvyk', 'B6H34Mea', 'Z0EN6jSh')},
                              'native_source_contract': {k: original_native_missions.get(source, {}).get(k) for k in
                                                         ('G4L0YIB2', 'B6kyCQ9M', '8xi6Xvyk', 'B6H34Mea', 'Z0EN6jSh')},
                              'source_phase_graph': graph,
                              'source_actor_rows': [{'actor': pid,
                                                     'model': native_monsters.get(pid, {}).get('V9j8wJcC'),
                                                     'name': reader.names.get(pid),
                                                     'parts': [{k: r.get(k) for k in
                                                                ('6Yc4RkdM', *STATS.values(), '8a6gAwN9', 'A5x02C6a',
                                                                 'jmKe42Yg', 'e56NZY42', 'hn42BL3Q', 'D9Nb7jgd', 'Rcqa1Zt7')}
                                                               for r in native_parts[pid]]}
                                                    for pid in sorted(actors, key=int)],
                              'provenance_status': 'Native JP source fields are preserved; own Global equivalence requires the recorded identity/tier evidence, not the numeric ID alone.'})
    with zipfile.ZipFile(ROOT / 'repository snapshots/TBMonkey__ffbe-gl-server-770788072563.zip') as archive:
        baseline = json.loads(archive.read(next(n for n in archive.namelist() if n.endswith('/server/responses.json'))))
    authored_audit = []
    compare_fields = (*STATS.values(), 'hn42BL3Q', 'D9Nb7jgd', 'Rcqa1Zt7', 'e56NZY42', '8a6gAwN9',
                      'A5x02C6a', 'jmKe42Yg', '4Y2DGP7m')
    for response_key, bundle in responses.items():
        if not response_key.startswith('jnw49dUq@') or not isinstance(bundle, dict):
            continue
        mid = response_key.split('@', 1)[1]
        mission = missions.get(mid, {})
        area = dungeon_areas.get(mission.get('U9iHsau3'))
        if area in EXCLUDED_AREAS:
            continue
        original = baseline.get(response_key, {})
        original_parts = {(r['xqartN26'], r['6Yc4RkdM']): r for r in original.get('bV34YIJQ', [])}
        actor_rows = []
        for row in bundle.get('bV34YIJQ', []):
            source = original_parts.get((row['xqartN26'], row['6Yc4RkdM']))
            actor_rows.append({'actor': row['xqartN26'], 'part': row['6Yc4RkdM'],
                               'source_present': source is not None,
                               'differences': {k: {'original': source.get(k), 'current': row.get(k)}
                                               for k in compare_fields if source and source.get(k) != row.get(k)}})
        authored_audit.append({'mission': mid, 'area': area,
                               'baseline_source': 'TBMonkey__ffbe-gl-server-770788072563.zip/server/responses.json',
                               'original_response_present': response_key in baseline, 'actors': actor_rows})
    report = {'scope': 'Every authored encounter and native event binding, effective authored response precedence, excluding user-excluded unit introductions',
              'limitations': ['A declared source association is inspected, not upgraded to original Global wire provenance.',
                              'A unique infobox does not alone establish the own stage tier, so it produces no automatic patch.',
                              'Missing own NPC server stats, passives, Break and exact formation fields remain separate from model/AI identity.',
                              'Documented interpolation is identified, not claimed to be the recovered original level formula.'],
              'counts': {'encounter_entries': len(document['missions']), 'inspected': len(result),
                         'excluded_unit_intro': len(excluded), 'scoped_mismatch_missions': len(corrections),
                         'scoped_mismatch_fields': sum(len(r['changes']) for r in corrections.values()),
                         'native_bindings': len(binding_audit), 'authored_responses': len(authored_audit),
                         'baseline_authored_parts': sum(a['source_present'] for s in authored_audit for a in s['actors']),
                         'baseline_stat_differences': sum(bool(a['differences']) for s in authored_audit for a in s['actors'])},
              'excluded_unit_intro_missions': excluded, 'missions': result,
              'native_bindings': binding_audit, 'authored_responses': authored_audit}
    return report, corrections


if __name__ == '__main__':
    report, corrections = inspect()
    target = ROOT / 'logs/ffbe-reconstructed-combat-source-audit-20261111.json'
    target.write_text(json.dumps(report, ensure_ascii=False, separators=(',', ':')) + '\n', encoding='utf-8')
    target = ROOT / 'build/scratch/reconstructed-combat-stat-corrections.json'
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(corrections, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report['counts']))
