"""BibTeX for this repository and for the sources a project used, from data/citations.bib."""
import re

from . import __version__
from .index import data_dir

REPO_URL = 'https://github.com/mnky9800n/open-subsurface-data'


def repo_entry() -> str:
    return ('@misc{aiken2026osd,\n'
            '  author = {Aiken, John M.},\n'
            '  title = {Open Subsurface Data},\n'
            f'  howpublished = {{\\url{{{REPO_URL}}}}},\n'
            '  year = {2026},\n'
            f'  note = {{Version {__version__}, Veles Labs}}\n'
            '}')


def entries() -> list[tuple[str, str]]:
    """(source_id, entry) for each entry in citations.bib, with the osd_source field taken out."""
    text = (data_dir() / 'citations.bib').read_text(encoding='utf-8')
    out = []
    for block in re.split(r'\n(?=@)', text):
        if not block.startswith('@'):
            continue
        m = re.search(r'^\s*osd_source = \{([^}]*)\},?\n', block, re.M)
        out.append((m.group(1), block.replace(m.group(0), '').strip()) if m else ('', block.strip()))
    return out


def with_access(entry: str, day: str) -> str:
    """Add the day the data were fetched to a source without a DOI, and a year if the entry has none."""
    if re.search(r'^\s*doi = ', entry, re.M):
        return entry
    body = entry.rstrip()[:-1].rstrip()   # drop the closing brace
    if not re.search(r'^\s*year = ', body, re.M):
        body += f',\n  year = {{{day[:4]}}}'
    note = re.search(r'^  note = \{(.*)\}(,?)$', body, re.M)
    if note:
        body = body.replace(note.group(0), f'  note = {{{note.group(1)}. Accessed {day}}}{note.group(2)}')
    else:
        body += f',\n  note = {{Accessed {day}}}'
    return body + '\n}'


def bibtex(sources, accessed=None) -> tuple[str, list[str]]:
    """This repository's entry, then each entry for the given sources (in citations.bib order). accessed maps
    a source_id to the day its files were fetched. Returns the text and the sources that have no entry."""
    accessed = accessed or {}
    out, have = [repo_entry()], set()
    for sid, e in entries():
        if sid in sources:
            have.add(sid)
            out.append(with_access(e, accessed[sid]) if accessed.get(sid) else e)
    return '\n\n'.join(out) + '\n', sorted(set(sources) - have)
