"""Main scraper module for climate platform documents."""

import logging
import time
import json
from typing import List, Dict, Optional
from datetime import datetime
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import re

from config import CLIMATE_PLATFORM_URL, SCRAPER_CONFIG, EXPECTED_DOCUMENT_COUNT

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(SCRAPER_CONFIG['log_file']),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class ClimateDocumentScraper:
    """Scraper for climate platform documents."""

    def __init__(self):
        self.session = requests.Session()
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                         '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
        self.documents = []
        self.errors = []
        self.start_time = None
        self.end_time = None

    def fetch_page(self, url: str, params: Optional[Dict] = None) -> Optional[requests.Response]:
        """Fetch a page with retry logic."""
        for attempt in range(SCRAPER_CONFIG['retry_attempts']):
            try:
                logger.info(f"Fetching: {url} (attempt {attempt + 1})")
                response = self.session.get(
                    url,
                    headers=self.headers,
                    params=params,
                    timeout=SCRAPER_CONFIG['request_timeout']
                )
                response.raise_for_status()
                logger.debug(f"Successfully fetched {url}")
                return response
            except requests.exceptions.RequestException as e:
                logger.warning(f"Error fetching {url}: {e}")
                if attempt < SCRAPER_CONFIG['retry_attempts'] - 1:
                    wait_time = SCRAPER_CONFIG['retry_delay'] * (2 ** attempt)
                    logger.info(f"Retrying in {wait_time} seconds...")
                    time.sleep(wait_time)
                else:
                    error_msg = f"Failed to fetch {url} after {SCRAPER_CONFIG['retry_attempts']} attempts: {e}"
                    self.errors.append(error_msg)
                    logger.error(error_msg)
                    return None
        return None

    def extract_documents_from_html(self, html: str) -> List[Dict]:
        """Extract document metadata from HTML."""
        documents = []
        try:
            soup = BeautifulSoup(html, 'html.parser')

            # Try multiple selector strategies for robustness
            selectors = [
                'tr[data-doc-id]',  # Custom data attribute
                'table tr',  # Generic table rows
                'div.document-item',  # Common class name
            ]

            rows = []
            for selector in selectors:
                rows = soup.select(selector)
                if rows:
                    logger.info(f"Found {len(rows)} rows using selector: {selector}")
                    break

            if not rows:
                logger.warning("No document rows found in HTML")
                return documents

            for idx, row in enumerate(rows, 1):
                try:
                    doc = self.parse_document_row(row, idx)
                    if doc:
                        documents.append(doc)
                except Exception as e:
                    logger.warning(f"Error parsing row {idx}: {e}")
                    continue

            logger.info(f"Extracted {len(documents)} documents from HTML")
            return documents

        except Exception as e:
            logger.error(f"Error parsing HTML: {e}")
            self.errors.append(f"HTML parsing error: {e}")
            return documents

    def parse_document_row(self, row_element, row_number: int) -> Optional[Dict]:
        """Parse a single document row."""
        try:
            cells = row_element.find_all(['td', 'th'])
            if len(cells) < 4:
                return None

            # Extract text from cells
            cell_texts = [cell.get_text(strip=True) for cell in cells]

            # Find download link
            download_url = ""
            download_link = row_element.find('a')
            if download_link and download_link.get('href'):
                download_url = urljoin(CLIMATE_PLATFORM_URL, download_link['href'])

            # Parse file format and size from download link or last cell
            file_format = self.extract_file_format(download_url)
            file_size = self.extract_file_size(cell_texts[-1] if cell_texts else "")

            # Create document record
            doc = {
                'id': row_number,
                'title': cell_texts[1] if len(cell_texts) > 1 else "",
                'type': cell_texts[2] if len(cell_texts) > 2 else "",
                'category': cell_texts[2] if len(cell_texts) > 2 else "",
                'county': cell_texts[3] if len(cell_texts) > 3 else "",
                'publish_date': self.parse_date(cell_texts[4] if len(cell_texts) > 4 else ""),
                'status': cell_texts[5] if len(cell_texts) > 5 else "已發佈",
                'download_url': download_url,
                'file_format': file_format,
                'file_size': file_size,
            }

            return doc

        except Exception as e:
            logger.debug(f"Error parsing document row: {e}")
            return None

    @staticmethod
    def extract_file_format(url: str) -> str:
        """Extract file format from URL."""
        if not url:
            return "Unknown"

        path = urlparse(url).path.lower()
        if path.endswith('.pdf'):
            return 'PDF'
        elif path.endswith(('.doc', '.docx')):
            return 'Word'
        elif path.endswith(('.xls', '.xlsx')):
            return 'Excel'
        elif path.endswith(('.ppt', '.pptx')):
            return 'PowerPoint'
        elif path.endswith('.zip'):
            return 'ZIP'
        else:
            return 'Other'

    @staticmethod
    def extract_file_size(text: str) -> str:
        """Extract file size from text."""
        match = re.search(r'(\d+(?:\.\d+)?)\s*(KB|MB|GB|B)', text, re.IGNORECASE)
        return match.group(0) if match else ""

    @staticmethod
    def parse_date(date_str: str) -> str:
        """Parse and normalize date string."""
        if not date_str:
            return ""

        # Try common date formats
        formats = ['%Y-%m-%d', '%Y/%m/%d', '%m/%d/%Y', '%d/%m/%Y']
        for fmt in formats:
            try:
                from datetime import datetime
                parsed = datetime.strptime(date_str.strip(), fmt)
                return parsed.strftime('%Y-%m-%d')
            except ValueError:
                continue

        # Return as-is if parsing fails
        return date_str.strip()

    def scrape(self) -> List[Dict]:
        """Main scraping method."""
        self.start_time = datetime.now()
        logger.info("=" * 60)
        logger.info("Starting climate platform document scraper")
        logger.info(f"Target URL: {CLIMATE_PLATFORM_URL}")
        logger.info(f"Expected documents: {EXPECTED_DOCUMENT_COUNT}")
        logger.info("=" * 60)

        try:
            # Fetch main page
            response = self.fetch_page(CLIMATE_PLATFORM_URL)
            if not response:
                logger.error("Failed to fetch main page")
                return []

            # Check if page has pagination or dynamic loading
            self.documents = self.extract_documents_from_html(response.text)

            # If documents found are less than expected, try pagination
            if len(self.documents) < EXPECTED_DOCUMENT_COUNT:
                logger.info(f"Found {len(self.documents)} documents, trying pagination...")
                self.documents.extend(self.scrape_paginated())

            # Deduplicate documents
            self.documents = self.deduplicate_documents(self.documents)

            self.end_time = datetime.now()
            duration = (self.end_time - self.start_time).total_seconds()

            logger.info("=" * 60)
            logger.info(f"Scraping completed in {duration:.2f} seconds")
            logger.info(f"Total documents found: {len(self.documents)}")
            logger.info(f"Expected documents: {EXPECTED_DOCUMENT_COUNT}")
            logger.info(f"Errors encountered: {len(self.errors)}")
            logger.info("=" * 60)

            return self.documents

        except Exception as e:
            logger.error(f"Scraping failed: {e}")
            self.errors.append(f"Scraping error: {e}")
            return []

    def scrape_paginated(self, max_pages: int = 50) -> List[Dict]:
        """Scrape paginated results."""
        documents = []
        for page in range(1, max_pages + 1):
            try:
                time.sleep(SCRAPER_CONFIG['request_delay'])

                # Try common pagination parameters
                params = {'page': page}
                response = self.fetch_page(CLIMATE_PLATFORM_URL, params=params)
                if not response:
                    logger.info(f"Page {page} returned no content, stopping pagination")
                    break

                page_docs = self.extract_documents_from_html(response.text)
                if not page_docs:
                    logger.info(f"No documents in page {page}, stopping pagination")
                    break

                documents.extend(page_docs)
                logger.info(f"Page {page}: Found {len(page_docs)} documents")

                # Stop if we've found enough documents
                if len(self.documents) + len(documents) >= EXPECTED_DOCUMENT_COUNT:
                    break

            except Exception as e:
                logger.warning(f"Error scraping page {page}: {e}")
                continue

        return documents

    def deduplicate_documents(self, documents: List[Dict]) -> List[Dict]:
        """Remove duplicate documents based on title and URL."""
        seen = set()
        unique_docs = []

        for doc in documents:
            key = (doc.get('title', ''), doc.get('download_url', ''))
            if key not in seen and key != ('', ''):
                seen.add(key)
                unique_docs.append(doc)

        if len(unique_docs) < len(documents):
            logger.info(f"Removed {len(documents) - len(unique_docs)} duplicate documents")

        return unique_docs

    def get_statistics(self) -> Dict:
        """Calculate statistics from scraped documents."""
        stats = {
            'total_documents': len(self.documents),
            'by_county': {},
            'by_type': {},
            'by_format': {},
            'by_date': {},
            'errors_count': len(self.errors),
        }

        for doc in self.documents:
            # By county
            county = doc.get('county', 'Unknown')
            stats['by_county'][county] = stats['by_county'].get(county, 0) + 1

            # By type
            doc_type = doc.get('type', 'Unknown')
            stats['by_type'][doc_type] = stats['by_type'].get(doc_type, 0) + 1

            # By format
            file_format = doc.get('file_format', 'Unknown')
            stats['by_format'][file_format] = stats['by_format'].get(file_format, 0) + 1

            # By date
            date = doc.get('publish_date', 'Unknown')[:7]  # YYYY-MM
            stats['by_date'][date] = stats['by_date'].get(date, 0) + 1

        return stats


def main():
    """Run the scraper."""
    scraper = ClimateDocumentScraper()
    documents = scraper.scrape()

    if documents:
        print(f"\nSuccessfully scraped {len(documents)} documents")
        print(f"Sample document: {json.dumps(documents[0], indent=2, ensure_ascii=False)}")
    else:
        print("No documents were scraped")

    return documents


if __name__ == '__main__':
    main()
