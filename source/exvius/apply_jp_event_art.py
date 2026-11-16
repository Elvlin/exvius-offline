"""Bind reviewed English JP event cards through existing menu artwork paths."""
import argparse,copy,hashlib,json,sys
from pathlib import Path
from PIL import Image
from apply_jp_content import NativeCache
from apply_jp_unit_tables import apply_contract
from decode_client_data import decode

ROOT=Path(__file__).resolve().parents[2]
BASE=ROOT/'Japan content/Earlier JP crossovers/Sources'

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def records():
    result={}
    missing=set()
    for name in ('event-card-english-copy.json','older-event-card-english-copy.json'):
        document=json.loads((BASE/name).read_text(encoding='utf8'))
        missing.update(document.get('unrecovered_original_area_ids',[]))
        for row in document['cards']:
            if row.get('reconstruction'):
                raise ValueError('Invented or reconstructed banner artwork is not an original-source translation')
            result[row['source_area_id']]=row
    doc=json.loads((BASE/'Roto/banner-image-english-copy.json').read_text(encoding='utf8'))
    originals=json.loads((BASE/'original-event-art.json').read_text(encoding='utf8'))
    filenames={r['area_id']:r['active_primary_filename'] for r in originals['events']}
    for row in doc['cards']:
        r=dict(row)
        r['english_file']='Japan content/Earlier JP crossovers/Sources/Roto/'+r['english_file']
        r['source_file']='Japan content/Earlier JP crossovers/Sources/Roto/'+r['source_file']
        r['source_page']=doc['primary_announcement']
        result[r['source_area_id']]=r
    if set(result)!=set(filenames)-missing:
        raise ValueError('English cards must match recovered original sources; missing originals stay unfilled')
    for aid,r in result.items():
        r['native_original_filename']=filenames[aid]
        raw=(ROOT/r['english_file']).read_bytes()
        if sha(raw)!=r['english_sha256'] or Image.open(ROOT/r['english_file']).size!=Image.open(ROOT/r['source_file']).size:
            raise ValueError('Reviewed English image changed: '+aid)
        if sha((ROOT/r['source_file']).read_bytes())!=r['source_sha256']:
            raise ValueError('Retained original image changed: '+aid)
    return result

