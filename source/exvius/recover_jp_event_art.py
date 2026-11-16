"""Extract exact original JP event images using the proven native decoder.

No image is resized, retouched, generated or substituted with a Global image.
Stale native icon links are preserved as evidence rather than silently repaired.
"""
import hashlib
import json
from pathlib import Path
import re
import zipfile

from decode_client_data import TRIPLET, decode, getter_manifest
from recover_jp_assets import DECODER_SHA256, decoded_member, inspect_member, source_rows

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / 'Japan content/Earlier JP crossovers'
SOURCES = BASE / 'Sources'
PACKS = ROOT / 'Japan content/Shared sources/jp_andapp'
NATIVE_SHA = '6c7e501c98939581528df3d712ff1f58afcfd392160f1e71ef1f903d49926b77'
PRIMARY_ROTO = {'spd_20221120_bn_list_ROTO_01.png': '6210',
                'spd_20221120_bn_list_ROTO_weapon1.png': '6212',
                'spd_20221120_bn_list_ROTO_weapon2.png': '6213',
                'spd_20221120_bn_list_ROTO_chara.png': '6214'}
# Full original cards were visually read, with their titles compared to the
# exact native event identities. Date-like filenames alone are not bindings.
EVENT_CARDS = {
    '702': 'spd_bn_list_imperial_saga.png',
    '738': 'spd_20161222_bn_list_FFBE.png',
    '742': 'spd_20170120_bn_list_ffbe.png',
    '771': 'spd_20170721_bn_list_BDFE.png',
    '772': 'spd_20170724_bn_list_BDFE_02.png',
    '3037': 'spd_20190911_bn_list_SINoALICE_01.png',
    '3038': 'spd_20190911_bn_list_SINoALICE_02.png',
    '3147': 'spd_20200406_bn_list_ToM_02.png',
    '4082': 'spd_20210906_bn_list_sinoalice_01.png',
    '4480': 'spd_20240111_bn_list_saga_01.png',
    '4481': 'spd_20240111_bn_list_evolve.png',
    '4482': 'spd_20240111_bn_list_saga_weapon.png',
    '4483': 'spd_20240111_bn_list_saga_weapon2.png',
    '4484': 'spd_20240111_bn_list_saga_chara.png',
    '6410': 'spd_20240119_bn_list_saga_01.png',
    '6411': 'spd_20240119_bn_list_saga_weapon.png',
    '6412': 'spd_20240119_bn_list_evolve.png',
    '6413': 'spd_20240119_bn_list_saga_chara.png',
    '6210': 'spd_20221120_bn_list_ROTO_01.png',
    '6212': 'spd_20221120_bn_list_ROTO_weapon1.png',
    '6213': 'spd_20221120_bn_list_ROTO_weapon2.png',
    '6214': 'spd_20221120_bn_list_ROTO_chara.png',
    '6215': 'spd_20240219_bn_list_ROTO_crown.png',
    '6216': 'spd_20240219_bn_list_roto_chara.png',
    '6217': 'spd_20240219_bn_list_evolve_ROTO.png',
    '4500': 'spd_20240228_bn_list_roto_01.png',
    '4501': 'spd_20240228_bn_list_ROTO_weapon.png',
    '4502': 'spd_20240228_bn_list_roto_chara.png',
}
PATTERNS = (
    r'spd_20210906_bn_list_sinoalice_01(?:_last)?\.png',
    r'spd_20221120_bn_list_ROTO_(?:01|chara|weapon1|weapon2)(?:_last)?\.png',
    r'spd_202401(?:11|19)_bn_list_saga_(?:01|chara|weapon|weapon2)(?:_last)?\.png',
    r'spd_202401(?:11|19)_bn_list_evolve(?:_last)?\.png',
    r'spd_20240219_bn_list_(?:roto|roto_chara|ROTO_crown)(?:_last)?\.png',
    r'spd_20240219_bn_list_evolve_ROTO(?:_last)?\.png',
    r'spd_20240228_bn_list_(?:roto_01|roto_chara|ROTO_weapon)(?:_last)?\.png',
)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def relative(path):
    return path.relative_to(ROOT).as_posix()


