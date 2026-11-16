"""Exercise GL9 seekable byte offsets and the King Mog description path."""
import struct
import tempfile
import unittest
from pathlib import Path

from decode_client_data import client_manifest, decode
from native_master_index import SCHEMAS, build_index, paired_index, validate_release_indexes

def _scratch(root):
    path = root / 'build' / 'scratch'
    path.mkdir(parents=True, exist_ok=True)
    return path


ROOT = Path(__file__).resolve().parents[2]


class NativeMasterIndexes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = client_manifest(ROOT / 'repository snapshots/FFBE-Global-v9.0.0-original.apk')

    def sources(self, table):
        info = next(r for r in self.manifest.values() if r['table'] == table)
        original = next((ROOT / 'data/client/files/mst').glob('Ver*_' + info['token'] + '.dat'))
        return info, original, ROOT / 'data/overlay/mst' / original.name

    def test_original_native_indexes_reproduce_byte_for_byte(self):
        for table in SCHEMAS:
            with self.subTest(table=table):
                info, original, _ = self.sources(table)
                path, raw = paired_index(table, original, original.read_bytes(), info['key'])
                self.assertEqual(raw, path.read_bytes())

    def test_generated_raid_banner_index_decrypts_every_direct_and_type_lookup(self):
        import json
        from build_raid_summon_cache import build_files
        from prepare_offline_cache import raid_reward_banners
        info, original, _ = self.sources('F_BANNER_MST')
        files = build_files()
        raw = files['native/mst/Ver595_' + info['token'] + '.dat']
        index = files['native/mst/' + info['token'] + '.i']
        self.assertEqual(index, build_index('F_BANNER_MST', raw, info['key'], 595))
        _, rows = decode(raw, info['key'])
        count = struct.unpack_from('<H', index, 8)[0]
        direct = {}
        for i in range(count):
            ident, start, size = struct.unpack_from('<iII', index, 10 + 12 * i)
            _, found = decode(raw[start:start + size], info['key'])
            self.assertEqual(int(found[0]['fSxqkF10']), ident)
            direct[ident] = found[0]
        offset = 10 + count * 12
        group_count = struct.unpack_from('<H', index, offset)[0]
        offset += 2
        groups = {}
        for _ in range(group_count):
            kind, length = struct.unpack_from('<iH', index, offset)
            offset += 6
            groups[kind] = list(struct.unpack_from('<' + 'i' * length, index, offset))
            offset += length * 4
        self.assertEqual(index[offset:], bytes.fromhex('beff0000'))
        expected = {}
        for row in rows:
            if '1' in row.get('T4o9heqC', '').split(','):
                expected.setdefault(int(row['w2A76noc']), []).append(int(row['fSxqkF10']))
        self.assertEqual(groups, expected)
        links = json.loads((ROOT / 'source/server/raid_summon_links.json').read_text('utf-8'))['links']
        self.assertEqual(len(links), 71)
        for link in links:
            ident = int(link['banner_id'])
            self.assertIn(ident, groups[6])
            self.assertEqual(direct[ident]['1X65WPLU'], link['gacha_id'])
        with tempfile.TemporaryDirectory(dir=_scratch(ROOT)) as scratch:
            target = Path(scratch) / ('Ver595_' + info['token'] + '.dat')
            self.assertEqual(raid_reward_banners(original, target, info['key']), raw)
            self.assertEqual(target.read_bytes(), raw)
            self.assertEqual(target.with_name(info['token'] + '.i').read_bytes(), index)

    def test_all_repaired_direct_offsets_identify_the_requested_record(self):
        for table, (identity, _) in SCHEMAS.items():
            with self.subTest(table=table):
                info, original, effective = self.sources(table)
                effective = effective if effective.exists() else original
                raw = effective.read_bytes()
                index, expected = paired_index(table, effective, raw, info['key'])
                active_index = index if index.exists() else original.with_name(index.name)
                self.assertEqual(active_index.read_bytes(), expected)
                _, rows = decode(raw, info['key'])
                fields = (identity,) if isinstance(identity, str) else identity
                entry_format = '<' + 'i' * len(fields) + 'II'
                entry_size = struct.calcsize(entry_format)
                offsets, offset = {}, 0
                for line, row in zip(raw.splitlines(keepends=True), rows):
                    offsets[(offset, len(line.rstrip(b'\r\n')))] = tuple(int(row[field]) for field in fields)
                    offset += len(line)
                count = struct.unpack_from('<H', expected, 8)[0]
                for i in range(count):
                    entry = struct.unpack_from(entry_format, expected, 10 + entry_size * i)
                    self.assertEqual(offsets[entry[-2:]], entry[:-2])

    def test_ai_pair_keys_and_group_members_survive_native_group_append(self):
        from collections import Counter
        from apply_jp_unit_tables import patch_native
        info, original, _ = self.sources('F_AI_MST')
        raw = original.read_bytes()
        _, rows = decode(raw, info['key'])
        counts = Counter(row['8a6gAwN9'] for row in rows)
        ai = next(key for key, count in counts.items() if count >= 3)
        selected = [(line, row) for line, row in zip(raw.splitlines(keepends=True), rows)
                    if row['8a6gAwN9'] == ai][:3]
        other = next((line, row) for line, row in zip(raw.splitlines(keepends=True), rows)
                     if row['8a6gAwN9'] != ai)
        fixture = b''.join(pair[0] for pair in [selected[1], other, selected[0], selected[2]])
        added = [dict(selected[0][1], **{'8a6gAwN9': '204171001', 'w7VR6ypY': str(order)})
                 for order in [1, 2]]
        changed, _ = patch_native(fixture, info['key'], ['8a6gAwN9'], added,
                                  operation='replace_groups')
        index = build_index('F_AI_MST', changed, info['key'], 335)
        count = struct.unpack_from('<H', index, 8)[0]
        self.assertEqual(count, 6)
        direct = {}
        for i in range(count):
            key, order, start, size = struct.unpack_from('<iiII', index, 10 + 16 * i)
            _, found = decode(changed[start:start + size], info['key'])
            self.assertEqual((int(found[0]['8a6gAwN9']), int(found[0]['w7VR6ypY'])), (key, order))
            direct[key, order] = start, size
        offset = 10 + count * 16
        group_count = struct.unpack_from('<H', index, offset)[0]
        offset += 2
        groups = {}
        for _ in range(group_count):
            key, length = struct.unpack_from('<iH', index, offset)
            offset += 6
            groups[key] = [struct.unpack_from('<ii', index, offset + i * 8) for i in range(length)]
            offset += length * 8
        self.assertEqual(groups[204171001], [(204171001, 1), (204171001, 2)])
        self.assertEqual(groups[int(ai)], [(int(ai), int(pair[1]['w7VR6ypY']))
                                          for pair in [selected[1], selected[0], selected[2]]])
        self.assertEqual(index[offset:], bytes.fromhex('beff0000'))
        self.assertIn((204171001, 2), direct)

    def test_every_king_mog_offer_description_decrypts_via_its_native_index(self):
        import json
        def table(name):
            return [json.loads(line) for line in (ROOT / 'data/mst_decoded' / (name + '.ndjson')).read_bytes().splitlines()]
        stock = [r for r in table('F_STORE_ITEM_MST') if r['Z20mNDvL'] == '7000458']
        medals = {r['S21FT3L8']: r for r in table('F_MEDAL_EXCHANGE_MST')}
        info, _, effective = self.sources('F_UNIT_EXPLAIN_MST')
        raw = effective.read_bytes()
        index = effective.with_name(info['token'] + '.i').read_bytes()
        count = struct.unpack_from('<H', index, 8)[0]
        entries = {ident: (start, size) for ident, start, size in
                   (struct.unpack_from('<iII', index, 10 + 12 * i) for i in range(count))}
        self.assertEqual(len(stock), 127)
        for product in stock:
            kind, unit, *_ = medals[product['6uIYE15X']]['7iJpH5zZ'].split(':')
            self.assertEqual(kind, '10')
            start, size = entries[int(unit)]
            _, rows = decode(raw[start:start + size], info['key'])
            self.assertEqual(rows[0]['3HriTp6B'], unit)
            self.assertTrue(rows[0]['fYhnz5N9'])

    def test_stale_original_abel_offset_reproduces_failure(self):
        info, original, effective = self.sources('F_UNIT_EXPLAIN_MST')
        index = original.with_name(info['token'] + '.i').read_bytes()
        count = struct.unpack_from('<H', index, 8)[0]
        ident, start, size = next(struct.unpack_from('<iII', index, 10 + 12 * i)
                                  for i in range(count)
                                  if struct.unpack_from('<i', index, 10 + 12 * i)[0] == 100006303)
        self.assertEqual(decode(original.read_bytes()[start:start + size], info['key'])[1][0]['3HriTp6B'], str(ident))
        with self.assertRaises(ValueError):
            decode(effective.read_bytes()[start:start + size], info['key'])

    def test_release_inputs_reject_stale_or_missing_pair(self):
        info, original, effective = self.sources('F_UNIT_EXPLAIN_MST')
        filename = 'native/mst/' + effective.name
        index = 'native/mst/' + info['token'] + '.i'
        registry = {'keyF_UNIT_EXPLAIN_MST': '244'}
        files = {filename: effective, index: effective.with_name(info['token'] + '.i')}
        self.assertEqual(validate_release_indexes(files, ROOT, registry), ['F_UNIT_EXPLAIN_MST'])
        files[index] = original.with_name(info['token'] + '.i')
        with self.assertRaisesRegex(ValueError, 'does not match'):
            validate_release_indexes(files, ROOT, registry)
        del files[index]
        with self.assertRaisesRegex(ValueError, 'does not match'):
            validate_release_indexes(files, ROOT, registry)

    def test_existing_master_writer_emits_the_matching_pair(self):
        from prepare_offline_cache import exbonus_master
        info, original, _ = self.sources('F_UNIT_EXPLAIN_MST')
        _, rows = decode(original.read_bytes(), info['key'])
        changed = dict(rows[0], fYhnz5N9='A different length for the native index regression.')
        with tempfile.TemporaryDirectory(dir=_scratch(ROOT)) as scratch:
            target = Path(scratch) / original.name
            exbonus_master(original, target, info['key'], 'F_UNIT_EXPLAIN_MST',
                           {'key': '3HriTp6B', 'rows': [changed], 'replace': True})
            index, expected = paired_index('F_UNIT_EXPLAIN_MST', target, target.read_bytes(), info['key'])
            self.assertEqual(index.read_bytes(), expected)
            self.assertNotEqual(expected, original.with_name(index.name).read_bytes())

    def test_unknown_index_schema_is_not_guessed(self):
        self.assertIsNone(paired_index('F_UNREVIEWED_MST', Path('Ver1_12345678.dat'), b'', '12345678'))

    def test_count_overflow_is_rejected(self):
        from native_master_index import short_count
        with self.assertRaisesRegex(ValueError, 'overflow'):
            short_count(65536)


if __name__ == '__main__':
    unittest.main()
