"""Stream the verified content cache into the debuggable test app over USB."""
import argparse
import atexit
import hashlib
import json
from pathlib import Path
import subprocess
import tarfile
import xml.etree.ElementTree as ET

PROJECT = Path(__file__).resolve().parents[2]
PACKAGE = 'com.exvius.offline.test'
CONTENT = {'mst', 'en', 'common_lang', 'localized_texts', 'homeMarquee'}


def cache_registry(adb, template):
    """Update resource versions without replacing the phone's other preferences."""
    original = subprocess.check_output(adb + ['exec-out', 'run-as', PACKAGE,
                                             'cat', 'shared_prefs/gamedata.xml'])
    current = ET.fromstring(original)
    source = ET.parse(template).getroot()
    entries = {node.get('name'): node for node in current}
    for incoming in source:
        name = incoming.get('name', '')
        if incoming.tag != 'string' or not name.startswith('keyF_'):
            continue
        node = entries.get(name)
        if node is None:
            node = ET.SubElement(current, 'string', {'name': name})
        node.text = incoming.text
    digest = hashlib.sha256(original).hexdigest()
    backup = PROJECT / 'data/state/backups' / ('gamedata-before-cache-' + digest[:16] + '.xml')
    if backup.exists():
        if hashlib.sha256(backup.read_bytes()).hexdigest() != digest:
            raise ValueError('Native preferences backup checksum mismatch.')
    else:
        backup.write_bytes(original)
    staging = PROJECT / 'source/build/android/client-cache-transfer-gamedata.xml'
    ET.ElementTree(current).write(staging, encoding='utf-8', xml_declaration=True)
    atexit.register(staging.unlink, missing_ok=True)
    print('Prepared native resource versions; retained other phone preferences. Backup:', backup, flush=True)
    return staging


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--adb', required=True)
    parser.add_argument('--serial', required=True)
    parser.add_argument('--overlay-only', action='store_true')
    parser.add_argument('--missing-only', action='store_true',
                        help='Copy only missing or differently sized versioned content, plus current overrides.')
    parser.add_argument('--content', type=Path,
                        help='Copy only this folder, laid out like the app files folder. Never preferences.')
    parser.add_argument('--log', type=Path, default=PROJECT / 'logs/device-content-adb-20261023.log')
    args = parser.parse_args()
    adb = [args.adb, '-s', args.serial]
    subprocess.run(adb + ['shell', 'am', 'force-stop', PACKAGE], check=True)
    root = PROJECT / 'data/client'
    recovered = PROJECT / 'data/memorial_fill'
    paths = []
    if args.content:
        paths = [(p, 'files/' + p.relative_to(args.content).as_posix())
                 for p in args.content.rglob('*') if p.is_file() and p.name != 'manifest.json']
    elif not args.overlay_only:
        # Recovered maps, town interiors and event packs are a separate source
        # tree. Omitting it leaves World locations without their native assets.
        # Prefer original cache bytes where both trees contain the same path.
        if recovered.is_dir():
            paths.extend((p, 'files/' + p.relative_to(recovered).as_posix())
                         for p in recovered.rglob('*') if p.is_file()
                         and p.relative_to(recovered).parts[0] in CONTENT)
        paths.extend((p, p.relative_to(root).as_posix()) for p in (root / 'files').rglob('*') if p.is_file()
                     and p.relative_to(root / 'files').parts[0] in CONTENT)
    overlay = PROJECT / 'data/overlay'
    if overlay.exists() and not args.content:
        paths.extend((p, 'files/' + p.relative_to(overlay).as_posix())
                     for p in overlay.rglob('*') if p.is_file()
                     and p.relative_to(overlay).as_posix() not in
                     ('shared_prefs/gamedata.xml', 'manifest.json'))
    if not args.content:
        template = overlay / 'shared_prefs/gamedata.xml'
        if not template.exists():
            template = root / 'shared_prefs/gamedata.xml'
        paths.append((cache_registry(adb, template), 'shared_prefs/gamedata.xml'))
    # An override replaces its original path. Verify the effective file once.
    paths = [(path, relative) for relative, path in
             {relative: path for path, relative in paths}.items()]
    expected = {relative: path.stat().st_size for path, relative in paths}
    if args.missing_only:
        # A repaired CPK index has the same byte count as the broken file.
        # Send these recorded repairs even when a size-only inventory matches.
        repair_manifest = recovered / 'manifest.json'
        repaired = ({('files/' + row['path']) for row in
                    json.loads(repair_manifest.read_text(encoding='utf-8'))
                    if row.get('global_extended_id_index') or row.get('global_filename_lookup_linear')}
                    if repair_manifest.is_file() else set())
        result = subprocess.run(adb + ['shell',
            "run-as " + PACKAGE + " find files shared_prefs -type f -exec stat -c '%s %n' {} +"],
            capture_output=True, text=True, check=True)
        present = {}
        for line in result.stdout.splitlines():
            size, relative = line.split(' ', 1)
            present[relative] = int(size)
        paths = [(path, relative) for path, relative in paths
                 if path.is_relative_to(overlay) or relative == 'shared_prefs/gamedata.xml'
                 or (path.is_relative_to(recovered) and relative in repaired)
                 or present.get(relative) != path.stat().st_size]
        print('Existing cache retained; copying', len(paths), 'missing/updated files,',
              sum(path.stat().st_size for path, _ in paths), 'bytes.', flush=True)
    batches, batch, batch_size = [], [], 0
    for path, relative in paths:
        if batch and batch_size + path.stat().st_size > 256 * 1024 * 1024:
            batches.append(batch)
            batch, batch_size = [], 0
        batch.append((path, relative))
        batch_size += path.stat().st_size
    if batch:
        batches.append(batch)
    count, size = 0, 0
    staging = PROJECT / 'source/build/android/client-cache-transfer.tar'
    remote_staging = '/data/local/tmp/exvius-client-cache-transfer.tar'
    with args.log.open('ab') as log:
        for index, batch in enumerate(batches, 1):
            try:
                with tarfile.open(staging, mode='w', format=tarfile.USTAR_FORMAT) as archive:
                    directories = {str(parent).replace('\\', '/') for _, relative in batch
                                   for parent in Path(relative).parents if str(parent) != '.'}
                    for directory in sorted(directories, key=lambda name: (name.count('/'), name)):
                        info = tarfile.TarInfo(directory)
                        info.type, info.mode = tarfile.DIRTYPE, 0o700
                        archive.addfile(info)
                    for path, relative in batch:
                        info = tarfile.TarInfo(relative)
                        info.size, info.mode, info.mtime = path.stat().st_size, 0o600, int(path.stat().st_mtime)
                        with path.open('rb') as content:
                            archive.addfile(info, content)
                        count += 1
                        size += info.size
                subprocess.run(adb + ['push', str(staging), remote_staging],
                               stdout=log, stderr=log, check=True)
                checksum = hashlib.sha256()
                with staging.open('rb') as content:
                    for block in iter(lambda: content.read(1024 * 1024), b''):
                        checksum.update(block)
                digest = checksum.hexdigest()
                remote_digest = subprocess.check_output(adb + ['shell', 'run-as', PACKAGE,
                    'sha256sum', remote_staging], text=True).split()[0]
                if digest != remote_digest:
                    raise ValueError('Staged USB archive checksum mismatch.')
                subprocess.run(adb + ['shell', 'run-as', PACKAGE, 'tar', '-xf', remote_staging],
                               stdout=log, stderr=log, check=True)
            finally:
                subprocess.run(adb + ['shell', 'rm', '-f', remote_staging],
                               stdout=log, stderr=log, check=True)
                staging.unlink(missing_ok=True)
            result = subprocess.run(adb + ['shell',
                "run-as " + PACKAGE + " find files shared_prefs -type f -exec stat -c '%s %n' {} +"],
                capture_output=True, text=True, check=True)
            present = {line.split(' ', 1)[1]: int(line.split(' ', 1)[0])
                       for line in result.stdout.splitlines()}
            if any(present.get(relative) != path.stat().st_size for path, relative in batch):
                raise ValueError('USB batch verification failed; retain existing files and diagnose this batch.')
            print(f'Verified USB batch {index}/{len(batches)}: {count}/{len(paths)} files, '
                  f'{size // 1048576} MiB', flush=True)
    result = subprocess.run(adb + ['shell',
        "run-as " + PACKAGE + " find files shared_prefs -type f -exec stat -c '%s %n' {} +"],
        capture_output=True, text=True, check=True)
    present = {}
    for line in result.stdout.splitlines():
        nbytes, relative = line.split(' ', 1)
        present[relative] = int(nbytes)
    missing = [name for name, nbytes in expected.items() if present.get(name) != nbytes]
    if missing:
        raise ValueError('Native cache verification failed: ' + str(len(missing)) + ' missing/different files.')
    print(f'USB content complete: {count} files, {size} bytes. '
          f'Verified {len(expected)} expected native cache paths and byte counts. No account data copied.', flush=True)


if __name__ == '__main__':
    main()
