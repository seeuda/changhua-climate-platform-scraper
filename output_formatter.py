"""Output formatting utilities for document metadata."""

import csv
import json
import logging
from typing import List, Dict
from pathlib import Path

from config import OUTPUT_CONFIG, DOCUMENT_FIELDS

logger = logging.getLogger(__name__)


class DocumentOutputFormatter:
    """Format and save document metadata to various formats."""

    @staticmethod
    def save_csv(documents: List[Dict], output_file: Path = None) -> Path:
        """Save documents to CSV format with UTF-8 BOM for Excel."""
        output_file = output_file or OUTPUT_CONFIG['csv_file']

        try:
            with open(output_file, 'w', encoding=OUTPUT_CONFIG['encoding'], newline='') as f:
                if not documents:
                    logger.warning("No documents to write to CSV")
                    return output_file

                fieldnames = list(DOCUMENT_FIELDS.keys())
                writer = csv.DictWriter(f, fieldnames=fieldnames)

                writer.writeheader()
                for doc in documents:
                    # Ensure all fields exist
                    row = {field: doc.get(field, '') for field in fieldnames}
                    writer.writerow(row)

            logger.info(f"Successfully saved {len(documents)} documents to {output_file}")
            return output_file

        except Exception as e:
            logger.error(f"Error saving CSV: {e}")
            raise

    @staticmethod
    def save_json(documents: List[Dict], output_file: Path = None) -> Path:
        """Save documents to JSON format."""
        output_file = output_file or OUTPUT_CONFIG['json_file']

        try:
            output_data = {
                'metadata': {
                    'total_documents': len(documents),
                    'scrape_timestamp': __import__('datetime').datetime.now().isoformat(),
                    'source_url': 'https://www.cca.gov.tw/information-service/info/2095.html',
                },
                'documents': documents,
            }

            with open(output_file, 'w', encoding=OUTPUT_CONFIG['encoding']) as f:
                json.dump(output_data, f, ensure_ascii=False, indent=2)

            logger.info(f"Successfully saved {len(documents)} documents to {output_file}")
            return output_file

        except Exception as e:
            logger.error(f"Error saving JSON: {e}")
            raise

    @staticmethod
    def save_excel(documents: List[Dict], output_file: Path = None) -> Path:
        """Save documents to Excel format if pandas available."""
        output_file = output_file or Path(OUTPUT_CONFIG['csv_file']).parent / "climate_docs_metadata.xlsx"

        try:
            import pandas as pd

            df = pd.DataFrame(documents)
            df.to_excel(output_file, index=False, sheet_name='Documents')

            logger.info(f"Successfully saved {len(documents)} documents to {output_file}")
            return output_file

        except ImportError:
            logger.warning("pandas not installed, skipping Excel export")
            return None
        except Exception as e:
            logger.error(f"Error saving Excel: {e}")
            raise
