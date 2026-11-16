"""Apply validated original JP unit records to existing native cache versions.

Only explicitly identified records change. Composite keys distinguish upgrades
from new acquisition, LB-level and EX records. Unrelated encrypted and decoded
lines remain byte-identical. No resource version, save or APK is changed.
"""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import sys
import tempfile

from decode_client_data import decode
from native_master_index import paired_index

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'server'))
from ffbe_crypto import aes_ecb_decrypt, cbc_decrypt, cbc_encrypt, key16
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

def _scratch(root):
    path = root / 'build' / 'scratch'
    path.mkdir(parents=True, exist_ok=True)
    return path

ROOT = Path(__file__).resolve().parents[2]
READY = 'VALIDATED_READY_TO_APPLY'
DEFAULT_CONTRACT = ROOT / 'Japan content/Earlier JP crossovers/Sources/native-unit-import.json'
RECEIPT = ROOT / 'logs/jp-unit-native-integration.json'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def identity(row, fields):
    if not fields or len(set(fields)) != len(fields) or not all(isinstance(k, str) and k for k in fields):
        raise ValueError('Explicit distinct identity_fields are required.')
    result = []
    for field in fields:
        if field not in row or isinstance(row[field], (dict, list, bool)):
            raise ValueError('Missing or nonscalar native identity field: ' + field)
        value = row[field]
        result.append((type(value).__name__, json.dumps(value, ensure_ascii=False, separators=(',', ':'))))
    return tuple(result)


def indexed(values, fields, label):
    result = {}
    for row in values:
        if not isinstance(row, dict):
            raise ValueError(label + ' includes a nonobject record.')
        key = identity(row, fields)
        if key in result:
            raise ValueError(label + ' has duplicate composite identity: ' + repr(key))
        result[key] = row
    return result


def parts(raw):
    """Retain each original line ending and every empty line exactly."""
    result = []
    for line in raw.splitlines(keepends=True):
        if line.endswith(b'\r\n'):
            result.append((line[:-2], b'\r\n'))
        elif line.endswith((b'\n', b'\r')):
            result.append((line[:-1], line[-1:]))
        else:
            result.append((line, b''))
    return result


def decrypt_line(body, key, mode):
    if mode == 'cbc':
        plain = cbc_decrypt(key16(key), body.decode('ascii'))
        outer = 1
    else:
        plain = aes_ecb_decrypt(key16(key), base64.b64decode(body, validate=True))
        outer = 0
    # As in exbonus_master's ECB path, strip real PKCS7 layers before parsing.
    # JSON accepts tab/newline/carriage-return whitespace, so parsing first
    # would miss an inner padding layer whose byte happens to be 9, 10 or 13.
    layers = outer
    while plain:
        pad = plain[-1]
        if not 1 <= pad <= 16 or plain[-pad:] != bytes([pad]) * pad:
            break
        plain = plain[:-pad]
        layers += 1
        if layers > 4:
            raise ValueError('Unsupported native padding depth.')
    row = json.loads(plain.decode('utf-8'))
    if not isinstance(row, dict) or not layers:
        raise ValueError('Native record is not a padded JSON object.')
    return row, layers


