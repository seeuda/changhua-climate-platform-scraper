#!/usr/bin/env python3
"""Phase 2: Download and upload documents to GCS."""

import logging
import sys
import argparse
import json
import os
from pathlib import Path

from download_manager import DownloadManager
from gcs_uploader import GCSUploader

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('download.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


def load_documents(metadata_file: Path = None) -> list:
    """Load documents from metadata JSON."""
    metadata_file = metadata_file or Path('output/climate_docs_metadata.json')

    if not metadata_file.exists():
        logger.error(f"Metadata file not found: {metadata_file}")
        logger.error("Run main.py first to generate metadata")
        return []

    try:
        with open(metadata_file, encoding='utf-8-sig') as f:
            data = json.load(f)
            documents = data.get('documents', [])
            logger.info(f"Loaded {len(documents)} documents from metadata")
            return documents
    except Exception as e:
        logger.error(f"Failed to load metadata: {e}")
        return []


def download_phase(documents: list, max_workers: int = 3) -> bool:
    """Phase 1: Download documents."""
    if not documents:
        logger.error("No documents to download")
        return False

    try:
        manager = DownloadManager(download_dir=Path('downloads'))
        stats = manager.download_documents(documents, max_workers=max_workers)

        # Show directory structure
        structure = manager.get_directory_structure()
        logger.info("\n📁 Downloaded files by county:")
        for county, info in sorted(structure.items()):
            logger.info(f"   {county}: {info['count']} files ({DownloadManager.format_size(info['size'])})")

        # Save download log
        log_data = {
            'stats': stats,
            'structure': structure,
            'documents_count': len(documents)
        }
        with open('downloads/download_log.json', 'w', encoding='utf-8') as f:
            json.dump(log_data, f, ensure_ascii=False, indent=2)

        success_rate = (stats['success'] / stats['total'] * 100) if stats['total'] > 0 else 0
        logger.info(f"\n✓ Download phase complete: {success_rate:.1f}% success rate")
        return True

    except Exception as e:
        logger.error(f"Download phase failed: {e}")
        return False


def upload_phase(bucket_name: str = None, project_id: str = None, dry_run: bool = False) -> bool:
    """Phase 2: Upload to GCS."""
    # Get credentials from environment
    project_id = project_id or os.getenv('GCP_PROJECT_ID')
    bucket_name = bucket_name or os.getenv('GCS_BUCKET_NAME')

    if not project_id or not bucket_name:
        logger.error("\n❌ GCS credentials missing!")
        logger.error("Set environment variables:")
        logger.error("  export GCP_PROJECT_ID='your-project-id'")
        logger.error("  export GCS_BUCKET_NAME='your-bucket-name'")
        logger.error("\nOr use command: python phase2_download.py --upload --project-id xxx --bucket xxx")
        return False

    download_dir = Path('downloads')
    if not download_dir.exists() or not list(download_dir.glob('*')):
        logger.error(f"No downloaded files found in {download_dir}")
        return False

    if dry_run:
        logger.info("🔍 DRY RUN: Showing what would be uploaded")
        logger.info(f"   Project: {project_id}")
        logger.info(f"   Bucket: {bucket_name}")
        logger.info(f"   Source: {download_dir.absolute()}")
        logger.info(f"   Prefix: climate-docs")

        # Count files
        files = list(download_dir.rglob('*'))
        files = [f for f in files if f.is_file()]
        logger.info(f"   Files: {len(files)}")
        return True

    try:
        logger.info("\n📤 Starting GCS upload...")
        uploader = GCSUploader(project_id, bucket_name)
        stats = uploader.upload_directory(download_dir)

        # Generate public URLs
        logger.info("\n🔗 Generating public URLs...")
        urls = uploader.generate_public_urls()

        # Save URLs to file
        with open('downloads/public_urls.json', 'w', encoding='utf-8') as f:
            json.dump(urls, f, ensure_ascii=False, indent=2)

        logger.info(f"✓ Saved {len(urls)} public URLs to downloads/public_urls.json")
        logger.info(f"✓ Upload complete: {stats['success']}/{stats['total']} successful")

        return stats['failed'] == 0

    except Exception as e:
        logger.error(f"Upload phase failed: {e}")
        return False


def main():
    """Main entry point for Phase 2."""
    parser = argparse.ArgumentParser(
        description='Phase 2: Download and upload climate platform documents'
    )
    parser.add_argument(
        '--download',
        action='store_true',
        default=True,
        help='Download documents (default: True)'
    )
    parser.add_argument(
        '--upload',
        action='store_true',
        help='Upload to GCS after download'
    )
    parser.add_argument(
        '--max-workers',
        type=int,
        default=3,
        help='Max concurrent downloads (default: 3)'
    )
    parser.add_argument(
        '--metadata',
        type=Path,
        default=Path('output/climate_docs_metadata.json'),
        help='Metadata JSON file'
    )
    parser.add_argument(
        '--project-id',
        help='GCP project ID (or set GCP_PROJECT_ID env var)'
    )
    parser.add_argument(
        '--bucket',
        help='GCS bucket name (or set GCS_BUCKET_NAME env var)'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be uploaded without uploading'
    )

    args = parser.parse_args()

    logger.info("=" * 70)
    logger.info("Phase 2: Climate Platform Document Download & Upload")
    logger.info("=" * 70)

    # Load documents
    documents = load_documents(args.metadata)
    if not documents:
        return 1

    # Download phase
    if args.download:
        if not download_phase(documents, max_workers=args.max_workers):
            logger.error("Download phase failed")
            return 1

    # Upload phase
    if args.upload:
        if not upload_phase(
            project_id=args.project_id,
            bucket_name=args.bucket,
            dry_run=args.dry_run
        ):
            if not args.dry_run:
                logger.error("Upload phase failed")
                return 1

    logger.info("=" * 70)
    logger.info("✓ Phase 2 complete!")
    logger.info("=" * 70)
    return 0


if __name__ == '__main__':
    sys.exit(main())
