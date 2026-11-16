"""Map preserved Global raid reward rows to real native master identities.

Unknown values remain gaps except for the user's explicitly approved, recorded
reconstructions. No extra slots are appended to force a particular box total.
"""
from collections import defaultdict
import json
from pathlib import Path
import re

from build_raid_archive import item_key, name_tables, plain
from recover_raid_summons import source_pages, summon_section

ROOT = Path(__file__).resolve().parents[2]
JP_AREAS = {'738', '742', '771', '4082', '6210', '6410', '4480', '4500'}


class Resolver:
    def __init__(self):
        self.names = name_tables()
        self.units = {r['3HriTp6B']: r for r in map(json.loads,
            (ROOT / 'data/mst_decoded/F_UNIT_MST.ndjson').read_text('utf-8').splitlines())}
        self.item_names = {r['key'].rsplit('_', 1)[-1]: r['v'][0] for r in map(json.loads,
            (ROOT / 'data/text_decoded/F_TEXT_ITEM_NAME.ndjson').read_text('utf-8').splitlines())}

    def exact(self, name, kinds, rarity=None):
        for kind in kinds:
            values = self.names[kind].get(item_key(name), [])
            if kind == 10 and values:
                if rarity is not None:
                    values = [i for i in values if int(self.units[str(i)]['9fW0TePj']) == rarity]
                if values:
                    # Native unit rewards use the original base form unless
                    # the source explicitly names a higher rarity.
                    return kind, min(values)
            if kind in (21, 22) and len(values) > 1:
                targets = {int(u['9mu4boy7'].split(':')[1]) for u in self.units.values()
                           if str(u.get('9mu4boy7', '')).startswith(str(kind) + ':')}
                original_trust = [i for i in values if i in targets]
                if len(original_trust) == 1:
                    return kind, original_trust[0]
            if len(values) == 1:
                return kind, values[0]
        raise ValueError('Unmapped or ambiguous reward: ' + name)

    def group(self, label, context):
        normalized = plain(label).strip()
        # These groups use the same original identities as build_reward_summons.
        if re.fullmatch(r'T[123] Forticite', normalized, re.I):
            tier = int(normalized[1]) - 1
            return [(20, 271000100 + (colour * 3 + tier) * 100) for colour in range(6)]
        if normalized.lower() in ('alcryst', 'milcryst', 'heavicryst', 'giancryst', 'purecryst', 'supercite'):
            types = ('Red', 'Blue', 'Green', 'White', 'Black', 'Yellow', 'Orange', 'Violet') if normalized.lower() == 'supercite' else (
                'White', 'Black', 'Green', 'Power', 'Guard', 'Healing', 'Support', 'Tech')
            matches = [(20, int(i)) for i, name in self.item_names.items()
                       if name.lower() in {(t + ' ' + normalized).lower() for t in types}
                       and int(i) in {v for values in self.names[20].values() for v in values}]
            if len(matches) != 8:
                raise ValueError('Expected eight original types for ' + normalized)
            return matches
        if re.search(r'6-star\s+Awakening materials', normalized, re.I):
            ids = [290050500, 290060100, 290060300, 290060000, 290060200, 290060400]
            if normalized.lower().startswith('other'):
                explicit = {item_key(plain(r['wiki_label'])) for r in context}
                ids = [i for i in ids if item_key(self.item_names[str(i)]) not in explicit]
            return [(20, i) for i in ids]
        if re.search(r'\b(?:King\s+)?(?:Stat\s+)?Pots$', normalized, re.I):
            rarity_match = re.search(r'(\d)-star', normalized)
            rarity = int(rarity_match[1]) if rarity_match else 5 if 'King' in normalized else None
            if rarity not in (3, 4, 5):
                raise ValueError('Missing pot rarity: ' + normalized)
            prefix = {3: 'Mini ', 4: '', 5: 'King '}[rarity]
            names = [prefix + n + ' Pot' for n in ('Tough', 'Magi', 'Power', 'Shield', 'Smart', 'Soul', 'Burst')]
            if 'Stat' in normalized:
                names = names[:-1]
            if normalized.lower().startswith('other') or 'Other ' in normalized:
                explicit = {plain(x['wiki_label']).replace('Though', 'Tough').lower() for x in context
                            if re.search(r'\[\[.*Pot\]\]', x['wiki_label']) or re.search(r'\b(?:King )?(?:Burst|Tough|Though|Magi) Pot$', plain(x['wiki_label']))}
                names = [n for n in names if not any(n.lower() in e for e in explicit)]
            return [self.exact(n, (10,)) for n in names]
        return None

    def moogle(self, raw, amount):
        label = plain(raw)
        donor_shorthand = re.search(r'\{\{rarity\|3\}\}', raw, re.I) and re.search(r'\d+%', raw)
        if (not re.search(r'Moogle', label, re.I) and not donor_shorthand) or re.search(r'Ticket|Cape', label, re.I):
            return None
        channel = 1 if 'Super Trust Moogle' in label else 0
        percentage = re.search(r'(\d+)%', label)
        rarity = re.search(r'(\d)-star', label)
        # Generic ALL moogle rarity-to-percentage is already used by the
        # project's original reward resolver. Specific-TMR amount needs evidence.
        generic = bool(re.search(r'\[\[(?:Super )?Trust Moogle\]\]', raw)) and not re.search(r'\[\[[^]]+\]\].*\d+%.*\)', raw)
        all_moogle = 'all' in label.lower() or (generic and label.strip().endswith('Trust Moogle'))
        if not percentage and all_moogle and rarity and channel == 0:
            percent = {1: 1, 4: 5, 5: 10}.get(int(rarity[1]))
        else:
            percent = int(percentage[1]) if percentage else None
        inferred = False
        if percent is None and channel == 0 and not all_moogle and (
                (rarity and rarity[1] == '3') or re.search(r'Trust Moogle\s*\([^)]+\)|TMR Moogle', label)):
            # Explicit user decision, 2026-11-10: use the wiki's typical 5%
            # value when a named three-star raid donor omits its percentage.
            percent, inferred = 5, True
        if percent is None:
            raise ValueError('Unspecified moogle trust percentage: ' + label)
        # Target-specific moogles remain three-star units even at 100% trust.
        # The percentage belongs to the owned unit, not its master rarity.
        if channel:
            master = 906000103 if not all_moogle else 906000104 if rarity and rarity[1] == '4' else 906000105
        else:
            master = 904000103 if not all_moogle else 904000105 if percent >= 10 else 904000104 if percent == 5 else 904000101
        row = {'kind': 10, 'id': master, 'count': amount,
               'affinity_points': ['', str(percent * 10)] if channel else [str(percent * 10), '']}
        display = re.sub(r'^\d-star\s+', '', label).strip()
        if 'Moogle' not in display:
            display = ('Super Trust Moogle' if channel else 'Trust Moogle') + ' (' + display + ')'
        if not percentage:
            display += ' (' + str(percent) + '%' + (', inferred' if inferred else '') + ')'
        row['display_name'] = display
        if inferred:
            row['trust_value_source'] = 'User-approved 5% inference from https://exvius.fandom.com/wiki/Trust_Moogle; original raid table omits the value.'
        if all_moogle:
            return row
        links = re.findall(r'\[\[([^]|]+)(?:\|[^]]*)?\]\]', raw)
        links = [l for l in links if l not in ('Trust Moogle', 'Super Trust Moogle')]
        if len(links) != 1:
            raise ValueError('Ambiguous moogle target: ' + raw)
        target = links[0]
        if channel:
            candidates = self.names[10].get(item_key(target), [])
            fields = {':'.join(self.units[str(u)]['C74EmZ1I'].split(':')[:3]) for u in candidates
                      if self.units[str(u)].get('C74EmZ1I')}
            if len(fields) != 1:
                raise ValueError('Unmapped STMR target: ' + target)
            info = fields.pop() + ':1000:0:0:0'
        else:
            target = {"Fairy's Wisdom": 'Fairy Wisdom', 'Soul Eater (KH)': 'Soul Eater',
                      'Dark Ring': 'Dark Ring (FFV)'}.get(target, target)
            if target == 'Crimson Blood':
                kind, identity = 21, 1100000077  # Original Global Reberta; 308003700 is the JP unit's TMR.
            else:
                kind, identity = self.exact(target, (21, 22))
            infos = {u.get('9mu4boy7') for u in self.units.values()
                     if str(u.get('9mu4boy7', '')).startswith(f'{kind}:{identity}:')}
            if len(infos) != 1:
                # Each native rarity can carry a different donation amount;
                # the reward identity triple is sufficient for targeting.
                triples = {s.split(':')[0:3][0] + ':' + ':'.join(s.split(':')[1:3]) for s in infos}
                if len(triples) != 1:
                    raise ValueError('Missing native TMR target: ' + target)
                info = next(iter(triples)) + ':1000:0:0:0'
            else:
                info = infos.pop()
        row['affinity_info'] = ['', info] if channel else [info, '']
        return row

    def resolve(self, record, context=()):
        raw = re.sub(r'<!--.*?-->', '', record['wiki_label'], flags=re.S).strip()
        amount = record.get('award_count', 1)
        bundle = re.search(r'\s+x(\d+)\s*$', raw)
        if bundle:
            raw, amount = raw[:bundle.start()], int(bundle[1]) * amount
        if amount is None:
            raise ValueError('Unspecified award quantity')
        grouped = self.group(raw, context)
        if grouped:
            return [{'kind': k, 'id': i, 'count': amount} for k, i in grouped]
        moogle = self.moogle(raw, amount)
        if moogle:
            return [moogle]
        # A few raid tables abbreviate a named donor to the unit name and its
        # trust percentage. The native unit owns the unambiguous TMR target.
        abbreviated = re.fullmatch(r'\{\{rarity\|3\}\}\s*\[\[([^]|]+)\]\]\s*\((\d+)%\)', raw, re.I)
        if abbreviated:
            _, uid = self.exact(abbreviated[1], (10,))
            info = self.units[str(uid)].get('9mu4boy7')
            if not info:
                raise ValueError('Missing native TMR for donor: ' + abbreviated[1])
            return [{'kind': 10, 'id': 904000103, 'count': amount,
                     'affinity_points': [str(int(abbreviated[2]) * 10), ''], 'affinity_info': [info, '']}]
        label = plain(raw).replace('King Though Pot', 'King Tough Pot')
        rarity_match = re.match(r'^(\d)-star\s+', label, re.I)
        label = re.sub(r'^\d-star\s+', '', label, flags=re.I)
        maximum_level = bool(re.search(r'\(max (?:level|lvl)\)', label, re.I))
        label = re.sub(r'\s*\(max (?:level|lvl)\)', '', label, flags=re.I)
        if label == 'Lapis':
            return [{'kind': 50, 'id': 1, 'count': amount}]
        aliases = {'Rare Summon Ticket': (23, 50), '4★+ Guaranteed Ticket': (23, 70),
                   '5★+ Guaranteed EX Ticket': (23, 180), 'Raid Restore': (23, 903),
                   'Platinum Ore (DQ XI S)': (20, 235019400),
                   'Broken Blade (VP)': (20, 235016600),
                   'Metal King Claws (DQMSL)': (21, 309007600),
                   "Vayne's Garb (FFXII)": (21, 405022000),
                   'Zero Pulsar': (21, 313011100), 'Maverick (Item)': (21, 309002700),
                   "Metal Gigantuar's Here!": (10, 900020101),
                   'Sniper Eye (FFVI)+2': (21, 405031900),
                   'Crystal Orb (FFVI)+2': (21, 409082800)}
        aliases['Black Leather (Item)'] = (20, 226000300)
        # The retained original item descriptions identify these raid materials,
        # distinguishing them from later exchange items with identical names.
        aliases.update({'Moonstone': (20, 220000200), 'Gunmetal Alloy': (20, 224000200),
                        'Dense Ore': (20, 224000400), 'Gunpowder': (20, 224000500)})
        links = re.findall(r'\[\[([^]|]+)(?:\|[^]]*)?\]\]', raw)
        is_recipe = label.startswith('Recipe for ') or label.endswith(' - Recipe')
        explicit = aliases.get(links[0]) if len(links) == 1 and not is_recipe else None
        if label.endswith('+2'):
            explicit = None
        explicit = explicit or aliases.get(label)
        if explicit:
            return [{'kind': explicit[0], 'id': explicit[1], 'count': amount}]
        recipe = label.startswith('Recipe for ') or label.endswith(' - Recipe')
        if recipe:
            label = re.sub(r'^Recipe for | - Recipe$', '', label)
            label = {'Resistance Armor (FFXII)': 'Resistance Armor',
                     'Guard Stick (FFVII REMAKE)': 'Guard Stick', 'Zero Pulsar+': 'Zero Pulsar+1'}.get(label, label)
            if item_key(label + ' Recipe') in self.names[60]:
                label += ' Recipe'
            kinds = (60,)
        elif 'Ticket' in label:
            kinds = (23, 20)
        elif re.search(r'Pot$|Minituar|Gigantuar|Snapper|Emperor Gigantuar', label):
            kinds = (10, 20)
        else:
            kinds = (20, 21, 22, 10, 23)
        kind, identity = self.exact(label, kinds, int(rarity_match[1]) if rarity_match else None)
        row = {'kind': kind, 'id': identity, 'count': amount}
        if maximum_level:
            if kind != 10:
                raise ValueError('Maximum level requested for a non-unit')
            from player_state import max_level
            row['level'] = max_level(str(identity))
        return [row]


