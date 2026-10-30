"""Static package consistency audit, stdlib only. No imported server modules."""
import ast
import hashlib
import json
import sys
import zipfile
from pathlib import Path

def audit(path):
    with zipfile.ZipFile(path) as z:
        names={n.removeprefix('exvius/'):n for n in z.namelist() if not n.endswith('/')}
        modules={Path(n).stem for n in names if n.startswith('server/') and n.endswith('.py')}
        missing=[];external={};hashes={};parsed=0
        for name in sorted(names):
            if not name.startswith('server/') or not name.endswith('.py'):continue
            data=z.read(names[name]);hashes[name]=hashlib.sha256(data).hexdigest();parsed+=1
            for node in ast.walk(ast.parse(data,filename=name)):
                imports=[]
                if isinstance(node,ast.Import):imports=[a.name.split('.')[0] for a in node.names]
                elif isinstance(node,ast.ImportFrom) and node.module:imports=[node.module.split('.')[0]]
                for dep in imports:
                    if dep in sys.stdlib_module_names or dep in modules:continue
                    if dep in ('yaml','cryptography'):
                        external.setdefault(dep,[]).append(name)
                    else:missing.append({'module':name,'missing_import':dep})
        required=['server/endpoints.json','server/responses.json','server/seasons.json','server_app/deps.json',
                  'server/gacha_catalogue.json','server/gacha_community.json','server/gacha_authored.json',
                  'server/gacha_standard.json','server/gacha_campaigns.json']
        absent=[n for n in required if n not in names]
        routes=json.loads(z.read(names['server/endpoints.json'])) if 'server/endpoints.json' in names else None
        problems=[]
        if routes:
            for cls,row in routes['by_class'].items():
                if row['url']!='/actionSymbol/'+row['url_token']+'.php':problems.append('route mismatch: '+cls)
            if routes['classes']!=len(routes['by_class']):problems.append('class count mismatch')
            if routes['distinct_urls']!=len(routes['by_url_token']):problems.append('URL count mismatch')
        return {'static_consistency_passed':not(missing or absent or problems),'server_modules_parsed':parsed,
                'missing_imports':missing,'missing_packaged_files':absent,'route_schema_issues':problems,
                'external_python_dependencies':{k:sorted(set(v)) for k,v in external.items()},
                'route_counts':None if routes is None else {'classes':routes['classes'],'distinct_urls':routes['distinct_urls']},
                'server_source_sha256':hashes,'runtime_executed':False,
                'limits':['Static import and file closure only; not an actual server/pipeline/client run.',
                          'Game-data files and GL9 client compatibility require separate verified inputs.',
                          'Third-party runtime dependency presence/version is not tested.']}
if __name__=='__main__':
    result=audit(sys.argv[1]);print(json.dumps(result,indent=2));sys.exit(0 if result['static_consistency_passed'] else 2)
