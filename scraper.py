"""Scraper for 氣候資訊公開平臺 document metadata.

Target: https://www.cca.gov.tw/information-service/info/2095.html

Known facts about the real site (verified via search-engine snapshots,
since www.cca.gov.tw returns 403 to non-browser/foreign clients):

- Actual document download links use the pattern
      https://service.cca.gov.tw/File/Get/cca/zh-tw/<token>
  with NO file extension in the URL. File format and size therefore
  cannot be derived from the URL; they must be probed from the HTTP
  response headers (Content-Disposition / Content-Type / Content-Length)
  or read from labels on the page.

- The site must be scraped from a normal residential/office network in
  Taiwan with a browser User-Agent. Cloud/proxy egress IPs get 403.

Extraction strategy is anchored on the File/Get link pattern rather than
guessed CSS selectors: find every File/Get anchor, then walk up to its
row container (tr/li) to recover title, date, and organization context.
"""

import logging
import re
import time
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import urljoin, urlparse, parse_qs

import requests
from bs4 import BeautifulSoup

from config import CLIMATE_PLATFORM_URL, SCRAPER_CONFIG, DATA_DIR, EXPECTED_DOCUMENT_COUNT
from fileinfo import (EXTENSION_FORMATS, filename_from_disposition,
                      format_from_headers, human_size)