def encode_row(row, key, mode, layers):
    if not 1 <= layers <= 4:
        raise ValueError('Native padding requires one to four proven layers.')
    body = json.dumps(row, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
    for _ in range(layers - (1 if mode == 'cbc' else 0)):
        pad = 16 - len(body) % 16
        body += bytes([pad]) * pad
    if mode == 'cbc':
        return cbc_encrypt(key16(key), body).encode('ascii')
    encryptor = Cipher(algorithms.AES(key16(key)), modes.ECB()).encryptor()
    return base64.b64encode(encryptor.update(body) + encryptor.finalize())


def patch_groups(raw, fields, updates, decode_one, encode_one, append_format=None):
    """Replace explicit buckets whose original schema allows repeated keys."""
    wanted, before, parsed, typed = {}, {}, [], {}
    for row in updates:
        if not isinstance(row, dict):
            raise ValueError('Requested group includes a nonobject record.')
        wanted.setdefault(identity(row, fields), []).append(row)
    for body, ending in parts(raw):
        if not body.strip():
            parsed.append((body, ending, None, None, None))
            continue
        row, fmt = decode_one(body)
        key = identity(row, fields)
        text = tuple(str(row[k]) for k in fields)
        if text in typed and typed[text] != key:
            raise ValueError('Active group source has inconsistent identity value types.')
        typed[text] = key
        before.setdefault(key, []).append((row, body, ending, fmt))
        parsed.append((body, ending, row, fmt, key))
    for key, values in wanted.items():
        same_text = typed.get(tuple(str(values[0][k]) for k in fields))
        if same_text is not None and same_text != key:
            raise ValueError('Requested group identity changes native field value types.')
    changed = {key for key in wanted if key in before and [r[0] for r in before[key]] != wanted[key]}
    new = set(wanted) - set(before)
    formats = {fmt for _, _, row, fmt, _ in parsed if row is not None}
    ending = next((end for _, end, _, _, _ in parsed if end), b'\n')
    output, expected, emitted = [], [], set()
    unchanged_lines = 0

    def emit_group(key):
        nonlocal unchanged_lines
        # Exact-row matching here only reuses already encrypted source bytes.
        # It is not an identity fallback and never drops repeated source rows.
        reusable = list(before.get(key, []))
        local_formats = {r[3] for r in reusable} or formats
        for row in wanted[key]:
            match = next((i for i, old in enumerate(reusable) if old[0] == row), None)
            if match is not None:
                _, body, _, _ = reusable.pop(match)
                unchanged_lines += 1
            else:
                fmt = append_format
                if fmt is None:
                    if len(local_formats) != 1:
                        raise ValueError('Group replacement padding is ambiguous; supply append_padding_layers.')
                    fmt = next(iter(local_formats))
                elif local_formats and fmt not in local_formats:
                    raise ValueError('Group replacement padding is not demonstrated by source records.')
                body = encode_one(row, fmt)
            output.append(body + ending)
            expected.append(row)
        emitted.add(key)

    for body, end, row, fmt, key in parsed:
        if row is not None and key in changed:
            if key not in emitted:
                emit_group(key)
            continue
        output.append(body + end)
        if row is not None:
            expected.append(row)
            unchanged_lines += 1
    for key in wanted:
        if key in new:
            if output and not output[-1].endswith((b'\r', b'\n')):
                output.append(ending)
            emit_group(key)
    result = b''.join(output)
    after = [decode_one(body)[0] for body, _ in parts(result) if body.strip()]
    if after != expected:
        raise ValueError('Grouped native record round-trip or order differs.')
    actual_groups = {}
    for row in after:
        actual_groups.setdefault(identity(row, fields), []).append(row)
    expected_groups = {key: [r[0] for r in values] for key, values in before.items()}
    expected_groups.update(wanted)
    if actual_groups != expected_groups:
        raise ValueError('Unselected native bucket changed or selected source rows were lost.')
    return result, {'before_rows': sum(len(v) for v in before.values()), 'after_rows': len(after),
                    'requested_rows': len(updates), 'requested_groups': len(wanted),
                    'replaced_groups': len(changed),
                    'replaced_rows': sum(len(before[k]) for k in changed),
                    'appended_rows': sum(len(wanted[k]) for k in new) + sum(max(0, len(wanted[k]) - len(before[k])) for k in changed),
                    'unchanged_lines': unchanged_lines,
                    'unchanged_unrequested_records': sum(len(v) for k, v in before.items() if k not in wanted)}


def patch_lines(raw, fields, updates, operation, decode_one, encode_one, append_format=None):
    """Shared native/decoded merger. No whole-JSON fallback identity exists."""
    if operation == 'replace_groups':
        return patch_groups(raw, fields, updates, decode_one, encode_one, append_format)
    if operation not in ('replace', 'merge_fields'):
        raise ValueError('Only replace, merge_fields or replace_groups is supported.')
    requested = indexed(updates, fields, 'Requested rows')
    original, parsed = {}, []
    text_keys = {}
    for body, ending in parts(raw):
        if not body.strip():
            parsed.append((body, ending, None, None))
            continue
        row, fmt = decode_one(body)
        ident = identity(row, fields)
        if ident in original:
            raise ValueError('Active source has duplicate composite identity: ' + repr(ident))
        original[ident] = row
        text = tuple(str(row[k]) for k in fields)
        if text in text_keys and text_keys[text] != ident:
            raise ValueError('Active source has inconsistent identity value types.')
        text_keys[text] = ident
        parsed.append((body, ending, row, fmt))
    for ident, row in requested.items():
        same_text = text_keys.get(tuple(str(row[k]) for k in fields))
        if same_text is not None and same_text != ident:
            raise ValueError('Requested identity changes native field value types.')
    expected = dict(original)
    for ident, row in requested.items():
        expected[ident] = dict(original.get(ident, {}), **row) if operation == 'merge_fields' else row
    formats = {fmt for _, _, row, fmt in parsed if row is not None}
    additions = [ident for ident in requested if ident not in original]
    if additions:
        if append_format is None:
            if len(formats) != 1:
                raise ValueError('Append format is ambiguous; supply explicit append_padding_layers.')
            append_format = next(iter(formats))
        elif formats and append_format not in formats:
            raise ValueError('Append padding is not demonstrated by an active native record.')
    output, changed, unchanged_ciphertext = [], 0, 0
    ending = next((end for _, end, _, _ in parsed if end), b'\n')
    for body, end, row, fmt in parsed:
        if row is not None:
            ident = identity(row, fields)
            replacement = expected[ident]
            if ident in requested and replacement != row:
                body = encode_one(replacement, fmt)
                changed += 1
            else:
                unchanged_ciphertext += 1
        output.append(body + end)
    for ident in additions:
        if output and not output[-1].endswith((b'\n', b'\r')):
            output.append(ending)
        output.append(encode_one(expected[ident], append_format) + ending)
    result = b''.join(output)
    after = []
    for body, _ in parts(result):
        if body.strip():
            row, _ = decode_one(body)
            after.append(row)
    if indexed(after, fields, 'Serialized rows') != expected:
        raise ValueError('Serialized typed-record round-trip differs.')
    expected_order = [identity(r, fields) for _, _, r, _ in parsed if r is not None] + additions
    if [identity(r, fields) for r in after] != expected_order:
        raise ValueError('Unrelated row order changed.')
    return result, {'before_rows': len(original), 'after_rows': len(after),
                    'requested_rows': len(requested), 'replaced_rows': changed,
                    'appended_rows': len(additions), 'unchanged_lines': unchanged_ciphertext,
                    'unchanged_unrequested_records': len(set(original) - set(requested))}


def verify_prior_english(values, fields, guards):
    if not guards:
        return
    existing = indexed(values, fields, 'English guard source')
    for guard in guards:
        key = identity(guard['identity'], fields)
        row = existing.get(key)
        if row is None or guard['field'] not in row:
            raise ValueError('Prior English guard target is absent.')
        if row[guard['field']] not in (guard['prior_english'], guard['english']):
            raise ValueError('Prior English guard rejected an unrelated current value: ' + guard['field'])


def patch_native(raw, key, fields, updates, operation='replace', append_padding_layers=None,
                 prior_english_guard=None):
    mode, before = decode(raw, key)
    verify_prior_english(before, fields, prior_english_guard)
    read = lambda body: decrypt_line(body, key, mode)
    write = lambda row, layers: encode_row(row, key, mode, layers)
    if [read(body)[0] for body, _ in parts(raw) if body.strip()] != before:
        raise ValueError('Per-line reader differs from established native decoder.')
    output, stats = patch_lines(raw, fields, updates, operation, read, write, append_padding_layers)
    after_mode, after = decode(output, key)
    if after_mode != mode:
        raise ValueError('Native encryption mode changed.')
    stats['mode'] = mode
    stats['unchanged_encrypted_lines'] = stats['unchanged_lines']
    stats['source_padding_layers'] = sorted({read(body)[1] for body, _ in parts(raw) if body.strip()})
    stats['unrelated_ciphertext_preserved'] = True
    stats['prior_english_fields_guarded'] = len(prior_english_guard or [])
    return output, stats


def patch_decoded(raw, fields, updates, operation='replace', prior_english_guard=None):
    if prior_english_guard:
        verify_prior_english([json.loads(s) for s in raw.splitlines() if s.strip()], fields, prior_english_guard)
    read = lambda body: (json.loads(body.decode('utf-8-sig')), 1)
    write = lambda row, _: json.dumps(row, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
    return patch_lines(raw, fields, updates, operation, read, write, append_format=1)


def atomic_write(path, raw):
    path.parent.mkdir(parents=True, exist_ok=True)
    scratch = _scratch(ROOT)
    scratch.mkdir(exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='jp-native-', suffix='.part', dir=scratch)
    try:
        with os.fdopen(fd, 'wb') as handle:
            handle.write(raw)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def verify_active_source(origin, raw, expected):
    if expected is None:
        return
    if not isinstance(expected, dict):
        raise ValueError('active_native_source must describe a resolved path or pack member.')

    def project_path(value):
        path = Path(value)
        path = path.resolve() if path.is_absolute() else (ROOT / path).resolve()
        if not path.is_relative_to(ROOT):
            raise ValueError('Active native source must stay inside the project.')
        return path.relative_to(ROOT).as_posix()

    if 'container' in expected and 'member' in expected:
        wanted = project_path(expected['container']) + '::' + PurePosixPath(expected['member']).as_posix()
    elif 'path' in expected:
        wanted = project_path(expected['path'])
        if expected.get('sha256') and sha(raw) != expected['sha256']:
            raise ValueError('Resolved active native path hash changed.')
    else:
        raise ValueError('active_native_source needs path or container/member.')
    if origin.replace('\\', '/') != wanted:
        raise ValueError('Effective native cache winner differs from the validated source: ' + origin)


def apply_contract(contract_path, apply=False, receipt_path=RECEIPT):
    from apply_jp_content import NativeCache
    contract_path = Path(contract_path).resolve()
    receipt_path = Path(receipt_path).resolve()
    if not receipt_path.is_relative_to((ROOT / 'logs').resolve()):
        raise ValueError('Native integration receipts belong in the existing logs folder.')
    contract_raw = contract_path.read_bytes()
    contract = json.loads(contract_raw)
    if contract.get('schema') != 1 or contract.get('status') != READY:
        raise ValueError('Only a finalized VALIDATED_READY_TO_APPLY schema1 contract can be consumed.')
    entries = contract.get('tables')
    if not isinstance(entries, list) or not entries or len({r['table'] for r in entries}) != len(entries):
        raise ValueError('Contract must name each table exactly once.')
    cache = NativeCache()
    pending, receipts, pending_indexes = [], [], []
    try:
        for entry in entries:
            table = entry['table']
            if not re.fullmatch(r'F_[A-Z0-9_]+_MST', table) or table not in cache.tables:
                raise ValueError('Unsupported native master table: ' + table)
            fields = entry['identity_fields']
            updates = entry.get('rows')
            source_sha = None
            if updates is None:
                path = (ROOT / entry['file']).resolve()
                if not path.is_relative_to(ROOT):
                    raise ValueError('Reviewed record source must stay inside the project.')
                raw = path.read_bytes()
                source_sha = sha(raw)
                if source_sha != entry['sha256']:
                    raise ValueError('Reviewed native row source changed: ' + table)
                updates = [json.loads(line) for line in raw.splitlines() if line.strip()]
            if not isinstance(updates, list) or not updates:
                raise ValueError('Every requested table needs explicit source records.')
            operation = entry.get('operation', 'replace')
            token, key = cache.tables[table]
            relative = entry['active_native_path']
            path = PurePosixPath(relative)
            if path.is_absolute() or '..' in path.parts or not re.fullmatch(r'mst/Ver\d+_' + re.escape(token) + r'\.dat', relative):
                raise ValueError('active_native_path must name this table in its existing mst cache version: ' + table)
            before, origin = cache.read(relative)
            verify_active_source(origin, before, entry.get('active_native_source'))
            expected_sha = entry.get('active_native_sha256')
            if expected_sha and sha(before) != expected_sha:
                raise ValueError('Active native source changed since contract validation: ' + table)
            after, stats = patch_native(before, key, fields, updates, operation, entry.get('append_padding_layers'), entry.get('prior_english_guard'))
            decoded_path = ROOT / 'data/mst_decoded' / (table + '.ndjson')
            decoded_before = decoded_path.read_bytes() if decoded_path.is_file() else b''
            expected_decoded = entry.get('decoded_baseline_sha256')
            if expected_decoded and sha(decoded_before) != expected_decoded:
                raise ValueError('Decoded baseline changed since validation: ' + table)
            canonical_sha = entry.get('expected_decoded_canonical_sha256')
            if canonical_sha:
                decoded_rows = [json.loads(line) for line in decoded_before.splitlines() if line.strip()]
                canonical = json.dumps(decoded_rows, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')
                if sha(canonical) != canonical_sha:
                    raise ValueError('Canonical decoded native content changed since validation: ' + table)
            decoded_after, decoded_stats = patch_decoded(decoded_before, fields, updates, operation, entry.get('prior_english_guard'))
            native_target = ROOT / 'data/overlay' / relative
            pending.append((native_target, after, decoded_path, decoded_after, relative, sha(before), decoded_before))
            index = paired_index(table, native_target, after, key)
            if index is not None:
                pending_indexes.append(index)
            receipts.append({'table': table, 'identity_fields': fields, 'operation': operation,
                             'source': origin, 'before_sha256': sha(before),
                             'output': native_target.relative_to(ROOT).as_posix(), 'after_sha256': sha(after),
                             'decoded_output': decoded_path.relative_to(ROOT).as_posix(),
                             'decoded_before_sha256': sha(decoded_before), 'decoded_after_sha256': sha(decoded_after),
                             'reviewed_row_source_sha256': source_sha, 'stats': stats,
                             'decoded_stats': decoded_stats})
        # Recheck every input after all serialization, before committing any table.
        if contract_path.read_bytes() != contract_raw:
            raise ValueError('Validated contract changed during preparation.')
        for _, _, decoded_path, _, relative, before_sha, decoded_before in pending:
            if sha(cache.read(relative)[0]) != before_sha or (decoded_path.read_bytes() if decoded_path.is_file() else b'') != decoded_before:
                raise ValueError('An active native or decoded input changed during preparation: ' + relative)
        result = {'status': 'APPLIED' if apply else 'VALIDATED_PREVIEW_NO_WRITES',
                  'contract': str(contract_path.relative_to(ROOT)), 'contract_sha256': sha(contract_raw),
                  'tables': receipts, 'resource_versions_changed': False, 'saves_changed': False,
                  'apk_built': False, 'enemy_records_fabricated': False}
        if apply:
            for native_path, native_raw, decoded_path, decoded_raw, _, _, _ in pending:
                atomic_write(native_path, native_raw)
                atomic_write(decoded_path, decoded_raw)
                if native_path.read_bytes() != native_raw or decoded_path.read_bytes() != decoded_raw:
                    raise ValueError('Committed native/decoded readback differs.')
            for index_path, index_raw in pending_indexes:
                atomic_write(index_path, index_raw)
                if index_path.read_bytes() != index_raw:
                    raise ValueError('Committed native index readback differs.')
            atomic_write(receipt_path, (json.dumps(result, ensure_ascii=False, indent=2) + '\n').encode('utf-8'))
        print(json.dumps({'status': result['status'], 'tables': len(receipts),
                          'requested_rows': sum(r['stats']['requested_rows'] for r in receipts),
                          'replaced_rows': sum(r['stats']['replaced_rows'] for r in receipts),
                          'appended_rows': sum(r['stats']['appended_rows'] for r in receipts),
                          'unrelated_ciphertext_preserved': True}), flush=True)
        return result
    finally:
        cache.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--contract', type=Path, default=DEFAULT_CONTRACT)
    parser.add_argument('--apply', action='store_true', help='Commit only an already validated final contract.')
    parser.add_argument('--receipt', type=Path, default=RECEIPT,
                        help='Separate receipt for a separately validated integration transaction.')
    args = parser.parse_args()
    apply_contract(args.contract, args.apply, args.receipt)
