"""Native master, map-page and normal-flow checks for two authored quest chains."""
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import sys
import unittest

from cpk import Cpk
from decode_client_data import client_manifest, decode
from native_master_index import paired_index
from repair_quest_chains import ROOT, CONTENT, build, encode_events, sid

spec = importlib.util.spec_from_file_location('quest_native_pages', ROOT / 'source/build/inspect-map-chests-20261027.py')
native = importlib.util.module_from_spec(spec)
previous = sys.argv
try:
    sys.argv = ['native-pages']
    spec.loader.exec_module(native)
finally:
    sys.argv = previous


def parse_map(data, base):
    r = native.Reader(data)
    size, version = r.integer(), r.integer()
    assert size == len(data)
    r.take(12 if version >= 1009 else 0)
    r.take(4 if version >= 1022 else 0)
    if base:
        r.integer()
    for _ in range(r.integer()):
        r.short(); r.string()
    if base and version > 1014:
        r.take(4 * r.short())
    maps = {}
    for _ in range(r.short()):
        start = r.pos
        length, mapid = r.integer(), r.short()
        entry = {'events': [], 'plane': None}
        if base:
            r.integer()
            width, height = r.short(), r.short()
            r.byte()
            cells = width * height
            for _ in range(4):
                if r.byte():
                    r.take(cells * 4)
            if version >= 1033:
                r.take(cells * 4)
            entry.update(width=width, height=height, collision=r.take(cells))
            if version >= 1015:
                entry['plane'] = r.take(cells)
            if version >= 1019:
                r.take(9 * r.integer())
                if version >= 1040:
                    r.take(9 * r.integer())
            for _ in range(r.short()):
                r.take(12)
                hit, display = r.byte(), r.byte()
                if display:
                    r.take(13)
                if hit:
                    r.take(8)
        elif version >= 1015:
            entry['plane'] = r.take(r.integer() * r.integer())
        for _ in range(r.short()):
            event_start = r.pos
            ident = r.integer() if version >= 1024 else r.short()
            kind = r.byte()
            xy = [r.integer(), r.integer()]
            r.take(14 + 2 * (version >= 1046))
            pages = []
            for _ in range(r.byte()):
                conditions, commands = native.page(r, kind, version)
                pages.append({'conditions': [list(c) for c in conditions], 'commands': [
                    {'op': op, 'payload_hex': payload.hex()} for op, payload, _ in commands]})
            entry['events'].append({'id': ident, 'kind': kind, 'xy': xy, 'pages': pages,
                                    'raw': data[event_start:r.pos]})
        assert r.pos == start + length, (mapid, r.pos, start + length)
        maps[mapid] = entry
    assert r.pos == len(data)
    return version, maps


def active_page(event, flags):
    # MapEventData::checkPage1fc55b8 keeps the last active page.
    matches = [p for p in event['pages'] if all(flags.get(flag, 0) == value for flag, value in p['conditions'])]
    return matches[-1] if matches else None


