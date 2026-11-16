"""Check every preserved indexed master against local pack and overlay bytes.

Run after any native data edit: python source/exvius/check_master_indexes.py
Pack order is data/latest.json order. No phone access or project mutation is
performed unless an explicit --json report destination is supplied.
"""
import argparse
import hashlib
import io
import json
from pathlib import Path
import re
import struct
import zipfile

from decode_client_data import client_manifest, decode
from native_master_index import (COMPLEX_SCHEMAS, SCHEMAS, build_index,
                                 row_identity, schema)

PROJECT = Path(__file__).resolve().parents[2]
DAT_NAME = re.compile(r'Ver(\d+)_([A-Za-z0-9]{8})\.dat')


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


class MasterInputs:
    """Resolve physical sources without downloading, rebuilding or using ADB."""
    def __init__(self, root):
        self.root = Path(root)
        self.manifest = client_manifest(self.root / 'repository snapshots/FFBE-Global-v9.0.0-original.apk')
        self.originals = {}
        self.packs = []
        try:
            for ip in sorted((self.root / 'data/client/files/mst').glob('*.i')):
                token = ip.stem
                info = self.manifest[token]
                dats = list(ip.parent.glob('Ver*_' + token + '.dat'))
                dp = max(dats, key=lambda p: int(DAT_NAME.fullmatch(p.name)[1]))
                self.originals[token] = dict(info, dat=dp, index=ip,
                                             version=int(DAT_NAME.fullmatch(dp.name)[1]))
            if not self.originals:
                raise ValueError('No original indexed masters found.')
            latest = json.loads((self.root / 'data/latest.json').read_bytes())
            for entry in latest['packs']:
                path = self.root / 'source/build/distribution/assets' / entry['url'].rsplit('/', 1)[-1]
                archive = zipfile.ZipFile(path)
                names = archive.namelist()
                if len(names) != len(set(names)):
                    archive.close()
                    raise ValueError('Duplicate ZIP members: ' + str(path))
                self.packs.append((path, archive, set(names)))
        except Exception:
            self.close()
            raise

    def close(self):
        for _, archive, _ in self.packs:
            archive.close()

    def pack_dats(self, token):
        for path, archive, names in self.packs:
            members = sorted((n for n in names if n.startswith('native/mst/Ver')
                              and DAT_NAME.fullmatch(n.rsplit('/', 1)[-1])
                              and n.endswith('_' + token + '.dat')),
                             key=lambda n: int(DAT_NAME.fullmatch(n.rsplit('/', 1)[-1])[1]))
            # One unversioned .i can address only the selected version. Older
            # versioned files in the same pack are retained historical inputs.
            if members:
                yield path, archive, members[-1]

    def effective(self, token, overlay=True):
        info = self.originals[token]
        dat = info['dat'].read_bytes()
        version = info['version']
        dat_source = info['dat'].relative_to(self.root).as_posix()
        index = info['index'].read_bytes()
        index_source = info['index'].relative_to(self.root).as_posix()
        for path, archive, names in self.packs:
            members = [n for n in names if n.startswith('native/mst/Ver') and n.endswith('_' + token + '.dat')]
            if members:
                member = max(members, key=lambda n: int(DAT_NAME.fullmatch(n.rsplit('/', 1)[-1])[1]))
                dat = archive.read(member)
                version = int(DAT_NAME.fullmatch(member.rsplit('/', 1)[-1])[1])
                dat_source = path.relative_to(self.root).as_posix() + ':' + member
            member = 'native/mst/' + token + '.i'
            if member in names:
                index = archive.read(member)
                index_source = path.relative_to(self.root).as_posix() + ':' + member
        if overlay:
            folder = self.root / 'data/overlay/mst'
            dats = list(folder.glob('Ver*_' + token + '.dat'))
            if dats:
                dp = max(dats, key=lambda p: int(DAT_NAME.fullmatch(p.name)[1]))
                dat = dp.read_bytes()
                version = int(DAT_NAME.fullmatch(dp.name)[1])
                dat_source = dp.relative_to(self.root).as_posix()
            ip = folder / (token + '.i')
            if ip.exists():
                index = ip.read_bytes()
                index_source = ip.relative_to(self.root).as_posix()
        return dat, index, version, dat_source, index_source


