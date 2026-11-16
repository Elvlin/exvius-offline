"""Add the four original January 19 SaGa sets to the earlier JP inventory.

Uses the existing canonical battle resolver against the pinned published APK.
No game tables, enemy stats or runtime selectors are authored by this tool.
"""
import collections
import contextlib
import csv
import hashlib
import io
import json
from pathlib import Path
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / 'Japan content/Earlier JP crossovers'
SHARED = ROOT / 'Japan content/Shared sources'
sys.path.insert(0, str(ROOT / 'source/server'))
from battle_content import Source, derive_mission, unescape_cell

NEW = {'641001': ('Half-Human, Half-Mystic Fate', 3),
       '641101': ('Tragedy at the Ice Megalith', 4),
       '641201': ('The Golden Swordsman', 2),
       '641301': ('Character Battle II (SaGa, January 19)', 5)}


def nd(path):
    return [json.loads(s) for s in path.read_text(encoding='utf-8-sig').splitlines() if s.strip()]


def read_csv(name):
    with (BASE / name).open(encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))


def write_csv(name, values):
    with (BASE / name).open('w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(values[0]))
        w.writeheader(); w.writerows(values)


def union(values, key):
    return sorted({s for r in values for s in str(r.get(key, '')).split(';') if s}, key=lambda s: int(s) if s.isdigit() else s)


def true(value):
    return str(value).lower() == 'true'


class ApkSource(Source):
    def __init__(self, archive):
        self.archive, self.cache = archive, {}

    def load(self, table):
        if table not in self.cache:
            raw = self.archive.read('assets/rules/content/battle/' + table + '.tsv').decode('utf-8-sig').splitlines()
            header = json.loads(raw[0][1:].strip())
            self.cache[table] = [dict(zip(header['fields'], [unescape_cell(v) for v in line.split('\t')])) for line in raw[1:] if line]
        return self.cache[table]


def main():
    with zipfile.ZipFile(SHARED / 'ffbe-jp-ea7d9fa82659.zip') as z:
        parsed = {t: json.loads(z.read(next(n for n in z.namelist() if n.endswith('/' + t + '.json'))))
                  for t in ('dungeons', 'missions', 'monster_ai', 'monster_skillsets')}
    inventory = read_csv('earlier-crossovers.csv')
    next_id = max(int(r['entry_id'].rsplit('-', 1)[1]) for r in inventory) + 1
    for did, (label, count) in NEW.items():
        if any(did in r['jp_dungeon_ids'].split(';') for r in inventory):
            continue
        mids = list(parsed['dungeons'][did]['missions'])
        if len(mids) != count:
            raise ValueError('Original Japanese dungeon membership differs: ' + did)
        row = dict.fromkeys(inventory[0], '')
        row.update(entry_id=f'JP-OLD-{next_id:03}', release_date_jst='2024-01-19', family='SaGa series',
                   event_or_wave=label, jp_dungeon_ids=did, jp_mission_ids=';'.join(mids),
                   source_mission_count=str(count), public_mission_ids_present=str(count),
                   unit_ids_in_final_jp_source='350000107;350000117;351000107;351000117',
                   owned_data='Original live Japanese area, dungeon, mission and challenge masters; retained native encounter graph; original native card image',
                   visuals='Exact original Japanese spdungeon7 card owned; model dependencies tracked separately',
                   english='Native IDs and objective order retained for reviewed English bindings',
                   missing='Original enemy body/part records where absent; verified combat references and end-to-end gameplay validation',
                   source='https://jp.finalfantasy.com/news/4870/',
                   evidence_note='Publisher January 19 release, original card title, native owner graph and parsed Japanese dungeon membership agree. Separate from the January 11 sets.',
                   status='SOURCE_OWNED_CATALOGUE_ENTRY_MISSING')
        inventory.append(row); next_id += 1
    inventory.sort(key=lambda r: (r['release_date_jst'] or '9999', r['entry_id']))
    selected_events = [r for r in inventory if r['status'].startswith('SOURCE_OWNED_CATALOGUE_ENTRY_MISSING')]
    if len(selected_events) != 28:
        raise ValueError('Expected 28 earlier source-owned catalogue gaps.')
    stages, event_counts = read_csv('stage-details.csv'), read_csv('stage-counts-and-gaps.csv')
    evidence = json.loads((BASE / 'stage-gap-evidence.json').read_text(encoding='utf-8'))
    native_missions = {r['qo3PECw6']: r for r in nd(ROOT / 'data/mst_decoded/F_MISSION_MST.ndjson')}
    native_challenges = nd(ROOT / 'data/mst_decoded/F_CHALLENGE_MST.ndjson')
    dictionaries = {r['V9j8wJcC']: r for r in nd(ROOT / 'data/mst_decoded/F_MONSTER_DICTIONARY_MST.ndjson')}
    known = {r['mission_id'] for r in stages}
    apk_path = ROOT / 'release/exvius-offline-v0.1.25.apk'
    if hashlib.sha256(apk_path.read_bytes()).hexdigest() != evidence['summary']['apk_sha256']:
        raise ValueError('Pinned APK changed.')
    with zipfile.ZipFile(apk_path) as z:
        source = ApkSource(z)
        phases, lotteries, groups = collections.defaultdict(list), collections.defaultdict(list), collections.defaultdict(list)
        for r in source.load('F_MISSION_PHASE_MST'): phases[r['qo3PECw6']].append(r)
        for r in source.load('F_BATTLE_LOTTERY_MST'): lotteries[r['c2gnh6Jd']].append(r)
        for r in source.load('F_BATTLE_GROUP_MST'): groups[r['2fY1IomW']].append(r)
        monsters = {r['xqartN26']: r for r in source.load('F_MONSTER_MST')}
        parts = {r['xqartN26']: r for r in source.load('F_MONSTER_PARTS_MST')}
        for event in selected_events:
            if event['jp_dungeon_ids'] not in NEW:
                continue
            own = []
            for mid in event['jp_mission_ids'].split(';'):
                if mid in known:
                    own.append(next(r for r in stages if r['mission_id'] == mid)); continue
                native, jp, phase = native_missions[mid], parsed['missions'][mid], phases[mid]
                missing_pools, missing_groups, enemies = set(), set(), set()
                for p in phase:
                    if p.get('gou39JeI') != '2': continue
                    pool = p['6uIYE15X']; candidates = [r for r in lotteries[pool] if int(r.get('ixDq7yJ8') or 0) > 0]
                    if not candidates: missing_pools.add(pool)
                    for candidate in candidates:
                        group = candidate['2fY1IomW']
                        if not groups[group]: missing_groups.add(group)
                        enemies.update(r['xqartN26'] for r in groups[group])
                missing_monsters, missing_parts = enemies - set(monsters), enemies - set(parts)
                graphics = {monsters[i]['V9j8wJcC'] for i in enemies if i in monsters}
                candidate_graphics = {i[:-2] for i in missing_monsters if i[:-2] in dictionaries}
                success, error = False, ''
                try:
                    with contextlib.redirect_stdout(io.StringIO()): derive_mission(int(mid), source, break_status={})
                    success = True
                except (Exception, SystemExit) as exc: error = str(exc)
                row = dict.fromkeys(stages[0], '')
                row.update(entry_id=event['entry_id'], event=event['event_or_wave'], family=event['family'], mission_id=mid,
                           jp_name=jp['name'], jp_high_level_type=jp['type'], jp_cost_type=jp['cost_type'], native_subtype=native['gQR24kST'],
                           original_stage_wave_count=jp.get('wave_count', 0), shipped_phase_rows=len(phase),
                           shipped_battle_phase_rows=sum(p.get('gou39JeI') == '2' for p in phase),
                           canonical_derivation_passed=success, canonical_derivation_error=error,
                           enemy_identity_count_all_alternatives=len(enemies), enemy_ids=';'.join(sorted(enemies)),
                           part_rows_available=len(enemies & set(parts)), missing_monster_ids=';'.join(sorted(missing_monsters)),
                           missing_part_ids=';'.join(sorted(missing_parts)), missing_weighted_lotteries=';'.join(sorted(missing_pools)),
                           missing_groups=';'.join(sorted(missing_groups)), graphic_ids=';'.join(sorted(graphics)),
                           background_ids=';'.join(sorted({p['DYTx1Is3'] for p in phase if p.get('DYTx1Is3') not in ('', '0', None)})),
                           native_resource_selector_ids=native.get('q4f9IdMs', ''),
                           source_clear_reward_count=len(jp.get('rewards', [])), source_challenge_count=sum(r['qo3PECw6'] == mid for r in native_challenges),
                           measured_graph_and_geometry_closure=False, opening_battle_derivation_applicable=True,
                           readiness_classification='ORIGINAL_ENEMY_BODIES_AND_PARTS_REQUIRED' if missing_monsters or missing_parts else 'FULL_GAMEPLAY_NOT_VERIFIED',
                           missing_bodies_recovered_in_owned_Memorial_source=0, missing_parts_recovered_in_owned_Memorial_source=0,
                           encyclopedia_candidate_graphic_ids=';'.join(sorted(candidate_graphics)),
                           candidate_graphics_binding_status='Surviving original dictionary prefix candidates; original body-to-graphic pointers still absent',
                           AI_and_skill_closure_status='Original missing part pointers prevent claiming full AI/skill/drop closure',
                           still_unverified='Original enemy stats and native pointers; field/drop semantics; native graphical version and gameplay verification')
                stages.append(row); own.append(row); known.add(mid)
                gaps = {'missing_monsters': sorted(missing_monsters), 'missing_parts': sorted(missing_parts)}
                if missing_pools: gaps['missing_weighted_lotteries'] = sorted(missing_pools)
                if missing_groups: gaps['missing_groups'] = sorted(missing_groups)
                evidence['per_stage'].append({'mission_id': mid, 'source_native_name': native['G4L0YIB2'],
                                               'all_alternative_gaps': gaps, 'canonical_notes': error, 'graphics': sorted(graphics)})
                for ident in missing_monsters:
                    gid = ident[:-2]
                    if gid in dictionaries:
                        evidence['missing_body_dictionary_candidates'][ident] = {'candidate_graphic_id': gid,
                            'dictionary_row': dictionaries[gid], 'binding_status': 'Original dictionary prefix candidate; absent original body graphic pointer remains unverified'}
            if any(r['entry_id'] == event['entry_id'] for r in event_counts): continue
            count = dict.fromkeys(event_counts[0], '')
            count.update(entry_id=event['entry_id'], family=event['family'], event=event['event_or_wave'], dungeon_ids=event['jp_dungeon_ids'],
                         stage_count=len(own), unique_stage_count=len(own), community_BATTLE_count=len(own), community_EXPLORATION_count=0,
                         source_native_subtypes=json.dumps(dict(collections.Counter(r['native_subtype'] for r in own)), sort_keys=True),
                         source_cost_types=json.dumps(dict(collections.Counter(r['jp_cost_type'] for r in own)), sort_keys=True),
                         canonical_derivation_passed=sum(true(r['canonical_derivation_passed']) for r in own),
                         canonical_derivation_failed=sum(not true(r['canonical_derivation_passed']) for r in own),
                         all_alternative_missing_monster_ids=';'.join(union(own, 'missing_monster_ids')),
                         all_alternative_missing_part_ids=';'.join(union(own, 'missing_part_ids')),
                         missing_lottery_ids=';'.join(union(own, 'missing_weighted_lotteries')), missing_group_ids=';'.join(union(own, 'missing_groups')),
                         graphics_ids=';'.join(union(own, 'graphic_ids')), ordinary_battle_stages_with_derivation_failure=sum(not true(r['canonical_derivation_passed']) for r in own),
                         field_stages_needing_script_route_validation=0, missing_bodies_recovered_in_owned_Memorial_source=0,
                         missing_parts_recovered_in_owned_Memorial_source=0, resource_binding_status='Exact original selectors retained; canonical native graph export supplies file ownership',
                         why_not_enabled='Absent catalogue entry; original body/part source gaps prevent original combat resolution', gameplay_verified=False,
                         graphic_binding_status='Original dictionary candidates and original model source recovery tracked separately',
                         AI_and_skill_binding_status='Full closure cannot be inferred while original part rows are absent')
            event_counts.append(count)
    if len(stages) != 130 or len(event_counts) != 28:
        raise ValueError('Expected 28 sets and 130 original unique stages.')
    summary = evidence['summary']
    summary.update(quest_sets=28, unique_stages=130, total_stage_references=130,
                   stage_types=dict(collections.Counter(r['jp_high_level_type'] for r in stages)),
                   native_subtypes=dict(collections.Counter(str(r['native_subtype']) for r in stages)),
                   canonical_derivation_passed=sum(true(r['canonical_derivation_passed']) for r in stages),
                   canonical_derivation_failed=sum(not true(r['canonical_derivation_passed']) for r in stages),
                   ordinary_battle_derivation_failures=sum(not true(r['canonical_derivation_passed']) and r['jp_high_level_type'] != 'EXPLORATION' for r in stages))
    for target, field in [('missing_monster_ids', 'missing_monster_ids'), ('missing_part_ids', 'missing_part_ids')]: summary[target] = union(stages, field)
    missing = set(summary['missing_monster_ids'])
    native_ai = {r['8a6gAwN9'] for r in nd(ROOT / 'data/mst_decoded/F_AI_MST.ndjson')}
    native_sets = {r['A5x02C6a'] for r in nd(ROOT / 'data/mst_decoded/F_MONSTER_SKILL_SET_MST.ndjson')}
    summary.update(missing_enemy_body_count=len(missing), missing_enemy_parts_identity_count=len(summary['missing_part_ids']),
                   same_ID_community_AI_entries_owned=len(missing & set(parsed['monster_ai'])),
                   same_ID_community_skillset_entries_owned=len(missing & set(parsed['monster_skillsets'])),
                   same_ID_native_AI_entries_owned=len(missing & native_ai), same_ID_native_skillset_entries_owned=len(missing & native_sets),
                   missing_enemy_dictionary_candidate_rows=len(evidence['missing_body_dictionary_candidates']),
                   unique_dictionary_candidate_graphics=len({v['candidate_graphic_id'] for v in evidence['missing_body_dictionary_candidates'].values()}))
    summary.pop('all_55_graphic_candidate_required_files_present', None)
    evidence['scope_expansion'] = {'source': 'https://jp.finalfantasy.com/news/4870/', 'additional_dungeons': list(NEW),
                                   'sets_added': 4, 'stages_added': 14, 'basis': 'Primary release, original card text and exact native membership verified'}
    evidence['inspected_original_corpus']['meaning'] = f'{len(missing)} missing original body/part identities remain absent from the inspected source corpus; this is not a claim that every historical source has been exhausted.'
    for family in evidence['families']:
        own = [r for r in stages if r['family'] == family['family']]
        family.update(quest_sets=len({r['entry_id'] for r in own}), stages=len(own),
                      community_BATTLE=sum(r['jp_high_level_type'] == 'BATTLE' for r in own),
                      community_EXPLORATION=sum(r['jp_high_level_type'] == 'EXPLORATION' for r in own),
                      unique_missing_body_ids=len(union(own, 'missing_monster_ids')), unique_missing_part_ids=len(union(own, 'missing_part_ids')),
                      surviving_dictionary_candidate_graphics=len({i[:-2] for i in union(own, 'missing_monster_ids') if i[:-2] in dictionaries}))
    write_csv('earlier-crossovers.csv', inventory)
    write_csv('stage-details.csv', stages)
    write_csv('stage-counts-and-gaps.csv', event_counts)
    (BASE / 'stage-gap-evidence.json').write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'sets': 28, 'stages': 130, 'missing_original_body_ids': len(missing),
                      'dictionary_candidate_graphics': summary['unique_dictionary_candidate_graphics'],
                      'new_model_candidates': sorted({i[:-2] for i in missing if i[:-2] in dictionaries} -
                          {r['graphic_id'] for r in read_csv('original-jp-monster-source-map.csv')})}))


if __name__ == '__main__':
    main()
