# 檔案儲存位置與分類選項

## 🖥️ 檔案儲存位置澄清

### 本地儲存 vs GitHub

```
你的電腦 (本機磁碟)                    GitHub (遠端代碼倉庫)
════════════════════════════════════════════════════════════
downloads/                          📄 Python 代碼、文檔
├── 環保署/                         ├── scraper.py
├── 經濟部/                         ├── config.py
├── 交通部/                         ├── README.md
├── ... (中央部會)                  └── phase2_download.py
│
├── 臺北市政府/                      ❌ 不儲存在 GitHub
├── 新北市政府/                      - 實際下載的檔案
├── 基隆市政府/                      - CSV/JSON 中繼檔案
└── ... (地方政府)                  - 太大（500MB-1GB）

   ↓
 存在你的電腦上
 (500MB - 1GB)
```

**重點**：
- ✅ **代碼、配置、文檔** → 儲存在 GitHub
- ❌ **實際下載的檔案** → 只在本機，不推送到 GitHub
- ❌ **CSV/JSON 中繼檔案** → 列在 `.gitignore`，不追蹤

---

## 📂 分類方式總覽

目前支援 **6 種分類方式**：

| 分類方式 | 命令 | 適用場景 | 結構範例 |
|---------|------|--------|---------|
| **organization** | `--organize-by organization` | 按提交單位分類（預設） | downloads/環保署/, downloads/臺北市政府/ |
| **org_type** | `--organize-by org_type` | 按機構類型分類 | downloads/中央部會/環保署/, downloads/地方政府/臺北市政府/ |
| **county** | `--organize-by county` | 按縣市分類 | downloads/中央/, downloads/臺北市/, downloads/新北市/ |
| **type** | `--organize-by type` | 按文件類型分類 | downloads/行動方案/環保署/, downloads/執行方案/臺北市政府/ |
| **category** | `--organize-by category` | 按政策領域分類 | downloads/能源/環保署/, downloads/運輸/交通部/ |
| **date** | `--organize-by date` | 按發佈時間分類 | downloads/2020-01/環保署/, downloads/2021-03/臺北市政府/ |

---

## 🎯 使用示例

### 1️⃣ 按提交單位分類（預設，推薦）

最直觀的方式 - 直接看提交單位。

```bash
python phase2_download.py
```

**結構**：
```
downloads/
├── 環保署/
│   ├── 00001_環保署淨零排放路徑規劃.pdf
│   ├── 00013_環保署淨零排放路徑規劃.xlsx
│   └── ...
├── 經濟部/
│   ├── 00002_經濟部再生能源推廣計畫.docx
│   └── ...
├── 交通部/
├── ... (中央部會 12 個)
│
├── 臺北市政府/
│   ├── 00014_臺北市淨零排放路徑規劃.pdf
│   └── ...
├── 新北市政府/
├── ... (地方政府 22 個)
│
└── download_log.json
```

**優點**：清楚知道誰提交的文件  
**缺點**：無法快速看全局分布

---

### 2️⃣ 按機構類型分類（推薦用於統計）

區分中央vs地方。

```bash
python phase2_download.py --organize-by org_type
```

**結構**：
```
downloads/
├── 中央部會/
│   ├── 環保署/
│   │   ├── 00001_環保署淨零排放路徑規劃.pdf
│   │   └── ...
│   ├── 經濟部/
│   ├── 交通部/
│   └── ... (12 個中央部會)
│
├── 地方政府/
│   ├── 臺北市政府/
│   │   ├── 00014_臺北市淨零排放路徑規劃.pdf
│   │   └── ...
│   ├── 新北市政府/
│   └── ... (22 個地方政府)
│
└── download_log.json
```

**優點**：清晰的中央vs地方分布  
**數據**：
- 中央部會：126 筆
- 地方政府：220 筆

---

### 3️⃣ 按縣市分類（推薦給地方政府人員）

只看自己縣市的文件。

```bash
python phase2_download.py --organize-by county
```

**結構**：
```
downloads/
├── 中央/
│   ├── 00001_環保署淨零排放路徑規劃.pdf
│   ├── 00002_經濟部再生能源推廣計畫.docx
│   └── ... (126 筆中央部會文件)
│
├── 臺北市/
│   ├── 00014_臺北市淨零排放路徑規劃.pdf
│   └── ...
├── 新北市/
├── 基隆市/
├── 新竹市/
├── ... (所有 22 個縣市)
│
└── download_log.json
```

**優點**：地方政府快速找到自己的文件  
**用法**：`ls downloads/臺北市/`

---

### 4️⃣ 按文件類型分類（推薦用於內容分析）

區分行動方案、執行方案、成果報告。

```bash
python phase2_download.py --organize-by type
```

**結構**：
```
downloads/
├── 行動方案/
│   ├── 環保署/
│   │   ├── 00001_環保署淨零排放路徑規劃.pdf
│   │   └── ...
│   ├── 經濟部/
│   └── ... (各單位的行動方案)
│
├── 執行方案/
│   ├── 環保署/
│   ├── 經濟部/
│   └── ...
│
├── 成果報告/
│   ├── 環保署/
│   ├── 經濟部/
│   └── ...
│
└── download_log.json
```

