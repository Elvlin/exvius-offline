"""Serialize native seekable indexes alongside the ciphertext they address.

The integer, pair-key and grouped-vector layouts are from the original GL9 readers.
Each supported schema must reproduce its preserved original index exactly.
"""
import re
import struct
from pathlib import Path

from decode_client_data import client_manifest, decode


# parseKey/readIndexFile in the pinned original libgame.so:
# UnitExplain 0x1cc2a80, UnitSubCategory 0x1cfe9cc,
# Challenge 0x1d0d698/0x1d0db98, Dungeon 0x1c961d8/0x1c96e50.
# AI pair key 0x1cd1040, direct reader 0x1cd176c,
# integer-to-pair-vector group reader 0x1ccab1c.
# Banner parseKey 0x1d21460, direct reader 0x1d21a6c,
# grouped reader 0x1c42cc4. Type groups select Global Android platform 1.
SCHEMAS = {
    'F_BANNER_MST': ('fSxqkF10', ('w2A76noc',)),
    'F_UNIT_EXPLAIN_MST': ('3HriTp6B', ()),
    'F_UNIT_SUB_CATEGORY_MST': ('SVT5aU9n', ()),
    'F_CHALLENGE_MST': ('V36ygRYs', ('qo3PECw6',)),
    'F_DUNGEON_MST': ('U9iHsau3', ('Esxe71j3', 'uv60hgDW')),
    # Original GL46 (8110 bytes) and GL265 (61802 bytes) reproduce exactly.
    'F_QUEST_SUB_MST': ('7Svg2kdT', ('Z34jU7ue',)),
    'F_RESOURCE_MAP_MST': ('Nnb20keZ', ()),
    'F_AI_MST': (('8a6gAwN9', 'w7VR6ypY'), ('8a6gAwN9',)),
    # GL9 parseKey readers: Sacrifice 0x1c50f78, LB levels 0x1cd55cc,
    # MedalExchange 0x1ca83fc, MonsterSkillSet 0x1ccdbd0,
    # BeastCp 0x1c469e4, GachaStore 0x1ca6744, RB season 0x1d16bdc,
    # Ticket 0x1c63468. Original-byte proofs: Temporary/index-rebuild/.
    'F_SACRIFICE_MST': ('woghJa61', ()),
    'F_LIMITBURST_LV_MST': (('PR2HIc71', '7wV3QZ80'), ()),
    'F_MEDAL_EXCHANGE_MST': ('S21FT3L8', ()),
    'F_MONSTER_SKILL_SET_MST': ('A5x02C6a', ()),
    'F_BEAST_CP_MST': ('5hqFc4ey', ()),
    'F_GACHA_STORE_MST': ('X1IuZnj2', ()),
    'F_RB_SS_MST': ('6Z9DxQFf', ()),
    'F_TICKET_MST': ('zJ1A6HXm', ('zF6QIY2r',)),
}
# These use row ordinals or additional typed groups rather than only field IDs.
# Store parseKey 0x1ca52cc, RB reward 0x1d19d1c, recipe 0x1c420f4.
COMPLEX_SCHEMAS = {
    'F_STORE_ITEM_MST': (None, ('Z20mNDvL',)),
    'F_RB_SS_REWARD_MST': (None, ('6Z9DxQFf',)),
    'F_SUBLIMATION_RECIPE_MST': ('SJ56uhz2', (('j1z0Nxo9', 'hxu12ZFS'),)),
    # Mission parseKey 0x1c8d778, reader 0x1c90110: integer dungeon
    # groups, string link groups, then the type-2 and type-6 vectors.
    'F_MISSION_MST': ('qo3PECw6', ('U9iHsau3',)),
}
HEADER = bytes.fromhex('0000beff')
TRAILER = bytes.fromhex('beff0000')


def short_count(count):
    if not 0 <= count <= 65535:
        raise ValueError('Native uint16 index count overflow: ' + str(count))
    return struct.pack('<H', count)


def schema(table):
    return SCHEMAS[table] if table in SCHEMAS else COMPLEX_SCHEMAS[table]


def row_identity(identity, row, ordinal):
    if identity is None:
        return (ordinal,)
    fields = (identity,) if isinstance(identity, str) else identity
    return tuple(int(row[field]) for field in fields)


