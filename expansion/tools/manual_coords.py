#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""人工補座標的輔助工具。

內政部門牌 API 查不到的點位（鄉間巷弄、公園球場、無門牌設施），可用
Google 地圖以地址或地點名稱查詢後取座標。

兩個子命令：

  links   產生待查清單，每筆附可直接點開的 Google 地圖查詢網址
            python manual_coords.py links unlocated_points.csv 待查_附連結.csv

  merge   讀回填好的座標，驗證後併入 geocode_accepted.json
            python manual_coords.py merge 待查_附連結.csv expansion/staging

回填方式（擇一，google_url 優先）：
  - google_url 欄：整段網址貼上即可
  - lat / lng 欄：直接填經緯度

網址座標的取法（依精確度排序）：
  1. 查到地點後按「分享」→ 複製連結 → 貼上網址列前往，
     此時網址的 data= 參數含 !3d<緯度>!4d<經度>，是**地點本身**的座標
  2. 網址的 @<緯度>,<經度> 是**地圖視窗中心**，會受面板與拖曳影響，
     縮放層級低時誤差可達數百公尺

本工具兩種都能解析，並優先採用 !3d/!4d。
Google 地圖座標為 WGS84，與本專案輸出一致，不需轉換。
"""
import csv
import json
import re
import sys
from pathlib import Path
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).resolve().parent))
from addr_util import in_changhua  # noqa: E402

PLACE_COORD = re.compile(r'!3d(-?\d+\.\d+)!4d(-?\d+\.\d+)')
VIEW_COORD = re.compile(r'@(-?\d+\.\d+),(-?\d+\.\d+)')
SEARCH_URL = 'https://www.google.com/maps/search/?api=1&query='


def parse_coords(url):
    """回傳 (lat, lng, 取值來源)。優先地點座標，其次視窗中心。"""
    if not url:
        return None, None, ''
    m = PLACE_COORD.search(url)
    if m:
        return float(m.group(1)), float(m.group(2)), 'place(!3d!4d)'
    m = VIEW_COORD.search(url)
    if m:
        return float(m.group(1)), float(m.group(2)), 'viewport(@)'
    return None, None, ''


def cmd_links(src, dst):
    rows = list(csv.DictReader(open(src, encoding='utf-8-sig')))
    out = []
    for r in rows:
        # 有地址者用地址查；來源就沒地址者改用「名稱＋鄉鎮」查
        if r.get('failure') == 'not_addressable' or not r.get('address'):
            q = f"彰化縣{r.get('town','')}{r.get('name','')}"
        else:
            q = r['address']
        out.append({**r, 'query': q, 'google_search_url': SEARCH_URL + quote(q),
                    'google_url': '', 'lat': '', 'lng': '', 'note': ''})
    cols = list(out[0].keys())
    with open(dst, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(out)
    print(f'{len(out)} 筆待查清單寫入 {dst}')
    print('請在 google_url 欄貼上分享連結導頁後的網址，或直接填 lat/lng')


def cmd_merge(src, staging):
    staging = Path(staging)
    rows = list(csv.DictReader(open(src, encoding='utf-8-sig')))
    acc_path = staging / 'geocode_accepted.json'
    accepted = json.loads(acc_path.read_text(encoding='utf-8')) \
        if acc_path.exists() else {}
    added, skipped, outside = 0, 0, []
    for r in rows:
        lat, lng, src_kind = parse_coords(r.get('google_url'))
        if lat is None and r.get('lat') and r.get('lng'):
            try:
                lat, lng, src_kind = float(r['lat']), float(r['lng']), 'manual'
            except ValueError:
                lat = None
        if lat is None:
            skipped += 1
            continue
        if not in_changhua(lng, lat):
            outside.append((r.get('id'), r.get('name'), lat, lng))
            continue
        accepted[r['address']] = {
            'lon': round(lng, 6), 'lat': round(lat, 6),
            'source': f'google_maps:{src_kind}',
            'coordinate_review_status': 'manually_reviewed',
            'note': r.get('note') or None}
        added += 1
    acc_path.write_text(json.dumps(accepted, ensure_ascii=False, indent=1),
                        encoding='utf-8')
    print(f'併入 {added} 筆｜未填座標略過 {skipped} 筆｜落在彰化縣外 {len(outside)} 筆')
    for o in outside:
        print(f'   界外(未併入): {o[0]} {o[1]} ({o[2]}, {o[3]})')
    print(f'已接受座標共 {len(accepted)} 個唯一地址')


def main():
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    cmd = sys.argv[1]
    if cmd == 'links':
        cmd_links(sys.argv[2], sys.argv[3] if len(sys.argv) > 3
                  else 'unlocated_with_links.csv')
    elif cmd == 'merge':
        cmd_merge(sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else 'staging')
    else:
        sys.exit(__doc__)


if __name__ == '__main__':
    main()
