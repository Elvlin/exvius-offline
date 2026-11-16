"""Exercise field profile sourcing before strict original-group derivation."""
import copy
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / p) for p in ('source/server', 'source/exvius', 'custom-engine/tools')]
import battle_content
from player_state import mission_row


class FieldProfileSourceTests(unittest.TestCase):
    def test_glaive_preserves_all_original_groups_and_five_imp_formations(self):
        source = battle_content._default_index_source()
        for mid, imp in (('7640101', '104061001'), ('7640102', '104061000')):
            with self.subTest(mission=mid):
                original = [r for r in source.load('F_BATTLE_GROUP_MST')
                            if r['2fY1IomW'].startswith(mid) and len(r['2fY1IomW']) == len(mid)+2]
                bundle = battle_content.field_mission_bundle({}, mission_row(mid))
                by_identity = lambda rows: {(r['2fY1IomW'], r['Z0EN6jSh']): r for r in rows}
                self.assertEqual(by_identity(bundle['Bi6hVv34']), by_identity(original))
                actors = {r['xqartN26'] for r in original}
                self.assertEqual(actors, {r['xqartN26'] for r in bundle['wbet57nF']})
                self.assertEqual(actors, {r['xqartN26'] for r in bundle['bV34YIJQ']})
                imp_group = '764010112' if mid == '7640101' else '764010208'
                self.assertEqual(sum(r['xqartN26'] == imp and r['2fY1IomW'] == imp_group
                                     for r in bundle['Bi6hVv34']), 5)
                self.assertFalse(bundle.get('an6TB4WS'))
                self.assertFalse(bundle.get('y35YvQjZ'))
                self.assertEqual(bundle['6v0LPiRe'], [])
                monsters = {r['xqartN26']: r for r in bundle['wbet57nF']}
                self.assertEqual(monsters[imp]['V9j8wJcC'], '1040610')
                self.assertEqual(monsters[imp]['G4L0YIB2'], 'Imp')

    def test_published_hard_boss_fields_and_original_combat_dependencies(self):
        source = battle_content._default_index_source()
        sets = {r['A5x02C6a']: r for r in source.load('F_MONSTER_SKILL_SET_MST')}
        bundle = battle_content.field_mission_bundle({}, mission_row('7640101'))
        profiles = {r['xqartN26']: r for r in bundle['bV34YIJQ']}
        for pid, name, hp, mp, ai in (('301141001', 'Chimera', '3600000', '2500', '301141000'),
                                      ('305241001', 'Dark Lord', '4000000', '5000', '305241000')):
            profile = profiles[pid]
            self.assertEqual((profile['G4L0YIB2'], profile['7wV3QZ80'], profile['fh31sk7B'], profile['PC97pWQj']),
                             (name, '99', hp, mp))
            self.assertEqual(profile['hn42BL3Q'], '0,0,0,0,0,0,0,0,0')
            self.assertEqual(profile['D9Nb7jgd'], '100,100,100,100,100,100,100,100')
            self.assertEqual((profile['8a6gAwN9'], profile['A5x02C6a']), (ai, pid))
        self.assertEqual(profiles['305241001']['Rcqa1Zt7'], '0,100,100,100,100,0,0')
        supplied = {r['6E5u1xrs'] for r in bundle['Wp39QX52']}
        for profile in profiles.values():
            sid = profile['A5x02C6a']
            if sid != '0':
                self.assertTrue({s for s in sets[sid]['7qxLC5hP'].split(',') if s} <= supplied)
        self.assertTrue({'174290', '174300', '174310', '174320', '174330', '153730', '174340'} <= supplied)

    def test_explicit_profiles_are_loaded_before_original_group_derivation(self):
        source = battle_content._default_index_source()
        original = battle_content.field_mission_bundle({}, mission_row('1115005'))
        pid, gid, sid = '301021000', '111500511', '111500501'
        supplied = {
            'rqxw0p9k': [{'ja07xgLF': sid, '6w4xiIsS': '400007'}],
            'YjHhvN65': [{'ja07xgLF': sid, '2fY1IomW': gid}],
            'wbet57nF': [r for r in original['wbet57nF'] if r['xqartN26'] == pid],
            'bV34YIJQ': [r for r in original['bV34YIJQ'] if r['xqartN26'] == pid],
            'Wp39QX52': original['Wp39QX52']}

        class MissingOriginalActor(battle_content.Source):
            def load(self, table):
                rows = source.load(table)
                if table in ('F_MONSTER_MST', 'F_MONSTER_PARTS_MST'):
                    return [row for row in rows if row['xqartN26'] != pid]
                return rows

        filtered = MissingOriginalActor()
        with patch.object(battle_content, '_default_index_source', return_value=filtered):
            with patch.object(battle_content, 'event_encounter', return_value=supplied):
                restored = battle_content.field_mission_bundle({}, mission_row('1115005'))
            self.assertEqual(restored['Bi6hVv34'], original['Bi6hVv34'])
            self.assertEqual({r['xqartN26'] for r in restored['wbet57nF']},
                             {r['xqartN26'] for r in original['wbet57nF']})
            self.assertFalse(restored.get('an6TB4WS'))
            self.assertFalse(restored.get('y35YvQjZ'))
            # A partial field definition must still fail the real dependency
            # validator. It cannot acknowledge a battle without its parts.
            incomplete = copy.deepcopy(supplied)
            incomplete['bV34YIJQ'] = []
            with patch.object(battle_content, 'event_encounter', return_value=incomplete):
                with self.assertRaisesRegex(SystemExit, 'PARTS|parts'):
                    battle_content.field_mission_bundle({}, mission_row('1115005'))
            ordinary = {key: value for key, value in supplied.items()
                        if key not in ('rqxw0p9k', 'YjHhvN65')}
            with patch.object(battle_content, 'event_encounter', return_value=ordinary):
                with self.assertRaisesRegex(SystemExit, 'MONSTER|monster'):
                    battle_content.field_mission_bundle({}, mission_row('1115005'))


if __name__ == '__main__':
    unittest.main()
