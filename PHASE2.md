# 第二階段：檔案下載與 GCS 上傳

## 概況

第二階段實現大規模檔案下載和 Google Cloud Storage（GCS）上傳功能，完整流程為：

```
metadata.json → 下載管理器 → 本地存儲 (downloads/) → GCS 上傳
```

---

## 📁 檔案存儲結構

所有下載的檔案按縣市分類存儲：

```
downloads/
├── 臺北市/
│   ├── 00001_文件標題_1.pdf
│   ├── 00002_文件標題_2.docx
│   └── ...
├── 新北市/
│   ├── 00015_文件標題_15.xlsx
│   └── ...
├── 基隆市/
│── 新竹市/
├── 新竹縣/
├── ... (共 22 個縣市)
├── 連江縣/
├── download_log.json          # 下載統計
└── public_urls.json           # GCS 公開 URL
```

### 檔案名稱規則

`{序號}_{標題_前50字}_{簡稱}.{格式}`

例如：
- `00001_臺北市淨零排放路徑規劃_臺北市.pdf`
- `00015_新北市再生能源推廣計畫_新北市.docx`

---

## 🚀 快速開始

### Step 1: 安裝依賴

```bash
# 基本依賴
pip install -r requirements.txt

# 如果要上傳到 GCS，還需要
pip install google-cloud-storage>=2.10.0
```

### Step 2: 運行爬蟲（第一階段）

```bash
# 如果還沒有 metadata，先生成
python main.py
# 或使用演示數據
python demo_scraper.py
```

### Step 3: 下載檔案

```bash
# 基本下載（3 個並發 worker）
python phase2_download.py

# 自訂並發數
python phase2_download.py --max-workers 5

# 使用自訂 metadata 檔案
python phase2_download.py --metadata /path/to/metadata.json
```

### Step 4: 上傳到 GCS

#### 方法 A：使用環境變數

```bash
export GCP_PROJECT_ID="your-project-id"
export GCS_BUCKET_NAME="your-bucket-name"

# 下載 + 上傳
python phase2_download.py --upload

# 僅上傳（跳過下載）
python phase2_download.py --upload --download false
```

#### 方法 B：命令行參數

```bash
python phase2_download.py --upload \
  --project-id your-project-id \
  --bucket your-bucket-name
```

#### 方法 C：先預覽（dry-run）

```bash
python phase2_download.py --upload --dry-run
```

---

## 📊 DownloadManager 模組

### 功能特性

| 特性 | 說明 |
|------|------|
| **並發下載** | 支援多線程並發下載（預設 3 workers） |
| **進度跟蹤** | 實時顯示下載進度 |
| **錯誤恢復** | 失敗自動重試，詳細錯誤報告 |
| **斷點續傳** | 已存在檔案自動跳過 |
| **縣市分類** | 按縣市自動建立目錄 |
| **檔案驗證** | 驗證下載完整性 |

### 使用示例

```python
from download_manager import DownloadManager
import json

# 加載 metadata
with open('output/climate_docs_metadata.json') as f:
    data = json.load(f)
    documents = data['documents']

# 下載檔案
manager = DownloadManager(download_dir=Path('downloads'))
stats = manager.download_documents(documents, max_workers=5)

# 查看結果
print(f"成功: {stats['success']}")
print(f"失敗: {stats['failed']}")
print(f"總大小: {manager.format_size(stats['total_size'])}")

# 查看目錄結構
structure = manager.get_directory_structure()
for county, info in structure.items():
    print(f"{county}: {info['count']} 檔案, {manager.format_size(info['size'])}")
```

---

## ☁️ GCSUploader 模組

### 前置需求

1. **Google Cloud 帳戶**
   - 有效的 GCP 專案

2. **GCS 儲存桶**
   - 已建立的 GCS bucket

3. **認證設定**
   ```bash
   # 方法 1：使用服務帳戶金鑰（推薦）
   export GOOGLE_APPLICATION_CREDENTIALS="/path/to/service-account-key.json"

   # 方法 2：使用 gcloud CLI
   gcloud auth application-default login
   ```

### 使用示例

```python
from gcs_uploader import GCSUploader
from pathlib import Path

# 初始化上傳器
uploader = GCSUploader(
    project_id='your-project-id',
    bucket_name='your-bucket-name',
    prefix='climate-docs'
)

# 上傳整個目錄
stats = uploader.upload_directory(Path('downloads'))
print(f"上傳成功: {stats['success']}")

# 取得上傳的檔案列表
files = uploader.list_uploaded_files()
for f in files:
    print(f)

# 生成公開 URL
urls = uploader.generate_public_urls()
for url_info in urls:
    print(f"gs://{bucket}/{url_info['name']}")
    print(f"Public: {url_info['url']}")
```

---

## 📊 下載統計

### 下載日誌

下載完成後，會生成 `downloads/download_log.json`：

```json
{
  "stats": {
    "total": 346,
    "success": 320,
    "failed": 15,
    "skipped": 11,
    "total_size": 524288000
  },
  "structure": {
    "臺北市": {"count": 19, "size": 25165824},
    "新北市": {"count": 19, "size": 27262976},
    ...
  }
}
```

### 上傳日誌

上傳完成後，會生成 `downloads/public_urls.json`：

```json
[
  {
    "name": "climate-docs/臺北市/00001_文件標題.pdf",
    "url": "https://storage.googleapis.com/bucket/climate-docs/...",
    "size": 1048576
  },
  ...
]
```

