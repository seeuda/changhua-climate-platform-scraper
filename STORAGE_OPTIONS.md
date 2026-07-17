# 檔案儲存位置與分類選項

## 儲存位置：本機，不是 GitHub

```
你的電腦（本機磁碟）                      GitHub（代碼倉庫）
────────────────────────────────        ────────────────────
downloads/     ← 下載的 346 筆檔案        Python 代碼、文檔、測試
output/        ← CSV/JSON/報告            （downloads/ 與 output/
data/snapshots/← 除錯用 HTML 快照           皆在 .gitignore 排除）
```

## 六種分類方式

透過 `--organize-by` 選擇，**全部 346 筆（中央 + 地方）都會下載**：

| 方式 | 目錄結構 | 適用場景 |
|------|---------|---------|
| `organization`（預設） | `downloads/環境部/`、`downloads/南投縣政府/` | 依提交機關快速查找 |
| `org_type` | `downloads/中央部會/環境部/`、`downloads/地方政府/南投縣政府/` | 中央 vs 地方對照（推薦） |
| `county` | `downloads/中央/`、`downloads/南投縣/` | 地方使用者只關心自己縣市 |
| `type` | `downloads/成果報告/南投縣政府/` | 按行動/執行/成果研究 |
| `category` | `downloads/能源/經濟部/` | 按政策領域研究（注意：category 欄位需真實頁面有標示才有值） |
| `date` | `downloads/2023-05/南投縣政府/` | 時間序列分析 |

```bash
python phase2_download.py --organize-by org_type
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

- 標題含 22 縣市名之一（台/臺自動正規化）→ `{縣市}政府`，org_type=地方政府
- 標題含中央機關名（環境部、經濟部…，含環保署等改制前舊名）→ 該機關，org_type=中央部會
- 都比對不到 → `未識別`（真實執行後如出現，請回報標題樣本以補規則）

## 需要多種分類並存？

同一份下載重跑不同分類會混在一起，請用不同目錄：

```bash
python phase2_download.py --organize-by org_type
mv downloads downloads_by_orgtype
python phase2_download.py --organize-by date
```

（第二次會重新下載；或直接用檔案管理器複製第一份再手動重組。）

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
