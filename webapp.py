#!/usr/bin/env python3
"""Local browser query UI for the climate-docs Vertex AI Search data
store — no per-seat Gemini Enterprise App subscription required.

Runs entirely on your own machine; nothing is exposed to the network
unless you explicitly pass --host 0.0.0.0. Uses the same Discovery
Engine Search API call as query_search.py (see search_client.py), so it
costs the same standard Search usage and nothing more.

Usage:
    set GCP_PROJECT_ID=your-project
    set DATA_STORE_ID=your-datastore-id
    pip install flask
    python webapp.py
    (then open http://127.0.0.1:5000 in your browser)
"""

import argparse
import json
import os
import sys
from pathlib import Path

from flask import Flask, jsonify, render_template_string, request

from search_client import search_documents

# 22 counties/cities, matching scraper.py's COUNTIES list, plus 中央
# for national-level documents. Used as the county filter's fallback
# option list when no local metadata file is available to read the
# real set from.
DEFAULT_COUNTIES = [
    '中央', '臺北市', '新北市', '桃園市', '臺中市', '臺南市', '高雄市',
    '基隆市', '新竹市', '嘉義市',
    '宜蘭縣', '新竹縣', '苗栗縣', '彰化縣', '南投縣', '雲林縣',
    '嘉義縣', '屏東縣', '花蓮縣', '臺東縣', '澎湖縣', '金門縣', '連江縣',
]
REPORT_TYPES = ['清冊', '計畫/方案', '成果', '國家報告', '目標', '綱領', '通訊']

METADATA_PATH = Path('output/climate_docs_metadata.json')

app = Flask(__name__)


def load_filter_options():
    """Prefer the real counties/orgs seen in the local metadata, if
    present, over the static fallback lists above."""
    counties, orgs = DEFAULT_COUNTIES, []
    if METADATA_PATH.exists():
        try:
            docs = json.loads(METADATA_PATH.read_text(encoding='utf-8'))['documents']
            counties = sorted({d.get('county', '') for d in docs if d.get('county')})
            orgs = sorted({d.get('organization', '') for d in docs if d.get('organization')})
        except (OSError, json.JSONDecodeError, KeyError):
            pass
    return counties, orgs


