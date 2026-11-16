"""Restore omitted native loot columns from the retained, identical actor/part rows.

This is a data authoring helper. It preserves existing indexed columns, including
normal-drop repairs, and does not run a Python server or change encounter bindings.
"""
import hashlib
import json
import argparse
import sys
from pathlib import Path

def _scratch(root):
    path = root / 'build' / 'scratch'
    path.mkdir(parents=True, exist_ok=True)
    return path


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / 'Japan content/Shared sources/memorial_battle_decoded/F_MONSTER_PARTS_MST.ndjson'
TARGET = ROOT / 'source/server/content/battle/F_MONSTER_PARTS_MST.tsv'
CHANNELS = ('MZn8LC6H', 'g4voc2Aw', 'Vf5DGw07')
IDENTITY = ('xqartN26', '6Yc4RkdM')


def restore_encounter_channels(document, source=None):
    """Forward omitted channels only for an unchanged, exact native actor/part.

    An equal name or a donor profile is insufficient. Stage-authored normal
    rewards and all existing channel overrides remain authoritative.
    """
    sys.path.insert(0, str(ROOT / 'source/server'))
    from battle_content import IndexSource, PARTS_TOKENS, PARTS_DEFAULTS

    source = source or IndexSource()
    original = {tuple(row[key] for key in IDENTITY): row
                for row in source.load('F_MONSTER_PARTS_MST')}
    source_hash = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
    totals = {key: 0 for key in CHANNELS}
    changed_missions = []
    for mid, entry in document['missions'].items():
        bundle = entry.get('bundle', {})
        parts = {tuple(row[key] for key in IDENTITY): row
                 for row in bundle.get('bV34YIJQ', [])}
        changed = {key: 0 for key in CHANNELS}
        for tag in ('6v0LPiRe', 'JR7jZci2'):
            for row in bundle.get(tag, []):
                identity = tuple(row.get(key) for key in IDENTITY)
                native = original.get(identity)
                served = parts.get(identity)
                if not native or not served:
                    continue
                if any(served.get(key, PARTS_DEFAULTS.get(key, '')) !=
                       native.get(key, PARTS_DEFAULTS.get(key, '')) for key in PARTS_TOKENS):
                    continue
                if row.get('9BetM2Ds', '') != native.get('9BetM2Ds', ''):
                    continue
                for channel in CHANNELS:
                    if native.get(channel) and not row.get(channel):
                        row[channel] = native[channel]
                        changed[channel] += 1
                        totals[channel] += 1
        phases = {row['6v7y3QcJ']: row.get('2fY1IomW')
                  for row in bundle.get('an6TB4WS', [])}
        for row in bundle.get('y35YvQjZ', []):
            group = phases.get(row.get('6v7y3QcJ'))
            # Rows with real slot identities already own their explicit
            # per-enemy contract. Only restore the old aggregate wave shape.
            if not group or row.get('2fY1IomW') == group or row.get('_drop_choices'):
                continue
            slots = [slot for slot in bundle.get('Bi6hVv34', [])
                     if slot.get('2fY1IomW') == group]
            channels = {key: [] for key in ('9BetM2Ds',) + CHANNELS}
            exact = bool(slots)
            for slot in slots:
                matches = [(identity, part) for identity, part in parts.items()
                           if identity[0] == slot['xqartN26']]
                if not matches:
                    exact = False
                for identity, part in matches:
                    native = original.get(identity)
                    if not native or any(part.get(key, PARTS_DEFAULTS.get(key, '')) !=
                            native.get(key, PARTS_DEFAULTS.get(key, '')) for key in PARTS_TOKENS):
                        exact = False
                        continue
                    for channel, candidates in channels.items():
                        candidates.extend(item for item in native.get(channel, '').split(',') if item)
            if not exact or row.get('9BetM2Ds', '') != ','.join(channels['9BetM2Ds']):
                continue
            for channel in CHANNELS:
                if channels[channel] and not row.get(channel):
                    row[channel] = ','.join(channels[channel])
                    changed[channel] += 1
                    totals[channel] += 1
        if any(changed.values()):
            changed_missions.append(mid)
            entry['native_loot_channels'] = {
                'source': SOURCE.relative_to(ROOT).as_posix(),
                'source_sha256': source_hash,
                'identity': list(IDENTITY),
                'restored_rows': changed,
                'proof': 'Exact native actor/part, unchanged full served profile '
                         'and identical normal-drop definition. Existing nonempty '
                         'reward channels and authored overrides preserved.',
            }
    return {'restored_rows': totals, 'missions': changed_missions}


