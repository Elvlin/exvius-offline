"""Verify restored field graphs against the original typed event scripts."""
import json
import re
import hashlib
from pathlib import Path
import sys
import unittest
from collections import Counter, defaultdict

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / p) for p in ('source/server','source/exvius','custom-engine/tools')]
import battle_content
from cpk import Cpk
from player_state import _load_ndjson, mission_row
from repair_field_scenarios import MERMAID_LANTERNS, NIAN_REGULAR, NIAN_CAPTURE, NIAN_BONUS, script_scenarios




class FieldScenarioRepairTests(unittest.TestCase):
    def test_touched_native_id_localizations_retain_original_english_names(self):
        document = json.loads((ROOT/'source/server/event_encounters.json').read_text(encoding='utf8'))
        original = {r['key'].rsplit('_',1)[-1]:r['v'][0]for r in map(json.loads,
            (ROOT/'data/text_decoded/F_TEXT_MONSTER_NAME.ndjson').read_text(encoding='utf8').splitlines())}
        checked = set()
        for entry in document['missions'].values():
            if not entry.get('field_scenario_reconstruction'):continue
            for row in entry['bundle'].get('wbet57nF',[]):
                iid = row['xqartN26']
                expected = original.get(iid,row['G4L0YIB2'])
                self.assertEqual(document['local_monster_names'][iid],expected)
                self.assertEqual(document['local_monster_names'][iid+'A'],expected)
                checked.add(iid)
        self.assertTrue(checked)

    def test_tantarian_own_ai_ciphertext_and_pair_index_preserve_original_master(self):
        from decode_client_data import client_manifest, decode
        from native_master_index import build_index
        content = json.loads((ROOT/'source/server/content/battle/ai_repairs.json').read_text(encoding='utf8'))
        rule = content['tables']['F_AI_MST']['rows'][0]
        self.assertEqual((rule['8a6gAwN9'],rule['w7VR6ypY']),('204171001','1'))
        self.assertTrue(rule['z5hB3P01'].startswith('attack@'))
        self.assertEqual(rule['9Fe2mBtK'],'non')
        info = next(v for v in client_manifest(ROOT/'repository snapshots/FFBE-Global-v9.0.0-original.apk').values()
                    if v['table']=='F_AI_MST')
        original = (ROOT/'data/client/files/mst/Ver335_PCm9K3no.dat').read_bytes()
        patched = (ROOT/'data/overlay/mst/Ver335_PCm9K3no.dat').read_bytes()
        self.assertTrue(patched.startswith(original))
        _, new_rows = decode(patched[len(original):],info['key'])
        self.assertEqual(new_rows,[rule])
        self.assertEqual(build_index('F_AI_MST',patched,info['key'],335),
                         (ROOT/'data/overlay/mst/PCm9K3no.i').read_bytes())
        for entry in content['native_overlay']['files']:
            self.assertEqual(hashlib.sha256((ROOT/'data/overlay'/entry['path']).read_bytes()).hexdigest(),entry['sha256'])
        p = next(r for r in battle_content.field_mission_bundle({},mission_row('7540101'))['bV34YIJQ']
                 if r['xqartN26']=='204171001')
        self.assertEqual((p['8a6gAwN9'],p['A5x02C6a'],p['4Y2DGP7m']),('204171001','204171001','6,6'))
        self.assertEqual(tuple(p[t]for t in ('fh31sk7B','PC97pWQj','9NBV1XCS','Pn5w9dfh','84FJM3PD','T8xMDAZ4')),
                         ('5000000','10000','650','100','500','80'))

    def test_tantarian_guaranteed_ticket_reward_uses_own_scenario_and_currency(self):
        bundle = battle_content.field_mission_bundle({},mission_row('7540101'))
        drops = [r for r in bundle['JR7jZci2']if r.get('9BetM2Ds')]
        self.assertEqual(len(drops),1)
        row = drops[0]
        self.assertEqual(tuple(row[t]for t in ('ja07xgLF','2fY1IomW','xqartN26','Z0EN6jSh','6Yc4RkdM')),
                         ('7540105','754010113','204171001','1','1'))
        self.assertEqual(row['9BetM2Ds'],'20:106303100:200:100')
        self.assertTrue(all(not r['9BetM2Ds']for r in bundle['6v0LPiRe']))
        medals = _load_ndjson('F_MEDAL_EXCHANGE_MST.ndjson','S21FT3L8')
        stock = _load_ndjson('F_STORE_ITEM_MST.ndjson')['__rows__']
        owned = [medals[r['6uIYE15X']]for r in stock if r['Z20mNDvL']=='900125'
                 and r.get('6uIYE15X')in medals]
        self.assertTrue(owned)
        self.assertEqual({r['ak2dhKm3']for r in owned},{'106303100'})
        self.assertTrue({'21:404002300:1:100','21:409014700:1:100'} <= {r['7iJpH5zZ']for r in owned})

    def test_dreadnought_beginner_remains_documented_boss_only(self):
        reference = json.loads((ROOT / 'logs/reference/field-scenario-wiki-20261109.json').read_text(encoding='utf8'))
        from reconstruct_event_battles import templates, fields
        first = fields(next(templates(reference['pages']['The Dreadnought'],'Battle Infobox'))[1])
        self.assertEqual((first['battle'].strip(),first['unit-exp'].strip(),first['gil'].strip()),('1','300','30'))
        bundle = battle_content.field_mission_bundle({},mission_row('7130101'))
        self.assertEqual(bundle['6v0LPiRe'],[])
        self.assertFalse(bundle.get('an6TB4WS'))
        self.assertFalse(bundle.get('y35YvQjZ'))

    def test_dreadnought_four_progressive_zone_samples_match_primary_columns(self):
        from reconstruct_event_battles import templates, fields
        reference = json.loads((ROOT / 'logs/reference/field-scenario-wiki-20261109.json').read_text(encoding='utf8'))
        boxes = [fields(t)for _,t in templates(reference['pages']['The Dreadnought'],'Battle Infobox')]
        english = {r['key'].rsplit('_',1)[-1]:r['v'][0]for r in map(json.loads,
            (ROOT/'data/text_decoded/F_TEXT_MONSTER_NAME.ndjson').read_text(encoding='utf8').splitlines())}
        for tier in range(1,5):
            mid = str(7130101+tier)
            with self.subTest(mission=mid):
                bundle = battle_content.field_mission_bundle({},mission_row(mid))
                rows = bundle['6v0LPiRe']
                self.assertEqual({r['YzGa63QM']for r in rows},
                                 {str(110+10*i)for i in range(tier+1)})
                published = boxes[tier]['monster'].split('----')[1]
                columns = [Counter()for _ in range(tier+1)]
                for match in re.finditer(r'\[\[([^]]+)\]\]([^<\n]+)',published):
                    name = match[1].split('|')[-1]
                    for column,count in enumerate(map(int,re.findall(r'\((\d+)\)',match[2]))):
                        columns[column][name] = count
                for column,expected in enumerate(columns):
                    actual = Counter(english[r['xqartN26']]for r in rows
                                     if r['YzGa63QM']==str(110+10*column))
                    self.assertEqual(actual,expected)
                counters = defaultdict(set)
                for r in rows:
                    self.assertEqual(r['qo3PECw6'],mid)
                    self.assertLess(int(r['2fY1IomW'][-2:]),80)
                    counters[r['YzGa63QM'],r['2fY1IomW']].add(int(r['h4Sjf96p']))
                self.assertEqual(sum(map(len,counters.values())),(20,25,30,34)[tier-1])
                for occurrences in counters.values():self.assertEqual(occurrences,set(range(len(occurrences))))
                p = {r['xqartN26']:r for r in bundle['bV34YIJQ']}
                boss = [r['xqartN26']for r in bundle['Bi6hVv34']
                        if r['2fY1IomW']==mid+'90' and r['WJdBp9f0']=='1']
                exp = sum(int(p[r['xqartN26']]['B6H34Mea'])for r in rows)+sum(int(p[i]['B6H34Mea'])for i in boss)
                gil = sum(int(p[r['xqartN26']]['7UR4J2SE'])for r in rows)+sum(int(p[i]['7UR4J2SE'])for i in boss)+int(mission_row(mid)['7UR4J2SE'])
                self.assertEqual(exp,(6230,11300,29750,49350)[tier-1])
                self.assertEqual(gil,(822,2933,4650,6867)[tier-1])
                if tier == 4:
                    hidden = [r for r in bundle['Bi6hVv34']if r['2fY1IomW']==mid+'90' and r['WJdBp9f0']=='0']
                    self.assertEqual({r['Z0EN6jSh']for r in hidden},{'4','5','6','7'})
                    self.assertTrue(all(r['xqartN26']=='205302005'for r in hidden))
                    skills = {r['6E5u1xrs']:r for r in bundle['Wp39QX52']}
                    for slot,sid in zip(range(4,8),('156960','156970','156980','156990')):
                        self.assertEqual(skills[sid]['2kq0BpnD'],'87')
                        self.assertTrue(skills[sid]['Ha9G5sCS'].startswith('1,'+str(slot)+','))
                    # The guide's minimum includes two actual summons. Their
                    # reward remains conditional on the unchanged native AI.
                    exp += 2*int(p['205302005']['B6H34Mea'])
                    gil += 2*int(p['205302005']['7UR4J2SE'])
                for value,source in ((exp,boxes[tier]['unit-exp']),(gil,boxes[tier]['gil'])):
                    lower,upper = map(int,source.split('-'))
                    self.assertLessEqual(lower,value)
                    self.assertLessEqual(value,upper)

    def test_exact_typed_cross_stage_bindings_supply_complete_original_groups(self):
        from repair_field_group_bindings import candidates
        document = json.loads((ROOT / 'source/server/content/field_group_bindings.json').read_text(encoding='utf8'))
        original = {(mid, gid, json.dumps(evidence, sort_keys=True))
                    for mid, gid, evidence in candidates()}
        links = document['typed_scenario_links']
        self.assertTrue(links)
        for mid, references in links.items():
            with self.subTest(mission=mid):
                bundle = battle_content.field_mission_bundle({}, mission_row(mid))
                self.assertFalse(bundle.get('an6TB4WS'))
                self.assertFalse(bundle.get('y35YvQjZ'))
                monsters = {row['xqartN26'] for row in bundle.get('wbet57nF', [])}
                parts = {row['xqartN26'] for row in bundle.get('bV34YIJQ', [])}
                for evidence in references:
                    gid = evidence['group']
                    self.assertIn((mid, gid, json.dumps(evidence, sort_keys=True)), original)
                    self.assertIn(gid, document['missions'][mid])
                    slots = [row for row in bundle['Bi6hVv34'] if row['2fY1IomW'] == gid]
                    self.assertTrue(slots)
                    self.assertTrue({row['xqartN26'] for row in slots} <= monsters & parts)

    def test_original_own_event_scenarios_resolve_for_all_29_missions(self):
        resources = _load_ndjson('F_RESOURCE_MAP_MST.ndjson','Nnb20keZ')
        versions = _load_ndjson('F_RESOURCE_MAP_VERSION_MST_LOCALIZE.ndjson','Nnb20keZ')
        missions = [str(i) for a,b in ((9000701,9000721),(9002001,9002004),(610010100,610010103)) for i in range(a,b+1)]
        for mid in missions:
            with self.subTest(mission=mid):
                mission = mission_row(mid)
                event = next(resources[rid] for rid in mission['q4f9IdMs'].split(',')
                             if rid in resources and resources[rid].get('drE35YcF') == 'event')
                version = versions[event['Nnb20keZ']]['OzT5lSz3']
                relative = 'common_lang/sd/' + event['3LHdc6Qa'] + '/Ver' + version + '_' + event['pJ56sAEo']
                path = next(ROOT / folder / relative for folder in ('data/overlay','data/client/files')
                            if (ROOT / folder / relative).is_file())
                pack = Cpk(path.read_bytes())
                # Select this declared event's own file. Cumulative packages
                # also retain earlier unrelated members; they are not ownership.
                member = Path(event['pJ56sAEo']).stem + '_event.bin'
                wanted = script_scenarios(pack.read(member))
                self.assertTrue(wanted)
                bundle = battle_content.field_mission_bundle({},mission)
                masters = {r['ja07xgLF'] for r in bundle['rqxw0p9k']}
                groups = {r['ja07xgLF']:r['2fY1IomW'] for r in bundle['YjHhvN65']}
                self.assertTrue(wanted <= masters & groups.keys())
                self.assertNotIn('an6TB4WS',bundle)
                self.assertNotIn('y35YvQjZ',bundle)
                for sid in wanted:
                    slots = [r for r in bundle['Bi6hVv34'] if r['2fY1IomW']==groups[sid]]
                    self.assertTrue(slots)
                    actors = {r['xqartN26'] for r in slots}
                    self.assertTrue(actors <= {r['xqartN26'] for r in bundle['wbet57nF']})
                    self.assertTrue(actors <= {r['xqartN26'] for r in bundle['bV34YIJQ']})

    def test_original_nian_identity_ai_skills_and_tier_resistances(self):
        bundle = battle_content.field_mission_bundle({},mission_row('9000701'))
        bosses = {str(i) for i in range(900010178,900010181)}
        self.assertEqual({r['xqartN26']:r['V9j8wJcC'] for r in bundle['wbet57nF'] if r['xqartN26'] in bosses},
                         {str(i):'10000006' for i in range(900010178,900010181)})
        for p in (p for p in bundle['bV34YIJQ'] if p['xqartN26'] in bosses):
            self.assertEqual((p['8a6gAwN9'],p['A5x02C6a']),('900000009','900000009'))
            self.assertLess(int(p['T8xMDAZ4']),100)
        self.assertTrue({'900031','900021','900022','120210','900032','900033','900026'} <=
                        {r['6E5u1xrs'] for r in bundle['Wp39QX52']})
        self.assertTrue(all(not r['9BetM2Ds'] for r in bundle['JR7jZci2']))

    def test_nian_21_own_zone_finite_encounters_dependencies_and_published_rewards(self):
        # Audit captures the original own-zone parser result, not a guessed
        # zone based on a cumulative package's unrelated map members.
        audit = json.loads((ROOT / 'logs/ffbe-field-channel-audit-20261109.json').read_text(encoding='utf8'))
        records = audit if isinstance(audit,list) else audit['missions']
        owned = {r['mission']:r['own_external_positive_fields'] for r in records}
        for index in range(21):
            mid, tier = str(9000701+index), index % 3
            with self.subTest(mission=mid):
                bundle = battle_content.field_mission_bundle({},mission_row(mid))
                allocations = bundle['6v0LPiRe']
                self.assertTrue(allocations)
                self.assertEqual({r['qo3PECw6'] for r in allocations},{mid})
                self.assertEqual({r['YzGa63QM'] for r in allocations},{'10'})
                self.assertIn('10',owned[mid])
                parts = {r['xqartN26']:r for r in bundle['bV34YIJQ']}
                monsters = {r['xqartN26']:r for r in bundle['wbet57nF']}
                groups = defaultdict(dict)
                for row in allocations:
                    groups[row['2fY1IomW']].setdefault(int(row['h4Sjf96p']),[]).append(row)
                    self.assertIn(row['xqartN26'],parts)
                    self.assertIn(row['xqartN26'],monsters)
                    self.assertIn((row['2fY1IomW'],row['Z0EN6jSh'],row['xqartN26']),
                        {(r['2fY1IomW'],r['Z0EN6jSh'],r['xqartN26']) for r in bundle['Bi6hVv34']})
                # Each native group consumes occurrence0..N-1. There is no
                # row for its next occurrence and no scripted boss in pool.
                self.assertEqual(sum(len(counters) for counters in groups.values()),16)
                for counters in groups.values():
                    self.assertEqual(set(counters),set(range(len(counters))))
                    self.assertNotIn(len(counters),counters)
                roster = Counter(monsters[r['xqartN26']]['G4L0YIB2'] for r in allocations
                                 if r['xqartN26'] not in NIAN_CAPTURE)
                self.assertEqual(roster,{'Wolf':6,'Purusa':8,'Coeurl':8,'Wild Rat':6,'Poison Toad':6,'Adamantoise':4})
                self.assertFalse(any(900010178 <= int(r['xqartN26']) <= 900010180 for r in allocations))
                for species, (name,_,ai,skillset,_,profiles) in enumerate(NIAN_REGULAR):
                    iid = str(900010181+tier*6+species)
                    p = parts[iid]
                    self.assertEqual(monsters[iid]['G4L0YIB2'],name)
                    self.assertEqual(tuple(int(p[t]) for t in ('7wV3QZ80','fh31sk7B','PC97pWQj','B6H34Mea','7UR4J2SE')),profiles[tier])
                    self.assertEqual((p['8a6gAwN9'],p['A5x02C6a']),(ai,skillset))
                captures = [r['Vf5DGw07'] for r in allocations if r['Vf5DGw07']]
                self.assertEqual(set(captures),{'10:'+NIAN_CAPTURE[iid]+':1' for iid in NIAN_BONUS[tier]})
                self.assertEqual(len(captures),2)
                exp = sum(int(parts[r['xqartN26']]['B6H34Mea']) for r in allocations)+4000
                gil = sum(int(parts[r['xqartN26']]['7UR4J2SE']) for r in allocations)+400+int(mission_row(mid)['7UR4J2SE'])
                self.assertEqual(exp,(11708,11718,11728)[tier])
                self.assertEqual(gil,(987,1027,1077)[tier])
                self.assertNotIn('an6TB4WS',bundle)
                self.assertNotIn('y35YvQjZ',bundle)

    def test_mermaid_native_event_skills_and_repeatable_lanterns(self):
        for i,count in enumerate(MERMAID_LANTERNS):
            with self.subTest(tier=i):
                bundle = battle_content.field_mission_bundle({},mission_row(str(9002001+i)))
                self.assertEqual(len(bundle['bV34YIJQ']),1)
                p = bundle['bV34YIJQ'][0]
                self.assertEqual((p['xqartN26'],p['8a6gAwN9'],p['A5x02C6a']),
                                 (str(900010319+5*i),'900000021','900000030'))
                self.assertEqual({r['6E5u1xrs'] for r in bundle['Wp39QX52']},
                                 {str(s) for s in range(900099,900104)})
                self.assertEqual([r['9BetM2Ds'] for r in bundle['JR7jZci2']],
                                 ['20:1209000836:'+str(count)+':100'])

    def test_classic_crystal_tower_finite_original_formations_and_published_totals(self):
        source = battle_content.IndexSource()
        original_groups = source.load('F_BATTLE_GROUP_MST')
        original_monsters = {r['xqartN26']:r for r in source.load('F_MONSTER_MST')}
        original_parts = {r['xqartN26']:r for r in source.load('F_MONSTER_PARTS_MST')}
        bosses = (3,4,5,6,7)
        expected = (({'105063000':23},15,2600,99),
            ({'105063001':18,'312021001':6},18,6680,359),
            ({'105063002':15,'312021002':5,'205231001':5},20,11900,753),
            ({'105063003':30,'312021003':5,'205231002':15,'205221001':5,'407043000':2},27,41000,2560),
            ({'105063004':35,'312021004':6,'205231003':16,'205221002':5,'204034001':10,
              '407042000':2,'407043000':2,'407041000':1},38,75500,5097))
        for tier,(roster,count,exp,gil) in enumerate(expected):
            mid = str(7070101+tier)
            with self.subTest(mission=mid):
                bundle = battle_content.field_mission_bundle({},mission_row(mid))
                rows = bundle['6v0LPiRe']
                self.assertEqual(Counter(r['xqartN26'] for r in rows),roster)
                self.assertEqual({(r['qo3PECw6'],r['YzGa63QM'])for r in rows},{(mid,'10')})
                counters = defaultdict(set)
                for r in rows:
                    counters[r['2fY1IomW']].add(int(r['h4Sjf96p']))
                    self.assertEqual(r['Vf5DGw07'],'')
                self.assertEqual(sum(map(len,counters.values())),count)
                for occurrences in counters.values():
                    self.assertEqual(occurrences,set(range(len(occurrences))))
                    self.assertNotIn(len(occurrences),occurrences)
                boss = mid+str(bosses[tier]).zfill(2)
                self.assertNotIn(boss,counters)
                groups = [r for r in original_groups if r['2fY1IomW'].startswith(mid)]
                self.assertTrue(all(r in bundle['Bi6hVv34']for r in groups))
                p = {r['xqartN26']:r for r in bundle['bV34YIJQ']}
                for r in bundle['wbet57nF']:
                    self.assertEqual(r,original_monsters[r['xqartN26']])
                for r in bundle['bV34YIJQ']:
                    source_part = original_parts[r['xqartN26']]
                    self.assertEqual(r,{t:source_part.get(t,battle_content.PARTS_DEFAULTS.get(t,''))
                                        for t in battle_content.PARTS_TOKENS})
                boss_members = [r['xqartN26'] for r in groups if r['2fY1IomW']==boss and r['WJdBp9f0']=='1']
                self.assertTrue(boss_members)
                self.assertEqual(sum(int(p[r['xqartN26']]['B6H34Mea']) for r in rows)+
                                 sum(int(p[i]['B6H34Mea'])for i in boss_members),exp)
                self.assertEqual(sum(int(p[r['xqartN26']]['7UR4J2SE']) for r in rows)+
                                 sum(int(p[i]['7UR4J2SE'])for i in boss_members)+int(mission_row(mid)['7UR4J2SE']),gil)
                self.assertNotIn('an6TB4WS',bundle)
                self.assertNotIn('y35YvQjZ',bundle)

    def test_lands_original_seven_boss_scenarios_and_full_bgn_formation(self):
        bundle = battle_content.field_mission_bundle({},mission_row('610010100'))
        self.assertEqual({r['ja07xgLF'] for r in bundle['YjHhvN65']},
                         {str(s) for s in range(610010100,610010107)})
        group = next(r['2fY1IomW'] for r in bundle['YjHhvN65'] if r['ja07xgLF']=='610010100')
        names = {r['xqartN26']:r['G4L0YIB2'] for r in bundle['wbet57nF']}
        from collections import Counter
        self.assertEqual(Counter(names[r['xqartN26']] for r in bundle['Bi6hVv34']
                                 if r['2fY1IomW']==group),{'Goblin':4,'Goblin Guard':1})
        by_name = {r['G4L0YIB2']:r for r in bundle['bV34YIJQ']}
        self.assertEqual(by_name['Amoebozoa']['fh31sk7B'],'50000')
        self.assertEqual(by_name['Ogre']['fh31sk7B'],'98000')

    def test_macalania_finite_random_groups_preserve_scripted_butterflies(self):
        expected = (({'109041000':18},12,{'726010103':1,'726010104':1},910,123),
            ({'109041001':13,'208061001':6},15,{'726010204':1},4600,272),
            ({'109041002':12,'208061002':6,'209041001':6},18,
             {'726010304':1,'726010305':2},18600,973),
            ({'201111001':12,'209041002':24},20,{'726010406':1,'726010407':3},33200,1830),
            ({'201111002':32,'209041003':24,'301061001':4},24,
             {'726010507':1,'726010508':5,'726010509':2},95000,6367))
        for tier,(roster,count,scripted,exp,gil) in enumerate(expected):
            mid = str(7260101+tier)
            with self.subTest(mission=mid):
                bundle = battle_content.field_mission_bundle({},mission_row(mid))
                rows = bundle['6v0LPiRe']
                self.assertEqual(Counter(r['xqartN26']for r in rows),roster)
                self.assertEqual({(r['qo3PECw6'],r['YzGa63QM'])for r in rows},{(mid,'10')})
                counters = defaultdict(set)
                for r in rows:
                    counters[r['2fY1IomW']].add(int(r['h4Sjf96p']))
                    self.assertEqual(r['9BetM2Ds'],'')
                self.assertEqual(sum(map(len,counters.values())),count)
                self.assertFalse(counters.keys() & scripted.keys())
                for occurrences in counters.values():
                    self.assertEqual(occurrences,set(range(len(occurrences))))
                p = {r['xqartN26']:r for r in bundle['bV34YIJQ']}
                script_members = [r['xqartN26'] for gid,times in scripted.items()
                    for r in bundle['Bi6hVv34'] if r['2fY1IomW']==gid and r['WJdBp9f0']=='1'
                    for _ in range(times)]
                self.assertEqual(len(script_members),sum(scripted.values()))
                self.assertEqual(sum(int(p[r['xqartN26']]['B6H34Mea'])for r in rows)+
                                 sum(int(p[i]['B6H34Mea'])for i in script_members),exp)
                self.assertEqual(sum(int(p[r['xqartN26']]['7UR4J2SE'])for r in rows)+
                    sum(int(p[i]['7UR4J2SE'])for i in script_members)+int(mission_row(mid)['7UR4J2SE']),gil)
                self.assertNotIn('an6TB4WS',bundle)
                self.assertNotIn('y35YvQjZ',bundle)

    def test_babil_finite_original_formations_all_tier_species_and_reward_totals(self):
        expected = (({'206061000':12,'206071000':12},15,(6,),2700,102),
            ({'206061001':18,'206071001':18},18,(4,5),8202,442),
            ({'206061002':26,'206051000':16,'206071002':8},20,(7,8,9),19500,1373),
            ({'206061003':27,'206051001':15,'206071003':24},25,(9,10,11,12),34400,2970),
            ({'206061004':35,'206051002':18,'206071004':27},30,(9,10,11,12,13),64000,5917))
        for tier,(roster,count,script_suffixes,exp,gil) in enumerate(expected):
            mid = str(7050101+tier)
            with self.subTest(mission=mid):
                bundle = battle_content.field_mission_bundle({},mission_row(mid))
                rows = bundle['6v0LPiRe']
                self.assertEqual(Counter(r['xqartN26']for r in rows),roster)
                self.assertEqual({(r['qo3PECw6'],r['YzGa63QM'])for r in rows},{(mid,'10')})
                counters = defaultdict(set)
                for r in rows:counters[r['2fY1IomW']].add(int(r['h4Sjf96p']))
                self.assertEqual(sum(map(len,counters.values())),count)
                for occurrences in counters.values():self.assertEqual(occurrences,set(range(len(occurrences))))
                scripted = {mid+str(i).zfill(2)for i in script_suffixes}
                self.assertFalse(counters.keys() & scripted)
                p = {r['xqartN26']:r for r in bundle['bV34YIJQ']}
                boss_members = [r['xqartN26'] for r in bundle['Bi6hVv34']
                                if r['2fY1IomW'] in scripted and r['WJdBp9f0']=='1']
                self.assertEqual(len(boss_members),tier+1)
                self.assertEqual(sum(int(p[r['xqartN26']]['B6H34Mea'])for r in rows)+
                                 sum(int(p[i]['B6H34Mea'])for i in boss_members),exp)
                self.assertEqual(sum(int(p[r['xqartN26']]['7UR4J2SE'])for r in rows)+
                    sum(int(p[i]['7UR4J2SE'])for i in boss_members)+int(mission_row(mid)['7UR4J2SE']),gil)

    def test_paired_source_constrained_fields_original_profiles_and_totals(self):
        expected = (
            ('7030101','10',14,'703010106',{'205061000':11,'205081000':12},2750,139),
            ('7030102','10',25,'703010206',{'205061002':15,'205081002':20,'205071000':15},13600,1461),
            ('7030103','10',29,'703010307',{'205061004':24,'205081004':26,'205071002':25},52250,6855),
            ('7450101','10',30,'745010108',{'205581005':20,'106061000':8,'201142003':9,'201141004':9,'206131002':5},112600,11887),
            ('7450102','10',10,'745010112',{'205581006':7,'106051006':6},590,79),
            ('7490102','10',29,'749010110',{'203091006':33,'104051006':33},8090,829),
            ('7540101','12',29,'754010108,754010113',{'205631005':20,'205651005':12,'205641004':24,'102061000':16,'201161002':2},165900,17447),
            ('7540102','12',18,'754010112',{'205631006':12,'205651006':12},920,112),
            ('7590101','11',30,'759010101',{'206141006':33,'211041006':16,'201171004':6,'206151003':16,'205681002':10},175600,18550),
            ('7590102','11',15,'759010201',{'206141005':12,'211041005':12},920,112),
            ('7690101','11',30,'769010101',{'111111007':19,'203101007':27,'203111005':29,'307071004':6},175600,18600),
            ('7690102','11',15,'769010201',{'111111006':12,'203101006':12},920,112),
            ('7790101','10',20,'779010101',{'201181009':10,'103151005':13,'209081000':20,'204181004':8,'407101000':1},118100,12600),
            ('7790102','10',10,'779010201',{'201181008':25},950,115),
            ('8000101','11',27,'800010101',{'105191008':30,'101071006':21,'203121004':9,'203131003':12},156700,16620),
            ('8000102','11',9,'800010201',{'105191007':9,'101071005':12},830,103),
            ('7950102','11',9,'795010201',{'204201007':9,'310011005':12},830,103))
        source = battle_content.IndexSource()
        original_parts = {r['xqartN26']:r for r in source.load('F_MONSTER_PARTS_MST')}
        original_groups = source.load('F_BATTLE_GROUP_MST')
        for mid,field,count,boss,roster,exp,gil in expected:
            with self.subTest(mission=mid):
                bundle = battle_content.field_mission_bundle({},mission_row(mid))
                rows = bundle['6v0LPiRe']
                self.assertEqual(Counter(r['xqartN26']for r in rows),roster)
                self.assertEqual({(r['qo3PECw6'],r['YzGa63QM'])for r in rows},{(mid,field)})
                counters = defaultdict(set)
                for r in rows:
                    counters[r['2fY1IomW']].add(int(r['h4Sjf96p']))
                    self.assertIn(next(x for x in original_groups if x['2fY1IomW']==r['2fY1IomW']
                        and x['Z0EN6jSh']==r['Z0EN6jSh']),bundle['Bi6hVv34'])
                self.assertEqual(sum(map(len,counters.values())),count)
                for group in boss.split(','):self.assertNotIn(group,counters)
                for occurrences in counters.values():self.assertEqual(occurrences,set(range(len(occurrences))))
                p = {r['xqartN26']:r for r in bundle['bV34YIJQ']}
                for iid in roster:
                    self.assertEqual(p[iid],{t:original_parts[iid].get(t,battle_content.PARTS_DEFAULTS.get(t,''))
                                            for t in battle_content.PARTS_TOKENS})
                boss_members = [r['xqartN26']for r in bundle['Bi6hVv34']if r['2fY1IomW'] in boss.split(',') and r['WJdBp9f0']=='1']
                self.assertEqual(len(boss_members),3 if mid.startswith('70301') else 2 if mid=='7540101' else 1)
                self.assertEqual(sum(int(p[r['xqartN26']]['B6H34Mea'])for r in rows)+sum(int(p[i]['B6H34Mea'])for i in boss_members),exp)
                self.assertEqual(sum(int(p[r['xqartN26']]['7UR4J2SE'])for r in rows)+
                                 sum(int(p[i]['7UR4J2SE'])for i in boss_members)+int(mission_row(mid)['7UR4J2SE']),gil)


if __name__ == '__main__':
    unittest.main()