def main(apply=False):
    cards=records();cache=NativeCache();tables=[];native={};paths={}
    try:
        for table,version in [('F_ICON_MST','375'),('F_AREA_MST','611'),('F_DUNGEON_MST','422')]:
            token,key=cache.tables[table];relative='mst/Ver'+version+'_'+token+'.dat'
            raw,origin=cache.read(relative);_,rs=decode(raw,key)
            native[table]=rs;paths[table]=(relative,raw,origin)
        icons={r['0HUPxDf1']:r for r in native['F_ICON_MST']}
        areas={r['uv60hgDW']:r for r in native['F_AREA_MST']}
        dungeons={r['U9iHsau3']:r for r in native['F_DUNGEON_MST']}
        original_areas={r['uv60hgDW']:r for r in map(json.loads,(BASE/'Event graph/F_AREA_MST.ndjson').read_text(encoding='utf8').splitlines())}
        original_dungeons={r['U9iHsau3']:r for r in map(json.loads,(BASE/'Event graph/F_DUNGEON_MST.ndjson').read_text(encoding='utf8').splitlines())}
        updates={k:[] for k in native};outputs={};bindings=[]
        art_path=ROOT/'source/server/event_art.json';art=json.loads(art_path.read_text(encoding='utf8'));old=copy.deepcopy(art)
        for aid in sorted(cards,key=int):
            number=sorted(original_areas,key=int).index(aid)+1
            row=cards[aid];icon=str(879000000+number);filename='jp_event_'+aid+'_en.png'
            title=row['title'];icon_row={'0HUPxDf1':icon,'G4L0YIB2':title,'qtkvrS60':filename}
            if icon in icons and icons[icon]!=icon_row:
                raise ValueError('Scoped JP event icon ID collides: '+icon)
            if areas[aid]['G4L0YIB2']!=original_areas[aid]['G4L0YIB2']:
                raise ValueError('Native area identity differs from original JP: '+aid)
            owned=[r for r in original_dungeons.values() if r['uv60hgDW']==aid]
            if len(owned)!=1:
                raise ValueError('Expected one independently owned event dungeon: '+aid)
            dungeon=owned[0]['U9iHsau3']
            if dungeons[dungeon]['uv60hgDW']!=aid or dungeons[dungeon]['G4L0YIB2']!=owned[0]['G4L0YIB2']:
                raise ValueError('Native dungeon identity differs from original JP: '+dungeon)
            updates['F_ICON_MST'].append(icon_row)
            updates['F_AREA_MST'].append({'uv60hgDW':aid,'0HUPxDf1':icon})
            updates['F_DUNGEON_MST'].append({'U9iHsau3':dungeon,'0HUPxDf1':icon})
            raw=(ROOT/row['english_file']).read_bytes();out='data/overlay/en/sd/area/'+filename;outputs[out]=raw
            art['events'][aid]={'name':title,'filename':filename,'source_file':row['source_file'],'source_sha256':row['source_sha256'],'source_page':row.get('source_page'),'runtime_file':out,'runtime_sha256':sha(raw),'size':list(Image.open(ROOT/row['english_file']).size),'localization_source':row['english_file'],'localization':'Original Japanese banner with only its existing text translated into English.','native_icon_id':icon}
            art['dungeons'][dungeon]={'name':title,'filename':filename,'original_image':filename,'source_page':row.get('source_page')}
            bindings.append({'area':aid,'dungeon':dungeon,'icon':icon,'filename':filename,'english_file':row['english_file'],'sha256':sha(raw),'original_native_filename':row['native_original_filename']})
        for kind in ('events','dungeons'):
            touched={r['area' if kind=='events' else 'dungeon'] for r in bindings}
            if any(art[kind].get(k)!=v for k,v in old[kind].items() if k not in touched):
                raise ValueError('Unrelated existing event artwork changed')
        for table,rows in updates.items():
            relative,raw,origin=paths[table];key={'F_ICON_MST':'0HUPxDf1','F_AREA_MST':'uv60hgDW','F_DUNGEON_MST':'U9iHsau3'}[table]
            tables.append({'table':table,'identity_fields':[key],'operation':'replace' if table=='F_ICON_MST' else 'merge_fields','active_native_path':relative,'active_native_sha256':sha(raw),'active_native_source':{'path':origin,'sha256':sha(raw)},'decoded_baseline_sha256':sha((ROOT/'data/mst_decoded'/(table+'.ndjson')).read_bytes()),'rows':rows})
        contract={'schema':1,'status':'VALIDATED_READY_TO_APPLY','scope':'Original-source English JP event icons, only original event owner references changed','tables':tables}
        contract_path=BASE/'event-art-native-import.json';contract_path.write_text(json.dumps(contract,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
        apply_contract(contract_path,apply,ROOT/'logs/jp-event-art-native-integration.json')
        if apply:
            for path,raw in outputs.items():
                p=ROOT/path;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(raw)
                if p.read_bytes()!=raw:raise ValueError('Image write/readback failed: '+path)
            art_path.write_text(json.dumps(art,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
        receipt={'status':'APPLIED_PENDING_NATIVE_REBUILD' if apply else 'VALIDATED_PREVIEW','cards':len(cards),'native_icon_reference_rows':len(cards)*2,'bindings':bindings,'runtime_metadata':'source/server/event_art.json','original_art_retained':True,'global_unrelated_rows_preserved':True,'resource_versions_changed':False,'required_next_step':'Regenerate menu_assets.h through established gen_edit_data.menu_assets before an approved native APK rebuild. Current released APK has compiled owned-image and inner-dungeon lists.'}
        (ROOT/'logs/jp-event-art-integration.json').write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf8')
        print(json.dumps({'status':receipt['status'],'cards':len(cards),'native_icon_reference_rows':len(cards)*2}))
    finally:
        cache.close()

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--apply',action='store_true')
    main(parser.parse_args().apply)
