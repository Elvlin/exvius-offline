"""Fill Global content packages that the saved Global cache lacks from the Memorial download.

The Global client asks for `common_lang/sd/<dir>/Ver<v>_<file>` as listed in its own
F_RESOURCE_MST / F_RESOURCE_MAP_MST and their version tables. The saved Global cache only
holds what the original player downloaded. Memorial packages carry the same members, except
that every Global text table `X.txt` (`<id>_event_text`, `<id>_event_teller`, `map_text`,
`map_teller`, `common_teller`) has a localized companion `X_sg.txt` the Global client reads
(`id^EN^ZH^KO^FR^DE^ES^TH^ID`); without it the client shows raw MAP_TEXT/MAP_TELLER keys.
Memorial keeps the English in `X.txt` (`id,text`), so the companions are generated from it.
Memorial story scenes set in a town also name town speakers (`<name=2000xx>`) that only the
town's `map_teller` lists (`<scene id>` with the last two digits `00`, or without them for a
series such as event/SG/900015); they are given scene speaker ids, see add_scene_speakers.

Writes a staging folder laid out like the app's files folder, plus manifest.json. Existing
Global files are never replaced. Use push_client_cache.py --content to copy it to the phone.
"""
import argparse
import collections
import hashlib
import json
import re
import struct
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT / 'tools/vendor/python'))
DATA = PROJECT / 'data'
LANGUAGES = 8  # EN, ZH, KO, FR, DE, ES, TH, ID
# The later Global Farplane introduction is absent from the preserved files.
# Its original retail introduction uses the same Farplane map and retains the
# English story. Keep the source intact and provide the requested scene names.
LEGACY_STORY_PACKAGES = {'211020123.cpk': '211020101.cpk',
                         '211020111.cpk': '211020101.cpk'}
# The preserved Afterglow entry scene has an older, unrelated teller table.
# Its next scene supplies these same speaker ids and their original names.
SCENE_TELLER_SOURCES = {'855010101': '855010701'}
# Resource 383108101 belongs to map resource 283108 in the original Realm
# of the Dragon King mission. The entry downloads eight maps at once.
SCENE_MAP_SOURCES = {'1830301': '183010800', '1610202': '161020100',
                     '1520202': '152020100'}
# These unused retail English name cells are empty. Translate their exact
# Japanese map captions, scoped to the original map rather than a shared id.
MAP_ENGLISH_NAMES = {
    '309010100': {'200011': 'Middle Moogle', '200012': 'Right Moogle',
                  '200013': 'Left Moogle', '200014': 'Three Moogles'},
    '310010100': {'200012': 'Lotti', '200013': 'Ayaka & Lotti'},
}
# Mitra's exit script requests 100071, absent from its preserved Global table.
MAP_ENGLISH_DEFAULTS = {'111020100': {'100071': 'No'}}
# The workshop map itself was not preserved. Its introduction identifies
# Gress (210006), Milty (210015) and Theo (210018-210024). The shared 200000
# caption is used before each character introduces themselves.
SCENE_ENGLISH_NAMES = {'111040101': {'200000': '???', '200001': 'Gress',
                                    '200002': 'Milty', '200003': 'Theo'},
                       # Native F_TEXT_NPC_NAME: MST_NPC_NAME_1101050.
                       '111020115': {'1101050': 'Woman'},
                       # Sakura names Ohga in 171020116:210012. Kaede is
                       # named in 210020; 171020117:210023 identifies her
                       # companion as the other parent of their child.
                       '171020116': {'200116': 'Ohga', '200117': 'Kaede'},
                       '171020117': {'200116': 'Ohga', '200117': 'Kaede',
                                     '200118': "Kaede's Partner"},
                       # The recap retains a town-scoped actor without its map.
                       # 650010112:210001-210010 explicitly addresses Emma.
                       '650010112': {'200011': 'Emma'},
                       # Both duelists announce Mirror of Equity together at
                       # 210059. The original teller 300001 names the pair.
                       '650010126': {'200011': 'Rain & Lasswell'},
                       '650010127': {'200011': 'Rain & Lasswell'}}

_DIALOGUE_ENGLISH = None


def normalize_dialogue_commands(text):
    """Repair a missing closing bracket before another numeric game command."""
    return re.sub(r'(<(?:wait|speed|name|name_npc)=\d+)(?=<)', r'\1>', text)


