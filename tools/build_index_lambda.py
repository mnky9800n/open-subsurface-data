"""Build the per-volume header table and the well-to-grid ties for the open-subsurface-data index.
Runs on lambda-scalar. Reads only: the corpus metadata.json files and a sample of trace headers from finished
SEG-Y files on the NAS, plus the public Gulf well table (explo_wells.csv) and the NAMSS outlines. Writes to
~/osd-build/. Touches nothing in the corpus folder.

    uv run --with numpy --with pyproj --with matplotlib python build_index_lambda.py
"""
import csv, glob, json, os, re, sys
import numpy as np
from matplotlib.path import Path
from pyproj import CRS, Transformer

NAS = '/mnt/nas/seismic-corpus'
HOME = os.path.expanduser('~')
OUT = f'{HOME}/osd-build'
WELLS = f'{HOME}/veles-toy-basin/gulf_logs/explo_wells.csv'
OUTLINES = f'{HOME}/veles-toy-basin/gulf_data/extracted/namss_outlines.json'
BPS = {1: 4, 2: 4, 3: 2, 5: 4, 6: 8, 8: 1, 9: 8, 10: 4, 11: 2, 12: 8, 15: 3, 16: 1}
N_SAMPLE = 40
os.makedirs(OUT, exist_ok=True)


def done_surveys():
    """Survey folders whose archive finished (status done in jobs.jsonl)."""
    ok = set()
    for line in open(f'{NAS}/log/jobs.jsonl'):
        d = json.loads(line)
        if d.get('status') == 'done':
            for k in d.get('volumes', {}):
                ok.add(k)
    return ok


def volume_rows():
    ok = done_surveys()
    rows = []
    for p in sorted(glob.glob(f'{NAS}/*/*/metadata.json')):
        rel = os.path.relpath(os.path.dirname(p), NAS)
        if rel not in ok:
            continue
        m = json.load(open(p))
        for vname, v in m['volumes'].items():
            heads = list(v.get('file_headers', {}).values())
            bh = [h.get('binary_header') for h in heads if h.get('binary_header')]
            proc = sorted({l for h in heads for l in h.get('text_header_processing_lines', [])})
            coords = (v.get('header_bytes') or {}).get('coordinates') or {}
            rows.append(dict(
                folder=rel, source=m['source'], survey_id=m['survey_id'], volume=vname,
                include=v['manifest']['include'], role=v['manifest']['role'], stack_type=v['manifest']['stack_type'],
                two_d_cubed=v['manifest']['two_d_cubed'], n_files=len(v['files']),
                bytes=sum(f['bytes'] for f in v['files']),
                files=[dict(path=f['path'], bytes=f['bytes'], crc32=f['crc32'], sha256=f['sha256'], archive_member=f['archive_member']) for f in v['files']],
                opened_with_segyio=v['opened_with_segyio'], failed_to_open=v['failed_to_open'],
                inline_range=v['inline_range'], crossline_range=v['crossline_range'], samples=v['samples'],
                sample_interval=v['sample_interval'], header_bytes=dict(inline=v['header_bytes']['inline'], crossline=v['header_bytes']['crossline']),
                coordinates=coords, traces=sum(h.get('traces', 0) or 0 for h in heads),
                format_codes=sorted({b['format_code'] for b in bh}), endianness=sorted({b['endianness'] for b in bh}),
                revisions=sorted({b['revision'] for b in bh}), measurement_system=sorted({b['measurement_system'] for b in bh}),
                ext_text_headers=sorted({b['ext_text_headers'] for b in bh}),
                text_header_crs=v['crs']['text_header'], text_header_processing=proc,
                catalogue_crs=m.get('catalogue_crs'), crs_in_side_files=m.get('crs_in_side_files'),
                problems=v['problems']))
    return rows


# ------------------------------------------------------------- trace header sampling and grid fit

def sample_headers(path, il_b, xl_b, x_b, y_b, binh, ntr):
    end = '>' if binh['endianness'] == 'big' else '<'
    ns, bps = binh['samples'], BPS[binh['format_code']]
    start = 3600 + 3200 * max(binh['ext_text_headers'], 0)
    tl = 240 + ns * bps
    size = os.path.getsize(path)
    if (size - start) % tl:
        return None
    n = (size - start) // tl
    idx = np.unique(np.linspace(0, n - 1, min(N_SAMPLE, n)).astype(np.int64))
    out = []
    fd = os.open(path, os.O_RDONLY)
    try:
        os.posix_fadvise(fd, 0, 0, os.POSIX_FADV_RANDOM)
        for i in idx:
            h = os.pread(fd, 240, start + int(i) * tl)
            g4 = lambda b: int(np.frombuffer(h[b - 1:b + 3], end + 'i4')[0])
            sc = int(np.frombuffer(h[70:72], end + 'i2')[0])
            fac = (1 / abs(sc) if sc < 0 else sc) if sc else 1
            out.append((g4(il_b), g4(xl_b), g4(x_b) * fac, g4(y_b) * fac))
    finally:
        os.close(fd)
    return np.array(out, float)


