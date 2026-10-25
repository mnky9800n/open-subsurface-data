"""USGS NAMSS: one zip per survey on walrus.wr.usgs.gov. The index holds the server's ETag for each zip (from
the 2026-10-17 crawl), so a changed ETag means USGS replaced the file. Some zips hold zips; such a member is
named 'Data/inner.zip' in the volume table and is unpacked in full."""
from .base import SeismicZip


class Namss(SeismicZip):
    def identity(self, row, head):
        errors, notes = super().identity(row, head)
        kind, _, value = row['checksum'].partition(':')
        if kind == 'etag' and head.get('etag') and head['etag'] != value:
            notes.append(f'ETag changed since the index ({value} -> {head["etag"]}): USGS has replaced the file')
        return errors, notes
