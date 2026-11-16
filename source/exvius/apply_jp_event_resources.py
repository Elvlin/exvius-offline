"""Install owned earlier JP resource dependencies at existing native cache paths."""
import argparse
import hashlib
import json
from pathlib import Path

from apply_jp_content import NativeCache
from decode_client_data import decode
from fill_content_from_memorial import device_dir, global_cpk_header, localized_package
import fill_content_from_memorial as field_localizer

def _scratch(root):
    path = root / 'build' / 'scratch'
    path.mkdir(parents=True, exist_ok=True)
    return path

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / 'Japan content/Earlier JP crossovers/Sources'
TABLE_PATHS = {
    'F_RESOURCE_MST': 'mst/Ver329_ZQqB38Ns.dat',
    'F_RESOURCE_MAP_MST': 'mst/Ver265_B7LnP2TH.dat',
    'F_RESOURCE_VERSION_MST_LOCALIZE': 'mst/Ver735_A1L1GlaQ.dat',
    'F_RESOURCE_MAP_VERSION_MST_LOCALIZE': 'mst/Ver563_YIgCpDKW.dat',
}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--audio-only', action='store_true')
    args = parser.parse_args()
    # Scope this adaptation to these historical SINoALICE packages. The original
    # reviewed translation and raw JP source remain unchanged in their own homes.
    raffle_key = '5b1554fb26f40c47a0f5867daf102ca9ec65297fd68e3c4c120c1c1554f5c56a'
    if not args.audio_only:
        translations = json.loads((ROOT / 'source/server/content/dialogue_en.json').read_text(encoding='utf8'))['translations']
        translations = {key: dict(value) for key, value in translations.items()}
        translations[raffle_key]['english'] = '<name=200010><br>The original prize raffle has closed, kupo.<br>Entry tickets are historical souvenirs.<br>No real prize draw is held offline, kupo!<keywait>'
        field_localizer._DIALOGUE_ENGLISH = translations
    graph = json.loads((BASE / 'Event graph/graph-status.json').read_text(encoding='utf8'))
    selectors = [json.loads(s) for s in (BASE / 'Event graph/F_RESOURCE_MAP_MST.ndjson').read_text(encoding='utf8').splitlines() if s]
    cache = NativeCache()
    try:
        tables, table_sources = {}, []
        for table, relative in TABLE_PATHS.items():
            raw, origin = cache.read(relative)
            _, rows = decode(raw, cache.tables[table][1])
            tables[table] = rows
            table_sources.append({'table': table, 'path': relative, 'origin': origin, 'sha256': sha(raw)})
        records = {str(r.get('9ZCEWn0z') or r.get('Nnb20keZ')): r for table in ('F_RESOURCE_MST', 'F_RESOURCE_MAP_MST') for r in tables[table]}
        versions = {str(r.get('9ZCEWn0z') or r.get('Nnb20keZ')): r for table in ('F_RESOURCE_VERSION_MST_LOCALIZE', 'F_RESOURCE_MAP_VERSION_MST_LOCALIZE') for r in tables[table]}
        receipts, outputs = [], {}
        for source_row in selectors:
            rid, name = source_row['Nnb20keZ'], source_row['pJ56sAEo']
            active = records.get(rid)
            for field in ('dX0SkK3j', '3LHdc6Qa', 'pJ56sAEo'):
                if active is None or active[field] != source_row[field]:
                    raise ValueError('Original/native resource identity mismatch: ' + rid + ':' + field)
            version = versions.get(rid, {}).get('OzT5lSz3')
            if not version or not str(version).isdecimal():
                raise ValueError('No existing active resource version: ' + rid)
            relative = 'common_lang/' + device_dir(active['3LHdc6Qa']) + '/Ver' + str(version) + '_' + name
            if name == '211020100.cpk':
                before, origin = cache.read(relative)
                receipts.append({'id': rid, 'file': name, 'output': relative, 'status': 'Existing English shared Farplane resource preserved', 'sha256': sha(before), 'origin': origin})
                continue
            if args.audio_only and not name.endswith('.acb'):
                continue
            candidates = graph['asset_sources'][name]
            source = next((r for r in candidates if r.get('matches_original_archive_bytes')), None)
            if source is None:
                raise ValueError('No verified original archive payload: ' + name)
            original = ROOT / source['path']
            raw = original.read_bytes()
            if sha(raw) != source['sha256']:
                raise ValueError('Original payload changed: ' + name)
            if name.endswith('.cpk'):
                body, count = localized_package(original)
                body = global_cpk_header(body)
                from cricodecs import cpk
                import tempfile
                with tempfile.TemporaryDirectory(dir=_scratch(ROOT)) as temporary:
                    target = Path(temporary) / name
                    target.write_bytes(body)
                    archive = cpk.load(str(target))
                    members = {v.full_path: i for i, v in enumerate(archive.file_infos())}
                    for member, index in members.items():
                        if member.endswith('_sg.txt'):
                            import re
                            for line in archive.file_bytes(index).decode('utf8').splitlines():
                                cells = line.split('^')
                                if len(cells) > 1 and re.search('[\u3040-\u30ff\u3400-\u9fff]', cells[1]):
                                    raise ValueError('Untranslated field English: ' + name + '/' + member + ':' + cells[0])
                    # The native CPK reader memory-maps its input on Windows.
                    # Release it before TemporaryDirectory removes that file.
                    del archive
            else:
                body, count = raw, 0
            try:
                before, origin = cache.read(relative)
            except FileNotFoundError:
                before, origin = None, None
            outputs[relative] = body
            receipts.append({'id': rid, 'file': name, 'source': source['path'], 'source_sha256': sha(raw), 'output': 'data/overlay/' + relative, 'output_sha256': sha(body), 'before_sha256': sha(before) if before else None, 'before_origin': origin, 'localized_member_changes': count, 'status': 'UNCHANGED' if before == body else 'READY'})
        if args.apply:
            for relative, body in outputs.items():
                target = ROOT / 'data/overlay' / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(body)
                if sha(target.read_bytes()) != sha(body):
                    raise ValueError('Native resource write/readback mismatch: ' + relative)
        result = {'status': 'APPLIED' if args.apply else 'PREVIEW', 'audio_only': args.audio_only, 'native_table_sources': table_sources, 'resource_versions_changed': False, 'event_selectors_enabled': False, 'outputs': len(outputs), 'resources': receipts,
                  'offline_adaptation': None if args.audio_only else {'source_sha256': raffle_key, 'packages': 'SINoALICE 3037010101..0106 and3038010101..0107 only', 'rule': 'Original prize raffle is closed. Tickets are historical souvenirs. No real prize draw offline. Original script commands preserved.'}}
        path = ROOT / 'logs' / ('jp-event-audio-integration.json' if args.audio_only else 'jp-event-resource-integration.json')
        path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
        print(json.dumps({'status': result['status'], 'outputs': len(outputs), 'shared_resources_preserved': sum('Existing' in r['status'] for r in receipts)}))
    finally:
        cache.close()


if __name__ == '__main__':
    main()