---

## 🔧 配置參數

### DownloadManager

| 參數 | 預設值 | 說明 |
|------|--------|------|
| `download_dir` | `./downloads` | 本地下載目錄 |
| `max_workers` | 3 | 並發下載數 |
| `request_timeout` | 10秒 | 單個下載逾時 |
| `request_delay` | 2秒 | 下載間隔 |

### GCSUploader

| 參數 | 說明 |
|------|------|
| `project_id` | GCP 專案 ID |
| `bucket_name` | GCS Bucket 名稱 |
| `prefix` | GCS 物件前綴（預設：climate-docs） |

---

## 🚨 故障排除

### 下載問題

**Q: 下載速度很慢**
- A: 增加 `--max-workers` 參數（推薦 5-10）
- A: 檢查網路連接

**Q: 某些檔案下載失敗**
- A: 檢查 `download.log` 查看具體錯誤
- A: 某些 URL 可能已過期或被封鎖
- A: 重新運行會自動跳過已下載的檔案

**Q: 磁碟空間不足**
- A: 預計需要 500MB-1GB 空間（取決於檔案大小）
- A: 可先下載特定縣市的檔案進行測試

### 上傳問題

**Q: 無法連接 GCS**
- A: 檢查 Google Cloud 認證
- A: 確認 GCP_PROJECT_ID 和 GCS_BUCKET_NAME 正確
- A: 使用 `--dry-run` 先檢查連接

**Q: 權限不足**
```
PermissionError: 403 Forbidden
```
- A: 確保服務帳戶有 `storage.objects.create` 權限
- A: 更新 IAM 角色為 `roles/storage.admin`

**Q: Bucket 不存在**
```
NotFound: 404 POST gs://bucket/...
```
- A: 先建立 GCS Bucket：
```bash
gsutil mb gs://your-bucket-name
```

---

## 📈 效能優化

### 下載優化

1. **增加並發數**
   ```bash
   python phase2_download.py --max-workers 10
   ```

2. **分批下載**
   - 為不同縣市建立不同的元資料檔案
   - 分別下載後再合併

3. **選擇性下載**
   - 修改 metadata，只保留需要的文件

### 上傳優化

1. **使用 gsutil（更快速）**
   ```bash
   # 安裝 Google Cloud SDK
   gcloud init
   
   # 上傳整個目錄
   gsutil -m cp -r downloads/* gs://your-bucket/climate-docs/
   ```

2. **分批上傳**
   - 將大目錄分成多個子目錄
   - 並行上傳不同縣市

---

## 🔐 安全建議

### 認證安全

1. **不要在代碼中硬編碼認證資訊**
   - 使用環境變數
   - 使用服務帳戶金鑰檔

2. **保護服務帳戶金鑰**
   ```bash
   chmod 400 /path/to/service-account-key.json
   ```

3. **定期輪換密鑰**

### 資料安全

1. **啟用 GCS 版本控制**
   - 防止意外刪除

2. **設定存取控制**
   ```bash
   # 限制只有特定使用者可以存取
   gsutil acl ch -u user@example.com:R gs://bucket/climate-docs/
   ```

3. **啟用加密**
   - 使用 Google 管理的密鑰（預設）
   - 或客戶管理的密鑰（CMEK）

---

## 📝 日誌檔案

### 位置

- `download.log` - 下載過程詳細日誌
- `downloads/download_log.json` - 下載統計
- `downloads/public_urls.json` - 生成的公開 URL

### 查看日誌

```bash
# 即時查看
tail -f download.log

# 查看失敗的下載
grep "✗" download.log

# 統計成功率
grep "✓" download.log | wc -l
```

---

## 🎯 完整工作流程

```bash
# 1. 安裝依賴
pip install -r requirements.txt

# 2. 運行第一階段爬蟲（如果還沒有 metadata）
python main.py

# 3. 下載檔案
python phase2_download.py

# 4. 檢查下載結果
cat downloads/download_log.json

# 5. 設定 GCS 認證
export GOOGLE_APPLICATION_CREDENTIALS="path/to/key.json"
export GCP_PROJECT_ID="your-project"
export GCS_BUCKET_NAME="your-bucket"

# 6. 預覽上傳（不實際上傳）
python phase2_download.py --upload --dry-run

# 7. 上傳到 GCS
python phase2_download.py --upload

# 8. 驗證上傳
python -c "
from gcs_uploader import GCSUploader
uploader = GCSUploader('project', 'bucket')
files = uploader.list_uploaded_files()
print(f'已上傳 {len(files)} 個檔案')
"
```

---

## 💡 提示

### 測試建議

1. **先用小批量測試**
   ```bash
   # 編輯 metadata，只保留前 10 筆
   python phase2_download.py
   ```

2. **檢查下載品質**
   - 驗證檔案大小是否合理
   - 嘗試開啟部分檔案

3. **測試 GCS 連接**
   ```bash
   python gcs_uploader.py
   ```

### 後續擴展

1. **自動化排程**
   - 使用 Cron job 定期執行
   - 或使用 Cloud Scheduler

2. **監控告警**
   - 監控下載失敗率
   - 設定 Slack/Email 通知

3. **數據分析**
   - 分析下載統計
   - 追蹤檔案變更

---

**版本**: 2.0.0  
**狀態**: ✅ 第二階段實現完成