def apply_english_dialogue(archive, members):
    """Apply reviewed translations only to their exact preserved source strings."""
    global _DIALOGUE_ENGLISH
    if _DIALOGUE_ENGLISH is None:
        path = PROJECT / 'source/server/content/dialogue_en.json'
        _DIALOGUE_ENGLISH = (json.loads(path.read_text(encoding='utf8'))['translations']
                             if path.is_file() else {})
    changed = 0
    for name, index in members.items():
        if not name.endswith('_sg.txt'):
            continue
        values = localized_rows(archive.file_bytes(index))
        repaired = 0
        for text_id, cells in values.items():
            if not cells:
                continue
            key = hashlib.sha256(cells[0].encode('utf8')).hexdigest()
            replacement = _DIALOGUE_ENGLISH.get(key)
            if replacement is None:
                continue
            english = replacement['english']
            if replacement['source'] != cells[0] or not english_source(english):
                raise ValueError('Invalid English translation source: ' + key)
            if re.findall(r'<[^>]+>', normalize_dialogue_commands(cells[0])) != re.findall(r'<[^>]+>', english):
                raise ValueError('Translation changed original game commands: ' + key)
            if '^' in english or '\n' in english or '\r' in english:
                raise ValueError('Translation cannot change the localized row structure: ' + key)
            cells[0] = english
            repaired += 1
        if repaired:
            archive.replace_bytes(index, ''.join('^'.join([i] + cells) + '\n'
                                                 for i, cells in values.items()).encode('utf8'))
            changed += repaired
    return changed


def translated_caption(text):
    """Resolve an exact accepted caption before building scene speaker tables."""
    global _DIALOGUE_ENGLISH
    if _DIALOGUE_ENGLISH is None:
        path = PROJECT / 'source/server/content/dialogue_en.json'
        _DIALOGUE_ENGLISH = (json.loads(path.read_text(encoding='utf8'))['translations']
                             if path.is_file() else {})
    match = _DIALOGUE_ENGLISH.get(hashlib.sha256(text.encode('utf8')).hexdigest())
    return match['english'] if match and match['source'] == text else text


def global_cpk_header(packet):
    """Use Global-compatible index flags without changing any file offsets."""
    from cricodecs import utf
    size = struct.unpack_from('<Q', packet, 8)[0]
    header = utf.Utf.load_bytes(packet[16:16 + size])
    changed = False
    if header.value(0, 'CpkMode') == 2 and header.value(0, 'EID') != 1:
        # Without EID=1, Global interprets CpkExtendId as DataL/DataH and
        # dereferences a missing table.
        header.set(0, 'EID', 1)
        changed = True
    if header.value(0, 'Sorted') != 0:
        # The writer's filename order differs from Global's CRI name search.
        # A false Sorted=1 hides valid members. Changing only this flag made
        # Mitra load its 50 text rows instead of zero in the original client.
        header.set(0, 'Sorted', 0)
        changed = True
    if not changed:
        return packet
    rebuilt = header.build()
    if len(rebuilt) != size:
        raise ValueError('Changing the CPK index flag must preserve all file offsets.')
    return packet[:16] + rebuilt


def repair_staged_indexes(folder):
    """Repair generated containers already recorded in this staging manifest."""
    from cricodecs import utf
    path = folder / 'manifest.json'
    records = json.loads(path.read_text(encoding='utf-8')) if path.is_file() else []
    changed = 0
    source_changes = {}
    for record in records:
        target = folder / record['path']
        if target.suffix != '.cpk' or not target.is_file():
            continue
        with target.open('r+b') as existing:
            prefix = existing.read(16)
            packet = prefix + existing.read(struct.unpack_from('<Q', prefix, 8)[0])
            if packet[16:20] != b'@UTF':  # untouched encrypted originals
                continue
            repaired = global_cpk_header(packet)
            if repaired == packet:
                continue
            before = hashlib.sha256(target.read_bytes()).hexdigest()
            if record.get('sha256') != before:
                raise ValueError('Staged package checksum mismatch: ' + str(target))
            existing.seek(0)
            existing.write(repaired)
        record['sha256'] = hashlib.sha256(target.read_bytes()).hexdigest()
        if target.is_relative_to(DATA):
            source_changes[target.relative_to(DATA).as_posix()] = (before, record['sha256'])
        if utf.Utf.load_bytes(repaired[16:]).value(0, 'CpkMode') == 2:
            record['global_extended_id_index'] = True
        record['global_filename_lookup_linear'] = True
        changed += 1
    if changed:
        path.write_text(json.dumps(records, indent=1), encoding='utf-8')
        refresh_staged_sources(source_changes)
    return changed


