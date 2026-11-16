"""Apply reviewed JP content to the established native cache overlay.

Keeps existing resource versions and the published data packs unchanged.
"""
from pathlib import Path
import argparse
import hashlib
import json
import re
import tempfile
import zipfile

from decode_client_data import client_manifest, decode
from prepare_offline_cache import loading_text, localized_text_versions

def _scratch(root):
    path = root / 'build' / 'scratch'
    path.mkdir(parents=True, exist_ok=True)
    return path

ROOT = Path(__file__).resolve().parents[2]
EVENT_CONTRACT = ROOT / 'Japan content/Earlier JP crossovers/Sources/Event graph/english-import.json'


def sha(data):
    return hashlib.sha256(data).hexdigest()


class NativeCache:
    def __init__(self):
        self.tables = {r['table']: (token, r['key']) for token, r in
                       client_manifest(ROOT / 'repository snapshots/FFBE-Global-v9.0.0-original.apk').items()}
        self.packs = []
        manifest = json.loads((ROOT / 'source/build/distribution/repository/data/latest.json').read_text(encoding='utf-8'))
        for entry in manifest['packs']:
            path = ROOT / 'source/build/distribution/assets' / entry['url'].rsplit('/', 1)[-1]
            if path.is_file():
                pack = zipfile.ZipFile(path)
                self.packs.append((path, pack, set(pack.namelist())))

    def read(self, relative):
        path = ROOT / 'data/overlay' / relative
        if path.is_file():
            return path.read_bytes(), path.relative_to(ROOT).as_posix()
        member = 'native/' + relative
        for path, pack, names in reversed(self.packs):
            if member in names:
                return pack.read(member), path.relative_to(ROOT).as_posix() + '::' + member
        for folder in ('client/files', 'memorial_fill'):
            path = ROOT / 'data' / folder / relative
            if path.is_file():
                return path.read_bytes(), path.relative_to(ROOT).as_posix()
        raise FileNotFoundError('Effective native cache file missing: ' + relative)

    def close(self):
        for _, pack, _ in self.packs:
            pack.close()