**統計**：
- 行動方案：116 筆
- 執行方案：115 筆
- 成果報告：115 筆

---

### 5️⃣ 按政策領域分類（推薦用於領域研究）

按能源、運輸、住宅等領域分類。

```bash
python phase2_download.py --organize-by category
```

**結構**：
```
downloads/
├── 能源/
│   ├── 環保署/
│   │   ├── 00001_環保署淨零排放路徑規劃.pdf
│   │   └── ...
│   ├── 經濟部/
│   └── ...
│
├── 運輸/
│   ├── 交通部/
│   ├── 臺北市政府/
│   └── ...
│
├── 住宅建築/
├── 產業/
├── 農業/
├── 水資源/
├── 廢棄物/
├── 其他/
│
└── download_log.json
```

**應用**：
- 能源研究者 → 只看 downloads/能源/
- 運輸規劃者 → 只看 downloads/運輸/

---

### 6️⃣ 按發佈時間分類（推薦用於時間序列分析）

按年月分類。

```bash
python phase2_download.py --organize-by date
```

**結構**：
```
downloads/
├── 2020-01/
│   ├── 環保署/
│   │   ├── 00001_環保署淨零排放路徑規劃.pdf
│   │   └── ...
│   ├── 經濟部/
│   └── ...
│
├── 2020-02/
├── 2020-03/
├── ... (時間序列)
│
├── 2023-10/
│
└── download_log.json
```

**應用**：
- 追蹤政策發佈進度
- 分析時間趨勢

---

## 📊 346 筆檔案分佈

### 按機構類型分佈

```
┌──────────────────────────┐
│  中央部會  │ 地方政府     │
│  126 筆   │ 220 筆      │
└──────────────────────────┘
```

### 按文件類型分佈

```
行動方案   執行方案   成果報告
116 筆    115 筆    115 筆
```

### 中央部會（12 個）

| 部會 | 筆數 | 典型領域 |
|------|------|--------|
| 環保署 | 11 | 環保、廢棄物、水資源 |
| 經濟部 | 11 | 能源、產業 |
| 交通部 | 11 | 運輸、低碳交通 |
| 農委會 | 11 | 農業、林業 |
| 科技部 | 11 | 科技研發 |
| 內政部 | 11 | 住宅建築、都市計畫 |
| 林務局 | 10 | 林業、森林保護 |
| 水利署 | 10 | 水資源、防災 |
| 文化部 | 10 | 文化、藝術 |
| 衛福部 | 10 | 健康、公共衛生 |
| 勞動部 | 10 | 勞動、就業 |
| 國防部 | 10 | 國防、安全 |

### 地方政府（22 個）

每個縣市約 10 筆文件，涵蓋各自負責的領域。

---

## 🔄 多次分類

需要同時用多種分類？只需多次執行：

```bash
# 首次按提交單位
python phase2_download.py

# 然後按機構類型重新組織
python phase2_download.py --organize-by org_type

# 再按政策領域
python phase2_download.py --organize-by category
```

**注意**：會覆蓋之前的目錄結構。如需保留多個版本：

```bash
# 方式 1：改變下載目錄
mkdir downloads_by_org
python phase2_download.py  # 預設 downloads/

mkdir downloads_by_type
mv downloads downloads_by_org
mkdir downloads
python phase2_download.py --organize-by type
mv downloads downloads_by_type

# 方式 2：手動複製整個資料夾
cp -r downloads downloads_backup
python phase2_download.py --organize-by category
```

---

## 💾 磁碟空間預估

```
中央部會 (126 筆)      ~ 150-200 MB
地方政府 (220 筆)      ~ 300-500 MB
─────────────────────────────────
總計 (346 筆)          ~ 500 MB - 1 GB
```

**預留磁碟空間**：至少 1.5 GB（考慮中間檔案）

---

## 📝 下載日誌

每次下載都會生成 `downloads/download_log.json`：

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
    "環保署": {"count": 11, "size": 25165824},
    "臺北市政府": {"count": 10, "size": 15728640},
    ...
  }
}
```

---

## ✅ 快速參考

```bash
# 下載所有 346 筆文件
pip install -r requirements.txt
python main.py                               # 生成 metadata
python phase2_download.py                    # 下載並按提交單位分類

# 其他分類方式
python phase2_download.py --organize-by org_type      # 中央vs地方
python phase2_download.py --organize-by county        # 按縣市
python phase2_download.py --organize-by type          # 按文件類型
python phase2_download.py --organize-by category      # 按政策領域
python phase2_download.py --organize-by date          # 按時間

# 增加下載速度
python phase2_download.py --max-workers 10

# 上傳到 GCS
python phase2_download.py --upload
```

---

## 🎓 總結

| 需求 | 推薦分類方式 |
|------|------------|
| 快速找我單位的文件 | `organization` 或 `county` |
| 統計中央vs地方 | `org_type` |
| 分析政策領域 | `category` |
| 研究文件類型 | `type` |
| 追蹤時間趨勢 | `date` |

**預設（最推薦）**：`--organize-by organization`

---

**版本**: 1.0  
**更新**: 2026-07-17  
**狀態**: ✅ 支援所有分類方式
