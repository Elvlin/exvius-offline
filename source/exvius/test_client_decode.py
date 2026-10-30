"""Validate source-data decoding and refusal of corrupt or mixed records."""
import base64
import json
import unittest

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from decode_client_data import decode, json_record, key16, localized_records


def encrypt(value, mode, double=False):
    raw = json.dumps(value).encode()
    pad = 16 - len(raw) % 16
    raw += bytes([pad]) * pad
    if double:
        raw += b'\x10' * 16
    cipher_mode = modes.CBC(b'dZMjkk8gFDzKHlsx') if mode == 'cbc' else modes.ECB()
    op = Cipher(algorithms.AES(key16('fixture1')), cipher_mode).encryptor()
    return base64.b64encode(op.update(raw) + op.finalize())


class ClientDecode(unittest.TestCase):
    def test_double_padded_cbc_multiple_records_preserved(self):
        values = [{'id': 1, 'name': 'fixture'}, {'id': 2, 'count': 10}]
        raw = b'\n'.join(encrypt(v, 'cbc', double=True) for v in values)
        self.assertEqual(decode(raw, 'fixture1'), ('cbc', values))

    def test_ecb_generation_preserved(self):
        value = {'id': 3, 'count': 20}
        self.assertEqual(decode(encrypt(value, 'ecb'), 'fixture1'), ('ecb', [value]))

    def test_corrupt_second_record_does_not_return_partial_content(self):
        raw = encrypt({'id': 1}, 'cbc') + b'\nnot-base64'
        with self.assertRaises(ValueError):
            decode(raw, 'fixture1')

    def test_wrong_key_and_invalid_padding_rejected(self):
        with self.assertRaises(ValueError):
            decode(encrypt({'id': 1}, 'cbc'), 'wrongkey')
        with self.assertRaises(ValueError):
            json_record(b'{"id":1}\x01\x02')

    def test_localized_keys_and_all_value_columns_preserved(self):
        raw = b'MST_FIXTURE_1^First^Second\nMST_FIXTURE_2^Third^Fourth\n'
        self.assertEqual(localized_records(raw), [
            {'key': 'MST_FIXTURE_1', 'v': ['First', 'Second']},
            {'key': 'MST_FIXTURE_2', 'v': ['Third', 'Fourth']},
        ])

    def test_structured_localized_keys_keep_original_spacing(self):
        self.assertEqual(localized_records(b'{"id": 1}^Fixture^Other\n'), [
            {'key': '{"id": 1}', 'v': ['Fixture', 'Other']},
        ])


if __name__ == '__main__':
    unittest.main()
