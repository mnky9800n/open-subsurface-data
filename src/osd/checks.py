"""Checksums, zip checks and member extraction. The zip logic follows seismic-corpus/tools/corpus_fetch.py:
members are copied byte for byte and checked against the CRC32 stored in the zip."""
import hashlib
import os
import time
import zipfile
import zlib

try:
    import zipfile_deflate64  # noqa: F401  adds Deflate64 (method 9), used by some SARIG zips
    DEFLATE64 = True
except ImportError:
    DEFLATE64 = False

CHUNK = 16 << 20


def sha256(path: str, algo: str = 'sha256') -> str:
    h = hashlib.new(algo)
    with open(path, 'rb') as f:
        while b := f.read(CHUNK):
            h.update(b)
    return h.hexdigest()


def zip_listing(path: str) -> dict:
    """{member name: (size, crc32 as 8 hex digits, compression method)} from the central directory."""
    with zipfile.ZipFile(path) as z:
        return {i.filename: (i.file_size, f'{i.CRC:08x}', i.compress_type) for i in z.infolist() if not i.is_dir()}


def compare_members(path: str, members: list[dict]) -> list[str]:
    """Compare the zip's central directory with the member sizes and CRC32 values in the index.
    Members recorded as 'catalog listing, rounded' only need to be present."""
    problems = []
    have = zip_listing(path)
    low = {k.lower(): k for k in have}
    for m in members:
        name = m['member'].split('!')[0]
        k = name if name in have else low.get(name.lower())
        if k is None:
            problems.append(f'member missing: {name}')
            continue
        if '!' in m['member'] or m['record'].startswith('catalog'):
            continue
        size, crc, _ = have[k]
        if m['bytes'] and int(m['bytes']) != size:
            problems.append(f'{name}: size {size}, index says {m["bytes"]}')
        if m['crc32'] and m['crc32'] != crc:
            problems.append(f'{name}: CRC32 {crc}, index says {m["crc32"]}')
    return problems


def test_zip(path: str) -> list[str]:
    """Read every member and check its CRC32 (slow: reads the whole archive)."""
    problems = []
    with zipfile.ZipFile(path) as z:
        for i in z.infolist():
            if i.is_dir():
                continue
            if i.compress_type == 9 and not DEFLATE64:
                problems.append(f'{i.filename}: Deflate64, not tested (install the deflate64 extra)')
                continue
            crc = 0
            with z.open(i) as f:
                while b := f.read(CHUNK):
                    crc = zlib.crc32(b, crc)
            if crc != i.CRC:
                problems.append(f'{i.filename}: CRC32 mismatch')
    return problems


def find_member(names, want):
    low = {n.lower(): n for n in names}
    if want in names:
        return want
    if want.lower() in low:
        return low[want.lower()]
    tail = [n for n in names if n.lower().endswith('/' + want.lower()) or os.path.basename(n).lower() == os.path.basename(want).lower()]
    return tail[0] if len(tail) == 1 else None


def write_member(z, info, out_path):
    """Copy one member out of an open zip, check its CRC32 and size, keep the zip's file time."""
    if info.compress_type == 9 and not DEFLATE64:
        raise RuntimeError(f'{info.filename} uses Deflate64; run with the deflate64 extra: uv run --extra deflate64 osd ...')
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    tmp = out_path + '.part'
    crc, sha, n = 0, hashlib.sha256(), 0
    with z.open(info) as src, open(tmp, 'wb') as dst:
        while b := src.read(CHUNK):
            crc, n = zlib.crc32(b, crc), n + len(b)
            sha.update(b)
            dst.write(b)
    if crc != info.CRC or n != info.file_size:
        os.remove(tmp)
        raise RuntimeError(f'{info.filename}: CRC or size mismatch ({crc:08x} vs {info.CRC:08x}, {n} vs {info.file_size})')
    os.replace(tmp, out_path)
    ts = time.mktime(info.date_time + (0, 0, -1))
    os.utime(out_path, (ts, ts))
    return dict(bytes=n, crc32=f'{crc:08x}', sha256=sha.hexdigest())


def extract(zpath: str, wanted: list[str], out_dir: str, staging: str) -> list[dict]:
    """Extract the named members (a 'outer.zip!inner/file' name reaches into a nested zip). The archive is
    only read. Returns one record per file written."""
    recs = []
    with zipfile.ZipFile(zpath) as z:
        infos = {i.filename: i for i in z.infolist() if not i.is_dir()}
        outer = {}
        for w in wanted:
            a, _, b = w.partition('!')
            name = find_member(list(infos), a)
            if name is None:
                raise RuntimeError(f'member {a} is not in {os.path.basename(zpath)}')
            outer.setdefault(name, []).append(b)
        for name, inner in outer.items():
            if name.lower().endswith('.zip'):
                tmp = os.path.join(staging, hashlib.sha1((zpath + name).encode()).hexdigest()[:10] + '.zip')
                try:
                    write_member(z, infos[name], tmp)
                    base = os.path.dirname(name)
                    with zipfile.ZipFile(tmp) as iz:
                        for ii in iz.infolist():
                            if ii.is_dir() or (any(inner) and ii.filename not in inner):
                                continue
                            rel = os.path.join(base, ii.filename)
                            r = write_member(iz, ii, os.path.join(out_dir, rel))
                            recs.append(dict(r, path=rel, member=f'{name}!{ii.filename}'))
                finally:
                    if os.path.exists(tmp):
                        os.remove(tmp)
            else:
                r = write_member(z, infos[name], os.path.join(out_dir, name))
                recs.append(dict(r, path=name, member=name))
    return recs
