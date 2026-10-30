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
        cls.names = dict(cls.bindings['local_monster_names'], **cls.encounters['local_monster_names'])
        cls.sets = {r['A5x02C6a']: r for r in rows('F_MONSTER_SKILL_SET_MST')}
        for r in [json.loads(line) for line in (ROOT / 'data/memorial_battle_decoded/F_MONSTER_SKILL_SET_MST.ndjson')
                  .read_text(encoding='utf8').splitlines() if line]:
            cls.sets.setdefault(r['A5x02C6a'], r)
        cls.source = IndexSource()

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
                self.assertEqual(len(bundle['an6TB4WS']), int(self.missions[mid]['8xi6Xvyk']))
                groups = defaultdict(list)
                for row in bundle['Bi6hVv34']:
                    groups[row['2fY1IomW']].append(row['xqartN26'])
                ids = {r['xqartN26'] for r in bundle['wbet57nF']}
                for phase in bundle['an6TB4WS']:
                    self.assertEqual(phase['qo3PECw6'], mid)
                    self.assertTrue(groups[phase['2fY1IomW']], mid)
                    self.assertTrue(set(groups[phase['2fY1IomW']]) <= ids, mid)
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
