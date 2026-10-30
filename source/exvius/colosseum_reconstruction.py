"""Build the user-approved local Advanced rounds from original enemy identities."""
from collections import defaultdict
import copy
import hashlib
import json
import math
from pathlib import Path
import re
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[2]
REFERENCE = ROOT / 'logs/reference/colosseum/advanced-enemies-wiki.json'
ELEMENTS = ('fire', 'ice', 'lightning', 'water', 'wind', 'earth', 'light', 'dark')
AILMENTS = ('poison', 'blind', 'sleep', 'silence', 'paralyze', 'confuse', 'disease', 'petrify')
STATS = ('9NBV1XCS', 'Pn5w9dfh', '84FJM3PD', 'T8xMDAZ4')


def normalized(text):
    return re.sub('[^a-z0-9]', '', str(text).lower())


def wiki_stats(text, round_name):
    """Keep separate body and limb rows when a page has a multipart enemy."""
    found = []
    for row in re.split(r'\n\|-\s*\n', text):
        if not re.search(r'\bAdvanced\s+' + re.escape(round_name) + r'\b', row, re.I):
            continue
        match = re.search(r'\n\|\s*([\d,]+)\s*\|\|\s*([\d,]+)\s*\|\|\s*([\d,]+)', row)
        if match:
            found.append(dict(zip(('level', 'hp', 'mp'),
                                  (int(value.replace(',', '')) for value in match.groups()))))
    return found


def resistance(text, round_name):
    templates = list(re.finditer(r'\{\{Resistance Infobox\b(.*?)\n\}\}', text, re.S | re.I))
    if not templates:
        return {}, 'known donor resistances'
    headings = list(re.finditer(r'(?m)^=+\s*([^=\n]+?)\s*=+\s*$', text))
    ranked = []
    target = normalized(round_name)
    for template in templates:
        previous = [h.group(1) for h in headings if h.end() < template.start()]
        heading = normalized(previous[-1]) if previous else ''
        exact = ('adv' + target in heading or 'advanced' + target in heading)
        common = 'colosseum' in heading and not re.search(r'[dcbas][1-5]', heading)
        ranked.append((2 if exact else 1 if common else 0, template))
    priority, chosen = max(ranked, key=lambda pair: pair[0])
    # An unrelated encounter-specific template must not replace known data.
    if priority == 0:
        chosen = templates[0]
    values = {}
    for field, raw in re.findall(r'\|\s*(\w+)\s*=([^\n]*)', chosen.group(1)):
        raw = raw.strip().lower()
        if not raw:
            values[field.lower()] = 0
        elif raw == 'null':
            values[field.lower()] = 100
        elif re.fullmatch(r'[+-]?\d+%?', raw):
            values[field.lower()] = int(raw.rstrip('%'))
    return values, 'wiki exact round' if priority == 2 else 'wiki common/default'


