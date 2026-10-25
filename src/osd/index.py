"""Read the index tables in data/ and select rows from them."""
import csv
import os
from dataclasses import dataclass, field
from pathlib import Path


def data_dir() -> Path:
    """The index folder: $OSD_DATA, the copy inside an installed package, or data/ in a source checkout."""
    if os.environ.get('OSD_DATA'):
        return Path(os.environ['OSD_DATA'])
    here = Path(__file__).resolve().parent
    for p in (here / 'data', here.parent.parent / 'data'):
        if (p / 'files.csv').exists():
            return p
    raise SystemExit('cannot find the index tables (data/files.csv); set OSD_DATA to the data folder')


def read_csv(name: str) -> list[dict]:
    p = data_dir() / name
    with open(p, newline='', encoding='utf-8') as f:
        return list(csv.DictReader(f))


def split(v: str) -> list[str]:
    return [x for x in (v or '').split(';') if x]


@dataclass
class Index:
    sources: dict = field(default_factory=dict)
    files: list = field(default_factory=list)
    volumes: list = field(default_factory=list)
    members: dict = field(default_factory=dict)

    @classmethod
    def load(cls, with_members=False):
        ix = cls()
        ix.sources = {r['source_id']: r for r in read_csv('sources.csv')}
        ix.files = read_csv('files.csv')
        ix.volumes = read_csv('seismic/volumes.csv')
        if with_members:
            for r in read_csv('seismic/members.csv'):
                ix.members.setdefault(r['file_id'], []).append(r)
        return ix


INCLUDE_ORDER = ['yes', 'decide', 'no', 'blocked']


def select(ix: Index, source=None, region=None, survey=None, kind=None, include='yes', file_ids=None):
    """Files that match every filter given. Each filter is a list of values (any may match).

    include applies to seismic archives only: an archive is kept when at least one volume in it has an
    include value in the list ('all' keeps everything). Naming a survey or a file id overrides it."""
    out = []
    surveys = {s.lower() for s in survey or []}
    named = bool(surveys or file_ids)
    inc = None if (named or not include or 'all' in include) else set(include)
    for r in ix.files:
        if file_ids and r['file_id'] not in file_ids:
            continue
        if source and r['source'] not in source:
            continue
        if kind and r['kind'] not in kind:
            continue
        if region and not set(split(r['regions'])) & set(region):
            continue
        if surveys and not {s.lower() for s in split(r['surveys'])} & surveys:
            continue
        if inc is not None and r['kind'] == 'seismic' and not set(split(r['include'])) & inc:
            continue
        out.append(r)
    return out


def human(n: float) -> str:
    for unit, k in (('TB', 1e12), ('GB', 1e9), ('MB', 1e6), ('kB', 1e3)):
        if abs(n) >= k:
            return f'{n / k:.2f} {unit}'
    return f'{int(n)} B'
