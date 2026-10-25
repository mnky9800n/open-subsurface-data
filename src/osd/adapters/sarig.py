"""SARIG (South Australia): zips on an Azure blob store, listed in the SARIG CKAN catalog. The index holds
each member's size and CRC32, read from the zip's central directory during the crawl, so a download is
checked member by member without unpacking. Some zips use Deflate64 (install the deflate64 extra)."""
from .base import SeismicZip


class Sarig(SeismicZip):
    pass
