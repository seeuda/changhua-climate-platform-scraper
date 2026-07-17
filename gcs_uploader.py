"""Google Cloud Storage uploader for downloaded documents."""

import logging
from pathlib import Path
from typing import Dict, Optional, List
import os

logger = logging.getLogger(__name__)


class GCSUploader:
    """Upload files to Google Cloud Storage."""

    def __init__(self, project_id: str, bucket_name: str, prefix: str = "climate-docs"):
        """
        Initialize GCS uploader.

        Args:
            project_id: GCP project ID
            bucket_name: GCS bucket name
            prefix: GCS object prefix/path
        """
        self.project_id = project_id
        self.bucket_name = bucket_name
        self.prefix = prefix
        self.client = None
        self.bucket = None

        self._initialize_client()

    def _initialize_client(self):
        """Initialize Google Cloud Storage client."""
        try:
            from google.cloud import storage
            self.client = storage.Client(project=self.project_id)
            self.bucket = self.client.bucket(self.bucket_name)

            logger.info(f"GCS client initialized")
            logger.info(f"Project: {self.project_id}")
            logger.info(f"Bucket: {self.bucket_name}")

        except ImportError:
            logger.error("google-cloud-storage not installed. Install with: pip install google-cloud-storage")
            raise

        except Exception as e:
            logger.error(f"Failed to initialize GCS client: {e}")
            raise

    def upload_directory(self, local_dir: Path, remote_prefix: str = None) -> Dict:
        """
        Upload entire directory to GCS.

        Args:
            local_dir: Local directory path
            remote_prefix: Remote GCS prefix (default: self.prefix)

        Returns:
            Upload statistics
        """
        remote_prefix = remote_prefix or self.prefix
        stats = {
            'total': 0,
            'success': 0,
            'failed': 0,
            'total_size': 0,
            'errors': []
        }

        if not local_dir.exists():
            logger.error(f"Directory not found: {local_dir}")
            return stats

        logger.info(f"Starting directory upload: {local_dir}")
        logger.info(f"Remote prefix: {remote_prefix}")

        # Collect all files
        files = list(local_dir.rglob('*'))
        files = [f for f in files if f.is_file()]

        logger.info(f"Found {len(files)} files to upload")

        for idx, filepath in enumerate(files, 1):
            try:
                # Calculate relative path and remote path
                relative_path = filepath.relative_to(local_dir)
                remote_path = f"{remote_prefix}/{relative_path.as_posix()}"

                # Upload file
                file_size = filepath.stat().st_size
                self._upload_file(filepath, remote_path)

                stats['success'] += 1
                stats['total_size'] += file_size

                logger.info(f"[{idx}/{len(files)}] ✓ {relative_path}")

            except Exception as e:
                stats['failed'] += 1
                error_msg = f"{filepath.name}: {str(e)}"
                stats['errors'].append(error_msg)
                logger.error(f"[{idx}/{len(files)}] ✗ {filepath.name}: {e}")

            finally:
                stats['total'] += 1

        return self._generate_upload_report(stats)

    def _upload_file(self, local_path: Path, remote_path: str):
        """Upload single file to GCS."""
        blob = self.bucket.blob(remote_path)

        # Set metadata
        blob.metadata = {
            'original-filename': local_path.name,
            'source': 'climate-platform-scraper'
        }

        # Upload with progress
        logger.debug(f"Uploading: {local_path} -> gs://{self.bucket_name}/{remote_path}")
        blob.upload_from_filename(str(local_path))

        logger.debug(f"Uploaded: {remote_path}")

    def _generate_upload_report(self, stats: Dict) -> Dict:
        """Generate and log upload report."""
        logger.info("=" * 60)
        logger.info("GCS Upload Summary")
        logger.info("=" * 60)
        logger.info(f"Total files: {stats['total']}")
        logger.info(f"✓ Successful: {stats['success']}")
        logger.info(f"✗ Failed: {stats['failed']}")
        logger.info(f"Total size: {self._format_size(stats['total_size'])}")

        if stats['errors']:
            logger.warning(f"\nUpload errors ({len(stats['errors'])}):")
            for error in stats['errors'][:5]:
                logger.warning(f"  - {error}")
            if len(stats['errors']) > 5:
                logger.warning(f"  ... and {len(stats['errors']) - 5} more")

        logger.info("=" * 60)
        return stats

    @staticmethod
    def _format_size(size_bytes: int) -> str:
        """Format bytes to human readable size."""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size_bytes < 1024:
                return f"{size_bytes:.1f} {unit}"
            size_bytes /= 1024
        return f"{size_bytes:.1f} TB"

    def list_uploaded_files(self, prefix: str = None) -> List[str]:
        """List uploaded files in GCS."""
        prefix = prefix or self.prefix
        blobs = self.client.list_blobs(self.bucket_name, prefix=prefix)

        files = []
        for blob in blobs:
            files.append(blob.name)

        logger.info(f"Found {len(files)} files in gs://{self.bucket_name}/{prefix}")
        return files

    def generate_public_urls(self, prefix: str = None) -> List[Dict]:
        """Generate public URLs for uploaded files."""
        prefix = prefix or self.prefix
        blobs = self.client.list_blobs(self.bucket_name, prefix=prefix)

        urls = []
        for blob in blobs:
            public_url = f"https://storage.googleapis.com/{self.bucket_name}/{blob.name}"
            urls.append({
                'name': blob.name,
                'url': public_url,
                'size': blob.size
            })

        return urls


def main():
    """Test GCS uploader."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # Configuration from environment
    project_id = os.getenv('GCP_PROJECT_ID')
    bucket_name = os.getenv('GCS_BUCKET_NAME')

    if not project_id or not bucket_name:
        logger.error("Set GCP_PROJECT_ID and GCS_BUCKET_NAME environment variables")
        return 1

    try:
        # Initialize uploader
        uploader = GCSUploader(project_id, bucket_name)

        # Upload downloads directory
        download_dir = Path('downloads')
        if download_dir.exists():
            stats = uploader.upload_directory(download_dir)
            logger.info(f"Upload complete: {stats['success']}/{stats['total']} successful")
        else:
            logger.warning("downloads/ directory not found")

        return 0

    except Exception as e:
        logger.error(f"Upload failed: {e}")
        return 1


if __name__ == '__main__':
    import sys
    sys.exit(main())
