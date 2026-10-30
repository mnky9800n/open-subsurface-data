"""osd: list, size up and fetch open subsurface data from the original archives.

    osd sources                         what the index covers and how each source is reached
    osd list     [filters]              the files a selection would fetch
    osd estimate [filters] --dest DIR   how much disk a selection needs, against the free space at DIR
    osd fetch    [filters] --dest DIR   download, resume, verify; optional --extract
    osd verify   --dest DIR             check files already fetched
    osd cite     --dest DIR             BibTeX for this repository and the sources of the files at DIR
    osd frs plan / osd frs check        BOEM well logs, which need your own Login.gov account
"""
import argparse
import collections
import datetime
import json
import os
import shutil
import sys

from . import __version__, checks, cite, frs, net
from .adapters import adapter
from .index import Index, human, select, split

MARGIN = 20e9   # keep this much disk free beyond the estimate


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='seconds')


def log(msg):
    print(msg, flush=True)


def csv_arg(v):
    return [x.strip() for x in v.split(',') if x.strip()] if v else None


def add_filters(p):
    p.add_argument('--source', type=csv_arg, help='source ids, comma separated (see: osd sources)')
    p.add_argument('--region', type=csv_arg, help='regions, comma separated (gulf-of-mexico, pacific, alaska, south-australia)')
    p.add_argument('--survey', type=csv_arg, help='survey ids, comma separated (overrides --include)')
    p.add_argument('--file', type=csv_arg, help='file ids from osd list, comma separated (overrides --include)')
    p.add_argument('--kind', type=csv_arg, help='seismic, wells, cores or reports')
    p.add_argument('--include', type=csv_arg, default=['yes'],
                   help="seismic archives to keep by their volumes' include flag: yes (default), decide, all")


def rows_for(a, ix):
    return select(ix, source=a.source, region=a.region, survey=a.survey, kind=a.kind, include=a.include, file_ids=a.file)


# ---------------------------------------------------------------- state at the destination

def state_path(dest):
    return os.path.join(dest, '.osd', 'state.jsonl')


def load_state(dest):
    st = {}
    p = state_path(dest)
    if os.path.exists(p):
        for line in open(p):
            d = json.loads(line)
            st[d['file_id']] = d
    return st


def save_state(dest, rec):
    os.makedirs(os.path.dirname(state_path(dest)), exist_ok=True)
    with open(state_path(dest), 'a') as f:
        f.write(json.dumps(rec) + '\n')


def is_done(st, dest, r):
    d = st.get(r['file_id'])
    p = os.path.join(dest, r['local_path'])
    return bool(d and d.get('verified') and os.path.exists(p) and os.path.getsize(p) == d['bytes'])


def extract_bytes(ix, r, roles):
    vols = [v for v in ix.volumes if v['file_id'] == r['file_id'] and v['role'] in roles]
    return sum(int(v['volume_bytes'] or 0) for v in vols)


# ---------------------------------------------------------------- commands

def cmd_sources(a):
    ix = Index.load()
    files = collections.defaultdict(lambda: [0, 0])
    for r in ix.files:
        files[r['source']][0] += 1
        files[r['source']][1] += int(r['bytes'] or 0)
    print(f'{"source_id":<20} {"access":<11} {"fetch":<13} {"files":>6} {"size":>10}  license')
    for sid, s in ix.sources.items():
        n, b = files.get(sid, (0, 0))
        print(f'{sid:<20} {s["access"]:<11} {s["fetch_support"]:<13} {n:>6} {human(b) if b else "":>10}  {s["license"][:60]}')
    print('\nfetch: direct = osd fetches it; request-list = osd writes the request, you submit it; listed = index entry only')