def fit_affine(a):
    il, xl, x, y = a.T
    G = np.column_stack([il, xl, np.ones_like(il)])
    cx, *_ = np.linalg.lstsq(G, x, rcond=None)
    cy, *_ = np.linalg.lstsq(G, y, rcond=None)
    res = np.hypot(G @ cx - x, G @ cy - y)
    return cx, cy, float(np.sqrt(np.mean(res ** 2))), float(res.max())


def crs_candidates(lines):
    t = ' '.join(lines).upper()
    ft = bool(re.search(r'FEET|\bFT\b|US SURVEY|FOOT', t))
    c = []
    m = re.search(r'(?:UTM|MERCATOR)\D{0,12}?(\d{2})', t) or re.search(r'ZONE\s*(\d{2})', t)
    if m and ('UTM' in t or 'MERCATOR' in t):
        z = int(m.group(1))
        c.append(('NAD27 / UTM zone %dN (%s)' % (z, 'US ft' if ft else 'm'),
                  CRS.from_proj4('+proj=utm +zone=%d +datum=NAD27 +units=%s +no_defs' % (z, 'us-ft' if ft else 'm'))))
    if re.search(r'LOUISIANA SOUTH|STATE PLANE SOUTH|LA SOUTH|\bLAS\b', t) or ('LOUISIANA' in t and 'SOUTH' in t):
        c.append(('NAD27 / Louisiana South (EPSG:26782)', CRS.from_epsg(26782)))
    if 'OFFSHORE' in t and ('LOUISIANA' in t or ' LA ' in t):
        c.append(('NAD27 / Louisiana Offshore (EPSG:32099)', CRS.from_epsg(32099)))
    if 'TEXAS' in t or ' TX ' in t:
        c += [('NAD27 / Texas South Central (EPSG:32040)', CRS.from_epsg(32040)), ('NAD27 / Texas South (EPSG:32041)', CRS.from_epsg(32041))]
    pinned = len(c) == 1
    if not c:
        c = [('NAD27 / Louisiana South (EPSG:26782)', CRS.from_epsg(26782)), ('NAD27 / Louisiana Offshore (EPSG:32099)', CRS.from_epsg(32099)),
             ('NAD27 / Texas South Central (EPSG:32040)', CRS.from_epsg(32040)), ('NAD27 / Texas South (EPSG:32041)', CRS.from_epsg(32041))] + \
            [('NAD27 / UTM zone %dN (%s)' % (z, 'US ft' if u else 'm'),
              CRS.from_proj4('+proj=utm +zone=%d +datum=NAD27 +units=%s +no_defs' % (z, 'us-ft' if u else 'm'))) for z in (14, 15, 16) for u in (0, 1)]
    return c, pinned


def grow(poly, d):
    p = np.asarray(poly, float)
    c = p.mean(0)
    return Path(c + (p - c) * (1 + d))


def sample_volume(v):
    c = v['coordinates']
    if not c or not v['inline_range'] or not v['crossline_range']:
        return []
    meta = json.load(open(os.path.join(NAS, v['folder'], 'metadata.json')))
    pts = []
    for fr in v['files']:
        if not fr['path'].lower().endswith(('.sgy', '.segy', '.seg')):
            continue
        h = meta['volumes'][v['volume']]['file_headers'].get(fr['path'], {})
        if 'binary_header' not in h:
            continue
        a = sample_headers(os.path.join(NAS, v['folder'], fr['path']), v['header_bytes']['inline'], v['header_bytes']['crossline'],
                           c['x_byte'], c['y_byte'], h['binary_header'], h.get('traces'))
        if a is not None:
            pts.append(a)
    print('sampled', v['survey_id'], v['volume'], len(pts), flush=True)
    return pts


