#!/usr/bin/env python3
"""Build classification views from the flat download archive.

Workflow: download EVERYTHING once into downloads/archive/ (flat), then
build any number of classification views afterwards — no re-download.
Views use hardlinks into the archive, so they cost no extra disk space
and can coexist (falls back to copying if the filesystem refuses links).

Every archived file is included in every view. Documents whose
organization could not be identified go under 未識別/ — nothing is
filtered out by preset name lists.

Usage:
    python organize.py --by org_type
    python organize.py --by org_type --by date
    python organize.py --all
"""

import argparse
import json
import logging
import os
import shutil
import sys
from pathlib import Path
from typing import Dict, List

from download_manager import ORGANIZE_METHODS, route_subpath

logging.basicConfig(level=logging.INFO, format='%(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

DEFAULT_ARCHIVE = Path('downloads/archive')
DEFAULT_BASE = Path('downloads')
DEFAULT_METADATA = Path('output/climate_docs_metadata.json')


def load_documents(metadata_file: Path) -> List[Dict]:
    with open(metadata_file, encoding='utf-8') as f:
        return json.load(f).get('documents', [])


def build_view(documents: List[Dict], archive_dir: Path, base_dir: Path,
               method: str) -> Dict:
    """Create base_dir/by_<method>/ with hardlinks into archive_dir."""
    view_dir = base_dir / f'by_{method}'
    stats = {'linked': 0, 'copied': 0, 'skipped': 0, 'missing': 0}

    for doc in documents:
        doc_id = str(doc.get('id', '0')).zfill(5)
        matches = sorted(archive_dir.glob(f'{doc_id}_*'))
        if not matches:
            stats['missing'] += 1
            continue
        src = matches[0]

        dest_dir = view_dir / route_subpath(doc, method)
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / src.name
        if dest.exists():
            stats['skipped'] += 1
            continue
        try:
            os.link(src, dest)
            stats['linked'] += 1
        except OSError:  # cross-device or FS without hardlink support
            shutil.copy2(src, dest)
            stats['copied'] += 1

    logger.info(f"View by_{method}: {stats['linked']} linked, "
                f"{stats['copied']} copied, {stats['skipped']} existing, "
                f"{stats['missing']} missing from archive")
    if stats['missing']:
        logger.warning(f"by_{method}: {stats['missing']} documents have no "
                       f"archived file — run phase2_download.py to fetch them")
    return stats


def main():
    parser = argparse.ArgumentParser(
        description='Build classification views from the flat archive '
                    '(no re-download)')
    parser.add_argument('--by', action='append', choices=ORGANIZE_METHODS,
                        help='classification method; repeatable')
    parser.add_argument('--all', action='store_true',
                        help='build all classification views')
    parser.add_argument('--archive', type=Path, default=DEFAULT_ARCHIVE)
    parser.add_argument('--base', type=Path, default=DEFAULT_BASE,
                        help='directory to create by_<method>/ views under')
    parser.add_argument('--metadata', type=Path, default=DEFAULT_METADATA)
    args = parser.parse_args()

    methods = ORGANIZE_METHODS if args.all else (args.by or ['org_type'])

    if not args.archive.is_dir() or not any(args.archive.iterdir()):
        logger.error(f"Archive {args.archive} is empty — run "
                     f"phase2_download.py first")
        return 1
    if not args.metadata.exists():
        logger.error(f"Metadata not found: {args.metadata}")
        return 1

    documents = load_documents(args.metadata)
    logger.info(f"{len(documents)} documents in metadata; building views: "
                f"{', '.join(methods)}")
    for method in methods:
        build_view(documents, args.archive, args.base, method)
    return 0


if __name__ == '__main__':
    sys.exit(main())