def cmd_list(a):
    ix = Index.load()
    rows = rows_for(a, ix)
    if a.volumes:
        ids = {r['file_id'] for r in rows}
        vols = [v for v in ix.volumes if v['file_id'] in ids]
        print(f'{"source":<7} {"survey":<16} {"volume":<34} {"role":<10} {"include":<7} {"size":>10}  stack')
        for v in vols:
            print(f'{v["source"]:<7} {v["survey_id"]:<16} {v["volume"][:34]:<34} {v["role"]:<10} {v["include"]:<7} '
                  f'{human(int(v["volume_bytes"] or 0)):>10}  {v["stack_type"][:40]}')
        print(f'{len(vols)} volumes')
        return
    print(f'{"file_id":<34} {"region":<16} {"size":>10}  surveys')
    for r in rows[:a.limit] if a.limit else rows:
        sv = split(r['surveys'])
        print(f'{r["file_id"][:34]:<34} {(split(r["regions"]) or [""])[0]:<16} {human(int(r["bytes"] or 0)):>10}  '
              f'{";".join(sv[:3])}{" +%d" % (len(sv) - 3) if len(sv) > 3 else ""}')
    if a.limit and len(rows) > a.limit:
        print(f'... {len(rows) - a.limit} more (use --limit 0 for all)')
    print(f'{len(rows)} files, {human(sum(int(r["bytes"] or 0) for r in rows))}')
    listed = [s for s in (a.source or []) if s in ix.sources and not adapter(s).fetchable]
    for s in listed:
        print('\n' + adapter(s).route(ix.sources[s]))


def plan_size(a, ix, rows):
    st = load_state(a.dest) if a.dest and os.path.isdir(a.dest) else {}
    roles = {'primary', 'additional'} if a.roles == 'all' else {a.roles}
    by = collections.defaultdict(lambda: dict(files=0, bytes=0, todo=0, extract=0))
    for r in rows:
        s = by[r['source']]
        s['files'] += 1
        s['bytes'] += int(r['bytes'] or 0)
        if not is_done(st, a.dest or '', r):
            part = os.path.join(a.dest, r['local_path'] + '.part') if a.dest else ''
            have = os.path.getsize(part) if part and os.path.exists(part) else 0
            s['todo'] += max(int(r['bytes'] or 0) - have, 0)
        if getattr(a, 'extract', False) and r['kind'] == 'seismic':
            s['extract'] += extract_bytes(ix, r, roles)
    return by


def cmd_estimate(a):
    ix = Index.load()
    rows = [r for r in rows_for(a, ix) if adapter(r['source']).fetchable]
    by = plan_size(a, ix, rows)
    print(f'{"source":<20} {"files":>6} {"download":>11} {"still to get":>13} {"unpacked SEG-Y":>15}')
    tot = collections.Counter()
    for src, s in sorted(by.items()):
        print(f'{src:<20} {s["files"]:>6} {human(s["bytes"]):>11} {human(s["todo"]):>13} {human(s["extract"]) if s["extract"] else "-":>15}')
        tot.update(s)
    print(f'{"total":<20} {tot["files"]:>6} {human(tot["bytes"]):>11} {human(tot["todo"]):>13} {human(tot["extract"]) if tot["extract"] else "-":>15}')
    need = tot['todo'] + tot['extract']
    if a.dest:
        free = shutil.disk_usage(existing_parent(a.dest)).free
        ok = need + MARGIN <= free
        print(f'\nfree at {a.dest}: {human(free)}; needed: {human(need)} plus a {human(MARGIN)} margin -> {"fits" if ok else "DOES NOT FIT"}')
    if a.extract:
        print('unpacked size counts the selected SEG-Y volumes only; NAMSS sizes are rounded from the catalog')
    return 0


def existing_parent(p):
    p = os.path.abspath(p)
    while not os.path.exists(p):
        p = os.path.dirname(p)
    return p


