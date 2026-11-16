"""Build only approved repairs on the already installed Global/Kira baselines.

Unapproved earlier-JP overlay files are never read here. The only overlay read
is the single exact hash-approved quest title used by shared text metadata.
This module reads pinned members of existing published data archives, applies
the reviewed holiday recipes and English labels, repairs missing existing unit
names, then rebuilds the two unit lookup indexes.
Missing Break descriptions are appended without changing existing labels.
One classic HARD challenge target is merged without replacing its other fields.
The separately hash-approved quest title participates in shared text metadata.
No archive is extracted, copied or changed, and no resource version is changed.
"""
from contextlib import ExitStack
import hashlib
import json
from pathlib import Path
import re
import zipfile

from apply_jp_unit_tables import patch_decoded, patch_native
from decode_client_data import client_manifest
from native_master_index import build_index
from prepare_offline_cache import loading_text, localized_text_versions

ROOT = Path(__file__).resolve().parents[2]
ARCHIVES = ROOT / 'source/build/distribution/assets'
RECIPE_CONTRACT = ROOT / 'source/server/content/quest_recipe_repair.json'
BREAK_TEXT_CONTRACT = ROOT / 'source/server/content/battle/break_text_repairs.json'
BREAK_TEXT_MEMBER = 'native/localized_texts/en/Ver13_f3uHXanH.dat'
CLASSIC_CHALLENGE_CONTRACT = ROOT / 'source/server/content/battle/classic_hard_challenge_repair.json'
CLASSIC_CHALLENGE_MEMBER = 'native/mst/Ver373_GL9t6cMF.dat'
CLASSIC_CHALLENGE_STATIC = 'static/mst_decoded/F_CHALLENGE_MST.ndjson'

# Memorial changed these scripts without supplying their new dialogue rows.
# Use the matching original Global script/text packages recovered from the
# content-server archive, with their existing native resource names/versions.
GLOBAL_TOWN_PACKAGES = {
    'common_lang/sd/event/11/Ver47_111020301.cpk': 'fa8fedb2591d826acac3742a8384a2d600fd4c6189d05431021a7b63b0cab41a',
    'common_lang/sd/map/11/Ver32_111020400.cpk': '8c93ea69753e4ff95ac29d9993b96a1a29888319646b2e4050f99a858f058890',
    'common_lang/sd/map/11/Ver39_111020300.cpk': '04e1a2f123dd43cb8146ae12a202ea261cbabb7840830e7d792eadf25d9e2728',
    'common_lang/sd/map/32/Ver13_132040100.cpk': '48c3ce12e9eb0450f598fbe09913364bdd0b76009c5bd8bfa6fc4ed3852cb897',
    'common_lang/sd/map/51/Ver46_151020100.cpk': 'e3d80865a053e3c0733b2b9c10380bf5909296e3ff8160b19195d05477d1b080',
    'common_lang/sd/event/21/Ver28_121020102.cpk': '4f5814f47ea10e5639b497dc2f96220b67f698d508e1a9a09951b4a3a3b7402d',
    'common_lang/sd/event2/06/Ver14_550620104.cpk': '9a1c9387dbe59e67d1d25f8d38a900373384b8c6a6c93bd698136e46b3ec3114',
    'common_lang/sd/event4/01/Ver1_554011902.cpk': '7c095ed6db7f959ad128a63daf0b228a4082be01ef60bb0ec598c25b6e2bb3a6',
    'common_lang/sd/event4/02/Ver2_554020202.cpk': '17ac3ec09e46ef27b9c36c44f22fdfac4b2376ecd3f4be8e29341f619fc1df09',
}

# Original Global packages with proven stale message bindings. The localized
# writer changes only the pinned script's specific message arguments and keeps
# the existing original dialogue. Never replace the downloaded source CPKs.
GLOBAL_SCENE_MESSAGE_PACKAGES = {
    'common_lang/sd/event/92/Ver28_18301010101.cpk': '5fa9f654518404e64c6f8c72537db51d18ce710e51a7f4039141a4724a7c83e1',
    'common_lang/sd/event2/chara2/Ver15_402090403.cpk': '1bd27374544a34ee003ec339e60e0650abdaff83badeda54a73da42a31786739',
}

