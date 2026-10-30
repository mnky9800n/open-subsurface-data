"""tools/zenodo_<community>.json: the open records of a Zenodo community and their files, as the Zenodo API gives
them (record id, DOIs, title, date, license and, per file, the name, size and md5). build_index.py turns these into
files.csv rows. Used for the IODP community (https://zenodo.org/communities/iodp) and LDEO LogDB
(https://zenodo.org/communities/logdb).

    uv run python tools/zenodo_community.py iodp
    uv run python tools/zenodo_community.py logdb --jsonl saved_records.jsonl

Without a token the API returns 25 records a page, so the IODP community takes about 140 requests; the script waits
between pages. --jsonl reads records saved earlier (one API hit per line) instead of asking the API.
"""
import argparse, datetime, json, os, sys, time, urllib.parse, urllib.request

TOOLS = os.path.dirname(os.path.abspath(__file__))
API = 'https://zenodo.org/api/communities/{}/records?size=25&page={}&sort=oldest'


def get(url):
    for attempt in range(5):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'open-subsurface-data index (osd)'})
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.load(r)
        except Exception as e:  # Zenodo rate limits and times out now and then; wait and try again
            print(f'retry {attempt + 1}: {e}', file=sys.stderr)
            time.sleep(10 * (attempt + 1))
    raise SystemExit(f'gave up on {url}')


def records_from_api(community):
    page, out = 1, []
    while True:
        d = get(API.format(community, page))
        out += d['hits']['hits']
        print(f'page {page}: {len(out)} of {d["hits"]["total"]}', file=sys.stderr)
        if not d['hits']['hits'] or len(out) >= d['hits']['total']:
            return out
        page += 1
        time.sleep(1.5)


def trim(r):
    m = r['metadata']
    return dict(id=str(r['id']), doi=r.get('doi', ''), conceptdoi=r.get('conceptdoi', ''), title=m['title'],
                publication_date=m.get('publication_date', ''), license=(m.get('license') or {}).get('id', ''),
                files=[dict(key=f['key'], size=f['size'], checksum=f['checksum'],
                            url=f'https://zenodo.org/records/{r["id"]}/files/{urllib.parse.quote(f["key"])}?download=1')
                       for f in r['files']])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('community')
    ap.add_argument('--jsonl', help='records saved from the API, one per line, instead of asking the API')
    a = ap.parse_args()
    recs = [json.loads(line) for line in open(a.jsonl)] if a.jsonl else records_from_api(a.community)
    keep = [r for r in recs if r['metadata'].get('access_right') == 'open' and r.get('files')]
    out = os.path.join(TOOLS, f'zenodo_{a.community}.json')
    head = json.dumps(dict(community=f'https://zenodo.org/communities/{a.community}', read=str(datetime.date.today())))
    with open(out, 'w') as f:   # one record a line, so a later refresh shows up as a readable diff
        f.write(head[:-1] + ', "records": [\n' + ',\n'.join(json.dumps(trim(r)) for r in keep) + '\n]}\n')
    n = sum(len(r['files']) for r in keep)
    print(f'wrote {out}: {len(keep)} records, {n} files; left out {len(recs) - len(keep)} records that are not open '
          f'or have no files')


if __name__ == '__main__':
    main()
