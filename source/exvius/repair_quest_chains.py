"""Reconstruct two localized but unpreserved map quests through native data.

Original objective text and NPC identities survive. Quest definitions, scripts,
placements, flags and 1000 gil rewards below are explicitly authored restoration.
The version 1014 append format adds events without overwriting encounter planes.
"""
from copy import deepcopy
import argparse
import hashlib
import json
from pathlib import Path
import struct

ROOT = Path(__file__).resolve().parents[2]
CONTENT = ROOT / 'source/server/content/quest_chain_repairs.json'
SWITCHES = {
    'ring_accept': (20063051, 200, 1221), 'ring_done': (20063052, 201, 526),
    'ring_found': (20063053, 200, 1222), 'ring_step1': (20063054, 200, 1223),
    'ring_given': (20063055, 200, 1224),
    'filter_accept': (20340021, 200, 1225), 'filter_done': (20340022, 201, 527),
    'worker_met': (20340023, 200, 1226), 'filter_step1': (20340024, 200, 1227),
    'filter_ready': (20340025, 200, 1228), 'filter_given': (20340026, 200, 1229),
}
KEYS = {'F_QUEST_MST': 'Z34jU7ue', 'F_QUEST_SUB_MST': '7Svg2kdT',
        'F_SWITCH_MST': '8vAYn3IX', 'F_RESOURCE_MAP_MST': 'Nnb20keZ',
        'F_RESOURCE_MAP_VERSION_MST_LOCALIZE': 'Nnb20keZ', 'F_MAP_EXT_RESOURCE_MST': None}


def original(table):
    return [json.loads(line) for line in (ROOT / 'data/mst_decoded' / (table + '.ndjson'))
            .read_text(encoding='utf8').splitlines()]


def localized(table, key):
    rows = map(json.loads, (ROOT / 'data/text_decoded' / (table + '.ndjson')).read_text(encoding='utf8').splitlines())
    return next(row['v'][0] for row in rows if row['key'] == key)


def sid(name):
    return SWITCHES[name][0]


def conditions(**values):
    return [[sid(name), value] for name, value in values.items()]


def command(op, *values):
    return {'op': op, 'payload_hex': b''.join(struct.pack('>i', value) for value in values).hex()}


def switch(name):
    return {'op': 10, 'payload_hex': (struct.pack('>i', sid(name)) + b'\1').hex()}


def dialogue(text_id):
    return command(8, text_id)


def wait():
    return command(1)


def page(terms, commands, npc=None):
    return {'conditions': terms, 'commands': commands, 'npc': npc}


def event(ident, kind, xy, pages):
    return {'id': ident, 'kind': kind, 'xy': xy, 'pages': pages}


def face(npc_event):
    return {'op': 11, 'payload_hex': (b'\1' + struct.pack('>i', npc_event) + b'\10').hex()}


def completion(qid, step, reminder, success, before=(), final=False, npc_event=None):
    # Clone the original op38/branch/op75 arrangement, including its waiting
    # points. The goal check gates payment and completion in the native scene.
    out = ([face(npc_event), wait()] if npc_event else [])
    for action in before:
        out += [action, wait()]
    out += [{'op': 38, 'payload_hex': (b'\0' + struct.pack('>ii', qid, step) + b'\1').hex()}, wait(),
            dialogue(reminder), wait(), {'op': 4, 'payload_hex': '0001'}, wait(),
            dialogue(success), wait(), command(75, qid, step), wait()]
    if final:
        out += [command(101), wait()]
    return out


def actor_events(ident, npc, xy, actor_terms, interactions, accept_marker=None, finish_marker=None):
    x, y = xy
    result = [event(ident, 0, [x + 23, y + 52], interactions),
              event(ident + 1, 1, xy, [page(actor_terms, [], npc)])]
    if finish_marker is not None:
        result.append(event(ident + 2, 28, [x + 23, y - 64], [page(finish_marker, [])]))
    if accept_marker is not None:
        result.append(event(ident + 3, 29, [x + 23, y - 64], [page(accept_marker, [])]))
    return result


def acceptance(qid, step, start, text, actor):
    return [face(actor + 1), wait(), dialogue(text), wait(), switch(start), wait(),
            command(74, qid, step), wait(),
            {'op': 42, 'payload_hex': (struct.pack('>i', actor + 3) + b'\0').hex()}, wait(), command(94), wait()]


