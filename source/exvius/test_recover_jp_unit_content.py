"""Focused checks for typed JP dependency rewrites and version preservation."""
import json
import unittest

from recover_jp_unit_content import HOME, effect_parameters, rewrite_rewards, rewrite_row, rewrite_effect_frames
from recover_earlier_jp_vfx import replacement


class NativeReferenceTests(unittest.TestCase):
    def test_auto_magic_tag_identity_and_limited_multicast_operands(self):
        mapping={'10121':'835000002','1192001':'830001001',
            '1191072':'830001002','1191074':'830001004','1191071':'830001005'}
        for opcode,params,expected in [
            ('35','10121','835000002'),
            ('165','1192001,1,1,1,1,1','830001001,1,1,1,1,1'),
            ('168','5,1191072&1191074,0,4,1191071,0,2,120,99999',
             '5,830001002&830001004,0,4,830001005,0,2,120,99999')]:
            result,pending=effect_parameters({'2kq0BpnD':opcode,'Ha9G5sCS':params},mapping,{})
            self.assertEqual(result,expected);self.assertFalse(pending)

    def test_hybrid_coefficients_are_not_regen_magic_references(self):
        params='0,0,0,0,0,0,0,0,10400,10400'
        result,pending=effect_parameters({'2kq0BpnD':'40','Ha9G5sCS':params},
            {'10400':'835000003'},{})
        self.assertEqual(result,params);self.assertFalse(pending)

    def test_every_process_group_rebinds_without_changing_frames(self):
        value='120:100:2:7:0&120:101:1:7:0@0:99999999:2:4:0@22:102:1:1:0&31:103:1:1:0'
        result=rewrite_effect_frames(value,{'100':'850000001','102':'850000002','103':'850000003'})
        self.assertEqual(result,'120:850000001:2:7:0&120:101:1:7:0@0:99999999:2:4:0@22:850000002:1:1:0&31:850000003:1:1:0')
        self.assertEqual(rewrite_effect_frames(value,{'102':'850000002'},legacy=True),value)

    def test_effect_file_alias_preserves_internal_animation_identity(self):
        maps={t:{}for t in ('F_ABILITY_MST','F_MAGIC_MST','F_LIMITBURST_MST','F_EFFECT_GROUP_MST')}
        row={'h5t4yBm2':'123','2HjxCGo6':'MAY17_reberta_lb5_hit.bmb','o2ye8th6':'MAY17_reberta_lb5_hit'}
        result,pending=rewrite_row('F_EFFECT_MST',row,maps,
            {'F_EFFECT_MST':{'key':'h5t4yBm2'}},
            {'MAY17_reberta_lb5_hit.bmb':'jp_reberta_originalfx.bmb'})
        self.assertEqual(result['2HjxCGo6'],'jp_reberta_originalfx.bmb')
        self.assertEqual(result['o2ye8th6'],row['o2ye8th6'])
        self.assertEqual(row['2HjxCGo6'],'MAY17_reberta_lb5_hit.bmb')
        self.assertFalse(pending)

    def test_binary_resource_rebinding_keeps_offsets_and_whole_names(self):
        raw=b'IBMB\x00tex_beta\x00other_tex_beta\x00tex_beta.png\x00\xff\x00'
        changed,edits=replacement(raw,{'tex_beta.png':'j1234567.png'})
        self.assertEqual(len(raw),len(changed))
        self.assertEqual(changed,b'IBMB\x00j1234567\x00other_tex_beta\x00j1234567.png\x00\xff\x00')
        self.assertEqual(len(edits),2)
        self.assertEqual(raw[-2:],changed[-2:])

    def test_passive_and_active_opcode100_have_different_child_positions(self):
        mapping = {'514360': '830000001', '505580': '830000002'}
        value, pending = effect_parameters({'2kq0BpnD': '100',
            'Ha9G5sCS': '514360,1,0,0'}, mapping, {})
        self.assertEqual(value, '830000001,1,0,0')
        self.assertFalse(pending)
        value, pending = effect_parameters({'2kq0BpnD': '100',
            'Ha9G5sCS': '2&2,505580&505590,9999,2,1'}, mapping, {})
        self.assertEqual(value, '2&2,830000002&505590,9999,2,1')
        self.assertFalse(pending)

    def test_multicast_include_exclude_and_button_references(self):
        value, pending = effect_parameters({'2kq0BpnD': '102',
            'Ha9G5sCS': '5,214410&502120,1189011,3,1189011,0'},
            {'214410': '830000001', '1189011': '830000002'}, {})
        self.assertEqual(value, '5,830000001&502120,830000002,3,830000002,0')
        self.assertFalse(pending)

    def test_ordinary_numeric_effect_values_are_not_rewritten(self):
        params = '1,0,100020,0'
        value, pending = effect_parameters({'2kq0BpnD': '1', 'Ha9G5sCS': params},
                                           {'100020': '830000001'}, {})
        self.assertEqual(value, params)
        self.assertEqual(pending[0]['ids'], ['100020'])

    def test_bound_stmr_moogle_tracks_target_unit(self):
        value = rewrite_rewards('10:906000103:1:100:1:0:0:0:1346000107',
            {'F_UNIT_MST': {'346000107': '820001107'}})
        self.assertEqual(value, '10:906000103:1:100:1:0:0:0:1820001107')

    def test_final_contract_keeps_global_duran_and_angela(self):
        contract = json.loads((HOME / 'Sources/native-unit-import.json').read_text('utf-8'))
        units = next(t['rows'] for t in contract['tables'] if t['table'] == 'F_UNIT_MST')
        targets = {r['3HriTp6B'] for r in units}
        self.assertFalse(targets & {'312000517', '312000527', '312000617', '312000627'})
        self.assertEqual(len(contract['mappings']['F_UNIT_MST']), 10)
        self.assertFalse(contract['unresolved_references'])


if __name__ == '__main__':
    unittest.main()