def apply_english(contract_path=EVENT_CONTRACT, mapped_unit_labels=False, row_labels=False, receipt_path=None):
    contract_bytes = contract_path.read_bytes()
    document = json.loads(contract_bytes)
    if row_labels:
        grouped = {}
        for row in document['rows']:
            table = grouped.setdefault(row['table'], {})
            if row['key'] in table:
                raise ValueError('Duplicate reviewed English key: ' + row['key'])
            table[row['key']] = row['v'][0]
        document, mapped_unit_labels = grouped, True
    contract = ({'id_replacements': {}, 'text_tables': [
        {'table': table, 'inline_labels': labels, 'rows': len(labels)}
        for table, labels in document.items()]} if mapped_unit_labels else document)
    if contract['id_replacements']:
        raise ValueError('This event text contract requires an explicit ID mapping')
    outputs, receipts, decoded_outputs = {}, [], {}
    receipt_path = (Path(receipt_path).resolve() if receipt_path is not None else
                    ROOT / 'logs' / ('jp-extra-english-integration.json' if row_labels else
                                     'jp-unit-english-integration.json' if mapped_unit_labels else
                                     'jp-event-english-integration.json'))
    if not receipt_path.is_relative_to((ROOT / 'logs').resolve()):
        raise ValueError('Native English integration receipts belong in the existing logs folder.')
    prior_receipts = ({r['table']: r for r in json.loads(receipt_path.read_text(encoding='utf-8'))['tables']}
                      if receipt_path.is_file() else {})
    cache = NativeCache()
    try:
        token, key = cache.tables['F_LOCALIZED_TEXT_MST']
        index_relative = f'mst/Ver710_{token}.dat'
        index_bytes, index_origin = cache.read(index_relative)
        _, index_rows = decode(index_bytes, key)
        versions = {row['a4hXTIm0']: row['00zAYGYS'] for row in index_rows}
        localized = {}
        with tempfile.TemporaryDirectory(prefix='jp-content-', dir=_scratch(ROOT)) as scratch:
            scratch = Path(scratch)
            for table_entry in contract['text_tables']:
                table = table_entry['table']
                if 'inline_labels' in table_entry:
                    raw = json.dumps(table_entry['inline_labels'], sort_keys=True, ensure_ascii=False).encode('utf-8')
                    rows = [{'key': key, 'v': [value, value]} for key, value in table_entry['inline_labels'].items()]
                else:
                    raw = (ROOT / table_entry['file']).read_bytes()
                    if sha(raw) != table_entry['sha256']:
                        raise ValueError('Reviewed English source changed: ' + table)
                    rows = [json.loads(line) for line in raw.splitlines() if line.strip()]
                labels = {row['key']: row['v'][0] for row in rows}
                if len(rows) != table_entry['rows'] or len(labels) != len(rows):
                    raise ValueError('Reviewed English key count mismatch: ' + table)
                if any(re.search(r'[\u3040-\u30ff\u3400-\u9fff]', value) or '\u2014' in value
                       or any(c in value for c in ('^', '\r', '\n')) for value in labels.values()):
                    raise ValueError('English text contains an unsupported value: ' + table)
                expected_prefix = {'F_TEXT_ITEM_NAME': 'MST_ITEM_NAME_',
                                   'F_TEXT_ITEM_EQUIP_NAME': 'MST_EQUIP_ITEM_NAME_'}.get(table)
                if expected_prefix and any(not label.startswith(expected_prefix) for label in labels):
                    raise ValueError('Wrong native item/equipment namespace: ' + table)
                token, table_key = cache.tables[table]
                relative = f'localized_texts/en/Ver{versions[table]}_{token}.dat'
                before, origin = cache.read(relative)
                source, target = scratch / (table + '-source.dat'), scratch / (table + '.dat')
                source.write_bytes(before)
                loading_text(source, target, table_key, labels, append_missing=True)
                _, previous = decode(before, table_key, localized=True)
                _, merged = decode(target.read_bytes(), table_key, localized=True)
                old_rows = {row['key']: row for row in previous}
                new_rows = {row['key']: row for row in merged}
                if any(new_rows[k] != row for k, row in old_rows.items() if k not in labels):
                    raise ValueError('An unrelated English row changed: ' + table)
                if any(not all(v == value for v in new_rows[k]['v']) for k, value in labels.items()):
                    raise ValueError('Native English round-trip mismatch: ' + table)
                outputs[relative] = target.read_bytes()
                localized[table] = (versions[table], target)
                decoded_path = ROOT / 'data/text_decoded' / (table + '.ndjson')
                decoded_rows = ([json.loads(line) for line in decoded_path.read_bytes().splitlines() if line.strip()]
                                if decoded_path.is_file() else [])
                decoded_keys = {row['key'] for row in decoded_rows}
                decoded_rows = [new_rows[row['key']] if row['key'] in labels else row for row in decoded_rows]
                decoded_rows.extend(new_rows[k] for k in sorted(set(labels) - decoded_keys))
                decoded_outputs[decoded_path] = ''.join(json.dumps(row, ensure_ascii=False, separators=(',', ':')) + '\n'
                                                      for row in decoded_rows).encode('utf-8')
                prior = prior_receipts.get(table, {})
                continued = prior.get('output_sha256') == sha(before)
                receipts.append({'table': table, 'source': prior['source'] if continued else origin,
                                 'source_sha256': prior['source_sha256'] if continued else sha(before),
                                 'output': 'data/overlay/' + relative,
                                 'output_sha256': sha(outputs[relative]),
                                 'reviewed_source_sha256': sha(raw), 'english_keys': len(labels),
                                 'unchanged_other_keys': len(set(old_rows) - set(labels)),
                                 'added_keys': len(set(labels) - set(old_rows))})
            source, target = scratch / 'index-source.dat', scratch / 'index.dat'
            source.write_bytes(index_bytes)
            localized_text_versions(source, target, key, localized)
            outputs[index_relative] = target.read_bytes()
            _, new_index = decode(outputs[index_relative], key)
            by_table = {row['a4hXTIm0']: row for row in new_index}
            for table, (version, path) in localized.items():
                row = by_table[table]
                if (row['00zAYGYS'] != version or row['zptmZGqa'] != hashlib.md5(path.read_bytes()).hexdigest()
                        or int(row['MLOSu5E0']) != path.stat().st_size):
                    raise ValueError('Native localized-text index mismatch: ' + table)
        # Commit only after every table and the native text index round-trip pass.
        for relative, body in outputs.items():
            path = ROOT / 'data/overlay' / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(body)
        for path, body in decoded_outputs.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(body)
        result = {'status': 'Native English cache overlay applied; phone UI not yet verified',
                  'contract': contract_path.relative_to(ROOT).as_posix(),
                  'contract_sha256': sha(contract_bytes), 'tables': receipts,
                  'english_keys': sum(row['english_keys'] for row in receipts),
                  'localized_index_source': index_origin,
                  'localized_index_sha256': sha(outputs[index_relative]),
                  'resource_versions_changed': False, 'event_selectors_enabled': False}
        receipt_path.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
        print(json.dumps({'english_keys': result['english_keys'], 'tables': len(receipts),
                          'native_index_updated': True, 'unrelated_rows_preserved': True}), flush=True)
        return result
    finally:
        cache.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--event-english', action='store_true')
    group.add_argument('--unit-english', type=Path)
    group.add_argument('--extra-english', type=Path)
    args = parser.parse_args()
    if args.extra_english:
        apply_english(args.extra_english.resolve(), row_labels=True)
    elif args.unit_english:
        apply_english(args.unit_english.resolve(), mapped_unit_labels=True)
    else:
        apply_english()