def direct_entries(index, width, count):
    fmt = '<' + 'i' * width + 'II'
    size = struct.calcsize(fmt)
    if 10 + count * size + 4 > len(index):
        raise ValueError('Truncated direct index.')
    return [struct.unpack_from(fmt, index, 10 + n * size) for n in range(count)]


class IndexChecker:
    def __init__(self, inputs):
        self.inputs = inputs
        self.cache = {}
        self.proofs = {}

    def original_proof(self, token):
        if token in self.proofs:
            return self.proofs[token]
        info = self.inputs.originals[token]
        raw = info['dat'].read_bytes()
        index = info['index'].read_bytes()
        table = info['table']
        supported = table in SCHEMAS or table in COMPLEX_SCHEMAS
        if supported and build_index(table, raw, info['key'], info['version']) != index:
            raise ValueError('Builder does not reproduce the original index: ' + table)
        self.proofs[token] = dict(table=table, token=token, dat_sha256=digest(raw),
                                  index_sha256=digest(index), builder_byte_exact=supported)
        return self.proofs[token]

    def check_pair(self, token, raw, index, version):
        info = self.inputs.originals[token]
        table = info['table']
        cache_key = token, digest(raw), digest(index), version
        if cache_key in self.cache:
            return self.cache[cache_key]
        self.original_proof(token)
        supported = table in SCHEMAS or table in COMPLEX_SCHEMAS
        if supported:
            if build_index(table, raw, info['key'], version) != index:
                raise ValueError('Stale or missing index: ' + table)
        else:
            if index != self.build_for_source(token, raw, version):
                raise ValueError('Stale index header or bytes: ' + table)
        if index[:4] != bytes.fromhex('0000beff') or index[-4:] != bytes.fromhex('beff0000'):
            raise ValueError('Invalid native index markers: ' + table)
        if struct.unpack_from('<I', index, 4)[0] != version:
            raise ValueError('Index version differs from data filename: ' + table)
        _, rows = decode(raw, info['key'])
        lines = raw.splitlines(keepends=True)
        if len(rows) != len(lines) or b''.join(lines) != raw:
            raise ValueError('Unexpected physical row framing: ' + table)
        declared = struct.unpack_from('<H', index, 8)[0]
        if supported:
            identity, _ = schema(table)
            identities = [row_identity(identity, row, n) for n, row in enumerate(rows)]
            width = len(identities[0])
            count = len(set(identities))
        else:
            # No changed unknown schema is accepted. For preserved bytes, infer
            # only the direct entry width from every exact physical row boundary.
            boundaries = set()
            offset = 0
            for line in lines:
                boundaries.add((offset, len(line.rstrip(b'\r\n'))))
                offset += len(line)
            widths = []
            count = declared
            for candidate in range(1, 5):
                if 10 + count * (candidate * 4 + 8) + 4 > len(index):
                    continue
                entries = direct_entries(index, candidate, count)
                if all(entry[-2:] in boundaries for entry in entries):
                    widths.append(candidate)
            if len(widths) != 1:
                raise ValueError('Ambiguous preserved direct layout: ' + table)
            width = widths[0]
            identities = None
        entries = direct_entries(index, width, count)
        direct = {entry[:-2]: entry[-2:] for entry in entries}
        if len(direct) != count or list(direct) != sorted(direct):
            raise ValueError('Duplicate or unordered direct index keys: ' + table)
        source = io.BytesIO(raw)
        by_offset = {}
        offset = 0
        for ordinal, (line, row) in enumerate(zip(lines, rows)):
            by_offset[offset] = (ordinal, line.rstrip(b'\r\n'), row)
            offset += len(line)
        indexed_rows = set()
        for ident, (start, length) in direct.items():
            if start not in by_offset:
                raise ValueError('Index does not seek to a record boundary: ' + table)
            ordinal, body, row = by_offset[start]
            source.seek(start)
            found = source.read(length)
            if found != body or len(found) != length:
                raise ValueError('Index does not read the complete exact row: ' + table)
            if identities is not None and identities[ordinal] != ident:
                raise ValueError('Indexed key differs from decrypted row identity: ' + table)
            # Independently decode the result of each seek, including every row
            # of every changed table, rather than trusting the serializer.
            if decode(found, info['key'])[1] != [row]:
                raise ValueError('Indexed read decodes to a different row: ' + table)
            indexed_rows.add(ordinal)
        shadowed = len(rows) - len(indexed_rows)
        # Duplicate keys retain the native first-record rule. They are reported
        # explicitly, never counted as independently seekable rows.
        result = dict(rows=len(rows), direct_entries=count, rows_seek_verified=len(indexed_rows),
                      preserved_shadowed_rows=shadowed, declared_uint16_count=declared,
                      native_count_overflow=count != declared, key_width=width,
                      dat_sha256=cache_key[1], index_sha256=cache_key[2], version=version,
                      complete_index_matches=True)
        self.cache[cache_key] = result
        return result

    def build_for_source(self, token, raw, version):
        info = self.inputs.originals[token]
        table = info['table']
        self.original_proof(token)
        if table in SCHEMAS or table in COMPLEX_SCHEMAS:
            return build_index(table, raw, info['key'], version)
        if raw != info['dat'].read_bytes():
            raise ValueError('Changed master needs a reviewed schema: ' + table)
        # Ciphertext-identical copies need only the existing filename version in
        # the common header. Every offset, key and grouped byte stays original.
        original = info['index'].read_bytes()
        return original[:4] + struct.pack('<I', version) + original[8:]