def cmd_fetch(a):
    net.need_curl()
    ix = Index.load(with_members=True)
    rows = rows_for(a, ix)
    skipped = sorted({r['source'] for r in rows if not adapter(r['source']).fetchable})
    rows = [r for r in rows if adapter(r['source']).fetchable]
    for s in a.source or []:
        if s in ix.sources and not adapter(s).fetchable:
            log(f'not fetched by osd: {s}\n' + adapter(s).route(ix.sources[s]))
    if skipped:
        log(f'skipped (no direct download): {", ".join(skipped)}')
    if not rows:
        log('nothing selected')
        return 1
    os.makedirs(a.dest, exist_ok=True)
    st = load_state(a.dest)
    todo = [r for r in rows if not is_done(st, a.dest, r)]
    roles = {'primary', 'additional'} if a.roles == 'all' else {a.roles}
    by = plan_size(a, ix, rows)
    need = sum(s['todo'] + s['extract'] for s in by.values())
    free = shutil.disk_usage(a.dest).free
    log(f'{len(rows)} files selected, {len(rows) - len(todo)} already verified at {a.dest}; '
        f'{human(need)} to write, {human(free)} free')
    if a.max_bytes is not None and need > a.max_bytes:
        log(f'stopping: the selection needs {human(need)}, above --max-gb {a.max_bytes / 1e9:g}')
        return 1
    if need + MARGIN > free:
        log(f'stopping: not enough disk (need {human(need)} plus a {human(MARGIN)} margin)')
        return 1
    if not todo:
        log('nothing to fetch: every selected file is already verified')
        return 0
    if a.dry_run:
        for r in todo:
            log(f'would fetch {r["file_id"]} ({human(int(r["bytes"] or 0))}) -> {r["local_path"]}')
        return 0
    bad = 0
    for i, r in enumerate(todo, 1):
        log(f'[{i}/{len(todo)}] {r["file_id"]} {human(int(r["bytes"] or 0))}')
        rec = fetch_one(a, ix, r, roles)
        save_state(a.dest, rec)
        if not rec['verified']:
            bad += 1
    write_attribution(a.dest, ix, load_state(a.dest))
    write_manifest(a.dest, load_state(a.dest))
    write_citation(a.dest, load_state(a.dest))
    log(f'done: {len(todo) - bad} verified, {bad} with problems. Log: {state_path(a.dest)}')
    return 1 if bad else 0


def fetch_one(a, ix, r, roles):
    ad = adapter(r['source'])
    path = os.path.join(a.dest, r['local_path'])
    rec = dict(file_id=r['file_id'], source=r['source'], url=r['url'], path=r['local_path'], started=now(), verified=False)
    h = net.head(r['url'])
    errors, notes = ad.identity(r, h)
    rec.update(etag=h.get('etag'), last_modified=h.get('last-modified'))
    if errors:
        rec.update(errors=errors, notes=notes, finished=now())
        log('  ' + '; '.join(errors))
        return rec
    want = int(h['content-length']) if h.get('content-length') else (int(r['bytes']) if r['bytes'] else None)
    part = path + '.part'
    try:
        net.download(r['url'], part, want, lambda m: log('  ' + m))
        os.replace(part, path)
        os.chmod(path, 0o444)   # originals stay as fetched
    except RuntimeError as e:
        rec.update(errors=[str(e)], notes=notes, finished=now())
        log(f'  {e}')
        return rec
    members = ix.members.get(r['file_id'], [])
    errs, more, digest = ad.verify(r, path, members, a.deep)
    rec.update(bytes=os.path.getsize(path), sha256=digest, errors=errs, notes=notes + more)
    if not errs and a.extract and r['kind'] == 'seismic':
        vols = [v for v in ix.volumes if v['file_id'] == r['file_id']]
        names = ad.extract_members(members, vols, roles)
        out = os.path.join(a.dest, 'extracted', r['source'], os.path.splitext(os.path.basename(r['local_path']))[0])
        try:
            recs = checks.extract(path, names, out, os.path.join(a.dest, '.osd'))
            known = {m['member']: m['sha256'] for m in members if m['sha256']}
            for x in recs:
                if x['member'] in known and known[x['member']] != x['sha256']:
                    errs.append(f'{x["path"]}: SHA-256 differs from the reference copy')
            rec['extracted'] = [dict(path=os.path.relpath(os.path.join(out, x['path']), a.dest), bytes=x['bytes'],
                                     crc32=x['crc32'], sha256=x['sha256']) for x in recs]
        except Exception as e:
            errs.append(f'extract failed: {type(e).__name__}: {e}')
    rec.update(verified=not errs, finished=now())
    for n in rec['notes']:
        log(f'  note: {n}')
    log('  ' + ('verified' if not errs else 'PROBLEM: ' + '; '.join(errs[:5])))
    return rec


