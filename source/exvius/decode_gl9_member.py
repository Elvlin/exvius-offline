"""Exact GL9 CRI per-member transform, not FileCrypt's unrelated i*i transform.
Native callback 0x1ef4250 -> 0x19b5e90; filename is trimFilePath result.
Use only for source-pinned encoded members. Never auto-detect/rewrite resources.
"""
def decode(raw, filename):
    if '/' in filename or '\\' in filename:
        raise ValueError('Pass the exact native trimmed filename, not a path')
    h = 0
    for c in filename.encode('utf-8'):
        h = (31 * h + c) & 0xffffffff
    out = bytearray(raw)
    half = len(raw) // 2
    offset = half + len(raw) % 2
    for i in range(half):
        key = (((h >> (8 * (i % 4))) & 255) + i + i // 255) & 255
        out[i] = raw[i + offset] ^ key
        out[i + offset] = raw[i] ^ key ^ 255
    return bytes(out)