def refresh_staged_sources(changes):
    """Keep derived package provenance valid after a header-only source repair."""
    updated = 0
    for folder in ('memorial_fill', 'overlay'):
        manifest = DATA / folder / 'manifest.json'
        if not manifest.is_file():
            continue
        records = json.loads(manifest.read_text(encoding='utf8'))
        changed = False
        for record in records:
            pair = changes.get(record.get('source'))
            if not pair:
                continue
            before, after = pair
            if record.get('source_sha256') not in (before, after):
                raise ValueError('Unexpected preserved source checksum: ' + record['source'])
            if record.get('source_sha256') != after:
                record['source_sha256'] = after
                changed = True
                updated += 1
        if changed:
            manifest.write_text(json.dumps(records, indent=1), encoding='utf8')
    return updated


def rows(name):
    with open(DATA / 'mst_decoded' / name, encoding='utf-8') as fh:
        return [json.loads(line) for line in fh if line.strip()]


def wanted_files():
    """(dir, file, version) for every package the client's resource tables list."""
    for resources, versions, key in (
            ('F_RESOURCE_MST.ndjson', 'F_RESOURCE_VERSION_MST_LOCALIZE.ndjson', '9ZCEWn0z'),
            ('F_RESOURCE_MAP_MST.ndjson', 'F_RESOURCE_MAP_VERSION_MST_LOCALIZE.ndjson', 'Nnb20keZ')):
        version = {str(row[key]): str(row.get('OzT5lSz3') or '') for row in rows(versions)}
        for row in rows(resources):
            directory, name = row.get('3LHdc6Qa') or '', row.get('pJ56sAEo') or ''
            if directory and name and version.get(str(row[key])):
                yield directory, name, version[str(row[key])]


def device_dir(directory):
    """Folder under the app's files folder: CRI sound banks sit in an android subfolder."""
    if directory.split('/')[0] == 'sound':
        return f'sound/{directory.split("/", 1)[1]}/android'
    return f'sd/{directory}'


def global_names():
    present = set()
    for path in (DATA / 'client/files').rglob('*'):
        match = re.match(r'Ver\d+_(.+)$', path.name)
        if path.is_file() and match:
            present.add((path.parent.relative_to(DATA / 'client/files').as_posix(), path.name))
    return present


def memorial_index():
    index = collections.defaultdict(list)
    for root in ('memorial', 'jp_andapp'):
        for path in (DATA / root).rglob('*'):
            if path.suffix in ('.cpk', '.acb', '.awb', '.usm'):
                index[re.sub(r'^Ver\d+_', '', path.name)].append(path)
    return index


def town_atlas_overrides(memorial):
    """Preserve whole original atlases for the native reader's two 32px fallbacks."""
    from cricodecs import cpk
    for source in memorial.get('111020100.cpk', []):
        archive = cpk.load(str(source))
        for index, entry in enumerate(archive.file_infos()):
            if entry.full_path not in ('mapchip_0003_001.png', 'mapchip_0003_002.png'):
                continue
            content = archive.file_bytes(index)
            if content[:8] != b'\x89PNG\r\n\x1a\n' or int.from_bytes(content[16:20], 'big') != 986:
                raise ValueError('Unexpected original town atlas: ' + entry.full_path)
            target = DATA / 'overlay/common_lang/sd/map/11/111020100' / entry.full_path
            if target.exists() and target.read_bytes() != content:
                raise ValueError('Town atlas override differs from its original: ' + str(target))
            target.parent.mkdir(parents=True, exist_ok=True)
            if not target.exists():
                target.write_bytes(content)
        return
    raise FileNotFoundError('Original Mitra package is required for its atlas overrides.')


TEXT_TABLES = ('_event_text.txt', '_event_teller.txt', 'map_text.txt', 'map_teller.txt', 'common_teller.txt')