def cmd_verify(a):
    ix = Index.load(with_members=True)
    st = load_state(a.dest)
    rows = {r['file_id']: r for r in ix.files}
    bad = 0
    for fid, d in st.items():
        r = rows.get(fid)
        path = os.path.join(a.dest, d['path'])
        if r is None or not os.path.exists(path):
            log(f'{fid}: {"not in the index" if r is None else "file missing"}')
            bad += 1
            continue
        errs, notes, digest = adapter(r['source']).verify(r, path, ix.members.get(fid, []), a.deep)
        if d.get('sha256') and digest != d['sha256']:
            errs.append('SHA-256 changed since it was fetched')
        log(f'{fid}: {"ok" if not errs else "; ".join(errs[:5])}')
        bad += bool(errs)
    log(f'{len(st) - bad} ok, {bad} with problems')
    return 1 if bad else 0


def write_manifest(dest, st):
    with open(os.path.join(dest, 'MANIFEST.tsv'), 'w') as f:
        f.write('file_id\tpath\tbytes\tsha256\turl\tverified\tfetched\n')
        for d in st.values():
            f.write(f'{d["file_id"]}\t{d["path"]}\t{d.get("bytes", "")}\t{d.get("sha256", "")}\t{d["url"]}\t{d["verified"]}\t{d.get("finished", "")}\n')


def used_sources(st):
    """Sources with verified files in a fetch log, and the last day files from each were fetched."""
    accessed = {}
    for d in st.values():
        if d.get('verified'):
            accessed[d['source']] = max(accessed.get(d['source'], ''), (d.get('finished') or '')[:10])
    return set(accessed), accessed


def write_citation(dest, st):
    with open(os.path.join(dest, 'CITATION.bib'), 'w') as f:
        f.write(cite.bibtex(*used_sources(st))[0])


def write_attribution(dest, ix, st):
    used = sorted({d['source'] for d in st.values() if d.get('verified')})
    lines = ['# Sources and attribution', '', 'Files in this folder were fetched from these sources by open-subsurface-data.',
             'Keep this note with any copy you pass on. CITATION.bib has BibTeX for these sources and for',
             'open-subsurface-data (or run: osd cite --dest <this folder>).', '']
    for s in used:
        src = ix.sources.get(s, {})
        lines += [f'## {src.get("name", s)}', '', f'- License or terms: {src.get("license", "")} ({src.get("license_url", "")})',
                  f'- Credit: {src.get("attribution", "")}', f'- Landing page: {src.get("landing_page", "")}']
        if src.get('doi'):
            lines.append(f'- DOI: https://doi.org/{src["doi"]}')
        lines.append('')
    with open(os.path.join(dest, 'ATTRIBUTION.md'), 'w') as f:
        f.write('\n'.join(lines))


def cmd_cite(a):
    sources, accessed = set(a.source or []), {}
    if a.dest:
        st = load_state(a.dest)
        if not st:
            print(f'no fetch log at {state_path(a.dest)}', file=sys.stderr)
            return 1
        used, accessed = used_sources(st)
        sources |= used
    text, missing = cite.bibtex(sources, accessed)
    for s in missing:
        print(f'no citation for source {s!r} (see: osd sources)', file=sys.stderr)
    if not sources:
        print('only this repository: add --dest DIR (a folder osd fetched into) or --source ids for the data you used',
              file=sys.stderr)
    if a.out:
        with open(a.out, 'w') as f:
            f.write(text)
        print(f'wrote {a.out}: {text.count(chr(10) + "@") + 1} entries', file=sys.stderr)
    else:
        sys.stdout.write(text)
    return 1 if missing else 0


