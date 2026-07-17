#!/usr/bin/env python3
"""Re-run organization classification over existing metadata — offline,
no re-scraping. Use after classification rules improve.

Run: python reclassify.py
Rewrites output/climate_docs_metadata.{csv,json} and the report.
"""

import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from scraper import ClimateDocumentScraper  # noqa: E402
from output_formatter import DocumentOutputFormatter  # noqa: E402
from report_generator import ReportGenerator  # noqa: E402

METADATA = Path('output/climate_docs_metadata.json')


def main():
    if not METADATA.exists():
        print(f"Not found: {METADATA} — run autopilot.py first")
        return 1

    data = json.loads(METADATA.read_text(encoding='utf-8'))
    docs = data['documents']
    scraper = ClimateDocumentScraper()

    changed = 0
    for doc in docs:
        if doc.get('organization') in ('', '未識別', None):
            # list_title (the 方案成果 row title) is the most reliable
            # source; the doc title may be a bare attachment name.
            basis = ' '.join(filter(None, [doc.get('list_title'),
                                           doc.get('title')]))
            org = scraper.classify_organization(basis, '')
            if org != '未識別':
                doc['organization'] = org
                changed += 1

        org = doc.get('organization') or '未識別'
        doc['org_type'] = ('地方政府' if str(org).endswith('政府')
                           else '未識別' if org == '未識別' else '中央部會')
        doc['county'] = (org.replace('政府', '')
                         if doc['org_type'] == '地方政府'
                         else '中央' if doc['org_type'] == '中央部會' else '')

    DocumentOutputFormatter.save_csv(docs)
    DocumentOutputFormatter.save_json(docs)
    scraper.documents = docs
    stats = scraper.get_statistics()
    ReportGenerator(docs, stats, [], 0.0).generate_markdown_report()

    print(f"Reclassified {changed} documents")
    print("by_org_type:", stats['by_org_type'])
    remaining = stats['by_organization'].get('未識別', 0)
    if remaining:
        print(f"\nStill unidentified: {remaining}. Sample titles:")
        shown = 0
        for doc in docs:
            if doc.get('organization') == '未識別' and shown < 10:
                print("  -", (doc.get('list_title') or doc.get('title'))[:70])
                shown += 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
