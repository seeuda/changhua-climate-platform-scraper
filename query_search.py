#!/usr/bin/env python3
"""Canonical query tool: Vertex AI Search FIRST, Gemini API never by default.

This is the default retrieval path for the climate-docs data store.
It uses the Discovery Engine Search API with built-in summarization —
consuming the Vertex AI Search allowance/credits — and deliberately does
NOT import or call the Gemini API. See COST_POLICY.md for when (and only
when) direct Gemini calls are permitted.

Usage:
    set GCP_PROJECT_ID=your-project
    set DATA_STORE_ID=your-datastore-id
    python query_search.py "彰化縣第二期執行方案的減量目標是什麼"
    python query_search.py --no-summary "南投縣 調適 水資源"   (retrieval only)
"""

import argparse
import os
import sys

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from search_client import search_documents  # noqa: E402


def print_results(query: str, project: str, data_store: str,
                  page_size: int = 10, with_summary: bool = True):
    result = search_documents(query, project, data_store,
                              page_size=page_size, with_summary=with_summary)

    if with_summary:
        print("=" * 60)
        print("摘要（由 Search 內建生成，計入 Search 額度）")
        print("=" * 60)
        print(result['summary'] or "（無法生成摘要）")

    print("\n" + "=" * 60)
    print("檢索結果")
    print("=" * 60)
    for i, doc in enumerate(result['results'], 1):
        print(f"\n[{i}] {doc['title']}")
        for key in ('organization', 'report_type', 'publish_date'):
            if doc[key]:
                print(f"    {key}: {doc[key]}")
        for snip in doc['snippets']:
            print(f"    …{snip[:160]}…")
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('query', help='查詢字串')
    parser.add_argument('--no-summary', action='store_true',
                        help='只檢索不生成摘要（更省額度）')
    parser.add_argument('--page-size', type=int, default=10)
    args = parser.parse_args()

    project = os.getenv('GCP_PROJECT_ID')
    data_store = os.getenv('DATA_STORE_ID')
    if not project or not data_store:
        print("請先設定環境變數 GCP_PROJECT_ID 與 DATA_STORE_ID")
        return 1

    print_results(args.query, project, data_store,
                 page_size=args.page_size, with_summary=not args.no_summary)
    return 0


if __name__ == '__main__':
    sys.exit(main())
