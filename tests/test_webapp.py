"""Route-level tests for webapp.py using Flask's test client.

search_client.search_documents is monkeypatched so these run without
real GCP credentials or network access.

Run: python tests/test_webapp.py
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

os.environ.setdefault('GCP_PROJECT_ID', 'fake-project')
os.environ.setdefault('DATA_STORE_ID', 'fake-store')

import webapp  # noqa: E402

FAKE_RESULT = {
    'summary': '測試摘要內容',
    'results': [
        {'title': '南投縣執行方案', 'organization': '南投縣政府', 'org_type': '地方政府',
         'county': '南投縣', 'report_type': '計畫/方案', 'publish_date': '2023',
         'detail_url': 'https://x/1.html', 'snippets': ['南投片段']},
        {'title': '臺北市成果報告', 'organization': '臺北市政府', 'org_type': '地方政府',
         'county': '臺北市', 'report_type': '成果', 'publish_date': '2024',
         'detail_url': 'https://x/2.html', 'snippets': ['臺北片段']},
    ],
}


def test_index_page_loads():
    client = webapp.app.test_client()
    resp = client.get('/')
    assert resp.status_code == 200
    assert '氣候資訊公開平臺文件查詢'.encode() in resp.data


def test_search_requires_query():
    client = webapp.app.test_client()
    resp = client.post('/api/search', json={'query': ''})
    assert resp.status_code == 400
    assert '請輸入查詢字串' in resp.get_json()['error']


def test_search_returns_all_results_without_filter(monkeypatch):
    monkeypatch.setattr(webapp, 'search_documents', lambda *a, **kw: FAKE_RESULT)
    client = webapp.app.test_client()
    resp = client.post('/api/search', json={'query': '執行方案'})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['summary'] == '測試摘要內容'
    assert len(data['results']) == 2


def test_search_county_filter_narrows_results(monkeypatch):
    monkeypatch.setattr(webapp, 'search_documents', lambda *a, **kw: FAKE_RESULT)
    client = webapp.app.test_client()
    resp = client.post('/api/search',
                       json={'query': '執行方案', 'county': '南投縣'})
    data = resp.get_json()
    assert len(data['results']) == 1
    assert data['results'][0]['organization'] == '南投縣政府'


def test_search_report_type_filter(monkeypatch):
    monkeypatch.setattr(webapp, 'search_documents', lambda *a, **kw: FAKE_RESULT)
    client = webapp.app.test_client()
    resp = client.post('/api/search',
                       json={'query': '執行方案', 'report_type': '成果'})
    data = resp.get_json()
    assert len(data['results']) == 1
    assert data['results'][0]['title'] == '臺北市成果報告'


def test_search_api_error_returns_502(monkeypatch):
    def boom(*a, **kw):
        raise RuntimeError('Discovery Engine unreachable')
    monkeypatch.setattr(webapp, 'search_documents', boom)
    client = webapp.app.test_client()
    resp = client.post('/api/search', json={'query': '執行方案'})
    assert resp.status_code == 502
    assert 'unreachable' in resp.get_json()['error']


class _MonkeyPatch:
    """Minimal monkeypatch shim so this file can run standalone with
    `python tests/test_webapp.py` instead of requiring pytest."""

    def __init__(self):
        self._restore = []

    def setattr(self, obj, name, value):
        self._restore.append((obj, name, getattr(obj, name)))
        setattr(obj, name, value)

    def undo(self):
        for obj, name, old in reversed(self._restore):
            setattr(obj, name, old)


if __name__ == '__main__':
    test_index_page_loads()
    test_search_requires_query()

    for fn in (test_search_returns_all_results_without_filter,
              test_search_county_filter_narrows_results,
              test_search_report_type_filter,
              test_search_api_error_returns_502):
        mp = _MonkeyPatch()
        try:
            fn(mp)
        finally:
            mp.undo()

    print("ALL WEBAPP TESTS PASSED")