# These are member hashes, not hashes of the multi-gigabyte archives. The Kira
# patch follows the base pack in the existing published installation manifest.
BASELINES = {
    CLASSIC_CHALLENGE_MEMBER: ('exvius-data-010.zip', '42f0c66de5d4dca59f2c117d5f29998a34faa793523534b1f88a3f3c10d231ad'),
    CLASSIC_CHALLENGE_STATIC: ('exvius-data-001.zip', '2c34c606987a3b096ad72cf02b319e382aa15ac2fbe59a348362da91a8cab412'),
    BREAK_TEXT_MEMBER: ('exvius-data-010.zip', '8ad7f5e3721331247c2eebe9c83428484da039bfc62dd1a8b4bd81adf1b3f8be'),
    'native/mst/Ver318_yu5rvEI3.dat': ('exvius-data-010.zip', 'b59a766f2ba25d1b5291c15795a649bd15ff61c03f1af043a304328d7455f077'),
    'native/mst/Ver323_27pGMZDm.dat': ('exvius-data-010.zip', '12488b40653b514b31394b8f11f3589e5b26b82ed152e192e86eb38f48d089d9'),
    'native/mst/Ver392_S67QEJsz.dat': ('exvius-kira-r7.zip', '88202b347484611bb7f84418e40f024ecd01f711404b091d635243ec208eaa50'),
    'native/mst/Ver325_psuJ5VE2.dat': ('exvius-data-010.zip', '000d7d01f22c022cf0e35e4d04c0ff5851d0188cd120929cdaaa41f0e47a2667'),
    'native/mst/Ver375_LM1APs6u.dat': ('exvius-data-010.zip', '8b9514c23b32ce253aea215694c1da719c01cbeb6d0ca7da3dd9c3296dcd4ba0'),
    'native/localized_texts/en/Ver235_E0NdslwL.dat': ('exvius-kira-r7.zip', 'd2ba46aaa8a61ebe09318b14ca684984fa89763b9a73f2e3315e0d5c473f8c4d'),
    'native/localized_texts/en/Ver232_Nao9HYWk.dat': ('exvius-data-010.zip', '09de1a1711ff27e6f07f839472b3d612c5b5ae576ebea28aa886ac64dfce3e23'),
    'native/localized_texts/en/Ver239_CD4giPVu.dat': ('exvius-data-010.zip', '6b41a17f3934a49fff8ee35c5c2c09ef8f5cbf516d06a8b35bfec5e92d70f0c3'),
    'native/mst/Ver710_i5QEJpua.dat': ('exvius-kira-r7.zip', '3c5a0dfb8d2ed689930a88d07ce45b929e22d7683e6a224118eab75e2116630e'),
    'native/mst/Ver244_Da62x85q.dat': ('exvius-kira-r7.zip', 'ea3abc39b5ba88c5493d96f27f583cb3e3a39832e03706441c47d3136d59014c'),
    'native/mst/Ver26_jqv20D3o.dat': ('exvius-data-010.zip', '60bf578789e8f1651c90f4d4a5d79003e39bc7381fb36564afba4a14ad24f2f2'),
    'static/mst_decoded/F_RECIPE_BOOK_MST.ndjson': ('exvius-data-001.zip', 'e2965cd208f2e8592df1486511792a9e8948a1ce45b03c7768f7f3e2d50323ba'),
    'static/mst_decoded/F_RECIPE_MST.ndjson': ('exvius-data-001.zip', 'b962a123a7c715c376447e7bd793a0a9d680404a0f1437927e84e1f8b286e7bd'),
    'static/mst_decoded/F_EQUIP_ITEM_MST.ndjson': ('exvius-kira-r7.zip', 'b74e3fbf20324c648c5882cc1254cdd0addd992ce7b0fbe829edc0ed629a67db'),
    'static/mst_decoded/F_EQUIP_ITEM_EXPLAIN_MST.ndjson': ('exvius-data-001.zip', '6c9b65170e85f3aeca4798a611b2b0b76ed840f678cdd398d09ba2a77225a35c'),
    'static/mst_decoded/F_ICON_MST.ndjson': ('exvius-data-001.zip', '1b2437f7b8a71323a7305ba22a97b0e6d8586e196a2b0ce8b933abef9498da69'),
    'static/text_decoded/F_TEXT_ITEM_EQUIP_NAME.ndjson': ('exvius-kira-r7.zip', 'fb3383c314f6686b8bb567aa50d390e2ff62ab89b3c3489d5bb1ed4f8b49b2ee'),
    'static/text_decoded/F_TEXT_ITEM_EQUIP_SHORT.ndjson': ('exvius-data-001.zip', '7d774396430ef7c98d672311dbdc07ee95bb56dcdb057d4a0ad5813a50e4a1d1'),
    'static/text_decoded/F_TEXT_ITEM_EQUIP_LONG.ndjson': ('exvius-data-001.zip', 'a4ff3d36db28976375dc6fbea7ed0436117cab4eb452adaddc340709b4066508'),
    'native/localized_texts/en/Ver229_sZE3Lhgj.dat': ('exvius-kira-r7.zip', '9f5b758de407b08ca33db35aea4a21a96c8e9ce365e6a5f25c3bb97d4f1477d8'),
    'static/text_decoded/F_TEXT_UNITS_NAME.ndjson': ('exvius-kira-r7.zip', '31af4c03ff09818e39bdde330190ed5237a12ec035defb35773e746ceec66205'),
    'static/mst_decoded/F_UNIT_MST.ndjson': ('exvius-kira-r7.zip', '2ae3532852fb3ba85f5efeaa4cea97ef45ecf594b3933f2340e8a509a9318051'),
    'native/common_lang/sd/item/Ver167_item1_common.cpk': ('exvius-data-003.zip', 'f1d7603bafdf36e56be2ead5ae9248d68f9023c35aa68cb778583be8695627b8'),
}
RECIPE_TABLES = {
    'F_RECIPE_BOOK_MST': ('staFu8U1', 'native/mst/Ver318_yu5rvEI3.dat', {'904001710', '904001720'}),
    'F_RECIPE_MST': ('MpNE6gB5', 'native/mst/Ver323_27pGMZDm.dat', {'904001710', '904001720'}),
    'F_EQUIP_ITEM_MST': ('J1YX9kmM', 'native/mst/Ver392_S67QEJsz.dat', {'870000018', '870000019'}),
    'F_EQUIP_ITEM_EXPLAIN_MST': ('J1YX9kmM', 'native/mst/Ver325_psuJ5VE2.dat', {'870000018', '870000019'}),
    'F_ICON_MST': ('0HUPxDf1', 'native/mst/Ver375_LM1APs6u.dat', {'880000001', '880000002'}),
}
TEXT_TABLES = {
    'F_TEXT_ITEM_EQUIP_NAME': 'native/localized_texts/en/Ver235_E0NdslwL.dat',
    'F_TEXT_ITEM_EQUIP_SHORT': 'native/localized_texts/en/Ver232_Nao9HYWk.dat',
    'F_TEXT_ITEM_EQUIP_LONG': 'native/localized_texts/en/Ver239_CD4giPVu.dat',
}