def text_rows(data):
    """(id, text) rows of a Memorial `id,text` table."""
    try:
        decoded = data.decode('utf-8-sig')
    except UnicodeDecodeError:
        # Two original Paladia teller tables use Windows Japanese encoding.
        # Their scene text is UTF-8. Decode each table independently.
        decoded = data.decode('cp932')
    for line in decoded.splitlines():
        if line.strip():
            text_id, _, text = line.partition(',')
            yield text_id, text


_MAP_TELLERS = {}
_GLOBAL_MAPS = None


def localized_rows(data):
    """Read English and the other language cells without dropping empty cells."""
    return {fields[0]: fields[1:] for line in data.decode('utf-8-sig').splitlines()
            if line.strip() for fields in [line.split('^')]}


def english_source(text):
    """Do not fill an English gap with untranslated Japanese/Korean source text."""
    # Editor annotations inside original commands are not displayed dialogue.
    display = re.sub(r'<[^>]+>', '', text)
    return bool(text.strip()) and not re.search(r'[\u3041-\u3096\u30a1-\u30fa\u30fd-\u30ff\u3400-\u9fff\uac00-\ud7af]', display)


def merge_localized(base, existing, replacements=None, defaults=None):
    """Fill missing English cells, retaining retail translations in every other cell."""
    values = localized_rows(existing)
    changed = 0
    for text_id, text in text_rows(base):
        text = translated_caption((replacements or {}).get(text_id, text))
        english = re.sub('，(?=<)', ',', text).replace('，', ', ')
        if text_id not in values:
            values[text_id] = [english] * LANGUAGES
            changed += 1
        elif english_source(english) and not (values[text_id] and values[text_id][0].strip()):
            cells = values[text_id]
            cells.extend([''] * max(0, LANGUAGES - len(cells)))
            cells[0] = english
            changed += 1
    for text_id, english in (defaults or {}).items():
        cells = values.setdefault(text_id, [''] * LANGUAGES)
        if not cells[0].strip():
            cells[0] = english
            changed += 1
    if not changed:
        return existing, 0
    return ''.join('^'.join([i] + cells) + '\n' for i, cells in values.items()).encode('utf8'), changed


def map_tellers(map_id, memorial):
    """{teller id: name} from the Memorial town map package `map_id`, {} when there is none."""
    from cricodecs import cpk
    global _GLOBAL_MAPS
    if _GLOBAL_MAPS is None:
        _GLOBAL_MAPS = collections.defaultdict(list)
        for path in (DATA / 'client/files').rglob('*.cpk'):
            if any(part.startswith('map') for part in path.parts):
                _GLOBAL_MAPS[re.sub(r'^Ver\d+_', '', path.name)].append(path)
    if map_id not in _MAP_TELLERS:
        tellers = {}
        originals = _GLOBAL_MAPS.get(f'{map_id}.cpk', [])
        for source in originals + memorial.get(f'{map_id}.cpk', []):
            try:
                archive = cpk.load(str(source))
                source_names, translated = {}, {}
                for index, entry in enumerate(archive.file_infos()):
                    if entry.full_path == 'map_teller.txt':
                        source_names = dict(text_rows(archive.file_bytes(index)))
                    elif entry.full_path == 'map_teller_sg.txt':
                        translated = {i: cells[0] for i, cells in
                                      localized_rows(archive.file_bytes(index)).items()
                                      if cells and cells[0].strip()}
                for speaker, name in {**source_names, **translated}.items():
                    name = translated_caption(name)
                    if english_source(name):
                        tellers.setdefault(speaker, name)
            except ValueError:
                continue
        tellers.update(MAP_ENGLISH_NAMES.get(map_id, {}))
        _MAP_TELLERS[map_id] = tellers
    return _MAP_TELLERS[map_id]


_SCENE_MAPS = None