def map_rewards():
    resolver = Resolver()
    recovered = json.loads((ROOT / 'logs/raid-summon-recovery-20261109.json').read_text('utf-8'))
    result, unknown = [], defaultdict(list)
    for event in recovered['events']:
        if str(event['event_id']) in JP_AREAS:
            continue
        boxes, complete, reconstructions = [], True, []
        for box in event['boxes']:
            entries = []
            for record in box['entries']:
                try:
                    if str(event['event_id']) == '3231' and record['copies'] is None:
                        # User-approved reconstruction, 2026-11-10. The source
                        # says only awakening materials, 10-15 copies per type.
                        # Choose the native six-star family plus Holy Crystal,
                        # fifteen each. Preserve every other published count
                        # rather than adding filler to force 300/500 slots.
                        types = resolver.group('6-star Awakening materials', ()) + [resolver.exact('Holy Crystal', (20,))]
                        notice = 'Reconstructed awakening group: six-star materials and Holy Crystal, 15 copies per type; source only specifies various awakening materials, 10-15 per type.'
                        for kind, iid in types:
                            entries.append({'reward': {'kind': kind, 'id': iid, 'count': 1}, 'copies': 15,
                                            'featured': False, 'label': resolver.item_names[str(iid)] + ' (reconstructed)',
                                            'reconstruction': notice})
                        reconstructions.append({'box': box['number'], 'source_row': record['source_row'], 'decision': notice})
                        continue
                    if str(event['event_id']) == '3128' and record['wiki_label'].strip().lower() == '{{rarity|3}} [[trust moogle]]':
                        notice = 'Reconstructed unnamed featured moogle as Trust Moogle (ALL 5%); source names a three-star moogle without a trust target.'
                        entries.append({'reward': {'kind': 10, 'id': 904000104, 'count': record['award_count'],
                                                   'affinity_points': ['50', '']}, 'copies': record['copies'],
                                        'featured': record['featured'], 'label': 'Trust Moogle (ALL 5%, reconstructed)',
                                        'reconstruction': notice})
                        reconstructions.append({'box': box['number'], 'source_row': record['source_row'], 'decision': notice})
                        continue
                    if record['copies'] is None:
                        raise ValueError('Source supplies a range, not an exact slot count')
                    for row in resolver.resolve(record, box['entries']):
                        entries.append({'reward': row, 'copies': record['copies'],
                                        'featured': record['featured'], 'label': record['label']})
                except (ValueError, KeyError) as exc:
                    complete = False
                    unknown[str(exc)].append({'event_id': event['event_id'], 'box': box['number'],
                                              'source_row': record['source_row']})
            boxes.append({'number': box['number'], 'entries': entries,
                          'mapped_slots': sum(r['copies'] for r in entries)})
        result.append({'event_id': event['event_id'], 'name': event['name'],
                       'source_url': event['source_url'], 'source_revision': event['source_revision'],
                       'finite_inventory_mapped': bool(boxes) and complete, 'boxes': boxes,
                       'reconstructions': reconstructions})
    return {'scope': 'Global raid identities, published counts and user-approved labeled reconstructions',
            'events': result, 'unresolved': dict(unknown)}


if __name__ == '__main__':
    doc = map_rewards()
    target = ROOT / 'logs/raid-reward-id-mapping-20261110.json'
    target.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    mapped = sum(len(box['entries']) for e in doc['events'] for box in e['boxes'])
    print('Mapped native reward entries:', mapped)
    print('Distinct unresolved source labels:', len(doc['unresolved']))
    for reason, rows in doc['unresolved'].items():
        print(len(rows), reason)
