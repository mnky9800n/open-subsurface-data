"""BOEM/BSEE File Request System (FRS): plan requests for digital well logs and check what arrives.

The FRS needs a Login.gov account. This module never signs in and never sees credentials. It writes lists of
public file IDs (from BOEM's public FRS inventory) that you upload yourself, and it checks the zips BOEM sends
you against those lists. It only reads the zips."""
import csv
import io
import os
import re
import zipfile

from .index import data_dir, human, split

FRS_HOME = 'https://www.data.boem.gov/Other/FileRequestSystem/Default.aspx'
FRS_WELLS = 'https://www.data.boem.gov/Other/FileRequestSystem/WellData.aspx'
FRS_TUTORIAL = 'https://www.data.boem.gov/Main/Tutorials/FileRequestSystem.aspx'
INVENTORY_URL = 'https://www.data.boem.gov/Other/Files/FRSWellDataRawData.zip'


def read_inventory(path, apis):
    """Digital log rows ('raw-' IDs) for the given 10-digit APIs from a fresh FRSWellDataRawData.zip."""
    out = []
    with zipfile.ZipFile(path) as z:
        name = next(n for n in z.namelist() if n.endswith('mv_frs_file_inventory.txt'))
        with z.open(name) as f:
            for r in csv.DictReader(io.TextIOWrapper(f, encoding='latin-1')):
                if r['DOC_ID'].startswith('raw-') and r['API'][:10] in apis:
                    out.append(dict(doc_id=r['DOC_ID'], api=r['API'], api10=r['API'][:10], bytes=int(r['FILE_SIZE'] or 0),
                                    run_date=r['RUN_DATE'], releasable_date=r['RELEASABLE_DATE']))
    return out


def plan(out_dir, wells='after-survey', surveys=None, apis=None, max_request_gb=24.0, max_file_mb=100.0,
         inventory=None, log=print):
    with open(data_dir() / 'wells' / 'gulf_exploration_wells.csv', newline='') as f:
        W = list(csv.DictReader(f))
    sel = [w for w in W if w['in_namss'] == 'True']
    if wells == 'after-survey':
        sel = [w for w in sel if w['after_survey'] == 'True']
    elif wells == 'discoveries':
        sel = [w for w in sel if w['after_survey'] == 'True' and w['discovery'] == 'True']
    if surveys:
        s = {x.lower() for x in surveys}
        sel = [w for w in sel if {x.lower() for x in split(w['surveys'])} & s]
    if apis:
        sel = [w for w in sel if w['api'][:10] in {a[:10] for a in apis}]
    keep = {w['api'][:10] for w in sel}
    if inventory:
        files = read_inventory(inventory, keep)
    else:
        with open(data_dir() / 'wells' / 'boem_frs_raw_logs.csv', newline='') as f:
            files = [dict(r, bytes=int(r['bytes'])) for r in csv.DictReader(f) if r['api10'] in keep]
    by = {}
    for r in files:
        by.setdefault(r['api10'], []).append(r)
    cap, limit = max_file_mb * 1e6, max_request_gb * 1e9
    big = [r for r in files if r['bytes'] > cap]
    sel.sort(key=lambda w: (w['discovery'] != 'True', w['api']))
    batches, cur, size = [], [], 0
    for w in sel:
        fs = [r for r in by.get(w['api'][:10], []) if r['bytes'] <= cap]
        if not fs:
            continue
        s = sum(r['bytes'] for r in fs)
        if cur and size + s > limit:
            batches.append(cur)
            cur, size = [], 0
        cur.append((w, fs))
        size += s
    if cur:
        batches.append(cur)
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, 'request_files.csv'), 'w', newline='') as fo:
        wr = csv.writer(fo)
        wr.writerow(['request', 'api', 'discovery', 'surveys', 'doc_id', 'bytes'])
        for i, b in enumerate(batches, 1):
            ids = [r['doc_id'] for _, fs in b for r in fs]
            with open(os.path.join(out_dir, f'request_{i:03d}.txt'), 'w') as f:
                f.write('\n'.join(ids) + '\n')
            for w, fs in b:
                for r in fs:
                    wr.writerow([i, w['api'], w['discovery'], w['surveys'], r['doc_id'], r['bytes']])
    with open(os.path.join(out_dir, 'skipped_large_files.csv'), 'w', newline='') as fo:
        wr = csv.writer(fo)
        wr.writerow(['api', 'doc_id', 'bytes'])
        for r in big:
            wr.writerow([r['api'], r['doc_id'], r['bytes']])
    summary = []
    for i, b in enumerate(batches, 1):
        n_files = sum(len(fs) for _, fs in b)
        gb = sum(r['bytes'] for _, fs in b for r in fs)
        summary.append((i, len(b), sum(w['discovery'] == 'True' for w, _ in b), n_files, gb))
    write_howto(out_dir, summary, max_request_gb, inventory is not None)
    n_wells = sum(s[1] for s in summary)
    log(f'{len(sel)} wells selected; {n_wells} have digital logs under {max_file_mb:.0f} MB')
    for i, nw, nd, nf, gb in summary:
        log(f'  request_{i:03d}.txt: {nw} wells ({nd} discoveries), {nf} files, {human(gb)}')
    log(f'  {len(big)} files over {max_file_mb:.0f} MB left out (skipped_large_files.csv)')
    log(f'next: read {os.path.join(out_dir, "HOW_TO_REQUEST.md")}')
    return summary


