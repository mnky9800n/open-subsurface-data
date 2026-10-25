"""data/cores/lily_holes.csv: every hole with data in the LILY database, with its position from LILY's own core
summary (2_CoreSUMM.zip). The LILY data files carry expedition, site and hole but no coordinates.

    uv run python tools/lily_holes.py --raw ~/repos/jenniferprojects/lilyvae/data/raw

--raw is a folder with the LILY files from https://doi.org/10.5281/zenodo.8408297 (all *_DataLITH.csv and
2_CoreSUMM.zip). Reading the 11 GB of CSV takes a few minutes.
"""
import argparse, collections, csv, glob, io, os, zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, 'data', 'cores', 'lily_holes.csv')


def number(v):
    try:
        float(v)
        return True
    except ValueError:   # the core summary writes NA for a missing position
        return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--raw', required=True)
    a = ap.parse_args()
    raw = os.path.expanduser(a.raw)

    data = collections.defaultdict(set)   # (exp, site, hole) -> LILY data sets with rows for the hole
    for path in sorted(glob.glob(os.path.join(raw, '*_DataLITH.csv'))):
        name = os.path.basename(path).split('_')[0]
        with open(path, encoding='utf-8', errors='replace') as f:
            next(f)
            for line in f:
                exp, site, hole = (v.strip('"') for v in line.split(',', 3)[:3])
                data[(exp, site, hole)].add(name)
        print(f'{name}: {len(data)} holes so far')

    pos, site_pos = {}, {}   # first core of each hole (and site) with a position: latitude, longitude, water depth, program
    with zipfile.ZipFile(os.path.join(raw, '2_CoreSUMM.zip')) as z:
        member = next(n for n in z.namelist() if n.endswith('CoreSUMM.csv') and '/._' not in n)
        for r in csv.DictReader(io.TextIOWrapper(z.open(member), encoding='utf-8', errors='replace')):
            if number(r['Latitude (DD)']) and number(r['Longitude (DD)']):
                p = (r['Latitude (DD)'], r['Longitude (DD)'], r['Water Depth (mbsl)'], r['Program'])
                pos.setdefault((r['Exp'], r['Site'], r['Hole']), p)
                site_pos.setdefault((r['Exp'], r['Site']), p)

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    missing = 0
    with open(OUT, 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['exp', 'site', 'hole', 'latitude', 'longitude', 'water_depth_m', 'program', 'position_from', 'datasets'])
        for key in sorted(data, key=lambda k: (k[0].zfill(5), k[1], k[2])):
            src = 'hole' if key in pos else 'site' if key[:2] in site_pos else ''
            lat, lon, wd, prog = pos.get(key) or site_pos.get(key[:2]) or ('', '', '', '')
            missing += not lat
            w.writerow([*key, lat, lon, wd, prog, src, ';'.join(sorted(data[key]))])
    print(f'wrote {OUT}: {len(data)} holes, {missing} without a position in the core summary')


if __name__ == '__main__':
    main()