def load_rows(path):
    return [json.loads(s) for s in path.read_text(encoding='utf-8').splitlines() if s.strip()]


def original_tables():
    with zipfile.ZipFile(ROOT / 'repository snapshots/FFBE-Memorial-EN-Global-Events-v208.apk') as z:
        native = z.read('lib/arm64-v8a/libgame.so')
    if sha(native) != NATIVE_SHA:
        raise ValueError('Original native table authority changed.')
    manifest = getter_manifest(native)
    for match in TRIPLET.finditer(native):
        table, token, key = (s.decode() for s in match.groups())
        manifest[token] = {'table': table, 'token': token, 'key': key}
    result, receipts = {}, []
    for token in ('LM1APs6u', 'oB0YVw67'):
        path = next(PACKS.glob('Ver*_' + token + '.dat'))
        mode, values = decode(path.read_bytes(), manifest[token]['key'])
        result[manifest[token]['table']] = values
        receipts.append({'table': manifest[token]['table'], 'source': relative(path),
                         'sha256': sha(path.read_bytes()), 'mode': mode, 'rows': len(values)})
    return result, receipts, manifest


def main():
    decoder = Path(__file__).with_name('decode_gl9_member.py')
    if sha(decoder.read_bytes()) != DECODER_SHA256:
        raise ValueError('Proven original member decoder changed.')
    tables, table_receipts, manifest = original_tables()
    areas = load_rows(SOURCES / 'Event graph/F_AREA_MST.ndjson')
    dungeons = load_rows(SOURCES / 'Event graph/F_DUNGEON_MST.ndjson')
    area_ids = {r['uv60hgDW'] for r in areas}
    icons = {r['0HUPxDf1']: r for r in tables['F_ICON_MST']}
    linked_icons = {r.get('0HUPxDf1') for r in areas + dungeons} - {'0', None, ''}
    exact_filenames = {icons[i]['qtkvrS60'] for i in linked_icons if i in icons} | set(EVENT_CARDS.values())
    home_rows = []
    for r in tables['F_BANNER_MST']:
        # A lone number may be a news ID, not an area. Only the demonstrated
        # world,land,area,dungeon,mission route is a native event ownership link.
        route = r.get('1X65WPLU', '').split(',')
        if r.get('rUP3Gix0') == '7' and len(route) == 5 and route[2] in area_ids:
            home_rows.append(r)
    home_filenames = {r['6Dgaqir0'] for r in home_rows if r.get('6Dgaqir0')}
    metadata = {r['name']: r for r in json.loads((ROOT / 'Japan content/Shared sources/original-jp-archive-index.json').read_text())['files']}
    pack_names = ['spdungeon' + str(i) + '.cpk' for i in range(1, 9)] + ['banner1.cpk', 'banner2.cpk']
    assets, pack_receipts = [], []
    for name in pack_names:
        path = PACKS / name
        raw, toc, start = source_rows(path)
        expected = metadata[name]
        if len(raw) != int(expected['size']) or hashlib.md5(raw).hexdigest() != expected['md5'] or hashlib.sha1(raw).hexdigest() != expected['sha1']:
            raise ValueError('Original archive package checksum differs: ' + name)
        pack_receipts.append({'path': relative(path), 'sha256': sha(raw), 'members': len(toc)})
        for row in toc:
            member = row['FileName']
            selected = (any(re.fullmatch(pattern, member) for pattern in PATTERNS)
                        or member in home_filenames
                        or member in exact_filenames and member not in ('spd_bn_dummy.png', 'spd_bn_top_00003.png', 'spd_20170411_bn_list_ffbe_last.png', 'spd_20190831_DQXI_S_charabattle.png'))
            if not selected:
                continue
            offset = start + row['FileOffset']
            stored = raw[offset:offset + row['FileSize']]
            payload = decoded_member(stored, row, path.stem)
            image = inspect_member(member, payload)
            if member in PRIMARY_ROTO:
                output = SOURCES / 'Roto/original-art' / (PRIMARY_ROTO[member] + '-official-original.png')
                if not output.is_file() or output.read_bytes() != payload:
                    raise ValueError('Accepted original Roto image differs from the original native member.')
                reused = True
            else:
                output = SOURCES / ('Roto/original-art' if 'roto' in member.lower() else 'original-art') / member
                if output.exists() and output.read_bytes() != payload:
                    raise ValueError('Another original version already owns this output: ' + str(output))
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_bytes(payload)
                reused = False
            assets.append({'filename': member, 'original_file': relative(output), 'sha256': sha(payload),
                           'package': relative(path), 'package_sha256': sha(raw),
                           'stored_sha256': sha(stored), 'native_user_string': row.get('UserString'),
                           'original_member_id': row.get('ID'), 'source_image': image,
                           'existing_original_reused': reused,
                           'reviewed_event_area_ids': [aid for aid, filename in EVENT_CARDS.items() if filename == member],
                           'native_icon_rows': [r for r in tables['F_ICON_MST'] if r['qtkvrS60'] == member],
                           'native_home_banner_rows': [r for r in home_rows if r['6Dgaqir0'] == member],
                           'binding_status': 'Native icon or visually reviewed original title binding' if member in EVENT_CARDS.values() else 'Original related campaign image; no active event binding inferred'})
    recovered = {r['filename'] for r in assets}
    events = []
    for area in areas:
        dungeon = next(r for r in dungeons if r['uv60hgDW'] == area['uv60hgDW'])
        refs = []
        for kind, row in (('area', area), ('dungeon', dungeon)):
            icon = icons.get(row.get('0HUPxDf1'))
            refs.append({'owner_type': kind, 'icon_id': row.get('0HUPxDf1'), 'icon': icon,
                         'asset_recovered': bool(icon and icon['qtkvrS60'] in recovered),
                         'limit': 'Generic/stale icon references are source evidence, not an authorization to use unrelated artwork.'})
        events.append({'area_id': area['uv60hgDW'], 'dungeon_id': dungeon['U9iHsau3'],
                       'native_jp_name': area['G4L0YIB2'], 'native_icon_refs': refs,
                       'active_primary_filename': EVENT_CARDS.get(area['uv60hgDW']),
                       'active_primary_status': 'ORIGINAL_IMAGE_RECOVERED' if EVENT_CARDS.get(area['uv60hgDW']) in recovered else 'EXACT_ORIGINAL_IMAGE_NOT_FOUND_IN_INSPECTED_PACKS',
                       'japanese_title_copy': area['G4L0YIB2'],
                       'home_banner_records': [r for r in home_rows if r['1X65WPLU'].split(',')[2] == area['uv60hgDW']]})
    report = {'schema': 1, 'status': 'Exact original source images only; no English image edits or runtime activation',
              'sources': table_receipts, 'packages': pack_receipts, 'assets': assets,
              'events': events, 'event_sets': len(events), 'recovered_images': len(assets),
              'accepted_originals_reused': sum(r['existing_original_reused'] for r in assets),
              'active_primary_cards_recovered': sum(EVENT_CARDS.get(a['uv60hgDW']) in recovered for a in areas),
              'related_unmapped_world_of_visions_card': {'filename': 'spd_20240219_bn_list_roto.png',
                  'japanese_title': 'ロトの紋章の導き', 'event_scope': 'Known earlier inventory topic with native stage IDs still unresolved; not a substitute for Gorgona6217.'},
              'missing_explicit_native_filenames': sorted(exact_filenames - recovered - {'spd_bn_dummy.png', 'spd_bn_top_00003.png', 'spd_20170411_bn_list_ffbe_last.png', 'spd_20190831_DQXI_S_charabattle.png'}),
              'summon_master_search': {'native_F_GACHA_MST_literal_present': False,
                  'native_F_GACHA_MST_file_getter_found': any(r['table'] == 'F_GACHA_MST' for r in manifest.values()),
                  'related_verified_tables': [r['table'] for r in manifest.values() if 'GACHA' in r['table']],
                  'conclusion': 'No original persistent F_GACHA_MST file identity was demonstrated in the original native manifest or the 215 acquired archive master candidates. F_BANNER_MST supplies historical UI labels and target IDs; those are not original summon pools, costs or rates.'}}
    (SOURCES / 'original-event-art.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k: report[k] for k in ('event_sets', 'recovered_images', 'accepted_originals_reused', 'missing_explicit_native_filenames')}))


if __name__ == '__main__':
    main()
