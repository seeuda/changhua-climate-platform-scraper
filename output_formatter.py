"""Output formatting utilities for document metadata."""

import csv
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List

from config import CLIMATE_PLATFORM_URL, OUTPUT_CONFIG, DOCUMENT_FIELDS

logger = logging.getLogger(__name__)


class DocumentOutputFormatter:
    """Format and save document metadata to various formats."""

    @staticmethod
    def save_csv(documents: List[Dict], output_file: Path = None) -> Path:
        """Save documents to CSV with UTF-8 BOM so Excel opens it correctly."""
        output_file = output_file or OUTPUT_CONFIG['csv_file']

        with open(output_file, 'w', encoding=OUTPUT_CONFIG['csv_encoding'],
                  newline='') as f:
            if not documents:
                logger.warning("No documents to write to CSV")
                return output_file

            fieldnames = list(DOCUMENT_FIELDS.keys())
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for doc in documents:
                writer.writerow({field: doc.get(field, '') for field in fieldnames})

        logger.info(f"Saved {len(documents)} documents to {output_file}")
        return output_file

    @staticmethod
    def save_json(documents: List[Dict], output_file: Path = None,
                  is_demo: bool = False) -> Path:
        """Save documents to JSON (plain UTF-8 — a BOM breaks json.load)."""
        output_file = output_file or OUTPUT_CONFIG['json_file']

        output_data = {
            'metadata': {
                'total_documents': len(documents),
                'scrape_timestamp': datetime.now().isoformat(),
                'source_url': CLIMATE_PLATFORM_URL,
                'is_demo_data': is_demo,
            },
            'documents': documents,
        }

        with open(output_file, 'w', encoding=OUTPUT_CONFIG['json_encoding']) as f:
            json.dump(output_data, f, ensure_ascii=False, indent=2)

        logger.info(f"Saved {len(documents)} documents to {output_file}")
        return output_file

    @staticmethod
    def save_excel(documents: List[Dict], output_file: Path = None) -> Path:
        """Save documents to Excel if pandas is available."""
        output_file = output_file or \
            Path(OUTPUT_CONFIG['csv_file']).parent / "climate_docs_metadata.xlsx"

        try:
            import pandas as pd
        except ImportError:
            logger.warning("pandas not installed, skipping Excel export")
            return None

        df = pd.DataFrame(documents)
        df.to_excel(output_file, index=False, sheet_name='Documents')
        logger.info(f"Saved {len(documents)} documents to {output_file}")
        return output_file
