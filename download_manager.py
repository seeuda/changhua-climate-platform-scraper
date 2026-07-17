"""Download manager for climate platform documents.

Real download URLs (service.cca.gov.tw/File/Get/<token>) carry no file
extension, so the saved filename's extension comes from the server's
Content-Disposition header, falling back to the metadata's file_format.
"""

import logging
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, List, Optional

import requests

from config import SCRAPER_CONFIG
from fileinfo import (extension_for_format, filename_from_disposition,
                      format_from_headers, human_size)
from http_client import make_session
from rate_limiter import GLOBAL_RATE_LIMITER

logger = logging.getLogger(__name__)

ORGANIZE_METHODS = ['organization', 'org_type', 'county', 'type', 'category', 'date']


def route_subpath(doc: Dict, organize_by: str) -> Path:
    """Relative directory for a document under a given classification.

    Shared by DownloadManager (legacy direct routing) and organize.py
    (post-download views), so both always agree on the layout.
    """
    org = doc.get('organization') or 'Unknown'
    if organize_by == 'flat':
        return Path('.')
    if organize_by == 'org_type':
        return Path(doc.get('org_type') or 'Unknown') / org
    if organize_by == 'county':
        return Path(doc.get('county') or 'Unknown')
    if organize_by == 'type':
        return Path(doc.get('type') or 'Unknown') / org
    if organize_by == 'category':
        return Path(doc.get('category') or 'Unknown') / org
    if organize_by == 'date':
        return Path((doc.get('publish_date') or 'Unknown')[:7] or 'Unknown') / org
    return Path(org)  # 'organization' and fallback


class DownloadManager:
    """Bulk-download documents with polite rate limiting and progress tracking."""

    def __init__(self, download_dir: Path = None, organize_by: str = 'flat'):
        """
        Args:
            download_dir: Base download directory
            organize_by: 'flat' (default; classify afterwards with
                organize.py), or one of ORGANIZE_METHODS to route files
                into subdirectories during download
        """
        self.download_dir = download_dir or Path("downloads")
        self.download_dir.mkdir(parents=True, exist_ok=True)
        self.organize_by = organize_by

        self.session = make_session()

        self._stats_lock = threading.Lock()
        self.stats = {'total': 0, 'success': 0, 'failed': 0,
                      'skipped': 0, 'total_size': 0}
        self.failed_downloads: List[str] = []

    def _record(self, key: str, size: int = 0, error: Optional[str] = None):
        with self._stats_lock:
            self.stats[key] += 1
            self.stats['total_size'] += size
            if error:
                self.failed_downloads.append(error)

    def download_documents(self, documents: List[Dict], max_workers: int = None) -> Dict:
        """Download all documents. The global rate limiter keeps aggregate
        request spacing polite regardless of worker count."""
        max_workers = max_workers or SCRAPER_CONFIG.get('max_workers', 3)
        self.stats['total'] = len(documents)

        logger.info("=" * 60)
        logger.info(f"Downloading {len(documents)} files -> "
                    f"{self.download_dir.absolute()} (by {self.organize_by})")
        logger.info("=" * 60)

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {}
            for doc in documents:
                save_dir = self.get_save_directory(doc)
                save_dir.mkdir(parents=True, exist_ok=True)
                futures[executor.submit(self.download_document, doc, save_dir)] = doc

            for idx, future in enumerate(as_completed(futures), 1):
                doc = futures[future]
                try:
                    result = future.result()
                    if result:
                        logger.info(f"[{idx}/{len(documents)}] OK {result['filename']}"
                                    f" ({human_size(result['size'])})")
                except Exception as e:
                    logger.error(f"[{idx}/{len(documents)}] "
                                 f"FAIL {doc.get('title', 'Unknown')}: {e}")

        return self.generate_report()

    def get_save_directory(self, doc: Dict) -> Path:
        """Route a document to its directory per the classification method."""
        return self.download_dir / route_subpath(doc, self.organize_by)

    def download_document(self, doc: Dict, save_dir: Path) -> Optional[Dict]:
        """Download one document; skip if a file for its id already exists."""
        url = doc.get('download_url', '')
        if not url:
            self._record('skipped')
            return None

        doc_id = str(doc.get('id', '0')).zfill(5)
        existing = list(save_dir.glob(f"{doc_id}_*"))
        if existing:
            self._record('skipped')
            logger.debug(f"Already downloaded, skipping: {existing[0].name}")
            return None

        GLOBAL_RATE_LIMITER.acquire()
        try:
            response = self.session.get(
                url, timeout=SCRAPER_CONFIG.get('request_timeout', 10), stream=True)
            response.raise_for_status()

            filepath = save_dir / self.build_filename(doc, response.headers)
            total_size = 0
            with open(filepath, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        total_size += len(chunk)

            self._record('success', size=total_size)
            return {'filename': filepath.name, 'size': total_size,
                    'title': doc.get('title', ''), 'url': url}

        except requests.exceptions.RequestException as e:
            self._record('failed', error=f"{doc.get('title', 'Unknown')}: {e}")
            logger.error(f"Download failed {doc.get('title', 'Unknown')}: {e}")
            return None

    def build_filename(self, doc: Dict, headers) -> str:
        """{id}_{server filename} — the platform's own filename, not a
        preset one. The id prefix guarantees uniqueness (many documents
        share generic names like 成果報告.pdf) and drives resume-skip.
        Falls back to the page title only when the server sends no name.
        """
        doc_id = str(doc.get('id', '0')).zfill(5)

        server_name = filename_from_disposition(
            headers.get('Content-Disposition', ''))
        if server_name:
            return f"{doc_id}_{self.sanitize(server_name)[:120]}"

        title = self.sanitize((doc.get('title') or 'document')[:50])
        fmt = format_from_headers(headers) or doc.get('file_format', '')
        return f"{doc_id}_{title}{extension_for_format(fmt)}"

    @staticmethod
    def sanitize(name: str) -> str:
        for char in '/\\:*?"<>|':
            name = name.replace(char, '_')
        return name.strip()

    def generate_report(self) -> Dict:
        logger.info("=" * 60)
        logger.info(f"Total: {self.stats['total']}  "
                    f"OK: {self.stats['success']}  "
                    f"Failed: {self.stats['failed']}  "
                    f"Skipped: {self.stats['skipped']}  "
                    f"Size: {human_size(self.stats['total_size'])}")
        if self.failed_downloads:
            logger.warning(f"Failed downloads ({len(self.failed_downloads)}):")
            for error in self.failed_downloads[:10]:
                logger.warning(f"  - {error}")
            if len(self.failed_downloads) > 10:
                logger.warning(f"  ... and {len(self.failed_downloads) - 10} more")
        logger.info("=" * 60)
        return self.stats

    @staticmethod
    def format_size(size_bytes: int) -> str:
        return human_size(size_bytes)

    def get_directory_structure(self) -> Dict:
        """Summarize downloaded files by top-level directory."""
        structure = {}
        for subdir in self.download_dir.iterdir():
            if subdir.is_dir():
                files = [f for f in subdir.rglob('*') if f.is_file()]
                structure[subdir.name] = {
                    'count': len(files),
                    'size': sum(f.stat().st_size for f in files),
                }
        return structure
