#!/usr/bin/env python3
"""Repair archive filenames and metadata — offline, no re-download.

Fixes two defects found in the first full download:
1. Server filenames arrived percent-encoded and were truncated at 120
   chars, cutting off extensions — real PDFs got mislabeled 非PDF and
   excluded from consolidation.
2. publish_date misparsed period ranges (115-119年 → 2030).

What it does:
- Detects each archive file's TRUE format from magic bytes
  (%PDF / zip-container inspection for xlsx-ods-docx / text probing)
- Renames to {id}_{readable name}{true ext}: percent-decoding the
  current name when it decodes cleanly, otherwise falling back to the
  document title from the metadata
- Re-fetches the 6 NewsList pages (~15s, polite) to restore the
  authoritative 公開年度/報告/進度 per case, and rewrites the metadata
  CSV/JSON (use --no-refresh to skip the network entirely)
- Rebuilds all classification views (hardlinks reference old names)

Run:  python fix_archive.py
Then: python consolidate.py --gcs-base gs://... (regenerate case files)
"""

import json
import re
import shutil
import sys
import zipfile
from pathlib import Path
from urllib.parse import unquote

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

METADATA = Path('output/climate_docs_metadata.json')
ARCHIVE = Path('downloads/archive')
VIEW_DIRS = [p for p in Path('downloads').glob('by_*')] \
    if Path('downloads').exists() else []


def detect_ext(path: Path) -> str:
    with path.open('rb') as f:
        head = f.read(8)
    if head.startswith(b'%PDF'):
        return '.pdf'
    if head.startswith(b'PK'):
        try:
            with zipfile.ZipFile(path) as z:
                names = z.namelist()
                if 'mimetype' in names:
                    mt = z.read('mimetype')[:100].decode('ascii', 'ignore')
                    if 'spreadsheet' in mt:
                        return '.ods'
                    if 'presentation' in mt:
                        return '.odp'
                    if 'text' in mt:
                        return '.odt'
                if any(n.startswith('xl/') for n in names):
                    return '.xlsx'
                if any(n.startswith('word/') for n in names):
                    return '.docx'
                if any(n.startswith('ppt/') for n in names):
                    return '.pptx'
        except zipfile.BadZipFile:
            pass
        return '.zip'
    if head.startswith(b'\xd0\xcf\x11\xe0'):  # legacy OLE (doc/xls/ppt)
        return '.xls'
    try:
        path.open('rb').read(4096).decode('utf-8')
        return '.csv'
    except UnicodeDecodeError:
        return '.bin'


def sanitize(name: str) -> str:
    for ch in '/\\:*?"<>|':
        name = name.replace(ch, '_')
    return name.strip()


KNOWN_EXT = re.compile(r'\.(pdf|docx?|xlsx?|ods|odt|odp|pptx?|zip|csv)$',
                       re.IGNORECASE)


def readable_base(current_body: str, doc: dict) -> str:
    """Best readable stem: cleanly-decoded server name, else doc title.

    Strips only KNOWN extensions — Path.stem would truncate names like
    圖ES2.1 1990年至... at the inner dot."""
    decoded = unquote(current_body)
    stem = KNOWN_EXT.sub('', decoded).strip()
    # Truncation artifacts: leftover % sequences or a dangling partial
    # percent escape mean the decode is unreliable.
    if '%' not in decoded and '�' not in decoded and len(stem) >= 2:
        return sanitize(stem)[:90]
    title = (doc.get('title') or doc.get('list_title') or '').strip()
    title = KNOWN_EXT.sub('', title)
    if len(title) >= 3:
        return sanitize(title)[:90]
    return sanitize(stem)[:90] or 'document'


def refresh_list_metadata(docs):
    """Re-fetch NewsList pages to restore authoritative per-case fields."""
    from autopilot import build_body, stub_docs_from_fragment, polite, \
        KNOWN_ENDPOINT
    from scraper import ClimateDocumentScraper
    scraper = ClimateDocumentScraper()

    stub_map = {}
    for page in range(1, 10):
        body = build_body(2095, dc=60, p=page)
        resp = polite('POST', KNOWN_ENDPOINT, json=body)
        if resp.status_code != 200:
            break
        stubs = stub_docs_from_fragment(resp.text, scraper)
        if not stubs:
            break
        for st in stubs:
            stub_map[st['detail_url']] = st
    print(f"refreshed {len(stub_map)} cases from NewsList")

    fixed = 0
    for doc in docs:
        st = stub_map.get(doc.get('detail_url', ''))
        if not st:
            continue
        changed = False
        if st.get('year') and doc.get('publish_date') != st['year']:
            doc['publish_date'] = st['year']
            changed = True
        for src, dst in [('rtype', 'type'), ('status', 'status'),
                         ('category', 'category')]:
            if st.get(src) and doc.get(dst) != st[src]:
                doc[dst] = st[src]
                changed = True
        fixed += changed
    print(f"corrected fields on {fixed} file records")
    return docs


def main():
    no_refresh = '--no-refresh' in sys.argv

    if not METADATA.exists() or not ARCHIVE.is_dir():
        print("output/climate_docs_metadata.json or downloads/archive missing")
        return 1

    data = json.loads(METADATA.read_text(encoding='utf-8'))
    docs = data['documents']
    by_id = {d['id']: d for d in docs}

    renamed = skipped = 0
    ext_counts = {}
    for f in sorted(ARCHIVE.iterdir()):
        m = re.match(r'^(\d{5})_(.*)$', f.name)
        if not m or not f.is_file():
            continue
        doc_id, body = int(m.group(1)), m.group(2)
        doc = by_id.get(doc_id, {})

        ext = detect_ext(f)
        base = readable_base(body, doc)
        new_name = f"{m.group(1)}_{base}{ext}"
        if new_name == f.name:
            skipped += 1
        else:
            target = ARCHIVE / new_name
            if target.exists() and target != f:
                new_name = f"{m.group(1)}_{base}_{doc_id}{ext}"
                target = ARCHIVE / new_name
            f.rename(target)
            renamed += 1
        ext_counts[ext] = ext_counts.get(ext, 0) + 1
        if doc:
            doc['file_format'] = {'.pdf': 'PDF', '.docx': 'Word',
                                  '.doc': 'Word', '.xls': 'Excel',
                                  '.xlsx': 'Excel', '.ods': 'ODF Excel',
                                  '.odt': 'ODF Word', '.zip': 'ZIP',
                                  '.csv': 'CSV'}.get(ext, ext.lstrip('.'))
            doc['server_filename'] = new_name.split('_', 1)[1]

    print(f"renamed {renamed}, already-clean {skipped}")
    print("true formats:", dict(sorted(ext_counts.items(),
                                       key=lambda kv: -kv[1])))

    if not no_refresh:
        try:
            docs = refresh_list_metadata(docs)
        except Exception as e:
            print(f"list refresh failed ({e}); continuing without it")

    from output_formatter import DocumentOutputFormatter
    DocumentOutputFormatter.save_csv(docs)
    DocumentOutputFormatter.save_json(docs)
    print("metadata CSV/JSON rewritten")

    # Views hold hardlinks under the old names — rebuild them
    for view in VIEW_DIRS:
        shutil.rmtree(view)
    from organize import build_view
    from download_manager import ORGANIZE_METHODS
    for method in ORGANIZE_METHODS:
        build_view(docs, ARCHIVE, Path('downloads'), method)
    print("views rebuilt")

    print("\nNext: python consolidate.py --gcs-base gs://... "
          "(regenerates case files with readable names + full PDF bodies)")
    return 0


if __name__ == '__main__':
    sys.exit(main())
