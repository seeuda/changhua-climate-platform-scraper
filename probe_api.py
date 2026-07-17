#!/usr/bin/env python3
"""Discover and probe the AJAX API that returns the document list.

QueryData in the page is only the search-form state; the actual list is
fetched by site.js from an endpoint defined in /js/apiurl.js. This tool:

  1. re-reads the snapshot for MainSN / page-id hints
  2. downloads apiurl.js + site.js and extracts endpoint URLs
  3. politely test-calls the most likely list endpoints (GET and POST)
     and prints response summaries

Run: python probe_api.py
Paste the whole output back to the developer.
"""

import json
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from http_client import make_session  # noqa: E402
from rate_limiter import GLOBAL_RATE_LIMITER  # noqa: E402

BASE = 'https://www.cca.gov.tw'
PAGE_URL = f'{BASE}/information-service/info/2095.html'
SNAPSHOT = Path('data/snapshots/page_1.html')
DATA_DIR = Path('data')

session = make_session()
session.headers.update({'Referer': PAGE_URL,
                        'X-Requested-With': 'XMLHttpRequest'})


def fetch(url):
    GLOBAL_RATE_LIMITER.acquire()
    try:
        resp = session.get(url, timeout=15)
        return resp
    except Exception as e:
        print(f"  fetch failed: {e}")
        return None


def show_response(resp):
    ctype = resp.headers.get('Content-Type', '?')
    body = resp.text
    print(f"    -> HTTP {resp.status_code}  {ctype}  {len(body):,} bytes")
    if 'json' in ctype or body[:1] in '[{':
        try:
            data = resp.json()
            if isinstance(data, list):
                print(f"    JSON list, {len(data)} items")
                if data:
                    print(f"    first item keys/preview: "
                          f"{json.dumps(data[0], ensure_ascii=False)[:400]}")
            elif isinstance(data, dict):
                print(f"    JSON dict keys: {list(data.keys())}")
                for k, v in data.items():
                    if isinstance(v, list):
                        print(f"    {k}: list of {len(v)}")
                        if v:
                            print(f"    first item: "
                                  f"{json.dumps(v[0], ensure_ascii=False)[:400]}")
                    elif not isinstance(v, dict):
                        print(f"    {k} = {str(v)[:80]}")
            return True
        except ValueError:
            pass
    print(f"    body head: {body[:300]!r}")
    return False


def main():
    print("=" * 62)
    print("API PROBE")
    print("=" * 62)

    # --- 1. hints from the snapshot ---
    sn_hits = []
    if SNAPSHOT.exists():
        html = SNAPSHOT.read_text(encoding='utf-8', errors='replace')
        print("\n[MainSN context in page]")
        for m in re.finditer(r'.{0,60}MainSN.{0,80}', html):
            line = ' '.join(m.group(0).split())
            print(f"  {line[:140]}")
            sn_hits.append(line)
        print("\n[attributes containing 2095]")
        for m in set(re.findall(r'[\w-]+=["\'][^"\']*2095[^"\']*["\']', html)):
            print(f"  {m[:120]}")
        print("\n[hidden inputs]")
        for m in re.finditer(
                r'<input[^>]*type=["\']hidden["\'][^>]*>', html):
            print(f"  {m.group(0)[:140]}")
    else:
        print(f"\n(no snapshot at {SNAPSHOT})")

    # --- 2. fetch the JS files and mine endpoints ---
    endpoints = set()
    for js_path in ['/js/apiurl.js', '/js/site.js']:
        print(f"\n[fetching {js_path}]")
        resp = fetch(BASE + js_path)
        if not resp or resp.status_code != 200:
            print(f"  unavailable "
                  f"(HTTP {resp.status_code if resp else 'n/a'})")
            continue
        text = resp.text
        out = DATA_DIR / Path(js_path).name
        out.write_text(text, encoding='utf-8')
        print(f"  saved {out} ({len(text):,} bytes)")

        strings = set(re.findall(r'''["']([^"'\s]{3,120})["']''', text))
        urlish = sorted(s for s in strings
                        if ('/' in s and not s.startswith(('<', 'http://www.w3'))
                            and not s.endswith(('.png', '.jpg', '.svg', '.css',
                                                '.gif', '.woff', '.woff2'))))
        print(f"  url-ish strings ({len(urlish)}):")
        for s in urlish[:40]:
            print(f"    {s}")
        endpoints.update(s for s in urlish
                         if re.search(r'api|list|query|search|info|data',
                                      s, re.IGNORECASE))

        if 'site.js' in js_path:
            print("  lines mentioning QueryData/ajax/post/get:")
            for line in text.splitlines():
                if re.search(r'QueryData|\.ajax|\.post\(|\.get\(|fetch\(',
                             line):
                    print(f"    {line.strip()[:150]}")

    # --- 3. try the most likely endpoints ---
    candidates = sorted(endpoints)[:8]
    print(f"\n[test-calling {len(candidates)} candidate endpoints]")
    params = {'MainSN': '2095', 'p': '1', 'Lang': 'zh-tw'}
    for ep in candidates:
        url = ep if ep.startswith('http') else \
            BASE + ('' if ep.startswith('/') else '/') + ep
        print(f"\n  GET {url}  params={params}")
        GLOBAL_RATE_LIMITER.acquire()
        try:
            resp = session.get(url, params=params, timeout=15)
            show_response(resp)
        except Exception as e:
            print(f"    -> failed: {e}")
        print(f"  POST {url}  json={params}")
        GLOBAL_RATE_LIMITER.acquire()
        try:
            resp = session.post(url, json=params, timeout=15)
            show_response(resp)
        except Exception as e:
            print(f"    -> failed: {e}")

    print("\n" + "=" * 62)
    print("END OF PROBE — paste everything above back for analysis")
    print("=" * 62)
    return 0


if __name__ == '__main__':
    sys.exit(main())
