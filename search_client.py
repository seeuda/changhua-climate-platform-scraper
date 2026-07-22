"""Shared Discovery Engine Search call, used by both the CLI
(query_search.py) and the local web UI (webapp.py) so the two never
drift out of sync.

Per COST_POLICY.md rule 1, this is the ONLY retrieval path — Discovery
Engine Search with built-in summarization (billed within the Vertex AI
Search allowance). No Gemini API call anywhere in this file.
"""

import sys

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
        .SnippetSpec(return_snippet=True),
        # snippet_spec alone returns raw keyword-context fragments (choppy
        # list/table excerpts like "…6-1…6-2…6-3…"). extractive_content_spec
        # asks for coherent, sentence/paragraph-level segments instead —
        # this is the field that actually improves excerpt readability.
        extractive_content_spec=discoveryengine.SearchRequest
        .ContentSearchSpec.ExtractiveContentSpec(
            max_extractive_segment_count=3,
            max_extractive_answer_count=1))
    if with_summary:
        content_spec.summary_spec = (
            discoveryengine.SearchRequest.ContentSearchSpec.SummarySpec(
                summary_result_count=5,
                include_citations=True,
                language_code='zh-TW',
                use_semantic_chunks=True,
                # Explicit (not relying on assumed defaults): don't let
                # the server silently skip summary generation because it
                # heuristically judged the query "not summary-seeking" —
                # this looked like the cause of the summary box never
                # appearing for a normal question-style query.
                ignore_non_summary_seeking_query=False,
                ignore_adversarial_query=False,
                ignore_low_relevant_content=False))

    request = discoveryengine.SearchRequest(
        serving_config=serving_config,
        query=query,
        page_size=page_size,
        content_search_spec=content_spec)

    response = client.search(request=request)
    return parse_response(response, with_summary=with_summary)


def _struct_to_dict(value):
    """Recursively convert a Discovery Engine struct field (struct_data
    / derived_struct_data, or any value nested inside them) to plain
    Python dict/list/str/float/bool/None.

    These fields arrive as proto-plus MapComposite (mapping-like) and
    RepeatedComposite (sequence-like) wrappers — not dict/list
    subclasses, so `isinstance(x, dict)` against them is always False
    and silently drops nested data (that was the first bug here: every
    result's snippets vanished, leaving only the plain-string title and
    detail_url — 'only a link to the report page, no real content').

    The obvious next fix — unwrap via `.​_pb` and run
    `google.protobuf.json_format.MessageToDict` — also breaks: for a
    `map<string, Value>`-typed field (as struct_data/derived_struct_data
    actually are, confirmed empirically against a live
    google.cloud.discoveryengine_v1.Document), `._pb` is a raw
    `MessageMapContainer`, which has no `.DESCRIPTOR` and MessageToDict
    requires one.

    The only approach that works for both MapComposite and
    RepeatedComposite is walking the Mapping/Sequence protocol they
    actually implement (`.keys()` / iteration) — no unwrapping needed.
    """
    if value is None:
        return None
    if hasattr(value, 'keys'):
        return {k: _struct_to_dict(value[k]) for k in value.keys()}
    if hasattr(value, '__iter__') and not isinstance(value, (str, bytes)):
        return [_struct_to_dict(v) for v in value]
    return value


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
        # An untouched struct_data/derived_struct_data field reads back
        # as Python None (not an empty MapComposite) — verified against
        # a live Document. `or {}` guards the .get() calls below against
        # that real, not just theoretical, case.
        derived = _struct_to_dict(doc.derived_struct_data) or {}
        struct = _struct_to_dict(doc.struct_data) or {}

        title = (struct.get('title') or derived.get('title')
                 or derived.get('link', '').split('/')[-1] or doc.id)

        # extractive_content_spec asks the API for coherent segments,
        # which read far better than snippet_spec's raw keyword-context
        # fragments (e.g. "…6-1…6-2…6-3…"). The exact key(s) Discovery
        # Engine uses in derived_struct_data for this aren't pinned down
        # in the client's static proto (derived_struct_data is a free-
        # form map filled in server-side), so check every plausible name
        # and fall back to snippets if none are present — this also
        # means a real response's raw keys are worth logging (see
        # webapp.py) to confirm which one is actually in use.
        excerpts = []
        for key in ('extractive_segments', 'extractive_answers', 'snippets'):
            for item in derived.get(key) or []:
                if not isinstance(item, dict):
                    continue
                text = item.get('content') or item.get('snippet') or ''
                if text and text not in excerpts:
                    excerpts.append(text)
            if excerpts:
                break
        else:
            # None of the expected keys had usable content — print what
            # derived_struct_data actually contained so the real key
            # name (if different from our guesses) can be read off a
            # live run instead of guessed again.
            print(f"[search_client] no excerpt found; "
                 f"derived_struct_data keys were: {sorted(derived.keys())}",
                 file=sys.stderr)

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
            'snippets': excerpts[:2],
        })

    return {'summary': summary, 'results': results}
