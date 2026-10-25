"""HTTP with curl: a HEAD request and a resumable download. Taken from seismic-corpus/tools/corpus_fetch.py.

curl is used because it resumes cleanly (-C -), drops stalled transfers (--speed-limit) and ships with macOS,
Linux and Windows 10 or later."""
import os
import shutil
import subprocess
import time
import urllib.parse

from . import __version__

USER_AGENT = f'open-subsurface-data/{__version__} (research data fetcher; https://veleslabs.ai)'


def need_curl():
    if not shutil.which('curl'):
        raise SystemExit('curl is not on PATH; install curl and try again')


def quote(url: str) -> str:
    return urllib.parse.quote(url, safe=':/%?=&')


def head(url: str) -> dict:
    """Status, size, ETag and Last-Modified of the final response after redirects."""
    p = subprocess.run(['curl', '-sSIL', '-A', USER_AGENT, '--connect-timeout', '60', quote(url)],
                       capture_output=True, text=True)
    out = {}
    for line in p.stdout.splitlines():
        k, _, v = line.partition(':')
        k = k.strip().lower()
        if line.startswith('HTTP/'):
            out = {'status': line.split()[1]}
        elif k in ('content-length', 'etag', 'last-modified'):
            out[k] = v.strip()
    if p.returncode and not out:
        out = {'status': 'error', 'error': p.stderr.strip()[:200]}
    return out


def download(url: str, path: str, want: int | None, log, attempts: int = 10) -> None:
    """Fetch url into path, resuming a partial file. want is the expected size, or None if unknown.
    Raises RuntimeError if the file is not complete after all attempts."""
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    for attempt in range(attempts):
        have = os.path.getsize(path) if os.path.exists(path) else 0
        if want is not None and have == want:
            return
        if want is not None and have > want:
            os.remove(path)
        p = subprocess.run(['curl', '-sSL', '--fail', '-A', USER_AGENT, '--connect-timeout', '60',
                            '--speed-limit', '20000', '--speed-time', '300', '-C', '-', '-o', path,
                            '-w', '%{http_code}', quote(url)], capture_output=True, text=True)
        code = p.stdout.strip()[-3:]
        if p.returncode == 0:
            if want is None:
                return
            continue
        if code == '416' and want is None:   # nothing left to fetch
            return
        if code in ('429', '503'):
            log(f'HTTP {code} from {url}; waiting 15 minutes')
            time.sleep(900)
        else:
            log(f'curl exit {p.returncode} (HTTP {code}) on {url}, attempt {attempt + 1}: {p.stderr.strip()[:200]}')
            time.sleep(min(60 * (attempt + 1), 600))
    got = os.path.getsize(path) if os.path.exists(path) else 0
    raise RuntimeError(f'download incomplete after {attempts} attempts ({got} of {want} bytes)')
