"""Reconstruct missing Global encounters from documented campaign rosters.

Uses the same native encounter assembler as Colosseum and Fundamental Forces.
Enemy identity, graphics and published statistics are retained. The unpublished
server formations and lower-tier statistics are explicit local reconstructions.
No unrelated enemy is substituted when its identity cannot be established.
"""
from collections import defaultdict
import copy
import hashlib
import json
from pathlib import Path
import re
import sys
from urllib.parse import unquote, quote
import zipfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'source/server'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from battle_content import IndexSource, derive_mission, resolve_pool, PARTS_TOKENS, PARTS_DEFAULTS
from build_event_archive import rows
from build_raid_archive import templates, plain
from colosseum_reconstruction import ELEMENTS, AILMENTS, STATS
from restore_event_battles import ReconstructionSource

# The wiki and original Global AI/text masters identify this campaign's enemy
# set, but its per-stage formations and server stats were not preserved. These
# assignments are local reconstructions, not recovered original wave lists.
DRAGON_ARC_BOSSES = {
    '11040404': ('Sigrien', '900011195', '900011195'),
    '11040604': ('Sigrien', '900011195', '900011195'),
    '11040802': ('Dark Ancestral Dragon', '900011196', '900011196'),
    '11040803': ('Dark Ancestral Dragon', '900011197', '900011196'),
    '11040804': ('Dark Ancestral Dragon', '900011198', '900011196'),
}

# Original Global enemy-ID blocks retain the 2016 Halloween/Christmas pools.
# Their original server wave order and lottery weights are unavailable.
LEGACY_POOLS = {
    '9000201': (900010130, 900010135),
    '9000202': (900010136, 900010141),
    '9000203': (900010142, 900010149),
    '9000301': (900010150, 900010150),
    '9000302': (900010151, 900010151),
    '9000303': (900010152, 900010152),
    '9000401': (900010153, 900010153),
    '9000402': (900010154, 900010157),
    '9000403': (900010158, 900010161),
    '9000404': (900010162, 900010165),
    '9000405': (900010166, 900010169),
}


def key(value):
    value = re.sub(r'\blevel\b', 'lvl', plain(value).casefold())
    value = re.sub(r'\bquests\b', 'quest', value)
    return re.sub(r'[^\w+]', '', value)


def fields(block):
    return {name.strip().casefold(): value.strip() for name, value in
            re.findall(r'^\|\s*([^=\n]+?)\s*=(.*?)(?=^\||\Z)', block, re.M | re.S)}


def numeric(value):
    value = plain(str(value)).replace(',', '').replace("'", '').strip()
    return int(value) if re.fullmatch(r'[+-]?\d+', value) else None


def linked_enemies(value):
    result = []
    for match in re.finditer(r'\[\[([^]|]+)(?:\|([^]]+))?\]\](?:\s*(?:x|×)\s*(\d+))?', value):
        title, label, quantity = match.groups()
        if title.startswith(('File:', 'Category:')):
            continue
        result.extend([(title, label or re.sub(r'\s*\(Monster\)$', '', title))] * int(quantity or 1))
    return result


