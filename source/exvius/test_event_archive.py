"""Check the complete archive's native battle dependencies without a device."""
from collections import defaultdict
import json
from pathlib import Path
import re
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'source/server'))
from battle_content import IndexSource, resolve_pool


def document(path):
    return json.loads((ROOT / path).read_text(encoding='utf8'))


def rows(table):
    return [json.loads(line) for line in (ROOT / 'data/mst_decoded' / (table + '.ndjson'))
            .read_text(encoding='utf8').splitlines() if line]


class EventArchiveContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bindings = document('source/server/event_battles.json')
        cls.encounters = document('source/server/event_encounters.json')
        cls.events = document('source/server/event_archive.json')['events']
        cls.missions = {r['qo3PECw6']: r for r in rows('F_MISSION_MST')}
        cls.units = {r['3HriTp6B'] for r in rows('F_UNIT_MST')}
        cls.ai = {r['8a6gAwN9'] for r in rows('F_AI_MST')} | {'', '0'}
        cls.graphics = {r['V9j8wJcC'] for r in rows('F_MONSTER_DICTIONARY_MST')}
        text = ROOT / 'data/text_decoded/F_TEXT_MONSTER_NAME.ndjson'
        cls.names = {r['key'].removeprefix('MST_MONSTER_NAME_'): r['v'][0]
                     for r in map(json.loads, text.read_text(encoding='utf8').splitlines())
                     if r.get('v')}
        cls.names.update(cls.bindings['local_monster_names'])
        cls.names.update(cls.encounters['local_monster_names'])
        cls.sets = {r['A5x02C6a']: r for r in rows('F_MONSTER_SKILL_SET_MST')}
        for r in [json.loads(line) for line in (ROOT / 'Japan content/Shared sources/memorial_battle_decoded/F_MONSTER_SKILL_SET_MST.ndjson')
                  .read_text(encoding='utf8').splitlines() if line]:
            cls.sets.setdefault(r['A5x02C6a'], r)
        cls.source = IndexSource()

    def test_break_dependencies_preserve_guardians_mechanics(self):
        from copy import deepcopy
        from battle_content import derive_mission, load_break_status, BREAK_STATUS_DEFAULT
        definitions = load_break_status(BREAK_STATUS_DEFAULT)
        for mid, pid, hp, turns, broken_atk in (
                (31520101, '312059000', '1500', '4', '170'),
                (31520102, '312059001', '2500', '3', '500')):
            with self.subTest(mission=mid):
                bundle = derive_mission(mid, self.source)
                original = next(r for r in bundle['bV34YIJQ'] if r['xqartN26'] == pid)
                self.assertEqual(original['e56NZY42'], pid)
                broken = next(r for r in bundle['BJ6A0KTt'] if r['e56NZY42'] == pid)
                extended = next(r for r in bundle['7KCkJd1E'] if r['e56NZY42'] == pid)
                self.assertEqual(broken['9NBV1XCS'], broken_atk)
                self.assertNotEqual(original['9NBV1XCS'], broken_atk)
                self.assertEqual(broken['Rcqa1Zt7'], '0,100,0,100,100,100,100')
                self.assertEqual(broken['n0UEb71s'], '80,100')
                self.assertEqual(broken['6uvHX2JG'], 'MST_MONSTER_PARTS_BREAK_DESCRIPTION_' + pid)
                self.assertEqual((extended['CX5D2V1j'], extended['JX6mCav4']), (hp, turns))
                self.assertEqual((extended['zW97Bico'], extended['8HnQR9Wx']), ('1', '300'))
                self.assertEqual(extended['RHe5r72C'], '2000,2000,100,2000,2000,2000,2000,2000,2000,2000,2000,2000,2000,2000,2000,100')
        for defect in ('missing', 'weapon_csv', 'broken_stat', 'ailment_csv'):
            with self.subTest(defect=defect):
                invalid = deepcopy(definitions)
                if defect == 'missing':
                    del invalid['312059000']
                elif defect == 'weapon_csv':
                    invalid['312059000']['RHe5r72C'] = '100'
                elif defect == 'broken_stat':
                    del invalid['312059000']['broken']['atk']
                else:
                    invalid['312059000']['resists']['n0UEb71s'] = '80'
                with self.assertRaisesRegex(SystemExit, '312059000.*Break'):
                    derive_mission(31520101, self.source, invalid)

    def test_shadows_break_suppresses_attack_without_changing_stats(self):
        from battle_content import derive_mission
        bundle = derive_mission(62020104, self.source)
        part = next(r for r in bundle['bV34YIJQ'] if r['xqartN26'] == '507012004')
        broken = next(r for r in bundle['BJ6A0KTt'] if r['e56NZY42'] == '507012004')
        extended = next(r for r in bundle['7KCkJd1E'] if r['e56NZY42'] == '507012004')
        for token in ('9NBV1XCS', 'Pn5w9dfh', '84FJM3PD', 'T8xMDAZ4', 'hn42BL3Q', 'D9Nb7jgd'):
            self.assertEqual(broken[token], part[token])
        self.assertEqual(broken['6uvHX2JG'], 'MST_MONSTER_PARTS_BREAK_DESCRIPTION_507012004')
        self.assertEqual((extended['CX5D2V1j'], extended['JX6mCav4']), ('2500', '4'))
        self.assertEqual(extended['RHe5r72C'], '10000,50,10000,50,10000,10000,10000,10000,10000,50,10000,10000,10000,50,10000,10000')

    def test_event_specific_break_restorations_keep_original_enemy_profiles(self):
        from battle_content import derive_mission
        cases = [(mid, str(507012001 + i), '2500', '4')
                 for i, mid in enumerate((62020101, 62020102, 62020103))]
        cases += [(mid, str(407481001 + i), '1000', '999')
                  for i, mid in enumerate((51520101, 51520102, 51520103))]
        cases += [(31880101, '306291000', '1000', '1')]
        for mid, pid, hp, turns in cases:
            with self.subTest(mission=mid):
                bundle = derive_mission(mid, self.source)
                normal = next(r for r in bundle['bV34YIJQ'] if r['xqartN26'] == pid)
                broken = next(r for r in bundle['BJ6A0KTt'] if r['e56NZY42'] == pid)
                extended = next(r for r in bundle['7KCkJd1E'] if r['e56NZY42'] == pid)
                self.assertEqual(normal['e56NZY42'], pid)
                self.assertEqual((extended['CX5D2V1j'], extended['JX6mCav4']), (hp, turns))
                for token in ('9NBV1XCS', 'Pn5w9dfh', '84FJM3PD', 'T8xMDAZ4'):
                    self.assertEqual(normal[token], broken[token])
                self.assertEqual(len(broken['n0UEb71s'].split(',')), 2)
                if pid == '306291000':
                    self.assertEqual(broken['hn42BL3Q'], '0,0,0,0,0,0,0,0,0')
                    self.assertEqual(broken['D9Nb7jgd'], '100,0,100,0,100,100,100,100')
                    self.assertEqual(extended['RHe5r72C'], '100,100,2000,2000,2000,100,100,2000,2000,2000,2000,2000,2000,100,2000,2000')
                else:
                    for token in ('hn42BL3Q', 'D9Nb7jgd', 'Rcqa1Zt7'):
                        self.assertEqual(normal[token], broken[token])

    def test_gilgamesh_break_retains_normal_profile_and_native_dependencies(self):
        from battle_content import derive_mission
        profiles = ((562, 63750), (3375, 127500), (6750, 255000), (17500, 510000))
        for i, (attack, defense) in enumerate(profiles):
            pid = str(305391002 + i)
            with self.subTest(part=pid):
                bundle = derive_mission(62430101 + i, self.source)
                normal = next(r for r in bundle['bV34YIJQ'] if r['xqartN26'] == pid)
                broken = next(r for r in bundle['BJ6A0KTt'] if r['e56NZY42'] == pid)
                extended = next(r for r in bundle['7KCkJd1E'] if r['e56NZY42'] == pid)
                self.assertEqual(normal['e56NZY42'], pid)
                self.assertEqual(tuple(int(normal[k]) for k in
                                      ('9NBV1XCS', 'Pn5w9dfh', '84FJM3PD', 'T8xMDAZ4')),
                                 (attack, defense, attack, defense))
                self.assertEqual(int(broken['9NBV1XCS']), attack)
                self.assertEqual(int(broken['84FJM3PD']), attack)
                self.assertLess(int(broken['Pn5w9dfh']), defense)
                self.assertLess(int(broken['T8xMDAZ4']), defense)
                for token in ('hn42BL3Q', 'D9Nb7jgd', 'Rcqa1Zt7', 'n0UEb71s'):
                    self.assertEqual(broken[token], normal[token])
                self.assertEqual((extended['CX5D2V1j'], extended['JX6mCav4']), ('1500', '999'))
                self.assertEqual(extended['RHe5r72C'],
                                 '200,100,200,200,200,200,100,200,200,200,200,200,100,100,200,200')

    def test_hell_wyrm_break_matches_recorded_gauge_sequence(self):
        import math
        from battle_content import derive_mission
        for i in range(3):
            pid = str(407371000 + i)
            with self.subTest(part=pid):
                bundle = derive_mission(31290101 + i, self.source)
                normal = next(r for r in bundle['bV34YIJQ'] if r['xqartN26'] == pid)
                broken = next(r for r in bundle['BJ6A0KTt'] if r['e56NZY42'] == pid)
                extended = next(r for r in bundle['7KCkJd1E'] if r['e56NZY42'] == pid)
                self.assertEqual(normal['e56NZY42'], pid)
                for token in ('9NBV1XCS', '84FJM3PD'):
                    self.assertEqual(normal[token], broken[token])
                self.assertEqual(extended['JX6mCav4'], '2')
                pool = int(extended['CX5D2V1j'])
                # The original UI rounds remaining BP up. These observations
                # constrain this explicitly reconstructed weapon normalization.
                self.assertEqual([math.ceil(100 * (pool - loss) / pool)
                                  for loss in (0, 210, 220, 335, 345)],
                                 [100, 97, 96, 94, 94])
                factors = list(map(int, extended['RHe5r72C'].split(',')))
                self.assertLess(factors[13], factors[1])
                self.assertLess(factors[1], factors[0])
                self.assertEqual(len(broken['n0UEb71s'].split(',')), 2)

    def test_levian_break_uses_independently_recorded_tier_gauges(self):
        import math
        from battle_content import derive_mission
        for i, observed in enumerate((80, 87)):
            pid = str(303091000 + i)
            with self.subTest(part=pid):
                bundle = derive_mission(31810101 + i, self.source)
                normal = next(r for r in bundle['bV34YIJQ'] if r['xqartN26'] == pid)
                broken = next(r for r in bundle['BJ6A0KTt'] if r['e56NZY42'] == pid)
                extended = next(r for r in bundle['7KCkJd1E'] if r['e56NZY42'] == pid)
                self.assertEqual(normal['e56NZY42'], pid)
                self.assertEqual(extended['JX6mCav4'], '3')
                pool = int(extended['CX5D2V1j'])
                # Each tier has its own recorded first fresh dual-weapon
                # action, before the native repeat-decay counter advances.
                self.assertEqual(math.ceil(100 * (pool - 200) / pool), observed)
                self.assertEqual(extended['RHe5r72C'], ','.join(
                    '100' if j in (3, 5, 11) else '2000' for j in range(16)))
                for token in ('9NBV1XCS', '84FJM3PD'):
                    self.assertEqual(normal[token], broken[token])
                self.assertEqual(len(broken['n0UEb71s'].split(',')), 2)

    def test_every_audited_break_definition_is_present(self):
        from battle_content import load_break_status, BREAK_STATUS_DEFAULT
        expected = {'306291000', '305791001'}
        for first, count in ((312059000, 2), (507012001, 4), (407481001, 3),
                             (310041000, 2), (311051000, 2), (402049000, 2),
                             (303091000, 2), (407371000, 3), (306251002, 6),
                             (305391002, 4)):
            expected.update(str(first + i) for i in range(count))
        self.assertEqual(len(expected), 32)
        definitions = load_break_status(BREAK_STATUS_DEFAULT)
        self.assertFalse(expected.difference(definitions),
                         'An audited native Break dependency was removed')
        for pid in sorted(expected):
            with self.subTest(part=pid):
                self.assertGreater(definitions[pid]['break_hp'], 0)
                self.assertGreater(definitions[pid]['turns'], 0)

    def test_break_weapon_values_match_original_client_division(self):
        from battle_content import load_break_status, BREAK_STATUS_DEFAULT
        import struct
        f32 = lambda value: struct.unpack('<f', struct.pack('<f', value))[0]
        weapons = ('Dagger', 'Sword', 'Great Sword', 'Katana', 'Staff', 'Rod', 'Bow', 'Axe',
                   'Hammer', 'Spear', 'Instrument', 'Whip', 'Throwing', 'Gun', 'Mace', 'Fist')
        for pid, definition in load_break_status(BREAK_STATUS_DEFAULT).items():
            with self.subTest(part=pid):
                factors = list(map(int, definition['RHe5r72C'].split(',')))
                self.assertEqual(len(factors), len(weapons))
                for weapon, resistance in zip(weapons, factors):
                    points = f32(100.0 / f32(resistance / 100.0))
                    self.assertEqual(round(points), definition['weapon_break_damage'][weapon])
        # These have exact integer damage and establish the direction of the
        # denominator independently of the generated asset's published table.
        self.assertEqual([int(f32(100.0 / f32(value / 100.0)))
                          for value in (2000, 200, 100, 50, 10000)], [5, 50, 100, 200, 1])

    def assert_native_rows(self, monsters, parts):
        for monster in monsters:
            self.assertIn(monster['V9j8wJcC'], self.graphics, monster)
        for part in parts:
            pid = part['xqartN26']
            label = pid + chr(64 + int(part['6Yc4RkdM']))
            self.assertTrue(self.names.get(label), label)
            self.assertFalse(re.search(r'[\u3040-\u30ff\u3400-\u9fff]', self.names[label]), label)
            self.assertIn(part.get('8a6gAwN9', ''), self.ai, pid)
            unit = part.get('3HriTp6B', '')
            if unit and unit != '0':
                self.assertIn(unit, self.units, pid)
            skill_set = part.get('A5x02C6a', '')
            if skill_set and skill_set != '0':
                self.assertIn(skill_set, self.sets, pid)

    def test_every_archive_mission_has_a_battle_or_original_resource_route(self):
        from battle_content import is_menu_resource_row
        from battle_content import DEFAULT_RESPONSES
        authored = json.loads(Path(DEFAULT_RESPONSES).read_text(encoding='utf8'))
        for event in self.events:
            for mid in event['missions']:
                mission = self.missions[mid]
                if not int(mission['8xi6Xvyk']) or is_menu_resource_row(mission):
                    continue
                if self.bindings['resource_missions'].get(mid) == 'exploration':
                    continue
                self.assertTrue(mid in self.bindings['missions'] or mid in self.encounters['missions'] or
                                'jnw49dUq@' + mid in authored, mid)

    def test_reconstructed_battles_resolve_all_native_references_and_waves(self):
        for mid, entry in self.encounters['missions'].items():
            with self.subTest(mission=mid):
                bundle = entry['bundle']
                phases = bundle.get('an6TB4WS', [])
                field = self.missions[mid]['Y4VoF8yu'] == '2'
                if field:
                    self.assertFalse(phases, mid)
                    self.assertTrue(bundle.get('rqxw0p9k') or bundle.get('6v0LPiRe'), mid)
                    scenarios = {r['ja07xgLF'] for r in bundle.get('rqxw0p9k', [])}
                    self.assertTrue({r['ja07xgLF'] for r in bundle.get('YjHhvN65', [])} <= scenarios, mid)
                else:
                    self.assertEqual(len(phases), int(self.missions[mid]['8xi6Xvyk']))
                groups = defaultdict(list)
                for row in bundle['Bi6hVv34']:
                    groups[row['2fY1IomW']].append(row['xqartN26'])
                ids = {r['xqartN26'] for r in bundle['wbet57nF']}
                for phase in phases:
                    self.assertEqual(phase['qo3PECw6'], mid)
                    self.assertTrue(groups[phase['2fY1IomW']], mid)
                    self.assertTrue(set(groups[phase['2fY1IomW']]) <= ids, mid)
                for link in bundle.get('YjHhvN65', []):
                    self.assertTrue(groups[link['2fY1IomW']], mid)
                for encounter in bundle.get('6v0LPiRe', []):
                    self.assertEqual(encounter['qo3PECw6'], mid)
                    self.assertIn(encounter['xqartN26'], groups[encounter['2fY1IomW']], mid)
                for members in groups.values():
                    self.assertTrue(set(members) <= ids, mid)
                self.assert_native_rows(bundle['wbet57nF'], bundle['bV34YIJQ'])
                served = {r['6E5u1xrs'] for r in bundle.get('Wp39QX52', [])}
                for part in bundle['bV34YIJQ']:
                    skill_set = self.sets.get(part.get('A5x02C6a'))
                    if skill_set:
                        self.assertTrue(set(filter(None, skill_set['7qxLC5hP'].split(','))) <= served, mid)

    def test_bound_battles_resolve_selected_pools_models_units_ai_and_skills(self):
        phases, pools, groups, parts = (defaultdict(list) for _ in range(4))
        monsters = {r['xqartN26']: r for r in self.source.load('F_MONSTER_MST')}
        for r in self.source.load('F_MISSION_PHASE_MST'):
            if r.get('gou39JeI') == '2':
                phases[r['qo3PECw6']].append(r)
        for r in self.source.load('F_BATTLE_LOTTERY_MST'):
            pools[r['c2gnh6Jd']].append(r)
        for r in self.source.load('F_BATTLE_GROUP_MST'):
            groups[r['2fY1IomW']].append(r)
        for r in self.source.load('F_MONSTER_PARTS_MST'):
            parts[r['xqartN26']].append(r)
        support = self.bindings['native_battle_support']
        skills = {r['6E5u1xrs'] for r in self.source.load('F_MONSTER_SKILL_MST') + support['F_MONSTER_SKILL_MST']}
        served_sets = {r['A5x02C6a']: r for r in self.source.load('F_MONSTER_SKILL_SET_MST')}
        served_sets.update({r['A5x02C6a']: r for r in support['F_MONSTER_SKILL_SET_MST']})
        checked = set()
        for mid, binding in self.bindings['missions'].items():
            for phase in sorted(phases[binding['source']], key=lambda r: int(r['6v7y3QcJ']))[:binding['waves']]:
                pool = phase.get('6uIYE15X', '')
                resolved = resolve_pool(pools[pool], pool)
                self.assertIsNotNone(resolved, mid)
                slots = groups[resolved[0]]
                self.assertTrue(slots, mid)
                for slot in slots:
                    pid = slot['xqartN26']
                    if pid in checked:
                        continue
                    checked.add(pid)
                    with self.subTest(mission=mid, enemy=pid):
                        monster = dict(monsters[pid], **binding.get('monster_overrides', {}).get(pid, {}))
                        profiles = [dict(p, **binding.get('part_overrides', {}).get(pid + ':' + p['6Yc4RkdM'], {}))
                                    for p in parts[pid]]
                        self.assertTrue(profiles, pid)
                        self.assert_native_rows([monster], profiles)
                        for part in profiles:
                            skill_set = self.sets.get(part.get('A5x02C6a'))
                            if skill_set:
                                self.assertEqual(served_sets[skill_set['A5x02C6a']]['7qxLC5hP'], skill_set['7qxLC5hP'])
                                self.assertTrue(set(filter(None, skill_set['7qxLC5hP'].split(','))) <= skills,
                                                (mid, pid, skill_set['A5x02C6a']))

    def test_recovered_global_skill_sets_are_served_in_actual_battle_payloads(self):
        from battle_content import EventSource, derive_mission
        for mid in ('8991106', '7340101', '32030101'):
            with self.subTest(mission=mid):
                bundle = derive_mission(mid, EventSource(self.source, mid, self.bindings['missions'][mid]))
                served = {r['6E5u1xrs'] for r in bundle['Wp39QX52']}
                for part in bundle['bV34YIJQ']:
                    skill_set = self.sets.get(part.get('A5x02C6a'))
                    if skill_set:
                        self.assertTrue(set(filter(None, skill_set['7qxLC5hP'].split(','))) <= served)


if __name__ == '__main__':
    unittest.main()
