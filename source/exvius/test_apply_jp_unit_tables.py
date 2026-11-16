"""Check composite upgrades and native ciphertext preservation without writes."""
import json
import unittest

from apply_jp_unit_tables import decrypt_line, encode_row, patch_decoded, patch_native
from decode_client_data import decode


class NativePatches(unittest.TestCase):
    key = 'Test1234'
    fields = ['unit', 'ability', 'level']

    def records(self):
        return [
            {'unit': '820000107', 'ability': '50', 'level': '1', 'power': '100'},
            {'unit': '820000107', 'ability': '50', 'level': '2', 'power': '200'},
            {'unit': '999', 'ability': '50', 'level': '2', 'power': '300'},
        ]

    def test_composite_upgrade_not_duplicate_and_other_rows_exact(self):
        for mode in ('cbc', 'ecb'):
            for layers in (1, 2):
                with self.subTest(mode=mode, layers=layers):
                    old = self.records()
                    lines = [encode_row(r, self.key, mode, layers) for r in old]
                    raw = b'\r\n' + b'\r\n'.join(lines) + b'\r\n\r\n'
                    changed = dict(old[1], power='900')
                    new = {'unit': '820000107', 'ability': '50', 'level': '3', 'power': '1000'}
                    result, stats = patch_native(raw, self.key, self.fields, [changed, new])
                    self.assertEqual(decode(result, self.key)[1], [old[0], changed, old[2], new])
                    self.assertEqual(result.splitlines()[1], lines[0])
                    self.assertEqual(result.splitlines()[3], lines[2])
                    self.assertEqual(stats['replaced_rows'], 1)
                    self.assertEqual(stats['appended_rows'], 1)
                    self.assertEqual(stats['source_padding_layers'], [layers])
                    self.assertEqual(decrypt_line(result.splitlines()[2], self.key, mode)[1], layers)
                    same, second = patch_native(result, self.key, self.fields, [changed, new])
                    self.assertEqual(same, result)
                    self.assertEqual(second['replaced_rows'], 0)
                    self.assertEqual(second['appended_rows'], 0)

    def test_padding_bytes_that_are_json_whitespace(self):
        for pad in (9, 10, 13):
            row = {'unit': '1', 'ability': '2', 'level': '3', 'value': ''}
            while (16 - len(json.dumps(row, separators=(',', ':')).encode()) % 16) != pad:
                row['value'] += 'x'
            for mode in ('cbc', 'ecb'):
                encrypted = encode_row(row, self.key, mode, 2)
                self.assertEqual(decrypt_line(encrypted, self.key, mode), (row, 2))
                result, _ = patch_native(encrypted, self.key, self.fields, [dict(row, value='updated')])
                self.assertEqual(decrypt_line(result, self.key, mode)[1], 2)

    def test_duplicates_missing_identity_and_type_changes_rejected(self):
        row = self.records()[0]
        line = encode_row(row, self.key, 'cbc', 2)
        with self.assertRaisesRegex(ValueError, 'duplicate composite'):
            patch_native(line + b'\n' + line, self.key, self.fields, [row])
        with self.assertRaisesRegex(ValueError, 'duplicate composite'):
            patch_native(line, self.key, self.fields, [row, row])
        with self.assertRaisesRegex(ValueError, 'identity field'):
            patch_native(line, self.key, self.fields, [{'unit': '1'}])
        with self.assertRaisesRegex(ValueError, 'value types'):
            patch_native(line, self.key, self.fields, [dict(row, level=1)])

    def test_decoded_merge_preserves_other_raw_lines(self):
        old = self.records()
        lines = [json.dumps(r, ensure_ascii=False, indent=None).encode() for r in old]
        raw = b'\n'.join(lines)
        changed = dict(old[1], power='900')
        new = {'unit': '1', 'ability': '2', 'level': '3', 'power': '4'}
        out, stats = patch_decoded(raw, self.fields, [changed, new])
        self.assertEqual(out.splitlines()[0], lines[0])
        self.assertEqual(out.splitlines()[2], lines[2])
        self.assertEqual([json.loads(s) for s in out.splitlines()], [old[0], changed, old[2], new])
        self.assertEqual(stats['unchanged_unrequested_records'], 2)

    def test_merge_fields_is_explicit_and_preserves_extra_columns(self):
        old = self.records()[0]
        raw = encode_row(old, self.key, 'ecb', 2)
        patch = {k: old[k] for k in self.fields}
        patch['new'] = 'yes'
        out, _ = patch_native(raw, self.key, self.fields, [patch], operation='merge_fields')
        self.assertEqual(decode(out, self.key)[1], [dict(old, new='yes')])

    def test_native_acquisition_bucket_replaces_all_rows_without_collapsing(self):
        fields = ['unit', 'rarity', 'level']
        first = {'unit': '309000304', 'rarity': '6', 'level': '1', 'skills': '214510'}
        second = dict(first, skills='108001')
        unrelated = {'unit': '999', 'rarity': '6', 'level': '1', 'skills': 'original'}
        upgraded = dict(first, skills='830000001')
        extra = dict(first, skills='830000002')
        fresh = {'unit': '820000304', 'rarity': '6', 'level': '1', 'skills': '830000003'}
        for mode in ('cbc', 'ecb'):
            with self.subTest(mode=mode):
                # Buckets may be interleaved. Both unrelated duplicate rows
                # must survive byte-for-byte, and exact selected rows can reuse
                # their ciphertext while the bucket's other rows are upgraded.
                old = [first, unrelated, second, unrelated]
                lines = [encode_row(r, self.key, mode, 2) for r in old]
                raw = b'\r\n'.join(lines)
                out, stats = patch_native(raw, self.key, fields,
                                          [upgraded, second, extra, fresh], operation='replace_groups')
                values = decode(out, self.key)[1]
                self.assertEqual(values, [upgraded, second, extra, unrelated, unrelated, fresh])
                self.assertEqual(out.splitlines().count(lines[1]), 2)
                self.assertIn(lines[2], out.splitlines())
                self.assertEqual(stats['replaced_groups'], 1)
                same, _ = patch_native(out, self.key, fields,
                                       [upgraded, second, extra, fresh], operation='replace_groups')
                self.assertEqual(same, out)

    def test_decoded_bucket_preserves_duplicate_unselected_rows(self):
        fields = ['unit', 'level']
        one = {'unit': '1', 'level': '1', 'skills': 'A'}
        two = dict(one, skills='B')
        other = {'unit': '9', 'level': '1', 'skills': 'keep'}
        raw = b'\n'.join(json.dumps(r).encode() for r in [one, two, other, other])
        replacement = [dict(one, skills='C'), two]
        out, stats = patch_decoded(raw, fields, replacement, operation='replace_groups')
        self.assertEqual([json.loads(s) for s in out.splitlines()], replacement + [other, other])
        self.assertEqual(stats['unchanged_unrequested_records'], 2)

    def test_english_correction_guards_existing_meaningful_text(self):
        old = {'unit': '1', 'name': 'Gustav XIII', 'other': 'keep'}
        guard = [{'identity': {'unit': '1'}, 'field': 'name',
                  'prior_english': 'Gustav XIII', 'english': 'Gustave XIII'}]
        patch = [{'unit': '1', 'name': 'Gustave XIII'}]
        raw = encode_row(old, self.key, 'cbc', 2)
        out, stats = patch_native(raw, self.key, ['unit'], patch, operation='merge_fields', prior_english_guard=guard)
        self.assertEqual(decode(out, self.key)[1], [dict(old, name='Gustave XIII')])
        same, _ = patch_native(out, self.key, ['unit'], patch, operation='merge_fields', prior_english_guard=guard)
        self.assertEqual(same, out)
        unexpected = encode_row(dict(old, name='Another meaningful name'), self.key, 'cbc', 2)
        with self.assertRaisesRegex(ValueError, 'guard rejected'):
            patch_native(unexpected, self.key, ['unit'], patch, operation='merge_fields', prior_english_guard=guard)
        with self.assertRaisesRegex(ValueError, 'guard rejected'):
            patch_decoded(json.dumps(dict(old, name='Another meaningful name')).encode(), ['unit'], patch,
                          operation='merge_fields', prior_english_guard=guard)


if __name__ == '__main__':
    unittest.main()
