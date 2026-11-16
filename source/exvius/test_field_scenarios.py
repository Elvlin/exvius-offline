"""Field entry must load explicit native scenario dependencies before its script."""
import copy
import importlib.util
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'source/server'))
sys.path.insert(0, str(ROOT / 'custom-engine/tools'))

import battle_content
from cpk import Cpk
from fill_content_from_memorial import localized_package
from player_state import mission_row


class FieldScenarioTests(unittest.TestCase):
    def test_musical_typed_scripts_resolve_complete_boss_graphs(self):
        # Parse complete native event containers, not byte-pattern collisions.
        spec = importlib.util.spec_from_file_location('native_pages', ROOT / 'source/build/inspect-map-chests-20261027.py')
        native = importlib.util.module_from_spec(spec)
        with patch.object(sys, 'argv', ['inspect-map-chests']):
            spec.loader.exec_module(native)
        entries = json.loads((ROOT / 'source/server/event_encounters.json').read_text(encoding='utf8'))['missions']
        for index, filename in enumerate(('Ver14_90000401.cpk', 'Ver14_90000402.cpk',
                                         'Ver9_90000403.cpk', 'Ver9_90000404.cpk', 'Ver9_90000405.cpk')):
            mid = str(9001701 + index)
            with self.subTest(mission=mid):
                pack = Cpk((ROOT / 'data/overlay/common_lang/sd/event/SG' / filename).read_bytes())
                scenarios = set()
                for name in pack.files:
                    if not name.endswith('.bin'):
                        continue
                    data = pack.read(name)
                    r = native.Reader(data)
                    size, version = r.integer(), r.integer()
                    self.assertEqual(size, len(data))
                    r.take(12 if version >= 1009 else 0)
                    r.take(4 if version >= 1022 else 0)
                    for _ in range(r.integer()):
                        r.short()
                        r.string()
                    for _ in range(r.short()):
                        start = r.pos
                        length, mapid = r.integer(), r.short()
                        if version >= 1015:
                            width, height = r.integer(), r.integer()
                            r.take(width * height)
                        for _ in range(r.short()):
                            r.integer() if version >= 1024 else r.short()
                            kind = r.byte()
                            r.take(8 + 14 + 2 * (version >= 1046))
                            for _ in range(r.byte()):
                                _, commands = native.page(r, kind, version)
                                for opcode, payload, _ in commands:
                                    if opcode == 0x47:
                                        self.assertEqual(len(payload), 4)
                                        scenarios.add(str(int.from_bytes(payload, 'big')))
                        self.assertEqual(r.pos, start + length)
                    self.assertEqual(r.pos, len(data))
                self.assertEqual(scenarios, {'9001701' if index == 1 else mid})
                actual = battle_content.field_mission_bundle({}, mission_row(mid))
                groups = {r['ja07xgLF']: r for r in actual['YjHhvN65']}
                masters = {r['ja07xgLF'] for r in actual['rqxw0p9k']}
                for sid in scenarios:
                    self.assertIn(sid, masters)
                    gid = groups[sid]['2fY1IomW']
                    formation = [r for r in actual['Bi6hVv34'] if r['2fY1IomW'] == gid]
                    self.assertEqual([r['Z0EN6jSh'] for r in formation], ['1', '2', '3', '4', '5'])
                    self.assertEqual([r['WJdBp9f0'] for r in formation], ['1', '1', '1', '0', '0'])
                    self.assertTrue(all(r['m9BvFk2X'] == '1' for r in formation))
                    part_ids = {r['xqartN26'] for r in actual['bV34YIJQ']}
                    monster_ids = {r['xqartN26'] for r in actual['wbet57nF']}
                    self.assertTrue({r['xqartN26'] for r in formation} <= part_ids & monster_ids)
                    self.assertEqual(len([r for r in actual['JR7jZci2'] if r['ja07xgLF'] == sid]), 5)
                skills = {r['6E5u1xrs']: r for r in actual['Wp39QX52']}
                self.assertTrue({str(i) for i in range(900086, 900091)} <= skills.keys())
                self.assertEqual(skills['900086']['Ha9G5sCS'], '1,4,MST_MONSTERSKILL_PARAM_MSG_900086,100,0')
                self.assertEqual(skills['900087']['Ha9G5sCS'], '1,5,MST_MONSTERSKILL_PARAM_MSG_900087,100,0')
                self.assertNotIn('an6TB4WS', actual)
                self.assertIn('derived_stats', entries[mid]['scripted_boss_reconstruction'])

    def test_explicit_original_scenario_is_available_before_field_script(self):
        mid, sid = '1115005', '1115101'
        captured = json.loads((ROOT / 'source/server/responses.json').read_text(encoding='utf8'))['29JRaDbd']
        master = next(r for r in captured['rqxw0p9k'] if r['ja07xgLF'] == sid)
        group = next(r for r in captured['YjHhvN65'] if r['ja07xgLF'] == sid)
        original = battle_content.field_mission_bundle({}, mission_row(mid))
        formation = [r for r in original['Bi6hVv34'] if r['2fY1IomW'] == group['2fY1IomW']]
        supplied = {'rqxw0p9k': [master], 'YjHhvN65': [group], 'Bi6hVv34': formation,
                    'an6TB4WS': [{'qo3PECw6': mid, 'gou39JeI': '2'}],
                    'y35YvQjZ': [{'qo3PECw6': mid}], '1IfDqR4n': []}
        before = copy.deepcopy(supplied)
        with patch.object(battle_content, 'event_encounter', return_value=supplied):
            actual = battle_content.field_mission_bundle({}, mission_row(mid))
        self.assertEqual(actual['rqxw0p9k'], [master])
        self.assertEqual(actual['YjHhvN65'], [group])
        self.assertTrue(formation)
        self.assertEqual(actual['Bi6hVv34'], original['Bi6hVv34'])
        self.assertEqual(actual['1IfDqR4n'], [mission_row(mid)])
        self.assertNotIn('an6TB4WS', actual)
        self.assertNotIn('y35YvQjZ', actual)
        self.assertEqual(supplied, before)

    def test_regular_wave_definition_does_not_replace_field_dependencies(self):
        mid = '1115005'
        original = battle_content.field_mission_bundle({}, mission_row(mid))
        with patch.object(battle_content, 'event_encounter', return_value={
                'an6TB4WS': [{'gou39JeI': '2'}], 'Bi6hVv34': [{'2fY1IomW': 'unrelated'}]}):
            actual = battle_content.field_mission_bundle({}, mission_row(mid))
        self.assertEqual(actual, original)

    def test_random_only_field_data_is_preserved_and_next_field_clears_it(self):
        mid = '1115005'
        # A controlled native response fixture, not a reconstructed production
        # allocation or a claim about this mission's random encounter quota.
        original = battle_content.field_mission_bundle({}, mission_row(mid))
        formation = next(row for row in original['Bi6hVv34'] if row['2fY1IomW'] == '111500511')
        encounter = {'qo3PECw6': mid, 'YzGa63QM': '10', '2fY1IomW': formation['2fY1IomW'],
                     'h4Sjf96p': '0', 'Z0EN6jSh': formation['Z0EN6jSh'],
                     'xqartN26': formation['xqartN26'], '6Yc4RkdM': '1'}
        supplied = {'6v0LPiRe': [encounter], 'an6TB4WS': [{'gou39JeI': '2'}]}
        before = copy.deepcopy(supplied)
        with patch.object(battle_content, 'event_encounter', return_value=supplied):
            actual = battle_content.field_mission_bundle({}, mission_row(mid))
        self.assertEqual(actual['6v0LPiRe'], [encounter])
        self.assertNotIn('an6TB4WS', actual)
        self.assertEqual(supplied, before)
        with patch.object(battle_content, 'event_encounter', return_value=None):
            cleared = battle_content.field_mission_bundle(actual, mission_row('1115006'))
        self.assertEqual(cleared['6v0LPiRe'], [])

    def test_musical_reconstructed_random_allocations_are_finite_and_complete(self):
        from collections import Counter, defaultdict
        expected = ((7, {'900010278': 6, '111051000': 3}),
                    (8, {'900010278': 8, '111051000': 1, '111061000': 1}),
                    (6, {'900010279': 6, '111061000': 2}),
                    (6, {'900010280': 4, '111061000': 1, '211011000': 2}),
                    (7, {'900010280': 8, '211011000': 2}))
        for index, (battles, actors) in enumerate(expected):
            mid = str(9001701 + index)
            with self.subTest(mission=mid):
                bundle = battle_content.field_mission_bundle({}, mission_row(mid))
                encounters = bundle['6v0LPiRe']
                self.assertEqual(Counter(r['xqartN26'] for r in encounters), actors)
                self.assertNotIn('an6TB4WS', bundle)
                bard_drops = [r for r in bundle['JR7jZci2'] if r.get('9BetM2Ds')]
                self.assertEqual(len(bard_drops), 1)
                self.assertEqual(bard_drops[0]['xqartN26'], str(900010273 + index))
                self.assertEqual(bard_drops[0]['9BetM2Ds'], '20:1209000835:' + str(index + 1) + ':100')
                groups, counters = defaultdict(list), defaultdict(set)
                monsters = {r['xqartN26'] for r in bundle['wbet57nF']}
                parts = {(r['xqartN26'], r['6Yc4RkdM']) for r in bundle['bV34YIJQ']}
                formation = {(r['2fY1IomW'], r['Z0EN6jSh'], r['xqartN26'])
                             for r in bundle['Bi6hVv34']}
                for row in encounters:
                    self.assertEqual((row['qo3PECw6'], row['YzGa63QM']), (mid, '10'))
                    self.assertIn(row['xqartN26'], monsters)
                    self.assertIn((row['xqartN26'], row['6Yc4RkdM']), parts)
                    self.assertIn((row['2fY1IomW'], row['Z0EN6jSh'], row['xqartN26']), formation)
                    captured = {'111051000': '900020101', '111061000': '900020201',
                                '211011000': '900020301'}.get(row['xqartN26'])
                    self.assertEqual(row['Vf5DGw07'], '10:' + captured + ':1' if captured else '')
                    key = row['2fY1IomW'], int(row['h4Sjf96p'])
                    groups[key].append(row)
                    counters[key[0]].add(key[1])
                self.assertEqual(len(groups), battles)
                for gid, values in counters.items():
                    self.assertEqual(values, set(range(len(values))))
                    # Original getList/checkEnable uses exact equality. Once
                    # every supplied counter is consumed, no matching row exists.
                    self.assertNotIn((gid, len(values)), groups)
                # PRO's two published profiles are resolved by total EXP.
                if index == 3:
                    pro_parts = {r['xqartN26']: r for r in bundle['bV34YIJQ']}
                    random_exp = sum(int(pro_parts[r['xqartN26']]['B6H34Mea']) for r in encounters)
                    boss = [r for r in bundle['Bi6hVv34']
                            if r['2fY1IomW'] == '900170401' and r['WJdBp9f0'] == '1']
                    self.assertEqual(random_exp + sum(int(pro_parts[r['xqartN26']]['B6H34Mea'])
                                                     for r in boss), 9480)

    def test_musical_localized_keys_match_the_original_native_csv_reader(self):
        paths = ['common_lang/sd/map/SG/Ver15_900004.cpk'] + [
            'common_lang/sd/event/SG/' + name for name in (
                'Ver14_90000401.cpk', 'Ver14_90000402.cpk', 'Ver9_90000403.cpk',
                'Ver9_90000404.cpk', 'Ver9_90000405.cpk')]
        for relative in paths:
            with self.subTest(package=relative):
                source = ROOT / 'data/client/files' / relative
                before = Cpk(source.read_bytes())
                effective_path = ROOT / 'data/overlay' / relative
                rebuilt, count = localized_package(effective_path)
                after = Cpk(rebuilt)
                effective = Cpk(effective_path.read_bytes())
                self.assertEqual(count, 0)
                self.assertEqual(set(effective.files), set(after.files))
                for name in effective.files:
                    self.assertEqual(after.read(name), effective.read(name), name)
                for name in before.files:
                    original = before.read(name)
                    if name.endswith('_text_sg.txt') and original:
                        expected = original[3:] if original.startswith(b'\xef\xbb\xbf') else original
                        self.assertEqual(effective.read(name), expected, name)
                    elif not name.endswith('.txt'):
                        self.assertEqual(effective.read(name), original, name)
        pack = Cpk((ROOT / 'data/overlay/common_lang/sd/event/SG/Ver14_90000401.cpk').read_bytes())
        first = pack.read('90000401_event_text_sg.txt').splitlines()[0]
        # Native 0x1a37124 preserves every byte before the first caret as key.
        self.assertEqual(first.split(b'^', 1)[0], b'210001')
        self.assertEqual(first.split(b'^')[1], b'The Bard Spirit gazes upon you.<br>Proceed?')


if __name__ == '__main__':
    unittest.main()
