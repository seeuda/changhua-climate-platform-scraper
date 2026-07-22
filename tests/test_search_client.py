"""Unit tests for search_client's response-parsing logic.

No live GCP call is made. Struct-backed fields (struct_data /
derived_struct_data) are built as real google.protobuf.struct_pb2.Struct
messages rather than plain Python dicts, so these tests exercise the
same MapComposite-style conversion path the real Discovery Engine client
returns. An earlier version of this suite used plain dicts, which
happened to satisfy `isinstance(x, dict)` checks that silently failed
against the real API's MapComposite objects — the tests passed while
production dropped every result's snippets. _struct_to_dict() and its
dedicated tests exist specifically to catch that class of bug.

Run: python tests/test_search_client.py
"""

import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).parent.parent))

from google.protobuf import struct_pb2  # noqa: E402

from search_client import _struct_to_dict, parse_response  # noqa: E402


def make_struct(data: dict) -> struct_pb2.Struct:
    s = struct_pb2.Struct()
    s.update(data)
    return s


class _ProtoPlusStyleWrapper:
    """Mimics proto-plus's MapComposite: not a dict subclass, exposes
    the raw protobuf message via ._pb — the shape _struct_to_dict must
    handle for real API responses."""

    def __init__(self, pb_struct):
        self._pb = pb_struct

    def __bool__(self):
        return True


class FakeDoc:
    def __init__(self, doc_id, struct_data=None, derived_struct_data=None):
        self.id = doc_id
        self.struct_data = _ProtoPlusStyleWrapper(make_struct(struct_data or {}))
        self.derived_struct_data = _ProtoPlusStyleWrapper(
            make_struct(derived_struct_data or {}))


class FakeResult:
    def __init__(self, document):
        self.document = document


def make_response(summary_text=None, results=None):
    summary = SimpleNamespace(summary_text=summary_text) if summary_text is not None else None
    return SimpleNamespace(summary=summary, results=results or [])


def test_struct_to_dict_nested_list_of_dicts():
    """The exact shape (list of dicts under a struct field) that the
    isinstance(x, dict) bug silently dropped."""
    s = make_struct({'title': 'X', 'snippets': [{'snippet': 'a'}, {'snippet': 'b'}]})
    out = _struct_to_dict(s)
    assert out == {'title': 'X', 'snippets': [{'snippet': 'a'}, {'snippet': 'b'}]}


def test_struct_to_dict_handles_proto_plus_wrapper():
    wrapped = _ProtoPlusStyleWrapper(make_struct({'a': 1}))
    assert _struct_to_dict(wrapped) == {'a': 1}


def test_struct_to_dict_empty():
    assert _struct_to_dict(None) == {}
    assert _struct_to_dict({}) == {}


def test_parse_with_summary_and_snippets():
    doc = FakeDoc(
        'abc123',
        struct_data={'title': '南投縣第二期溫室氣體減量執行方案', 'organization': '南投縣政府',
                    'org_type': '地方政府', 'county': '南投縣', 'report_type': '計畫/方案',
                    'publish_date': '2023', 'detail_url': 'https://x/1001.html'},
        derived_struct_data={'snippets': [{'snippet': '本案減量目標為...'},
                                          {'snippet': '執行期程為 115-119 年'}]})
    resp = make_response(summary_text='南投縣的減量目標包含...', results=[FakeResult(doc)])

    out = parse_response(resp, with_summary=True)
    assert out['summary'] == '南投縣的減量目標包含...'
    assert len(out['results']) == 1
    r = out['results'][0]
    assert r['title'] == '南投縣第二期溫室氣體減量執行方案'
    assert r['organization'] == '南投縣政府'
    assert r['county'] == '南投縣'
    assert r['report_type'] == '計畫/方案'
    assert r['detail_url'] == 'https://x/1001.html'
    # This is the assertion that would have caught the MapComposite bug:
    # snippets must actually come through, not silently end up empty.
    assert r['snippets'] == ['本案減量目標為...', '執行期程為 115-119 年']


def test_parse_without_summary():
    doc = FakeDoc('def456', struct_data={'title': '測試文件'})
    resp = make_response(summary_text=None, results=[FakeResult(doc)])
    out = parse_response(resp, with_summary=False)
    assert out['summary'] == ''
    assert out['results'][0]['title'] == '測試文件'


def test_parse_empty_results():
    resp = make_response(summary_text='', results=[])
    out = parse_response(resp, with_summary=True)
    assert out['summary'] == ''
    assert out['results'] == []


def test_title_fallback_to_doc_id():
    doc = FakeDoc('fallback-id-789', struct_data={}, derived_struct_data={})
    resp = make_response(results=[FakeResult(doc)])
    out = parse_response(resp, with_summary=False)
    assert out['results'][0]['title'] == 'fallback-id-789'


def test_snippets_capped_at_two():
    doc = FakeDoc('cap-test', derived_struct_data={
        'snippets': [{'snippet': f's{i}'} for i in range(5)]})
    resp = make_response(results=[FakeResult(doc)])
    out = parse_response(resp, with_summary=False)
    assert len(out['results'][0]['snippets']) == 2


if __name__ == '__main__':
    test_struct_to_dict_nested_list_of_dicts()
    test_struct_to_dict_handles_proto_plus_wrapper()
    test_struct_to_dict_empty()
    test_parse_with_summary_and_snippets()
    test_parse_without_summary()
    test_parse_empty_results()
    test_title_fallback_to_doc_id()
    test_snippets_capped_at_two()
    print("ALL SEARCH CLIENT TESTS PASSED")
