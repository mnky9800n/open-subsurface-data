"""One adapter per kind of source. An adapter knows how a source's files are checked after download and
which members to unpack. Sources the tool cannot fetch (account, request or not yet indexed per file) get
an adapter that explains the route instead."""
from .base import Direct, Listed
from .namss import Namss
from .sarig import Sarig

ADAPTERS = {
    'namss': Namss(),
    'sarig': Sarig(),
    'boem-data-center': Direct(stable_note='BOEM refreshes these tables (most weekly); a new checksum means a newer release, not a broken file'),
    'netl-edx': Direct(),
    'ldeo-logdb': Direct(),
    'lily': Direct(),
}


def adapter(source_id: str):
    return ADAPTERS.get(source_id) or Listed()
