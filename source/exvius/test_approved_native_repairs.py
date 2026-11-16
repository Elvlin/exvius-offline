"""Approved-only delivery must retain the installed baseline and exclude JP imports."""
import json
from pathlib import Path
import struct
import unittest
import zipfile

import approved_native_repairs as repairs
from decode_client_data import client_manifest, decode
from native_master_index import build_index


class ApprovedNativeRepairs(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.files = repairs.build_approved_files()
        cls.contract = json.loads(repairs.RECIPE_CONTRACT.read_text(encoding='utf8'))
        cls.manifest = {r['table']: r for r in client_manifest(
            repairs.ROOT / 'repository snapshots/FFBE-Global-v9.0.0-original.apk').values()}

    def baseline(self, member):
        archive, expected = repairs.BASELINES[member]
        with zipfile.ZipFile(repairs.ARCHIVES / archive) as pack:
            raw = pack.read(member)
        self.assertEqual(repairs.sha(raw), expected)
        return raw

    def test_recipe_native_and_static_preserve_every_unselected_baseline_record(self):
        definitions = {r['table']: r for r in self.contract['tables']}
        for table, (key, member, expected_ids) in repairs.RECIPE_TABLES.items():
            with self.subTest(table=table):
                source, output = self.baseline(member), self.files[member]
                self.assertTrue(output.startswith(source))
                before = decode(source, self.manifest[table]['key'])[1]
                after = decode(output, self.manifest[table]['key'])[1]
                self.assertEqual(after, before + definitions[table]['rows'])
                self.assertEqual({r[key] for r in after} - {r[key] for r in before}, expected_ids)
                static = 'static/mst_decoded/' + table + '.ndjson'
                source = self.baseline(static)
                self.assertTrue(self.files[static].startswith(source))
                previous = [json.loads(r) for r in source.splitlines() if r.strip()]
                current = [json.loads(r) for r in self.files[static].splitlines() if r.strip()]
                self.assertEqual(current, previous + definitions[table]['rows'])
        book = decode(self.files['native/mst/Ver318_yu5rvEI3.dat'], self.manifest['F_RECIPE_BOOK_MST']['key'])[1]
        equip = decode(self.files['native/mst/Ver392_S67QEJsz.dat'], self.manifest['F_EQUIP_ITEM_MST']['key'])[1]
        self.assertEqual(len(book), 2050)
        self.assertEqual(len(equip), 4277)
        self.assertFalse({r['J1YX9kmM'] for r in equip} & {'870000001', '870000017', '870000020', '870000021'})

    def test_reviewed_english_labels_and_coupled_quest_title_metadata_change(self):
        definitions = {r['table']: r for r in self.contract['text_tables']}
        for table, member in repairs.TEXT_TABLES.items():
            with self.subTest(table=table):
                labels = definitions[table]['inline_labels']
                before = decode(self.baseline(member), self.manifest[table]['key'], localized=True)[1]
                after = decode(self.files[member], self.manifest[table]['key'], localized=True)[1]
                self.assertEqual([r for r in after if r['key'] not in labels], before)
                self.assertEqual({r['key']: r['v'] for r in after if r['key'] in labels},
                                 {key: [label, label] for key, label in labels.items()})
                static = 'static/text_decoded/' + table + '.ndjson'
                self.assertTrue(self.files[static].startswith(self.baseline(static)))
        table, member = 'F_LOCALIZED_TEXT_MST', 'native/mst/Ver710_i5QEJpua.dat'
        before = decode(self.baseline(member), self.manifest[table]['key'])[1]
        after = decode(self.files[member], self.manifest[table]['key'])[1]
        import hashlib
        repaired_tables = {**repairs.TEXT_TABLES,
                           'F_TEXT_UNITS_NAME': 'native/localized_texts/en/Ver229_sZE3Lhgj.dat',
                           'F_TEXT_MONSTER_PARTS_BREAK_DES': repairs.BREAK_TEXT_MEMBER}
        for old, new in zip(before, after):
            name = old['a4hXTIm0']
            if name not in set(repaired_tables) | {'F_TEXT_QUEST'}:
                self.assertEqual(old, new)
                continue
            body = (repairs._approved_quest_title() if name == 'F_TEXT_QUEST'
                    else self.files[repaired_tables[name]])
            self.assertEqual(new['00zAYGYS'], old['00zAYGYS'])
            self.assertEqual(new['zptmZGqa'], hashlib.md5(body).hexdigest())
            self.assertEqual(int(new['MLOSu5E0']), len(body))
            self.assertEqual({k: v for k, v in new.items() if k not in ('zptmZGqa', 'MLOSu5E0')},
                             {k: v for k, v in old.items() if k not in ('zptmZGqa', 'MLOSu5E0')})

    def test_description_and_category_indexes_match_original_sized_approved_masters(self):
        for table, member, count, expected_index in [
            ('F_UNIT_EXPLAIN_MST', 'native/mst/Ver244_Da62x85q.dat', 3628,
             'b207339b903e780ad67e4095fdcd82af8e425ed0215151d2dafe331ccf7faf14'),
            ('F_UNIT_SUB_CATEGORY_MST', 'native/mst/Ver26_jqv20D3o.dat', 71,
             '9ee7d9f48e9272fa7a5ab4e40ab001c6239db55dfe0b4b239742aacd8bb57b55')]:
            with self.subTest(table=table):
                info = self.manifest[table]
                raw = self.files[member]
                self.assertEqual(raw, self.baseline(member))
                self.assertEqual(len(decode(raw, info['key'])[1]), count)
                version = int(Path(member).name.split('_')[0][3:])
                index = self.files['native/mst/' + info['token'] + '.i']
                self.assertEqual(index, build_index(table, raw, info['key'], version))
                self.assertEqual(repairs.sha(index), expected_index)
                self.assertEqual(struct.unpack_from('<H', index, 8)[0], count)

    def test_exact_delivery_scope_excludes_current_overlay_assets_and_extra_content(self):
        self.assertEqual(len(self.files), 38)
        self.assertEqual(sum(name.startswith('native/') for name in self.files), 28)
        self.assertEqual(sum(name.startswith('static/') for name in self.files), 10)
        self.assertEqual({name for name in self.files if name.endswith('.cpk')},
                         {'native/' + name for name in
                          repairs.GLOBAL_TOWN_PACKAGES.keys() | repairs.GLOBAL_SCENE_MESSAGE_PACKAGES.keys()})
        for relative, expected in repairs.GLOBAL_TOWN_PACKAGES.items():
            self.assertEqual(repairs.sha(self.files['native/' + relative]), expected)
        self.assertFalse(any(name.endswith('_1Bj4oy5Q.dat') for name in self.files))
        self.assertIn(repairs.CLASSIC_CHALLENGE_MEMBER, self.files)
        self.assertFalse(any('..' in Path(name).parts for name in self.files))


if __name__ == '__main__':
    unittest.main()
