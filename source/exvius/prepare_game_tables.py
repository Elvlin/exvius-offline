"""Prepare exact Java-decoder UTF-8 output beside external static game data.

The encrypted files remain authoritative. Each prepared filename includes their
SHA-256 and size, plus the decoder parameters, so a changed file cannot use an
older prepared copy. This is a data-generation tool, not a gameplay runtime.
"""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import re
from decode_client_data import decode as decode_content, getter_manifest, TRIPLET
from ffbe_crypto import IV, aes_ecb_decrypt, cbc_decrypt, key16


def manifest(native):
    result = getter_manifest(native)
    for match in TRIPLET.finditer(native):
        table, token, key = (v.decode('ascii') for v in match.groups())
        result[token] = dict(table=table, token=token, key=key)
    for table, token, key in [('F_TEXT_ANALYTICS_ITEMS', '8e6PGb3p', '7nyO4pC9'),
                              ('F_TEXT_TEXT_EN', '0ThfQQWd', 's9E34w78')]:
        assert (token + '\0' + key + '\0').encode() in native
        result[token] = dict(table=table, token=token, key=key)
    return result


def prepared_name(name, encrypted, password, iv=IV):
    parameters = hashlib.sha256(password.encode('utf-8') + b'\0' + iv).hexdigest()
    return f'{name}.{len(encrypted)}.{hashlib.sha256(encrypted).hexdigest()}.{parameters}.utf8'


def decode(raw, password, mode='cbc'):
    """Use the content decoder, then reproduce the Java reader's inner unpad."""
    # BufferedReader.readLine recognizes CR, LF and CRLF, with no final empty row.
    lines = re.split(rb'\r\n|\r|\n', raw)
    if lines[-1] == b'':
        lines.pop()
    rows = []
    for line in lines:
        if mode == 'ecb':
            plain = aes_ecb_decrypt(key16(password), base64.b64decode(line))
            padding = plain[-1]
            if not 1 <= padding <= 16 or plain[-padding:] != bytes([padding]) * padding:
                raise ValueError('Invalid ECB PKCS5 padding')
            plain = plain[:-padding]
        else:
            plain = cbc_decrypt(key16(password), line)
            padding = int.from_bytes(plain[-1:], 'big', signed=True)
            if padding > 0 and padding != 16 - (len(plain) - padding) % 16:
                plain = b'\0'
            elif padding >= 0:
                plain = plain[:len(plain) - padding]
            else:
                # Arrays.copyOf zero-extends when Java's signed byte is negative.
                plain += b'\0' * -padding
        rows.append(plain.decode('utf-8', errors='replace').encode('utf-8'))
    return b'\n'.join(rows)


def prepare(files_root, output, native, replacements=None):
    entries = manifest(native.read_bytes())
    sources = {p.relative_to(files_root).as_posix(): p
               for folder in ('mst', 'localized_texts')
               for p in (files_root / folder).rglob('*.dat')}
    for relative, path in (replacements or {}).items():
        if relative.startswith(('mst/', 'localized_texts/')) and relative.endswith('.dat'):
            sources[relative] = path
    output.mkdir(parents=True, exist_ok=True)
    records = []
    unused = []
    for relative, path in sorted(sources.items()):
        token = path.stem.split('_', 1)[1]
        if token not in entries:
            unused.append(dict(device='files/' + relative, reason='No table getter in pinned client'))
            continue
        entry = entries[token]
        raw = path.read_bytes()
        try:
            # PKCS padding alone cannot identify a mode. The existing content
            # decoder requires structured plaintext before accepting CBC or ECB.
            sample = next((line for line in raw.splitlines() if line.strip()), None)
            mode = decode_content(sample, entry['key'], relative.startswith('localized_texts/'))[0] if sample else 'cbc'
            plain = decode(raw, entry['key'], mode)
        except Exception as error:
            raise ValueError(f'{relative}: {error}') from error
        name = prepared_name(path.name, raw, entry['key'], IV if mode == 'cbc' else b'ECB')
        target = output / name
        target.write_bytes(plain)
        records.append(dict(source=str(path.resolve()), device='files/' + relative,
                            table=entry['table'], token=token, key=entry['key'], mode=mode,
                            encrypted_bytes=len(raw), encrypted_sha256=hashlib.sha256(raw).hexdigest(),
                            prepared=name, bytes=len(plain), sha256=hashlib.sha256(plain).hexdigest()))
    return records, unused


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--files-root', type=Path, required=True)
    ap.add_argument('--output', type=Path, required=True)
    ap.add_argument('--native', type=Path, required=True)
    ap.add_argument('--report', type=Path, required=True, help='PC parity manifest outside the content tree')
    ap.add_argument('--replacements', type=Path, help='Existing local/device CSV, rooted at project')
    args = ap.parse_args()
    replacements = {}
    if args.replacements:
        import csv
        root = Path(__file__).resolve().parents[2]
        for row in csv.DictReader(args.replacements.open(encoding='utf-8-sig', newline='')):
            path = root / row['local']
            assert hashlib.sha256(path.read_bytes()).hexdigest() == row['sha256'], path
            replacements[row['device'].removeprefix('files/')] = path
    records, unused = prepare(args.files_root, args.output, args.native, replacements)
    args.report.write_text(json.dumps(dict(tables=records, unused=unused), indent=2), encoding='utf-8')
    print(f'Prepared {len(records)} tables, {sum(r["bytes"] for r in records)} bytes')


if __name__ == '__main__':
    main()
