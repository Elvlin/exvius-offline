"""Export exact original earlier JP field captions for reviewed localization."""
import hashlib
import json
from pathlib import Path

from recover_jp_assets import source_rows, decoded_member

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / 'Japan content/Earlier JP crossovers/Sources'


def main():
    bindings = json.loads((BASE / 'Event graph/field-resource-bindings.json').read_text(encoding='utf8'))
    resources = {r['filename']: r for m in bindings['missions'] for r in m['native_resources']
                 if r['filename'].endswith('.cpk')}
    out = BASE / 'Field text'
    out.mkdir(exist_ok=True)
    texts, members = {}, []
    for name, resource in sorted(resources.items()):
        source = next(ROOT / p['path'] for p in resource['original_source_paths']
                      if p.get('matches_original_archive_bytes'))
        raw, toc, start = source_rows(source)
        for row in toc:
            member = row['FileName']
            if not member.endswith('.txt') or not any(k in member for k in ('text', 'teller')):
                continue
            offset = start + row['FileOffset']
            body = decoded_member(raw[offset:offset + row['FileSize']], row, source.stem)
            path = out / name.removesuffix('.cpk') / member
            path.parent.mkdir(exist_ok=True)
            path.write_bytes(body)
            members.append({'package': name, 'member': member, 'source': source.relative_to(ROOT).as_posix(),
                            'source_sha256': hashlib.sha256(raw).hexdigest(),
                            'path': path.relative_to(ROOT).as_posix(), 'bytes': len(body),
                            'sha256': hashlib.sha256(body).hexdigest()})
            for line in body.decode('utf-8-sig').splitlines():
                if not line:
                    continue
                key, sep, text = line.partition(',')
                if not sep:
                    raise ValueError('Unexpected original text row: ' + member)
                digest = hashlib.sha256(text.encode('utf8')).hexdigest()
                entry = texts.setdefault(digest, {'source': text, 'bindings': []})
                if entry['source'] != text:
                    raise ValueError('Caption hash collision')
                entry['bindings'].append({'package': name, 'member': member, 'id': key})
    result = {'schema': 1, 'original_packages': len(resources), 'members': members,
              'unique_texts': len(texts), 'source_rows': sum(len(r['bindings']) for r in texts.values()),
              'translations': texts,
              'pipeline': 'Original decoded members; fill_content_from_memorial.localized_package creates _sg companions; reviewed source SHA256 bindings feed apply_english_dialogue.'}
    (out / 'original-field-text.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    print(json.dumps({k: result[k] for k in ('original_packages', 'unique_texts', 'source_rows')}))


if __name__ == '__main__':
    main()
