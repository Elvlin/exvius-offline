"""Retain own Global clear/challenge contracts with explicit source identity."""
import hashlib
import json

from build_event_archive import ROOT, build_document, rows


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(',', ':')).encode('utf-8')).hexdigest()


def build_contracts():
    identities = json.loads((ROOT / 'source/server/content/omitted_global_event_sources.json')
                            .read_text(encoding='utf-8'))['events']
    # Use the same English-text and dungeon ownership filter as the archive.
    # Raw area rows can also retain untranslated, unused mission variants.
    eligible = {mid: event['area'] for event in build_document(include_unidentified=True)['events']
                if event['area'] in identities for mid in event['missions']}
    existing_scope = set(eligible)
    originals = {row['qo3PECw6']: row for row in rows('F_MISSION_MST')}
    published = {mid: event['area'] for event in json.loads((ROOT / 'source/server/event_archive.json')
                                                         .read_text(encoding='utf8'))['events']
                 for mid in event['missions']}
    document = json.loads((ROOT / 'source/server/event_encounters.json').read_text(encoding='utf8'))
    excluded_intro = {'756', '965', '976', '1089', '1090'}
    areas = {row['U9iHsau3']: row['uv60hgDW'] for row in rows('F_DUNGEON_MST')}
    receipt = {'source': 'data/mst_decoded/F_MISSION_MST.ndjson',
        'original_master_sha256': hashlib.sha256((ROOT / 'data/mst_decoded/F_MISSION_MST.ndjson').read_bytes()).hexdigest(),
        'added_full_identity_missions': [], 'excluded_jp_missions': [],
        'unproven_header_identity': [], 'unsupported_rewards': []}
    for mid, entry in document['missions'].items():
        if mid in eligible or mid not in published or mid not in originals:
            continue
        row = originals[mid]
        area = areas.get(row['U9iHsau3'])
        if area in excluded_intro:
            continue
        if (entry.get('jp_weighted_lottery') or entry.get('jp_original_scope')
                or str(entry.get('source_url', '')).startswith('Japan content')):
            receipt['excluded_jp_missions'].append(mid)
            continue
        headers = entry['bundle'].get('1IfDqR4n', [])
        if len(headers) != 1 or headers[0] != row:
            receipt['unproven_header_identity'].append(mid)
            continue
        eligible[mid] = area
        receipt['added_full_identity_missions'].append(mid)

    # The Chamber of the Fallen uses retained battle bindings for these
    # original Global missions, so the encounter loop above never sees them.
    trial_recovery = set()
    for mid, row in originals.items():
        if mid in eligible or published.get(mid) != '899' or row.get('uv60hgDW') != '899':
            continue
        if areas.get(row['U9iHsau3']) != '899':
            continue
        reward = row.get('1x4bG2J8', '').split(':')
        if len(reward) == 4 and reward[0] == '21' and reward[1].isdecimal() and reward[2:] == ['1', '100']:
            eligible[mid] = '899'
            trial_recovery.add(mid)
    receipt['chamber_equipment_recovery_missions'] = sorted(trial_recovery)

    dictionaries = {}
    for kind, table, primary in ((20, 'F_ITEM_MST', 'tL6G9egd'),
            (21, 'F_EQUIP_ITEM_MST', 'J1YX9kmM'), (22, 'F_MATERIA_MST', 'H5jBL0Vf'),
            (23, 'F_IMPORTANT_ITEM_MST', '2dfixko3'), (10, 'F_UNIT_MST', '3HriTp6B'),
            (60, 'F_RECIPE_BOOK_MST', 'staFu8U1')):
        dictionaries[kind] = {row[primary]: row for row in rows(table)}
    challenges = {}
    for row in rows('F_CHALLENGE_MST'):
        challenges.setdefault(row['qo3PECw6'], []).append(row)
    missions = {}
    for row in originals.values():
        if row['qo3PECw6'] not in eligible:
            continue
        mid = row['qo3PECw6']
        first = []
        unsupported = []
        for entry in (row.get('1x4bG2J8') or '').split(','):
            if not entry.strip() or entry.strip() == '0':
                continue
            fields = [value.strip() for value in entry.split(':')]
            if len(fields) < 3 or not all(value.isdecimal() for value in fields):
                raise ValueError('Invalid own mission reward: ' + mid)
            if len(fields) > 3 and fields[3] != '100':
                raise ValueError('Non-fixed mission clear reward needs its own policy: ' + mid)
            kind, iid = int(fields[0]), fields[1]
            supported = kind in (50, 51) or iid in dictionaries.get(kind, {})
            if kind == 60 and supported:
                supported = str(dictionaries[kind][iid].get('gJf3zp8a', '')).isdecimal()
            if not supported:
                unsupported.append({'kind': kind, 'id': iid, 'original_tuple': entry})
            first.append(':'.join(fields))
        if unsupported:
            receipt['unsupported_rewards'].append({'mission': mid,
                'original_mission_clear_reward': row.get('1x4bG2J8') or '',
                'mission_sha256': digest(row), 'missing_dictionary_references': unsupported})
            if mid in existing_scope or mid in trial_recovery:
                raise ValueError('Required own clear contract is unsupported: ' + mid)
            # Do not partially claim a mission receipt while its recipe is
            # missing. It must remain recoverable after its original book is restored.
            continue
        own_challenges = sorted(challenges.get(mid, []), key=lambda value: int(value['Z0EN6jSh']))
        missions[mid] = {'area': eligible[mid],
                         'original_mission_clear_reward': row.get('1x4bG2J8') or '',
                         'first_clear_reward': ','.join(first),
                         'original_rank_exp': row.get('B6H34Mea'),
                         'original_mission_gil': row.get('7UR4J2SE'),
                         'mission_sha256': digest(row),
                         'authority': 'Exact original Global mission row; fixed raw clear tuple. '
                             'Runtime CSV only trims whitespace and omits the original zero sentinel.',
                         'challenge_ids': [value['V36ygRYs'] for value in own_challenges],
                         'challenge_rows_sha256': digest(own_challenges)}
        if mid in trial_recovery:
            missions[mid]['recover_legacy_equipment_clear'] = True
    result = {'version': 1, 'scope': 'Source-proven Global restoration and published own-Global reconstructed missions',
              'sources': ['data/mst_decoded/F_MISSION_MST.ndjson',
                          'data/mst_decoded/F_CHALLENGE_MST.ndjson',
                          'source/server/content/omitted_global_event_sources.json'],
              'original_master_sha256': receipt['original_master_sha256'],
              'clear_reward_policy': 'Own fixed clear bonuses once per mission clear history; '
                  'enemy drops, gil and challenge awards use their existing independent paths. '
                  'The intentional replayable challenge Lapis policy is unchanged.',
              'missions': missions}
    receipt['scope_missions'] = len(missions)
    receipt['scope_nonempty_clear_rewards'] = sum(bool(v['first_clear_reward']) for v in missions.values())
    receipt['preserved_restoration_scope_missions'] = len(existing_scope)
    receipt['applied_additional_nonempty_contracts'] = sum(
        mid not in existing_scope and bool(v['first_clear_reward']) for mid, v in missions.items())
    return result, receipt


def main():
    result, receipt = build_contracts()
    output = ROOT / 'source/server/content/omitted_global_mission_rewards.json'
    temporary = output.with_name(output.name + '.writing')
    temporary.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    temporary.replace(output)
    report = ROOT / 'logs/ffbe-global-clear-reward-source-audit-20261111.json'
    report.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    print(json.dumps({key: receipt[key] for key in ('scope_missions', 'scope_nonempty_clear_rewards',
        'preserved_restoration_scope_missions', 'applied_additional_nonempty_contracts')}))


if __name__ == '__main__':
    main()
