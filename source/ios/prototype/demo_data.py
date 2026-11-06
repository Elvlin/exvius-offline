"""Metadata-only fixtures; summon definitions and gameplay remain in server/."""
import json
from pathlib import Path
import re

SERVER = Path(__file__).resolve().parents[2] / 'server'
BANNER_IDS = ('9100203', '49')


def prepare(root):
    root = Path(root).resolve()
    marker = root / 'synthetic-metadata.json'
    if root.exists() and any(root.iterdir()) and not marker.is_file():
        raise ValueError('Refusing to write demo fixtures into a non-demo data directory')
    root.mkdir(parents=True, exist_ok=True)
    for folder in ('mst_decoded', 'text_decoded'):
        (root / folder).mkdir(exist_ok=True)
    tables = set()
    for source in SERVER.glob('*.py'):
        tables.update(re.findall(r'F_[A-Z0-9_]+\.ndjson', source.read_text(encoding='utf-8')))
    for table in tables:
        (root / 'mst_decoded' / table).write_text('', encoding='utf-8')
    banners = json.loads((SERVER / 'gacha_authored.json').read_text(encoding='utf-8'))['banners']
    units = {'100000102': 2, '100000202': 2}

    def visit(value):
        if isinstance(value, dict):
            if 'rarity' in value and 'units' in value:
                for uid in value['units'] + value.get('featured', []):
                    units[str(uid)] = int(value['rarity'])
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    for banner in banners:
        if str(banner['id']) in BANNER_IDS:
            visit(banner)

    def write(relative, rows):
        (root / relative).write_text(''.join(json.dumps(row) + '\n' for row in rows), encoding='utf-8')
    write('mst_decoded/F_UNIT_MST.ndjson',
          ({'3HriTp6B': uid, '9fW0TePj': str(rarity), 'woghJa61': uid}
           for uid, rarity in units.items()))
    write('mst_decoded/F_EQUIP_ITEM_MST.ndjson',
          ({'J1YX9kmM': uid} for uid in ('302000100', '404000200', '406000100', '409000100')))
    write('text_decoded/F_TEXT_UNITS_NAME.ndjson',
          ({'key': 'MST_UNIT_NAME_' + uid, 'v': ['Fixture unit ' + uid]} for uid in units))
    marker.write_text(json.dumps({'synthetic': True, 'banner_ids': BANNER_IDS,
                                  'note': 'Placeholder metadata; no copied game tables or assets.'}), encoding='utf-8')
    return root
