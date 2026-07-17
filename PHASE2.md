# 第二階段：檔案下載與 GCS 上傳

## 流程

```
output/climate_docs_metadata.json → download_manager → 本機 downloads/ → (可選) GCS
```

**檔案存在你的本機**，不會進 GitHub（`.gitignore` 已排除）。
全部 346 筆（中央部會 + 地方政府）都會下載，分類方式見 `STORAGE_OPTIONS.md`。

## 重要：檔名與副檔名的來源

平臺下載 URL 不含副檔名（`.../File/Get/cca/zh-tw/<token>`）。
下載器以下列優先序決定存檔副檔名：

1. 回應標頭 `Content-Disposition` 中的伺服器檔名（最可靠）
2. `Content-Type` 對應的格式
3. metadata 中的 `file_format` 欄位
4. 都沒有時存為 `.bin`

存檔名格式：`{5位序號}_{標題前50字}{副檔名}`，例如
`00001_南投縣第二期溫室氣體減量執行方案（核定本）.pdf`

## 使用

```bash
# 前置：先完成階段一（在可連 cca.gov.tw 的本機）
python main.py --probe-files

# 下載全部 346 筆，預設按提交機關分類
python phase2_download.py

# 按中央/地方 → 機關兩層分類（推薦）
python phase2_download.py --organize-by org_type

# 其他分類：county / type / category / date（詳見 STORAGE_OPTIONS.md）
```

**併發與禮貌**：`--max-workers` 控制併發數，但全域速率限制器保證對伺服器
總請求間隔 ≥2 秒——加大 worker 數不會提高請求頻率，只是讓大檔下載時間重疊。
346 筆 × 2 秒 ≈ 至少 12 分鐘，加上傳輸時間預估 30-60 分鐘。

**續傳**：重跑會自動跳過已存在的檔案（以序號前綴比對），中斷後直接重跑即可。

**日誌**：`download.log`（過程）、`downloads/download_log.json`(統計)。

## GCS 上傳（可選）

```bash
pip install google-cloud-storage

export GOOGLE_APPLICATION_CREDENTIALS="/path/to/service-account-key.json"
export GCP_PROJECT_ID="your-project-id"
export GCS_BUCKET_NAME="your-bucket-name"

python phase2_download.py --upload --dry-run   # 先預覽
python phase2_download.py --upload             # 實際上傳
```

上傳後生成 `downloads/public_urls.json`（GCS 物件清單與 URL）。

大量檔案用 `gsutil` 更快：

```bash
gsutil -m cp -r downloads/* gs://your-bucket/climate-docs/
```

## 磁碟空間

346 筆估計 500 MB – 1 GB，預留 1.5 GB。

## 故障排除

| 症狀 | 處理 |
|------|------|
| 403 Forbidden | 你在雲端/代理環境——換到本機台灣網路執行 |
| 存成 .bin | 伺服器沒回 Content-Disposition；查 metadata 的 file_format 手動改名 |
| 部分下載失敗 | 看 `download.log` 的 FAIL 行；重跑會補抓失敗的（成功的自動跳過） |
| GCS 403 | 服務帳戶需 `storage.objects.create` 權限 |
