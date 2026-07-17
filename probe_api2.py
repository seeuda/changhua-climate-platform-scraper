#!/usr/bin/env python3
"""API probe round 2.

Round 1 found: apiurl.js = the API base host (service.cca.gov.tw),
hidden input sqn=2095, and a truncated hidden JSON config mentioning
ClimateGovernancePlace. The AJAX logic is not in site.js, so it lives in
another external script.

This round:
  1. prints apiurl.js in full and ALL hidden inputs fully decoded
  2. downloads every external <script src> from the snapshot and greps
     each (minified-safe, windowed) for API/AJAX keywords
  3. auto-calls candidate endpoints assembled from the findings

Run: python probe_api2.py   — paste the whole output back.
"""

import html as html_mod
import json
import re
import sys
from pathlib import Path
from urllib.parse import urljoin

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from bs4 import BeautifulSoup  # noqa: E402

from http_client import make_session  # noqa: E402
from rate_limiter import GLOBAL_RATE_LIMITER  # noqa: E402

BASE = 'https://www.cca.gov.tw'
PAGE_URL = f'{BASE}/information-service/info/2095.html'
SNAPSHOT = Path('data/snapshots/page_1.html')
DATA_DIR = Path('data')
API_BASE = 'https://service.cca.gov.tw'

KEYWORDS = ['service.cca', 'apiurl', 'ApiUrl', 'APIURL',
            'ClimateGovernance', 'GetList', 'QueryData', 'sqn',
            '.ajax', 'fetch(', 'XMLHttpRequest', 'axios', '$.post', '$.get']

session = make_session()
session.headers.update({'Referer': PAGE_URL})


def polite_get(url, **kw):
    GLOBAL_RATE_LIMITER.acquire()
    return session.get(url, timeout=15, **kw)


def polite_post(url, **kw):
    GLOBAL_RATE_LIMITER.acquire()
    return session.post(url, timeout=15, **kw)


def show_json_response(resp):
    ctype = resp.headers.get('Content-Type', '?')
    body = resp.text
    print(f"    -> HTTP {resp.status_code}  {ctype}  {len(body):,} bytes")
    try:
        data = resp.json()
    except ValueError:
        print(f"    body head: {body[:250]!r}")
        return
    if isinstance(data, list):
        print(f"    JSON list of {len(data)}")
        if data:
            print("    first: " + json.dumps(data[0], ensure_ascii=False)[:500])
    elif isinstance(data, dict):
        print(f"    JSON dict keys: {list(data.keys())[:20]}")
        for k, v in data.items():
            if isinstance(v, list):
                print(f"    {k}: list of {len(v)}")
                if v:
                    print("      first: "
                          + json.dumps(v[0], ensure_ascii=False)[:500])
            elif not isinstance(v, dict):
                print(f"    {k} = {str(v)[:100]}")


def main():
    print("=" * 62)
    print("API PROBE ROUND 2")
    print("=" * 62)

    if not SNAPSHOT.exists():
        print("No snapshot; run python main.py first")
        return 1
    page = SNAPSHOT.read_text(encoding='utf-8', errors='replace')
    soup = BeautifulSoup(page, 'html.parser')

    # --- 1. full apiurl.js + all hidden inputs, fully decoded ---
    apiurl_file = DATA_DIR / 'apiurl.js'
    if apiurl_file.exists():
        print(f"\n[apiurl.js FULL CONTENT]\n{apiurl_file.read_text(encoding='utf-8')}")

    print("\n[ALL hidden inputs, decoded]")
    for inp in soup.find_all('input', {'type': 'hidden'}):
        ident = inp.get('id') or inp.get('name') or '(no id)'
        value = html_mod.unescape(inp.get('value', ''))
        print(f"\n  id/name: {ident}")
        if value.startswith(('[', '{')):
            try:
                parsed = json.loads(value)
                print("  value (JSON): "
                      + json.dumps(parsed, ensure_ascii=False, indent=2)[:3000])
            except ValueError:
                print(f"  value: {value[:1500]}")
        else:
            print(f"  value: {value[:300]}")

    # --- also: inline scripts mentioning keywords ---
    print("\n[inline script keyword windows]")
    inline = '\n'.join(s.get_text() for s in soup.find_all('script')
                       if not s.get('src'))
    for kw in KEYWORDS:
        for m in re.finditer(re.escape(kw), inline):
            window = ' '.join(
                inline[max(0, m.start() - 120):m.start() + 200].split())
            print(f"  [{kw}] …{window}…")
            break  # first occurrence per keyword is enough

    # --- 2. download every external script and grep ---
    srcs = [s['src'] for s in soup.find_all('script', src=True)]
    print(f"\n[external scripts] {len(srcs)}")
    path_candidates = set()
    for src in srcs:
        url = urljoin(PAGE_URL, src)
        name = Path(src.split('?')[0]).name
        print(f"\n  --- {name} ({url[:90]}) ---")
        try:
            resp = polite_get(url)
        except Exception as e:
            print(f"  fetch failed: {e}")
            continue
        if resp.status_code != 200:
            print(f"  HTTP {resp.status_code}")
            continue
        text = resp.text
        (DATA_DIR / name).write_text(text, encoding='utf-8')
        print(f"  saved data/{name} ({len(text):,} bytes)")

        hits = 0
        for kw in KEYWORDS:
            for m in re.finditer(re.escape(kw), text):
                window = ' '.join(
                    text[max(0, m.start() - 150):m.start() + 250].split())
                print(f"  [{kw}] …{window[:380]}…")
                hits += 1
                # collect path-like strings near the hit
                for p in re.findall(r'''["'](/[A-Za-z][\w/.-]{2,80})["']''',
                                    text[max(0, m.start() - 300):
                                         m.start() + 400]):
                    path_candidates.add(p)
                break  # first window per keyword per file
        if not hits:
            print("  (no keyword hits)")

    # --- 3. try assembled endpoints ---
    sqn_input = soup.find('input', {'id': 'sqn'})
    sqn = sqn_input.get('value') if sqn_input else '2095'
    print(f"\n[page sqn] {sqn}")

    guesses = sorted(p for p in path_candidates
                     if not p.endswith(('.js', '.css', '.html')))
    print(f"\n[candidate paths from JS] {guesses}")

    params = {'sqn': sqn, 'MainSN': sqn, 'p': '1', 'Lang': 'zh-tw'}
    tried = 0
    for path in guesses:
        if tried >= 8:
            break
        url = API_BASE + path
        tried += 1
        print(f"\n  GET {url}")
        try:
            show_json_response(polite_get(url, params=params))
        except Exception as e:
            print(f"    -> failed: {e}")
        print(f"  POST {url}")
        try:
            show_json_response(polite_post(url, json=params))
        except Exception as e:
            print(f"    -> failed: {e}")

    print("\n" + "=" * 62)
    print("END OF PROBE 2 — paste everything above back")
    print("=" * 62)
    return 0


if __name__ == '__main__':
    sys.exit(main())
