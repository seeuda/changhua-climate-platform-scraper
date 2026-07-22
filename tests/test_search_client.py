"""Unit tests for search_client's response-parsing logic.

No live GCP call is made, but the fakes are built from the REAL
google.cloud.discoveryengine_v1.Document type (constructed locally,
without any network call) rather than a hand-rolled stand-in — this
history has already burned us twice on that shortcut:

  1. Plain-dict fakes made `isinstance(snip, dict)` pass in tests while
     the real API's MapComposite/RepeatedComposite wrappers made the
     same check silently fail in production — the tests were green
     while every result's snippets were being dropped.
  2. A second attempted fix used `._pb` + `MessageToDict`, which looked
     right and would have passed a fake built the same way, but broke
     against the real client: struct_data/derived_struct_data are
     map<string, Value>-typed fields, whose `._pb` is a raw
     MessageMapContainer with no `.DESCRIPTOR`, not a `Struct` message.

Building fakes from the real Document type sidesteps both traps by
construction — there is no separate "fake shape" to accidentally get
wrong.

Run: python tests/test_search_client.py
"""

import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).parent.parent))

from google.cloud import discoveryengine_v1 as discoveryengine  # noqa: E402

from search_client import _struct_to_dict, parse_response  # noqa: E402


def make_doc(doc_id, struct_data=None, derived_struct_data=None):
    doc = discoveryengine.Document()
    doc.id = doc_id
    if struct_data is not None:
        doc.struct_data = struct_data
    if derived_struct_data is not None:
        doc.derived_struct_data = derived_struct_data
    return doc


def make_response(summary_text=None, docs=None):
    summary = SimpleNamespace(summary_text=summary_text) if summary_text is not None else None
    results = [SimpleNamespace(document=d) for d in (docs or [])]
    return SimpleNamespace(summary=summary, results=results)


def test_struct_to_dict_nested_list_of_dicts():
    """The exact shape (map field containing a list of maps) that the
    isinstance(x, dict) bug silently dropped, and that the MessageToDict
    attempt then broke on."""
    doc = make_doc('x', struct_data={'title': 'X',
                                     'snippets': [{'snippet': 'a'}, {'snippet': 'b'}]})
    out = _struct_to_dict(doc.struct_data)
    assert out == {'title': 'X', 'snippets': [{'snippet': 'a'}, {'snippet': 'b'}]}
    assert isinstance(out, dict)
    assert isinstance(out['snippets'], list)
    assert isinstance(out['snippets'][0], dict)


def test_struct_to_dict_never_assigned_field_is_none():
    """An untouched struct_data/derived_struct_data reads back as
    Python None (not an empty MapComposite) — verified against a live
    Document. _struct_to_dict must not crash on it (it just passes
    None through); callers that need a dict use `or {}` at the call
    site (see parse_response), which is what actually matters for a
    document with no matched snippets — exercised end-to-end by
    test_title_fallback_to_doc_id below."""
    doc = make_doc('empty')  # struct_data/derived_struct_data never assigned
    assert _struct_to_dict(doc.struct_data) is None
    assert _struct_to_dict(doc.derived_struct_data) is None


def test_parse_with_summary_and_snippets():
    doc = make_doc(
        'abc123',
        struct_data={'title': '南投縣第二期溫室氣體減量執行方案', 'organization': '南投縣政府',
                    'org_type': '地方政府', 'county': '南投縣', 'report_type': '計畫/方案',
                    'publish_date': '2023', 'detail_url': 'https://x/1001.html'},
        derived_struct_data={'snippets': [{'snippet': '本案減量目標為...'},
                                          {'snippet': '執行期程為 115-119 年'}]})
    resp = make_response(summary_text='南投縣的減量目標包含...', docs=[doc])

    out = parse_response(resp, with_summary=True)
    assert out['summary'] == '南投縣的減量目標包含...'
    assert len(out['results']) == 1
    r = out['results'][0]
    assert r['title'] == '南投縣第二期溫室氣體減量執行方案'
    assert r['organization'] == '南投縣政府'
    assert r['county'] == '南投縣'
    assert r['report_type'] == '計畫/方案'
    assert r['detail_url'] == 'https://x/1001.html'
    # The assertion that would have caught both prior bugs: snippets
    # must actually come through, not end up empty or raise.
    assert r['snippets'] == ['本案減量目標為...', '執行期程為 115-119 年']


def test_parse_without_summary():
    doc = make_doc('def456', struct_data={'title': '測試文件'})
    resp = make_response(summary_text=None, docs=[doc])
    out = parse_response(resp, with_summary=False)
    assert out['summary'] == ''
    assert out['results'][0]['title'] == '測試文件'


def test_parse_empty_results():
    resp = make_response(summary_text='', docs=[])
    out = parse_response(resp, with_summary=True)
    assert out['summary'] == ''
    assert out['results'] == []


def test_title_fallback_to_doc_id():
    doc = make_doc('fallback-id-789')
    resp = make_response(docs=[doc])
    out = parse_response(resp, with_summary=False)
    assert out['results'][0]['title'] == 'fallback-id-789'


def test_snippets_capped_at_two():
    doc = make_doc('cap-test', derived_struct_data={
        'snippets': [{'snippet': f's{i}'} for i in range(5)]})
    resp = make_response(docs=[doc])
    out = parse_response(resp, with_summary=False)
    assert len(out['results'][0]['snippets']) == 2


if __name__ == '__main__':
    test_struct_to_dict_nested_list_of_dicts()
    test_struct_to_dict_never_assigned_field_is_none()
    test_parse_with_summary_and_snippets()
    test_parse_without_summary()
    test_parse_empty_results()
    test_title_fallback_to_doc_id()
    test_snippets_capped_at_two()
    print("ALL SEARCH CLIENT TESTS PASSED")
