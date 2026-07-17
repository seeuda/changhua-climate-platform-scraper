"""Extraction-logic tests using synthetic HTML that mimics the real site.

The real cca.gov.tw blocks cloud/bot clients, so these tests anchor on the
one structure we verified externally: download links of the form
https://service.cca.gov.tw/File/Get/cca/zh-tw/<token> (no file extension).

Run: python -m pytest tests/ -v   (or: python tests/test_extraction.py)
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from scraper import ClimateDocumentScraper  # noqa: E402
from fileinfo import filename_from_disposition, format_from_headers  # noqa: E402

BASE = "https://www.cca.gov.tw/information-service/info/2095.html"

SYNTHETIC_HTML = """
<html><body>
<table>
<tr><th>項次</th><th>名稱</th><th>日期</th><th>下載</th></tr>
<tr>
  <td>1</td><td>南投縣第二期溫室氣體減量執行方案（核定本）</td><td>112.05.03</td>
  <td><a href="https://service.cca.gov.tw/File/Get/cca/zh-tw/mIYeHpOAizxs4Mt">PDF下載</a></td>
</tr>
<tr>
  <td>2</td><td>台北市溫室氣體管制執行方案成果報告</td><td>2023-11-20</td>
  <td><a href="/File/Get/cca/zh-tw/AbCdEfG123">下載</a></td>
</tr>
<tr>
  <td>3</td><td>第三期能源部門溫室氣體減量行動方案</td><td>113年3月</td>
  <td><a href="https://service.cca.gov.tw/File/Get/cca/zh-tw/9AB5bQyMcKCbhJz"
         title="行動方案.docx">ODF</a></td>
</tr>
</table>
<ul class="list">
  <li>嘉義市112年度執行方案成果報告 (2.5 MB)
      <a href="https://service.cca.gov.tw/File/Get/cca/zh-tw/XyZ789">檔案下載</a></li>
</ul>
<div class="pagination">
  <a href="/information-service/info/2095.html?page=2">2</a>
  <a href="/information-service/info/2095.html?page=3">3</a>
</div>
</body></html>
"""


def test_extraction():
    scraper = ClimateDocumentScraper()
    docs = scraper.extract_documents(SYNTHETIC_HTML, BASE)
    assert len(docs) == 4

    d1, d2, d3, d4 = docs

    # Row context recovery: title from title cell, not the button anchor
    assert d1['title'] == '南投縣第二期溫室氣體減量執行方案（核定本）'
    assert d1['organization'] == '南投縣政府'
    assert d1['org_type'] == '地方政府'
    assert d1['county'] == '南投縣'
    assert d1['publish_date'] == '2023-05-03'  # ROC 112.05.03
    assert d1['type'] == '執行方案'
    assert d1['file_format'] == 'PDF'  # from "PDF下載" button label

    # 台→臺 normalization; relative URL resolved against base
    assert d2['organization'] == '臺北市政府'
    assert d2['type'] == '成果報告'
    assert d2['publish_date'] == '2023-11-20'
    assert d2['download_url'] == 'https://www.cca.gov.tw/File/Get/cca/zh-tw/AbCdEfG123'

    # Central agency doc; ROC year-only date; format from anchor title attr
    assert d3['type'] == '行動方案'
    assert d3['org_type'] == '中央部會'
    assert d3['county'] == '中央'
    assert d3['publish_date'] == '2024'  # 113年
    assert d3['file_format'] == 'Word'

    # li-based list item; size text on the row
    assert d4['title'] == '嘉義市112年度執行方案成果報告 (2.5 MB)'
    assert d4['organization'] == '嘉義市政府'
    assert d4['file_size'] == '2.5 MB'
    assert d4['publish_date'] == '2023'  # 112年度


def test_pagination_discovery():
    scraper = ClimateDocumentScraper()
    pages = scraper.discover_page_urls(SYNTHETIC_HTML, BASE)
    assert pages == [
        'https://www.cca.gov.tw/information-service/info/2095.html?page=2',
        'https://www.cca.gov.tw/information-service/info/2095.html?page=3',
    ]


def test_fileinfo_helpers():
    assert filename_from_disposition(
        "attachment; filename*=UTF-8''%E5%A0%B1%E5%91%8A.pdf") == '報告.pdf'
    assert filename_from_disposition(
        'attachment; filename="report.docx"') == 'report.docx'
    assert format_from_headers(
        {'Content-Disposition': 'attachment; filename="a.pdf"'}) == 'PDF'
    assert format_from_headers({'Content-Type': 'application/zip'}) == 'ZIP'
    assert format_from_headers({}) == ''


if __name__ == '__main__':
    test_extraction()
    test_pagination_discovery()
    test_fileinfo_helpers()
    print("ALL TESTS PASSED")
