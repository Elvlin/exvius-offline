#!/usr/bin/env python3
"""Field map for client requests the server does not handle yet, read from the GL9 libgame.so.

For each `<Name>Request` it lists the 8-character wire tokens `createBody` references, and for the
matching `<Name>Response` the tokens `readParam` compares plus the setters it calls (setItemId, ...),
which name what each field means. Writes source/docs/analysis/unhandled_request_fields.json.

    python -I source/harness/extract_request_fields.py
"""
import json
import re
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT / 'tools/vendor/python'))
import capstone  # noqa: E402
import lief  # noqa: E402

LIB = PROJECT / 'source/build/android/client/lib/arm64-v8a/libgame.so'
TOKEN = re.compile(rb'^[0-9A-Za-z]{8}$')


def main():
    sweep = (PROJECT / 'logs/sweep-unhandled-requests-20261025.md').read_text(encoding='utf-8')
    wanted = sorted(set(re.findall(r'\b(\w+Request|sgHiddenSkillUpgrade)\b', sweep)))
    lib = lief.parse(str(LIB))
    md = capstone.Cs(capstone.CS_ARCH_ARM64, capstone.CS_MODE_ARM)
    symbols = {}
    for s in lib.dynamic_symbols:
        if s.value and s.size:
            symbols.setdefault(s.name, (s.value, s.size))
    names_at = {value: name for name, (value, _) in symbols.items()}
    got = {r.address: r.symbol.name for r in lib.pltgot_relocations if r.has_symbol}

    def stub(target):
        try:
            ins = list(md.disasm(bytes(lib.get_content_from_virtual_address(target, 8)), target))
            page = int(re.search(r'#(0x[0-9a-f]+)', ins[0].op_str).group(1), 16)
            off = int(re.search(r'#(0x[0-9a-f]+)\]', ins[1].op_str).group(1), 16)
            return got.get(page + off, '')
        except Exception:
            return ''

    def read_cstring(address):
        try:
            data = bytes(lib.get_content_from_virtual_address(address, 40))
        except Exception:
            return None
        return data.split(b'\0', 1)[0]

    def scan(name):
        if name not in symbols:
            return None
        value, size = symbols[name]
        code = bytes(lib.get_content_from_virtual_address(value, size))
        tokens, calls, pages = [], [], {}
        params, last_token, getters, offsets, this = [], None, [], [], {'x0'}
        for ins in md.disasm(code, value):
            if ins.mnemonic == 'mov' and ins.op_str.endswith(', x0') and not this - {'x0'}:
                this.add(ins.op_str.split(',')[0])
            m = re.match(r'ldr\w*|ldp', ins.mnemonic) and re.search(r'\[(x\d+), #(0x[0-9a-f]+)\]', ins.op_str)
            if m and m.group(1) in this:
                offsets.append(int(m.group(2), 16))
            if ins.mnemonic == 'adrp':
                reg, imm = ins.op_str.split(', ')
                pages[reg] = int(imm.strip('#'), 16)
            elif ins.mnemonic == 'add' and ins.op_str.count('#') == 1:
                parts = [p.strip() for p in ins.op_str.split(',')]
                if len(parts) == 3 and parts[1] in pages:
                    text = read_cstring(pages[parts[1]] + int(parts[2].strip('#'), 16))
                    if text and TOKEN.match(text):
                        last_token = text.decode()
                        if last_token not in tokens:
                            tokens.append(last_token)
            elif ins.mnemonic == 'bl':
                target = int(ins.op_str.strip('#'), 16)
                callee = names_at.get(target) or stub(target)
                if callee and re.search(r'\d(set|add|get)[A-Z]', callee) and callee not in calls:
                    calls.append(callee)
                if callee and re.search(r'(get|Get|is|has|Count|Id|ID|Str)', callee) and 'addParam' not in callee:
                    getters.append(re.sub(r'^_ZN?K?\d+', '', callee)[:60])
                if callee and ('addParam' in callee or 'addGroup' in callee) and last_token:
                    kind = 'group' if 'addGroup' in callee else 'param'
                    params.append({kind: last_token, 'from': getters[-3:], 'fields': offsets[-3:]})
                    getters, offsets = [], []
        return {'tokens': tokens, 'calls': calls, 'params': params}

    def setters(cls):
        found = {}
        prefix = f'_ZN{len(cls)}{cls}'
        for name, (value, size) in symbols.items():
            if not name.startswith(prefix) or size > 400:
                continue
            method = re.match(r'\d+(\w+?)E', name[len(prefix):])
            if not method or not method.group(1).startswith(('set', 'add')):
                continue
            code = bytes(lib.get_content_from_virtual_address(value, size))
            for ins in md.disasm(code, value):
                m = re.match(r'str\w*|stp', ins.mnemonic) and re.search(r'\[x0, #(0x[0-9a-f]+)\]', ins.op_str)
                if m:
                    found.setdefault(int(m.group(1), 16), method.group(1))
        return found

    out = {}
    for request in wanted:
        base = request[:-len('Request')] if request.endswith('Request') else request
        n = len(request)
        entry = {'createBody': scan(f'_ZN{n}{request}10createBodyEv')}
        named = setters(request)
        for param in (entry['createBody'] or {}).get('params', []):
            names = [named[o] for o in param.pop('fields') if o in named]
            if names:
                param['setter'] = names[-1]
        response = base + 'Response'
        entry['readParam'] = scan(f'_ZN{len(response)}{response}9readParamEiiPKcS1_b')
        out[request] = entry
    target = PROJECT / 'source/docs/analysis/unhandled_request_fields.json'
    target.write_text(json.dumps(out, indent=1) + '\n', encoding='utf-8')
    print(f'{len(out)} requests -> {target.relative_to(PROJECT)}')


if __name__ == '__main__':
    main()