def build():
    quest_template = next(r for r in original('F_QUEST_MST') if r['Z34jU7ue'] == '1014004')
    step_template = next(r for r in original('F_QUEST_SUB_MST') if r['7Svg2kdT'] == '101400401')
    version_template = original('F_RESOURCE_MAP_VERSION_MST_LOCALIZE')[0]
    tables = {name: {'key': key, 'rows': []} for name, key in KEYS.items()}
    for qid, npc, town, gate, prefix in [(1014006, 1210060, 3101, 10077600, 'ring'),
                                       (1029003, 1520012, 12104, 10190400, 'filter')]:
        row = deepcopy(quest_template)
        name = (localized('F_TEXT_QUEST_SUB_NAME', 'MST_QUESTSUB_NAME_101400601') if qid == 1014006
                else localized('F_TEXT_QUEST', 'MST_QUEST_NAME_' + str(qid)))
        row.update({'Z34jU7ue': str(qid), 'G4L0YIB2': name, 'Z0EN6jSh': str(qid),
                    'Qvb5N1WT': str(npc), '6uIYE15X': str(town), 'juA0Z4m7': str(gate),
                    'dX6cor8j': '30:0:1000:100:1',
                    'dIPkNn61': ','.join(str(value[0]) for key, value in SWITCHES.items()
                                         if key.startswith(prefix + '_') or prefix == 'filter' and key == 'worker_met')})
        tables['F_QUEST_MST']['rows'].append(row)
    specs = [(101400601, 2, 1320906, 'ring_accept', 'ring_step1', 'ring_found', ''),
             (101400602, 1, 100002800, 'ring_step1', 'ring_done', 'ring_given', '2:3101:19:13:18'),
             (102900301, 1, 1520013, 'filter_accept', 'filter_step1', 'worker_met', '2:12103:1:2:10'),
             (102900302, 1, 1520013, 'filter_step1', 'filter_ready', None, '2:12103:1:2:10'),
             (102900303, 1, 1520012, 'filter_ready', 'filter_done', 'filter_given', '2:12104:10:9:19')]
    for subid, resource_type, resource_id, prerequisite, opened, target, teleport in specs:
        row = deepcopy(step_template)
        row.update({'7Svg2kdT': str(subid), 'Z34jU7ue': str(subid // 100),
                    'G4L0YIB2': localized('F_TEXT_QUEST_SUB_NAME', 'MST_QUESTSUB_NAME_' + str(subid)),
                    '42ZNoa7B': localized('F_TEXT_QUEST_SUB_STORY', 'MST_QUESTSUB_STORY_' + str(subid)),
                    '7EuJK9ZL': localized('F_TEXT_QUEST_SUB_DETAIL', 'MST_QUESTSUB_GOAL_DETAIL_' + str(subid)),
                    'Z0EN6jSh': str(subid % 100), 'dX0SkK3j': str(resource_type),
                    '9ZCEWn0z': str(resource_id), 'juA0Z4m7': str(sid(prerequisite)),
                    'dIPkNn61': str(sid(opened)), '71BDvsNw': teleport,
                    '89EvGKHx': '4' if target else '1', 'siLGXq94': '3' if target else '1',
                    '25oxcKwN': str(sid(target)) if target else '20:104004100:8:100'})
        tables['F_QUEST_SUB_MST']['rows'].append(row)
    for value, typ, index in SWITCHES.values():
        tables['F_SWITCH_MST']['rows'].append({'8vAYn3IX': str(value), '5opcUT9t': str(typ), 'QLfe23bu': str(index)})
    packs = []
    locations = [(331201206, 'event/sub31', '131010416', 2, 3101, 10077600, 'ring_done'),
                 (331209201, 'event/sub32', '132010916', 1, 1320906, sid('ring_accept'), 'ring_done'),
                 (602203203, 'event2/sub02', '550220413', 2, 12104, 10190400, 'filter_done'),
                 (602202203, 'event2/sub02', '550220313', 2, 12103, sid('filter_accept'), 'filter_done')]
    for resource_id, folder, stem, location_type, location, gate, end in locations:
        tables['F_RESOURCE_MAP_MST']['rows'].append({'Nnb20keZ': str(resource_id), 'dX0SkK3j': '300',
            '3LHdc6Qa': folder, 'drE35YcF': 'event', 'pJ56sAEo': stem + '.cpk', '6uvHX2JG': ''})
        version = deepcopy(version_template)
        version.update({'Nnb20keZ': str(resource_id), 'OzT5lSz3': '1', '950Qpfly': '1'})
        tables['F_RESOURCE_MAP_VERSION_MST_LOCALIZE']['rows'].append(version)
        tables['F_MAP_EXT_RESOURCE_MST']['rows'].append({'Lxj5u3WB': str(location_type),
            '6uIYE15X': str(location), 'a3u6d1re': str(gate), 'ECcDwp14': str(sid(end)), 'Y4PER0gB': str(resource_id)})
        packs.append({'resource_id': resource_id, 'folder': folder, 'stem': stem, 'maps': {}, 'dialogue': {}})
    ring, shrine, factory, worker = packs
    ring_terms = [[10077600, 1], [10063003, 1]] + conditions(ring_done=0)
    ring['maps'][19] = actor_events(31000, 1210060, [267, 992], ring_terms,
        [page(ring_terms + conditions(ring_accept=1), [face(31001), wait(), dialogue(91014062), wait()]),
         page(ring_terms + conditions(ring_accept=0), acceptance(1014006, 101400601, 'ring_accept', 91014061, 31000))],
        accept_marker=ring_terms + conditions(ring_accept=0))
    handover = [[10077600, 1], [10063008, 1]] + conditions(ring_step1=1, ring_done=0)
    ring['maps'][19] += actor_events(31010, 100002800, [731, 1050], handover,
        [page(handover, completion(1014006, 101400602, 91014065, 91014066,
                                  before=[switch('ring_given')], final=True, npc_event=31011))],
        finish_marker=handover)
    ring['dialogue'] = {91014061: "<name_npc=1210060><br>Elle left a ring near the Water Shrine. Please find it and take it to Arsha.<keywait>",
        91014062: "<name_npc=1210060><br>Look near the Water Shrine's entrance. Arsha should have the ring Elle left behind.<keywait>",
        91014065: '<name_npc=100002800><br>Have you found the ring Elle left behind?<keywait>',
        91014066: '<name_npc=100002800><br>This is Elle\'s ring. Thank you for bringing it to me.<keywait>'}
    pickup = conditions(ring_accept=1, ring_step1=0, ring_done=0)
    shrine['maps'][1] = [event(31020, 0, [1276, 1392], [page(pickup,
        completion(1014006, 101400601, 91014063, 91014064, before=[switch('ring_found')]))])]
    shrine['dialogue'] = {91014063: 'Search the Water Shrine for the ring Elle left behind.<keywait>',
        91014064: 'You found Elle\'s ring. Take it to Arsha in Olderion.<keywait>'}
    manager_terms = [[10190400, 1]] + conditions(filter_done=0)
    factory['maps'][10] = actor_events(31030, 1520012, [499, 992], manager_terms,
        [page(manager_terms + conditions(filter_accept=1), [face(31031), wait(), dialogue(91029032), wait()]),
         page(manager_terms + conditions(filter_ready=1), completion(1029003, 102900303, 91029033, 91029034,
              before=[switch('filter_given')], final=True, npc_event=31031)),
         page(manager_terms + conditions(filter_accept=0), acceptance(1029003, 102900301, 'filter_accept', 91029031, 31030))],
        accept_marker=manager_terms + conditions(filter_accept=0),
        finish_marker=manager_terms + conditions(filter_ready=1))
    factory['dialogue'] = {91029031: '<name_npc=1520012><br>I need an efficient filter. Please find the skilled worker in Luzell Colony.<keywait>',
        91029032: '<name_npc=1520012><br>Ask the skilled worker in Luzell Colony to make an efficient filter.<keywait>',
        91029033: '<name_npc=1520012><br>Have you brought the efficient filter?<keywait>',
        91029034: '<name_npc=1520012><br>This filter is just what the factory needs. Thank you for your help.<keywait>'}
    worker_terms = conditions(filter_accept=1, filter_done=0)
    worker['maps'][1] = actor_events(31040, 1520013, [93, 470], worker_terms,
        [page(worker_terms + conditions(filter_step1=0), completion(1029003, 102900301, 91029035, 91029036,
              before=[switch('worker_met')], npc_event=31041)),
         page(worker_terms + conditions(filter_step1=1, filter_ready=0), completion(1029003, 102900302,
              91029037, 91029038, npc_event=31041)),
         page(worker_terms + conditions(filter_ready=1), [face(31041), wait(), dialogue(91029039), wait()])],
        finish_marker=worker_terms + conditions(filter_ready=0))
    worker['dialogue'] = {91029035: '<name_npc=1520013><br>Are you looking for someone who can make an efficient filter?<keywait>',
        91029036: '<name_npc=1520013><br>I can make that filter. Bring me eight giant feathers.<keywait>',
        91029037: '<name_npc=1520013><br>I need eight giant feathers to make the filter.<keywait>',
        91029038: '<name_npc=1520013><br>These feathers will do. Here is the efficient filter. Take it to the factory manager in Dormdry.<keywait>',
        91029039: '<name_npc=1520013><br>Deliver the efficient filter to the factory manager in Dormdry.<keywait>'}
    return {'status': 'authored reconstruction', 'tables': tables, 'packs': packs,
            'localized_text': {'F_TEXT_QUEST': {'MST_QUEST_NAME_1014006':
                localized('F_TEXT_QUEST_SUB_NAME', 'MST_QUESTSUB_NAME_101400601')}},
            'provenance': {'objectives': 'Exact retained English F_TEXT_QUEST_SUB_NAME/STORY/DETAIL records.',
                'roles': 'Original F_NPC_MST and English F_TEXT_NPC_NAME.',
                'scripts': 'Original GL op38/74/75, NPC plus interaction plus marker arrangement from 131010411 and 131010414.',
                'rewards': '1000 gil per chain is authored, not recovered retail reward. Original quest 1003009 supplies the 30:0:1000:100:1 contract.',
                'placement': 'Nichol uses the vacated early Arsha floor position after flags 10077600 and 10063003. Arsha uses her original poststory position. Manager/worker use original generic NPC positions with identical models. Ring uses the Water Shrine header entry tile (22,24), map 1.',
                'navigation': 'Town goals use adjacent native 58px-grid tiles with original collision byte 0: Arsha (13,18) above foot (13,19); worker (2,10) below foot (2,9); manager (9,19) below foot (9,18). Ring mission navigation stays empty because its world-area destination was not recovered.',
                'switches': 'New IDs are absent in GL and JP. New bit positions follow JP maxima 1220/525, preserving all previous mappings.',
                'append_format': 'Original loadAppendData at 0x1fabcec skips plane writing below version 1015. Version 1014 uses short event IDs and no encounter plane.',
                'dialogue': 'All added speech is authored from preserved objectives, not recovered original dialogue.'}}


def encode_page(value, kind):
    # Original131010411 NPC image parameters, with post1034 extra byte absent.
    image = (b'\1' + struct.pack('>i', value['npc']) + bytes.fromhex('0000000001041400020100')
             if value.get('npc') is not None else b'\0')
    flags = bytes.fromhex('01000000' if kind == 1 else '01070000' if kind == 0 else '00000000')
    cond = bytes([len(value['conditions'])]) + b''.join(struct.pack('>iB', *c) for c in value['conditions'])
    script = b''.join(struct.pack('>Bh', c['op'], len(bytes.fromhex(c['payload_hex']))) + bytes.fromhex(c['payload_hex'])
                      for c in value['commands'])
    return image + flags + cond + b'\0' + struct.pack('>i', len(script)) + script


def encode_events(maps):
    out = bytearray(struct.pack('>6ih', 0, 1014, 0, 0, 0, 0, len(maps)))
    for mapid, events in maps.items():
        body = bytearray(struct.pack('>hh', int(mapid), len(events)))
        for e in events:
            header = ('003a003a00170034003a003a00ba' if e['kind'] == 1 else
                      '003a003a00000000003a003a0064' if e['kind'] == 0 else '003a003a00000000000000000064')
            body += struct.pack('>hBii', e['id'], e['kind'], *e['xy']) + bytes.fromhex(header) + bytes([len(e['pages'])])
            body += b''.join(encode_page(p, e['kind']) for p in e['pages'])
        out += struct.pack('>i', len(body) + 4) + body
    struct.pack_into('>i', out, 0, len(out))
    return bytes(out)


def pack_bytes(pack):
    from cricodecs import cpk
    result = cpk.create(cpk.CpkPreset.FILENAME, 2048)
    stem = pack['stem'] + '_event'
    result.add_bytes(encode_events(pack['maps']), stem + '.bin')
    result.add_bytes(b'', stem + '_teller.txt')
    result.add_bytes(b'', stem + '_teller_sg.txt')
    result.add_bytes(''.join(f'{key},{text}\r\n' for key, text in pack['dialogue'].items()).encode('utf8'), stem + '_text.txt')
    result.add_bytes(''.join(str(key) + '^' + '^'.join([text] * 8) + '\r\n' for key, text in pack['dialogue'].items()).encode('utf8'),
                     stem + '_text_sg.txt')
    return result.save_bytes()


def write_draft(target):
    target.mkdir(parents=True, exist_ok=True)
    value = build()
    for pack in value['packs']:
        raw = pack_bytes(pack)
        (target / (pack['stem'] + '.cpk')).write_bytes(raw)
        pack['sha256'] = hashlib.sha256(raw).hexdigest()
    (target / 'quest_chain_repairs.json').write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    print('Prepared two quest chains, five steps and four native event packs in', target)


def write_runtime():
    from decode_client_data import client_manifest, decode
    from native_master_index import build_index
    from prepare_offline_cache import exbonus_master, loading_text
    value = build()
    manifest = client_manifest(ROOT / 'repository snapshots/FFBE-Global-v9.0.0-original.apk')
    manifest = {row['table']: row for row in manifest.values()}
    # Check both preserved families, not just a guessed ID gap. Appended bitmap
    # positions deliberately follow the newer JP maximum as well as Global.
    for table, source in [('F_SWITCH_MST', 'Ver1511_T46RpNZH.dat'),
                          ('F_RESOURCE_MAP_MST', 'Ver765_B7LnP2TH.dat')]:
        info = manifest[table]
        _, jp = decode((ROOT / 'Japan content/Shared sources/jp_andapp' / source).read_bytes(), info['key'])
        identity = value['tables'][table]['key']
        added = value['tables'][table]['rows']
        existing = original(table) + jp
        assert not {r[identity] for r in existing} & {r[identity] for r in added}, table
        if table == 'F_SWITCH_MST':
            assert not {(r['5opcUT9t'], r['QLfe23bu']) for r in existing} & {
                (r['5opcUT9t'], r['QLfe23bu']) for r in added}
    selected = []
    for table, restored in value['tables'].items():
        info = manifest[table]
        sources = list((ROOT / 'data/client/files').rglob('Ver*_' + info['token'] + '.dat'))
        assert len(sources) == 1, table
        source = sources[0]
        relative = source.relative_to(ROOT / 'data/client/files')
        target = ROOT / 'data/overlay' / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if table in ('F_QUEST_SUB_MST', 'F_RESOURCE_MAP_MST'):
            version = int(source.name.split('_')[0][3:])
            assert build_index(table, source.read_bytes(), info['key'], version) == source.with_name(info['token'] + '.i').read_bytes()
        exbonus_master(source, target, info['key'], table, restored)
        selected.append(target)
        if table in ('F_QUEST_SUB_MST', 'F_RESOURCE_MAP_MST'):
            selected.append(target.with_name(info['token'] + '.i'))
    for pack in value['packs']:
        relative = Path('common_lang/sd') / pack['folder'] / ('Ver1_' + pack['stem'] + '.cpk')
        target = ROOT / 'data/overlay' / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(pack_bytes(pack))
        selected.append(target)
    for table, texts in value['localized_text'].items():
        info = manifest[table]
        sources = list((ROOT / 'data/client/files').rglob('Ver*_' + info['token'] + '.dat'))
        assert len(sources) == 1, table
        source = sources[0]
        target = ROOT / 'data/overlay' / source.relative_to(ROOT / 'data/client/files')
        target.parent.mkdir(parents=True, exist_ok=True)
        loading_text(source, target, info['key'], texts, append_missing=True)
        selected.append(target)
    value['native_overlay'] = {'files': [
        {'path': p.relative_to(ROOT / 'data/overlay').as_posix(),
         'sha256': hashlib.sha256(p.read_bytes()).hexdigest()} for p in selected]}
    CONTENT.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    print('Restored two quest chains, five steps, eleven append-only flags and', len(selected), 'native overlay files.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--draft', type=Path, default=ROOT / 'build/scratch/ffbe-quest-repairs/draft')
    parser.add_argument('--apply', action='store_true', help='Write approved runtime content and exact-version overlays.')
    args = parser.parse_args()
    write_runtime() if args.apply else write_draft(args.draft)
