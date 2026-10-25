"""Shared adapter behavior."""
from .. import checks


class Adapter:
    fetchable = True

    def identity(self, row: dict, head: dict) -> tuple[list[str], list[str]]:
        """Compare the server's answer with the index before downloading. Returns (errors, notes)."""
        errors, notes = [], []
        if head.get('status') != '200':
            errors.append(f'HEAD returned {head.get("status")} {head.get("error", "")}'.strip())
        size = head.get('content-length')
        if size and row['bytes'] and int(size) != int(row['bytes']):
            notes.append(f'size at the source changed since the index: {row["bytes"]} -> {size}')
        return errors, notes

    def verify(self, row: dict, path: str, members: list[dict], deep: bool) -> tuple[list[str], list[str], str]:
        """Check a downloaded file. Returns (errors, notes, sha256)."""
        errors, notes = [], []
        digest = checks.sha256(path)
        kind, _, value = row['checksum'].partition(':')
        if kind == 'sha256' and value and value != digest:
            (notes if row['stable'] == 'no' else errors).append(f'SHA-256 differs from the index ({value[:12]}... vs {digest[:12]}...)')
        if kind == 'md5' and value and value != (md5 := checks.sha256(path, 'md5')):   # Zenodo gives md5
            (notes if row['stable'] == 'no' else errors).append(f'MD5 differs from the index ({value[:12]}... vs {md5[:12]}...)')
        if path.lower().endswith('.zip'):
            try:
                if members:
                    errors += checks.compare_members(path, members)
                if deep:
                    errors += checks.test_zip(path)
            except Exception as e:  # a broken zip is an error, not a crash
                errors.append(f'zip check failed: {type(e).__name__}: {e}')
        return errors, notes, digest

    def extract_members(self, members: list[dict], volumes: list[dict], roles: set) -> list[str]:
        return []


class SeismicZip(Adapter):
    """A zip that holds one or more SEG-Y volumes plus side files."""

    def extract_members(self, members, volumes, roles):
        """SEG-Y members of the selected volumes, plus the small side files (navigation, notes, images)."""
        want = set()
        for v in volumes:
            if v['role'] in roles:
                want.update(m for m in v['members'].split(';') if m)
        side = [m['member'] for m in members if m['kind'] == 'side']
        return sorted(want) + side


class Direct(Adapter):
    """Single files on a web server with a SHA-256 or MD5 in the index (BOEM tables, NETL EDX, LDEO, LILY)."""

    def __init__(self, stable_note: str = ''):
        self.stable_note = stable_note


class Listed(Adapter):
    """A source in the index without per-file rows. The tool prints the route; it fetches nothing."""
    fetchable = False

    def route(self, src: dict) -> str:
        return (f'{src["name"]}\n  access: {src["access"]}\n  how: {src["how_to_get"]}\n'
                f'  license: {src["license"]}\n  landing page: {src["landing_page"]}')