from http_client import make_session
from rate_limiter import GLOBAL_RATE_LIMITER

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(SCRAPER_CONFIG['log_file'], encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Verified real download-link pattern on cca.gov.tw
FILE_LINK_MARKER = '/File/Get/'

# 22 counties/cities. Titles may use 台 or 臺; normalize before matching.
COUNTIES = [
    '臺北市', '新北市', '桃園市', '臺中市', '臺南市', '高雄市',
    '基隆市', '新竹市', '嘉義市',
    '宜蘭縣', '新竹縣', '苗栗縣', '彰化縣', '南投縣', '雲林縣',
    '嘉義縣', '屏東縣', '花蓮縣', '臺東縣', '澎湖縣', '金門縣', '連江縣',
]

# Sector action plans (e.g. 第二期能源部門溫室氣體減量行動方案) name a
# sector, not a ministry; map each sector to its responsible ministry.
# Checked before the plain agency list so 環境部門 resolves via the
# sector rule rather than accidental substring match.
SECTOR_MINISTRIES = {
    '能源部門': '經濟部',
    '製造部門': '經濟部',
    '住商部門': '內政部',
    '運輸部門': '交通部',
    '農業部門': '農業部',
    '環境部門': '環境部',
}

# National-level document markers: these titles belong to no single
# ministry (published at the national level via 環境部/氣候署). Checked
# AFTER counties and sectors so any specific attribution wins first.
NATIONAL_KEYWORDS = [
    '國家', '中華民國', '領域調適', '領域行動方案', '領域氣候變遷調適',
    '階段管制目標', '行動綱領', '溫室氣體推動方案', '調適通訊',
]

# Central agencies responsible for the six GHG-reduction sectors
# (能源/製造:經濟部, 運輸:交通部, 住商:內政部, 農業:農業部, 環境:環境部)
CENTRAL_AGENCIES = [
    '環境部', '經濟部', '交通部', '內政部', '農業部', '國家發展委員會',
    '氣候變遷署', '國土管理署', '行政院',
    # Pre-2023 names that may still appear on older documents
    '環保署', '農委會', '行政院環境保護署',
]

DOC_TYPE_KEYWORDS = [
    ('成果報告', '成果報告'),
    ('執行方案', '執行方案'),
    ('行動方案', '行動方案'),
    ('調適計畫', '調適計畫'),
    ('推動方案', '推動方案'),
]

def normalize_tw(text: str) -> str:
    """Normalize for matching: full-width→half-width, 台→臺."""
    text = unicodedata.normalize('NFKC', text or '')
    return text.replace('台', '臺')


class ClimateDocumentScraper:
    """Scraper anchored on the verified File/Get link pattern."""

    def __init__(self, probe_files: bool = False):
        """
        Args:
            probe_files: if True, send a HEAD request per document to read
                real filename/format/size from headers. Adds ~2s x N to
                runtime because of the polite rate limit.
        """
        self.session = make_session()
        self.probe_files = probe_files
        self.documents: List[Dict] = []
        self.errors: List[str] = []
        self.start_time: Optional[datetime] = None
        self.end_time: Optional[datetime] = None
        self.snapshot_dir = DATA_DIR / 'snapshots'
        self.snapshot_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # HTTP
    # ------------------------------------------------------------------

    def fetch_page(self, url: str, params: Optional[Dict] = None) -> Optional[requests.Response]:
        """GET with polite rate limit, retries, and 429/503 backoff."""
        for attempt in range(SCRAPER_CONFIG['retry_attempts']):
            GLOBAL_RATE_LIMITER.acquire()
            try:
                logger.info(f"Fetching: {url} (attempt {attempt + 1})")
                response = self.session.get(
                    url, params=params, timeout=SCRAPER_CONFIG['request_timeout'])

                if response.status_code in (429, 503):
                    retry_after = response.headers.get('Retry-After')
                    wait = int(retry_after) if (retry_after or '').isdigit() \
                        else SCRAPER_CONFIG['retry_delay'] * (2 ** attempt)
                    logger.warning(f"HTTP {response.status_code}, backing off {wait}s")
                    time.sleep(wait)
                    continue

                # The server sometimes omits charset; requests then falls
                # back to latin-1 and every snapshot turns to mojibake.
                response.encoding = 'utf-8'

                if response.status_code == 403:
                    self.errors.append(
                        f"403 Forbidden for {url} — the site blocks non-browser "
                        f"or non-Taiwan clients; run this scraper from a local "
                        f"machine, not a cloud/proxy environment.")
                    logger.error(self.errors[-1])
                    return None

                response.raise_for_status()
                return response

            except requests.exceptions.RequestException as e:
                logger.warning(f"Error fetching {url}: {e}")
                if attempt < SCRAPER_CONFIG['retry_attempts'] - 1:
                    time.sleep(SCRAPER_CONFIG['retry_delay'] * (2 ** attempt))
                else:
                    self.errors.append(f"Failed to fetch {url}: {e}")
        return None

    def save_snapshot(self, name: str, html: str):
        """Keep raw HTML so parsing failures can be diagnosed offline."""
        path = self.snapshot_dir / name
        path.write_text(html, encoding='utf-8')
        logger.info(f"Saved HTML snapshot: {path}")

    # ------------------------------------------------------------------
    # Extraction
    # ------------------------------------------------------------------

    def extract_documents(self, html: str, base_url: str) -> List[Dict]:
        """Find every File/Get anchor and rebuild metadata from row context."""
        soup = BeautifulSoup(html, 'html.parser')
        docs = []
        seen_urls = set()

        for anchor in soup.find_all('a', href=True):
            href = urljoin(base_url, anchor['href'])
            if FILE_LINK_MARKER not in href:
                continue
            if href in seen_urls:
                continue
            seen_urls.add(href)

            row = anchor.find_parent(['tr', 'li']) or anchor.parent
            row_text = row.get_text(' ', strip=True) if row else ''
            title = self.derive_title(anchor, row) or href

            doc = {
                'title': title,
                'type': self.classify_type(title, row_text),
                'category': '',
                'organization': self.classify_organization(title, row_text),
                'org_type': '',
                'county': '',
                'publish_date': self.find_date(row_text) or self.find_date(title),
                'status': '已公開',
                'download_url': href,
                'file_format': self.format_from_page(anchor, row_text),
                'file_size': self.find_size(row_text),
            }
            doc['org_type'] = '地方政府' if doc['organization'].endswith(('縣', '市')) \
                or doc['organization'].endswith('政府') else '中央部會'
            doc['county'] = doc['organization'].replace('政府', '') \
                if doc['org_type'] == '地方政府' else '中央'
            docs.append(doc)

        logger.info(f"Extracted {len(docs)} File/Get links from page")
        return docs

    @classmethod
    def derive_title(cls, anchor, row) -> str:
        """Prefer meaningful anchor text; fall back to the row's title cell.

        Download anchors are often bare buttons ('下載', 'PDF下載', 'ODF'),
        in which case the document title lives in a sibling cell.
        """
        anchor_text = (anchor.get('title') or anchor.get_text(strip=True) or '').strip()
        if anchor_text and not cls.is_button_text(anchor_text):
            return anchor_text[:120]
        if row is None:
            return anchor_text
        if row.name == 'tr':
            cells = [td.get_text(' ', strip=True) for td in row.find_all(['td', 'th'])]
            cells = [c for c in cells if c and not cls.is_button_text(c)]
            if cells:
                return max(cells, key=len)[:120]
        # li or generic container: row text minus button labels
        text = row.get_text(' ', strip=True)
        for a in row.find_all('a'):
            label = a.get_text(strip=True)
            if label and cls.is_button_text(label):
                text = text.replace(label, '')
        return text.strip()[:120] or anchor_text

    @staticmethod
    def is_button_text(text: str) -> bool:
        t = text.strip()
        return len(t) <= 10 and (
            '下載' in t
            or t.upper() in ('PDF', 'ODF', 'WORD', 'EXCEL', 'ZIP',
                             'DOC', 'DOCX', 'XLS', 'XLSX'))

    @staticmethod
    def classify_type(title: str, row_text: str) -> str:
        text = title + ' ' + row_text
        for keyword, label in DOC_TYPE_KEYWORDS:
            if keyword in text:
                return label
        return '其他'

    @staticmethod
    def classify_organization(title: str, row_text: str) -> str:
        text = normalize_tw(title + ' ' + row_text)
        for county in COUNTIES:
            if county in text:
                return county + '政府'
        for sector, ministry in SECTOR_MINISTRIES.items():
            if sector in text:
                return ministry
        for agency in CENTRAL_AGENCIES:
            if normalize_tw(agency) in text:
                return agency
        # National-level documents (inventories, adaptation-domain
        # reports, framework directives...) name no single ministry.
        for keyword in NATIONAL_KEYWORDS:
            if keyword in text:
                return '國家層級'
        return '未識別'

    @staticmethod
    def find_date(text: str) -> str:
        """Parse 西元 (2023-05-03) and 民國 (112.05.03 / 112年5月3日) dates."""
        if not text:
            return ''
        m = re.search(r'(20\d{2})[./\-年](\d{1,2})[./\-月](\d{1,2})', text)
        if m:
            y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
            return f"{y:04d}-{mo:02d}-{d:02d}"
        m = re.search(r'(?<!\d)(1[01]\d)[./\-年](\d{1,2})[./\-月](\d{1,2})', text)
        if m:  # ROC year 100-119 → 2011-2030
            y, mo, d = int(m.group(1)) + 1911, int(m.group(2)), int(m.group(3))
            return f"{y:04d}-{mo:02d}-{d:02d}"
        m = re.search(r'(?<!\d)(1[01]\d)\s*年(?:度)?', text)
        if m:  # Year only, e.g. 112年度
            return f"{int(m.group(1)) + 1911:04d}"
        return ''

    @staticmethod
    def find_size(text: str) -> str:
        m = re.search(r'(\d+(?:\.\d+)?)\s*(KB|MB|GB)', text or '', re.IGNORECASE)
        return m.group(0) if m else ''

    @staticmethod
    def format_from_page(anchor, row_text: str) -> str:
        """Infer format from link text/labels; URLs carry no extension."""
        text = (anchor.get_text(' ', strip=True) + ' '
                + (anchor.get('title') or '') + ' ' + (row_text or '')).lower()
        for hint, label in [('pdf', 'PDF'), ('.docx', 'Word'), ('.doc', 'Word'),
                            ('.xlsx', 'Excel'), ('.xls', 'Excel'), ('odf', 'ODF'),
                            ('.odt', 'ODF Word'), ('.ods', 'ODF Excel'), ('zip', 'ZIP')]:
            if hint in text:
                return label
        return ''  # unknown until probed

    # ------------------------------------------------------------------
    # File probing (HEAD): real format / size / server filename
    # ------------------------------------------------------------------

    def probe_file(self, doc: Dict):
        """HEAD the download URL to fill format/size from response headers."""
        GLOBAL_RATE_LIMITER.acquire()
        try:
            resp = self.session.head(
                doc['download_url'], timeout=SCRAPER_CONFIG['request_timeout'],
                allow_redirects=True)
            if resp.status_code == 405:  # server rejects HEAD; try ranged GET
                GLOBAL_RATE_LIMITER.acquire()
                resp = self.session.get(
                    doc['download_url'], timeout=SCRAPER_CONFIG['request_timeout'],
                    headers={'Range': 'bytes=0-0'}, stream=True)
                resp.close()
            resp.raise_for_status()

            filename = filename_from_disposition(
                resp.headers.get('Content-Disposition', ''))
            if filename:
                doc['server_filename'] = filename

            probed_format = format_from_headers(resp.headers)
            if probed_format:
                doc['file_format'] = probed_format

            length = resp.headers.get('Content-Length') or \
                (resp.headers.get('Content-Range', '').split('/')[-1]
                 if '/' in resp.headers.get('Content-Range', '') else '')
            if length.isdigit():
                doc['file_size_bytes'] = int(length)
                doc['file_size'] = human_size(int(length))

        except requests.exceptions.RequestException as e:
            logger.warning(f"Probe failed for {doc['download_url']}: {e}")

    # ------------------------------------------------------------------
    # Pagination: follow links the page actually renders
    # ------------------------------------------------------------------

    def discover_page_urls(self, html: str, base_url: str) -> List[str]:
        """Collect pagination URLs present in the page (no blind ?page=N)."""
        soup = BeautifulSoup(html, 'html.parser')
        base_path = urlparse(base_url).path
        urls = []
        for anchor in soup.find_all('a', href=True):
            href = urljoin(base_url, anchor['href'])
            parsed = urlparse(href)
            if parsed.path != base_path:
                continue
            if parse_qs(parsed.query).get('page') or parse_qs(parsed.query).get('P'):
                if href not in urls and href != base_url:
                    urls.append(href)
        if urls:
            logger.info(f"Discovered {len(urls)} pagination URLs")
        return urls

    # ------------------------------------------------------------------
    # Main flow
    # ------------------------------------------------------------------

    def scrape(self) -> List[Dict]:
        self.start_time = datetime.now()
        logger.info("=" * 60)
        logger.info(f"Target: {CLIMATE_PLATFORM_URL}")
        logger.info(f"Expected documents: ~{EXPECTED_DOCUMENT_COUNT}")
        logger.info("=" * 60)

        response = self.fetch_page(CLIMATE_PLATFORM_URL)
        if not response:
            logger.error("Failed to fetch main page — see errors above")
            return []

        self.save_snapshot('page_1.html', response.text)
        self.documents = self.extract_documents(response.text, CLIMATE_PLATFORM_URL)

        # Follow pagination links actually present in the page
        visited = {CLIMATE_PLATFORM_URL}
        queue = self.discover_page_urls(response.text, CLIMATE_PLATFORM_URL)
        page_no = 1
        while queue:
            url = queue.pop(0)
            if url in visited:
                continue
            visited.add(url)
            page_no += 1
            resp = self.fetch_page(url)
            if not resp:
                continue
            self.save_snapshot(f'page_{page_no}.html', resp.text)
            self.documents.extend(self.extract_documents(resp.text, url))
            for new_url in self.discover_page_urls(resp.text, url):
                if new_url not in visited and new_url not in queue:
                    queue.append(new_url)

        self.documents = self.deduplicate(self.documents)
        for idx, doc in enumerate(self.documents, 1):
            doc['id'] = idx

        if self.probe_files and self.documents:
            eta = len(self.documents) * GLOBAL_RATE_LIMITER.min_interval / 60
            logger.info(f"Probing {len(self.documents)} files via HEAD "
                        f"(~{eta:.0f} min at polite rate)...")
            for doc in self.documents:
                self.probe_file(doc)

        self.end_time = datetime.now()
        duration = (self.end_time - self.start_time).total_seconds()
        logger.info("=" * 60)
        logger.info(f"Done in {duration:.1f}s — {len(self.documents)} documents, "
                    f"{len(self.errors)} errors")
        if len(self.documents) != EXPECTED_DOCUMENT_COUNT:
            logger.warning(
                f"Count differs from expected {EXPECTED_DOCUMENT_COUNT}. "
                f"Inspect {self.snapshot_dir}/page_*.html to check whether the "
                f"list is rendered by JavaScript or split across sub-pages.")
        return self.documents

    @staticmethod
    def deduplicate(documents: List[Dict]) -> List[Dict]:
        seen, unique = set(), []
        for doc in documents:
            key = doc.get('download_url', '')
            if key and key not in seen:
                seen.add(key)
                unique.append(doc)
        return unique

    def get_statistics(self) -> Dict:
        stats = {
            'total_documents': len(self.documents),
            'by_org_type': {}, 'by_organization': {}, 'by_county': {},
            'by_type': {}, 'by_format': {}, 'by_date': {},
            'errors_count': len(self.errors),
        }
        for doc in self.documents:
            for field, key in [('by_org_type', 'org_type'),
                               ('by_organization', 'organization'),
                               ('by_county', 'county'), ('by_type', 'type'),
                               ('by_format', 'file_format')]:
                value = doc.get(key) or 'Unknown'
                stats[field][value] = stats[field].get(value, 0) + 1
            date = (doc.get('publish_date') or 'Unknown')[:7]
            stats['by_date'][date] = stats['by_date'].get(date, 0) + 1
        return stats


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--probe-files', action='store_true',
                        help='HEAD each file for real format/size (slow but accurate)')
    args = parser.parse_args()

    scraper = ClimateDocumentScraper(probe_files=args.probe_files)
    documents = scraper.scrape()
    if documents:
        import json
        print(f"\nScraped {len(documents)} documents")
        print(json.dumps(documents[0], indent=2, ensure_ascii=False))
    else:
        print("No documents scraped — check scraper.log and data/snapshots/")
    return documents


if __name__ == '__main__':
    main()
