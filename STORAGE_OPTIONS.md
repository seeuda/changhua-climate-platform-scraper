# 檔案儲存位置與分類選項

## 儲存位置：本機，不是 GitHub

```
你的電腦（本機磁碟）                      GitHub（代碼倉庫）
────────────────────────────────        ────────────────────
downloads/archive/ ← 實體檔案（一次下載）  Python 代碼、文檔、測試
downloads/by_*/    ← 分類檢視（硬連結）    （downloads/ 與 output/
output/            ← CSV/JSON/報告          皆在 .gitignore 排除）
data/snapshots/    ← 除錯用 HTML 快照
```

## 下載一次，分類隨意

實體檔案只存一份在 `downloads/archive/`（扁平目錄、伺服器原始檔名 +
序號前綴）。分類是事後建立的「檢視」：`downloads/by_org_type/`、
`downloads/by_date/` 等，內容物是指向 archive 的硬連結——
**不佔額外空間、可同時存在多種、重建不需重新下載**。

## 六種分類檢視

| 方式 | 檢視結構 | 適用場景 |
|------|---------|---------|
| `org_type`（預設） | `by_org_type/中央部會/環境部/`、`by_org_type/地方政府/南投縣政府/` | 中央 vs 地方對照 |
| `organization` | `by_organization/環境部/`、`by_organization/南投縣政府/` | 依提交機關快速查找 |
| `county` | `by_county/中央/`、`by_county/南投縣/` | 只關心特定縣市 |
| `type` | `by_type/成果報告/南投縣政府/` | 按行動/執行/成果研究 |
| `category` | `by_category/能源/經濟部/` | 按政策領域（需真實頁面有標示才有值） |
| `date` | `by_date/2023-05/南投縣政府/` | 時間序列分析 |

```bash
# 下載 + 建檢視一次完成
python phase2_download.py --organize-by all

# 之後隨時補建（秒級，不下載）
python organize.py --by county
```

### org_type 分類的完整結構示例

```
downloads/
├── 中央部會/
│   ├── 環境部/
│   │   └── 00001_溫室氣體減量推動方案.pdf
│   ├── 經濟部/          # 能源、製造部門
│   ├── 交通部/          # 運輸部門
│   ├── 內政部/          # 住商部門
│   ├── 農業部/          # 農業部門
│   └── ...
├── 地方政府/
│   ├── 臺北市政府/
│   ├── 新北市政府/
│   ├── 基隆市政府/
│   ├── ...              # 22 個縣市政府
│   └── 連江縣政府/
└── download_log.json
```

### 機關識別方式

機關名單**只用於貼分類標籤，不會過濾下載**——查到的每一筆都下載：

- 標題含 22 縣市名之一（台/臺自動正規化）→ `{縣市}政府`，org_type=地方政府
- 標題含中央機關名（環境部、經濟部…，含環保署等改制前舊名）→ 該機關，org_type=中央部會
- 都比對不到 → `未識別`（照樣下載，檢視中歸入 `未識別/`；
  真實執行後如出現，回報標題樣本即可補規則後重建檢視）

## 磁碟空間

346 筆估計 500 MB – 1 GB。metadata 中 `file_size_bytes` 欄位
（`--probe-files` 開啟時）加總即為精確總量，下載前可先算：

```bash
python -c "
import json
docs = json.load(open('output/climate_docs_metadata.json'))['documents']
total = sum(d.get('file_size_bytes', 0) for d in docs)
known = sum(1 for d in docs if d.get('file_size_bytes'))
print(f'{known}/{len(docs)} 筆已知大小，共 {total/1e6:.0f} MB')"
```