def scene_maps(scene):
    """Resolve town packages from the same mission's original resource list."""
    global _SCENE_MAPS
    if scene[:-2] in SCENE_MAP_SOURCES:
        return {SCENE_MAP_SOURCES[scene[:-2]]}
    if _SCENE_MAPS is None:
        resources = {}
        for table, key in (('F_RESOURCE_MST.ndjson', '9ZCEWn0z'),
                           ('F_RESOURCE_MAP_MST.ndjson', 'Nnb20keZ')):
            resources.update({str(r[key]): r for r in rows(table)})
        linked = collections.defaultdict(set)
        for mission in rows('F_MISSION_MST.ndjson'):
            refs = [resources[i] for i in re.findall(r'\d+', str(mission.get('q4f9IdMs', '')))
                    if i in resources]
            maps = {Path(r['pJ56sAEo']).stem for r in refs
                    if str(r.get('3LHdc6Qa', '')).split('/')[0].startswith('map')}
            for resource in refs:
                if str(resource.get('3LHdc6Qa', '')).split('/')[0].startswith('event'):
                    linked[Path(resource['pJ56sAEo']).stem].update(maps)
        _SCENE_MAPS = linked
    if scene in _SCENE_MAPS:
        return _SCENE_MAPS[scene]
    # Consecutive scenes may share a single resource declaration on entry.
    return set().union(*(maps for sibling, maps in _SCENE_MAPS.items()
                         if sibling[:-2] == scene[:-2]))


def scene_tellers(scene, memorial):
    candidates = collections.defaultdict(set)
    for map_id in scene_maps(scene):
        for speaker, name in map_tellers(map_id, memorial).items():
            if english_source(name):
                candidates[speaker].add(name)
    # Long scene ids have both two-digit and four-digit command suffixes.
    # Try their actual map ids rather than truncating only the last two digits.
    direct = {}
    for suffix in (2, 4):
        for map_id in (scene[:-suffix], scene[:-suffix] + '00'):
            direct.update({i: n for i, n in map_tellers(map_id, memorial).items()
                           if english_source(n)})
    inherited = {}
    for source in memorial.get(SCENE_TELLER_SOURCES.get(scene, '') + '.cpk', [])[:1]:
        from cricodecs import cpk
        archive = cpk.load(str(source))
        for index, entry in enumerate(archive.file_infos()):
            if entry.full_path.endswith('_event_teller.txt'):
                inherited.update(text_rows(archive.file_bytes(index)))
    return {**{i: next(iter(names)) for i, names in candidates.items() if len(names) == 1},
            **direct, **inherited, **SCENE_ENGLISH_NAMES.get(scene, {})}


_UNIQUE_TELLERS = {}


def unique_tellers(memorial):
    """{teller id: name} over every Memorial map_teller, for ids that always carry one name."""
    from cricodecs import cpk
    if not _UNIQUE_TELLERS:
        names = collections.defaultdict(set)
        for sources in memorial.values():
            for source in sources:
                if source.suffix != '.cpk':
                    continue
                try:
                    archive = cpk.load(str(source))
                    for index, entry in enumerate(archive.file_infos()):
                        if entry.full_path == 'map_teller.txt':
                            for text_id, name in text_rows(archive.file_bytes(index)):
                                names[text_id].add(name)
                except (ValueError, UnicodeDecodeError):
                    continue
        _UNIQUE_TELLERS.update({i: n.pop() for i, n in names.items() if len(n) == 1})
        _UNIQUE_TELLERS.setdefault('', '')  # built, even when empty
    return _UNIQUE_TELLERS


_COMMON_IDS = set()


def common_ids():
    """Speaker ids of the shared common_teller (Rain, Lasswell, ...), looked up bare."""
    from cricodecs import cpk
    if not _COMMON_IDS:
        archive = cpk.load(str(DATA / 'client/files/common_lang/sd/common/Ver94_map_common_tutorial.cpk'))
        for index, entry in enumerate(archive.file_infos()):
            if entry.full_path == 'common_teller.txt':
                _COMMON_IDS.update(i for i, _ in text_rows(archive.file_bytes(index)))
    return _COMMON_IDS


def scene_scoped(speaker):
    """True for the ids the client looks up in the scene's own table (`<scene id><id>`)."""
    return len(speaker) == 6 and speaker.startswith('3')


