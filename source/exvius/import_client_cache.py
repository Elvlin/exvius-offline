"""Import game content from the archived cache without importing account data."""
import argparse
import json
from pathlib import Path, PurePosixPath
import shutil
import zipfile
import zlib

PREFIX = 'data/data/com.square_enix.android_googleplay.FFBEWW/'
CONTENT = {'mst', 'en', 'common_lang', 'localized_texts', 'homeMarquee'}


def crc32(path):
    value = 0
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            value = zlib.crc32(chunk, value)
    return value & 0xffffffff


def import_cache(archive, data):
    destination = (data / 'client').resolve()
    count, size = 0, 0
    with zipfile.ZipFile(archive) as source:
        for entry in source.infolist():
            if entry.is_dir() or not entry.filename.startswith(PREFIX):
                continue
            relative = PurePosixPath(entry.filename[len(PREFIX):])
            if not (str(relative) == 'shared_prefs/gamedata.xml' or
                    (relative.parts[0] == 'files' and len(relative.parts) > 2
                     and relative.parts[1] in CONTENT)):
                continue
            if relative.is_absolute() or '..' in relative.parts or '\\' in str(relative):
                raise ValueError('Invalid archive content path.')
            target = destination.joinpath(*relative.parts).resolve()
            if destination not in target.parents:
                raise ValueError('Archive path escaped the content directory.')
            if target.exists():
                if target.stat().st_size != entry.file_size or crc32(target) != entry.CRC:
                    raise FileExistsError('Existing content differs: ' + str(relative))
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                pending = target.with_name(target.name + '.importing')
                with source.open(entry) as incoming, pending.open('wb') as output:
                    shutil.copyfileobj(incoming, output, 1024 * 1024)
                pending.replace(target)
            count += 1
            size += entry.file_size
    return {'content_files': count, 'content_bytes': size, 'account_data_imported': False}


def extract_art(data):
    """Use CriCodecs to populate the existing server's extracted-art layout."""
    from cricodecs import cpk

    files = data / 'client' / 'files'
    destination = (data / 'cpk_extract').resolve()
    packs = sorted(p for p in files.glob('*/sd/*/*.cpk')
                   if p.parent.name in {'area', 'banner', 'gacha'})
    if not packs:
        raise FileNotFoundError('No local area, banner or gacha packs were found.')
    count, size = 0, 0
    for path in packs:
        relative = path.relative_to(files)
        output = destination / relative.parts[0] / relative.parts[2] / path.stem
        archive = cpk.load(str(path))
        entries = archive.file_infos()
        for entry in entries:
            name = PurePosixPath(entry.full_path)
            if name.is_absolute() or '..' in name.parts or '\\' in str(name) or ':' in str(name):
                raise ValueError('Invalid CPK entry path: ' + str(name))
            target = output.joinpath(*name.parts).resolve()
            if output.resolve() not in target.parents:
                raise ValueError('CPK entry escaped its output directory.')
        # Original packs can contain distinct entries with identical filenames.
        # Use the library's conflict handling so all original entries survive.
        archive.extract(str(output), disambiguate_conflicts=True)
        extracted = [p for p in output.rglob('*') if p.is_file()]
        expected_size = sum(entry.extract_size for entry in entries)
        if len(extracted) != len(entries) or sum(p.stat().st_size for p in extracted) != expected_size:
            raise ValueError('Extracted pack size/count mismatch: ' + str(path))
        count += len(entries)
        size += expected_size
    return {'art_packs': len(packs), 'art_files': count, 'art_bytes': size}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--archive', type=Path)
    parser.add_argument('--data', required=True, type=Path)
    parser.add_argument('--extract-art', action='store_true',
                        help='Extract existing client art packs with CriCodecs into the server art folder.')
    args = parser.parse_args()
    if not args.archive and not args.extract_art:
        parser.error('Provide --archive, --extract-art, or both.')
    result = import_cache(args.archive, args.data) if args.archive else {}
    if args.extract_art:
        result.update(extract_art(args.data))
    print(json.dumps(result, indent=2))