def sha(data):
    return hashlib.sha256(data).hexdigest()


class _MemoryFile:
    """Path text/bytes operations used by the proven cache writers, in memory."""
    def __init__(self, raw=b''):
        self.raw = raw

    def read_bytes(self):
        return self.raw

    def read_text(self, encoding='utf8'):
        return self.raw.decode(encoding)

    def write_text(self, text, encoding='utf8', **unused):
        self.raw = text.encode(encoding)
        return len(text)


def _approved_quest_title():
    """The shared text index must match the separately delivered quest title."""
    contract = json.loads((ROOT / 'source/server/content/quest_chain_repairs.json').read_text(encoding='utf8'))
    name = 'localized_texts/en/Ver6_NMwfx1lf.dat'
    files = [row for row in contract['native_overlay']['files'] if row['path'] == name]
    if len(files) != 1 or not re.fullmatch(r'[a-f0-9]{64}', files[0]['sha256']):
        raise ValueError('Approved quest title must have exactly one pinned native file.')
    raw = (ROOT / 'data/overlay' / name).read_bytes()
    if sha(raw) != files[0]['sha256']:
        raise ValueError('Approved quest title changed before localized-index projection.')
    return raw


def build_approved_files():
    """Return {DataPack entry path: bytes}, without writing project files.

    There are 17 recipe outputs, four original-sized unit master/index outputs,
    two unit name outputs, one Break text output, three challenge outputs and
    nine original Global town and event script/text packages.
    Original item sprites are verified in the
    installed baseline and are not duplicated. The only overlay read is the
    exact hash-approved quest title used by the coupled localized-text index.
    """
    contract = json.loads(RECIPE_CONTRACT.read_text(encoding='utf8'))
    definitions = {row['table']: row for row in contract['tables']}
    if set(definitions) != set(RECIPE_TABLES):
        raise ValueError('Approved recipe master scope changed.')
    text_definitions = {row['table']: row for row in contract['text_tables']}
    if set(text_definitions) != set(TEXT_TABLES):
        raise ValueError('Approved recipe English scope changed.')
    manifest = {row['table']: row for row in client_manifest(
        ROOT / 'repository snapshots/FFBE-Global-v9.0.0-original.apk').values()}
    outputs = {}
    with ExitStack() as stack:
        archives = {}

        def baseline(member):
            name, expected = BASELINES[member]
            if name not in archives:
                archives[name] = stack.enter_context(zipfile.ZipFile(ARCHIVES / name))
            raw = archives[name].read(member)
            if sha(raw) != expected:
                raise ValueError('Approved archive member changed: ' + name + '::' + member)
            return raw

        for table, (identity, member, ids) in RECIPE_TABLES.items():
            definition = definitions[table]
            if (definition['identity_fields'] != [identity] or definition['operation'] != 'replace'
                    or definition['active_native_path'] != member[7:]
                    or len(definition['rows']) != 2 or {r[identity] for r in definition['rows']} != ids):
                raise ValueError('Approved recipe identities changed: ' + table)
            outputs[member], _ = patch_native(baseline(member), manifest[table]['key'],
                                               [identity], definition['rows'])
            static = 'static/mst_decoded/' + table + '.ndjson'
            outputs[static], _ = patch_decoded(baseline(static), [identity], definition['rows'])

        localized = {}
        for table, member in TEXT_TABLES.items():
            labels = text_definitions[table]['inline_labels']
            if len(labels) != 2 or not all(key.endswith(('870000018', '870000019')) for key in labels):
                raise ValueError('Approved recipe English identities changed: ' + table)
            source, target = _MemoryFile(baseline(member)), _MemoryFile()
            loading_text(source, target, manifest[table]['key'], labels, append_missing=True)
            outputs[member] = target.read_bytes()
            version = re.search(r'/Ver(\d+)_', member)[1]
            localized[table] = version, target
            static = 'static/text_decoded/' + table + '.ndjson'
            rows = [{'key': key, 'v': [label, label]} for key, label in labels.items()]
            # Preserved text files contain repeated unrelated keys. Keep every
            # original record in order rather than collapsing their groups.
            outputs[static], _ = patch_decoded(baseline(static), ['key'], rows, operation='replace_groups')
        member = 'native/mst/Ver710_i5QEJpua.dat'
        name_contract = json.loads((ROOT / 'source/server/content/unit_name_repair.json').read_text('utf-8'))
        labels = name_contract['labels']
        original_units = {row['3HriTp6B'] for row in map(json.loads,
                          baseline('static/mst_decoded/F_UNIT_MST.ndjson').splitlines())}
        old_names = [json.loads(line) for line in baseline('static/text_decoded/F_TEXT_UNITS_NAME.ndjson').splitlines()]
        missing = {'MST_UNIT_NAME_' + uid for uid in original_units} - {row['key'] for row in old_names}
        if set(labels) != missing or len(labels) != 222:
            raise ValueError('Unit name repair must cover exactly the existing missing forms, without importing units')
        if any(re.search(r'[\u3040-\u30ff\u3400-\u9fff]', value) or '\u2014' in value for value in labels.values()):
            raise ValueError('Unit name repair contains an untranslated name')
        name_member = 'native/localized_texts/en/Ver229_sZE3Lhgj.dat'
        name_target = _MemoryFile()
        loading_text(_MemoryFile(baseline(name_member)), name_target,
                     manifest['F_TEXT_UNITS_NAME']['key'], labels, append_missing=True)
        outputs[name_member] = name_target.read_bytes()
        localized['F_TEXT_UNITS_NAME'] = '229', name_target
        additions = [{'key': key, 'v': [label, label]} for key, label in sorted(labels.items())]
        outputs['static/text_decoded/F_TEXT_UNITS_NAME.ndjson'] = b''.join(
            (json.dumps(row, ensure_ascii=False, separators=(',', ':')) + '\n').encode('utf-8')
            for row in old_names + additions)
        break_contract = json.loads(BREAK_TEXT_CONTRACT.read_text(encoding='utf8'))
        break_labels = break_contract['labels']
        expected_break_ids = ({'407371000', '407371001', '407371002', '303091000', '303091001'}
                              | {str(value) for value in range(306251002, 306251008)})
        if (break_contract['table'] != 'F_TEXT_MONSTER_PARTS_BREAK_DES'
                or set(break_labels) != {'MST_MONSTER_PARTS_BREAK_DESCRIPTION_' + value
                                         for value in expected_break_ids}
                or any(not isinstance(value, str) or not value or any(c in value for c in '^\r\n')
                       for value in break_labels.values())):
            raise ValueError('Break description repair escaped the eleven missing references')
        break_target = _MemoryFile()
        loading_text(_MemoryFile(baseline(BREAK_TEXT_MEMBER)), break_target,
                     manifest['F_TEXT_MONSTER_PARTS_BREAK_DES']['key'], break_labels,
                     append_missing=True)
        outputs[BREAK_TEXT_MEMBER] = break_target.read_bytes()
        localized['F_TEXT_MONSTER_PARTS_BREAK_DES'] = '13', break_target
        target = _MemoryFile()
        localized['F_TEXT_QUEST'] = '6', _MemoryFile(_approved_quest_title())
        localized_text_versions(_MemoryFile(baseline(member)), target,
                                manifest['F_LOCALIZED_TEXT_MST']['key'], localized)
        outputs[member] = target.read_bytes()

        for table, member, version in [('F_UNIT_EXPLAIN_MST', 'native/mst/Ver244_Da62x85q.dat', 244),
                                       ('F_UNIT_SUB_CATEGORY_MST', 'native/mst/Ver26_jqv20D3o.dat', 26)]:
            raw = baseline(member)
            outputs[member] = raw
            outputs['native/mst/' + manifest[table]['token'] + '.i'] = build_index(
                table, raw, manifest[table]['key'], version)

        challenge = json.loads(CLASSIC_CHALLENGE_CONTRACT.read_text(encoding='utf8'))
        old_target = '18:854010101:306141000:1'
        new_target = '18:854010101:1820000005:1'
        expected_update = {'qo3PECw6': '8540101', 'V36ygRYs': '85401017', 'Pzn5h0Ga': new_target}
        if (challenge['table'] != 'F_CHALLENGE_MST' or challenge['mission_id'] != '8540101'
                or challenge['identity_fields'] != ['qo3PECw6', 'V36ygRYs']
                or challenge['operation'] != 'merge_fields'
                or challenge['original'] != {'V36ygRYs': '85401017', 'qo3PECw6': '8540101',
                                             'Pzn5h0Ga': old_target}
                or challenge['rows'] != [expected_update]
                or challenge['native_member'] != CLASSIC_CHALLENGE_MEMBER
                or challenge['static_member'] != CLASSIC_CHALLENGE_STATIC
                or challenge['native_index_member'] != 'native/mst/GL9t6cMF.i'
                or challenge['native_version'] != 373
                or manifest['F_CHALLENGE_MST']['token'] != 'GL9t6cMF'
                or manifest['F_CHALLENGE_MST']['key'] != '8Dx2QUZS'):
            raise ValueError('Classic HARD challenge repair escaped its single target field')
        static_source = baseline(CLASSIC_CHALLENGE_STATIC)
        selected = [json.loads(line) for line in static_source.splitlines()
                    if line.strip() and json.loads(line).get('V36ygRYs') == '85401017']
        if (len(selected) != 1 or selected[0].get('qo3PECw6') != '8540101'
                or selected[0].get('Pzn5h0Ga') != old_target):
            raise ValueError('Classic HARD challenge baseline identity or original condition changed')
        guards = [{'identity': {'qo3PECw6': '8540101', 'V36ygRYs': '85401017'}, 'field': field,
                   'prior_english': before, 'english': after}
                  for field, before, after in [('qo3PECw6', '8540101', '8540101'),
                                               ('Pzn5h0Ga', old_target, new_target)]]
        native_output, native_stats = patch_native(baseline(CLASSIC_CHALLENGE_MEMBER),
            manifest['F_CHALLENGE_MST']['key'], challenge['identity_fields'], challenge['rows'],
            operation='merge_fields', prior_english_guard=guards)
        static_output, static_stats = patch_decoded(static_source, challenge['identity_fields'], challenge['rows'],
            operation='merge_fields', prior_english_guard=guards)
        if any(stats['replaced_rows'] != 1 or stats['appended_rows'] != 0
               for stats in (native_stats, static_stats)):
            raise ValueError('Classic HARD challenge repair must merge exactly one existing row')
        outputs[CLASSIC_CHALLENGE_MEMBER] = native_output
        outputs['native/mst/GL9t6cMF.i'] = build_index(
            'F_CHALLENGE_MST', native_output, manifest['F_CHALLENGE_MST']['key'], 373)
        outputs[CLASSIC_CHALLENGE_STATIC] = static_output

        # Both icons required by the reconstructed recipes are already supplied
        # byte-for-byte by the approved original item CPK. No JP icon import.
        import sys
        vendor = str(ROOT / 'custom-engine/tools')
        if vendor not in sys.path:
            sys.path.insert(0, vendor)
        from cpk import Cpk
        icons = Cpk(baseline('native/common_lang/sd/item/Ver167_item1_common.cpk'))
        for filename, expected in [('item_20127.png', '292cd87ef1439b199f57863b40de267af0d3ba7c20ca100ac2470550674c6eca'),
                                    ('item_30133.png', 'c487a57d29bcb7cabd6061eaee2b7b17f0b6739a8c836346bb77b0308fb9d305')]:
            if sha(icons.read(filename)) != expected:
                raise ValueError('Original recipe icon changed: ' + filename)
    for relative, expected in GLOBAL_TOWN_PACKAGES.items():
        raw = (ROOT / 'data/client/files' / relative).read_bytes()
        if sha(raw) != expected:
            raise ValueError('Recovered Global town source changed: ' + relative)
        outputs['native/' + relative] = raw
    from fill_content_from_memorial import localized_package
    for relative, expected in GLOBAL_SCENE_MESSAGE_PACKAGES.items():
        source = ROOT / 'data/client/files' / relative
        if sha(source.read_bytes()) != expected:
            raise ValueError('Recovered Global scene source changed: ' + relative)
        raw, changed = localized_package(source)
        if not changed:
            raise ValueError('Recovered Global scene message repair was not applied: ' + relative)
        outputs['native/' + relative] = raw
    if len(outputs) != 38:
        raise ValueError('Approved native/static output count changed.')
    return outputs


if __name__ == '__main__':
    files = build_approved_files()
    print(json.dumps({'files': [{'path': path, 'sha256': sha(raw), 'bytes': len(raw)}
                               for path, raw in sorted(files.items())],
                      'total_bytes': sum(map(len, files.values()))}, indent=2))
