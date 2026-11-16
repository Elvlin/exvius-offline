"""Restore source-identified Global campaigns with their recovered original art.

Only the explicit source-authoring scope is merged. Existing archive rows and
dungeon mappings outside that scope remain untouched, including restored JP sets.
"""
from copy import deepcopy
import hashlib
import json

from build_event_archive import ROOT, build_document, rows


SERVER = ROOT / 'source/server'
SOURCES = SERVER / 'content/omitted_global_event_sources.json'
NATIVE_ART = SERVER / 'content/native_event_banner_sources.json'
DEPENDENCIES = ROOT / 'logs/ffbe-restored-event-effective-dependencies-20261111.json'
ADDITIONAL_DEPENDENCIES = ROOT / 'logs/ffbe-additional-event-source-graph-20261111.json'


def document(path):
    return json.loads(path.read_text(encoding='utf-8'))


def checked_art(entry):
    """Accept only retained source bytes and their reviewed runtime image."""
    for kind in ('source', 'runtime'):
        path = (ROOT / entry[kind + '_file']).resolve()
        if not path.is_relative_to(ROOT.resolve()):
            raise ValueError('Artwork outside project: ' + str(path))
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != entry[kind + '_sha256']:
            raise ValueError('Reviewed original artwork changed: ' + str(path))
    return deepcopy(entry)


def main():
    identities = document(SOURCES)['events']
    native = {row['area']: row for row in document(NATIVE_ART)['sources']}
    coverage = {row['area']: row for row in document(DEPENDENCIES)['areas']}
    if ADDITIONAL_DEPENDENCIES.exists():
        coverage.update({row['area']: row for row in document(ADDITIONAL_DEPENDENCIES)['areas']})
    raid_areas = {'747', '797', '940', '958'}
    point_parents = {'3150': ('3148', '31500101'), '3176': ('3175', '31760101')}
    raids = {row['event_id']: row for row in document(SERVER / 'raid_archive.json')['events']}
    raid_summons = {str(row.get('raid_event_id')): row
                    for row in document(SERVER / 'gacha_raid.json')['banners']}
    raid_links = {str(row['event_id']) for row in document(SERVER / 'raid_summon_links.json')['links']}
    art_path, archive_path = SERVER / 'event_art.json', SERVER / 'event_archive.json'
    art, archive = document(art_path), document(archive_path)
    recovered, restored, pending, held = [], [], [], []
    for aid, identity in identities.items():
        if aid in native:
            entry = checked_art(native[aid])
            entry.pop('area', None)
            entry['source_size'] = entry['size']
        elif identity.get('reuse_art_area'):
            parent = str(identity['reuse_art_area'])
            entry = checked_art(art['events'][parent])
            entry['same_campaign_art_area'] = parent
        else:
            pending.append(aid)
            continue
        entry.update(name=identity['canonical_name'],
                     archive_alias=identity.get('archive_alias'),
                     source_page=identity['source_page'],
                     banner_title=identity['banner_title'],
                     release=identity.get('release'),
                     release_source_page=identity.get('release_source_page'),
                     vortex_tab=identity.get('vortex_tab', 0),
                     vortex_category=identity.get('vortex_category', 'event'),
                     archive_ready=coverage.get(aid, {}).get('status') == 'source_graph_ready_no_known_core_gap')
        if aid in raid_areas:
            raid, summon = raids.get(aid, {}), raid_summons.get(aid, {})
            coin = (raid.get('raid_coin') or {}).get('id')
            entry['archive_ready'] = bool(entry['archive_ready'] and aid in raid_links and coin and
                (summon.get('cost') or {}).get('item_id') == coin and summon.get('reward_pool') and
                raid.get('mission_points') and raid.get('personal_milestones'))
        if aid in point_parents:
            parent, mid = point_parents[aid]
            ledger = raids.get(parent, {})
            entry['archive_ready'] = bool(entry['archive_ready'] and ledger.get('point_mode') == 'clear' and
                (ledger.get('mission_points') or {}).get(mid) == 2000 and ledger.get('personal_milestones'))
        art['events'][aid] = entry
        recovered.append(aid)
        if entry['archive_ready']:
            restored.append(aid)
        else:
            held.append(aid)

    generated = {row['area']: row for row in build_document(originals=art['events'])['events']}
    replacements = {}
    for aid in restored:
        event = generated[aid]
        identity = identities[aid]
        if identity.get('release'):
            # A preserved original release can precede the archive's rerun row.
            event['release'] = identity['release']
            event['date_source'] = identity.get('release_source_page') or identity['source_page']
        event.update(vortex_tab=identity.get('vortex_tab', 0),
                     vortex_category=identity.get('vortex_category', 'event'))
        replacements[aid] = event

    old_ids = {str(row['area']) for row in archive['events']}
    archive['events'] = [replacements.get(str(row['area']), row) for row in archive['events']
                         if str(row['area']) not in held]
    archive['events'].extend(sorted((row for aid, row in replacements.items() if aid not in old_ids),
                                    key=lambda row: (row['release'] or '', row['name'], int(row['area']))))
    names = {row['key'].rsplit('_', 1)[1]: row['v'][0]
             for row in rows('F_TEXT_DUNGEON_NAME', text=True)}
    dungeons = {row['U9iHsau3']: row for row in rows('F_DUNGEON_MST')}
    # Recover inner artwork independently of menu publication. Held campaigns
    # remain absent from the archive until their own dependencies are repaired.
    all_generated = {row['area']: row for row in build_document(include_unidentified=True,
                                                               originals=art['events'])['events']}
    for aid in recovered:
        event = all_generated[aid]
        for did in event['dungeons']:
            row = dungeons[did]
            art['dungeons'][did] = {
                'name': names.get(did) or event['name'],
                'filename': event['filename'],
                'original_image': row.get('7DTnc2Lt') or '',
                'source_page': event['source_page'],
                'fallback': 'Same campaign original English artwork with the original English stage caption.',
            }
    art_path.write_text(json.dumps(art, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    archive_path.write_text(json.dumps(archive, ensure_ascii=False, separators=(',', ':')) + '\n', encoding='utf-8')
    receipt = {'recovered_original_art_areas': recovered,
               'restored_areas': restored, 'new_areas': [aid for aid in restored if aid not in old_ids],
               'restored_missions': sum(len(row['missions']) for row in replacements.values()),
               'source_identified_pending_art': pending,
               'source_dependencies_pending_areas': held,
               'retained_other_archive_rows': len(old_ids - set(recovered)),
               'source_identity_file': SOURCES.relative_to(ROOT).as_posix(),
               'source_art_file': NATIVE_ART.relative_to(ROOT).as_posix(),
               'build_or_gameplay_tests_run': False}
    (ROOT / 'logs/ffbe-omitted-event-restoration-20261111.json').write_text(
        json.dumps(receipt, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(receipt))


if __name__ == '__main__':
    main()