def add_scene_speakers(archive, members, memorial):
    """Give every speaker a scene names a scene speaker id of its own; returns rows added.

    The client looks a scene's 3xxxxx speakers up as `<scene id><speaker id>` in the scene's
    own `_event_teller`, but any other id bare in the shared common list. Memorial scenes also
    name town speakers (2xxxxx, from the town's map_teller) and scene-local 99xxxxx ids, which
    that list never has. Each such speaker gets a free 3xxxxx id in `_event_teller` and the
    scene text is rewritten to name it.
    """
    added = 0
    for name, index in list(members.items()):
        if not name.endswith('_event_teller.txt'):
            continue
        scene = name[:-len('_event_teller.txt')]
        if scene + '_event_text.txt' not in members or not scene.isdigit():
            continue
        tellers = dict(text_rows(archive.file_bytes(index)))
        localized_tellers = members.get(scene + '_event_teller_sg.txt')
        localized_names = (localized_rows(archive.file_bytes(localized_tellers))
                           if localized_tellers is not None else {})
        tellers.update({i: cells[0] for i, cells in localized_names.items()
                        if cells and cells[0].strip()})
        texts = [members[scene + '_event_text.txt']]
        if scene + '_event_text_sg.txt' in members:
            texts.append(members[scene + '_event_text_sg.txt'])
        named = set(re.findall(r'<name=(\d+)>', archive.file_bytes(texts[0]).decode('utf-8-sig')))
        for text in texts[1:]:
            named.update(re.findall(r'<name=(\d+)>', archive.file_bytes(text).decode('utf-8-sig')))
        town = scene_tellers(scene, memorial)
        known = {**town, **tellers}
        # Empty retail teller rows deliberately suppress a speaker caption.
        # Remove only those name commands, keeping their dialogue unchanged.
        unnamed = {speaker for speaker in named if speaker in tellers and not tellers[speaker].strip()
                   and not any(cell.strip() for cell in localized_names.get(speaker, []))}
        if unnamed:
            for text in texts:
                body = archive.file_bytes(text).decode('utf-8-sig')
                body = re.sub(r'<name=(\d+)>', lambda m: '' if m.group(1) in unnamed else m.group(0), body)
                archive.replace_bytes(text, body.encode('utf8'))
            added += len(unnamed)
        renamed, taken = {}, set(tellers)
        for speaker in sorted(named - common_ids()):
            if speaker in unnamed or (scene_scoped(speaker) and speaker in tellers) or speaker not in known:
                continue
            new_id = '3' + speaker[1:] if len(speaker) == 6 else '39' + speaker[-4:]
            while new_id in taken:
                new_id = str(300000 + (int(new_id) + 1) % 100000)
            renamed[speaker] = new_id
            taken.add(new_id)
        if not renamed:
            continue
        extra = [(renamed[i], known[i]) for i in sorted(renamed)]
        table = ''.join(f'{i},{t}\n' for i, t in list(tellers.items()) + extra)
        archive.replace_bytes(index, table.encode('utf-8'))
        localized = members.get(name[:-len('.txt')] + '_sg.txt')
        if localized is not None:  # already shipped localized: extend it the same way
            old = archive.file_bytes(localized).decode('utf-8-sig').rstrip('\r\n')
            new = ''.join('\n' + '^'.join([i] + [t.replace('，', ', ')] * LANGUAGES) for i, t in extra)
            archive.replace_bytes(localized, (old + new + '\n').encode('utf-8'))
        for text in texts:
            body = archive.file_bytes(text).decode('utf-8-sig')
            body = re.sub(r'<name=(\d+)>', lambda m: f'<name={renamed.get(m.group(1), m.group(1))}>', body)
            archive.replace_bytes(text, body.encode('utf-8'))
        added += len(extra)
    return added


