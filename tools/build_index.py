"""Build the index tables in data/ from the corpus crawl, the reference mirror and the Gulf well work.

    uv run python tools/build_index.py --corpus ../seismic-corpus --mirror <osd-build copy> --gulf <gulf copy>

Inputs (all from public sources; nothing here comes from DISKOS):
  --corpus  seismic-corpus checkout: manifest.csv, crawl/namss/*.json (NAMSS survey pages and zip listings),
            crawl/sarig_zip_members.json (SARIG zip central directories), crawl/sarig_packages.json (CKAN),
            crawl/namss_outlines.json (NAMSS navigation outlines, lon/lat NAD27)
  --mirror  outputs of tools/build_index_lambda.py and tools/frs_subset_lambda.py run beside the reference
            mirror: volumes.jsonl, volume_grids.json, well_volume_ties.csv, boem_frs_raw_logs.csv, files.csv
            (the mirror's log/files.csv)
  --gulf    the Gulf well work: explo_wells.csv, wells_namss.csv, manifest.tsv (downloads with SHA-256)
The Zenodo file lists in tools/ (lily_zenodo_8408297.json, and zenodo_iodp.json and zenodo_logdb.json from
zenodo_community.py) add the LILY, IODP and LogDB rows to files.csv.
data/sources.csv is written by hand and is not touched here.
"""
import argparse, collections, csv, glob, json, os, re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, 'data')
SEGY = re.compile(r'\.(sgy|segy|seg)(\.part[a-z]+)?$', re.I)
SEGY_ZIP = re.compile(r'^data/.*\.zip$', re.I)
MAX_SIDE = 2e9
SRC = {'USGS NAMSS': 'namss', 'SARIG (South Australia)': 'sarig'}
NAMSS_DOI = '10.5066/F7930R7P'
REGION_BY_SUFFIX = {'LA': 'gulf-of-mexico', 'TX': 'gulf-of-mexico', 'MS': 'gulf-of-mexico', 'AL': 'gulf-of-mexico',
                    'FL': 'gulf-of-mexico', 'AK': 'alaska', 'CA': 'pacific', 'SC': 'pacific', 'CC': 'pacific'}


def region(r):
    if r['source'].startswith('SARIG'):
        return 'south-australia'
    suf = r['survey_id'].split('-')[-1].split('_')[0]
    if suf in REGION_BY_SUFFIX:
        return REGION_BY_SUFFIX[suf]
    loc = r['location']
    if 'Gulf of America' in loc:
        return 'gulf-of-mexico'
    if re.search(r'Beaufort|Chukchi|Cook Inlet|Alaska|Aleutian|Navarin|Norton|Bering', loc):
        return 'alaska'
    if 'California' in loc or 'Oregon' in loc:
        return 'pacific'
    return 'other'


def volume_name(members):
    names = [os.path.splitext(os.path.basename(m))[0] for m in members]
    if not names:
        return ''
    if len(names) == 1:
        return names[0]
    p = os.path.commonprefix(names).rstrip('_-. ')
    return p or names[0]


def file_id_for(r):
    u = r['archive_url']
    if r['source'] == 'USGS NAMSS':
        return 'namss:' + os.path.basename(u)[len('namss.'):].split('.')[0]
    rid = u.rstrip('/').split('/')[-2]
    return f'sarig:{rid}/{os.path.basename(u)}'


def local_path_for(r):
    u = r['archive_url']
    if r['source'] == 'USGS NAMSS':
        return f'namss/{os.path.basename(u)}'
    return f'sarig/{u.rstrip("/").split("/")[-2]}/{os.path.basename(u)}'


def write_csv(path, rows, cols):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, cols, extrasaction='ignore')
        w.writeheader()
        w.writerows(rows)
    print(f'{os.path.relpath(path, ROOT)}: {len(rows)} rows')


