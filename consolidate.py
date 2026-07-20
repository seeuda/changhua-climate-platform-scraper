#!/usr/bin/env python3
"""Consolidate each 案件 (document) into one searchable Markdown file.

For each of the 346 documents: gather its downloaded attachments from
downloads/archive/, extract text from the PDFs (statistical tables in
Excel/ODS/CSV are listed but not merged), and write a single .md with a
metadata header, the attachment list, and the extracted body text.

    python consolidate.py              # write downloads/consolidated/
    python consolidate.py --upload     # then upload that folder to GCS
                                       #   (GCP_PROJECT_ID / GCS_BUCKET_NAME
                                       #    / GOOGLE_APPLICATION_CREDENTIALS)

Notes on fidelity: text is extracted with pypdf. Scanned/image-only PDFs
yield little or no text and are flagged in place; no OCR is attempted.
"""

import argparse
import hashlib
import json
import os
import re
import sys
from urllib.parse import unquote
from collections import defaultdict
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

METADATA = Path('output/climate_docs_metadata.json')
ARCHIVE = Path('downloads/archive')
OUT_DIR = Path('downloads/consolidated')
GCS_PREFIX = 'climate-docs-consolidated'

MAX_PDFS_PER_CASE = 30       # inventories can carry hundreds of table PDFs
MAX_CHARS_PER_ATTACHMENT = 500_000
TABLE_EXTS = {'.xlsx', '.xls', '.ods', '.csv', '.odt', '.zip'}


def sanitize(name: str) -> str:
    for ch in '/\\:*?"<>|':
        name = name.replace(ch, '_')
    return name.strip()


def human_size(n: int) -> str:
    for unit in ['B', 'KB', 'MB', 'GB']:
        if n < 1024:
            return f"{n:.0f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def find_archive_file(doc_id: int):
    matches = sorted(ARCHIVE.glob(f"{str(doc_id).zfill(5)}_*"))
    return matches[0] if matches else None


# Lesson from the W04 upload debugging sessions: Vertex AI happily
# ingests garbage — control characters must be stripped BEFORE upload,
# and any pathological unbroken run of text must be force-chunked or the
# layout parser buffer overflows.
INVALID_XML_CHARS = re.compile(
    '[^\x09\x0a\x0d\x20-퟿-�\U00010000-\U0010ffff]')


def clean_text(text: str) -> str:
    text = INVALID_XML_CHARS.sub('', text)
    # Break any unbroken run longer than 1000 chars (W04 lesson #4)
    return re.sub(r'([^\n]{1000})', r'\1\n', text)


def extract_pdf_text(path: Path) -> str:
    from pypdf import PdfReader
    try:
        reader = PdfReader(str(path))
        parts = []
        total = 0
        for page in reader.pages:
            text = page.extract_text() or ''
            parts.append(text)
            total += len(text)
            if total > MAX_CHARS_PER_ATTACHMENT:
                parts.append('\n…（內容過長，以下截斷）')
                break
        return clean_text('\n'.join(parts).strip())
    except Exception as e:
        return f'（無法解析此 PDF：{e}）'