def write_howto(out_dir, summary, max_gb, fresh):
    lines = [
        '# How to request these BOEM well logs',
        '',
        'The BOEM/BSEE File Request System (FRS) is free, but it needs a Login.gov account. You make the account and',
        'sign in yourself. This tool never asks for, stores or uses your login.',
        '',
        'Each `request_NNN.txt` holds public FRS file IDs ("Filename IDs") of digital logs, one per line. They come',
        'from BOEM\'s public inventory' + (' (the copy you gave with --inventory).' if fresh else ' (the copy bundled with this index; pass --inventory with a fresh download to refresh it).'),
        f'Each list stays under {max_gb:.0f} GB, below the FRS limit ("The current request size limit is 25 GB").',
        '',
        '## Steps, one list at a time',
        '',
        f'1. Open {FRS_HOME} and sign in with Login.gov.',
        f'2. Open the Well Data page ({FRS_WELLS}). Once signed in, it offers "the option to upload and process a text',
        '   list of Filename IDs". Upload `request_001.txt`.',
        '3. If the page seems to ignore a long list, reload it before trying again. In our own use a 5,222-line',
        '   list had in fact been processed and showed up only after a reload.',
        '4. Add the files to your set and submit the request. BOEM says: "Our system will compile your requested',
        '   files and, when available, email you the link to download. This process can take up to 24 hours".',
        '   The email comes from BSEEOnline.Data@bsee.gov (check spam). "Your download link will be available for',
        '   5 days after it is activated."',
        '5. Download the zip into a folder of its own, then check it against the list:',
        '',
        '       osd frs check --plan <this folder> --request 1 <downloaded zip or folder>',
        '',
        '6. Move on to `request_002.txt` when the first one has arrived.',
        '',
        f'Button names on the BOEM pages can change. BOEM\'s video tutorial: {FRS_TUTORIAL}',
        '',
        'BOEM: "Information presented on this website is considered public information and may be distributed or',
        'copied. Use of appropriate byline/photo/image credit is requested." (https://www.boem.gov/about-boem/disclaimer-liability-and-endorsement)',
        '',
        '## The lists',
        '',
        '| list | wells | discoveries | files | size |',
        '|---|---:|---:|---:|---:|',
    ]
    for i, nw, nd, nf, gb in summary:
        lines.append(f'| request_{i:03d}.txt | {nw} | {nd} | {nf} | {human(gb)} |')
    lines += ['', 'Files over the size cap are listed in `skipped_large_files.csv` and are not in any list.', '']
    with open(os.path.join(out_dir, 'HOW_TO_REQUEST.md'), 'w') as f:
        f.write('\n'.join(lines))


def check(plan_dir, request, paths, log=print):
    """Match what BOEM delivered against one request list. Reads zips and folders; changes nothing."""
    with open(os.path.join(plan_dir, 'request_files.csv'), newline='') as f:
        want = {r['doc_id'].lower(): int(r['bytes']) for r in csv.DictReader(f) if int(r['request']) == request}
    seen = {}
    for p in paths:
        if os.path.isdir(p):
            for root, _, fs in os.walk(p):
                for fn in fs:
                    seen[fn] = os.path.getsize(os.path.join(root, fn))
        elif zipfile.is_zipfile(p):
            with zipfile.ZipFile(p) as z:
                for i in z.infolist():
                    if not i.is_dir():
                        seen[os.path.basename(i.filename)] = i.file_size
    found, size_diff = set(), []
    for name, size in seen.items():
        for d in re.findall(r'raw-\d+', name.lower()):
            if d in want:
                found.add(d)
                if size != want[d]:
                    size_diff.append((name, size, want[d]))
                break
    missing = sorted(set(want) - found)
    log(f'request {request}: {len(want)} files listed, {len(found)} found, {len(missing)} missing, {len(size_diff)} with a different size')
    for d in missing[:20]:
        log(f'  missing {d}')
    for name, s, w in size_diff[:20]:
        log(f'  size {name}: {s} bytes, inventory says {w}')
    if not found and seen:
        log('  no file name contains a listed ID; BOEM may have renamed the files. Compare request_files.csv by hand.')
    return missing, size_diff
