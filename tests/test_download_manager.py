"""End-to-end DownloadManager tests against a local HTTP server.

Simulates the real platform's behavior: extension-less download URLs that
return the actual filename via Content-Disposition.

Run: python tests/test_download_manager.py
"""

import shutil
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from download_manager import DownloadManager  # noqa: E402
from rate_limiter import GLOBAL_RATE_LIMITER  # noqa: E402

PDF_BYTES = b'%PDF-1.4 fake test payload ' * 40


class FakeFileHandler(BaseHTTPRequestHandler):
    """Serves /File/Get/<token> like service.cca.gov.tw: no extension in
    the URL, filename only in Content-Disposition."""

    def do_GET(self):
        if '/File/Get/' not in self.path:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header('Content-Type', 'application/pdf')
        self.send_header(
            'Content-Disposition',
            "attachment; filename*=UTF-8''%E6%B8%AC%E8%A9%A6%E5%A0%B1%E5%91%8A.pdf")
        self.send_header('Content-Length', str(len(PDF_BYTES)))
        self.end_headers()
        self.wfile.write(PDF_BYTES)

    def log_message(self, *args):
        pass  # keep test output clean


def make_docs(base_url):
    return [
        {'id': 1, 'title': '環境部溫室氣體減量行動方案', 'type': '行動方案',
         'organization': '環境部', 'org_type': '中央部會', 'county': '中央',
         'publish_date': '2023-05-03', 'file_format': 'PDF',
         'download_url': f'{base_url}/File/Get/cca/zh-tw/tokenAAA'},
        {'id': 2, 'title': '南投縣執行方案成果報告', 'type': '成果報告',
         'organization': '南投縣政府', 'org_type': '地方政府', 'county': '南投縣',
         'publish_date': '2024-01-15', 'file_format': '',
         'download_url': f'{base_url}/File/Get/cca/zh-tw/tokenBBB'},
        {'id': 3, 'title': '無連結文件', 'type': '其他',
         'organization': '環境部', 'org_type': '中央部會', 'county': '中央',
         'publish_date': '', 'file_format': '', 'download_url': ''},
    ]


def main():
    GLOBAL_RATE_LIMITER.min_interval = 0.01  # speed up test only

    server = HTTPServer(('127.0.0.1', 0), FakeFileHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base_url = f'http://127.0.0.1:{server.server_port}'
    tmp = Path(tempfile.mkdtemp(prefix='dl_test_'))

    try:
        docs = make_docs(base_url)

        # --- organize_by org_type: files routed to 機構類型/機關/ ---
        manager = DownloadManager(download_dir=tmp / 'by_org_type',
                                  organize_by='org_type')
        stats = manager.download_documents(docs, max_workers=2)
        assert stats['success'] == 2, stats
        assert stats['skipped'] == 1, stats  # the empty-URL doc
        assert stats['failed'] == 0, stats
        assert stats['total_size'] == 2 * len(PDF_BYTES), stats

        f1 = tmp / 'by_org_type' / '中央部會' / '環境部' / \
            '00001_環境部溫室氣體減量行動方案.pdf'
        f2 = tmp / 'by_org_type' / '地方政府' / '南投縣政府' / \
            '00002_南投縣執行方案成果報告.pdf'
        assert f1.exists(), f"missing {f1}; tree: {list((tmp / 'by_org_type').rglob('*'))}"
        assert f2.exists(), f"missing {f2}"
        assert f1.read_bytes() == PDF_BYTES
        # Extension .pdf came from Content-Disposition (URL has none)
        print("PASS: routing + Content-Disposition extension")

        # --- rerun: everything already downloaded is skipped, not re-fetched ---
        manager2 = DownloadManager(download_dir=tmp / 'by_org_type',
                                   organize_by='org_type')
        stats2 = manager2.download_documents(docs, max_workers=2)
        assert stats2['success'] == 0 and stats2['skipped'] == 3, stats2
        print("PASS: resume skips existing files")

        # --- organize_by county ---
        manager3 = DownloadManager(download_dir=tmp / 'by_county',
                                   organize_by='county')
        manager3.download_documents(docs[:2], max_workers=1)
        assert (tmp / 'by_county' / '中央').is_dir()
        assert (tmp / 'by_county' / '南投縣').is_dir()
        print("PASS: county routing")

        # --- directory structure summary counts nested files ---
        structure = manager2.get_directory_structure()
        assert structure['中央部會']['count'] == 1, structure
        assert structure['地方政府']['count'] == 1, structure
        print("PASS: directory structure summary")

        print("\nALL DOWNLOAD MANAGER TESTS PASSED")
    finally:
        server.shutdown()
        shutil.rmtree(tmp, ignore_errors=True)
        GLOBAL_RATE_LIMITER.min_interval = 2.0


if __name__ == '__main__':
    main()