class Reconstruction:
    def __init__(self):
        self.base = IndexSource()
        self.names = {row['key'].rsplit('_', 1)[-1]: row['v'][0]
                      for row in rows('F_TEXT_MONSTER_NAME', text=True)}
        self.monsters = {row['xqartN26']: row for row in self.base.load('F_MONSTER_MST')}
        self.parts = defaultdict(list)
        for row in self.base.load('F_MONSTER_PARTS_MST'):
            self.parts[row['xqartN26']].append(row)
        self.by_name, self.by_graphic = defaultdict(list), defaultdict(list)
        for iid, monster in self.monsters.items():
            if iid in self.parts:
                self.by_name[key(self.names.get(iid, ''))].append(iid)
                self.by_graphic[monster['V9j8wJcC']].append(iid)
        self.dictionary = {row['Z0EN6jSh']: row for row in rows('F_MONSTER_DICTIONARY_MST')}
        dictionary_by_id = {row['V9j8wJcC']: row for row in self.dictionary.values()}
        self.dictionary_labels = {row['key'].rsplit('_', 1)[-1]: row['v'][0]
                                  for row in rows('F_TEXT_MONSTER_DICTIONARY_NAME', text=True)}
        self.dictionary_by_name = defaultdict(list)
        for row in rows('F_TEXT_MONSTER_DICTIONARY_NAME', text=True):
            graphic = row['key'].rsplit('_', 1)[-1]
            if graphic in dictionary_by_id:
                self.dictionary_by_name[key(row['v'][0])].append(dictionary_by_id[graphic])
        # Some Global bestiary translations are blank although their native
        # enemy-name records and original graphic families are preserved.
        for pid, label in self.names.items():
            if pid.isdigit() and int(pid) < 900000000 and label:
                graphic = str(int(pid) // 100)
                if graphic in dictionary_by_id and dictionary_by_id[graphic] not in self.dictionary_by_name[key(label)]:
                    self.dictionary_by_name[key(label)].append(dictionary_by_id[graphic])
        self.pages, self.redirects = {}, {}
        for name in ('event-battles-wiki-20261026.json', 'event-battle-details-wiki-20261026.json',
                     'event-battle-extra-wiki-20261026.json', 'event-battle-linked-wiki-20261026.json',
                     'event-battle-legacy-wiki-20261026.json', 'event-battle-finalfantasy-wiki-20261026.json',
                     'event-battle-last-monsters-wiki-20261026.json', 'event-battle-clash-wiki-20261028.json',
                     'event-battle-vision-wiki-20261028.json'):
            for batch in json.loads((ROOT / 'logs/reference' / name).read_text(encoding='utf-8')):
                for redirect in batch.get('query', {}).get('redirects', []):
                    self.redirects[key(redirect['from'])] = key(redirect['to'])
                for page in batch.get('query', {}).get('pages', {}).values():
                    if page.get('revisions'):
                        if 'finalfantasy-wiki' in name:
                            page['_source_site'] = 'finalfantasy.fandom.com'
                            self.pages.setdefault(key(page['title']), page)
                        else:
                            self.pages[key(page['title'])] = page
        self.counter = 0
        self.group_counter = 0
        self.local_names = {}
        self.units = {row['3HriTp6B']: row for row in rows('F_UNIT_MST')}
        self.unit_names = defaultdict(list)
        for row in rows('F_TEXT_UNITS_NAME', text=True):
            self.unit_names[key(row['v'][0])].append(row['key'].rsplit('_', 1)[-1])
        for iid, row in self.units.items():
            self.unit_names[key(row.get('G4L0YIB2', ''))].append(iid)
        self.source_profiles = defaultdict(dict)
        self.source_profiles_by_id = defaultdict(dict)
        self.global_sets = {row['A5x02C6a']: row for row in rows('F_MONSTER_SKILL_SET_MST')}
        self.global_ai = {row['8a6gAwN9'] for row in rows('F_AI_MST')}
        self.skill_rows = {row['6E5u1xrs']: row for row in self.base.load('F_MONSTER_SKILL_MST')}
        self.skill_templates = {kind: next(row for row in self.skill_rows.values()
                                         if row['Isb1GDe2'] == kind and row.get('5w1o9DPV') == '0')
                                for kind in ('1', '2', '3', '4')}
        self.recovered_skills = set()
        self.source_phases, self.source_pools, self.source_groups = defaultdict(list), defaultdict(list), defaultdict(list)
        self.source_mission_names = {row['qo3PECw6']: row['G4L0YIB2'] for row in map(json.loads,
            (ROOT / 'data/memorial_battle_decoded/F_MISSION_MST.ndjson').read_text(encoding='utf8').splitlines())}
        for row in self.base.load('F_MISSION_PHASE_MST'):
            if row.get('gou39JeI') == '2':
                self.source_phases[row['qo3PECw6']].append(row)
        for row in self.base.load('F_BATTLE_LOTTERY_MST'):
            self.source_pools[row['c2gnh6Jd']].append(row)
        for row in self.base.load('F_BATTLE_GROUP_MST'):
            self.source_groups[row['2fY1IomW']].append(row)
        with zipfile.ZipFile(ROOT / 'repository snapshots/aEnigmatic__ffbe-95727376e82d.zip') as source:
            self.raw_skills = json.loads(source.read(next(n for n in source.namelist()
                                                         if n.endswith('/monster_skills.json'))))
        for gist in json.loads((ROOT / 'logs/reference/event-battle-gists-20261026.json').read_text(encoding='utf-8')):
            for filename, file in gist.get('data', {}).get('files', {}).items():
                text = file.get('content', '')
                missions = re.findall(r"# Mission '.*?' \((\d+)\)", text)
                headers = list(re.finditer(r'^# Monster\s+(.+?)\s+\(([\d, ]+)\)\s*$', text, re.M))
                for index, header in enumerate(headers):
                    block = text[header.end():headers[index + 1].start() if index + 1 < len(headers) else len(text)]
                    ids = [v.strip() for v in header[2].split(',')]
                    spec = {'name': header[1], 'part_id': ids[0],
                            'ai': ids[1] if len(ids) > 1 else ids[0],
                            'source': gist['data']['html_url'], 'file': filename,
                            'sha256': hashlib.sha256(text.encode('utf-8')).hexdigest()}
                    for label in ('Level', 'HP', 'MP', 'ATK', 'DEF', 'MAG', 'SPR'):
                        match = re.search(r'^#\s+' + label + r'\s+(\d+)\s*$', block, re.M)
                        if match:
                            spec[label.casefold()] = match[1]
                    actions = re.search(r'^#\s+Actions\s+(\d+)-(\d+)\s*$', block, re.M)
                    if actions:
                        spec['actions'] = actions[1] + ',' + actions[2]
                    element_block = re.search(r'# Element resist(.*?)(?:# Status resist|###)', block, re.S)
                    if element_block:
                        for element in ELEMENTS:
                            match = re.search(r'^#\s+' + element + r'\s+([+-]?\d+)%', element_block[1], re.I | re.M)
                            if match:
                                spec[element] = match[1]
                    status_block = re.search(r'# Status resist[^\n]*(.*?)(?:# Debuff resist|###)', block, re.S)
                    if status_block:
                        for label in AILMENTS:
                            source_label = 'Confusion' if label == 'confuse' else label
                            match = re.search(r'^#\s+' + source_label + r'\s+([+-]?\d+)%', status_block[1], re.I | re.M)
                            if match:
                                spec[label] = match[1]
                    for mid in missions:
                        self.source_profiles[mid][key(header[1])] = spec
                        self.source_profiles_by_id[mid][ids[0]] = spec

    def recover_skills(self, set_id, only_missing=False):
        skill_set = self.global_sets[set_id]
        for sid in skill_set['7qxLC5hP'].split(','):
            if not sid or sid not in self.raw_skills or sid in self.recovered_skills:
                continue
            if only_missing and sid in self.skill_rows:
                continue
            original = self.raw_skills[sid]
            attack_type = {'Physical': '1', 'Magic': '2', 'Hybrid': '3', 'None': '4'}[original['attack_type']]
            template = self.skill_templates[attack_type]
            effects = original['effects_raw']
            row = dict(template, **{
                '6E5u1xrs': sid, 'G4L0YIB2': original['name'], '8cY9hejo': '0',
                'oPD4yL58': '@'.join(str(e[0]) for e in effects),
                'a4hXTIm0': '@'.join(str(e[1]) for e in effects),
                '2kq0BpnD': '@'.join(str(e[2]) for e in effects),
                'PI18xnkD': '@'.join('0' for e in effects),
                'Ha9G5sCS': '@'.join(','.join(str(v) for v in e[3]) for e in effects),
                '7irj9hAb': ','.join(str(int(flag)) for flag in original['flags'])})
            descriptions = str(original.get('effects', '')).casefold()
            row['Jn6BbR2P'] = ','.join('1' if re.search(r'\b' + element + r'\b[^.;]*damage', descriptions) else '0'
                                      for element in ELEMENTS)
            self.skill_rows[sid] = row
            self.recovered_skills.add(sid)

    def page(self, title):
        marker = key(title)
        page = self.pages.get(self.redirects.get(marker, marker))
        if page is None:
            matches = [p for p in self.pages.values() if key(p['title'].rsplit('/', 1)[-1]) == marker]
            if len(matches) == 1:
                page = matches[0]
        return page

    def preserved_formation_record(self, gap, names, title):
        """Retain preserved wave rosters even when their combat profiles are absent."""
        candidates = list(gap.get('candidates', []))
        if (gap['mission'] not in candidates and
                key(self.source_mission_names.get(gap['mission'], '')) in {key(n) for n in names if n}):
            candidates.append(gap['mission'])
        if gap['mission'] in candidates:
            candidates.remove(gap['mission'])
            candidates.insert(0, gap['mission'])
        for source in candidates:
            phases = sorted(self.source_phases[source], key=lambda r: int(r['6v7y3QcJ']))[:gap['waves']]
            formations, native_rosters, donors = [], [], {}
            for phase in phases:
                pool = phase.get('6uIYE15X', '')
                resolved = resolve_pool(self.source_pools[pool], pool)
                slots = self.source_groups[resolved[0]] if resolved else []
                if not slots:
                    break
                formation, native = [], []
                for slot in sorted(slots, key=lambda r: int(r['Z0EN6jSh'])):
                    pid = slot['xqartN26']
                    graphic = self.monsters.get(pid, {}).get('V9j8wJcC') or str(int(pid) // 100)
                    name = self.names.get(pid) or self.dictionary_labels.get(graphic)
                    if not name:
                        break
                    formation.append((name, name))
                    native.append(pid)
                    if pid in self.monsters and self.parts[pid]:
                        donors.setdefault(name, pid)
                else:
                    formations.append(formation)
                    native_rosters.append(native)
                    continue
                break
            else:
                if formations:
                    while len(formations) < gap['waves']:
                        formations.append(formations[-1])
                        native_rosters.append(native_rosters[-1])
                    enemies = list(dict.fromkeys(name for wave in formations for _, name in wave))
                    page = self.page(title)
                    return {'heading': gap['name'], 'names': names,
                        'page': page or {'title': title, 'revisions': [{'revid': None, 'slots': {'main': {'*': ''}}}]},
                        'native_source_only': page is None,
                        'identity_source': 'Preserved named encounter wave rosters; local profiles only where source enemy records are absent',
                        'source_mission': source, 'source_rosters': native_rosters,
                        'native_donor_by_name': donors, 'formations': formations,
                        'fields': {'monster': '<br>'.join('[[' + name + ']]' for name in enemies), 'boss': ''}}
        return None

    def legacy_record(self, mid, names):
        if mid not in LEGACY_POOLS:
            return None
        start, end = LEGACY_POOLS[mid]
        actors = []
        for number in range(start, end + 1):
            iid = str(number)
            name = self.names[iid]
            choices = sorted((pid for pid, label in self.names.items()
                              if label == name and pid in self.global_ai), key=int)
            ai = iid if iid in self.global_ai else choices[0] if choices else '1'
            actors.append({'name': name, 'part_id': iid, 'ai': ai})
        overrides = {}
        for actor in actors:
            overrides.setdefault(actor['name'], actor)
        boss = actors[-1]['name']
        ordinary = list(dict.fromkeys(actor['name'] for actor in actors[:-1]))
        page = self.page('A Frosty Offensive' if start >= 900010154 else 'Halloween - Night of the Pumpkin')
        return {'heading': names[0], 'names': names, 'page': page,
                'identity_source': 'Original Global enemy-ID pool; local wave order/formation reconstruction',
                'native_enemy_overrides': overrides, 'native_actor_profiles': actors,
                'normal_formation_size': 2,
                'fields': {'monster': '<br>'.join('[[' + name + ']]' for name in ordinary),
                           'boss': '[[' + boss + ']]'}}

    @staticmethod
    def text(page):
        return re.sub(r'<!--.*?-->', '', page['revisions'][0]['slots']['main']['*'], flags=re.S)

    def records(self, title):
        result = []
        parent = self.page(title)
        prefix = parent['title'] if parent else title
        accepted = [p for p in self.pages.values()
                    if p['title'].startswith(prefix + '/') or
                    (prefix == 'Chamber of the Vengeful' and p['title'].startswith(prefix + ' - ')) or p is parent]
        for page in accepted:
            text = self.text(page)
            common_bosses = {plain(fields(block).get('name', ''))
                             for _, block in templates(text, 'Boss Infobox')} - {''}
            for position, block in templates(text, 'Battle Infobox'):
                stack = []
                for match in re.finditer(r'(?m)^(={2,6})\s*([^=\n]+?)\s*\1\s*$', text[:position]):
                    depth = len(match[1])
                    while stack and stack[-1][0] >= depth:
                        stack.pop()
                    stack.append((depth, match[2]))
                headings = [heading for _, heading in stack]
                variants = [' - '.join(headings[-count:]) for count in range(1, min(3, len(headings)) + 1)]
                variants.extend(page['title'] + ' - ' + heading for heading in headings[-3:])
                tabs = re.findall(r'(?:<tabber>|\|-\|)\s*([^=\n]+)=', text[:position])
                if tabs:
                    tab = tabs[-1].strip()
                    variants.append(tab)
                    variants.extend(heading + ' - ' + tab for heading in headings[-3:])
                    level = re.search(r'\b(?:Lv|Lvl|Level)\.?\s*(\d+)\b', tab, re.I)
                    if level:
                        variants.extend(heading + ' - Lvl ' + level[1] for heading in headings[-3:])
                battle_fields = fields(block)
                if len(common_bosses) == 1 and not linked_enemies(battle_fields.get('monster', '') + battle_fields.get('boss', '')):
                    battle_fields['boss'] = '[[' + next(iter(common_bosses)) + ']]'
                result.append({'heading': headings[-1] if headings else page['title'].rsplit('/', 1)[-1],
                               'names': variants,
                               'fields': battle_fields, 'page': page})
            floor_section = text.split('== Floor Composition ==', 1)
            if len(floor_section) == 2:
                for match in re.finditer(r'^\|\s*(\d+)F\s*\|\|\s*([^\n]+)\n\|\s*([\d,]+)\s*\|\|\s*([^\n]+)', floor_section[1], re.M):
                    floor, enemies, gil, remaining = match.groups()
                    alternatives = [linked_enemies(part) for part in re.split(r'(?:<br\s*/?>)+', enemies, flags=re.I)]
                    alternatives = [formation for formation in alternatives if formation]
                    heading = title + ' - Floor ' + floor
                    result.append({'heading': heading, 'names': [heading], 'page': page,
                                   'formations': alternatives,
                                   'fields': {'monster': enemies, 'boss': '', 'gil': gil,
                                              'unit-exp': remaining.split('||')[0].strip()}})
        return result

    def select(self, records, names, waves, campaign='', mission='', original=None):
        trial_names = {key(re.sub(r'\s*[-:]\s*(?:BGN|INT|ADV|PRO|ELT|LGD|EXT|SVG)\s*$', '', name)) for name in names}
        trial_matches = [r for r in records if key(r['page']['title'].rsplit(' - ', 1)[-1]) in trial_names]
        if trial_matches:
            records = trial_matches
        page_matches = [r for r in records if key(r['page']['title']) in {key(n) for n in names}]
        if page_matches:
            records = page_matches
        matching = [r for r in records if {key(n) for n in r['names']} & {key(n) for n in names}]
        if len(matching) == 1:
            return matching[0]
        matching = [r for r in records if any(key(variant).endswith(key(name))
                    for variant in r['names'] for name in names if len(key(name)) >= 8)]
        if len(matching) == 1:
            return matching[0]
        targets = set()
        for challenge in (original or {}).get('challenges', []):
            for description in challenge.get('parsed', []):
                match = re.match(r'Defeat\s+(?:(?:an?|the)\s+)?(.+?)\s+with\b', description, re.I)
                if match:
                    targets.add(key(match[1]))
        matching = [r for r in records if any(key(enemy) in targets
                    for _, enemy in linked_enemies(r['fields'].get('boss', '')))]
        if len(matching) == 1:
            return matching[0]
        species_matches = [r for r in records if any(
            len(key(enemy)) >= 5 and key(enemy) in key(name)
            for _, enemy in linked_enemies(r['fields'].get('boss', '')) for name in names)]
        if species_matches:
            records = species_matches
        dated_base = {key(re.sub(r'\s*\((?:Daily|[^)]*\d[^)]*)\)\s*$', '', name, flags=re.I))
                      for name in names if name}
        dated_matches = [r for r in records if any(
            len(base) >= 10 and key(r['heading']).startswith(base) for base in dated_base)]
        if dated_matches:
            records = dated_matches
        stages = {m[1] for name in names if (m := re.search(r'\b(BGN|INT|ADV|PRO|ELT|LGD|EXT|SVG)\s*$', name))}
        matching = [r for r in records if (m := re.search(r'\b(BGN|INT|ADV|PRO|ELT|LGD|EXT|SVG)\s*$', r['heading'])) and m[1] in stages]
        if len(matching) == 1:
            return matching[0]
        if len(records) == 1:
            return records[0]
        if original and original.get('cost_type') == 'NRG':
            matching = [r for r in records if numeric(r['fields'].get('battle', '')) == waves and
                        numeric(r['fields'].get('energy', '')) == original.get('cost')]
            if len(matching) == 1:
                return matching[0]
        # Some original Global names retain the former ELT label after the
        # campaign's highest difficulty was renamed LGD in the English text.
        if stages == {'LGD'} and not any('LGD' in r['heading'] for r in records):
            matching = [r for r in records if re.search(r'\bELT\s*$', r['heading'])]
            if len(matching) == 1:
                return matching[0]
        if any('daily' in name.casefold() for name in names):
            matching = [r for r in records if 'daily' in r['heading'].casefold()]
            if len(matching) == 1:
                return matching[0]
        if campaign == 'Vault of Hidden Treasures (1 Year Anniversary Dungeon)' and records:
            # The original daily server rotation was not retained. Keep the
            # documented anniversary rosters in a deterministic local rotation.
            return records[int(mission) % len(records)]
        rosters = {(tuple(linked_enemies(r['fields'].get('monster', ''))),
                    tuple(linked_enemies(r['fields'].get('boss', '')))) for r in records}
        if len(rosters) == 1 and any(roster[0] or roster[1] for roster in rosters):
            # Dated daily pages repeat the same documented enemy encounter.
            # Rewards and unlock dates continue to come from each Global row.
            return records[0]
        return None

    def enemy(self, title, name, record, mission_names, campaign, mission_id):
        page = self.page(title)
        event_page = record['page']
        event_text = self.text(event_page)
        def boss_specs(text):
            result = []
            for pos, block in templates(text, 'Boss Infobox'):
                spec = fields(block)
                tabs = re.findall(r'(?:<tabber>|\|-\|)\s*([^=\n]+)=', text[:pos])
                spec['_variant'] = tabs[-1].strip() if tabs else ''
                result.append(spec)
            return result
        specs = boss_specs(event_text)
        parent = self.page(campaign)
        if parent is not None and parent is not event_page:
            specs.extend(boss_specs(self.text(parent)))
        exact = [s for s in specs if key(s.get('name', '')) == key(name)]
        if len(exact) > 1:
            daily = 'daily' in record['heading'].casefold() or 'empowered' in title.casefold()
            variants = [s for s in exact if ('daily' in s['_variant'].casefold()) == daily]
            if len(variants) == 1:
                exact = variants
        spec = exact[0] if len(exact) == 1 else {}
        if record.get('season_scoped'):
            spec = dict(record.get('published_profiles', {}).get(key(name), spec))
        source_profile = (record.get('profile_override') or record.get('profile_overrides', {}).get(key(name))
                          or self.source_profiles.get(mission_id, {}).get(key(name)))
        if source_profile:
            spec = dict(spec, **source_profile)
        enemy_text = self.text(page) if page else ''
        boxes = [fields(b) for _, b in templates(enemy_text, 'Monster Infobox')]
        number = spec.get('no') or (boxes[0].get('no') or boxes[0].get('number') if boxes else '')
        dictionary = self.dictionary.get(str(numeric(number)))
        dictionary_name = {'Newborn Celestial Fry': 'Celestial Fry', 'Young Celestial Fry': 'Celestial Fry',
                           'Faulty Celestial Fry': 'Celestial Fry', 'Ghoul Hard': 'Ghoul'}.get(name, name)
        if dictionary is None and self.dictionary_by_name[key(dictionary_name)]:
            dictionary = min(self.dictionary_by_name[key(dictionary_name)], key=lambda r: int(r['Z0EN6jSh']))
        if not spec and dictionary:
            matching = [s for s in specs if str(numeric(s.get('no', ''))) == dictionary['Z0EN6jSh']]
            if len(matching) == 1:
                spec = matching[0]
        unit_ids = [iid for iid in self.unit_names[key(name)] if iid in self.units]
        # Prefer an original base form, rather than a numerically higher shift.
        base_ids = [iid for iid in unit_ids if int(iid) % 100 < 10]
        unit = self.units[min(base_ids or unit_ids, key=int)] if unit_ids else None
        candidates = self.by_name[key(name)]
        if dictionary:
            candidates = self.by_graphic[dictionary['V9j8wJcC']] or candidates
        has_model_profile = bool(candidates)
        model_basis = 'Preserved same-model profile'
        if not candidates and dictionary:
            races = set(dictionary.get('a9qg8vnP', '').split(','))
            candidates = [iid for iid in self.monsters if iid in self.parts and
                          races.intersection(self.parts[iid][0].get('a9qg8vnP', '').split(',')) and
                          not self.parts[iid][0].get('3HriTp6B', '0').strip('0')]
            model_basis = 'Original Global dictionary graphic with a preserved same-race combat profile'
        if unit is not None and dictionary and int(dictionary['V9j8wJcC']) in range(10000000, 20000000) and not has_model_profile:
            candidates = ['205771000']
            model_basis = 'Original Global unit animation with preserved unit-model enemy combat profile'
        if not candidates:
            raise ValueError('Original model/profile unavailable: ' + name)
        hp, mp, level = numeric(spec.get('hp', '')), numeric(spec.get('mp', '')), numeric(spec.get('level', ''))
        # Monster pages often publish separate HP/MP for each campaign tier.
        stat_rows = []
        stages = {m[1] for n in mission_names if (m := re.search(r'\b(BGN|INT|ADV|PRO|ELT|LGD|EXT|SVG)\s*$', n))}
        for block in re.split(r'\n\|-.*?\n', enemy_text):
            values = re.search(r'\n\|\s*([\d,]+)\s*\|\|\s*([\d,]+)\s*\|\|\s*([\d,]+)', block)
            contexts = {key(campaign), key(event_page['title'].split('/')[0])}
            if values and any(context and context in key(block[:values.start()]) for context in contexts):
                matching_stage = any(re.search(r'\b' + stage + r'\b', block[:values.start()]) for stage in stages)
                stat_rows.append((matching_stage, tuple(int(v.replace(',', '')) for v in values.groups())))
        exact_stats = [stats for matched, stats in stat_rows if matched]
        if len(exact_stats) == 1 and not source_profile:
            level, hp, mp = exact_stats[0]
        elif len(stat_rows) == 1 and not source_profile:
            level, hp, mp = stat_rows[0][1]
        target_level = level or max(1, min(99, numeric(record['fields'].get('difficulty', '')) or
                                           record.get('original_difficulty') or 1))
        donor = min(candidates, key=lambda iid: (abs(int(self.parts[iid][0].get('7wV3QZ80') or 1) - target_level), int(iid)))
        donor = record.get('native_donor_by_name', {}).get(name, donor)
        donor_unit = self.parts[donor][0].get('3HriTp6B')
        repair_unit = bool(unit and donor_unit and donor_unit != '0' and donor_unit not in self.units)
        if repair_unit:
            same_form = [iid for iid in unit_ids if iid[-2:] == donor_unit[-2:]]
            if same_form:
                unit = self.units[min(same_form, key=int)]
            model_basis = 'Original Global unit animation with preserved same-model enemy combat profile'
        self.counter += 1
        native_override = record.get('native_enemy_overrides', {}).get(name)
        local_id = source_profile['part_id'] if source_profile else (native_override['part_id'] if native_override else str(1800000000 + self.counter))
        if (record.get('retain_native_identity') and not (source_profile or native_override)
                and self.names.get(donor) == name):
            local_id = donor
        if native_override and self.names.get(local_id) != name:
            raise ValueError('Reconstructed enemy does not match its original Global identity')
        if not (source_profile or native_override or record.get('retain_native_identity')) and (local_id in self.monsters or local_id in self.names):
            raise ValueError('Local identity collision')
        monster = dict(self.monsters[donor], xqartN26=local_id, G4L0YIB2=name)
        if dictionary:
            monster['V9j8wJcC'] = dictionary['V9j8wJcC']
        profiles = []
        for original in sorted(self.parts[donor], key=lambda r: int(r['6Yc4RkdM'])):
            row = copy.deepcopy(original)
            row.update(xqartN26=local_id, G4L0YIB2=name,
                       **{'e56NZY42': '0', '7UR4J2SE': '0',
                          'ATM35pjf': '0', '9BetM2Ds': '', 'm28pD1GM': ''})
            if dictionary:
                row['a9qg8vnP'] = dictionary['a9qg8vnP']
            if source_profile and source_profile.get('actions'):
                row['4Y2DGP7m'] = source_profile['actions']
            if unit is not None and model_basis.startswith('Original Global unit'):
                row['3HriTp6B'] = unit['3HriTp6B']
                for token in ('5A8SmwyC', 'a9DvZ70c', '7KYufEd5', 'w04FtZqB', 'rtw4F6hn', 'rB70Ls63'):
                    row[token] = unit[token]
            if source_profile and source_profile['ai'] in self.global_ai:
                row['8a6gAwN9'] = source_profile['ai']
                set_id = next((iid for iid in (source_profile['ai'], source_profile['part_id'])
                               if iid in self.global_sets), None)
                if set_id:
                    row['A5x02C6a'] = set_id
                    self.recover_skills(set_id)
                else:
                    row['A5x02C6a'] = '0'
            if native_override:
                ai = native_override['ai']
                if ai not in self.global_ai:
                    raise ValueError('Original Global AI reference is absent: ' + ai)
                row['8a6gAwN9'] = ai
                if not record.get('retain_native_identity'):
                    row['4Y2DGP7m'] = '1,1'
                row['A5x02C6a'] = ai if ai in self.global_sets else '0'
                if ai in self.global_sets:
                    self.recover_skills(ai)
            if row.get('8a6gAwN9') not in self.global_ai and row.get('8a6gAwN9') not in ('', '0'):
                global_donors = [p for iid in self.by_graphic[monster['V9j8wJcC']] for p in self.parts[iid]
                                 if p.get('8a6gAwN9') in self.global_ai]
                row['8a6gAwN9'] = (min(global_donors, key=lambda p: abs(int(p.get('7wV3QZ80') or 1) - target_level))
                                     ['8a6gAwN9'] if global_donors else '116')
            # Only a single-body published infobox can replace the body stats.
            # Multipart profiles keep their original limb statistics.
            if len(self.parts[donor]) == 1:
                for token, value in (('fh31sk7B', hp), ('PC97pWQj', mp), ('7wV3QZ80', level)):
                    if value is not None:
                        row[token] = str(value)
                for field, token in zip(('atk', 'def', 'mag', 'spr'), STATS):
                    value = numeric(spec.get(field, ''))
                    if value is not None:
                        row[token] = str(value)
            for token, elements in (('hn42BL3Q', ELEMENTS), ('D9Nb7jgd', AILMENTS)):
                vector = row[token].split(',')
                for i, element in enumerate(elements):
                    raw = spec.get(element, '')
                    value = 100 if raw.casefold() == 'null' else numeric(raw)
                    if value is not None and i < len(vector):
                        vector[i] = str(value)
                row[token] = ','.join(vector)
            profiles.append(row)
            self.local_names[local_id + chr(64 + int(row['6Yc4RkdM']))] = name
        self.local_names[local_id] = name
        return monster, profiles, {'enemy': name, 'donor': donor, 'dictionary': monster['V9j8wJcC'],
            'wiki': page['title'] if page else event_page['title'],
            'published_stats': {'level': level, 'hp': hp, 'mp': mp},
            'original_datamine': source_profile,
            'local_roster_native_references': native_override,
            'unpublished_values': model_basis + ' and AI; no claim of original Global server stats'}

    def bundle(self, mid, mission, record, names, campaign):
        info = record['fields']
        ordinary = linked_enemies(info.get('monster', ''))
        bosses = linked_enemies(info.get('boss', ''))
        if not ordinary and not bosses:
            raise ValueError('No documented enemy roster')
        waves = int(mission['8xi6Xvyk'])
        lineup = list(dict.fromkeys(ordinary + bosses))
        monsters, profiles, provenance, ids = [], [], [], {}
        for title, name in lineup:
            monster, parts, basis = self.enemy(title, name, record, names, campaign, mid)
            monsters.append(monster); profiles.extend(parts); provenance.append(basis)
            ids[(title, name)] = monster['xqartN26']
        phases, lotteries, groups = [], [], []
        for wave in range(1, waves + 1):
            self.group_counter += 1
            gid = str(1700000000 + self.group_counter)
            foes = bosses if wave == waves and bosses else ordinary or bosses
            # Original server formation lotteries are absent. Cycle documented
            # species through normal waves; retain the documented boss lineup.
            foes = foes[:5] if wave == waves and bosses else [foes[(wave - 1) % len(foes)]]
            if record.get('normal_formation_size') and not (wave == waves and bosses):
                pool = ordinary or bosses
                count = record['normal_formation_size']
                foes = [pool[((wave - 1) * count + slot) % len(pool)] for slot in range(min(count, len(pool)))]
            if record.get('formations'):
                foes = record['formations'][(wave - 1) % len(record['formations'])]
            background = mission.get('DYTx1Is3', '0')
            phases.append({'qo3PECw6': mid, '6v7y3QcJ': str(wave), 'gou39JeI': '2',
                           '6uIYE15X': gid, 'DYTx1Is3': background if background not in ('', '0') else '100022',
                           'YS9kfCX7': mission.get('6w4xiIsS', '0')})
            lotteries.append({'c2gnh6Jd': gid, 'ixDq7yJ8': '1', '2fY1IomW': gid})
            for slot, foe in enumerate(foes, 1):
                groups.append({'2fY1IomW': gid, 'xqartN26': ids[foe], 'MxLFKZ13': f'{170 if slot % 2 else 100},{250 + 60 * slot}',
                               'Z0EN6jSh': str(slot), '3t7pZM5V': '2', 'WJdBp9f0': '1', 'm9BvFk2X': '1'})
        frequency = defaultdict(int)
        for group in groups:
            frequency[group['xqartN26']] += 1
        bodies = [row for row in profiles if row['6Yc4RkdM'] == '1']
        count = sum(frequency[row['xqartN26']] for row in bodies)
        for token, total in (('B6H34Mea', numeric(info.get('unit-exp', ''))),
                             ('7UR4J2SE', numeric(mission.get('7UR4J2SE', '')))):
            if total is not None and count:
                share, remainder = divmod(total, count)
                for row in bodies:
                    row[token] = str(share)
                single = next((row for row in bodies if frequency[row['xqartN26']] == 1), None)
                if single is not None:
                    single[token] = str(share + remainder)
        for profile in profiles:
            set_id = profile.get('A5x02C6a')
            if set_id in self.global_sets:
                self.recover_skills(set_id, only_missing=True)
        tables = {'F_MISSION_PHASE_MST': phases, 'F_BATTLE_LOTTERY_MST': lotteries,
                  'F_BATTLE_GROUP_MST': groups, 'F_MONSTER_MST': monsters,
                  'F_MONSTER_PARTS_MST': profiles,
                  'F_MONSTER_SKILL_SET_MST': self.base.load('F_MONSTER_SKILL_SET_MST') + list(self.global_sets.values()),
                  'F_MONSTER_SKILL_MST': list(self.skill_rows.values())}
        bundle = derive_mission(mid, ReconstructionSource(self.base, tables))
        # Original AI can summon adds that are absent from the initial roster.
        # Send their profiles and skills without placing them in the opening wave.
        present = {row['xqartN26'] for row in bundle['wbet57nF']}
        for source in self.source_profiles_by_id.get(mid, {}).values():
            if source['part_id'] in present:
                continue
            extra_record = dict(record, profile_override=source)
            monster, extra_parts, basis = self.enemy(source['name'], source['name'], extra_record, names, campaign, mid)
            bundle['wbet57nF'].append(monster)
            bundle['bV34YIJQ'].extend({token: part.get(token, PARTS_DEFAULTS.get(token, ''))
                                       for token in PARTS_TOKENS} for part in extra_parts)
            present.add(source['part_id'])
            provenance.append(basis)
        for actor in record.get('native_actor_profiles', []):
            if actor['part_id'] in present:
                continue
            extra_record = dict(record, native_enemy_overrides={actor['name']: actor})
            monster, extra_parts, basis = self.enemy(actor['name'], actor['name'], extra_record, names, campaign, mid)
            bundle['wbet57nF'].append(monster)
            bundle['bV34YIJQ'].extend({token: part.get(token, PARTS_DEFAULTS.get(token, ''))
                                       for token in PARTS_TOKENS} for part in extra_parts)
            present.add(actor['part_id'])
            provenance.append(basis)
        wanted = {sid for part in bundle['bV34YIJQ']
                  for sid in self.global_sets.get(part.get('A5x02C6a'), {}).get('7qxLC5hP', '').split(',') if sid}
        skills = {row['6E5u1xrs']: row for row in bundle['Wp39QX52']}
        skills.update({sid: self.skill_rows[sid] for sid in wanted if sid in self.skill_rows})
        bundle['Wp39QX52'] = list(skills.values())
        bundle['1IfDqR4n'] = [mission]
        return bundle, provenance


def main():
    reconstructor = Reconstruction()
    missions = {row['qo3PECw6']: row for row in rows('F_MISSION_MST')}
    with zipfile.ZipFile(ROOT / 'repository snapshots/aEnigmatic__ffbe-95727376e82d.zip') as source:
        original = json.loads(source.read(next(n for n in source.namelist() if n.endswith('/missions.json'))))
    gaps = json.loads((ROOT / 'source/build/event-battle-source-gaps-20261026.json').read_text(encoding='utf-8'))
    authored = json.loads((ROOT / 'source/server/responses.json').read_text(encoding='utf-8'))
    area_names = {r['key'].rsplit('_', 1)[-1]: r['v'][0] for r in rows('F_TEXT_AREA_NAME', text=True)}
    records, encounters, missing = {}, {}, []
    for gap in gaps:
        mid = gap['mission']
        if 'jnw49dUq@' + mid in authored:
            continue
        title = unquote(gap['page'].split('/wiki/')[-1]).replace('_', ' ')
        if gap.get('subtype') == '50':
            title = gap['name']
        elif gap.get('subtype') == '12' and area_names.get(gap['area']) != 'Dark Visions':
            title = area_names.get(gap['area'], title)
        if title not in records:
            records[title] = reconstructor.records(title)
        names = [gap['name'], original.get(mid, {}).get('name', ''), missions[mid].get('G4L0YIB2', '')]
        previous = original.get(str(int(mid) - 1), {}).get('name', '')
        lower = re.sub(r'\s+Lvl\.?\s*1\s*$', '', previous, flags=re.I)
        if previous != lower and key(lower) == key(original.get(mid, {}).get('name', '')):
            names.append(lower + ' Lvl. 2')
        own_records = records[title]
        record = reconstructor.select(own_records, names, gap['waves'], title, mid, original.get(mid))
        if record is None and gap.get('subtype') == '12' and 'Domain of' in gap['name']:
            # Identify the season by its unique final-stage title, then read
            # the published Battle Info row by attack type and weaknesses.
            season_names = [original.get(i, {}).get('name', '') for i, r in missions.items()
                            if r['uv60hgDW'] == gap['area']]
            markers = [n for n in season_names if 'Domain of' not in n and len(key(n)) >= 10]
            markers = [{'A Dance on Shadowed Strings': 'A Dance of Shadowed Strings'}.get(n, n) for n in markers]
            pages = [p for p in reconstructor.pages.values() if p['title'].startswith('Dark Visions - The Advent of Chaos')
                     and any(key(n) in key(reconstructor.text(p)) for n in markers)]
            if len(pages) == 1:
                page = pages[0]
                prefix, elements = gap['name'].rsplit('Domain of ', 1)
                elements = re.sub(r'\s+\d+$', '', elements)
                wanted = {key(e.strip().replace('Darkness', 'Dark')) for e in re.split(r',|\band\b', elements) if e.strip()}
                kind = 'P/M' if 'Physical' in prefix and 'Magical' in prefix else 'P' if 'Physical' in prefix else 'M'
                bosses = set()
                for line in reconstructor.text(page).splitlines():
                    cells = line.lstrip('| ').split('||')
                    if len(cells) < 5 or cells[2].strip() != kind:
                        continue
                    weakness = {key(e) for e in re.findall(r'\{\{Icon\|([^}|]+)', cells[3], re.I)}
                    if weakness == wanted:
                        bosses.add(plain(cells[4]).split(' [', 1)[0].strip())
                if len(bosses) == 1:
                    record = {'heading': gap['name'], 'names': names, 'page': page,
                              'identity_source': 'Original Global season final-stage identity and wiki Battle Info attack/weakness row',
                              'fields': {'monster': '', 'boss': '[[' + next(iter(bosses)) + ']]'}}
        if record is None and gap.get('subtype') == '50':
            page = reconstructor.page(title)
            bosses = list(dict.fromkeys(plain(fields(block).get('name', ''))
                          for _, block in templates(reconstructor.text(page), 'Boss Infobox'))) if page else []
            bosses = [name for name in bosses if name]
            if bosses:
                record = {'heading': gap['name'], 'names': names, 'page': page,
                          'identity_source': 'Original Clash of Wills boss infoboxes and published stats; local echelon formation',
                          'fields': {'monster': '', 'boss': ','.join('[[' + name + ']]' for name in bosses)}}
        if record is None:
            # Chamber index pages link named trials as separate wiki pages.
            # A trial's own name is stronger evidence than its numeric ID.
            trial_names = {re.sub(r'\s*[-:]\s*(?:BGN|INT|ADV|PRO|ELT|LGD|EXT|SVG)\s*$', '', name)
                           for name in names if name}
            trial_names.update(name.split(': ', 1)[1] for name in list(trial_names) if ': ' in name)
            for trial in sorted(trial_names):
                trial_records = reconstructor.records(trial)
                record = reconstructor.select(trial_records, names, gap['waves'], trial, mid, original.get(mid))
                if record is not None:
                    break
        if record is None:
            # Chronicle and Series Boss pages can omit their battle infoboxes.
            # An exact original mission/monster-name match still establishes
            # the boss identity without guessing from a reused numeric ID.
            for name in names[:2]:
                boss = re.sub(r'\s+(?:Lv|Lvl|Level)\.?\s*\d+\s*$', '', name, flags=re.I)
                boss = re.sub(r'\s*[-:]\s*(?:BGN|INT|ADV|PRO|ELT|LGD|EXT|SVG)\s*$', '', boss)
                if (reconstructor.by_name[key(boss)] or reconstructor.dictionary_by_name[key(boss)]):
                    page = reconstructor.page(title)
                    if page is not None:
                        record = {'heading': name, 'names': [name], 'page': page,
                                  'identity_source': 'Exact original Global mission and monster master names',
                                  'fields': {'monster': '', 'boss': '[[' + boss + ']]'}}
                        break
        if record is None and missions[mid].get('G4L0YIB2', '').endswith(('EX', 'EX+')):
            levels = [(int(match[1]), candidate) for candidate in own_records
                      if (match := re.search(r'\b(?:Lv|Lvl|Level)\.?\s*(\d+)\b', candidate['heading'], re.I))]
            if levels:
                record = dict(max(levels, key=lambda pair: pair[0])[1],
                              identity_source='Same original campaign roster; local EX tier counterpart from its highest documented stage')
        if record is None and title == 'Fundamental Forces: Dragon Arc':
            enemy, part_id, ai = DRAGON_ARC_BOSSES.get(mid, ('Draconaught Warrior', '900011194', '1'))
            record = {'heading': gap['name'], 'names': names, 'page': reconstructor.page(title),
                      'identity_source': 'Local wave reconstruction from the original campaign enemy set, wiki monster pages and Global AI/text masters',
                      'native_enemy_overrides': {enemy: {'part_id': part_id, 'ai': ai}},
                      'fields': {'monster': '' if mid in DRAGON_ARC_BOSSES else '[[' + enemy + ']]',
                                 'boss': '[[' + enemy + ']]' if mid in DRAGON_ARC_BOSSES else ''}}
        if mid in LEGACY_POOLS:
            record = reconstructor.legacy_record(mid, names)
        if record is None:
            record = reconstructor.preserved_formation_record(gap, names, title)
        if record is None and any(name.startswith('Dangerous Woman Tour - ') for name in names):
            # The archived page omits two stages. Use its closest documented
            # same-campaign cost tier while retaining the original quest row.
            cost = original.get(mid, {}).get('cost', 0)
            candidates = [candidate for candidate in reconstructor.records('Dangerous Woman Tour')
                          if linked_enemies(candidate['fields'].get('monster', '') + candidate['fields'].get('boss', ''))]
            if candidates:
                counterpart = min(candidates, key=lambda candidate: abs((numeric(candidate['fields'].get('energy', '')) or 0) - cost))
                record = dict(counterpart, identity_source='Local same-campaign counterpart for an omitted archived stage')
        try:
            if record is None:
                raise ValueError('Unique documented battle not identified')
            record = dict(record, original_difficulty=original.get(mid, {}).get('difficulty', 1))
            bundle, provenance = reconstructor.bundle(mid, missions[mid], record, names, title)
            encounters[mid] = {'bundle': bundle, 'enemies': provenance,
                'identity_source': record.get('identity_source', 'Original wiki campaign battle roster'),
                'source_page': record['page']['title'], 'source_revision': record['page']['revisions'][0]['revid']}
            if record.get('source_rosters'):
                encounters[mid]['preserved_formation_source'] = {
                    'mission': record['source_mission'], 'enemy_ids_by_wave': record['source_rosters']}
            encounters[mid]['source_url'] = ('https://' + record['page'].get('_source_site', 'exvius.fandom.com') +
                                             '/wiki/' + quote(record['page']['title'].replace(' ', '_')))
            if record.get('native_source_only'):
                encounters[mid]['source_url'] = 'data/memorial_battle_decoded/F_BATTLE_GROUP_MST.ndjson'
            if len(encounters) % 100 == 0:
                print('Assembled', len(encounters), 'documented encounters', flush=True)
        except (ValueError, SystemExit) as exc:
            missing.append(dict(gap, reason=str(exc)))
    used = {row['xqartN26'] for entry in encounters.values() for row in entry['bundle']['wbet57nF']}
    used_names = {iid: name for iid, name in reconstructor.local_names.items()
                  if iid in used or (iid[-1:].isalpha() and iid[:-1] in used)}
    document = {'version': 1,
        'provenance': 'User-approved event reconstruction. Original wiki rosters and published stats; locally reconstructed formations and preserved same-model profiles for unpublished stats/AI.',
        'missions': encounters, 'local_monster_names': used_names}
    (ROOT / 'source/server/event_encounters.json').write_text(json.dumps(document, ensure_ascii=False, separators=(',', ':')) + '\n', encoding='utf-8')
    (ROOT / 'source/build/event-reconstruction-gaps-20261026.json').write_text(json.dumps(missing, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    print('Reconstructed documented Global encounters:', len(encounters), '; unresolved:', len(missing))


if __name__ == '__main__':
    main()
