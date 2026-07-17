"""Download manager for climate platform documents."""

import logging
import os
import time
from pathlib import Path
from typing import List, Dict, Optional, Tuple
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlparse, unquote

from config import SCRAPER_CONFIG, EXPECTED_DOCUMENT_COUNT

logger = logging.getLogger(__name__)


class DownloadManager:
    """Manage bulk downloads of documents with progress tracking."""

    def __init__(self, download_dir: Path = None):
        self.download_dir = download_dir or Path("downloads")
        self.download_dir.mkdir(exist_ok=True)

        self.session = requests.Session()
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                         '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }

        self.stats = {
            'total': 0,
            'success': 0,
            'failed': 0,
            'skipped': 0,
            'total_size': 0,
        }
        self.failed_downloads = []

    def download_documents(self, documents: List[Dict], max_workers: int = None) -> Dict:
        """Download all documents with concurrent workers."""
        max_workers = max_workers or SCRAPER_CONFIG.get('max_workers', 3)
        self.stats['total'] = len(documents)

        logger.info("=" * 60)
        logger.info(f"Starting document downloads ({len(documents)} files)")
        logger.info(f"Download directory: {self.download_dir.absolute()}")
        logger.info(f"Max concurrent downloads: {max_workers}")
        logger.info("=" * 60)

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {}
            for doc in documents:
                # Create county directory
                county = doc.get('county', 'Unknown')
                county_dir = self.download_dir / county
                county_dir.mkdir(exist_ok=True)

                future = executor.submit(self.download_document, doc, county_dir)
                futures[future] = doc

            # Process completed downloads
            for idx, future in enumerate(as_completed(futures), 1):
                doc = futures[future]
                try:
                    result = future.result()
                    if result:
                        logger.info(f"[{idx}/{len(documents)}] ✓ {result['filename']}")
                    else:
                        logger.warning(f"[{idx}/{len(documents)}] ⊘ {doc.get('title', 'Unknown')}")
                except Exception as e:
                    logger.error(f"[{idx}/{len(documents)}] ✗ {doc.get('title', 'Unknown')}: {e}")

        return self.generate_report()

    def download_document(self, doc: Dict, county_dir: Path) -> Optional[Dict]:
        """Download a single document."""
        url = doc.get('download_url', '')
        if not url:
            self.stats['skipped'] += 1
            return None

        try:
            # Generate filename
            filename = self.generate_filename(doc, county_dir)
            filepath = county_dir / filename

            # Skip if already downloaded
            if filepath.exists():
                file_size = filepath.stat().st_size
                self.stats['skipped'] += 1
                logger.debug(f"File exists, skipping: {filename}")
                return None

            # Download file
            response = self.session.get(
                url,
                headers=self.headers,
                timeout=SCRAPER_CONFIG.get('request_timeout', 10),
                stream=True
            )
            response.raise_for_status()

            # Save file
            total_size = 0
            with open(filepath, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        total_size += len(chunk)

            self.stats['success'] += 1
            self.stats['total_size'] += total_size

            # Respect request delay
            time.sleep(SCRAPER_CONFIG.get('request_delay', 2))

            return {
                'filename': filename,
                'size': total_size,
                'title': doc.get('title', ''),
                'url': url
            }

        except requests.exceptions.RequestException as e:
            self.stats['failed'] += 1
            error_msg = f"{doc.get('title', 'Unknown')}: {str(e)}"
            self.failed_downloads.append(error_msg)
            logger.error(f"Failed to download {doc.get('title', 'Unknown')}: {e}")
            return None

        except Exception as e:
            self.stats['failed'] += 1
            error_msg = f"{doc.get('title', 'Unknown')}: {str(e)}"
            self.failed_downloads.append(error_msg)
            logger.error(f"Error downloading {doc.get('title', 'Unknown')}: {e}")
            return None

    def generate_filename(self, doc: Dict, county_dir: Path) -> str:
        """Generate safe filename for document."""
        doc_id = str(doc.get('id', '0')).zfill(5)
        title = doc.get('title', 'document')[:50]  # Limit title length

        # Clean title for filename
        for char in ['/', '\\', ':', '*', '?', '"', '<', '>', '|']:
            title = title.replace(char, '_')

        # Get file extension from URL or use default
        url = doc.get('download_url', '')
        ext = self.get_file_extension(url)

        filename = f"{doc_id}_{title}{ext}"
        return filename

    @staticmethod
    def get_file_extension(url: str) -> str:
        """Extract file extension from URL."""
        parsed = urlparse(url)
        path = unquote(parsed.path).lower()

        # Extract extension from path
        if '.' in path:
            ext = path.split('.')[-1]
            if len(ext) <= 5:  # Valid extension
                return f".{ext}"

        return ".bin"  # Default binary extension

    def generate_report(self) -> Dict:
        """Generate download report."""
        logger.info("=" * 60)
        logger.info("Download Summary")
        logger.info("=" * 60)
        logger.info(f"Total documents: {self.stats['total']}")
        logger.info(f"✓ Successful: {self.stats['success']}")
        logger.info(f"✗ Failed: {self.stats['failed']}")
        logger.info(f"⊘ Skipped: {self.stats['skipped']}")
        logger.info(f"Total size: {self.format_size(self.stats['total_size'])}")
        logger.info("=" * 60)

        if self.failed_downloads:
            logger.warning(f"\nFailed downloads ({len(self.failed_downloads)}):")
            for error in self.failed_downloads[:10]:
                logger.warning(f"  - {error}")
            if len(self.failed_downloads) > 10:
                logger.warning(f"  ... and {len(self.failed_downloads) - 10} more")

        return self.stats

    @staticmethod
    def format_size(size_bytes: int) -> str:
        """Format bytes to human readable size."""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size_bytes < 1024:
                return f"{size_bytes:.1f} {unit}"
            size_bytes /= 1024
        return f"{size_bytes:.1f} TB"

    def get_directory_structure(self) -> Dict:
        """Get summary of downloaded files by county."""
        structure = {}
        for county_dir in self.download_dir.iterdir():
            if county_dir.is_dir():
                files = list(county_dir.glob('*'))
                structure[county_dir.name] = {
                    'count': len(files),
                    'size': sum(f.stat().st_size for f in files if f.is_file())
                }
        return structure


def main():
    """Test download manager."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # Load documents from JSON
    import json
    try:
        with open('output/climate_docs_metadata.json', encoding='utf-8-sig') as f:
            data = json.load(f)
            documents = data.get('documents', [])[:5]  # Test with first 5
    except FileNotFoundError:
        logger.error("Documents file not found. Run scraper first.")
        return 1

    if not documents:
        logger.error("No documents to download")
        return 1

    # Download documents
    manager = DownloadManager()
    stats = manager.download_documents(documents, max_workers=1)

    # Show directory structure
    structure = manager.get_directory_structure()
    logger.info("\nDirectory structure:")
    for county, info in sorted(structure.items()):
        logger.info(f"  {county}: {info['count']} files ({manager.format_size(info['size'])})")

    return 0


if __name__ == '__main__':
    import sys
    sys.exit(main())
