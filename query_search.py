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


def search(query: str, project: str, data_store: str,
           location: str = 'global', page_size: int = 10,
           with_summary: bool = True):
    from google.cloud import discoveryengine_v1 as discoveryengine

    client = discoveryengine.SearchServiceClient()
    serving_config = (
        f"projects/{project}/locations/{location}"
        f"/collections/default_collection/dataStores/{data_store}"
        f"/servingConfigs/default_config")

    content_spec = discoveryengine.SearchRequest.ContentSearchSpec(
        snippet_spec=discoveryengine.SearchRequest.ContentSearchSpec
        .SnippetSpec(return_snippet=True))
    if with_summary:
        content_spec.summary_spec = (
            discoveryengine.SearchRequest.ContentSearchSpec.SummarySpec(
                summary_result_count=5,
                include_citations=True,
                language_code='zh-TW'))

    request = discoveryengine.SearchRequest(
        serving_config=serving_config,
        query=query,
        page_size=page_size,
        content_search_spec=content_spec)

    response = client.search(request=request)

    if with_summary and response.summary:
        print("=" * 60)
        print("摘要（由 Search 內建生成，計入 Search 額度）")
        print("=" * 60)
        print(response.summary.summary_text or "（無法生成摘要）")

    print("\n" + "=" * 60)
    print("檢索結果")
    print("=" * 60)
    for i, result in enumerate(response.results, 1):
        doc = result.document
        data = dict(doc.derived_struct_data) if doc.derived_struct_data else {}
        struct = dict(doc.struct_data) if doc.struct_data else {}
        title = (struct.get('title') or data.get('title')
                 or data.get('link', '').split('/')[-1] or doc.id)
        print(f"\n[{i}] {title}")
        for key in ('organization', 'report_type', 'publish_date'):
            if struct.get(key):
                print(f"    {key}: {struct[key]}")
        snippets = data.get('snippets') or []
        for snip in snippets[:2]:
            text = snip.get('snippet', '') if isinstance(snip, dict) else ''
            if text:
                print(f"    …{text[:160]}…")
    return response


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

    search(args.query, project, data_store,
           with_summary=not args.no_summary, page_size=args.page_size)
    return 0


if __name__ == '__main__':
    sys.exit(main())