class QuestChainRepairs(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.content = json.loads(CONTENT.read_text(encoding='utf8'))
        cls.manifest = {r['table']: r for r in client_manifest(ROOT / 'repository snapshots/FFBE-Global-v9.0.0-original.apk').values()}

    def interactions(self, location, flags):
        out = []
        for pack, binding in zip(self.content['packs'], self.content['tables']['F_MAP_EXT_RESOURCE_MST']['rows']):
            if (binding['Lxj5u3WB'], binding['6uIYE15X']) != location:
                continue
            if not flags.get(int(binding['a3u6d1re']), 0) or flags.get(int(binding['ECcDwp14']), 0):
                continue
            for events in pack['maps'].values():
                for event in events:
                    p = active_page(event, flags)
                    if event['kind'] == 0 and p:
                        out.append((event, p))
        return out

    def operation(self, location, flags, op):
        return [(e['id'], struct.unpack('>ii', bytes.fromhex(c['payload_hex'])))
                for e, p in self.interactions(location, flags) for c in p['commands'] if c['op'] == op]

    def test_native_pages_only_offer_the_five_steps_in_their_real_locations_and_phases(self):
        town, shrine, factory, worker = ('2', '3101'), ('1', '1320906'), ('2', '12104'), ('2', '12103')
        flags = {}
        self.assertEqual(self.interactions(town, flags), [])
        flags.update({10077600: 1, 10063003: 1, 10063008: 1})
        self.assertEqual(self.operation(town, flags, 74), [(31000, (1014006, 101400601))])
        self.assertEqual(self.operation(shrine, flags, 75), [])
        self.assertEqual(self.operation(town, flags, 75), [])
        flags[sid('ring_accept')] = 1
        self.assertEqual(self.operation(shrine, flags, 75), [(31020, (1014006, 101400601))])
        self.assertEqual(self.operation(('1', '1320905'), flags, 75), [])
        flags[sid('ring_step1')] = flags[sid('ring_found')] = 1
        self.assertEqual(self.operation(shrine, flags, 75), [])
        self.assertEqual(self.operation(town, flags, 75), [(31010, (1014006, 101400602))])
        flags[sid('ring_done')] = 1
        self.assertEqual(self.interactions(town, flags), [])
        self.assertEqual(self.interactions(factory, flags), [])
        flags[10190400] = 1
        self.assertEqual(self.operation(factory, flags, 74), [(31030, (1029003, 102900301))])
        self.assertEqual(self.operation(worker, flags, 75), [])
        flags[sid('filter_accept')] = 1
        self.assertEqual(self.operation(worker, flags, 75), [(31040, (1029003, 102900301))])
        self.assertEqual(self.operation(factory, flags, 75), [])
        flags[sid('filter_step1')] = flags[sid('worker_met')] = 1
        self.assertEqual(self.operation(worker, flags, 75), [(31040, (1029003, 102900302))])
        flags[sid('filter_ready')] = 1
        self.assertEqual(self.operation(worker, flags, 75), [])
        self.assertEqual(self.operation(factory, flags, 75), [(31030, (1029003, 102900303))])
        flags[sid('filter_done')] = 1
        self.assertEqual(self.interactions(factory, flags), [])
        self.assertEqual(self.interactions(worker, flags), [])

    def test_native_ciphertext_and_paired_indexes_preserve_all_original_rows(self):
        from player_state import _load_ndjson
        for table, added in self.content['tables'].items():
            info = self.manifest[table]
            source = next((ROOT / 'data/client/files').rglob('Ver*_' + info['token'] + '.dat'))
            target = ROOT / 'data/overlay' / source.relative_to(ROOT / 'data/client/files')
            raw = target.read_bytes()
            self.assertTrue(raw.startswith(source.read_bytes()))
            originals = decode(source.read_bytes(), info['key'])[1]
            rows = decode(raw, info['key'])[1]
            self.assertEqual(rows, originals + added['rows'])
            restored = _load_ndjson(table + '.ndjson', added['key'])
            actual = list(restored.values()) if added['key'] else restored['__rows__']
            self.assertEqual(len(actual), len(originals) + len(added['rows']))
            for original in originals:
                if added['key']:
                    self.assertEqual(restored[original[added['key']]], original)
            if table in ('F_QUEST_SUB_MST', 'F_RESOURCE_MAP_MST'):
                path, expected = paired_index(table, target, raw, info['key'])
                self.assertEqual(path.read_bytes(), expected)

    def test_each_native_pack_roundtrips_without_any_encounter_plane(self):
        for pack in self.content['packs']:
            relative = 'common_lang/sd/' + pack['folder'] + '/Ver1_' + pack['stem'] + '.cpk'
            cpk = Cpk((ROOT / 'data/overlay' / relative).read_bytes())
            raw = cpk.read(pack['stem'] + '_event.bin')
            self.assertEqual(raw, encode_events(pack['maps']))
            version, maps = parse_map(raw, False)
            self.assertEqual(version, 1014)
            for mapid, row in maps.items():
                self.assertIsNone(row['plane'])
                planned = pack['maps'][str(mapid)]
                self.assertEqual([e['id'] for e in row['events']], [e['id'] for e in planned])
                for actual, expected in zip(row['events'], planned):
                    for a, e in zip(actual['pages'], expected['pages']):
                        self.assertEqual(a['conditions'], e['conditions'])
                        self.assertEqual(a['commands'], e['commands'])
            for text in pack['dialogue'].values():
                self.assertNotIn('\u2014', text)
            for key, text in pack['dialogue'].items():
                self.assertIn((str(key) + '^' + text + '^').encode(), cpk.read(pack['stem'] + '_event_text_sg.txt'))

    def test_append_only_flags_and_original_floor_points_are_preserved(self):
        from repair_quest_chains import original
        from player_state import switch_position
        added = self.content['tables']['F_SWITCH_MST']['rows']
        old = original('F_SWITCH_MST')
        self.assertFalse({r['8vAYn3IX'] for r in old} & {r['8vAYn3IX'] for r in added})
        for row in old + added:
            self.assertEqual(switch_position(row['8vAYn3IX']), (row['5opcUT9t'], int(row['QLfe23bu'])))
        maps = {}
        for town, filename in [('3101', '131020100.cpk'), ('12103', '550220300.cpk'), ('12104', '550220400.cpk')]:
            raw = Cpk((ROOT / 'Japan content/Shared sources/jp_andapp' / filename).read_bytes()).read('map.bin')
            maps[town] = parse_map(raw, True)[1]
        for step in self.content['tables']['F_QUEST_SUB_MST']['rows']:
            if not step['71BDvsNw']:
                continue
            typ, town, mapid, x, y = step['71BDvsNw'].split(':')
            row = maps[town][int(mapid)]
            self.assertEqual(row['collision'][int(y) * row['width'] + int(x)], 0)
        for pack in self.content['packs']:
            if pack['resource_id'] == 331209201:
                continue
            town = {331201206: '3101', 602203203: '12104', 602202203: '12103'}[pack['resource_id']]
            for mid, events in pack['maps'].items():
                old_ids = {e['id'] for e in maps[town][int(mid)]['events']}
                self.assertFalse(old_ids & {e['id'] for e in events})
        # Native updateEvent1fac6a8 updates base then appended entries; each
        # ready appended interaction replaces activeEvent at1fac6e4. Old NPC
        # dialogue survives outside the appended page's own conditions.
        manager = self.content['packs'][2]['maps']['10'][0]
        self.assertIsNone(active_page(manager, {}))
        self.assertIsNotNone(active_page(manager, {10190400: 1}))

    def test_overlay_whitelist_and_native_quest_title_include_all_thirteen_artifacts(self):
        from player_state import map_ext_unservable_ignores
        files = self.content['native_overlay']['files']
        self.assertEqual(len(files), 13)
        for file in files:
            path = ROOT / 'data/overlay' / file['path']
            self.assertTrue(path.resolve().is_relative_to((ROOT / 'data/overlay').resolve()))
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), file['sha256'])
        self.assertEqual(self.content['tables'], build()['tables'])
        info = self.manifest['F_TEXT_QUEST']
        source = next((ROOT / 'data/client/files').rglob('Ver*_' + info['token'] + '.dat'))
        target = ROOT / 'data/overlay' / source.relative_to(ROOT / 'data/client/files')
        self.assertTrue(target.read_bytes().startswith(source.read_bytes()))
        rows = decode(target.read_bytes(), info['key'], localized=True)[1]
        title = next(row for row in rows if row['key'] == 'MST_QUEST_NAME_1014006')
        self.assertEqual(title['v'], ['Inherited Memories', 'Inherited Memories'])
        ignored = map_ext_unservable_ignores(lambda relative:
            any((ROOT / folder / relative).is_file() for folder in ('data/overlay', 'data/client/files')))
        self.assertNotIn(str(sid('ring_done')), ignored)
        self.assertNotIn(str(sid('filter_done')), ignored)


if __name__ == '__main__':
    unittest.main()