def main():
    vols = volume_rows()
    with open(f'{OUT}/volumes.jsonl', 'w') as f:
        for r in vols:
            f.write(json.dumps(r, default=str) + '\n')
    print(len(vols), 'volumes from', len({r['folder'] for r in vols}), 'survey folders', flush=True)

    outl = json.load(open(OUTLINES))
    wells = [r for r in csv.DictReader(open(WELLS)) if r['surveys']]
    by_survey = {}
    for w in wells:
        for s in w['surveys'].split(';'):
            by_survey.setdefault(s, []).append(w)
    nad27 = CRS.from_epsg(4267)
    grids, ties = [], []
    todo = [v for v in vols if v['source'] == 'USGS NAMSS' and v['survey_id'] in by_survey and outl.get(v['survey_id'])]
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(4) as ex:
        samples = dict(zip([id(v) for v in todo], ex.map(sample_volume, todo)))
    for v in todo:
        sid = v['survey_id']
        c = v['coordinates']
        if not c or not v['inline_range'] or not v['crossline_range']:
            grids.append(dict(survey_id=sid, volume=v['volume'], status='no coordinates or grid in headers'))
            continue
        pts = samples[id(v)]
        if not pts:
            grids.append(dict(survey_id=sid, volume=v['volume'], status='trace headers could not be sampled'))
            continue
        a = np.vstack(pts)
        a = a[(a[:, 2] != 0) | (a[:, 3] != 0)]
        cx, cy, rms, mx = fit_affine(a)
        poly = outl[sid]
        path_o = grow(poly, 0.05)
        cands, pinned = crs_candidates(v['text_header_crs'])
        best = None
        for name, crs in cands:
            tr = Transformer.from_crs(crs, nad27, always_xy=True)
            lon, lat = tr.transform(a[:, 2], a[:, 3])
            frac = float(np.mean(path_o.contains_points(np.column_stack([lon, lat]))))
            if best is None or frac > best[0] or (frac == best[0] and pinned):
                best = (frac, name, crs)
        frac, name, crs = best
        ilr, xlr = v['inline_range'], v['crossline_range']
        corners = [(ilr['min'], xlr['min']), (ilr['min'], xlr['max']), (ilr['max'], xlr['max']), (ilr['max'], xlr['min'])]
        tr_f = Transformer.from_crs(crs, nad27, always_xy=True)
        cxy = [(cx @ [i, x, 1], cy @ [i, x, 1]) for i, x in corners]
        clon, clat = tr_f.transform([p[0] for p in cxy], [p[1] for p in cxy])
        quality = 'good' if frac >= 0.95 and rms < 50 else ('check' if frac >= 0.5 else 'unresolved')
        grids.append(dict(survey_id=sid, volume=v['volume'], status='fitted', crs=name, crs_named_in_text_header=pinned,
                          frac_traces_inside_outline=round(frac, 3), affine_x=[float(t) for t in cx], affine_y=[float(t) for t in cy],
                          fit_rms=round(rms, 3), fit_max=round(mx, 3), n_traces_sampled=len(a), quality=quality,
                          corners_lonlat_nad27=[[round(float(o), 6), round(float(t), 6)] for o, t in zip(clon, clat)]))
        if quality == 'unresolved':
            continue
        inv = np.linalg.inv(np.array([[cx[0], cx[1]], [cy[0], cy[1]]]))
        tr_b = Transformer.from_crs(nad27, crs, always_xy=True)
        for w in by_survey[sid]:
            row = dict(api=w['api'], survey_id=sid, volume=v['volume'], crs=name, grid_quality=quality)
            for tag, lo, la in (('surface', w['surf_lon'], w['surf_lat']), ('bottom', w['bot_lon'], w['bot_lat'])):
                try:
                    X, Y = tr_b.transform(float(lo), float(la))
                except ValueError:
                    continue
                il, xl = inv @ (np.array([X, Y]) - np.array([cx[2], cy[2]]))
                inside = (ilr['min'] - ilr['step'] / 2 <= il <= ilr['max'] + ilr['step'] / 2) and (xlr['min'] - xlr['step'] / 2 <= xl <= xlr['max'] + xlr['step'] / 2)
                row[f'{tag}_x'] = round(float(X), 2)
                row[f'{tag}_y'] = round(float(Y), 2)
                row[f'{tag}_inline'] = round(float(il), 2)
                row[f'{tag}_crossline'] = round(float(xl), 2)
                row[f'{tag}_inside_grid'] = bool(inside)
            ties.append(row)
        print(sid, v['volume'], name, quality, round(frac, 3), round(rms, 2), len(by_survey[sid]), flush=True)
    json.dump(grids, open(f'{OUT}/volume_grids.json', 'w'), indent=1)
    cols = ['api', 'survey_id', 'volume', 'crs', 'grid_quality'] + [f'{t}_{k}' for t in ('surface', 'bottom') for k in ('x', 'y', 'inline', 'crossline', 'inside_grid')]
    with open(f'{OUT}/well_volume_ties.csv', 'w', newline='') as f:
        w = csv.DictWriter(f, cols)
        w.writeheader()
        w.writerows(ties)
    print('grids', len(grids), 'ties', len(ties), flush=True)


if __name__ == '__main__':
    main()
