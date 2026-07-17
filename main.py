#!/usr/bin/env python3
"""Main entry point for climate platform document scraper."""

import logging
import sys
import argparse
from datetime import datetime

from scraper import ClimateDocumentScraper
from output_formatter import DocumentOutputFormatter
from report_generator import ReportGenerator

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def main():
    """Main scraper execution."""
    parser = argparse.ArgumentParser(
        description='Scrape climate platform documents metadata'
    )
    parser.add_argument(
        '--format',
        choices=['csv', 'json', 'all', 'excel'],
        default='all',
        help='Output format (default: all)'
    )
    parser.add_argument(
        '--no-report',
        action='store_true',
        help='Skip generating report'
    )
    parser.add_argument(
        '--output-dir',
        help='Custom output directory'
    )
    parser.add_argument(
        '--probe-files',
        action='store_true',
        help='HEAD each download URL to get real filename/format/size from '
             'headers (real URLs have no extension); adds ~2s per document'
    )

    args = parser.parse_args()

    logger.info("Starting climate platform document scraper")
    logger.info("=" * 70)

    try:
        # Initialize and run scraper
        scraper = ClimateDocumentScraper(probe_files=args.probe_files)
        documents = scraper.scrape()

        if not documents:
            logger.error("No documents were scraped")
            return 1

        # Calculate duration
        duration = (scraper.end_time - scraper.start_time).total_seconds() if scraper.end_time else 0

        # Save outputs
        logger.info("\nSaving outputs...")
        if args.format in ['csv', 'all']:
            DocumentOutputFormatter.save_csv(documents)
        if args.format in ['json', 'all']:
            DocumentOutputFormatter.save_json(documents)
        if args.format in ['excel', 'all']:
            DocumentOutputFormatter.save_excel(documents)

        # Generate report
        if not args.no_report:
            logger.info("Generating report...")
            stats = scraper.get_statistics()
            report_gen = ReportGenerator(documents, stats, scraper.errors, duration)
            report_gen.generate_markdown_report()

        logger.info("=" * 70)
        logger.info("✓ Scraping completed successfully")
        logger.info(f"  - Documents found: {len(documents)}")
        logger.info(f"  - Duration: {duration:.2f} seconds")
        logger.info(f"  - Errors: {len(scraper.errors)}")

        return 0

    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        return 1


if __name__ == '__main__':
    sys.exit(main())
