#!/usr/bin/env python3
"""Phase 2: download every document once, then build classification views.

Flow:
  1. Download ALL documents in the metadata (no name-based filtering)
     into downloads/archive/ — flat, filenames taken from the server's
     Content-Disposition header.
  2. Build classification views (by_org_type/, by_county/, ...) as
     hardlinks into the archive. Re-classifying never re-downloads;
     run organize.py anytime to add more views.
  3. Optionally upload the archive to GCS.
"""

import argparse
import json
import logging
import os
import sys
from pathlib import Path

from download_manager import DownloadManager, ORGANIZE_METHODS
from organize import build_view

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('download.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

ARCHIVE_DIR = Path('downloads/archive')
BASE_DIR = Path('downloads')


def load_documents(metadata_file: Path) -> list:
    if not metadata_file.exists():
        logger.error(f"Metadata file not found: {metadata_file}")
        logger.error("Run main.py first (on a machine that can reach "
                     "cca.gov.tw) to generate metadata")
        return []
    try:
        with open(metadata_file, encoding='utf-8') as f:
            documents = json.load(f).get('documents', [])
        logger.info(f"Loaded {len(documents)} documents from metadata")
        return documents
    except Exception as e:
        logger.error(f"Failed to load metadata: {e}")
        return []


def download_phase(documents: list, max_workers: int) -> bool:
    """Download everything into the flat archive."""
    manager = DownloadManager(download_dir=ARCHIVE_DIR, organize_by='flat')
    stats = manager.download_documents(documents, max_workers=max_workers)

    log_data = {'stats': stats, 'documents_count': len(documents)}
    BASE_DIR.mkdir(exist_ok=True)
    with open(BASE_DIR / 'download_log.json', 'w', encoding='utf-8') as f:
        json.dump(log_data, f, ensure_ascii=False, indent=2)

    done = stats['success'] + stats['skipped']
    logger.info(f"Archive now covers {done}/{stats['total']} documents "
                f"({stats['failed']} failed — rerun to retry those)")
    return stats['failed'] == 0 or stats['success'] > 0


def organize_phase(documents: list, methods: list) -> None:
    for method in methods:
        build_view(documents, ARCHIVE_DIR, BASE_DIR, method)


def upload_phase(bucket_name: str, project_id: str, dry_run: bool) -> bool:
    """Upload the archive (views are local hardlinks; uploading them too
    would duplicate every object in GCS)."""
    project_id = project_id or os.getenv('GCP_PROJECT_ID')
    bucket_name = bucket_name or os.getenv('GCS_BUCKET_NAME')

    if not project_id or not bucket_name:
        logger.error("Set GCP_PROJECT_ID and GCS_BUCKET_NAME (env or flags)")
        return False
    if not ARCHIVE_DIR.is_dir() or not any(ARCHIVE_DIR.iterdir()):
        logger.error(f"No files in {ARCHIVE_DIR}")
        return False

    if dry_run:
        files = [f for f in ARCHIVE_DIR.rglob('*') if f.is_file()]
        logger.info(f"DRY RUN: would upload {len(files)} files from "
                    f"{ARCHIVE_DIR} to gs://{bucket_name}/climate-docs/")
        return True

    from gcs_uploader import GCSUploader
    uploader = GCSUploader(project_id, bucket_name)
    stats = uploader.upload_directory(ARCHIVE_DIR)

    urls = uploader.generate_public_urls()
    with open(BASE_DIR / 'public_urls.json', 'w', encoding='utf-8') as f:
        json.dump(urls, f, ensure_ascii=False, indent=2)
    logger.info(f"Upload complete: {stats['success']}/{stats['total']}")
    return stats['failed'] == 0


def main():
    parser = argparse.ArgumentParser(
        description='Download all documents into a flat archive, then '
                    'build classification views')
    parser.add_argument('--metadata', type=Path,
                        default=Path('output/climate_docs_metadata.json'))
    parser.add_argument('--max-workers', type=int, default=3,
                        help='concurrent downloads (aggregate request rate '
                             'stays >=2s regardless)')
    parser.add_argument('--organize-by', action='append',
                        choices=ORGANIZE_METHODS + ['all', 'none'],
                        help='view(s) to build after download; repeatable '
                             '(default: org_type). "none" skips; more views '
                             'can be added later with organize.py')
    parser.add_argument('--skip-download', action='store_true',
                        help='only (re)build views from the existing archive')
    parser.add_argument('--upload', action='store_true',
                        help='upload the archive to GCS afterwards')
    parser.add_argument('--project-id', help='GCP project (or env)')
    parser.add_argument('--bucket', help='GCS bucket (or env)')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()

    choices = args.organize_by or ['org_type']
    if 'none' in choices:
        methods = []
    elif 'all' in choices:
        methods = ORGANIZE_METHODS
    else:
        methods = list(dict.fromkeys(choices))

    documents = load_documents(args.metadata)
    if not documents:
        return 1

    if not args.skip_download:
        if not download_phase(documents, args.max_workers):
            logger.error("Download phase produced nothing — aborting")
            return 1

    if methods:
        organize_phase(documents, methods)

    if args.upload:
        if not upload_phase(args.bucket, args.project_id, args.dry_run):
            return 1

    logger.info("Phase 2 complete")
    return 0


if __name__ == '__main__':
    sys.exit(main())
