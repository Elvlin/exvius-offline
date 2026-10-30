"""Import browser-discovered original event pictures into the existing overlay."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import tarfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools/vendor/python'))
from PIL import Image
from build_event_archive import normal


def dungeon_banners(archive, metadata):
    names = {row['key'].rsplit('_', 1)[1]: row['v'][0]
             for line in (ROOT / 'data/text_decoded/F_TEXT_DUNGEON_NAME.ndjson').read_text(encoding='utf-8').splitlines()
             if line.strip() for row in [json.loads(line)]}
    parents = {str(did): event for event in archive['events'] for did in event['dungeons']}
    result = {}
    for line in (ROOT / 'data/mst_decoded/F_DUNGEON_MST.ndjson').read_text(encoding='utf-8').splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        did = str(row['U9iHsau3'])
        if did not in parents:
            continue
        event = parents[did]
        name = names.get(did) or 'Stage ' + str(row.get('Z0EN6jSh') or did)
        result[did] = {'name': name, 'filename': metadata['events'][event['area']]['filename'],
                       'original_image': row.get('7DTnc2Lt') or '',
                       'source_page': event['source_page'],
                       'fallback': 'Same campaign original English artwork with the original English stage caption.'}
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', action='append', default=[], type=Path)
    parser.add_argument('--metadata-only', action='store_true')
    args = parser.parse_args()
    index_path = ROOT / 'logs/reference/event-image-index-20261026.json'
    index = json.loads(index_path.read_text(encoding='utf-8'))
    images = {normal(row['title']): row for row in index if row.get('imageinfo')}
    archive = json.loads((ROOT / 'source/server/event_archive.json').read_text(encoding='utf-8'))
    output = ROOT / 'source/server/event_art.json'
    metadata = json.loads(output.read_text(encoding='utf-8'))
    if args.metadata_only:
        metadata['dungeons'] = dungeon_banners(archive, metadata)
        output.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        print('Inner banner mappings:', len(metadata['dungeons']))
        return
    originals = ROOT / 'data/state/backups/originals/events'
    overlay = ROOT / 'data/overlay/en/sd/area'
    originals.mkdir(parents=True, exist_ok=True)
    overlay.mkdir(parents=True, exist_ok=True)
    for archive_path in args.archive:
        with tarfile.open(archive_path) as transfer:
            manifest = json.load(transfer.extractfile('index.json'))
            for entry in manifest['items']:
                image = images[normal(entry['title'])]
                source = originals / (image['imageinfo'][0]['sha1'] + '.image')
                if not source.exists():
                    source.write_bytes(transfer.extractfile('original-' + str(entry['index']) + '.image').read())
    needed = {}
    for event in archive['events']:
        image = images.get(normal(event['banner_title']))
        if image:
            needed[image['title']] = image

    recovered, errors = {}, []
    for image in needed.values():
        source = originals / (image['imageinfo'][0]['sha1'] + '.image')
        if source.exists():
            recovered[normal(image['title'])] = source
    unresolved = []
    for event in archive['events']:
        aid = event['area']
        source = recovered.get(normal(event['banner_title']))
        if source is None:
            if aid not in metadata['events']:
                unresolved.append({'area': aid, 'name': event['name'], 'page': event['source_page']})
            continue
        filename = metadata['events'].get(aid, {}).get('filename', 'event_' + aid + '.png')
        target = overlay / filename
        with Image.open(source) as picture:
            picture.convert('RGBA').save(target, optimize=True)
            size = list(picture.size)
        image = images[normal(event['banner_title'])]
        entry = metadata['events'].setdefault(aid, {})
        entry.update({'name': event['name'], 'filename': filename,
                      'source_page': event['source_page'], 'source_url': image['imageinfo'][0]['url'],
                      'source_file': source.relative_to(ROOT).as_posix(),
                      'source_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
                      'runtime_file': target.relative_to(ROOT).as_posix(),
                      'runtime_sha256': hashlib.sha256(target.read_bytes()).hexdigest(),
                      'size': size,
                      'conversion': 'Original pixels and dimensions retained. PNG encoding only.'})
        event['filename'] = filename
    metadata['dungeons'] = dungeon_banners(archive, metadata)
    output.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    (ROOT / 'source/server/event_archive.json').write_text(
        json.dumps(archive, ensure_ascii=False, separators=(',', ':')) + '\n', encoding='utf-8')
    report = ROOT / 'source/build/event-art-unresolved-20261026.json'
    report.write_text(json.dumps({'unresolved': unresolved, 'errors': errors}, ensure_ascii=False, indent=2), encoding='utf-8')
    print('Event pictures ready:', len(metadata['events']), '; unresolved:', len(unresolved), '; transfer errors:', len(errors))


if __name__ == '__main__':
    main()
