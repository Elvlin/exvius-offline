"""Compare native message references with each preserved package's text tables."""
from pathlib import Path
import hashlib
import json
import re
import struct
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools/vendor/python'))
from cricodecs import cpk


def inspect(path):
    archive = cpk.load(str(path))
    entries = {e.full_path: i for i, e in enumerate(archive.file_infos())}
    # Scene bundles deliberately reuse their package's shared message table.
    # Auxiliary scene binaries do not each carry a same-named text file.
    shared_cells, shared_original = {}, {}
    for member, index in entries.items():
        if member.endswith('_text_sg.txt'):
            for line in archive.file_bytes(index).decode('utf-8-sig').splitlines():
                fields = line.split('^')
                if fields[0].isdigit(): shared_cells[fields[0]] = fields[1:]
        elif member.endswith('_text.txt'):
            for line in archive.file_bytes(index).decode('utf-8-sig').splitlines():
                key, sep, text = line.partition(',')
                if sep and key.isdigit(): shared_original[key] = text
    output = []
    for member, index in entries.items():
        if member != 'map.bin' and not member.endswith('_event.bin'):
            continue
        prefix = 'map' if member == 'map.bin' else member[:-len('.bin')]
        localized = entries.get(prefix + '_text_sg.txt')
        base = entries.get(prefix + '_text.txt')
        cells = dict(shared_cells)
        if localized is not None:
            for line in archive.file_bytes(localized).decode('utf-8-sig').splitlines():
                fields = line.split('^')
                if fields[0].isdigit(): cells[fields[0]] = fields[1:]
        original = dict(shared_original)
        if base is not None:
            for line in archive.file_bytes(base).decode('utf-8-sig').splitlines():
                key, sep, text = line.partition(',')
                if sep and key.isdigit(): original[key] = text
        raw = archive.file_bytes(index)
        references = sorted({str(struct.unpack('>I', m[1])[0])
                             for m in re.finditer(rb'\x08\x00\x04(.{4})', raw, re.DOTALL)
                             if 100000 <= struct.unpack('>I', m[1])[0] <= 999999})
        missing = [key for key in references if key not in cells]
        blank = [key for key in references if key in cells and (not cells[key] or not cells[key][0].strip())]
        output.append({'member': member, 'references': references, 'missing': missing, 'blank': blank,
                       'binary_sha256': hashlib.sha256(raw).hexdigest(),
                       'base_missing': [key for key in references if key not in original]})
    return output


def main():
    reports = []
    folders = ('data/client/files', 'data/memorial_fill', 'data/overlay')
    for folder in folders:
        base = ROOT / folder / 'common_lang/sd'
        packages = [p for parent in base.iterdir() if parent.is_dir() and
                    parent.name.startswith(('map', 'event')) for p in parent.rglob('*.cpk')]
        for path in packages:
            rows = inspect(path)
            reports.append({'path': path.relative_to(ROOT).as_posix(), 'scripts': rows})
    problems = [r for r in reports if any(s['missing'] or s['blank'] for s in r['scripts'])]
    from approved_native_repairs import GLOBAL_TOWN_PACKAGES
    effective = {}
    for folder in folders:
        for report in reports:
            prefix = folder + '/'
            if report['path'].startswith(prefix):
                relative = report['path'][len(prefix):]
                if '/test/' not in relative:
                    effective[relative] = report
    for relative in GLOBAL_TOWN_PACKAGES:
        path = ROOT / 'data/client/files' / relative
        effective[relative] = {'path': path.relative_to(ROOT).as_posix(), 'scripts': inspect(path)}
    gaps = []
    for relative, report in effective.items():
        stem = re.sub(r'^Ver\d+_', '', Path(relative).stem)
        for script in report['scripts']:
            if script['member'] not in ('map.bin', stem + '_event.bin'):
                continue
            if script['missing']:
                gaps.append({'path': relative, 'member': script['member'], 'missing': script['missing'],
                             'base_missing': script['base_missing']})
    doc = {'packages': len(reports), 'problem_packages': len(problems), 'problems': problems,
           'effective_message_gaps': gaps,
           'scope': 'Typed native message command 8 with four-byte text IDs. Shared package text tables are included. Effective primary scripts exclude debug packages and incorporate the hash-pinned Global replacements. This is a static dependency audit, not proof that every script branch is reachable.'}
    (ROOT / 'logs/ffbe-dialogue-dependency-audit-20261110.json').write_text(json.dumps(doc, indent=1), encoding='utf8')
    print(json.dumps({'packages': len(reports), 'raw_candidate_packages': len(problems), 'effective_message_gaps': gaps}), flush=True)


if __name__ == '__main__': main()