def lily_rows(sources):
    """files.csv rows for the LILY database, from the Zenodo file list saved in tools/lily_zenodo_8408297.json
    (sizes and md5 as Zenodo gives them). Global, so the region is 'global'."""
    z = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'lily_zenodo_8408297.json')))
    return [dict(file_id='lily:' + f['key'], source='lily', kind='cores', dataset=f['key'], url=f['url'], bytes=str(f['size']),
                 stable='yes', local_path='lily/' + f['key'], license=sources['lily']['license'], regions={'global'},
                 surveys=set(), include=set(), checksum=f['checksum']) for f in z['files']]


LICENSE_TEXT = {'cc-by-4.0': 'CC BY 4.0', 'cc-zero': 'CC0 1.0', 'cc-by-sa-4.0': 'CC BY-SA 4.0', '': 'not stated'}
LILY_CONCEPT_DOI = '10.5281/zenodo.8408296'   # every version of LILY; the lily source indexes version 8408297
REPORT = re.compile(r'^Proceedings of the|^Initial Reports of the|Technical Note|Preliminary Report|Manual|Cruise Report|'
                    r'Terminology|^A 3-year Snapshot|^Preserving Scientific')
LWD = re.compile(r'\bLWD\b')


def zenodo_rows(community, sid, prefix, seen):
    """files.csv rows for a Zenodo community, from tools/zenodo_<community>.json (written by zenodo_community.py).
    Sizes and md5 as Zenodo gives them; the license is each record's own. seen holds record ids already used, so a
    record in two communities is indexed once. Kind: 'wells' for logs, 'reports' for the ODP and DSDP volumes,
    technical notes and manuals, 'cores' for the rest (core, sample and shipboard data)."""
    z = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), f'zenodo_{community}.json')))
    rows, skipped = [], collections.Counter()
    for r in z['records']:
        if r['conceptdoi'] == LILY_CONCEPT_DOI:
            skipped['a version of LILY, indexed under lily'] += 1
            continue
        if r['id'] in seen:
            skipped['already indexed from another community'] += 1
            continue
        seen.add(r['id'])
        kind = ('wells' if sid == 'ldeo-logdb' or LWD.search(r['title']) else
                'reports' if REPORT.search(r['title']) else 'cores')
        for f in r['files']:
            rows.append(dict(file_id=f'{prefix}{r["id"]}/{f["key"]}', source=sid, kind=kind, dataset=r['title'], url=f['url'],
                             bytes=str(f['size']), stable='yes', local_path=f'{sid}/{r["id"]}/{f["key"]}',
                             license=LICENSE_TEXT[r['license']], regions={'global'}, surveys=set(), include=set(),
                             checksum=f['checksum']))
    for why, n in skipped.items():
        print(f'zenodo {community}: left out {n} records ({why})')
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--corpus', required=True)
    ap.add_argument('--mirror', required=True)
    ap.add_argument('--gulf', required=True)
    a = ap.parse_args()
    sources = {r['source_id']: r for r in csv.DictReader(open(os.path.join(DATA, 'sources.csv')))}

    # ------------------------------------------------------------ seismic volumes and archives
    man = [r for r in csv.DictReader(open(os.path.join(a.corpus, 'manifest.csv')))
           if r['section'] == 'main' and r['source'] in SRC and r['include'] in ('yes', 'decide') and r['archive_url'].endswith('.zip')]
    mirror_vols = {}
    for line in open(os.path.join(a.mirror, 'volumes.jsonl')):
        d = json.loads(line)
        mirror_vols[(SRC[d['source']], d['survey_id'], d['volume'])] = d
    vols, archives = [], collections.OrderedDict()
    for r in man:
        sid = SRC[r['source']]
        members = [m for m in r['members'].split(';') if m]
        vname = volume_name(members) or r['survey_id']
        fid = file_id_for(r)
        reg = region(r)
        mv = mirror_vols.get((sid, r['survey_id'], vname))
        vols.append(dict(source=sid, survey_id=r['survey_id'], volume=vname, survey_name=r['survey_name'], region=reg,
                         location=r['location'], year=r['year'], stack_type=r['stack_type'], domain=r['domain'], role=r['role'],
                         include=r['include'], flags=r['flags'], members=r['members'], file_count=r['file_count'],
                         volume_bytes=r['volume_bytes'], volume_bytes_exact=r['volume_bytes_exact'], file_id=fid,
                         license=sources[sid]['license'], landing_page=r['landing_page'], doi=NAMSS_DOI if sid == 'namss' else '',
                         on_reference_mirror='yes' if mv else 'no'))
        ar = archives.setdefault(fid, dict(file_id=fid, source=sid, kind='seismic',
                                           dataset='NAMSS 3D survey archive' if sid == 'namss' else 'SARIG 3D seismic package',
                                           url=r['archive_url'], bytes=r['archive_bytes'], stable='yes', local_path=local_path_for(r),
                                           license=sources[sid]['license'], regions=set(), surveys=set(), include=set(),
                                           checksum=''))
        ar['regions'].add(reg)
        ar['surveys'].add(r['survey_id'])
        ar['include'].add(r['include'])
        if sid == 'namss' and r['checksums'].startswith('etag'):
            ar['checksum'] = 'etag:' + r['checksums'][5:].strip()
        elif sid == 'sarig':
            ar['checksum'] = 'members:crc32'
    write_csv(os.path.join(DATA, 'seismic', 'volumes.csv'), vols, list(vols[0]))

    # ------------------------------------------------------------ members: zip listings and the mirror
    mirror_files = {}
    for r in csv.DictReader(open(os.path.join(a.mirror, 'files.csv'))):
        mirror_files[(r['archive_url'], r['archive_member'])] = r
    members = []
    sarig_zip = json.load(open(os.path.join(a.corpus, 'crawl', 'sarig_zip_members.json')))
    namss_pages = {}
    for p in glob.glob(os.path.join(a.corpus, 'crawl', 'namss', '*.json')):
        d = json.load(open(p))
        for u in d.get('data_urls', []):
            namss_pages[u] = d

    def kind(name, size):
        if SEGY.search(name) or SEGY_ZIP.search(name):
            return 'segy'
        return 'side' if size is None or size <= MAX_SIDE else 'other'

    def size_text(s):
        m = re.match(r'([\d.]+)\s*(bytes|KB|MB|GB|TB)', s.replace('\xa0', ' '))
        return int(float(m.group(1)) * {'bytes': 1, 'KB': 1024, 'MB': 1024 ** 2, 'GB': 1024 ** 3, 'TB': 1024 ** 4}[m.group(2)]) if m else None

    for fid, ar in archives.items():
        u = ar['url']
        seen = set()
        if ar['source'] == 'sarig':
            for m in sarig_zip.get(u, {}).get('members', []):
                mf = mirror_files.get((u, m['name']))
                members.append(dict(file_id=fid, member=m['name'], kind=kind(m['name'], m['size']), bytes=m['size'], crc32=m['crc'],
                                    sha256=mf['sha256'] if mf else '', record='zip index' + (' and reference mirror' if mf else '')))
                seen.add(m['name'])
        else:
            for m in namss_pages.get(u, {}).get('files', []):
                mf = mirror_files.get((u, m['name']))
                if mf:
                    members.append(dict(file_id=fid, member=m['name'], kind=kind(m['name'], int(mf['bytes'])), bytes=mf['bytes'],
                                        crc32=mf['crc32'], sha256=mf['sha256'], record='reference mirror'))
                else:
                    sz = size_text(m['size'])
                    members.append(dict(file_id=fid, member=m['name'], kind=kind(m['name'], sz), bytes=sz or '', crc32='', sha256='',
                                        record='catalog listing, rounded'))
                seen.add(m['name'])
        for (au, am), mf in mirror_files.items():
            if au == u and am not in seen:   # members inside nested zips, or not in the listing
                members.append(dict(file_id=fid, member=am, kind=kind(am.split('!')[-1], int(mf['bytes'])), bytes=mf['bytes'],
                                    crc32=mf['crc32'], sha256=mf['sha256'], record='reference mirror'))
    write_csv(os.path.join(DATA, 'seismic', 'members.csv'), members, ['file_id', 'member', 'kind', 'bytes', 'crc32', 'sha256', 'record'])

    # ------------------------------------------------------------ headers from the reference mirror
    hdr = []
    for (sid, survey, vname), d in sorted(mirror_vols.items()):
        il, xl, c = d['inline_range'] or {}, d['crossline_range'] or {}, d['coordinates'] or {}
        si = d['sample_interval']
        fixes = []
        hb = d['header_bytes']
        if hb.get('inline') and (hb['inline'], hb['crossline']) != (189, 193):
            fixes.append(f'inline/crossline at bytes {hb["inline"]}/{hb["crossline"]}')
        if c.get('x_byte') and (c['x_byte'], c['y_byte']) != (181, 185):
            fixes.append(f'coordinates at bytes {c["x_byte"]}/{c["y_byte"]}')
        if any(v > 32767 for v in si.get('binary_header', [])):
            fixes.append('sample interval above 32767 (read as unsigned)')
        if len(si.get('binary_header', [])) and si.get('trace_headers') and si['binary_header'] != si['trace_headers']:
            fixes.append('binary and trace header sample intervals differ')
        if not d['opened_with_segyio']:
            fixes.append('segyio cannot infer the geometry; use the ranges here')
        hdr.append(dict(source=sid, survey_id=survey, volume=vname, files=d['n_files'], bytes=d['bytes'], traces=d['traces'],
                        opened_with_segyio=d['opened_with_segyio'], inline_byte=hb.get('inline'), crossline_byte=hb.get('crossline'),
                        inline_min=il.get('min'), inline_max=il.get('max'), inline_step=il.get('step'),
                        crossline_min=xl.get('min'), crossline_max=xl.get('max'), crossline_step=xl.get('step'),
                        samples=';'.join(map(str, d['samples'])), sample_interval_binary=';'.join(map(str, si.get('binary_header', []))),
                        sample_interval_traces=';'.join(map(str, si.get('trace_headers', []))),
                        format_code=';'.join(map(str, d['format_codes'])), endianness=';'.join(d['endianness']),
                        segy_revision=';'.join(d['revisions']), ext_text_headers=';'.join(map(str, d['ext_text_headers'])),
                        x_byte=c.get('x_byte'), y_byte=c.get('y_byte'), coordinate_scalar=';'.join(map(str, c.get('scalar_values', []))),
                        x_min=(c.get('x_range') or [None, None])[0], x_max=(c.get('x_range') or [None, None])[1],
                        y_min=(c.get('y_range') or [None, None])[0], y_max=(c.get('y_range') or [None, None])[1],
                        crs_text_header=' | '.join(d['text_header_crs'])[:600],
                        crs_catalog='; '.join(f'{k}: {v}' for k, v in (d.get('catalogue_crs') or {}).items()),
                        processing_text_header=' | '.join(d['text_header_processing'])[:600],
                        header_fixes='; '.join(fixes), problems=' | '.join(d['problems'])[:1000], n_problems=len(d['problems'])))
    write_csv(os.path.join(DATA, 'seismic', 'headers.csv'), hdr, list(hdr[0]))

    grids = json.load(open(os.path.join(a.mirror, 'volume_grids.json')))
    # Second grading pass: the lambda step graded on outline containment of the sampled traces. Also require a
    # small misfit for 'check', and grid corners near the survey outline (a fit from a few lines can extrapolate
    # wildly when stretched to the full inline/crossline ranges).
    outl_all = json.load(open(os.path.join(a.corpus, 'crawl', 'namss_outlines.json')))
    regraded = {}
    for g in grids:
        c = g.get('corners_lonlat_nad27')
        if not c:
            continue
        p = outl_all[g['survey_id']]
        lo, la = [q[0] for q in p], [q[1] for q in p]
        excess = max(max(0, min(lo) - x, x - max(lo), min(la) - y, y - max(la)) for x, y in c)
        g['corner_excess_deg'] = round(excess, 3)
        q = g['quality']
        if q == 'good' and excess > 0.05:
            q = 'check'
        if q == 'check' and (g['fit_rms'] >= 50 or excess > 0.3):
            q = 'unresolved'
        g['quality'] = q
        regraded[(g['survey_id'], g['volume'])] = q
    gcols = ['survey_id', 'volume', 'status', 'quality', 'crs', 'crs_named_in_text_header', 'frac_traces_inside_outline',
             'corner_excess_deg', 'fit_rms', 'fit_max', 'n_traces_sampled', 'x0', 'x_per_inline', 'x_per_crossline', 'y0', 'y_per_inline', 'y_per_crossline']
    for g in grids:
        if g.get('affine_x'):
            g.update(x_per_inline=g['affine_x'][0], x_per_crossline=g['affine_x'][1], x0=g['affine_x'][2],
                     y_per_inline=g['affine_y'][0], y_per_crossline=g['affine_y'][1], y0=g['affine_y'][2])
    write_csv(os.path.join(DATA, 'seismic', 'grids.csv'), grids, gcols)

    # ------------------------------------------------------------ footprints
    feats = []
    outl = json.load(open(os.path.join(a.corpus, 'crawl', 'namss_outlines.json')))
    in_index = {v['survey_id'] for v in vols if v['source'] == 'namss'}
    for sid, poly in sorted(outl.items()):
        if sid in in_index and poly and isinstance(poly[0], list) and isinstance(poly[0][0], (int, float)):
            ring = [list(p) for p in poly] + ([list(poly[0])] if poly[0] != poly[-1] else [])
            feats.append(dict(type='Feature', geometry=dict(type='Polygon', coordinates=[ring]),
                              properties=dict(source='namss', survey_id=sid, footprint='NAMSS navigation outline', datum='NAD27')))
    for g in grids:
        if g.get('corners_lonlat_nad27') and g.get('quality') in ('good', 'check'):
            ring = g['corners_lonlat_nad27'] + [g['corners_lonlat_nad27'][0]]
            feats.append(dict(type='Feature', geometry=dict(type='Polygon', coordinates=[ring]),
                              properties=dict(source='namss', survey_id=g['survey_id'], volume=g['volume'],
                                              footprint='trace-header grid corners', datum='NAD27', quality=g['quality'])))
    pk = json.load(open(os.path.join(a.corpus, 'crawl', 'sarig_packages.json')))
    sar = {v['survey_id'] for v in vols if v['source'] == 'sarig'}
    for name, p in pk.items():
        if name in sar and p.get('spatial'):
            try:
                geom = json.loads(p['spatial'])
            except ValueError:
                continue
            feats.append(dict(type='Feature', geometry=geom, properties=dict(source='sarig', survey_id=name,
                                                                             footprint='SARIG catalog extent (often a coarse box)', datum='as given by SARIG (GDA94 or WGS84)')))
    with open(os.path.join(DATA, 'seismic', 'footprints.geojson'), 'w') as f:
        json.dump(dict(type='FeatureCollection', features=feats), f)
    print(f'data/seismic/footprints.geojson: {len(feats)} features')

    # ------------------------------------------------------------ well files (direct downloads)
    src_map = {'boem': 'boem-data-center', 'edx': 'netl-edx'}
    wf = []
    for r in csv.DictReader(open(os.path.join(a.gulf, 'manifest.tsv')), delimiter='\t'):
        s = 'ldeo-logdb' if r['source'].startswith('ldeo') else src_map[r['source']]
        name = os.path.basename(r['file'])
        if s == 'ldeo-logdb' and not re.search(r'standard|std-', name):
            continue   # LWD image zips: fetched by accident in the Gulf work, not part of the index
        if name.endswith('.pdf') or name.startswith('ogora'):
            continue   # release-list PDFs and monthly production: kept out to stay with wells and outcomes
        sub = r['file'].split('/', 2)[2] if s == 'ldeo-logdb' else name
        fid = {'boem-data-center': 'boem:', 'netl-edx': 'edx:', 'ldeo-logdb': 'ldeo:'}[s] + sub
        wf.append(dict(file_id=fid, source=s, kind='wells', dataset=sub, url=r['url'], bytes=r['bytes'], stable='no' if s == 'boem-data-center' else 'yes',
                       local_path=f'{s}/{sub}', license=sources[s]['license'], regions={'gulf-of-mexico'}, surveys=set(), include=set(),
                       checksum='sha256:' + r['sha256']))
    wf.append(dict(file_id='boem:FRSWellDataRawData.zip', source='boem-data-center', kind='wells', dataset='FRS file inventory (public)',
                   url='https://www.data.boem.gov/Other/Files/FRSWellDataRawData.zip', bytes='49336683', stable='no',
                   local_path='boem-data-center/FRSWellDataRawData.zip', license=sources['boem-data-center']['license'],
                   regions={'gulf-of-mexico', 'pacific', 'alaska', 'atlantic'}, surveys=set(), include=set(), checksum=''))
    seen = set()
    rows = (list(archives.values()) + wf + lily_rows(sources) + zenodo_rows('logdb', 'ldeo-logdb', 'ldeo:zenodo/', seen)
            + zenodo_rows('iodp', 'iodp-zenodo', 'iodp:', seen))
    for r in rows:
        r['regions'] = ';'.join(sorted(r['regions']))
        r['surveys'] = ';'.join(sorted(r['surveys']))
        r['include'] = ';'.join(sorted(r['include']))
    write_csv(os.path.join(DATA, 'files.csv'), rows, ['file_id', 'source', 'kind', 'dataset', 'url', 'bytes', 'checksum', 'stable',
                                                      'regions', 'surveys', 'include', 'local_path', 'license'])

    # ------------------------------------------------------------ Gulf wells
    W = list(csv.DictReader(open(os.path.join(a.gulf, 'explo_wells.csv'))))
    flags = {}
    for r in csv.DictReader(open(os.path.join(a.gulf, 'wells_namss.csv'))):
        flags[r['api']] = (r['has_checkshot'], r['has_paleo'])
    frs_rows = list(csv.DictReader(open(os.path.join(a.mirror, 'boem_frs_raw_logs.csv'))))
    frs_by = collections.defaultdict(list)
    for r in frs_rows:
        frs_by[r['api10']].append(int(r['bytes']))
    ties = []
    for t in csv.DictReader(open(os.path.join(a.mirror, 'well_volume_ties.csv'))):
        q = regraded.get((t['survey_id'], t['volume']), t['grid_quality'])
        if q != 'unresolved':
            t['grid_quality'] = q
            ties.append(t)
    tie_n = collections.Counter(t['api'] for t in ties if t.get('bottom_inside_grid') == 'True' or t.get('surface_inside_grid') == 'True')
    keep = ['api', 'well_name', 'operator', 'field', 'spud', 'td_date', 'type', 'status', 'rkb_ft', 'md_ft', 'tvd_ft', 'wd_ft',
            'surf_lon', 'surf_lat', 'bot_lon', 'bot_lat', 'surf_area_block', 'bot_area_block', 'spud_year', 'setting',
            'discovery', 'field_discovery', 'field_mmboe', 'in_namss', 'surveys', 'first_survey_year', 'after_survey']
    out = []
    for w in W:
        r = {k: w[k] for k in keep}
        r['has_checkshot'], r['has_paleo'] = flags.get(w['api'], ('', ''))
        b = frs_by.get(w['api'][:10], [])
        r['frs_raw_logs'] = len(b)
        r['frs_raw_bytes'] = sum(b)
        r['frs_raw_logs_le_100mb'] = sum(1 for x in b if x <= 100e6)
        r['volumes_tied'] = tie_n.get(w['api'], 0)
        out.append(r)
    write_csv(os.path.join(DATA, 'wells', 'gulf_exploration_wells.csv'), out, list(out[0]))
    write_csv(os.path.join(DATA, 'wells', 'gulf_well_volume_ties.csv'), ties, list(ties[0]) if ties else ['api'])
    write_csv(os.path.join(DATA, 'wells', 'boem_frs_raw_logs.csv'), frs_rows, list(frs_rows[0]))


if __name__ == '__main__':
    main()
