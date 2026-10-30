"""Decode the original client's versioned master and localized-text files.

The filename/key triplets come from the pinned original client, following the
archived BraveHaxvius data extractor. CBC and ECB are accepted only when every
decoded record is valid JSON. No content, fields or rewards are fabricated.
"""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import re
import struct
import sys
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'server'))
from ffbe_crypto import aes_ecb_decrypt, cbc_decrypt, key16

APK_HASH = '955deacfbe4b3d0cd04e2947eb005e310915ba98132d71216626bfb3554ad246'
TRIPLET = re.compile(rb'(F_[A-Z0-9_]+)\x00([A-Za-z0-9]{8})\x00([A-Za-z0-9]{8})\x00')


def getter_manifest(native):
    """Resolve the client's literal-returning ARM64 getters, without executing them.

    This is the archived GetDataKeys method adapted to the pinned ARM64 client.
    Only the observed ADRP x0 / ADD x0 / RET form is accepted.
    """
    section_offset = struct.unpack_from('<Q', native, 40)[0]
    section_size, section_count = struct.unpack_from('<HH', native, 58)
    sections = [struct.unpack_from('<IIQQQQIIQQ', native, section_offset + i * section_size)
                for i in range(section_count)]

    def file_offset(address):
        for section in sections:
            if section[3] <= address < section[3] + section[5] and section[1] != 8:
                return section[4] + address - section[3]
        raise ValueError('Unmapped client address.')

    def string_getter(address):
        pos = file_offset(address)
        adrp, add, ret = struct.unpack_from('<III', native, pos)
        if adrp & 0x9f00001f != 0x90000000 or add & 0xffc003ff != 0x91000000 or ret != 0xd65f03c0:
            raise ValueError('Not a literal-returning ARM64 getter.')
        immediate = ((adrp >> 5) & 0x7ffff) << 2 | (adrp >> 29) & 3
        if immediate & (1 << 20):
            immediate -= 1 << 21
        target = (address & ~0xfff) + (immediate << 12) + ((add >> 10) & 0xfff)
        pos = file_offset(target)
        end = native.index(0, pos, pos + 200)
        return native[pos:end].decode('ascii')

    groups = {}
    for section in sections:
        if section[1] != 11:
            continue
        strings = sections[section[6]]
        pool = native[strings[4]:strings[4] + strings[5]]
        for pos in range(section[4], section[4] + section[5], section[9]):
            name_offset, info, other, index, address, size = struct.unpack_from('<IBBHQQ', native, pos)
            name = pool[name_offset:pool.index(0, name_offset)].decode('ascii')
            match = re.fullmatch(r'(_ZN.+)(10getMstName|14getMstFileName|13getMstFileKey)Ev', name)
            if not match or not index:
                continue
            try:
                value = string_getter(address)
            except (ValueError, UnicodeError):
                continue
            groups.setdefault(match[1], {})[match[2]] = value
    result = {}
    for group in groups.values():
        if len(group) != 3:
            continue
        name, token, key = (group[n] for n in ('10getMstName', '14getMstFileName', '13getMstFileKey'))
        if re.fullmatch(r'F_[A-Z0-9_]+', name) and all(re.fullmatch(r'[A-Za-z0-9]{8}', v) for v in (token, key)):
            result[token] = {'table': name, 'token': token, 'key': key}
    return result


def client_manifest(apk):
    raw = Path(apk).read_bytes()
    if hashlib.sha256(raw).hexdigest() != APK_HASH:
        raise ValueError('Decoder requires the verified original Global v9.0.0 client.')
    with zipfile.ZipFile(apk) as z:
        native = z.read('lib/arm64-v8a/libgame.so')
    by_token = {}
    for match in TRIPLET.finditer(native):
        name, token, key = (v.decode('ascii') for v in match.groups())
        value = {'table': name, 'token': token, 'key': key}
        if token in by_token and by_token[token] != value:
            raise ValueError('Conflicting client manifest token: ' + token)
        by_token[token] = value
    for token, value in getter_manifest(native).items():
        if token in by_token and by_token[token] != value:
            raise ValueError('Getter and literal triplet disagree for ' + token)
        by_token[token] = value
    # These two generic text lists have no individual literal-returning getter.
    # Their archived BraveHaxvius mapping is corroborated by the exact table name
    # and adjacent filename/key bytes in this pinned GL9 binary.
    for name, token, key in (
        ('F_TEXT_ANALYTICS_ITEMS', '8e6PGb3p', '7nyO4pC9'),
        ('F_TEXT_TEXT_EN', '0ThfQQWd', 's9E34w78'),
    ):
        if name.encode() + b'\0' not in native or (token + '\0' + key + '\0').encode() not in native:
            raise ValueError('Generic text mapping is not corroborated by this client.')
        by_token[token] = {'table': name, 'token': token, 'key': key}
    return by_token


