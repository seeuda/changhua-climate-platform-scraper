"""Generate statistical reports from scraped documents."""

import logging
from typing import List, Dict
from pathlib import Path
from datetime import datetime

from config import OUTPUT_CONFIG, EXPECTED_DOCUMENT_COUNT

logger = logging.getLogger(__name__)


class ReportGenerator:
    """Generate scraped data statistics and reports."""

    def __init__(self, documents: List[Dict], statistics: Dict, errors: List[str], scraper_duration: float):
        self.documents = documents
        self.statistics = statistics
        self.errors = errors
        self.duration = scraper_duration

    def generate_markdown_report(self, output_file: Path = None) -> Path:
        """Generate a comprehensive markdown report."""
        output_file = output_file or OUTPUT_CONFIG['report_file']

        try:
            report = self._build_report_content()

            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(report)

            logger.info(f"Report saved to {output_file}")
            return output_file

        except Exception as e:
            logger.error(f"Error generating report: {e}")
            raise

    def _build_report_content(self) -> str:
        """Build the report markdown content."""
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        completion_rate = (len(self.documents) / EXPECTED_DOCUMENT_COUNT * 100) if EXPECTED_DOCUMENT_COUNT > 0 else 0

        report = f"""# 氣候資訊公開平臺文件爬蟲報告

**生成時間**: {timestamp}

---

## 執行摘要

| 項目 | 數值 |
|------|------|
| 已爬取文件數 | {len(self.documents):,} |
| 預期文件數 | {EXPECTED_DOCUMENT_COUNT:,} |
| 完成率 | {completion_rate:.1f}% |
| 執行時間 | {self.duration:.2f} 秒 |
| 錯誤數 | {len(self.errors)} |

---

## 文件統計

### 按地方政府單位統計

"""
        # By county statistics
        by_county = sorted(self.statistics.get('by_county', {}).items(), key=lambda x: x[1], reverse=True)
        if by_county:
            report += "| 縣市 | 筆數 | 佔比 |\n|------|------|------|\n"
            total = len(self.documents)
            for county, count in by_county:
                percentage = (count / total * 100) if total > 0 else 0
                report += f"| {county} | {count} | {percentage:.1f}% |\n"

        # By document type
        report += "\n### 按方案類型統計\n\n"
        by_type = sorted(self.statistics.get('by_type', {}).items(), key=lambda x: x[1], reverse=True)
        if by_type:
            report += "| 類型 | 筆數 | 佔比 |\n|------|------|------|\n"
            total = len(self.documents)
            for doc_type, count in by_type:
                percentage = (count / total * 100) if total > 0 else 0
                report += f"| {doc_type} | {count} | {percentage:.1f}% |\n"

        # By file format
        report += "\n### 按文件格式統計\n\n"
        by_format = sorted(self.statistics.get('by_format', {}).items(), key=lambda x: x[1], reverse=True)
        if by_format:
            report += "| 格式 | 筆數 | 佔比 |\n|------|------|------|\n"
            total = len(self.documents)
            for file_format, count in by_format:
                percentage = (count / total * 100) if total > 0 else 0
                report += f"| {file_format} | {count} | {percentage:.1f}% |\n"

        # By time period
        report += "\n### 按時間分佈統計\n\n"
        by_date = sorted(self.statistics.get('by_date', {}).items())
        if by_date:
            report += "| 時期 | 筆數 |\n|------|------|\n"
            for date, count in by_date:
                report += f"| {date} | {count} |\n"

        # Errors section
        report += f"\n---\n\n## 錯誤報告\n\n"
        if self.errors:
            report += f"**共 {len(self.errors)} 項錯誤**\n\n"
            for idx, error in enumerate(self.errors[:10], 1):  # Show first 10 errors
                report += f"{idx}. {error}\n"
            if len(self.errors) > 10:
                report += f"\n... 及其他 {len(self.errors) - 10} 項錯誤\n"
        else:
            report += "✓ 無錯誤\n"

        # Output files section
        report += f"""
---

## 輸出檔案

- `climate_docs_metadata.csv` - CSV 格式（UTF-8 BOM，可直接用 Excel 開啟）
- `climate_docs_metadata.json` - JSON 格式

---

## 資料欄位說明

"""
        report += """| 欄位 | 說明 |
|------|------|
| 序號 | 文件序號 |
| 標題 | 文件標題 |
| 類型 | 行動方案/執行方案/成果報告 |
| 方案類別 | 具體類別 |
| 地方政府單位 | 發佈或相關縣市 |
| 公開日期 | 文件公開日期 |
| 文件狀態 | 已發佈/待發佈等狀態 |
| 下載連結 | 完整 URL |
| 文件格式 | PDF/Word/Excel/PowerPoint 等 |
| 檔案大小 | 估計或標示的檔案大小 |

---

## 爬蟲設定

- **目標網址**: https://www.cca.gov.tw/information-service/info/2095.html
- **請求延遲**: 2 秒/次（遵守禮貌爬蟲原則）
- **逾時設定**: 10 秒
- **重試次數**: 3 次
- **User-Agent**: Chrome 120（標準瀏覽器識別）

---

## 後續建議

"""
        if completion_rate < 100:
            report += f"- 完成率為 {completion_rate:.1f}%，建議檢查是否有分頁載入或動態載入機制\n"
        else:
            report += "- ✓ 已完成全部文件爬取\n"

        report += """- 建議將此清單作為第二階段文件批次下載的基礎
- 檢查是否需要進行資料驗證和去重
- 考慮建立後續更新機制（定期抓取新增文件）

---

**生成工具**: Climate Platform Document Scraper v1.0
"""

        return report