class Reconstructor:
    def __init__(self, base, original_groups):
        pages = json.loads(REFERENCE.read_text(encoding='utf8'))['pages']
        self.pages = {normalized(page['title']): page for page in pages}
        for page in pages:
            if hashlib.sha256(page['wikitext'].encode('utf8')).hexdigest() != page['sha256']:
                raise ValueError('Original wiki reference checksum mismatch: ' + page['title'])
        names = {row['key'].rsplit('_', 1)[-1]: row['v'][0] for row in
                 map(json.loads, (ROOT / 'data/text_decoded/F_TEXT_MONSTER_NAME.ndjson').read_text(encoding='utf8').splitlines())}
        self.name_ids = set(names)
        self.monsters = {row['xqartN26']: row for row in base.load('F_MONSTER_MST')}
        self.parts = defaultdict(list)
        for row in base.load('F_MONSTER_PARTS_MST'):
            self.parts[row['xqartN26']].append(row)
        for rows in self.parts.values():
            rows.sort(key=lambda row: int(row['6Yc4RkdM']))
        self.candidates = defaultdict(list)
        for iid in self.parts:
            if iid in self.monsters and names.get(iid):
                self.candidates[normalized(names[iid])].append(iid)
        self.colosseum_parts = {row['xqartN26'] for rows in original_groups for row in rows}
        self.formations = {}
        for rows in sorted(original_groups, key=lambda rows: int(rows[0]['2fY1IomW'])):
            self.formations.setdefault(len(rows), sorted(rows, key=lambda row: int(row['Z0EN6jSh'])))

    def enemy(self, name, round_name, local_id, expected_level):
        if local_id in self.monsters or local_id in self.name_ids:
            raise ValueError('Local monster ID collides with an original: ' + local_id)
        page = self.pages[normalized(name)]
        stats = wiki_stats(page['wikitext'], round_name)
        candidates = self.candidates[normalized(name)]
        if not candidates:
            raise ValueError('No original model for ' + name)
        target_level = stats[0]['level'] if stats else expected_level
        donor = min(candidates, key=lambda iid: (
            iid not in self.colosseum_parts,
            abs(int(self.parts[iid][0]['7wV3QZ80']) - target_level), int(iid)))
        source_parts = self.parts[donor]
        if stats and len(stats) not in (1, len(source_parts), 2):
            raise ValueError('Unresolved multipart wiki statistics: ' + name)
        resists, resist_basis = resistance(page['wikitext'], round_name)
        rows = []
        for number, original in enumerate(source_parts):
            row = copy.deepcopy(original)
            source_level = max(1, int(original['7wV3QZ80']))
            values = stats[min(number, len(stats) - 1)] if stats else {
                'level': target_level,
                'hp': max(1, math.ceil(int(original['fh31sk7B']) * target_level / source_level)),
                'mp': int(original['PC97pWQj'])}
            ratio = max(.5, min(2, values['level'] / source_level))
            for token in STATS:
                row[token] = str(max(1, math.ceil(int(original[token]) * ratio)))
            row.update(xqartN26=local_id, G4L0YIB2=name + (' Tentacle' if number and name == 'Architeuth' else ''),
                       fh31sk7B=str(values['hp']), PC97pWQj=str(values['mp']),
                       **{'7wV3QZ80': str(values['level']), 'B6H34Mea': '0', '7UR4J2SE': '0',
                          'a9qg8vnP': '', 'm28pD1GM': '', '9BetM2Ds': '', 'e56NZY42': '0'})
            for token, labels, width in (('hn42BL3Q', ELEMENTS, 9), ('D9Nb7jgd', AILMENTS, 8)):
                fields = row[token].split(',')
                if len(fields) != width:
                    raise ValueError('Unexpected original resistance vector: ' + donor)
                # The native vector starts with fire. Preserve its ninth slot.
                for index, label in enumerate(labels):
                    if label in resists:
                        fields[index] = str(resists[label])
                row[token] = ','.join(fields)
            rows.append(row)
        monster = dict(self.monsters[donor], xqartN26=local_id, G4L0YIB2=name)
        provenance = {'name': name, 'local_id': local_id, 'donor_part_id': donor,
            'wiki_url': 'https://exvius.fandom.com/wiki/' + quote(page['title'].replace(' ', '_')),
            'wiki_sha256': page['sha256'], 'wiki_stats': stats,
            'resistance_basis': resist_basis,
            'local_stats': 'ATK/DEF/MAG/SPR scaled from the known donor by level ratio, capped at 0.5 to 2.0.',
            'hp_mp_level': 'Original wiki round values' if stats else 'Local HP/level adaptation of known donor stats'}
        return monster, rows, provenance

    def round(self, progress, wiki, missing):
        normal = [row for row in missing if not row['boss']]
        bosses = [row for row in missing if row['boss']]
        if len(normal) != 5 or len(bosses) != 1:
            raise ValueError('Expected five normal groups and one boss for ' + progress)
        boss_match = re.fullmatch(r'(.*?)(?: x (\d+))?', wiki['boss'])
        boss_name, quantity = boss_match.group(1), int(boss_match.group(2) or 1)
        boss_stats = wiki_stats(self.pages[normalized(boss_name)]['wikitext'], wiki['round'])
        if not boss_stats:
            raise ValueError('Missing original boss level/HP/MP: ' + wiki['round'])
        names = wiki['monsters'].splitlines()
        monster_rows, part_rows, provenance, ids = [], [], [], {}
        for number, name in enumerate([*names, boss_name]):
            iid = str(880000000 + int(progress) * 100 + number)
            monster, parts, source = self.enemy(name, wiki['round'], iid, max(1, boss_stats[0]['level'] - 3))
            ids[name] = iid
            monster_rows.append(monster)
            part_rows.extend(parts)
            provenance.append(source)
        groups = []
        for number, original in enumerate(normal + bosses):
            if original['boss']:
                count = sum(row['xqartN26'] == ids[boss_name] for row in part_rows)
                if quantity > 1 and count not in (1, quantity):
                    raise ValueError('Unresolved original boss quantity: ' + wiki['round'])
                lineup = [boss_name] * (1 if count == quantity else quantity)
            else:
                lineup = names if number == 4 else [names[number % len(names)], names[(number + 1) % len(names)]]
            formation = self.formations[len(lineup)]
            slots = [dict(template, **{'2fY1IomW': original['group_id'], 'xqartN26': ids[name]})
                     for template, name in zip(formation, lineup)]
            groups.append((original, slots))
        return groups, monster_rows, part_rows, provenance
