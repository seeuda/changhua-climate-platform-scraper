# 技術架構說明

## 概況

兩階段管線：**階段一**爬取 346 筆文件 metadata 輸出結構化清單；**階段二**依清單批次下載檔案（可選上傳 GCS）。

**分支**: `claude/climate-docs-scraper-mq3ckc`

## 關於目標網站的已查證事實

這兩點決定了整體設計，是本專案最重要的技術前提：

1. **`www.cca.gov.tw` 對雲端主機/代理/機器人客戶端回 403**（連首頁都擋）。
   爬蟲必須在台灣本機網路環境、帶瀏覽器 User-Agent 執行。
2. **真實下載連結為 `https://service.cca.gov.tw/File/Get/cca/zh-tw/<token>`，不含副檔名。**
   檔案格式、檔名、大小只能從 HTTP 回應標頭（Content-Disposition /
   Content-Type / Content-Length）或頁面標示取得。

## 模組一覽

| 模組 | 職責 |
|------|------|
| `scraper.py` | 爬取 metadata：錨定 `/File/Get/` 連結模式抽取、列上下文還原標題、機關/類型/日期分類、`--probe-files` HEAD 探測、分頁跟隨、HTML 快照 |
| `fileinfo.py` | 共用：從回應標頭推斷檔名/格式/大小（RFC 5987 Content-Disposition 解析） |
| `rate_limiter.py` | 全域速率限制器：跨線程保證對伺服器總請求間隔 ≥2 秒 |
| `output_formatter.py` | CSV（UTF-8 BOM，Excel 相容）/ JSON（無 BOM）/ Excel 輸出 |
| `report_generator.py` | Markdown 統計報告（中央vs地方、縣市、類型、格式、時間） |
| `download_manager.py` | 批次下載：6 種分類路由、Content-Disposition 副檔名、續傳跳過、線程安全統計 |
| `gcs_uploader.py` | Google Cloud Storage 批次上傳（可選） |
| `main.py` | 階段一 CLI |
| `phase2_download.py` | 階段二 CLI（下載 + 上傳） |
| `demo_scraper.py` | 生成 `demo_*` 前綴的假資料驗證輸出流程（**非真實資料**） |
| `config.py` | 集中配置 |
| `tests/` | 合成 HTML 解析測試 + 本地 HTTP 伺服器下載整合測試 |

## 爬蟲抽取策略

不猜 CSS selector，改以已驗證的連結模式為錨點：

1. 找出頁面上所有 href 含 `/File/Get/` 的 `<a>`（真實檔案連結的唯一特徵）
2. 上溯至所屬 `<tr>` / `<li>` 取得列上下文
3. 標題：優先取有意義的錨點文字；若是「下載」「PDF下載」等按鈕文字，改取列中最長的標題欄
4. 機關：以 22 縣市名單（台/臺正規化後）比對，其次比對中央部會清單（含改制前舊名）
5. 類型：標題關鍵字（成果報告/執行方案/行動方案/調適計畫/推動方案）
6. 日期：同時支援西元（`2023-11-20`）與民國（`112.05.03`、`112年度`）
7. 分頁：只跟隨頁面實際渲染出的分頁連結，不盲目遞增 `?page=N`
8. 每頁 HTML 存快照到 `data/snapshots/`，解析失敗可離線診斷

`--probe-files` 開啟後，對每筆文件發 HEAD 請求（伺服器拒絕 HEAD 時退回
Range GET），從標頭讀取真實檔名、格式、大小。346 筆在 2 秒禮貌間隔下約需 12 分鐘。

## 禮貌爬蟲實作

- `rate_limiter.GLOBAL_RATE_LIMITER`：以鎖保護的單例，爬取與下載共用同一配額，
  **不論並發 worker 數量**，任兩次請求間隔 ≥2 秒
- 429/503 依 `Retry-After` 退避；其他錯誤指數退避重試 3 次
- 403 直接停止並提示需在本機執行（重試無意義）

## 資料欄位

| 欄位 | 說明 |
|------|------|
| id | 序號 |
| title | 標題 |
| type | 行動方案/執行方案/成果報告/調適計畫/推動方案/其他 |
| organization | 提交機關（環境部、南投縣政府…） |
| org_type | 中央部會 / 地方政府 |
| county | 縣市（中央機關為「中央」） |
| publish_date | YYYY-MM-DD（民國日期已轉換） |
| download_url | 完整下載 URL |
| file_format | PDF/Word/Excel/ODF/ZIP（probe 後準確） |
| file_size / file_size_bytes | probe 後自 Content-Length 取得 |
| server_filename | probe 後自 Content-Disposition 取得 |

## 測試

```bash
python tests/test_extraction.py        # 解析邏輯（合成 HTML）
python tests/test_download_manager.py  # 下載端到端（本地 HTTP 伺服器）
```

## 已知限制

- 合成 HTML 測試驗證的是解析邏輯健全性，不是真實頁面結構；首次真實執行後
  請核對筆數，必要時把 `data/snapshots/page_1.html` 提供給開發者調整
- 若清單由 JavaScript 動態渲染，需改用 Playwright/Selenium 取得渲染後 HTML
  （快照會顯示這一點：頁面裡沒有任何 File/Get 連結）
- `category`（政策領域）欄位需依真實頁面呈現方式再補分類邏輯
