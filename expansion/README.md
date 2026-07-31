# 開圖系統擴充：九份素材 ETL 與地理編碼管線

本目錄是 [Changhua-Climate-Data-Engine-v1](https://github.com/seeuda/Changhua-Climate-Data-Engine-v1)
開圖系統的新圖層前置作業：從九份縣府名冊素材抽出結構化資料，
待地理編碼完成後轉為前端 `POINT_REGISTRY` 可掛載的 GeoJSON。

## 產出總覽（staging/）

| 檔案 | 內容 | 筆數 | 備註 |
|------|------|------|------|
| `shelter_records.json` | 避難收容處所（115年） | 401 | 含 8 項適用災害/特性旗標、服務里別 |
| `relief_station_records.json` | 救濟站（115年） | 334 | 含類型/所屬機關/樓層 |
| `care_station_records.json` | 社區照顧關懷據點（115/7/21） | 377 | 已剔除聯絡人姓名與電話；來源無序號180、序號177重複兩處 |
| `community_assoc_records.json` | 社區發展協會 | 586 | 已剔除理事長/總幹事/會址；定位一律用活動中心（109 筆無活動中心，不編碼） |
| `infant_care_records.json` | 私立托嬰中心（115/7/14） | 61 | 61 家全數為準公共簽約（與 115/7/24 簽約名單完全重合） |
| `early_intervention_records.json` | 早療服務單位（114/8/19） | 5 | 3 家與既有身障圖層同址（服務面向不同，予以保留） |
| `flood_resilient_villages.json` | 水患自主防災社區 | 21 村里/22 社區 | 屬性檔；面幾何待 `extract_villages.py` 併入村里界 |
| `addresses_to_geocode.csv` | 待編碼地址 | 1,655 筆點位/1,395 唯一地址 | `geocode.py` 的輸入 |

身心障礙福利機構一覽表（114/11/13）與既有 `disabled_welfare_facilities.json`
11 家完全一致，不另產出。

## 個資處理原則

來源名冊含個人姓名（理事長/總幹事/董事長/聯絡人）與個人手機號碼，
ETL 階段已全數剔除，只保留機構層級欄位（名稱/地址/機構電話/分類）。
**原始名冊檔案一律不入版控。** 社區發展協會的「會址」常為私人住宅，
不收錄、不上圖；一律以「活動中心」欄位定位。

## 地理編碼結果（三輪完成）

內政部 `query-single` 是**模糊比對**：找不到精確門牌時會拿路名／號碼在
全台猜一個最像的回傳，且不附信心度，一律 HTTP 200。因此 `addr_util.py`
在收到回應時比對縣市／鄉鎮／門牌號／路名，不通過即拒收。實測拒收的多數
確實是誤配，例如：

    彰化縣二水鄉山腳路一段48之1號  → 雲林縣四湖鄉中山東路４８之１號
    彰化縣大城鄉東城村大安路40之1號 → 屏東縣牡丹鄉東源村東源路４０之１號
    彰化縣北斗鎮文苑路二段150號    → 彰化縣北斗鎮西安里斗苑路二段１５０號

| 資料集 | 已定位 | 未定位 | 覆蓋率 |
|--------|-------|-------|-------|
| 避難收容處所 | 356 | 45 | 88.8% |
| 救濟站 | 314 | 20 | 94.0% |
| 關懷據點 | 325 | 52 | 86.2% |
| 社區發展協會 | 356 | 230 | 60.8%（另有 109 筆無活動中心地址） |
| 托嬰中心 | 58 | 3 | 95.1% |
| 早療服務單位 | 4 | 1 | 80.0% |
| **合計** | **1,413** | **242** | **85.4%** |

1,413 個點位全數落在彰化縣界內。未定位者列於
`staging/unlocated_points.csv`，附失敗類型與 API 的錯誤猜測供人工判讀：

- `api_無此門牌` 62 筆：API 查無資料（多為鄉間巷弄，如二水鄉光進一巷）
- `api_僅模糊比對` 150 筆：只回傳他縣市／他鄉鎮／他路名的誤配
- `not_addressable` 30 筆：來源就不是地址（「無」「同上」「社區自行興建」）
  或為地號

**未定位者不以村里中心點回填**。data-engine 的既有原則是未命中圖資即標
`no_hit`／`no_data`，不得回退為粗略位置或低風險（見 v1.3.1 風險語意修正），
點位層級的淹水套疊尤其不能用鄉鎮尺度的近似座標。

## 工具

| 檔案 | 用途 |
|------|------|
| `geocode.py` | 本機批次地理編碼；送查前正規化並產生候選寫法，收到回應即驗證。快取存原始回應（v3） |
| `addr_util.py` | 地址正規化與回應驗證（19 例測試全數正確） |
| `revalidate.py` | 以現行規則重跑已存的原始回應，不必再打 API |
| `merge_geocoded.py` | 併回座標、TWD97→WGS84、產出前端 GeoJSON |
| `crosscheck_care.py` | 以協會名冊校驗關懷據點的跨鄉鎮地址 |
| `extract_villages.py` | 從全國村里界篩出水患自主防災社區 21 村里 |
| `manual_coords.py` | 人工補座標：產生 Google 地圖查詢連結清單、回填後驗證併入 |
| `gmaps_lookup.py` | 以 Playwright 自動查 Google 地圖座標（本機執行） |
| `join_address_opendata.py` | 以內政部門牌坐標開放資料離線精確比對 |
| `verify_town.py` | 以鄉鎮界檢核座標所屬鄉鎮；內建圖資位移校準 |

### ⚠️ 已知問題：data-engine 的 changhua_towns.json 有約 3 公里東偏

用鄉鎮界檢核座標時發現，`changhua-climate-data-engine-v1` 的
`changhua_towns.json` 與真實 WGS84 位置有系統性偏移：

| 樣本（三組互相獨立） | 未位移相符 | 東移 0.03°／南移 0.005° 後 |
|------|-----------|--------------------------|
| 本專案 1,189 筆（內政部門牌座標） | 588 (49.5%) | 1,168 (**98.2%**) |
| data-engine 日照點位 88 筆（人工查核） | 34 (38.6%) | 87 (**98.9%**) |
| data-engine 環保設施點位 52 筆 | 23 (44.2%) | 52 (**100.0%**) |

三組獨立點位算出**完全相同**的最佳位移量，擬合度 98~100%——這是純平移
的特徵，換算為東偏約 3,051 公尺、南偏約 555 公尺。

已排除的可能原因：

- **本專案的座標換算**：`merge_geocoded.twd97_to_wgs84` 與 `pyproj`
  （EPSG:3826→4326）逐點比對，誤差 0.00 公尺
- **點在多邊形演算法**：26 個鄉鎮多邊形各自包含自身重心、彼此無重疊
- **單一來源偏差**：data-engine 自己已人工查核的日照點位（88 筆）
  出現同方向、同幅度的不符

**影響範圍不限於本專案。** `DATA_SCHEMA.md` 載明前端「優先依點位座標
套疊 `changhua_towns.json` 判定實際地理所屬鄉鎮」，且以套疊結果為準；
偏移 3 公里會使約半數點位被判到鄰近鄉鎮，鄉鎮層級的高溫／淹水風險
底色也會畫錯位置。建議以內政部原始鄉鎮界圖資重新產製該檔並回歸驗證。

`verify_town.py` 會先跑校準，偵測到顯著位移即中止逐筆判定（可用
`--force` 強制輸出，但結果不可信）。

### 人工補座標

門牌 API 查不到的點位（鄉間巷弄、公園球場、無門牌設施），可用 Google
地圖以地址或地點名稱查詢：

```bash
python manual_coords.py links staging/unlocated_points.csv 待查_附連結.csv
# 在 google_url 欄貼上網址（或直接填 lat/lng），然後：
python manual_coords.py merge 待查_附連結.csv staging
```

取座標時，**查到地點後按「分享」→ 複製連結 → 貼上網址列前往**，此時網址
`data=` 參數裡的 `!3d<緯度>!4d<經度>` 是**地點本身**的座標；網址開頭的
`@<緯度>,<經度>` 則是**地圖視窗中心**，會受側面板與拖曳影響。實測同一
地點兩者可差約 260 公尺（120.5375241 vs 120.5400990），故工具優先採用
`!3d/!4d`。Google 地圖座標為 WGS84，與本專案輸出一致，不需轉換。

人工補的點位 `coordinate_review_status` 記為 `manually_reviewed`，並帶
`coordinate_source`，與 API 定位的 `pending_review` 區隔。

**授權注意**：Google Maps 服務條款限制擷取其內容建立資料集供非 Google
底圖使用。本系統為 GitHub Pages 靜態站，若採用非 Google 底圖，逐筆人工
查詢與大量擷取的性質不同，建議僅用於少量補遺；若要整批補齊，改用內政部
「全國門牌地址資料」開放檔離線比對較無疑慮（見下）。

### 替代方案：門牌坐標開放資料離線比對

內政部於政府資料開放平臺提供全國門牌坐標檔。下載彰化縣部分後離線精確
比對，可同時解決兩件事：`query-single` 的模糊比對問題，以及 62 筆
「API 查無此門牌」——後者多為 API 端點的索引問題，完整檔案未必沒有。

## 執行流程

```
[雲端] ETL（已完成）──> staging/*.json + addresses_to_geocode.csv
[本機] $env:MOI_API_KEY = "..."
       python geocode.py addresses_retry.csv
       （政府 API 擋雲端 IP，僅能在本機執行；key 只放環境變數。
         geocode.py 與 addr_util.py 需放同一資料夾）
[本機] 從 data.gov.tw 下載「村(里)界(TWD97經緯度)」GeoJSON（同樣擋雲端）
[雲端] python tools/merge_geocoded.py expansion/staging geocoded_addresses.csv out/
       python tools/extract_villages.py 村里界.geojson
       ──> 7 個前端 GeoJSON，掛入 data-engine 的 POINT_REGISTRY
```

## 已知品質註記

- 避難收容處所的 8 個旗標欄序（水災/地震/土石流/海嘯/森林火災/
  適合避難弱者/室內/室外）依表頭排版推定，**上線前應抽 3-5 筆對照
  原始 PDF 人工確認**（各 record 的 `flag_order_note` 亦有標註）。
- 關懷據點有 46 筆經過地址/名稱後處理修補（`needs_review: true`），
  另有臨時停辦公告移至 `status_note`。
- 所有新點位 `coordinate_review_status` 一律標 `pending_review`，
  沿用 data-engine v1.3.1 的人工查核規範，查核後再升級。
- 水患自主防災社區的 22 個社區名，僅潭墘村（潭墘/尤士）為名冊明載，
  其餘以「村里名+社區」推定，待確認。
