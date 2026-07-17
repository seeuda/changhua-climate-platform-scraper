# 第二階段：下載一次，事後分類

## 流程

```
metadata.json ─→ ① 全部下載到 downloads/archive/（扁平、只下載一次）
                 ② 事後建立分類檢視 downloads/by_*/（硬連結，不佔額外空間）
                 ③（可選）上傳 archive 到 GCS
```

- **不預設名稱、不過濾**：metadata 裡的每一筆都會下載，包括機關「未識別」的文件
- **檔名用平臺自己的檔名**：從 Content-Disposition 取得伺服器真實檔名，
  只加 5 位序號前綴防重名，例如 `00001_溫室氣體減量行動方案核定本.pdf`；
  伺服器沒給檔名時才退回用頁面標題
- **重新分類永遠不需重新下載**：檢視是指向 archive 的硬連結，
  可隨時增刪、六種並存、不佔額外磁碟空間
- 檔案存在**你的本機**，不會進 GitHub

## 使用

```bash
# 前置：先在可連 cca.gov.tw 的本機完成階段一
python main.py --probe-files

# 下載全部 + 建立預設檢視（by_org_type：中央/地方 → 機關）
python phase2_download.py

# 下載全部 + 一次建立全部六種檢視
python phase2_download.py --organize-by all

# 只下載，不建檢視
python phase2_download.py --organize-by none

# 之後隨時補建/重建檢視（不重新下載）
python organize.py --by county --by date
python organize.py --all

# 已有 archive、只想重建檢視
python phase2_download.py --skip-download --organize-by all
```

## 目錄結構

```
downloads/
├── archive/                          ← 唯一的實體檔案存放處
│   ├── 00001_溫室氣體減量行動方案核定本.pdf
│   ├── 00002_112年度執行方案成果報告.pdf
│   └── ...（全部 346 筆）
├── by_org_type/                      ← 檢視（硬連結，零額外空間）
│   ├── 中央部會/環境部/...
│   ├── 地方政府/南投縣政府/...
│   └── 中央部會/未識別/...           ← 比對不到機關的也在
├── by_county/ by_type/ by_date/ ...  ← 想建幾種就建幾種
└── download_log.json
```

## 續傳與重試

- 重跑 `phase2_download.py` 會以序號前綴比對，已在 archive 的直接跳過
- 失敗的檔案重跑時自動補抓；明細在 `download.log` 的 FAIL 行

## 併發與禮貌

`--max-workers` 控制併發，但全域速率限制器保證對伺服器總請求間隔 ≥2 秒。
346 筆至少 12 分鐘，加傳輸時間估 30–60 分鐘；磁碟預留 1.5 GB。

## GCS 上傳（可選）

只上傳 `archive/`（檢視是硬連結，上傳會在 GCS 變成重複物件）：

```bash
pip install google-cloud-storage
export GOOGLE_APPLICATION_CREDENTIALS="/path/to/key.json"
export GCP_PROJECT_ID="your-project-id"
export GCS_BUCKET_NAME="your-bucket-name"

python phase2_download.py --skip-download --organize-by none --upload --dry-run
python phase2_download.py --skip-download --organize-by none --upload
```

## 故障排除

| 症狀 | 處理 |
|------|------|
| 403 Forbidden | 你在雲端/代理環境——換到本機台灣網路執行 |
| 檢視報 missing | 該序號在 archive 沒有檔案——先重跑下載補齊 |
| 檔名亂碼 | 回報 `download.log` 中該筆的 Content-Disposition 內容 |
| GCS 403 | 服務帳戶需 `storage.objects.create` 權限 |
