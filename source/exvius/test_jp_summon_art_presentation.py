"""Focused source-image and summon-contract checks for the31 art decisions."""
import hashlib
import json
from pathlib import Path
import subprocess
import unittest

ROOT=Path(__file__).resolve().parents[2]
BASE=ROOT/'Japan content/Earlier JP crossovers/Sources'
BACKUP=ROOT/'Trash/jp-banner-visual-correction/summon-presentation-before'
MAGICK='C:/Program Files/ImageMagick-7.1.1-Q16-HDRI/magick.exe'


def read(path):return json.loads(path.read_text(encoding='utf8'))
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


class OriginalSummonArt(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report=read(BASE/'original-summon-art-presentation.json')
        cls.entries={r['id']:r for r in cls.report['variants']}

    def test_all31_have_honest_presentation_decisions(self):
        original=read(BACKUP/'Japan content/Earlier JP crossovers/Sources/original-summon-completion.json')
        self.assertEqual(set(self.entries),{r['id']for r in original['without_art_variants']})
        self.assertEqual(len(self.entries),31)
        self.assertEqual(sum(bool(r.get('asset'))for r in self.entries.values()),31)
        self.assertEqual(sum(r['presentation']=='documented_native_text_fallback'for r in self.entries.values()),0)
        self.assertEqual(sum(r['presentation']=='translated_original_detail_notice'for r in self.entries.values()),2)
        for row in self.entries.values():
            self.assertFalse(row['dedicated_art_absence_proven'])
            self.assertTrue((ROOT/row['evidence']).is_file())
            if not row.get('asset'):
                self.assertFalse(row['historical_native_list_presentation_confirmed'])
                self.assertTrue(row['fallback_is_reconstruction'])

    def test_draw_rules_and_unrelated_offers_unchanged(self):
        allowed={'name','art','art_presentation','reconstruction'}
        for relative in ('source/server/gacha_named.json','source/server/gacha_original_jp.json'):
            before=read(BACKUP/relative)['banners'];after=read(ROOT/relative)['banners']
            self.assertEqual([r['id']for r in before],[r['id']for r in after])
            for old,new in zip(before,after):
                if old['id']not in self.entries:
                    self.assertEqual(old,new,old['id'])
                    continue
                self.assertEqual({k:v for k,v in old.items()if k not in allowed},
                                 {k:v for k,v in new.items()if k not in allowed},old['id'])
                self.assertEqual({k:v for k,v in old.get('reconstruction',{}).items()if k!='art_role'},
                                 {k:v for k,v in new.get('reconstruction',{}).items()if k!='art_role'},old['id'])

    def test_original_pixels_dimensions_and_alpha(self):
        assets=[(iid,row[key]) for iid,row in self.entries.items()
                for key in ('asset','detail_asset') if row.get(key)]
        assets.extend((iid,asset) for iid,row in self.entries.items()
                      for asset in row.get('supplemental_assets',[]))
        for iid,asset in assets:
            if not asset:
                continue
            source=ROOT/asset['source_file'];english=ROOT/asset['english_file'];mask=ROOT/asset['text_mask_file']
            self.assertEqual(sha(source),asset['source_sha256'])
            self.assertEqual(sha(english),asset['english_sha256'])
            self.assertEqual(sha(mask),asset['text_mask_sha256'])
            wh=subprocess.check_output([MAGICK,'identify','-format','%wx%h',str(english)],text=True)
            self.assertEqual(wh,'x'.join(map(str,asset['size'])),iid)
            original=subprocess.check_output([MAGICK,str(source),'-depth','8','rgba:-'])
            localized=subprocess.check_output([MAGICK,str(english),'-depth','8','rgba:-'])
            owned=subprocess.check_output([MAGICK,'-background','black',str(mask),'-alpha','off','-depth','8','gray:-'])
            self.assertEqual(len(original),len(localized),iid)
            self.assertEqual(len(owned)*4,len(original),iid)
            alpha=outside=0
            for pixel,coverage in enumerate(owned):
                offset=pixel*4;a=original[offset:offset+4];b=localized[offset:offset+4]
                alpha+=a[3]!=b[3]
                outside+=coverage==0 and a!=b and (a[3]!=0 or b[3]!=0)
            self.assertEqual(alpha,0,(iid,'alpha'))
            self.assertEqual(outside,0,(iid,'visible pixels outside text'))

    def test_bound_files_and_detail_only_notice(self):
        current={b['id']:b for b in read(ROOT/'source/server/gacha_named.json')['banners']}
        for iid,row in self.entries.items():
            asset=row.get('asset');art=current[iid].get('art',{})
            if not asset:
                self.assertFalse(art.get('banner')or art.get('detail_banner'),iid)
                continue
            name=Path(asset['english_file']).name
            detail=row.get('detail_asset') or asset
            self.assertEqual(art['detail_banner'],Path(detail['english_file']).name,iid)
            self.assertEqual(sha(ROOT/'data/gacha_community/art'/name),asset['english_sha256'],iid)
            self.assertEqual(sha(ROOT/'data/gacha_community/art'/Path(detail['english_file']).name),detail['english_sha256'],iid)
            if row['presentation']=='translated_original_detail_notice':
                self.assertFalse(art.get('banner'),iid)
            else:
                self.assertEqual(art['banner'],name,iid)
        self.assertEqual(current['9400159']['name'],'Avalon Robe Coin Summon 2024/1')
        self.assertEqual(current['9400160']['name'],'Dark Emperor Armor Coin Summon 2024/1')
        completion=read(BASE/'original-summon-completion.json')
        self.assertEqual((completion['variants'],completion['distinct_original_translations'],
                          completion['with_art_variant_bindings'],completion['without_dedicated_art']),
                         (76,66,76,0))


if __name__=='__main__':
    unittest.main(verbosity=2)