def cmd_frs(a):
    if a.frs_cmd == 'plan':
        frs.plan(a.out, wells=a.wells, surveys=a.survey, apis=a.api, max_request_gb=a.max_request_gb,
                 max_file_mb=a.max_file_mb, inventory=a.inventory, log=log)
    else:
        missing, diff = frs.check(a.plan, a.request, a.paths, log=log)
        return 1 if missing or diff else 0


def main(argv=None):
    ap = argparse.ArgumentParser(prog='osd', description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--version', action='version', version=__version__)
    sub = ap.add_subparsers(dest='cmd', required=True)
    sub.add_parser('sources', help='the sources in the index')
    p = sub.add_parser('list', help='files a selection would fetch')
    add_filters(p)
    p.add_argument('--volumes', action='store_true', help='list seismic volumes instead of files')
    p.add_argument('--limit', type=int, default=50, help='rows to print (0 for all)')
    for name in ('estimate', 'fetch'):
        p = sub.add_parser(name, help='disk needed for a selection' if name == 'estimate' else 'download and verify a selection')
        add_filters(p)
        p.add_argument('--dest', required=name == 'fetch', help='destination folder')
        p.add_argument('--extract', action='store_true', help='also unpack the selected SEG-Y volumes (the zips are kept)')
        p.add_argument('--roles', default='primary', choices=['primary', 'additional', 'all'],
                       help='volumes to unpack: primary (one full stack per survey, default), additional, all')
        if name == 'fetch':
            p.add_argument('--deep', action='store_true', help='read every zip member and check its CRC32 (slow)')
            p.add_argument('--dry-run', action='store_true', help='show what would be fetched')
            p.add_argument('--max-gb', dest='max_bytes', type=lambda v: float(v) * 1e9, help='refuse selections larger than this')
    p = sub.add_parser('verify', help='check files already fetched')
    p.add_argument('--dest', required=True)
    p.add_argument('--deep', action='store_true')
    p = sub.add_parser('cite', help='BibTeX for this repository and the data sources you used')
    p.add_argument('--dest', help='a folder osd fetched into: cite every source with verified files there')
    p.add_argument('--source', type=csv_arg, help='source ids to cite as well, comma separated (see: osd sources)')
    p.add_argument('--out', help='write to this file instead of standard output')
    p = sub.add_parser('frs', help='BOEM File Request System: plan and check well log requests')
    fs = p.add_subparsers(dest='frs_cmd', required=True)
    q = fs.add_parser('plan', help='write request lists of file IDs and the steps to submit them')
    q.add_argument('--out', required=True)
    q.add_argument('--wells', default='after-survey', choices=['after-survey', 'discoveries', 'in-namss'],
                   help='exploration wells drilled after the first NAMSS survey over them (default), only their discoveries, or all inside NAMSS outlines')
    q.add_argument('--survey', type=csv_arg)
    q.add_argument('--api', type=csv_arg)
    q.add_argument('--max-request-gb', type=float, default=24.0)
    q.add_argument('--max-file-mb', type=float, default=100.0)
    q.add_argument('--inventory', help=f'a fresh copy of {frs.INVENTORY_URL} (osd fetch --file boem:FRSWellDataRawData.zip)')
    q = fs.add_parser('check', help='match a BOEM delivery against a request list (read only)')
    q.add_argument('--plan', required=True)
    q.add_argument('--request', type=int, required=True)
    q.add_argument('paths', nargs='+')
    a = ap.parse_args(argv)
    fn = dict(sources=cmd_sources, list=cmd_list, estimate=cmd_estimate, fetch=cmd_fetch, verify=cmd_verify, cite=cmd_cite,
              frs=cmd_frs)[a.cmd]
    if a.cmd == 'estimate' and not hasattr(a, 'extract'):
        a.extract = False
    sys.exit(fn(a) or 0)


if __name__ == '__main__':
    main()
