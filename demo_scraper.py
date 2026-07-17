#!/usr/bin/env python3
"""Demo scraper with sample data for testing and demonstration."""

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict

from output_formatter import DocumentOutputFormatter
from report_generator import ReportGenerator
from config import EXPECTED_DOCUMENT_COUNT

logger = logging.getLogger(__name__)


class DemoScraper:
    """Generate sample data for demonstration purposes."""

    # Sample counties (22 counties and cities in Taiwan)
    COUNTIES = [
        # 6 direct-controlled cities
        '臺北市', '新北市', '桃園市', '臺中市', '臺南市', '高雄市',
        # 3 special cities
        '基隆市', '新竹市', '嘉義市',
        # 13 counties
        '宜蘭縣', '新竹縣', '苗栗縣', '彰化縣', '南投縣', '雲林縣',
        '嘉義縣', '屏東縣', '花蓮縣', '臺東縣', '澎湖縣', '金門縣', '連江縣'
    ]

    # Sample document types
    DOC_TYPES = ['行動方案', '執行方案', '成果報告']

    # Sample categories (政策領域)
    CATEGORIES = ['能源', '運輸', '住宅建築', '產業', '農業', '水資源', '廢棄物', '其他']

    # Sample organizations (中央部會 + 地方政府)
    ORGANIZATIONS = [
        # 中央部會 (12)
        '環保署', '經濟部', '交通部', '內政部', '農委會', '科技部',
        '水利署', '林務局', '文化部', '衛福部', '勞動部', '國防部',
        # 地方政府 (22)
        '臺北市政府', '新北市政府', '基隆市政府', '桃園市政府', '新竹市政府', '新竹縣政府',
        '苗栗縣政府', '臺中市政府', '彰化縣政府', '南投縣政府', '雲林縣政府', '嘉義市政府',
        '嘉義縣政府', '臺南市政府', '高雄市政府', '屏東縣政府', '宜蘭縣政府', '花蓮縣政府',
        '臺東縣政府', '澎湖縣政府', '金門縣政府', '連江縣政府'
    ]

    # Sample file formats
    FILE_FORMATS = ['PDF', 'Word', 'Excel', 'PowerPoint', 'ZIP']

    SAMPLE_TITLES = [
        '淨零排放路徑規劃',
        '再生能源推廣計畫',
        '低碳運輸方案',
        '建築能效提升計畫',
        '廢棄物減量方案',
        '節水推廣計畫',
        '電動公車導入計畫',
        '太陽光電推廣',
        '風力發電計畫',
        '綠色建築認證推廣',
    ]

    @staticmethod
    def generate_sample_data(count: int = None) -> List[Dict]:
        """Generate sample document data with central and local organizations."""
        if count is None:
            count = EXPECTED_DOCUMENT_COUNT

        documents = []
        base_date = datetime(2020, 1, 1)

        for i in range(1, count + 1):
            # Distribute across organizations (central + local)
            org = DemoScraper.ORGANIZATIONS[(i - 1) % len(DemoScraper.ORGANIZATIONS)]

            # Distribute across document types
            doc_type = DemoScraper.DOC_TYPES[(i - 1) % len(DemoScraper.DOC_TYPES)]

            # Distribute across categories
            category = DemoScraper.CATEGORIES[(i - 1) % len(DemoScraper.CATEGORIES)]

            # Determine county from organization
            if '政府' in org:  # 地方政府
                county = org.replace('政府', '')
                org_type = '地方政府'
            else:  # 中央部會
                county = '中央'
                org_type = '中央部會'

            # Generate publish date (spread over time)
            days_offset = (i - 1) * 4  # Roughly one doc every 4 days
            publish_date = base_date + timedelta(days=days_offset)

            # Select file format and generate fake URL
            file_format = DemoScraper.FILE_FORMATS[(i - 1) % len(DemoScraper.FILE_FORMATS)]
            file_ext = {
                'PDF': 'pdf',
                'Word': 'docx',
                'Excel': 'xlsx',
                'PowerPoint': 'pptx',
                'ZIP': 'zip'
            }[file_format]

            # Generate title
            title_base = DemoScraper.SAMPLE_TITLES[(i - 1) % len(DemoScraper.SAMPLE_TITLES)]
            title = f"{org}{title_base}_第{i}號"

            doc = {
                'id': i,
                'title': title,
                'type': doc_type,
                'category': category,
                'organization': org,  # 提交單位
                'org_type': org_type,  # 中央/地方
                'county': county,
                'publish_date': publish_date.strftime('%Y-%m-%d'),
                'status': '已發佈',
                'download_url': f'https://www.cca.gov.tw/documents/{i:05d}.{file_ext}',
                'file_format': file_format,
                'file_size': f'{(100 + i % 500) / 100:.1f} MB',
            }

            documents.append(doc)

        return documents

    @staticmethod
    def generate_statistics(documents: List[Dict]) -> Dict:
        """Generate statistics from sample data."""
        stats = {
            'total_documents': len(documents),
            'by_county': {},
            'by_type': {},
            'by_format': {},
            'by_date': {},
        }

        for doc in documents:
            # By county
            county = doc.get('county', 'Unknown')
            stats['by_county'][county] = stats['by_county'].get(county, 0) + 1

            # By type
            doc_type = doc.get('type', 'Unknown')
            stats['by_type'][doc_type] = stats['by_type'].get(doc_type, 0) + 1

            # By format
            file_format = doc.get('file_format', 'Unknown')
            stats['by_format'][file_format] = stats['by_format'].get(file_format, 0) + 1

            # By date (month)
            date = doc.get('publish_date', 'Unknown')[:7]
            stats['by_date'][date] = stats['by_date'].get(date, 0) + 1

        return stats