def localized_package(source, memorial=None, scene_alias=None):
    """Memorial package plus the Global `_sg` text members built from its English."""
    from cricodecs import cpk
    archive = cpk.load(str(source))
    members = {entry.full_path: index for index, entry in enumerate(archive.file_infos())}
    added = apply_english_dialogue(archive, members)
    # Fill reviewed base dialogue before speaker IDs are scoped to this scene.
    # Otherwise a newly resolved town speaker changes the source hash before
    # its English translation can fill an empty retail cell.
    for name, index in list(members.items()):
        if not name.endswith('_event_text.txt'):
            continue
        target = name[:-4] + '_sg.txt'
        existing = archive.file_bytes(members[target]) if target in members else b''
        merged, changed = merge_localized(archive.file_bytes(index), existing)
        if not changed:
            continue
        if target in members:
            archive.replace_bytes(members[target], merged)
        else:
            next_id = max((entry.id for entry in archive.file_infos()), default=-1) + 1
            archive.add_bytes(merged, target, id=next_id)
            members = {entry.full_path: i for i, entry in enumerate(archive.file_infos())}
        added += 1
    added += add_scene_speakers(archive, members, memorial) if memorial else 0
    for name, index in list(members.items()):
        for suffix in TEXT_TABLES:
            if not (name == suffix or name.endswith(suffix)):
                continue
            target = name[:-len('.txt')] + '_sg.txt'
            existing = archive.file_bytes(members[target]) if target in members else b''
            map_id = re.sub(r'^Ver\d+_', '', source.stem)
            replacements = MAP_ENGLISH_NAMES.get(map_id) if name == 'map_teller.txt' else None
            defaults = MAP_ENGLISH_DEFAULTS.get(map_id) if name == 'map_text.txt' else None
            merged, changed = merge_localized(archive.file_bytes(index), existing, replacements, defaults)
            if not changed and target in members:
                continue
            if target in members:
                archive.replace_bytes(members[target], merged)
            else:
                next_id = max((entry.id for entry in archive.file_infos()), default=-1) + 1
                archive.add_bytes(merged, target, id=next_id)
            added += 1
    members = {entry.full_path: index for index, entry in enumerate(archive.file_infos())}
    added += apply_english_dialogue(archive, members)
    if not added and not scene_alias:
        return source.read_bytes(), 0
    if scene_alias:
        original, requested = scene_alias
        for index, entry in enumerate(list(archive.file_infos())):
            if entry.full_path.startswith(original + '_event'):
                next_id = max((item.id for item in archive.file_infos()), default=-1) + 1
                archive.add_bytes(archive.file_bytes(index), requested + entry.full_path[len(original):], id=next_id)
                added += 1
        # The Global 9 reader requires the ID index when binding this scene.
        # Memorial's filename-only container otherwise crashes in CRI's ITOC reader.
        compatible = cpk.create(cpk.CpkPreset.FILENAME_ID, align=archive.alignment)
        for index, entry in enumerate(archive.file_infos()):
            compatible.add_bytes(archive.file_bytes(index), entry.full_path, id=index)
        archive = compatible
    data = archive.save_bytes()
    size = struct.unpack_from('<Q', data, 8)[0]
    end = 16 + size
    return global_cpk_header(data[:end]) + data[end:], added


