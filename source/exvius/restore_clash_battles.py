"""Restore Global CoW identities and AI instead of colliding Japanese mission IDs.

Pinned Global datamine profiles own the corresponding echelon. Missing
echelons reuse the same boss's preserved AI and profile. Intermediate levels
use the documented offline interpolation in battle_content.event_encounter.
"""
from copy import deepcopy
import hashlib
import json
import re

from build_event_archive import rows
from reconstruct_event_battles import Reconstruction, ROOT, key, fields, templates, numeric


def main():
    reconstruction = Reconstruction()
    reconstruction.counter = 9_000_000
    reconstruction.group_counter = 9_000_000
    references = json.loads((ROOT / 'logs/reference/clash-original-profiles-20261029.json').read_text(encoding='utf8'))
    references = {p['title']: p for p in references}
    pages = {p['title']: p for batch in json.loads((ROOT / 'logs/reference/event-battle-clash-wiki-20261028.json').read_text(encoding='utf8'))
             for p in batch['query']['pages'].values() if p.get('revisions')}
    names = {r['key'].rsplit('_', 1)[-1]: r['v'][0] for r in rows('F_TEXT_MISSION', text=True)}
    target = ROOT / 'source/server/event_encounters.json'
    document = json.loads(target.read_text(encoding='utf8'))
    restored = []
    for mission in rows('F_MISSION_MST'):
        if mission['gQR24kST'] != '50':
            continue
        mid = mission['qo3PECw6']
        title, tier = names[mid], int(mission['Z0EN6jSh'])
        page, reference = pages[title], references[title]
        files = [f for f in reference.get('files', []) if f['profiles'] and f['missions']]
        chosen = min(files, key=lambda f: abs(int(f['missions'][0][-2:]) - tier)) if files else None
        specs = [fields(block) for _, block in templates(reconstruction.text(page), 'Boss Infobox')]
        if chosen:
            profiles = deepcopy(chosen['profiles'])
        else:
            # The Kyros gist has been deleted. Retain its published boss and
            # original Global tier AI rather than substituting another enemy.
            spec = next(s for s in specs if s.get('name'))
            candidates = [(sid, row) for sid, row in reconstruction.global_sets.items()
                          if 'kyros' in row.get('G4L0YIB2', '').casefold() and sid in reconstruction.global_ai]
            exact = [item for item in candidates if re.search(r'tier\s*' + str(tier) + r'\b', item[1]['G4L0YIB2'], re.I)]
            sid, _ = min(exact or candidates, key=lambda item: int(item[0]))
            profile = {k: str(numeric(v)) for k, v in spec.items() if numeric(v) is not None}
            profile.update(name=spec['name'], part_id=sid, ai=sid)
            profiles = [profile]
        if chosen and int(chosen['missions'][0][-2:]) != tier:
            delta = tier - int(chosen['missions'][0][-2:])
            for profile in profiles:
                candidate = str(int(profile['ai']) + delta)
                old = reconstruction.global_sets.get(profile['ai'], {}).get('G4L0YIB2', '')
                new = reconstruction.global_sets.get(candidate, {}).get('G4L0YIB2', '')
                family = lambda s: re.sub(r'\s*tier\s*\d+.*$', '', s, flags=re.I).casefold()
                if candidate in reconstruction.global_ai and old and family(old) == family(new):
                    profile.update(ai=candidate, part_id=candidate)
        for profile in profiles:
            if profile['ai'] not in reconstruction.global_ai:
                raise ValueError('Missing original CoW AI: ' + profile['ai'])
        main = profiles[0]
        record = {'heading': title, 'names': [title], 'page': page,
                  'fields': {'monster': '', 'boss': '[[' + main['name'] + ']]'},
                  'profile_overrides': {key(main['name']): main},
                  'season_scoped': True, 'retain_native_identity': True}
        reconstruction.source_profiles_by_id[mid] = {p['part_id']: p for p in profiles}
        bundle, provenance = reconstruction.bundle(mid, mission, record, [title], title)
        document['missions'][mid] = {'bundle': bundle, 'enemies': provenance,
            'clash_scale': {'minimum': 1 if tier == 1 else (tier - 1) * 20,
                            'policy': 'Preserved reference stats at reference level; quadratic HP and linear combat-stat interpolation below it.'},
            'source_page': title, 'source_revision': page['revisions'][0]['revid'],
            'source_url': reference.get('url') or 'https://exvius.fandom.com/wiki/' + title.replace(' ', '_'),
            'source_sha256': chosen['sha256'] if chosen else hashlib.sha256(reconstruction.text(page).encode('utf8')).hexdigest(),
            'gist_revision': reference.get('revision'),
            'identity_source': 'Original Global boss, dictionary graphics and native AI. Published wiki fallback for deleted gist.'}
        restored.append(mid)
    document['local_monster_names'].update(reconstruction.local_names)
    target.write_text(json.dumps(document, ensure_ascii=False, separators=(',', ':')) + '\n', encoding='utf8')
    print('Restored Global Clash encounters:', len(restored))


if __name__ == '__main__':
    main()