def main():
    """Generate sample data and save to files."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )

    print("\n" + "=" * 70)
    print("Climate Platform Scraper - Demo Mode")
    print("=" * 70 + "\n")

    # Generate sample data
    print(f"Generating {EXPECTED_DOCUMENT_COUNT} sample documents...")
    documents = DemoScraper.generate_sample_data()

    # Generate statistics
    print("Calculating statistics...")
    stats = DemoScraper.generate_statistics(documents)

    # Save outputs
    print("\nSaving outputs...")
    try:
        DocumentOutputFormatter.save_csv(documents)
        DocumentOutputFormatter.save_json(documents)
        print("✓ CSV and JSON files saved")
    except Exception as e:
        print(f"✗ Error saving outputs: {e}")
        return 1

    # Generate report
    print("Generating report...")
    duration = 123.45  # Dummy duration
    report_gen = ReportGenerator(documents, stats, [], duration)
    report_gen.generate_markdown_report()
    print("✓ Report generated")

    # Print summary
    print("\n" + "=" * 70)
    print("Demo Completion Summary")
    print("=" * 70)
    print(f"Total documents generated: {len(documents)}")
    print(f"Date range: {documents[0]['publish_date']} to {documents[-1]['publish_date']}")
    print(f"\nBy County (Top 5):")
    for county, count in sorted(stats['by_county'].items(), key=lambda x: x[1], reverse=True)[:5]:
        print(f"  - {county}: {count}")
    print(f"\nBy Type:")
    for doc_type, count in sorted(stats['by_type'].items(), key=lambda x: x[1], reverse=True):
        print(f"  - {doc_type}: {count}")
    print(f"\nBy Format:")
    for fmt, count in sorted(stats['by_format'].items(), key=lambda x: x[1], reverse=True):
        print(f"  - {fmt}: {count}")

    print("\n✓ Demo data files created in output/ directory")
    print("  - climate_docs_metadata.csv")
    print("  - climate_docs_metadata.json")
    print("  - scraper_report.md")
    print("\n" + "=" * 70 + "\n")

    return 0


if __name__ == '__main__':
    import sys
    sys.exit(main())
