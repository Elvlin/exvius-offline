"""Regress blank English rows, native speaker scope and actual repaired CPKs."""
import hashlib
import json
import re
import struct
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from cricodecs import cpk, utf
import fill_content_from_memorial as content
from verify_content import inspect, common_tellers, common_npc_names, development_packages

ROOT = Path(__file__).resolve().parents[2]


def members(path):
    archive = cpk.load(str(path))
    return {e.full_path: archive.file_bytes(i) for i, e in enumerate(archive.file_infos())}


class LocalizationRegression(unittest.TestCase):
    def test_blank_translation_is_filled_before_town_speaker_is_scoped(self):
        source = '<name=200123><br>話そう。<keywait>'
        english = "<name=200123><br>Let's talk.<keywait>"
        key = hashlib.sha256(source.encode('utf8')).hexdigest()
        with tempfile.TemporaryDirectory(dir=ROOT / 'source/build', prefix='text-localization-') as tmp:
            path = Path(tmp) / 'Ver1_100010101.cpk'
            archive = cpk.create(cpk.CpkPreset.FILENAME_ID)
            archive.add_bytes(('210001,' + source + '\n').encode('utf8'),
                              '100010101_event_text.txt', id=1)
            archive.add_bytes(b'210001^^^^^^^^\n', '100010101_event_text_sg.txt', id=2)
            archive.add_bytes(b'300000,Thief\n', '100010101_event_teller.txt', id=3)
            path.write_bytes(archive.save_bytes())
            with patch.object(content, '_DIALOGUE_ENGLISH', {
                    key: {'source': source, 'english': english}}), \
                    patch.object(content, 'scene_tellers', return_value={'200123': 'Farmer'}), \
                    patch.object(content, 'common_ids', return_value=set()):
                data, changed = content.localized_package(path, {'fixture': []})
            path.write_bytes(data)
            tables = members(path)
            actual = content.localized_rows(tables['100010101_event_text_sg.txt'])['210001'][0]
            self.assertEqual(actual, english.replace('200123', '300123'))
            self.assertIn(b'300123^Farmer', tables['100010101_event_teller_sg.txt'])
            self.assertTrue(changed)

    def test_reviewed_japanese_base_fills_blank_english_without_changing_commands(self):
        source = '<name=100000 レイン><br>出発しよう。<keywait>'
        english = "<name=100000 レイン><br>Let's go.<keywait>"
        key = hashlib.sha256(source.encode('utf8')).hexdigest()
        with patch.object(content, '_DIALOGUE_ENGLISH', {
                key: {'source': source, 'english': english}}):
            merged, changed = content.merge_localized(
                ('210001,' + source + '\n').encode('utf8'),
                '210001^^保留^Keep French\n'.encode('utf8'))
        self.assertEqual(changed, 1)
        self.assertEqual(content.localized_rows(merged)['210001'][:3],
                         [english, '保留', 'Keep French'])
        self.assertTrue(content.english_source(english))
        self.assertFalse(content.english_source(source))

    def test_generated_header_lookup_preserves_indexes_and_payloads(self):
        for preset in (cpk.CpkPreset.FILENAME, cpk.CpkPreset.FILENAME_ID):
            with self.subTest(preset=preset):
                archive = cpk.create(preset)
                for i, name in enumerate(('map.bin', 'map_text_sg.txt', 'mapchip.bin')):
                    archive.add_bytes(('payload ' + name).encode(), name, id=7 + i)
                original = archive.save_bytes()
                end = 16 + struct.unpack_from('<Q', original, 8)[0]
                repaired = content.global_cpk_header(original[:end]) + original[end:]
                header = utf.Utf.load_bytes(repaired[16:end])
                self.assertEqual(header.value(0, 'Sorted'), 0)
                if header.value(0, 'CpkMode') == 2:
                    self.assertEqual(header.value(0, 'EID'), 1)
                self.assertEqual(repaired[end:], original[end:])
                self.assertEqual(len(repaired), len(original))
                self.assertEqual(content.global_cpk_header(repaired[:end]), repaired[:end])

    def test_staged_header_repair_updates_manifest_once(self):
        with tempfile.TemporaryDirectory(dir=ROOT / 'source/build', prefix='text-localization-') as tmp:
            folder = Path(tmp)
            archive = cpk.create(cpk.CpkPreset.FILENAME_ID)
            archive.add_bytes(b'unchanged map payload', 'map.bin', id=9)
            target = folder / 'map.cpk'
            original = archive.save_bytes()
            target.write_bytes(original)
            manifest = folder / 'manifest.json'
            manifest.write_text(json.dumps([{'path': 'map.cpk',
                                             'sha256': hashlib.sha256(original).hexdigest()}]))
            self.assertEqual(content.repair_staged_indexes(folder), 1)
            record = json.loads(manifest.read_text())[0]
            self.assertEqual(record['sha256'], hashlib.sha256(target.read_bytes()).hexdigest())
            self.assertTrue(record['global_filename_lookup_linear'])
            self.assertTrue(record['global_extended_id_index'])
            self.assertEqual(content.repair_staged_indexes(folder), 0)
            rebuilt = cpk.Cpk.load_bytes(target.read_bytes())
            self.assertEqual(rebuilt.file_infos()[0].id, 9)
            self.assertEqual(rebuilt.file_bytes(0), b'unchanged map payload')

    def test_original_japanese_teller_encoding(self):
        self.assertEqual(list(content.text_rows('300001,レジスタンス女性'.encode('cp932'))),
                         [('300001', 'レジスタンス女性')])

    def test_header_repair_updates_only_matching_derived_source_hashes(self):
        with tempfile.TemporaryDirectory(dir=ROOT / 'source/build', prefix='text-localization-') as tmp:
            root = Path(tmp)
            folder = root / 'overlay'
            folder.mkdir()
            manifest = folder / 'manifest.json'
            rows = [{'path': 'derived.cpk', 'source': 'memorial_fill/map.cpk', 'source_sha256': 'old'},
                    {'path': 'other.cpk', 'source': 'client/files/map.cpk', 'source_sha256': 'retail'}]
            manifest.write_text(json.dumps(rows))
            with patch.object(content, 'DATA', root):
                self.assertEqual(content.refresh_staged_sources({'memorial_fill/map.cpk': ('old', 'new')}), 1)
                self.assertEqual(content.refresh_staged_sources({'memorial_fill/map.cpk': ('old', 'new')}), 0)
                with self.assertRaises(ValueError):
                    content.refresh_staged_sources({'memorial_fill/map.cpk': ('unexpected', 'changed')})
            actual = json.loads(manifest.read_text())
            self.assertEqual(actual[0]['source_sha256'], 'new')
            self.assertEqual(actual[1], rows[1])

    def test_missing_map_choice_default_keeps_existing_translations(self):
        defaults = content.MAP_ENGLISH_DEFAULTS['111020100']
        merged, count = content.merge_localized(b'110070,Yes\n', b'110070^Yes^^^^^^^\n', defaults=defaults)
        self.assertEqual(count, 1)
        self.assertEqual(content.localized_rows(merged)['100071'], ['No'] + [''] * 7)
        self.assertEqual(content.merge_localized(b'110070,Yes\n', merged, defaults=defaults), (merged, 0))
        existing = b'100071^Keep^ZH^KO^FR^DE^ES^TH^ID\n'
        self.assertEqual(content.merge_localized(b'', existing, defaults=defaults), (existing, 0))

    def test_translation_keeps_commands_and_other_languages(self):
        source = '<name=300001><br>Example Japanese source<wait=30<br>'
        english = '<name=300001><br>English translation<wait=30><br>'
        archive = cpk.create(cpk.CpkPreset.FILENAME_ID)
        archive.add_bytes(('210001^' + source + '^ZH^KO^FR^DE^ES^TH^ID\n').encode('utf8'),
                          '123_event_text_sg.txt', id=7)
        key = hashlib.sha256(source.encode('utf8')).hexdigest()
        with patch.object(content, '_DIALOGUE_ENGLISH', {key: {'source': source, 'english': english}}):
            self.assertEqual(content.apply_english_dialogue(archive, {'123_event_text_sg.txt': 0}), 1)
        self.assertEqual(content.localized_rows(archive.file_bytes(0))['210001'],
                         [english, 'ZH', 'KO', 'FR', 'DE', 'ES', 'TH', 'ID'])

    def test_new_localized_member_preserves_original_native_ids(self):
        with tempfile.TemporaryDirectory(dir=ROOT / 'source/build', prefix='text-localization-') as tmp:
            archive = cpk.create(cpk.CpkPreset.FILENAME_ID)
            archive.add_bytes(b'unchanged original map binary', 'map.bin', id=7)
            archive.add_bytes(b'110001,Original English text\n', 'map_text.txt', id=8)
            source = Path(tmp) / 'map.cpk'
            source.write_bytes(archive.save_bytes())
            data, changed = content.localized_package(source)
            target = Path(tmp) / 'localized.cpk'
            target.write_bytes(data)
            rebuilt = cpk.load(str(target))
            ids = {e.full_path: e.id for e in rebuilt.file_infos()}
            self.assertTrue(changed)
            self.assertEqual(ids, {'map.bin': 7, 'map_text.txt': 8, 'map_text_sg.txt': 9})
            self.assertEqual(members(target)['map.bin'], b'unchanged original map binary')
            # The native reader memory-maps the file on Windows.
            del rebuilt

    def test_accepted_translation_sources_and_command_streams(self):
        records = json.loads((ROOT / 'source/server/content/dialogue_en.json').read_text(encoding='utf8'))['translations']
        self.assertTrue(records)
        for key, row in records.items():
            with self.subTest(source=key):
                self.assertEqual(hashlib.sha256(row['source'].encode('utf8')).hexdigest(), key)
                self.assertTrue(content.english_source(row['english']))
                self.assertEqual(re.findall(r'<[^>]+>', content.normalize_dialogue_commands(row['source'])),
                                 re.findall(r'<[^>]+>', row['english']))
                self.assertFalse(any(c in row['english'] for c in ('^', '\n', '\r', '\u2014')))

    def test_blank_english_preserves_existing_other_languages(self):
        base = b'210001,Restored English\n210002,Source variant\n'
        original = b'210001^^ZH^KO^FR^DE^ES^TH^ID\n210002^Retail English^^^^^^^\n'
        merged, count = content.merge_localized(base, original)
        self.assertEqual(count, 1)
        rows = content.localized_rows(merged)
        self.assertEqual(rows['210001'], ['Restored English', 'ZH', 'KO', 'FR', 'DE', 'ES', 'TH', 'ID'])
        self.assertEqual(rows['210002'][0], 'Retail English')
        self.assertEqual(content.merge_localized(base, merged), (merged, 0))

    def test_untranslated_source_does_not_fill_existing_english_gap(self):
        original = b'210001^^^^^^^^\n'
        self.assertEqual(content.merge_localized('210001,\u65e5\u672c\u8a9e\n'.encode('utf8'), original),
                         (original, 0))

    def test_reject_blank_rows_and_check_english_speaker_names(self):
        with tempfile.TemporaryDirectory(dir=ROOT / 'source/build', prefix='text-localization-') as tmp:
            archive = cpk.create(cpk.CpkPreset.FILENAME_ID)
            for i, (name, data) in enumerate({
                '123_event_text.txt': b'210001,Hello\n210002,World\n210003,Review\n',
                '123_event_text_sg.txt': ('210001^^^^^^^^\n210002^<name=300001>Hello^^^^^^^\n'
                                          '210003^\u65e5\u672c\u8a9e^^^^^^^\n').encode('utf8'),
                '123_event_teller.txt': b'300001,Name\n',
                '123_event_teller_sg.txt': b'300001^^^^^^^^\n',
            }.items()):
                archive.add_bytes(data, name, id=i)
            path = Path(tmp) / 'scene.cpk'
            path.write_bytes(archive.save_bytes())
            issues, _ = inspect(path, True)
            self.assertEqual({i['kind'] for i in issues},
                             {'blank English dialogue', 'unnamed English speakers',
                              'non-English dialogue needs review'})

    def test_seven_digit_and_deliberately_unnamed_speakers(self):
        archive = cpk.create(cpk.CpkPreset.FILENAME_ID)
        for i, (name, data) in enumerate({
            '123_event_text.txt': b'210001,<name=2001404>Hi\n210002,<name=300002>Narration\n',
            '123_event_text_sg.txt': b'210001^<name=2001404>Hi^^^^^^^\n210002^<name=300002>Narration^^^^^^^\n',
            '123_event_teller.txt': b'2001404,Louise\n300002,\n',
            '123_event_teller_sg.txt': b'2001404^Louise^^^^^^^\n300002^^^^^^^^\n',
        }.items()):
            archive.add_bytes(data, name, id=i)
        entries = {e.full_path: i for i, e in enumerate(archive.file_infos())}
        with patch.object(content, 'scene_tellers', return_value={}), \
             patch.object(content, 'common_ids', return_value=set()):
            self.assertEqual(content.add_scene_speakers(archive, entries, {}), 2)
        text = archive.file_bytes(entries['123_event_text_sg.txt']).decode('utf8')
        self.assertIn('<name=391404>Hi', text)
        self.assertNotIn('<name=300002>', text)
        self.assertIn('Narration', text)

    def test_repaired_production_packages_preserve_binary_members(self):
        manifest = json.loads((ROOT / 'data/overlay/manifest.json').read_text(encoding='utf8'))
        self.assertTrue(manifest)
        common = common_tellers()
        npc = common_npc_names()
        translations = json.loads((ROOT / 'source/server/content/dialogue_en.json')
                                  .read_text(encoding='utf8'))['translations']
        for row in manifest:
            if 'text_repairs' not in row:
                continue
            with self.subTest(package=row['path']):
                source = ROOT / 'data' / row['source']
                target = ROOT / 'data/overlay' / row['path']
                old, new = members(source), members(target)
                self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(), row['source_sha256'])
                self.assertEqual(hashlib.sha256(target.read_bytes()).hexdigest(), row['sha256'])
                self.assertTrue(old.keys() <= new.keys())
                for name, data in old.items():
                    if not name.endswith('.txt'):
                        self.assertEqual(data, new[name], name)
                    elif name.endswith('_sg.txt') and name in new:
                        target_rows = content.localized_rows(new[name])
                        for text_id, cells in content.localized_rows(data).items():
                            if not text_id.isdigit() or not cells:
                                continue
                            approved = translations.get(hashlib.sha256(cells[0].encode('utf8')).hexdigest())
                            if approved:
                                # Caption scope changes native speaker IDs. The
                                # approved prose and other commands must remain.
                                self.assertEqual(re.sub(r'<name=\d+>', '', target_rows[text_id][0]),
                                                 re.sub(r'<name=\d+>', '', approved['english']),
                                                 (name, text_id))
                issues, _ = inspect(target, True, common, npc)
                # Editor-only scenes use dummy actors that have no retail
                # captions. Their payloads and dialogue are still checked.
                if re.sub(r'^Ver\d+_', '', target.name) in development_packages():
                    issues = [i for i in issues if i['kind'] != 'unnamed English speakers']
                self.assertFalse([i for i in issues if i['kind'] in
                                  ('blank English dialogue', 'unnamed English speakers',
                                   'non-English dialogue needs review',
                                   'non-English map text or caption needs review',
                                   'unnamed native NPC captions')], issues)

    def test_native_index_selects_all_event_enemy_names(self):
        from decode_client_data import getter_manifest, decode, TRIPLET
        native = (ROOT / 'source/build/android/client/lib/arm64-v8a/libgame.so').read_bytes()
        manifest = {r['table']: r for r in getter_manifest(native).values()}
        for match in TRIPLET.finditer(native):
            table, token, key = (value.decode() for value in match.groups())
            manifest[table] = {'table': table, 'token': token, 'key': key}
        index = manifest['F_LOCALIZED_TEXT_MST']
        _, records = decode((ROOT / 'data/overlay/mst' / ('Ver709_' + index['token'] + '.dat'))
                            .read_bytes(), index['key'])
        original = {r['a4hXTIm0']: r for r in map(json.loads,
                    (ROOT / 'data/mst_decoded/F_LOCALIZED_TEXT_MST.ndjson')
                    .read_text(encoding='utf8').splitlines())}
        selected = {r['a4hXTIm0']: r for r in records}
        for table, version in (('F_TEXT_MONSTER_NAME', '227'), ('F_TEXT_TOWN_STORE_OWNER_NAME', '85'),
                               ('F_TEXT_NPC_NAME', '30')):
            info, row = manifest[table], selected[table]
            path = ROOT / 'data/overlay/localized_texts/en' / ('Ver' + version + '_' + info['token'] + '.dat')
            data = path.read_bytes()
            self.assertEqual(row['00zAYGYS'], version)
            self.assertEqual(row['zptmZGqa'], hashlib.md5(data).hexdigest())
            self.assertEqual(row['MLOSu5E0'], str(len(data)))
            self.assertEqual({k: v for k, v in row.items() if k not in ('00zAYGYS', 'zptmZGqa', 'MLOSu5E0')},
                             {k: v for k, v in original[table].items()
                              if k not in ('00zAYGYS', 'zptmZGqa', 'MLOSu5E0')})
        for table in original.keys() - {'F_TEXT_MONSTER_NAME', 'F_TEXT_TOWN_STORE_OWNER_NAME', 'F_TEXT_NPC_NAME'}:
            self.assertEqual(selected[table], original[table])
        row = selected['F_TEXT_MONSTER_NAME']
        info = manifest['F_TEXT_MONSTER_NAME']
        _, names = decode((ROOT / 'data/overlay/localized_texts/en' /
                           ('Ver' + row['00zAYGYS'] + '_' + info['token'] + '.dat')).read_bytes(),
                          info['key'], localized=True)
        names = {r['key']: r['v'][0] for r in names}
        expected = {}
        for file in ('event_battles', 'colosseum_encounters', 'event_encounters'):
            expected.update(json.loads((ROOT / 'source/server' / (file + '.json'))
                                       .read_text(encoding='utf8'))['local_monster_names'])
        self.assertTrue(expected)
        for key, name in expected.items():
            self.assertEqual(names.get('MST_MONSTER_NAME_' + key), name, key)
        info = manifest['F_TEXT_NPC_NAME']
        _, records = decode((ROOT / 'data/overlay/localized_texts/en' /
                              ('Ver30_' + info['token'] + '.dat')).read_bytes(),
                             info['key'], localized=True)
        actual = {r['key']: r['v'][0] for r in records}
        reviewed = json.loads((ROOT / 'source/server/content/dialogue_en.json').read_text(encoding='utf8'))
        for key, row in reviewed['npc_names'].items():
            self.assertEqual(actual['MST_NPC_NAME_' + key], row['english'])


if __name__ == '__main__':
    unittest.main()
