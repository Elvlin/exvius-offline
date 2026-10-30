"""Publish a clean source snapshot and release assets to the private review repository."""
import argparse
import json
from pathlib import Path
import re
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[2]
REPO = 'Elvlin/exvius-offline'
STAGE = ROOT / 'source/build/distribution/repository'
SKIP = {'.git', '.gradle', '.idea', '__pycache__', 'build', 'out', 'node_modules'}
PRIVATE_SUFFIXES = {'.jks', '.keystore', '.p12', '.pfx', '.pem', '.key', '.apk', '.zip', '.pyc'}
SENSITIVE = re.compile(rb'(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,}|sk-proj-[A-Za-z0-9_-]{30,}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----)')


def run(*args, capture=False):
    result = subprocess.run(list(args), cwd=ROOT, capture_output=capture, text=True)
    if result.returncode:
        raise RuntimeError('Command failed: ' + ' '.join(args[:3]) + (': ' + result.stderr[:400] if capture else ''))
    return result.stdout if capture else ''


def prepare():
    assert STAGE.resolve().is_relative_to((ROOT / 'source/build/distribution').resolve())
    STAGE.mkdir(parents=True, exist_ok=True)
    selected = []
    for folder in ('exvius', 'server', 'memorial', 'harness', 'docs', 'server_app'):
        for source in sorted((ROOT / 'source' / folder).rglob('*')):
            relative = source.relative_to(ROOT)
            if not source.is_file() or source.is_symlink() or any(part in SKIP for part in relative.parts):
                continue
            if source.suffix.lower() in PRIVATE_SUFFIXES or source.name in {'.env', 'local.properties', 'key.properties'}:
                continue
            selected.append((source, relative))
    selected.extend((ROOT / path, Path(path)) for path in ('README.md', 'source/README.md', 'data/README.md', 'data/latest.json'))
    selected.extend((path, path.relative_to(ROOT)) for path in (ROOT / 'release').rglob('*') if path.is_file())
    for source, relative in selected:
        if source.stat().st_size >= 95 * 1024 * 1024:
            raise ValueError('Large file belongs in release assets: ' + str(relative))
        if source.suffix.lower() not in {'.png', '.jpg', '.jpeg', '.jar'} and SENSITIVE.search(source.read_bytes()):
            raise ValueError('Possible private credential in: ' + str(relative))
        target = STAGE / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    (STAGE / '.gitignore').write_text('''/logs/
/tools/vendor/
/repository snapshots/
/source/build/
/source/out/
.gradle/
__pycache__/
*.pyc
*.apk
*.zip
*.jks
*.keystore
*.part
.env
local.properties
''')
    print(f'Prepared {len(selected)} source and documentation files. Saves, logs, signing keys and build outputs excluded.', flush=True)


def publish(version, upload, allow_public=False):
    metadata = json.loads(run('gh', 'repo', 'view', REPO, '--json', 'isPrivate,url', capture=True))
    if not metadata['isPrivate'] and not allow_public:
        raise ValueError('Public publication requires the explicit --allow-public option.')
    prepare()
    if not (STAGE / '.git').is_dir():
        run('git', '-C', str(STAGE), 'init', '-b', 'main')
        run('git', '-C', str(STAGE), 'remote', 'add', 'origin', 'https://github.com/' + REPO + '.git')
    origin = run('git', '-C', str(STAGE), 'remote', 'get-url', 'origin', capture=True).strip()
    if origin != 'https://github.com/' + REPO + '.git':
        raise ValueError('Unexpected source snapshot repository')
    run('git', '-C', str(STAGE), 'config', 'user.name', 'Elvlin')
    run('git', '-C', str(STAGE), 'config', 'user.email', '74374870+Elvlin@users.noreply.github.com')
    run('git', '-C', str(STAGE), 'config', 'core.autocrlf', 'false')
    run('git', '-C', str(STAGE), 'add', 'README.md', '.gitignore', 'source', 'release', 'data')
    status = run('git', '-C', str(STAGE), 'diff', '--cached', '--name-only', capture=True)
    if status.strip():
        run('git', '-C', str(STAGE), 'commit', '-q', '-m', 'Publish Exvius Offline ' + version + ' preview source and downloads')
    run('git', '-C', str(STAGE), '-c', 'credential.https://github.com.helper=', '-c',
        'credential.https://github.com.helper=!gh auth git-credential', 'push', '-u', 'origin', 'main')
    run('gh', 'repo', 'edit', REPO, '--add-topic', 'ffbe', '--add-topic', 'offline',
        '--add-topic', 'preservation', '--add-topic', 'android', '--add-topic', 'fan-project')
    tag = 'v' + version
    release = subprocess.run(['gh', 'release', 'view', tag, '--repo', REPO, '--json', 'assets'],
                             capture_output=True, text=True)
    if release.returncode:
        run('gh', 'release', 'create', tag, '--repo', REPO, '--target', 'main', '--prerelease',
            '--title', 'Exvius Offline ' + tag + ' Preview', '--notes-file', str(ROOT / 'release/notes-v0.1.0.md'))
        assets = []
    else:
        assets = json.loads(release.stdout)['assets']
    if upload:
        present = {asset['name']: asset for asset in assets}
        paths = sorted((ROOT / 'source/build/distribution/assets').glob('*.zip'))
        paths += sorted((ROOT / 'source/build/distribution/assets').glob('*.apk'))
        missing = []
        for path in paths:
            if path.name in present:
                if present[path.name]['size'] != path.stat().st_size:
                    raise ValueError('Existing release asset differs: ' + path.name)
            else:
                missing.append(str(path))
        if missing:
            print(f'Uploading {len(missing)} release assets ({sum(Path(p).stat().st_size for p in missing) / 1e9:.2f} GB).', flush=True)
            run('gh', 'release', 'upload', tag, '--repo', REPO, *missing)
    print('Private preview: https://github.com/' + REPO, flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--version', default='0.1.0')
    parser.add_argument('--upload', action='store_true')
    parser.add_argument('--stage-only', action='store_true')
    parser.add_argument('--allow-public', action='store_true', help='Allow uploads to an already public repository. Does not change visibility.')
    args = parser.parse_args()
    if args.stage_only:
        prepare()
    else:
        publish(args.version, args.upload, args.allow_public)
