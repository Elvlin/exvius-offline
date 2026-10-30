"""Apply season-scoped Global wiki profiles before same-ID edition bindings.

This supplements the existing encounter reconstruction. Stage sections own
their boss profiles, so a repeated boss name cannot borrow another season's
statistics. Original Global graphics, AI and skill sets remain authoritative
where preserved. Missing formations retain the documented reconstruction.
"""
from copy import deepcopy
import json
import hashlib
from pathlib import Path
import re
import zipfile

from reconstruct_event_battles import Reconstruction, ROOT, fields, key, templates
from build_event_archive import rows


BASE = 'Dark Visions - The Advent of Chaos'
REFERENCES = ('event-battle-vision-areas-wiki-20261029.json',
              'event-battle-vision-named-stages-wiki-20261029.json')


def sections(page):
    text = Reconstruction.text(page)
    headers = list(re.finditer(r'^==\s*Stage\s+([\d-]+)\s*==\s*$', text, re.M))
    if not headers:
        return [(None, page)]
    result = []
    for n, header in enumerate(headers):
        scoped = deepcopy(page)
        scoped['revisions'][0]['slots']['main']['*'] = text[
            header.end():headers[n + 1].start() if n + 1 < len(headers) else len(text)]
        result.append((header[1], scoped))
    return result


def record_for(reconstruction, page, name, stage=None):
    candidates = [(number, scoped) for number, scoped in sections(page)
                  if stage is None or number == stage]
    if len(candidates) != 1:
        return None
    _, scoped = candidates[0]
    specs = [fields(block) for _, block in templates(reconstruction.text(scoped), 'Boss Infobox')]
    specs = [s for s in specs if s.get('name') and s.get('hp')]
    if not specs:
        return None
    # The common reconstructor accepts a profile per enemy. Convert published
    # base + fixed totals explicitly rather than silently ignoring those cells.
    profiles = {}
    native = {}
    listed_skills = {key(fields(block).get('name', ''))
                     for _, block in templates(reconstruction.text(scoped), 'mstable')}
    for spec in specs:
        profile = dict(spec)
        for field in ('atk', 'def', 'mag', 'spr'):
            value = profile.get(field, '').replace(',', '').strip()
            if re.fullmatch(r'\d+\s*\+\s*\d+', value):
                profile[field] = str(sum(int(v) for v in value.split('+')))
        profiles[key(spec['name'])] = profile
        candidates = [row for sid, row in reconstruction.global_sets.items()
                      if sid in reconstruction.global_ai and
                      key(row.get('G4L0YIB2', '')) == key(spec['name']) and
                      reconstruction.names.get(sid) == spec['name']]
        if candidates:
            def agreement(row):
                names = {key(reconstruction.raw_skills.get(sid, {}).get('name', ''))
                         for sid in row['7qxLC5hP'].split(',') if sid}
                return (len(names & listed_skills), -len(names - listed_skills), -int(row['A5x02C6a']))
            chosen = max(candidates, key=agreement)
            native[spec['name']] = {'part_id': chosen['A5x02C6a'], 'ai': chosen['A5x02C6a']}
    return {'heading': name, 'names': [name], 'page': scoped,
            'fields': {'monster': '', 'boss': ','.join('[[' + s['name'] + ']]' for s in specs)},
            'published_profiles': profiles, 'season_scoped': True,
            'native_enemy_overrides': native, 'retain_native_identity': True}


def main():
    reconstruction = Reconstruction()
    # Stay outside the existing reconstruction's generated ID range while
    # retaining signed 32-bit native IDs and deterministic stage ordering.
    reconstruction.counter = 8_000_000
    reconstruction.group_counter = 8_000_000
    for name in REFERENCES:
        data = json.loads((ROOT / 'logs/reference' / name).read_text(encoding='utf8'))
        for batch in data['batches']:
            for redirect in batch.get('query', {}).get('redirects', []):
                reconstruction.redirects[key(redirect['from'])] = key(redirect['to'])
            for page in batch.get('query', {}).get('pages', {}).values():
                if page.get('revisions'):
                    reconstruction.pages[key(page['title'])] = page
    missions = {r['qo3PECw6']: r for r in rows('F_MISSION_MST')}
    events = [e for e in json.loads((ROOT / 'source/server/event_archive.json').read_text())['events']
              if e['name'] == 'Dark Visions']
    with zipfile.ZipFile(ROOT / 'repository snapshots/aEnigmatic__ffbe-95727376e82d.zip') as archive:
        original = json.loads(archive.read(next(n for n in archive.namelist() if n.endswith('/missions.json'))))
    destination = ROOT / 'source/server/event_encounters.json'
    document = json.loads(destination.read_text(encoding='utf8'))
    recovered = []
    for season, event in enumerate(events, 1):
        title = BASE + (f' {season}' if season > 1 else '')
        for mid in event['missions']:
            mission = missions[mid]
            if not int(mission['8xi6Xvyk']):
                continue
            name = original.get(mid, {}).get('name', '')
            record = None
            if season <= 3:
                match = re.fullmatch(r'Quest (\d+)-(\d+)', name)
                if match:
                    page = reconstruction.page(title + '/Area ' + match[1])
                    if page:
                        record = record_for(reconstruction, page, name, '-'.join(match.groups()))
            else:
                stage = re.search(r'\s+(II|III|\d+)$', name)
                stem = name[:stage.start()] if stage else name
                page = reconstruction.page(title + '/' + stem)
                if page:
                    ordinal = str({'II': 2, 'III': 3}.get(stage[1], stage[1])) if stage else '1'
                    scoped = sections(page)
                    record = record_for(reconstruction, page, name,
                                        ordinal if scoped[0][0] is not None else None)
                if record is None:
                    page = reconstruction.page(title)
                    if page:
                        boxes = [fields(b) for _, b in templates(reconstruction.text(page), 'Battle Info')]
                        matched = [box for box in boxes if key(box.get('name', '')) == key(name)]
                        if len(matched) == 1:
                            record = record_for(reconstruction, page, name)
            if record is None:
                continue
            bundle, provenance = reconstruction.bundle(mid, mission, record, [name], title)
            url = 'https://exvius.fandom.com/wiki/' + record['page']['title'].replace(' ', '_')
            document['missions'][mid] = {'bundle': bundle, 'enemies': provenance,
                'identity_source': 'Global campaign ordinal and exact stage-scoped boss infobox',
                'source_page': record['page']['title'],
                'source_revision': record['page']['revisions'][0].get('revid'), 'source_url': url,
                'source_sha256': hashlib.sha256(reconstruction.text(record['page']).encode('utf8')).hexdigest(),
                'vision_stage_scoped': True}
            recovered.append(mid)
    document['local_monster_names'].update(reconstruction.local_names)
    destination.write_text(json.dumps(document, ensure_ascii=False, separators=(',', ':')) + '\n', encoding='utf8')
    print('Applied Global stage-scoped profiles:', len(recovered))


if __name__ == '__main__':
    main()
