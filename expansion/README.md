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

## 執行流程

```
[雲端] ETL（已完成）──> staging/*.json + addresses_to_geocode.csv
[本機] set MOI_API_KEY=...
       python tools/geocode.py expansion/staging/addresses_to_geocode.csv
       （政府 API 擋雲端 IP，僅能在本機執行；key 只放環境變數）
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