def audit(root=PROJECT):
    inputs = MasterInputs(root)
    checker = IndexChecker(inputs)
    checks, failures = [], []
    try:
        def check(token, raw, index, version, dat_source, index_source, scope):
            info = inputs.originals[token]
            row = dict(table=info['table'], token=token, scope=scope,
                       dat_source=dat_source, index_source=index_source)
            try:
                row.update(checker.check_pair(token, raw, index, version))
                row['ok'] = True
            except (ValueError, KeyError, struct.error) as exc:
                row.update(ok=False, error=str(exc))
                failures.append(row)
            checks.append(row)
        for token, info in inputs.originals.items():
            check(token, info['dat'].read_bytes(), info['index'].read_bytes(), info['version'],
                  info['dat'].relative_to(inputs.root).as_posix(),
                  info['index'].relative_to(inputs.root).as_posix(), 'original')
            # Test every shipping .dat with the index inherited at that point in
            # pack installation order, including copies shadowed by later packs.
            active_index = info['index'].read_bytes()
            active_source = info['index'].relative_to(inputs.root).as_posix()
            for path, archive, names in inputs.packs:
                ip = 'native/mst/' + token + '.i'
                if ip in names:
                    active_index = archive.read(ip)
                    active_source = path.relative_to(inputs.root).as_posix() + ':' + ip
                members = [n for n in names if n.startswith('native/mst/Ver')
                           and n.endswith('_' + token + '.dat')]
                selected = max(members, key=lambda n: int(DAT_NAME.fullmatch(n.rsplit('/', 1)[-1])[1])) if members else None
                for member in [selected] if selected else []:
                    version = int(DAT_NAME.fullmatch(member.rsplit('/', 1)[-1])[1])
                    check(token, archive.read(member), active_index, version,
                          path.relative_to(inputs.root).as_posix() + ':' + member, active_source, 'pack-member')
            check(token, *inputs.effective(token, overlay=False), 'effective-packs')
            check(token, *inputs.effective(token, overlay=True), 'effective-overlay')
        overflows = sorted({r['table'] for r in checks if r.get('native_count_overflow')})
        return dict(indexed_tables=len(inputs.originals), checks=len(checks), stale_indexes=len(failures),
                    failures=failures, native_count_overflow_tables=overflows,
                    original_proofs=list(checker.proofs.values()), results=checks)
    finally:
        inputs.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=PROJECT)
    parser.add_argument('--json', type=Path)
    parser.add_argument('--strict-native-counts', action='store_true',
                        help='Also fail on the preserved GL9 uint16 LB count overflow.')
    args = parser.parse_args()
    report = audit(args.root)
    if args.json:
        args.json.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(f"Indexed tables: {report['indexed_tables']}; pair checks: {report['checks']}; stale indexes: {report['stale_indexes']}")
    for failure in report['failures']:
        print(f"FAIL {failure['table']} {failure['scope']}: {failure['error']} ({failure['dat_source']})")
    for table in report['native_count_overflow_tables']:
        print('NATIVE FORMAT LIMIT: ' + table + ' retains the original uint16 count overflow; full stored offsets are checked, not claimed to be loaded by the native reader.')
    return int(bool(report['stale_indexes'] or (args.strict_native_counts and report['native_count_overflow_tables'])))


if __name__ == '__main__':
    raise SystemExit(main())
