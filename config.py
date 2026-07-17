"""Configuration for the climate platform scraper."""

import os
from pathlib import Path

# Base configuration
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
OUTPUT_DIR = BASE_DIR / "output"

# Ensure directories exist
DATA_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)

# Platform configuration
CLIMATE_PLATFORM_URL = "https://www.cca.gov.tw/information-service/info/2095.html"

# API configuration (if available)
API_BASE_URL = "https://www.cca.gov.tw"
API_ENDPOINTS = {
    "search": "/api/search",
    "document": "/api/document",
}

# Scraper configuration
SCRAPER_CONFIG = {
    "request_timeout": 10,
    "retry_attempts": 3,
    "retry_delay": 2,
    "request_delay": 2,  # Delay between requests in seconds
    "max_workers": 3,  # Concurrent downloads
    "log_file": BASE_DIR / "scraper.log",
}

# Output configuration
# CSV gets a UTF-8 BOM so Excel opens it correctly; JSON must NOT have a
# BOM (json.load rejects it).
OUTPUT_CONFIG = {
    "csv_file": OUTPUT_DIR / "climate_docs_metadata.csv",
    "json_file": OUTPUT_DIR / "climate_docs_metadata.json",
    "report_file": OUTPUT_DIR / "scraper_report.md",
    "csv_encoding": "utf-8-sig",
    "json_encoding": "utf-8",
}

# Demo outputs are kept under separate names so fabricated sample data can
# never be mistaken for real scraped deliverables.
DEMO_OUTPUT_CONFIG = {
    "csv_file": OUTPUT_DIR / "demo_climate_docs_metadata.csv",
    "json_file": OUTPUT_DIR / "demo_climate_docs_metadata.json",
    "report_file": OUTPUT_DIR / "demo_scraper_report.md",
}

# Document field mapping
DOCUMENT_FIELDS = {
    "id": "序號",
    "title": "標題",
    "type": "類型",
    "category": "政策領域",
    "organization": "提交單位",
    "org_type": "機構類型",
    "county": "縣市",
    "publish_date": "公開日期",
    "status": "文件狀態",
    "download_url": "下載連結",
    "file_format": "文件格式",
    "file_size": "檔案大小",
}

# Expected document count
EXPECTED_DOCUMENT_COUNT = 346
