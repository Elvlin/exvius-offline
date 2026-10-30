"""Authored inert source-table converter; no downloaded module execution/network.
Produces the existing server's by_class schema, not new protocol behavior.
"""
import argparse
import hashlib
import json
import re
import zipfile
from pathlib import Path
PIN = '7707880725637ece42dbc42820c29db424f6f4cc'
BASE_HASH = 'cb91b0cfea59f22285fa7c707d10adff5dd2561b014da66cb0c6af87c2eb489e'

def parse_contract(raw):
    classes = {}
    request_ids = {}
    for line in raw.decode('utf-8').splitlines():
        cells = [c.strip() for c in line.strip().strip('|').split('|')]
        if len(cells) != 4 or not all(c.startswith('`') and c.endswith('`') for c in cells):
            continue
        name, request, key, url = [c[1:-1] for c in cells]
        if not url.startswith('/actionSymbol/'):
            continue
        if not (re.fullmatch(r'[A-Za-z0-9_]+', name) and
                re.fullmatch(r'[A-Za-z0-9]{8}', request) and
                re.fullmatch(r'[A-Za-z0-9]{8}', key) and
                re.fullmatch(r'/actionSymbol/[A-Za-z0-9]+\.php', url)):
            raise ValueError('Malformed endpoint table row')
        value = {'request_id': request, 'encode_key': key, 'url': url,
                 'url_token': url.split('/')[-1][:-4]}
        if name in classes and classes[name] != value:
            raise ValueError('Conflicting class ' + name)
        if request in request_ids and classes[request_ids[request]] != value:
            raise ValueError('Ambiguous request identifier ' + request)
        classes[name] = value
        request_ids[request] = name
    if not classes:
        raise ValueError('No endpoint rows')
    tokens = {}
    for name, value in classes.items():
        tokens.setdefault(value['url_token'], []).append(name)
    return {'source': 'docs/analysis/FFBE_SERVER_CONTRACT.md; inert authored conversion',
            'source_sha256': hashlib.sha256(raw).hexdigest(), 'source_commit': PIN,
            'classes': len(classes), 'distinct_urls': len(tokens),
            'by_class': classes, 'by_url_token': tokens}

def prepare(bundle):
    source = Path(bundle)
    if hashlib.sha256(source.read_bytes()).hexdigest() != BASE_HASH:
        raise ValueError('Expected exact pinned original source archive')
    with zipfile.ZipFile(source) as z:
        names = [n for n in z.namelist() if n.endswith('/docs/analysis/FFBE_SERVER_CONTRACT.md')]
        if len(names) != 1 or z.getinfo(names[0]).file_size > 2*1024*1024:
            raise ValueError('Missing, ambiguous or oversized source contract')
        return parse_contract(z.read(names[0]))

if __name__ == '__main__':
    ap = argparse.ArgumentParser(); ap.add_argument('--source',required=True); ap.add_argument('--output',required=True)
    args = ap.parse_args(); value = prepare(args.source)
    # Exclusive creation avoids silently replacing a user's manually curated route map.
    with open(args.output, 'x', encoding='utf-8') as out:
        json.dump(value,out,indent=2)
    print(json.dumps({'classes':value['classes'],'distinct_urls':value['distinct_urls'],'source_sha256':value['source_sha256']}))
