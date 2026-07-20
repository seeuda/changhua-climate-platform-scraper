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
# Vertex AI Search rejected our 4 largest consolidated documents (the
# 2023-2026 national GHG inventory reports) with "Document segmentation
# stage failure: Request contains an invalid argument" — the per-document
# processing ceiling was exceeded. Cap total body text per case well
# under that ceiling; overflow is listed in the attachment table only.
MAX_CASE_BODY_BYTES = 1_500_000
TABLE_EXTS = {'.xlsx', '.xls', '.ods', '.csv', '.odt', '.zip'}
# The platform's "全文下載" (full-report) PDF duplicates every chapter
# PDF already present in the same case. Keeping both roughly doubles the
# exported text for no benefit and was the direct cause of the four
# oversized documents above.
FULL_REPORT_RE = re.compile(r'全文下載|^\d+\.?\s*全文\b')


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

    # Resolve archive files once so both the attachment table and the
    # body pass see the same set.
    resolved = [(doc, find_archive_file(doc['id'])) for doc in case_docs]
    all_pdfs = [(doc, f) for doc, f in resolved if f and f.suffix.lower() == '.pdf']

    # Identify duplicate full-report PDFs to exclude from the body (see
    # FULL_REPORT_RE above) — only when chapter-level PDFs exist too, so
    # a case with just one PDF never loses its only content.
    dup_ids = set()
    if len(all_pdfs) > 1:
        for doc, f in all_pdfs:
            if FULL_REPORT_RE.search(unquote(f.name)):
                dup_ids.add(doc['id'])

    # Attachment inventory (everything listed, tables and duplicates flagged)
    lines += ["## 附件清單", ""]
    body_targets = []
    for doc, f in resolved:
        name = unquote(f.name) if f else f"{doc['id']:05d}（未下載）"
        size = human_size(f.stat().st_size) if f else '-'
        ext = f.suffix.lower() if f else ''
        tag = ''
        if ext in TABLE_EXTS:
            tag = '（表格/資料檔，未納入內文）'
        elif doc['id'] in dup_ids:
            tag = '（與其餘章節內容重複，未納入內文以節省空間）'
        elif ext == '.pdf' and f:
            body_targets.append((doc, f))
        elif f and ext != '.pdf':
            tag = '（非 PDF，未納入內文）'
        lines.append(f"- {name} — {size} {tag}  ")
        lines.append(f"  來源: {doc.get('download_url', '-')}")
    lines.append("")

    # Body: extracted text from PDFs, bounded by an attachment-count cap
    # and a total-size cap (see MAX_CASE_BODY_BYTES above).
    lines += ["## 內文（自 PDF 附件抽取）", ""]
    if not body_targets:
        lines.append("（本案件無 PDF 附件，或 PDF 未成功下載）")
    skipped_count = 0
    skipped_reason = ''
    body_bytes = 0
    for i, (doc, f) in enumerate(body_targets):
        if i >= MAX_PDFS_PER_CASE:
            skipped_count = len(body_targets) - MAX_PDFS_PER_CASE
            skipped_reason = '單案附件數量上限'
            break
        if body_bytes >= MAX_CASE_BODY_BYTES:
            skipped_count = len(body_targets) - i
            skipped_reason = '單案內容大小上限'
            break
        lines += [f"### {unquote(f.name)}", ""]
        text = extract_pdf_text(f)
        if len(text) < 40:
            text = text or '（此 PDF 無文字層，可能為掃描影像檔；未進行 OCR）'
        body_bytes += len(text.encode('utf-8'))
        lines += [text, ""]
    if skipped_count:
        lines.append(f"（另有 {skipped_count} 個 PDF 附件超出{skipped_reason}，"
                     f"僅列於附件清單，請至來源下載）")

    stats = {'deduped': bool(dup_ids), 'size_capped': skipped_reason == '單案內容大小上限'}
    return title, '\n'.join(lines), stats


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
    deduped_cases = []
    capped_cases = []
    for case_no, (detail_url, case_docs) in enumerate(case_items, 1):
        title, markdown, stats = build_case_markdown(case_docs, case_no)
        if stats['deduped']:
            deduped_cases.append(title)
        if stats['size_capped']:
            capped_cases.append(title)
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

    if deduped_cases:
        print(f"\n{len(deduped_cases)} 案排除了重複的「全文下載」附件"
              f"（節省空間、避免重複內容）：")
        for t in deduped_cases:
            print(f"  - {t}")
    if capped_cases:
        print(f"\n{len(capped_cases)} 案觸及單案內容大小上限，"
              f"部分附件僅列於清單未納入內文：")
        for t in capped_cases:
            print(f"  - {t}")
    if not deduped_cases and not capped_cases:
        print("\n沒有案件觸發去重複或大小上限規則。")

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
