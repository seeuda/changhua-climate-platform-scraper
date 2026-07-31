#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""以內政部「全國門牌坐標」開放資料離線比對，補齊未定位點位。

比 query-single API 好在三點：不會模糊比對亂猜、能一次處理整批、沒有
授權疑慮。API 回報「查無此門牌」的 62 筆多半只是該端點索引問題，
完整檔案未必沒有。

資料來源：政府資料開放平臺搜尋「門牌坐標」，下載彰化縣的 CSV
（欄位名稱各版本略有不同，本程式自動偵測）。

用法：
    python join_address_opendata.py 門牌坐標_彰化縣.csv staging [輸出.csv]

比對方式：把地址正規化成「鄉鎮+路街巷弄+門牌號」的鍵，兩邊都用同一套
規則（addr_util）處理後精確比對，不做模糊匹配。
"""
import csv
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from addr_util import (FULLWIDTH, SEC_NUM, TOWN_RE, VARIANT_CHARS,  # noqa: E402
                       _strip_village_prefix, clean, in_changhua)
from merge_geocoded import twd97_to_wgs84  # noqa: E402

# 各版本可能的欄位名稱
COL_CANDIDATES = {
    'town': ['鄉鎮市區', '鄉鎮市', 'TOWN', 'town', '鄉鎮'],
    'village': ['村里', 'VILLAGE', 'village'],
    'road': ['街路段', '路名', 'ROAD', 'road', '街道'],
    'lane': ['巷', 'LANE', 'lane'],
    'alley': ['弄', 'ALLEY', 'alley'],
    'number': ['號', 'NUMBER', 'number', '門牌號'],
    'x': ['橫坐標', 'X', 'x', '經度', 'LON', 'lon', 'TWD97X'],
    'y': ['縱坐標', 'Y', 'y', '緯度', 'LAT', 'lat', 'TWD97Y'],
    'full': ['地址', 'ADDRESS', 'address', '完整地址'],
}


def pick(header, key):
    for c in COL_CANDIDATES[key]:
        if c in header:
            return c
    return None


def norm_key(addr):
    """地址 → 比對鍵：鄉鎮 + 路街巷弄 + 門牌號。

    村里剝除必須錨定在鄉鎮之後，否則會從字串中間比對到而吃掉鄉鎮名
    （彰化市延和里埔西街 → 彰埔西街）。這裡沿用 addr_util 的
    _strip_village_prefix，不另寫一份規則。
    """
    a, st = clean(addr)
    if st != 'ok':
        a = addr or ''
    # 異體字（山腳路／山脚路）與全形數字統一，否則同一條路比不中
    a = a.translate(FULLWIDTH).translate(VARIANT_CHARS)
    a = a.replace('彰化縣', '')
    m = TOWN_RE.match(a)
    town = m.group(1) if m else ''
    rest = a[len(town):] if town else a
    rest = re.sub(r'\d{1,3}鄰', '', rest)
    rest = _strip_village_prefix(rest)
    rest = re.sub(r'(\d+)-(\d+)', r'\1之\2', rest)
    rest = re.sub(r'([一二三四五六七八九])段',
                  lambda mm: SEC_NUM[mm.group(1)] + '段', rest)
    return re.sub(r'\s', '', town + rest)


def main():
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    src = Path(sys.argv[1])
    staging = Path(sys.argv[2])
    report = Path(sys.argv[3] if len(sys.argv) > 3 else 'opendata_join_report.csv')

    with open(src, encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        header = reader.fieldnames or []
        cx, cy = pick(header, 'x'), pick(header, 'y')
        cfull, ctown = pick(header, 'full'), pick(header, 'town')
        if not (cx and cy):
            sys.exit(f'找不到座標欄。實際欄位：{header}')
        print(f'座標欄：{cx}/{cy}｜地址欄：{cfull or "(需組合)"}')
        index = {}
        for row in reader:
            if cfull:
                addr = row[cfull]
            else:
                parts = [row.get(pick(header, k) or '', '')
                         for k in ('town', 'road', 'lane', 'alley', 'number')]
                addr = ''.join(p for p in parts if p)
            try:
                x, y = float(row[cx]), float(row[cy])
            except (TypeError, ValueError):
                continue
            index[norm_key(addr)] = (x, y, addr)
    print(f'門牌索引建立完成：{len(index)} 筆')

    unloc = list(csv.DictReader(
        open(staging / 'unlocated_points.csv', encoding='utf-8-sig')))
    acc_path = staging / 'geocode_accepted.json'
    accepted = json.loads(acc_path.read_text(encoding='utf-8')) \
        if acc_path.exists() else {}

    hit, out_rows = 0, []
    for r in unloc:
        key = norm_key(r['address'])
        m = index.get(key)
        status = 'no_match'
        if m:
            x, y, matched = m
            lon, lat = (x, y) if abs(x) <= 180 else twd97_to_wgs84(x, y)
            if in_changhua(lon, lat):
                accepted[r['address']] = {
                    'lon': round(lon, 6), 'lat': round(lat, 6),
                    'x': x, 'y': y, 'full_address': matched,
                    'source': 'moi_opendata_門牌坐標'}
                hit += 1
                status = 'matched'
            else:
                status = 'outside_county'
        out_rows.append({**r, 'join_status': status,
                         'matched_address': m[2] if m else ''})
    acc_path.write_text(json.dumps(accepted, ensure_ascii=False, indent=1),
                        encoding='utf-8')
    with open(report, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(out_rows[0].keys()))
        w.writeheader()
        w.writerows(out_rows)
    print(f'比對成功 {hit}/{len(unloc)} 筆，已併入 geocode_accepted.json')
    print(f'明細寫入 {report}；仍未比中者可再用 gmaps_lookup.py 處理')


if __name__ == '__main__':
    main()
