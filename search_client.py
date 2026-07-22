"""Shared Discovery Engine Search call, used by both the CLI
(query_search.py) and the local web UI (webapp.py) so the two never
drift out of sync.

Per COST_POLICY.md rule 1, this is the ONLY retrieval path — Discovery
Engine Search with built-in summarization (billed within the Vertex AI
Search allowance). No Gemini API call anywhere in this file.
"""

TITLE_KEYS = ('title',)
ORG_KEYS = ('organization',)


def search_documents(query: str, project: str, data_store: str,
                     location: str = 'global', page_size: int = 10,
                     with_summary: bool = True) -> dict:
    """Run one search and return structured results (no printing/HTML).

    Returns:
        {'summary': str, 'results': [{'title', 'organization', 'org_type',
         'county', 'category', 'report_type', 'status', 'publish_date',
         'detail_url', 'snippets': [str, ...]}, ...]}
    """
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
    return parse_response(response, with_summary=with_summary)


def _struct_to_dict(struct_value) -> dict:
    """Convert a Discovery Engine struct field (struct_data /
    derived_struct_data) to plain Python dict/list/str.

    These fields arrive as proto-plus MapComposite objects wrapping a
    protobuf Struct — NOT dict subclasses. `dict(map_composite)` only
    converts the top level; nested values (e.g. the list under
    'snippets') stay as MapComposite/RepeatedComposite, so a later
    `isinstance(x, dict)` check on them is always False. That silently
    dropped every result's snippets — 'only see the report link, never
    the actual excerpted content' was this bug, not a data/config
    problem. MessageToDict on the underlying raw protobuf message does
    a full, correct conversion at every nesting level.
    """
    if not struct_value:
        return {}
    from google.protobuf.json_format import MessageToDict
    pb = struct_value._pb if hasattr(struct_value, '_pb') else struct_value
    return MessageToDict(pb)


def parse_response(response, with_summary: bool = True) -> dict:
    """Extract plain dicts from a Discovery Engine SearchResponse.

    Split out from search_documents() so the parsing logic can be unit
    tested against a fake response object without a live API call.
    """
    summary = ''
    if with_summary and getattr(response, 'summary', None):
        summary = response.summary.summary_text or ''

    results = []
    for result in response.results:
        doc = result.document
        derived = _struct_to_dict(doc.derived_struct_data)
        struct = _struct_to_dict(doc.struct_data)

        title = (struct.get('title') or derived.get('title')
                 or derived.get('link', '').split('/')[-1] or doc.id)

        snippets = []
        for snip in derived.get('snippets') or []:
            text = snip.get('snippet', '') if isinstance(snip, dict) else ''
            if text:
                snippets.append(text)

        results.append({
            'title': title,
            'organization': struct.get('organization', ''),
            'org_type': struct.get('org_type', ''),
            'county': struct.get('county', ''),
            'category': struct.get('category', ''),
            'report_type': struct.get('report_type', ''),
            'status': struct.get('status', ''),
            'publish_date': struct.get('publish_date', ''),
            'detail_url': struct.get('detail_url', ''),
            'snippets': snippets[:2],
        })

    return {'summary': summary, 'results': results}
