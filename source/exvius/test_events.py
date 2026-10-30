import calendar
import time
import json
import sys
import tempfile
import unittest
from pathlib import Path
sys.path[:0]=[str(Path(__file__).resolve().parent),str(Path(__file__).resolve().parents[1]/'server')]
from exvius_events import load_policy,save_policy,apply_availability,event_facts,native_gate_dates
from preflight import audit

class Events(unittest.TestCase):
    def test_archive_groups_duplicate_tiles_without_dropping_stages(self):
        from event_archive import events, listings, menu
        original = {str(row['area']): row for row in events()}
        groups = listings()
        covered = [str(row['area']) for row, _aliases in groups]
        covered.extend(alias for _row, aliases in groups for alias in aliases)
        self.assertEqual(len(covered), len(set(covered)))
        self.assertEqual(set(covered), set(original))
        self.assertEqual(
            {mid for area in covered for mid in original[area]['missions']},
            {mid for row in events() for mid in row['missions']})
        result = menu(None, '')
        all_group = next(row for row in result['groups'] if row['id'] == 'all')
        self.assertEqual(all_group['count'], len(groups))
        vault = [(row, aliases) for row, aliases in groups if row['name'] == 'Vault of Hidden Treasures']
        self.assertEqual(len(vault), 1)
        self.assertEqual(len(vault[0][1]), 11)

    def test_selection_survives_reload_and_backup(self):
        with tempfile.TemporaryDirectory() as d:
            save_policy(d,{'version':1,'areas':[970,970,888],'permanent':True})
            self.assertEqual(load_policy(d)['areas'],['970','888'])
            save_policy(d,{'version':1,'areas':[888],'permanent':False})
            self.assertEqual(load_policy(d)['areas'],['888'])
            self.assertEqual(len(list((Path(d)/'state').glob('*.backup-*'))),1)
    def test_explicit_empty_not_defaulted(self):
        with tempfile.TemporaryDirectory() as d:
            save_policy(d,{'version':1,'areas':[],'permanent':True})
            self.assertEqual(load_policy(d,[970])['areas'],[])
    def test_bad_policy_not_silently_defaulted(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'state/exvius_events.json';p.parent.mkdir();p.write_text('{bad')
            with self.assertRaises(ValueError):load_policy(d,[970])
    def test_existing_expired_row_extended_only_selected(self):
        source={'0xkoNP8U':[{'uv60hgDW':'970','m8ivD4NX':'1','other':'keep'}, {'uv60hgDW':'888','m8ivD4NX':'2'}]}
        out=apply_availability(source,{'version':1,'areas':[970],'permanent':True},now=2000000000)
        self.assertGreater(calendar.timegm(time.strptime(out['0xkoNP8U'][0]['m8ivD4NX'], '%Y-%m-%d %H:%M:%S')),2000000000)
        self.assertEqual(out['0xkoNP8U'][0]['other'],'keep')
        self.assertEqual(source['0xkoNP8U'][0]['m8ivD4NX'],'1')
        self.assertEqual(out['0xkoNP8U'][1],source['0xkoNP8U'][1])
    def test_rolling_window_and_unresolved_not_changed(self):
        source={'0xkoNP8U':[{'uv60hgDW':'970'}]};policy={'version':1,'areas':[970],'permanent':True}
        early=apply_availability(source,policy,100);late=apply_availability(source,policy,500)
        self.assertEqual(calendar.timegm(time.strptime(late['0xkoNP8U'][0]['m8ivD4NX'], '%Y-%m-%d %H:%M:%S'))-calendar.timegm(time.strptime(early['0xkoNP8U'][0]['m8ivD4NX'], '%Y-%m-%d %H:%M:%S')),400)
        self.assertEqual(apply_availability(source,policy,500,[]),source)
    def test_resolve_content_not_invented(self):
        facts,missing=event_facts([970,888],[{'uv60hgDW':'970','U9iHsau3':'d1'}],[{'U9iHsau3':'d1','qo3PECw6':'m1'}])
        self.assertEqual(facts,[{'area':'970','dungeon':'d1','first_mission':'m1'}])
        self.assertEqual(missing,[{'area':'888','missing':'dungeon'}])
    def test_native_gate_dates_preserve_captured_instants(self):
        source={'0xkoNP8U':[{'uv60hgDW':'226','VjJQ51uG':'1577836800','m8ivD4NX':'4102444800'}]}
        out=native_gate_dates(source)
        self.assertEqual(out['0xkoNP8U'][0]['VjJQ51uG'],'2020-01-01 00:00:00')
        self.assertEqual(out['0xkoNP8U'][0]['m8ivD4NX'],'2100-01-01 00:00:00')
        self.assertEqual(source['0xkoNP8U'][0]['VjJQ51uG'],'1577836800')
    def test_historical_policy_preserves_rows(self):
        source={'0xkoNP8U':[{'uv60hgDW':'970','m8ivD4NX':'1'}]}
        self.assertEqual(apply_availability(source,{'version':1,'areas':[970],'permanent':False}),source)

class Preflight(unittest.TestCase):
    def fixture(self,d):
        root=Path(d);bundle=root/'bundle';data=root/'data'
        (bundle/'server/content/battle').mkdir(parents=True);(bundle/'server_app').mkdir()
        for file,banners in [('gacha_catalogue.json',[{'id':1}]),('gacha_community.json',[{'id':2}]),('gacha_authored.json',[{'id':1}])]:
            (bundle/'server'/file).write_text(json.dumps({'banners':banners}))
        (bundle/'server/gacha_campaigns.json').write_text(json.dumps({'standard':[{'id':1}],'campaigns':{'test':{'banners':[{'id':2}]}}}))
        (bundle/'server_app/deps.json').write_text(json.dumps({'entries':[{'label':'MST','paths':['mst_decoded'],'min_files':2,'required':True}]}))
        (bundle/'server/content/battle/F_MISSION_MST.tsv').write_text('# comment\nqo3PECw6\tU9iHsau3\nm1\td1\n')
        (data/'mst_decoded').mkdir(parents=True)
        (data/'mst_decoded/F_DUNGEON_MST.ndjson').write_text(json.dumps({'uv60hgDW':'970','U9iHsau3':'d1'}))
        (data/'mst_decoded/F_MISSION_MST.ndjson').write_text(json.dumps({'U9iHsau3':'d1','qo3PECw6':'m1'}))
        return bundle,data
    def test_real_ids_and_chain_resolution(self):
        with tempfile.TemporaryDirectory() as d:
            b,r=self.fixture(d);result=audit(b,r,{'event_areas':[970]})
            self.assertEqual(result['banner_catalog_count'],2)
            self.assertTrue(result['resolved_event_chains'][0]['first_mission_in_battle_index'])
            self.assertTrue(result['ready_for_runtime_setup']);self.assertFalse(result['playable_verified'])
    def test_upstream_comment_header_schema(self):
        with tempfile.TemporaryDirectory() as d:
            b,r=self.fixture(d)
            (b/'server/content/battle/F_MISSION_MST.tsv').write_text('# {"fields":["qo3PECw6","U9iHsau3"]}\nm1\td1\n')
            result=audit(b,r,{'event_areas':[970]})
            self.assertEqual(result['battle_index_mission_count'],1)
            self.assertTrue(result['resolved_event_chains'][0]['first_mission_in_battle_index'])
    def test_unknown_selection_not_ready(self):
        with tempfile.TemporaryDirectory() as d:
            b,r=self.fixture(d);result=audit(b,r,{'event_areas':[970], 'banners':{'mode':'ids','ids':[999]}})
            self.assertEqual(result['unknown_banner_ids'],['999']);self.assertFalse(result['ready_for_runtime_setup'])
    def test_missing_event_not_ready(self):
        with tempfile.TemporaryDirectory() as d:
            b,r=self.fixture(d);result=audit(b,r,{'event_areas':[888]})
            self.assertFalse(result['ready_for_runtime_setup']);self.assertTrue(result['unresolved_event_chains'])
    def test_campaign_contains_standard(self):
        with tempfile.TemporaryDirectory() as d:
            b,r=self.fixture(d);result=audit(b,r,{'event_areas':[970], 'banners':{'mode':'campaign','campaign':'test'}})
            self.assertEqual(result['selected_banner_count'],2)
if __name__=='__main__':unittest.main()
