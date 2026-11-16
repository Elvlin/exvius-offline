"""Check calibrated enemy data, source preservation and native dependencies.

These are content checks. They do not execute the retired Python game runtime
and do not claim phone battle playback or original server fidelity.
"""
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import re
from statistics import median
import unittest

ROOT=Path(__file__).resolve().parents[2]
BASE=ROOT/'Japan content/Earlier JP crossovers/Sources/Battle recovery'
BACKUP=ROOT/'Trash/battle-data-backup/earlier-jp-enemy-refinement'
STATS={'HP':'fh31sk7B','MP':'PC97pWQj','ATK':'9NBV1XCS','DEF':'Pn5w9dfh',
       'MAG':'84FJM3PD','SPR':'T8xMDAZ4','level':'7wV3QZ80'}


def read(path):
    return json.loads(path.read_text(encoding='utf8'))


def nd(path):
    return [json.loads(line)for line in path.read_text(encoding='utf8').splitlines()if line.strip()]


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode('utf8')).hexdigest()


class CalibratedEnemies(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.receipt=read(BASE/'earlier-battle-reconstruction.json')
        cls.enemies={r['enemy_id']:r for r in cls.receipt['enemy_provenance']}
        cls.parts={(r['xqartN26'],r['6Yc4RkdM']):r for r in nd(BASE/'reconstructed-F_MONSTER_PARTS_MST.ndjson')}
        cls.behavior=read(BASE/'same-jp-unit-behaviors.json')
        cls.bundles=read(BASE/'reconstructed-event-encounters.json')['missions']
        cls.canonical=read(ROOT/'source/server/event_encounters.json')['missions']

    def test_original_sources_and_unrelated_content_unchanged(self):
        baseline=read(BACKUP/'preservation-baseline.json')
        for path,sha in baseline['original_source_hashes'].items():
            self.assertEqual(hashlib.sha256((ROOT/path).read_bytes()).hexdigest(),sha,path)
        self.assertEqual(digest({k:v for k,v in self.canonical.items()if k not in self.bundles}),baseline['unrelated_encounters_sha256'])
        fields=('an6TB4WS','Bi6hVv34','wbet57nF','y35YvQjZ','1IfDqR4n')
        for mid,sha in baseline['scoped_graph_rewards_sha256'].items():
            self.assertEqual(digest({f:self.bundles[mid]['bundle'].get(f)for f in fields}),sha,mid)

    def test_coverage_and_canonical_installation(self):
        self.assertEqual((len(self.enemies),len(self.parts),len(self.bundles)),(135,138,117))
        for mid,value in self.bundles.items():
            self.assertEqual(self.canonical[mid],value,mid)
        for part in self.parts.values():
            self.assertTrue(all(int(part[t])>0 for t in STATS.values()),part['xqartN26'])

    def test_published_values_and_tail_values_remain_exact(self):
        count=0
        for iid,row in self.enemies.items():
            exact=row.get('published_reference')
            if not exact:
                continue
            count+=1
            part=self.parts[iid,'1']
            for name,key in (('HP','hp'),('MP','mp'),('level','level')):
                if key in exact:
                    self.assertEqual(int(part[STATS[name]]),exact[key],(iid,name))
            if exact.get('tail'):
                tail=self.parts[iid,'2']
                self.assertEqual(int(tail[STATS['HP']]),exact['tail']['HP'])
                self.assertEqual(int(tail[STATS['MP']]),exact['tail']['MP'])
        self.assertEqual(count,27)

    def test_estimates_have_independent_donors_and_monotone_tiers(self):
        curves=defaultdict(list)
        for iid,row in self.enemies.items():
            trace=row['numeric_template']
            if 'same_JP_source_unit'in trace:
                continue
            donors=trace['cohort']['donors']
            self.assertGreaterEqual(len(donors),5,iid)
            self.assertEqual(len(donors),len({d['enemy']for d in donors}),iid)
            for name in STATS:
                self.assertEqual(trace['raw_cohort_medians'][name],max(1,round(median(d[name]for d in donors))),(iid,name))
            target=trace['target']
            curves[target['graphic'],tuple(target['areas'])].append((target['difficulty'],int(iid),self.parts[iid,'1']))
        for family,rows in curves.items():
            rows.sort(key=lambda r:(r[0],r[1]))
            for name,token in STATS.items():
                values=[int(r[2][token])for r in rows]
                self.assertEqual(values,sorted(values),(family,name))

    def test_daily_signature_skills_and_native_skillsets_resolve(self):
        skills={r['6E5u1xrs']:r for r in self.behavior['authored_skill_rows']}
        sets={r['A5x02C6a']:r for r in self.behavior['authored_skillsets']}
        installed={r['A5x02C6a']:r for r in nd(ROOT/'data/mst_decoded/F_MONSTER_SKILL_SET_MST.ndjson')}
        self.assertEqual((len(skills),len(sets)),(11,11))
        actors=[]
        for graphic,binding in self.behavior['bindings'].items():
            sid=binding.get('authored_skillset_id')
            if sid not in sets:
                continue
            actors.append(graphic)
            self.assertEqual(installed[sid],sets[sid])
            self.assertEqual(binding['native_ai'],'3')
            wanted={s for s in sets[sid]['7qxLC5hP'].split(',')if s}
            self.assertTrue(wanted)
            self.assertTrue(wanted<=skills.keys())
            part=self.parts[graphic+'00','1']
            self.assertEqual(part['A5x02C6a'],sid)
            self.assertEqual(part['8a6gAwN9'],'3')
        self.assertEqual(len(actors),11)
        for skill in skills.values():
            self.assertFalse(re.search('[\u3040-\u30ff\u3400-\u9fff]',skill['G4L0YIB2']))
        groups=nd(ROOT/'data/mst_decoded/F_EFFECT_GROUP_MST.ndjson')
        # Reuse the source contract's declared native identity field.
        contract=read(ROOT/'Japan content/Earlier JP crossovers/Sources/native-unit-import.json')
        identity=next(t['identity_fields'][0]for t in contract['tables']if t['table']=='F_EFFECT_GROUP_MST')
        active_groups={r[identity]for r in groups}
        mapping=read(ROOT/'Japan content/Earlier JP crossovers/Sources/native-unit-id-map.json')['mappings']['F_EFFECT_GROUP_MST']
        for skill in skills.values():
            clauses=[]
            for clause in re.split('([@&])',skill.get('5A8SmwyC','')):
                if clause in ('@','&'):
                    clauses.append(clause)
                    continue
                fields=clause.split(':')
                if len(fields)>=2:
                    fields[1]=mapping.get(fields[1],fields[1])
                clauses.append(':'.join(fields))
            expected=dict(skill,**{'5A8SmwyC':''.join(clauses)})
            found=[]
            for value in self.bundles.values():
                found.extend(s for s in value['bundle']['Wp39QX52']if s['6E5u1xrs']==skill['6E5u1xrs'])
            self.assertTrue(found,skill['6E5u1xrs'])
            self.assertTrue(all(s==expected for s in found),skill['6E5u1xrs'])
            for clause in re.split('[@&]',skill.get('5A8SmwyC','')):
                fields=clause.split(':')
                if len(fields)>=2 and fields[1] not in ('','0'):
                    self.assertIn(mapping.get(fields[1],fields[1]),active_groups,(skill['6E5u1xrs'],fields[1]))

    def test_friendly_healing_uses_a_proven_enemy_ai_combination(self):
        original=ROOT/'Japan content/Shared sources/memorial_battle_decoded'
        parts={r['xqartN26']:r for r in nd(original/'F_MONSTER_PARTS_MST.ndjson')if r['6Yc4RkdM']=='1'}
        sets={r['A5x02C6a']:r for r in nd(original/'F_MONSTER_SKILL_SET_MST.ndjson')}
        skills={r['6E5u1xrs']:r for r in nd(original/'F_MONSTER_SKILL_MST.ndjson')}
        part=parts['105037101']
        self.assertEqual(part['8a6gAwN9'],'3')
        self.assertIn('219698',sets[part['A5x02C6a']]['7qxLC5hP'].split(','))
        precedent=skills['219698']
        healing=next(r for r in self.behavior['authored_skill_rows']if r['6E5u1xrs']=='879510008')
        for field in ('2kq0BpnD','Ha9G5sCS','a4hXTIm0','oPD4yL58'):
            self.assertEqual(healing[field],precedent[field],field)

    def test_retained_role_bindings_and_native_dependencies(self):
        overrides=read(BASE/'enemy-behavior-overrides.json')['overrides']
        native_ai={r['8a6gAwN9']for r in nd(ROOT/'data/mst_decoded/F_AI_MST.ndjson')}
        native_sets={r['A5x02C6a']:r for r in nd(ROOT/'data/mst_decoded/F_MONSTER_SKILL_SET_MST.ndjson')}
        for row in overrides:
            actual=self.parts[row['enemy_id'],row['part_num']]
            for field,value in row['target_fields'].items():
                self.assertEqual(actual[field],value,(row['enemy_id'],row['part_num'],field))
        for part in self.parts.values():
            self.assertIn(part['8a6gAwN9'],native_ai)
            self.assertIn(part['A5x02C6a'],native_sets)
        for mid,value in self.bundles.items():
            fragments=[value['bundle']]
            for phase in value.get('jp_weighted_lottery',{}).get('phases',[]):
                fragments.extend(candidate['bundle']for candidate in phase['candidates'])
            for bundle in fragments:
                provided={r['6E5u1xrs']for r in bundle['Wp39QX52']}
                for part in bundle['bV34YIJQ']:
                    if part.get('A5x02C6a')in ('','0',None):
                        continue
                    wanted={s for s in native_sets[part['A5x02C6a']]['7qxLC5hP'].split(',')if s}
                    self.assertTrue(wanted<=provided,(mid,part['xqartN26'],wanted-provided))
        for iid in ('507001001','507001002','507001003'):
            self.assertEqual(self.parts[iid,'2']['8a6gAwN9'],'507001004')
            self.assertEqual(self.parts[iid,'2']['A5x02C6a'],'507001002')
            self.assertNotEqual(self.parts[iid,'1']['A5x02C6a'],'507001002')


if __name__=='__main__':
    unittest.main(verbosity=2)