def json_record(raw):
    # The wire and the master files can each carry two PKCS7 layers. Validate
    # their exact lengths rather than stripping arbitrary trailing control bytes.
    for _ in range(3):
        try:
            value = json.loads(raw.decode('utf-8'))
            if not isinstance(value, dict):
                raise ValueError('Expected an original JSON object record.')
            return value
        except (UnicodeDecodeError, json.JSONDecodeError):
            pad = raw[-1] if raw else 0
            if not 1 <= pad <= 16 or raw[-pad:] != bytes([pad]) * pad:
                raise ValueError('Record is neither JSON nor exactly PKCS7 padded.')
            raw = raw[:-pad]
    raise ValueError('Too many padding layers.')


def localized_records(raw):
    for _ in range(2):
        pad = raw[-1] if raw else 0
        if not 1 <= pad <= 16 or raw[-pad:] != bytes([pad]) * pad:
            break
        raw = raw[:-pad]
    records = []
    for line in raw.decode('utf-8').splitlines():
        if not line:
            continue
        parts = line.split('^')
        if len(parts) < 2 or not parts[0] or '\x00' in line:
            raise ValueError('Invalid original localized-text row.')
        records.append({'key': parts[0], 'v': parts[1:]})
    if not records:
        raise ValueError('Empty localized-text table.')
    return records


def decode(raw, key, localized=False):
    lines = [line for line in raw.decode('ascii').splitlines() if line.strip()]
    if not lines:
        raise ValueError('Empty source file.')
    valid = []
    for mode in ('cbc', 'ecb'):
        try:
            records = []
            for line in lines:
                plain = (cbc_decrypt(key16(key), line) if mode == 'cbc' else
                         aes_ecb_decrypt(key16(key), base64.b64decode(line, validate=True)))
                if localized:
                    records.extend(localized_records(plain))
                else:
                    records.append(json_record(plain))
            valid.append((mode, records))
        except (ValueError, UnicodeError):
            continue
    if len(valid) != 1:
        raise ValueError('Expected exactly one fully validated decoding mode.')
    return valid[0]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--apk', required=True)
    ap.add_argument('--data', required=True)
    args = ap.parse_args()
    data = Path(args.data)
    manifest = client_manifest(args.apk)
    results = []
    for folder, output in [('client/files/mst', 'mst_decoded'),
                           ('client/files/localized_texts/en', 'text_decoded')]:
        for source in sorted((data / folder).glob('Ver*_*.dat')):
            token = source.stem.split('_', 1)[1]
            entry = manifest.get(token)
            if entry is None:
                raise ValueError('No verified client manifest entry for ' + source.name)
            raw = source.read_bytes()
            try:
                mode, records = decode(raw, entry['key'], localized=entry['table'].startswith('F_TEXT'))
            except ValueError as exc:
                raise ValueError(source.name + ': ' + str(exc)) from exc
            target = data / output / (entry['table'] + '.ndjson')
            target.parent.mkdir(exist_ok=True)
            encoded = ''.join(json.dumps(row, ensure_ascii=False, separators=(',', ':')) + '\n'
                              for row in records).encode('utf-8')
            if target.exists() and target.read_bytes() != encoded:
                raise FileExistsError('Decoded output differs from existing file: ' + str(target))
            target.write_bytes(encoded)
            results.append({'table': entry['table'], 'source': source.name,
                            'source_sha256': hashlib.sha256(raw).hexdigest(),
                            'mode': mode, 'records': len(records),
                            'output_sha256': hashlib.sha256(encoded).hexdigest()})
    if not results:
        raise ValueError('No versioned client files found. No data was decoded.')
    print(json.dumps({'client_manifest_entries': len(manifest), 'decoded': results}, indent=2))


if __name__ == '__main__':
    main()
