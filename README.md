# 氣候資訊公開平臺文件爬蟲

爬取[氣候署平臺](https://www.cca.gov.tw/information-service/info/2095.html)所有行動方案、執行方案及成果報告文件的 metadata，輸出為結構化清單。

## 功能

- ✓ 爬取 346+ 筆文件 metadata
- ✓ 提取文件標題、類型、縣市、日期、下載連結等資訊
- ✓ 自動偵測文件格式（PDF/Word/Excel 等）
- ✓ 輸出 CSV（UTF-8 BOM）和 JSON 格式
- ✓ 生成統計報告（按縣市、類型、時間等分類）
- ✓ 禮貌爬蟲延遲和重試機制
- ✓ 詳細執行日誌

## 安裝

### 需求
- Python 3.8+
- pip

### 設定

```bash
# Clone 或下載此專案
cd changhua-climate-platform-scraper

# 安裝依賴
pip install -r requirements.txt
```

## 使用

### 基本用法

```bash
# 爬取所有文件並輸出 CSV、JSON 和報告
python main.py

# 只輸出 CSV
python main.py --format csv

# 只輸出 JSON
python main.py --format json

# 只輸出 Excel
python main.py --format excel

# 跳過生成報告
python main.py --no-report
```

### 輸出檔案

爬蟲執行完成後，在 `output/` 目錄下會產生：

- **climate_docs_metadata.csv** - CSV 格式清單（推薦用 Excel 開啟）
- **climate_docs_metadata.json** - JSON 格式清單
- **scraper_report.md** - 統計報告（Markdown）

## 資料欄位

| 欄位 | 說明 |
|------|------|
| 序號 | 文件序號 |
| 標題 | 文件標題 |
| 類型 | 行動方案/執行方案/成果報告 |
| 方案類別 | 具體類別 |
| 地方政府單位 | 發佈或相關縣市 |
| 公開日期 | 文件公開日期（YYYY-MM-DD） |
| 文件狀態 | 已發佈/待發佈等狀態 |
| 下載連結 | 完整 URL |
| 文件格式 | PDF/Word/Excel/PowerPoint 等 |
| 檔案大小 | 估計或標示的檔案大小 |

## 爬蟲行為

### 禮貌爬蟲原則

- 每次請求間隔 **2 秒**以上（可在 `config.py` 中調整）
- 標準瀏覽器 User-Agent（Chrome 120）
- 遇 429/503 自動回退並重試
- 最多重試 3 次，每次間隔依指數退避

### 超時與重試

- 請求超時：10 秒
- 重試次數：3 次
- 重試延遲：2 秒（第一次）、4 秒（第二次）、8 秒（第三次）

## 設定檔

編輯 `config.py` 可調整：

```python
# 爬蟲延遲（秒）
'request_delay': 2

# 並發下載數量
'max_workers': 3

# 請求超時（秒）
'request_timeout': 10

# 重試次數
'retry_attempts': 3
```

## 輸出範例

### CSV
```
序號,標題,類型,方案類別,地方政府單位,公開日期,文件狀態,下載連結,文件格式,檔案大小
1,台北市淨零排放路徑規劃,執行方案,能源,臺北市,2024-01-15,已發佈,https://...,PDF,2.5 MB
```

### JSON
```json
{
  "metadata": {
    "total_documents": 346,
    "scrape_timestamp": "2024-01-20T10:30:00",
    "source_url": "https://www.cca.gov.tw/information-service/info/2095.html"
  },
  "documents": [
    {
      "id": 1,
      "title": "台北市淨零排放路徑規劃",
      "type": "執行方案",
      "category": "能源",
      "county": "臺北市",
      "publish_date": "2024-01-15",
      "status": "已發佈",
      "download_url": "https://...",
      "file_format": "PDF",
      "file_size": "2.5 MB"
    }
  ]
}
```

## 日誌

執行過程中的詳細日誌會輸出到：
- 終端（stdout）
- `scraper.log` 檔案

## 故障排除

### 無法連接平臺

```
Error: Unable to connect to proxy
```

- 檢查網路連接
- 如有代理設定，確認代理配置正確
- 嘗試稍後重新執行

### 找不到文件

爬蟲未找到預期的 346 筆文件，可能原因：

1. 網站結構變更 - 檢查 HTML selector 是否仍有效
2. 動態載入 - 如網站使用 JavaScript 動態載入，需使用 Selenium 或 Playwright
3. 分頁邏輯變更 - 檢查 URL 參數或 API 端點

### 編碼問題

CSV 檔案已使用 UTF-8 BOM 編碼，應可直接在 Excel 中正常顯示繁體中文。

## 後續步驟

此爬蟲輸出可作為第二階段的基礎：

1. **批次下載** - 使用清單中的下載連結進行批次檔案下載
2. **雲端上傳** - 將檔案上傳至 Google Cloud Storage
3. **定期更新** - 設定定時任務定期更新清單

## 技術堆疊

- **requests** - HTTP 請求
- **BeautifulSoup4** - HTML 解析
- **pandas** - 資料處理（可選，用於 Excel 輸出）
- **lxml** - XML/HTML 解析引擎

## 常見問題

**Q: 爬蟲需要多久？**
A: 取決於網站速度和請求延遲設定，通常 5-15 分鐘。

**Q: 可以加快速度嗎？**
A: 可以減少 `request_delay`，但建議保持禮貌爬蟲原則。

**Q: 如何處理新增的文件？**
A: 重新執行爬蟲即可，會自動去重。

**Q: 可以下載實際檔案嗎？**
A: 目前只爬取 metadata，檔案下載可在第二階段實現。

## License

MIT

## 聯絡

如有問題或建議，請提交 Issue 或 PR。