def restore():
    source_rows = {}
    source_hash = hashlib.sha256()
    available = set()
    counts = {key: 0 for key in CHANNELS}
    with SOURCE.open('rb') as stream:
        for line in stream:
            source_hash.update(line)
            if not line.strip():
                continue
            row = json.loads(line)
            identity = tuple(str(row[key]) for key in IDENTITY)
            if identity in source_rows:
                raise ValueError('Duplicate source actor/part identity: ' + repr(identity))
            values = {}
            for key in CHANNELS:
                if key not in row:
                    continue
                if not isinstance(row[key], str):
                    raise ValueError('Non-string source loot channel: ' + repr((identity, key)))
                available.add(key)
                values[key] = row[key]
                counts[key] += bool(row[key])
            source_rows[identity] = values

    lines = TARGET.read_text(encoding='utf-8').splitlines()
    if not lines or not lines[0].startswith('# '):
        raise ValueError('Native battle index provenance header missing')
    metadata = json.loads(lines[0][2:])
    if metadata.get('table') != 'F_MONSTER_PARTS_MST' or metadata.get('escape') != 'json-notab':
        raise ValueError('Unexpected native battle index format')
    old_fields = metadata['fields']
    fields = old_fields + [key for key in CHANNELS if key in available and key not in old_fields]
    identity_columns = [old_fields.index(key) for key in IDENTITY]
    seen = set()
    output = []
    for line in lines[1:]:
        if not line:
            continue
        cells = line.split('\t')
        if len(cells) != len(old_fields):
            raise ValueError('Native battle index row arity differs from its header')
        identity = tuple(cells[index] for index in identity_columns)
        if identity in seen:
            raise ValueError('Duplicate indexed actor/part identity: ' + repr(identity))
        if identity not in source_rows:
            raise ValueError('Indexed actor/part has no exact source row: ' + repr(identity))
        seen.add(identity)
        values = source_rows[identity]
        for key in fields[len(old_fields):]:
            cells.append(json.dumps(values.get(key, ''), ensure_ascii=False)[1:-1])
        # Existing cells remain byte-for-byte intact. A rerun never overwrites
        # a subsequently authored regional override in an existing column.
        output.append('\t'.join(cells))
    if seen != source_rows.keys() or len(output) != metadata.get('rows'):
        raise ValueError('Source/index actor-part sets or declared row count differ')
    metadata['fields'] = fields
    metadata['absent'] = [key for key in metadata.get('absent', []) if key not in available]
    for key in CHANNELS:
        if key not in available and key not in metadata['absent']:
            metadata['absent'].append(key)
    metadata['loot_channel_source'] = {
        'path': SOURCE.relative_to(ROOT).as_posix(),
        'sha256': source_hash.hexdigest(),
        'identity': list(IDENTITY),
        'rows': len(source_rows),
        'columns': [key for key in CHANNELS if key in available],
        'nonempty_rows': {key: counts[key] for key in CHANNELS if key in available},
        'preserved': 'All existing columns and actor/part identities, in original indexed order.',
        'authoring_helper': 'source/exvius/restore_native_loot_channels.py',
    }
    pending = ROOT / 'build/scratch/native-loot-index.tsv'
    pending.parent.mkdir(parents=True, exist_ok=True)
    try:
        with pending.open('w', encoding='utf-8', newline='\n') as stream:
            stream.write('# ' + json.dumps(metadata, ensure_ascii=False) + '\n')
            stream.write('\n'.join(output) + '\n')
        pending.replace(TARGET)
    finally:
        pending.unlink(missing_ok=True)
    print('CHECKPOINT restored native loot channels:', json.dumps(metadata['loot_channel_source'], ensure_ascii=True))


def restore_served_content():
    """Apply exact-identity forwarding to authored files used by native assemble."""
    results = {}
    for filename in ('event_encounters.json', 'responses.json'):
        path = ROOT / 'source/server' / filename
        document = json.loads(path.read_text(encoding='utf8'))
        view = document if filename == 'event_encounters.json' else {
            'missions': {key: {'bundle': value} for key, value in document.items()
                         if isinstance(value, dict)}}
        restored = restore_encounter_channels(view)
        results[filename] = restored
        if not any(restored['restored_rows'].values()):
            continue
        pending = _scratch(ROOT) / ('loot-' + filename)
        try:
            with pending.open('w', encoding='utf8', newline='\n') as stream:
                if filename == 'responses.json':
                    json.dump(document, stream, ensure_ascii=False, indent=1)
                else:
                    json.dump(document, stream, ensure_ascii=False, separators=(',', ':'))
                stream.write('\n')
            pending.replace(path)
        finally:
            pending.unlink(missing_ok=True)
    return results


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--content-only', action='store_true',
                        help='Restore exact-actor served channels without rewriting the index.')
    arguments = parser.parse_args()
    if not arguments.content_only:
        restore()
    print('CHECKPOINT served loot channels:', json.dumps(restore_served_content()))
