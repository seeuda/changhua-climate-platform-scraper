#!/usr/bin/env python3
"""Analyze a saved HTML snapshot and print a compact structure report.

Run after scraping found 0 documents:
    python diagnose_snapshot.py
Paste the whole output back to the developer — it is designed to be
small enough to paste and reveals whether the list is JS-rendered,
paginated onto sub-pages, or uses a different link pattern.
"""

import re
import sys
from collections import Counter
from pathlib import Path
from urllib.parse import urlparse

from bs4 import BeautifulSoup

SNAPSHOT = Path('data/snapshots/page_1.html')


def main():
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else SNAPSHOT
    if not path.exists():
        print(f"Snapshot not found: {path}")
        return 1

    html = path.read_text(encoding='utf-8', errors='replace')
    soup = BeautifulSoup(html, 'html.parser')
    print("=" * 62)
    print(f"SNAPSHOT DIAGNOSIS: {path}  ({len(html):,} bytes)")
    print("=" * 62)

    title = soup.title.get_text(strip=True) if soup.title else '(no title)'
    print(f"\n[title] {title}")

    body_text = soup.body.get_text(' ', strip=True) if soup.body else ''
    print(f"[body text length] {len(body_text):,} chars")
    print(f"[body text head] {body_text[:300]}")

    # --- anchors ---
    anchors = soup.find_all('a', href=True)
    print(f"\n[anchors] total={len(anchors)}")
    prefix_counts = Counter()
    for a in anchors:
        href = a['href']
        parsed = urlparse(href)
        key = (parsed.netloc or '(rel)') + '/' + \
            '/'.join(parsed.path.strip('/').split('/')[:2])
        prefix_counts[key] += 1
    for prefix, count in prefix_counts.most_common(15):
        print(f"  {count:4d}  {prefix}")

    # --- download-ish links ---
    dl = [a for a in anchors if re.search(
        r'file|download|attach|\.pdf|\.doc|\.xls|\.odt|\.ods|\.zip',
        a['href'], re.IGNORECASE)]
    print(f"\n[download-like links] {len(dl)}")
    for a in dl[:10]:
        print(f"  {a['href'][:100]}  |text: {a.get_text(strip=True)[:40]}")

    # --- links whose text suggests document titles ---
    doc_links = [a for a in anchors if re.search(
        r'方案|報告|計畫|成果', a.get_text(strip=True))]
    print(f"\n[links with 方案/報告/計畫/成果 in text] {len(doc_links)}")
    for a in doc_links[:15]:
        print(f"  {a['href'][:90]}  |text: {a.get_text(strip=True)[:50]}")

    # --- pagination hints ---
    pag = [a for a in anchors if re.search(
        r'page|Page|下一頁|下頁|»|next', a['href'] + a.get_text(strip=True))]
    print(f"\n[pagination-like links] {len(pag)}")
    for a in pag[:8]:
        print(f"  {a['href'][:100]}  |text: {a.get_text(strip=True)[:20]}")

    # --- tables / lists ---
    tables = soup.find_all('table')
    print(f"\n[tables] {len(tables)}")
    for t in tables[:3]:
        rows = t.find_all('tr')
        head = t.get_text(' ', strip=True)[:120]
        print(f"  table rows={len(rows)}  head: {head}")
    for cls in ['list', 'item', 'data', 'result']:
        els = soup.select(f'[class*="{cls}"]')
        if els:
            names = Counter(' '.join(e.get('class', [])) for e in els)
            print(f"  class*='{cls}': " +
                  ', '.join(f"{n}({c})" for n, c in names.most_common(5)))

    # --- iframes / forms ---
    for tag, attr in [('iframe', 'src'), ('form', 'action')]:
        els = soup.find_all(tag)
        if els:
            print(f"\n[{tag}s] {len(els)}")
            for e in els[:5]:
                print(f"  {attr}={e.get(attr, '')[:100]}")

    # --- scripts: external + AJAX/API hints in inline code ---
    scripts = soup.find_all('script')
    ext = [s.get('src') for s in scripts if s.get('src')]
    print(f"\n[scripts] total={len(scripts)}, external={len(ext)}")
    for src in ext[:10]:
        print(f"  src={src[:100]}")

    inline = '\n'.join(s.get_text() for s in scripts if not s.get('src'))
    hints = set()
    for m in re.finditer(
            r'''["']([^"']*(?:api|Api|API|ajax|json|List|Query|Search|File)'''
            r'''[^"']*)["']''', inline):
        val = m.group(1)
        if len(val) < 120 and ('/' in val or '.' in val):
            hints.add(val)
    print(f"[inline-script url-ish strings] {len(hints)}")
    for h in sorted(hints)[:25]:
        print(f"  {h}")

    ajax_markers = [kw for kw in
                    ['fetch(', 'XMLHttpRequest', 'axios', '$.ajax', '$.post',
                     '$.get', 'vue', 'Vue', 'react', 'angular']
                    if kw in inline or any(kw in (s or '') for s in ext)]
    print(f"[JS framework/AJAX markers] {ajax_markers}")

    # --- data embedded as JSON? ---
    json_blobs = re.findall(r'\{"[^"]+":', inline)
    print(f"[inline JSON-ish blobs] {len(json_blobs)}")

    print("\n" + "=" * 62)
    print("END OF DIAGNOSIS — paste everything above back for analysis")
    print("=" * 62)
    return 0


if __name__ == '__main__':
    sys.exit(main())
