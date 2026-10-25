"""List the files of the first bucket release (0.1) and write docs/starter_release.csv.

    python3 tools/starter_release.py --corpus /mnt/nas/seismic-corpus
    python3 tools/starter_release.py --corpus <copy of log/ and the metadata.json files> --listing nas_files.tsv

--corpus is the seismic corpus folder (<source>/<survey_id>/<files> + metadata.json, log/files.csv,
log/jobs.jsonl). --listing is the output of `find sarig namss -type f -printf "%p\t%s\n"` run in the corpus
folder; give it when the SEG-Y files are not on this machine. The script only reads.

The release holds three parts, chosen by rule:
  sarig-3d               every SARIG 3D survey in the corpus whose archive was unpacked and checked
  namss-pacific-alaska   every NAMSS survey in the corpus from offshore California and the Beaufort Sea
  namss-gulf-psdm        NAMSS Gulf of Mexico surveys whose volumes are all include=yes, all depth migrated,
                         all opened by segyio with full geometry, and that have at least MIN_WELLS exploration
                         wells spudded after the survey year inside the survey outline
plus the index tables in data/. Files under data/original/ are the source's files, byte for byte. Everything
we wrote (metadata.json, the index) goes under metadata/.
"""
import argparse, collections, csv, hashlib, json, os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, 'data')
OUT = os.path.join(ROOT, 'docs', 'starter_release.csv')
RELEASE = '0.1'
MIN_WELLS = 40
SOURCE_ID = {'USGS NAMSS': 'namss', 'SARIG (South Australia)': 'sarig'}
INDEX_LICENSE = 'CC BY 4.0 (index tables, see data/LICENSE.md)'
COLUMNS = ['release', 'part', 'source', 'survey_id', 'region', 'kind', 'corpus_path', 's3_key', 'bytes', 'crc32',
           'sha256', 'source_url', 'license']


def read_csv(path):
    with open(path, newline='', encoding='utf-8') as f:
        return list(csv.DictReader(f))


def job_status(corpus):
    """Last status of each survey's archive job (a later run overrides an earlier one)."""
    last, surveys = {}, {}
    with open(os.path.join(corpus, 'log', 'jobs.jsonl')) as f:
        for line in f:
            j = json.loads(line)
            last[j['url']] = j['status']
            if 'surveys' in j:   # records of archives put off for lack of disk carry only the URL
                s = j['surveys']
                surveys[j['url']] = s if isinstance(s, list) else s.split(';')
    return {s: last[u] for u, ss in surveys.items() for s in ss}


def listing(corpus, path):
    """corpus-relative path -> bytes, for sarig/ and namss/."""
    out = {}
    if path:
        with open(path) as f:
            for line in f:
                p, b = line.rstrip('\n').split('\t')
                out[p] = int(b)
        return out
    for top in ('sarig', 'namss'):
        for d, _, names in os.walk(os.path.join(corpus, top)):
            for n in names:
                p = os.path.join(d, n)
                out[os.path.relpath(p, corpus)] = os.path.getsize(p)
    return out


def wells_after(volumes):
    """Survey id -> exploration wells spudded after the survey year, inside its NAMSS outline."""
    year = {}
    for v in volumes:
        year.setdefault(v['survey_id'], v['year'])
    n = collections.Counter()
    for w in read_csv(os.path.join(DATA, 'wells', 'gulf_exploration_wells.csv')):
        for s in filter(None, (w['surveys'] or '').split(';')):
            if year.get(s) and w['spud_year'] and float(w['spud_year']) > float(year[s]):
                n[s] += 1
    return n


def gulf_psdm(corpus, surveys, region, n_wells):
    keep = []
    for s in surveys:
        if region.get(s) != 'gulf-of-mexico' or n_wells[s] < MIN_WELLS:
            continue
        with open(os.path.join(corpus, 'namss', s, 'metadata.json')) as f:
            vols = json.load(f)['volumes'].values()
        if vols and all(v['manifest']['include'] == 'yes' and v['manifest']['domain'] == 'depth'
                        and v['opened_with_segyio'] for v in vols):
            keep.append(s)
    return keep


def sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for b in iter(lambda: f.read(1 << 20), b''):
            h.update(b)
    return h.hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--corpus', default='/mnt/nas/seismic-corpus')
    ap.add_argument('--listing', help='find output (path TAB bytes) when the corpus files are not local')
    a = ap.parse_args()

    sources = {r['source_id']: r for r in read_csv(os.path.join(DATA, 'sources.csv'))}
    volumes = read_csv(os.path.join(DATA, 'seismic', 'volumes.csv'))
    region = {v['survey_id']: v['region'] for v in volumes}
    status = job_status(a.corpus)
    on_disk = listing(a.corpus, a.listing)
    logged = {}
    for r in read_csv(os.path.join(a.corpus, 'log', 'files.csv')):
        logged[r['path']] = r   # a re-run logs the path again; keep the last

    done = collections.defaultdict(list)
    for p in on_disk:
        top, survey = p.split('/')[:2]
        if p.endswith('/metadata.json') and status.get(survey) == 'done':
            done[top].append(survey)
    n_wells = wells_after(volumes)
    namss = sorted(done['namss'])
    parts = {
        'sarig-3d': [('sarig', s) for s in sorted(done['sarig'])],
        'namss-pacific-alaska': [('namss', s) for s in namss if region.get(s) in ('pacific', 'alaska')],
        'namss-gulf-psdm': [('namss', s) for s in gulf_psdm(a.corpus, namss, region, n_wells)],
    }

    rows, problems = [], []
    for part, members in parts.items():
        for src, survey in members:
            prefix = f'{src}/{survey}/'
            lic = sources[src]['license']
            for p in sorted(x for x in on_disk if x.startswith(prefix)):
                rel = p[len(prefix):]
                if rel.endswith('.part'):
                    problems.append(f'skipped unfinished file {p}')
                    continue
                if rel == 'metadata.json':
                    rows.append(dict(part=part, source=src, survey_id=survey, kind='metadata', corpus_path=p,
                                     s3_key=f'metadata/surveys/source={src}/survey={survey}/metadata.json',
                                     bytes=on_disk[p], license=INDEX_LICENSE))
                    continue
                g = logged.get(p)
                if g is None:
                    problems.append(f'not in log/files.csv: {p}')
                elif int(g['bytes']) != on_disk[p]:
                    problems.append(f'size differs from log/files.csv: {p}')
                kind = 'segy' if g and g['volume'] else 'side'
                rows.append(dict(part=part, source=src, survey_id=survey, kind=kind, corpus_path=p,
                                 s3_key=f'data/original/source={src}/survey={survey}/{rel}', bytes=on_disk[p],
                                 crc32=g['crc32'] if g else '', sha256=g['sha256'] if g else '',
                                 source_url=g['archive_url'] if g else '', license=lic))
    for d, _, names in os.walk(DATA):
        for n in sorted(names):
            p = os.path.join(d, n)
            rel = os.path.relpath(p, DATA)
            rows.append(dict(part='index', source='', survey_id='', kind='index', corpus_path='',
                             s3_key=f'metadata/index/{rel}', bytes=os.path.getsize(p), sha256=sha256(p),
                             license=INDEX_LICENSE))
    for r in rows:
        r['release'] = RELEASE
        r['region'] = region.get(r['survey_id'], '')
    rows.sort(key=lambda r: (r['part'] == 'index', r['part'], r['survey_id'], r['s3_key']))
    with open(OUT, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, COLUMNS)
        w.writeheader()
        w.writerows(rows)

    by = collections.defaultdict(lambda: [set(), 0, 0])
    for r in rows:
        t = by[r['part']]
        t[0].add(r['survey_id'])
        t[1] += 1
        t[2] += int(r['bytes'])
    for part, (s, n, b) in by.items():
        print(f'{part}: {len(s - {""})} surveys, {n} files, {b / 1e9:.1f} GB')
    print(f'total: {len(rows)} files, {sum(int(r["bytes"]) for r in rows) / 1e9:.1f} GB')
    for p in problems:
        print('note:', p)
    print('wrote', OUT)


if __name__ == '__main__':
    main()
