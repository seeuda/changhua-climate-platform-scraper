"""End-to-end tests: flat archive download + post-download classification.

Simulates the real platform: extension-less download URLs that return the
actual filename via Content-Disposition. Verifies the download-once /
classify-afterwards flow, server-filename preference, resume-skip, and
hardlink views.

Run: python tests/test_download_manager.py
"""

import shutil
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).parent.parent))

from download_manager import DownloadManager  # noqa: E402
from organize import build_view  # noqa: E402
from rate_limiter import GLOBAL_RATE_LIMITER  # noqa: E402

PDF_BYTES = b'%PDF-1.4 fake test payload ' * 40

# Server-side filenames per token — like the real platform, the URL says
# nothing; only Content-Disposition carries the name.
SERVER_FILES = {
    'tokenAAA': '溫室氣體減量行動方案核定本.pdf',
    'tokenBBB': '112年度執行方案成果報告.pdf',
    'tokenCCC': None,  # server sends no Content-Disposition
}


class FakeFileHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        token = self.path.rsplit('/', 1)[-1]
        if '/File/Get/' not in self.path or token not in SERVER_FILES:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header('Content-Type', 'application/pdf')
        name = SERVER_FILES[token]
        if name:
            self.send_header('Content-Disposition',
                             f"attachment; filename*=UTF-8''{quote(name)}")
        self.send_header('Content-Length', str(len(PDF_BYTES)))
        self.end_headers()
        self.wfile.write(PDF_BYTES)

    def log_message(self, *args):
        pass


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
        # Unidentified org — must still be downloaded and appear in views
        {'id': 3, 'title': '某某機關調適計畫', 'type': '調適計畫',
         'organization': '未識別', 'org_type': '中央部會', 'county': '中央',
         'publish_date': '', 'file_format': 'PDF',
         'download_url': f'{base_url}/File/Get/cca/zh-tw/tokenCCC'},
    ]


def main():
    GLOBAL_RATE_LIMITER.min_interval = 0.01  # speed up test only

    server = HTTPServer(('127.0.0.1', 0), FakeFileHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base_url = f'http://127.0.0.1:{server.server_port}'
    tmp = Path(tempfile.mkdtemp(prefix='dl_test_'))

    try:
        docs = make_docs(base_url)
        archive = tmp / 'archive'

        # --- flat download: everything lands in one directory ---
        manager = DownloadManager(download_dir=archive, organize_by='flat')
        stats = manager.download_documents(docs, max_workers=2)
        assert stats['success'] == 3, stats
        assert stats['failed'] == 0, stats

        # Server filename preferred (id prefix + real name, not our title)
        f1 = archive / '00001_溫室氣體減量行動方案核定本.pdf'
        f2 = archive / '00002_112年度執行方案成果報告.pdf'
        assert f1.exists(), list(archive.iterdir())
        assert f2.exists(), list(archive.iterdir())
        # No Content-Disposition → falls back to title
        f3 = archive / '00003_某某機關調適計畫.pdf'
        assert f3.exists(), list(archive.iterdir())
        assert f1.read_bytes() == PDF_BYTES
        print("PASS: flat archive + server-filename preference")

        # --- rerun skips everything already archived ---
        stats2 = DownloadManager(download_dir=archive, organize_by='flat') \
            .download_documents(docs, max_workers=2)
        assert stats2['success'] == 0 and stats2['skipped'] == 3, stats2
        print("PASS: resume skips archived files")

        # --- build two views from the same archive, no re-download ---
        s_org = build_view(docs, archive, tmp, 'org_type')
        s_date = build_view(docs, archive, tmp, 'date')
        assert s_org['linked'] + s_org['copied'] == 3, s_org
        assert s_org['missing'] == 0, s_org

        v1 = tmp / 'by_org_type' / '中央部會' / '環境部' / f1.name
        v2 = tmp / 'by_org_type' / '地方政府' / '南投縣政府' / f2.name
        v3 = tmp / 'by_org_type' / '中央部會' / '未識別' / f3.name
        assert v1.exists() and v2.exists(), list((tmp / 'by_org_type').rglob('*'))
        assert v3.exists(), "unidentified doc missing from view"
        assert (tmp / 'by_date' / '2023-05' / '環境部' / f1.name).exists()
        assert (tmp / 'by_date' / 'Unknown' / '未識別' / f3.name).exists()

        # Hardlinks: same inode as archive, no extra disk
        assert v1.stat().st_ino == f1.stat().st_ino, "expected hardlink"
        print("PASS: hardlink views (org_type + date) incl. 未識別 docs")

        # --- rebuilding a view is idempotent ---
        s_again = build_view(docs, archive, tmp, 'org_type')
        assert s_again['skipped'] == 3 and s_again['linked'] == 0, s_again
        print("PASS: view rebuild is idempotent")

        print("\nALL DOWNLOAD + ORGANIZE TESTS PASSED")
    finally:
        server.shutdown()
        shutil.rmtree(tmp, ignore_errors=True)
        GLOBAL_RATE_LIMITER.min_interval = 2.0


if __name__ == '__main__':
    main()