PAGE = """
<!doctype html>
<html lang="zh-Hant">
<head>
<meta charset="utf-8">
<title>氣候文件查詢</title>
<style>
  body { font-family: -apple-system, "Microsoft JhengHei", sans-serif;
         max-width: 900px; margin: 2rem auto; padding: 0 1rem; color: #222; }
  h1 { font-size: 1.4rem; }
  .bar { display: flex; gap: 0.5rem; flex-wrap: wrap; margin-bottom: 1rem; }
  input[type=text] { flex: 1; min-width: 240px; padding: 0.5rem; font-size: 1rem; }
  select, button { padding: 0.5rem; font-size: 1rem; }
  button { cursor: pointer; }
  #summary { background: #f4f7fa; border: 1px solid #dbe4ec; border-radius: 6px;
             padding: 1rem; margin-bottom: 1rem; white-space: pre-wrap; }
  .doc { border-bottom: 1px solid #e5e5e5; padding: 0.8rem 0; }
  .doc h3 { margin: 0 0 0.3rem; font-size: 1.05rem; }
  .doc .meta { color: #666; font-size: 0.85rem; margin-bottom: 0.3rem; }
  .doc .snippet { font-size: 0.9rem; color: #333; }
  .doc a { color: #1a5fb4; text-decoration: none; }
  #status { color: #888; font-size: 0.9rem; }
</style>
</head>
<body>
<h1>氣候資訊公開平臺文件查詢（本機工具，不經 Gemini Enterprise 應用程式）</h1>
<div class="bar">
  <input type="text" id="q" placeholder="輸入查詢字串，例如：彰化縣執行方案的減量目標">
  <select id="county"><option value="">縣市（不限）</option></select>
  <select id="report_type"><option value="">報告種類（不限）</option>
    {% for t in report_types %}<option value="{{ t }}">{{ t }}</option>{% endfor %}
  </select>
  <button onclick="doSearch()">查詢</button>
</div>
<div id="status"></div>
<div id="summary" style="display:none"></div>
<div id="results"></div>

<script>
const counties = {{ counties|tojson }};
const countySel = document.getElementById('county');
counties.forEach(c => {
  const opt = document.createElement('option');
  opt.value = c; opt.textContent = c;
  countySel.appendChild(opt);
});

document.getElementById('q').addEventListener('keydown', e => {
  if (e.key === 'Enter') doSearch();
});

async function doSearch() {
  const q = document.getElementById('q').value.trim();
  if (!q) return;
  const county = document.getElementById('county').value;
  const reportType = document.getElementById('report_type').value;
  document.getElementById('status').textContent = '查詢中…';
  document.getElementById('summary').style.display = 'none';
  document.getElementById('results').innerHTML = '';

  const resp = await fetch('/api/search', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({query: q, county: county, report_type: reportType})
  });
  const data = await resp.json();
  document.getElementById('status').textContent = '';

  if (data.error) {
    document.getElementById('status').textContent = '錯誤：' + data.error;
    return;
  }

  if (data.summary) {
    const s = document.getElementById('summary');
    s.style.display = 'block';
    s.textContent = data.summary;
  }

  const container = document.getElementById('results');
  if (data.results.length === 0) {
    container.innerHTML = '<p>沒有符合的結果。</p>';
    return;
  }
  data.results.forEach(doc => {
    const div = document.createElement('div');
    div.className = 'doc';
    const link = doc.detail_url
      ? `<a href="${doc.detail_url}" target="_blank">${doc.title}</a>`
      : doc.title;
    const meta = [doc.organization, doc.report_type, doc.publish_date]
      .filter(Boolean).join(' ／ ');
    const snippets = doc.snippets.map(s => `<div class="snippet">…${s}…</div>`).join('');
    div.innerHTML = `<h3>${link}</h3><div class="meta">${meta}</div>${snippets}`;
    container.appendChild(div);
  });
}
</script>
</body>
</html>
"""


@app.route('/')
def index():
    counties, _orgs = load_filter_options()
    return render_template_string(PAGE, counties=counties,
                                  report_types=REPORT_TYPES)


@app.route('/api/search', methods=['POST'])
def api_search():
    payload = request.get_json(force=True) or {}
    query = (payload.get('query') or '').strip()
    if not query:
        return jsonify({'error': '請輸入查詢字串'}), 400

    project = os.getenv('GCP_PROJECT_ID')
    data_store = os.getenv('DATA_STORE_ID')
    if not project or not data_store:
        return jsonify({'error': '伺服器未設定 GCP_PROJECT_ID / DATA_STORE_ID'}), 500

    try:
        result = search_documents(query, project, data_store, page_size=20)
    except Exception as e:
        return jsonify({'error': str(e)}), 502

    # Client-requested filters are applied to the returned page here
    # rather than as a Discovery Engine `filter=` expression, since the
    # manifest-imported structData fields aren't guaranteed to be
    # configured as filterable in the data store schema. This narrows
    # the top 20 results already fetched; it does not re-query for
    # matches beyond that page.
    county = payload.get('county') or ''
    report_type = payload.get('report_type') or ''
    docs = result['results']
    if county:
        docs = [d for d in docs if d.get('county') == county]
    if report_type:
        docs = [d for d in docs if d.get('report_type') == report_type]

    return jsonify({'summary': result['summary'], 'results': docs})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--host', default='127.0.0.1',
                        help='預設僅本機存取；設 0.0.0.0 才會對區網開放')
    parser.add_argument('--port', type=int, default=5000)
    args = parser.parse_args()

    if not os.getenv('GCP_PROJECT_ID') or not os.getenv('DATA_STORE_ID'):
        print("請先設定環境變數 GCP_PROJECT_ID 與 DATA_STORE_ID 再啟動")
        return 1

    print(f"啟動於 http://{args.host}:{args.port} （Ctrl+C 結束）")
    app.run(host=args.host, port=args.port, debug=False)
    return 0


if __name__ == '__main__':
    sys.exit(main())