def build_index(table, raw, key, version):
    """Keep native first-record lookup and ordered duplicate group membership."""
    identity, group_fields = schema(table)
    key_format = '<' + 'i' * (1 if identity is None or isinstance(identity, str) else len(identity))
    _, rows = decode(raw, key)
    direct, groups, offset = {}, [{} for _ in group_fields], 0
    lines = [line for line in raw.splitlines(keepends=True) if line.strip()]
    if len(lines) != len(rows):
        raise ValueError('Decoded native row count differs from physical lines.')
    # Blank lines are not used in the preserved masters. Reject them rather
    # than silently shifting the byte offsets used by the native fseek call.
    if b''.join(lines) != raw:
        raise ValueError('Native indexed master contains blank lines.')
    materials = {}
    mission_links, mission_types = {}, {2: [], 6: []}
    for ordinal, (line, row) in enumerate(zip(lines, rows)):
        body = line.rstrip(b'\r\n')
        ident = row_identity(identity, row, ordinal)
        direct.setdefault(ident, (offset, len(body)))
        grouped = table != 'F_DUNGEON_MST' or row['rFd5CiV2'] == '1'
        if table == 'F_BANNER_MST':
            grouped = '1' in row.get('T4o9heqC', '').split(',')
        if grouped:
            for field, group in zip(group_fields, groups):
                fields = (field,) if isinstance(field, str) else field
                group_key = tuple(int(row[f]) for f in fields)
                group.setdefault(group_key, []).append(ident)
        if table == 'F_SUBLIMATION_RECIPE_MST' and row['j1z0Nxo9'] == '1' and row['25oxcKwN']:
            materials.setdefault(ident, tuple(int(v) for v in row['25oxcKwN'].split(',')))
        if table == 'F_MISSION_MST':
            mission_links.setdefault(row['dIPkNn61'], []).append(ident[0])
            kind = int(row['gQR24kST'])
            if kind in mission_types and kind not in mission_types[kind]:
                mission_types[kind].append(ident[0])
        offset += len(line)
    # The preserved GL325 LB file writes all 96,241 pairs but stores its
    # count modulo uint16, exactly as the client's writer at 0x1cd5c50.
    # Preserve that original encoding, and expose it in the checker report.
    count = len(direct) & 65535 if table == 'F_LIMITBURST_LV_MST' else len(direct)
    out = bytearray(HEADER + struct.pack('<I', int(version)) + short_count(count))
    for ident, (start, size) in sorted(direct.items()):
        out += struct.pack(key_format + 'II', *ident, start, size)
    for group in groups:
        out += short_count(len(group))
        for ident, members in sorted(group.items()):
            out += struct.pack('<' + 'i' * len(ident), *ident) + short_count(len(members))
            for member in members:
                out += struct.pack(key_format, *member)
    if table == 'F_SUBLIMATION_RECIPE_MST':
        out += short_count(len(materials))
        for ident, values in sorted(materials.items()):
            out += struct.pack('<i', *ident) + short_count(len(values))
            out += struct.pack('<' + 'i' * len(values), *values)
    if table == 'F_MISSION_MST':
        out += short_count(len(mission_links))
        for name, values in sorted(mission_links.items()):
            encoded = name.encode('utf-8')
            out += short_count(len(encoded)) + encoded + short_count(len(values))
            out += struct.pack('<' + 'i' * len(values), *values)
        for values in mission_types.values():
            out += short_count(len(values)) + struct.pack('<' + 'i' * len(values), *values)
    return bytes(out + TRAILER)


def paired_index(table, target, raw, key):
    """Return the same-version index path and bytes for a supported master."""
    if table not in SCHEMAS and table not in COMPLEX_SCHEMAS:
        return None
    target = Path(target)
    match = re.fullmatch(r'Ver(\d+)_([A-Za-z0-9]{8})\.dat', target.name)
    if not match:
        raise ValueError('Expected a versioned native master filename.')
    return target.with_name(match[2] + '.i'), build_index(table, raw, key, match[1])


def validate_release_indexes(files, root, registry):
    """Reject a publish input whose selected ciphertext and index disagree."""
    def content(value):
        return value.read_bytes() if isinstance(value, Path) else value
    manifest = client_manifest(root / 'repository snapshots/FFBE-Global-v9.0.0-original.apk')
    checked = []
    for info in manifest.values():
        table, token = info['table'], info['token']
        if table not in SCHEMAS and table not in COMPLEX_SCHEMAS:
            continue
        version = registry.get('key' + table)
        name = 'native/mst/Ver' + str(version) + '_' + token + '.dat'
        if name not in files:
            continue
        index = 'native/mst/' + token + '.i'
        expected = build_index(table, content(files[name]), info['key'], version)
        if index not in files or content(files[index]) != expected:
            raise ValueError('Native master index does not match selected ciphertext: ' + table)
        checked.append(table)
    return checked