def build_case_markdown(case_docs, case_no):
    first = case_docs[0]
    title = first.get('list_title') or first.get('title') or f'案件{case_no}'

    lines = [f"# {title}", ""]
    lines += ["| 欄位 | 值 |", "|------|------|"]
    for label, key in [('提交機關', 'organization'), ('機關類型', 'org_type'),
                       ('縣市', 'county'), ('類型', 'category'),
                       ('報告種類', 'type'), ('進度', 'status'),
                       ('公開日期/年度', 'publish_date')]:
        lines.append(f"| {label} | {first.get(key) or '-'} |")
    lines.append(f"| 詳細頁 | {first.get('detail_url', '-')} |")
    lines.append(f"| 附件數 | {len(case_docs)} |")
    lines.append("")

    # Attachment inventory (everything listed, tables flagged)
    lines += ["## 附件清單", ""]
    pdf_files = []
    for doc in case_docs:
        f = find_archive_file(doc['id'])
        name = unquote(f.name) if f else f"{doc['id']:05d}（未下載）"
        size = human_size(f.stat().st_size) if f else '-'
        ext = f.suffix.lower() if f else ''
        tag = ''
        if ext in TABLE_EXTS:
            tag = '（表格/資料檔，未納入內文）'
        elif ext == '.pdf' and f:
            pdf_files.append((doc, f))
        elif ext not in ('.pdf',):
            tag = '（非 PDF，未納入內文）'
        lines.append(f"- {name} — {size} {tag}  ")
        lines.append(f"  來源: {doc.get('download_url', '-')}")
    lines.append("")

    # Body: extracted text from PDFs
    lines += ["## 內文（自 PDF 附件抽取）", ""]
    if not pdf_files:
        lines.append("（本案件無 PDF 附件，或 PDF 未成功下載）")
    skipped = 0
    for i, (doc, f) in enumerate(pdf_files):
        if i >= MAX_PDFS_PER_CASE:
            skipped = len(pdf_files) - MAX_PDFS_PER_CASE
            break
        lines += [f"### {unquote(f.name)}", ""]
        text = extract_pdf_text(f)
        if len(text) < 40:
            text = text or '（此 PDF 無文字層，可能為掃描影像檔；未進行 OCR）'
        lines += [text, ""]
    if skipped:
        lines.append(f"（另有 {skipped} 個 PDF 附件超出單案上限，僅列於附件清單）")

    return title, '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--upload', action='store_true',
                        help='upload downloads/consolidated/ to GCS')
    parser.add_argument('--limit', type=int,
                        help='only process first N cases (for testing)')
    parser.add_argument('--ext', choices=['md', 'txt'], default='txt',
                        help='output extension (default txt — Gemini '
                             'Enterprise/Vertex AI Search data stores do '
                             'not list .md as a supported type)')
    parser.add_argument('--gcs-base', default='gs://BUCKET/climate-docs-consolidated',
                        help='gs:// prefix used inside manifest.jsonl '
                             '(edit to your real bucket before importing)')
    args = parser.parse_args()

    try:
        import pypdf  # noqa: F401
    except ImportError:
        print("pypdf is required: pip install pypdf")
        return 1

    if not METADATA.exists():
        print(f"Not found: {METADATA}")
        return 1
    if not ARCHIVE.is_dir():
        print(f"Not found: {ARCHIVE} — run phase2_download.py first")
        return 1

    docs = json.loads(METADATA.read_text(encoding='utf-8'))['documents']

    # A 案件 = one detail page
    cases = defaultdict(list)
    for doc in docs:
        cases[doc.get('detail_url') or f"standalone-{doc['id']}"].append(doc)
    print(f"{len(docs)} files grouped into {len(cases)} cases")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    index_lines = ["# 氣候資訊公開平臺文件彙整索引", "",
                   f"共 {len(cases)} 個案件。每案一個 Markdown 檔，"
                   f"含 metadata、附件清單與 PDF 內文。", ""]

    case_items = sorted(cases.items(), key=lambda kv: kv[1][0]['id'])
    if args.limit:
        case_items = case_items[:args.limit]

    manifest_lines = []
    for case_no, (detail_url, case_docs) in enumerate(case_items, 1):
        title, markdown = build_case_markdown(case_docs, case_no)
        fname = f"{case_no:03d}_{sanitize(title)[:60]}.{args.ext}"
        (OUT_DIR / fname).write_text(markdown, encoding='utf-8')
        first = case_docs[0]
        index_lines.append(
            f"{case_no}. [{title}]({fname}) — "
            f"{first.get('organization', '-')}／{first.get('type', '-')}"
            f"／{first.get('publish_date', '-')}")

        # Vertex AI Search import manifest, in the exact native-Document
        # format proven during the W04 uploads: id must be the MD5 of the
        # filename (no CJK, <=63 chars), plain `id` (NOT `_id`), and no
        # data_schema="custom" at import time or content.uri is ignored.
        doc_id = hashlib.md5(fname.encode('utf-8')).hexdigest()
        manifest_lines.append(json.dumps({
            'id': doc_id,
            'structData': {
                'title': title,
                'organization': first.get('organization', ''),
                'org_type': first.get('org_type', ''),
                'county': first.get('county', ''),
                'category': first.get('category', ''),
                'report_type': first.get('type', ''),
                'status': first.get('status', ''),
                'publish_date': first.get('publish_date', ''),
                'detail_url': first.get('detail_url', ''),
            },
            'content': {'mimeType': 'text/plain',
                        'uri': f"{args.gcs_base.rstrip('/')}/{fname}"},
        }, ensure_ascii=False))

        if case_no % 25 == 0 or case_no == len(case_items):
            print(f"  consolidated {case_no}/{len(case_items)}")

    (OUT_DIR / 'manifest.jsonl').write_text('\n'.join(manifest_lines),
                                            encoding='utf-8')

    (OUT_DIR / f'INDEX.{args.ext}').write_text('\n'.join(index_lines),
                                               encoding='utf-8')
    total_size = sum(f.stat().st_size for f in OUT_DIR.glob(f'*.{args.ext}'))
    print(f"\nDone: {len(case_items)} case files + INDEX.{args.ext} + "
          f"manifest.jsonl in {OUT_DIR} ({human_size(total_size)})")

    if args.upload:
        project = os.getenv('GCP_PROJECT_ID')
        bucket = os.getenv('GCS_BUCKET_NAME')
        if not project or not bucket:
            print("Set GCP_PROJECT_ID and GCS_BUCKET_NAME to upload")
            return 1
        from gcs_uploader import GCSUploader
        uploader = GCSUploader(project, bucket, prefix=GCS_PREFIX)
        stats = uploader.upload_directory(OUT_DIR, remote_prefix=GCS_PREFIX)
        print(f"Uploaded {stats['success']}/{stats['total']} to "
              f"gs://{bucket}/{GCS_PREFIX}/")
    return 0


if __name__ == '__main__':
    sys.exit(main())