def repair_text(out, only=()):
    """Repair effective cached text in overlays, leaving preserved source CPKs intact."""
    out = out.resolve()
    memorial = memorial_index()
    manifest = out / 'manifest.json'
    prior = json.loads(manifest.read_text(encoding='utf8')) if manifest.is_file() else []
    previous = {row['path']: row for row in prior}
    records, checked = [], 0
    for directory, name, version in wanted_files():
        if not name.endswith('.cpk') or not directory.split('/')[0].startswith(('event', 'map', 'common')):
            continue
        if only and not any(directory == p or directory.startswith(p.rstrip('/') + '/') for p in only):
            continue
        relative = f'{device_dir(directory)}/Ver{version}_{name}'
        candidates = [DATA / root / language / relative
                      for root in ('overlay', 'client/files', 'memorial_fill')
                      for language in ('common_lang', 'en')]
        source = next((p for p in candidates if p.is_file()), None)
        if source is None:
            continue
        checked += 1
        old = previous.get(source.relative_to(out).as_posix(), {}) if source.is_relative_to(out) else {}
        original = DATA / old['source'] if old.get('text_repairs') else source
        if original != source and hashlib.sha256(original.read_bytes()).hexdigest() != old['source_sha256']:
            raise ValueError('Preserved text repair source changed: ' + str(original))
        # Rebuild from the preserved input so edits to the accepted translations
        # also replace an earlier generated English cell.
        data, changed = localized_package(original, memorial)
        if not changed:
            continue
        target = out / source.relative_to(next(root for root in
                         (DATA / 'overlay', DATA / 'client/files', DATA / 'memorial_fill')
                         if source.is_relative_to(root)))
        target.parent.mkdir(parents=True, exist_ok=True)
        before = hashlib.sha256(source.read_bytes()).hexdigest()
        if data == source.read_bytes() and source == target:
            continue
        target.write_bytes(data)
        relative_target = target.relative_to(out).as_posix()
        old = previous.get(relative_target, {}) if source == target else {}
        records.append({'path': relative_target,
                        'source': old.get('source', source.relative_to(DATA).as_posix()),
                        'source_sha256': old.get('source_sha256', before),
                        'sha256': hashlib.sha256(data).hexdigest(),
                        'text_repairs': old.get('text_repairs', 0) + changed, 'bytes': len(data)})
    rebuilt = {row['path'] for row in records}
    if records:
        manifest.write_text(json.dumps([r for r in prior if r['path'] not in rebuilt] + records,
                                       indent=1), encoding='utf8')
    print(f'Checked {checked} cached packages; repaired {len(records)} text packages in {out}.', flush=True)
    return records


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--only', action='append', default=[],
                        help='Resource directory prefix to include, e.g. map/11 or event/11 (repeatable).')
    parser.add_argument('--rebuild', action='store_true',
                        help='Build packages again even when the output already has them.')
    parser.add_argument('--repair-text', action='store_true',
                        help='Repair existing cached English/speaker tables into --out overlays.')
    args = parser.parse_args()
    if args.repair_text:
        repair_text(args.out, args.only)
        return
    repaired_indexes = repair_staged_indexes(args.out)
    present, memorial = global_names(), memorial_index()
    town_atlas_overrides(memorial)
    manifest, skipped = [], collections.Counter()
    for directory, name, version in wanted_files():
        if args.only and not any(directory == p or directory.startswith(p.rstrip('/') + '/') for p in args.only):
            continue
        versioned = f'Ver{version}_{name}'
        if (f'common_lang/{device_dir(directory)}', versioned) in present or (f'en/{device_dir(directory)}', versioned) in present:
            skipped['global'] += 1
            continue
        source_name = LEGACY_STORY_PACKAGES.get(name, name)
        sources = memorial.get(source_name)
        if not sources:
            skipped['no-memorial'] += 1
            continue
        relative = f'common_lang/{device_dir(directory)}/Ver{version}_{name}'
        target = args.out / relative
        compatible = True
        if target.is_file() and source_name != name:
            from cricodecs import cpk
            compatible = cpk.load(str(target)).has_itoc
        if target.is_file() and not args.rebuild and compatible:
            if source_name != name:
                overlay = DATA / 'overlay' / relative
                overlay.parent.mkdir(parents=True, exist_ok=True)
                overlay.write_bytes(target.read_bytes())
            skipped['already-filled'] += 1
            continue
        data = None
        for source in sorted(sources, key=lambda p: (p.is_relative_to(DATA / 'memorial'),
                                                    p.stat().st_mtime), reverse=True):
            try:
                if source.suffix in ('.acb', '.awb'):
                    data, added = source.read_bytes(), 0
                    if data[:4] not in (b'@UTF', b'AFS2'):  # CRI sound bank headers
                        raise ValueError('not a CRI sound bank')
                elif source.suffix == '.usm':
                    data, added = source.read_bytes(), 0
                    if data[:4] != b'CRID':
                        raise ValueError('not a CRI movie')
                else:
                    alias = (Path(source_name).stem, Path(name).stem) if source_name != name else None
                    data, added = localized_package(source, memorial, alias)
                    if not added:
                        data = source.read_bytes()  # untouched original bytes
                break
            except ValueError:
                continue
        if data is None:
            skipped['unreadable-memorial'] += 1
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        if source_name != name:
            overlay = DATA / 'overlay' / relative
            overlay.parent.mkdir(parents=True, exist_ok=True)
            overlay.write_bytes(data)
        manifest.append({'path': relative, 'source': source.relative_to(DATA).as_posix(),
                         'sg_members_added': added, 'bytes': len(data),
                         'sha256': hashlib.sha256(data).hexdigest(),
                         **({'legacy_scene': Path(source_name).stem,
                             'requested_scene': Path(name).stem,
                             'scope': 'Original Farplane introduction replaces the unavailable later variant.'}
                            if source_name != name else {})})
    args.out.mkdir(parents=True, exist_ok=True)
    previous = args.out / 'manifest.json'
    if previous.is_file():
        rebuilt = {m['path'] for m in manifest}
        manifest = [m for m in json.loads(previous.read_text(encoding='utf-8'))
                    if m['path'] not in rebuilt] + manifest
    (args.out / 'manifest.json').write_text(json.dumps(manifest, indent=1), encoding='utf-8')
    print(f'wrote {len(manifest)} packages, {sum(m["bytes"] for m in manifest) / 2**20:.1f} MiB; '
          f'repaired {repaired_indexes} extended ID indexes; skipped {dict(skipped)}')


if __name__ == '__main__':
    main()
