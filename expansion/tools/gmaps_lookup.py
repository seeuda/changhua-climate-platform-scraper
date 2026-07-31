#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""用瀏覽器自動查 Google 地圖座標（在本機執行）。

把人工流程自動化：輸入地址或地點名稱 → 讀取結果頁網址裡的座標。
取的是 data= 參數中的 !3d<緯度>!4d<經度>（**地點本身**的座標），
不是 @<緯度>,<經度>（地圖視窗中心，會受面板與拖曳影響，實測可差 260 公尺）。

安裝與執行：
    pip install playwright
    python -m playwright install chromium
    python gmaps_lookup.py unlocated_with_links.csv

參數：
    --headed      顯示瀏覽器視窗（預設無頭；出現驗證時需要用這個模式手動通過）
    --limit N     這次只處理 N 筆
    --delay SEC   每筆間隔秒數（預設 4）

進度會即時寫回輸入檔的 google_url / lat / lng 欄，中斷後重跑會自動跳過
已填好的，可以分多次做完。完成後用 manual_coords.py merge 併入。

注意：Google Maps 服務條款禁止自動化擷取其內容建立資料集。是否採用這條
路徑請自行評估；若要整批補齊，內政部「全國門牌坐標」開放資料離線比對
較無疑慮（見 join_address_opendata.py）。
"""
import argparse
import csv
import re
import sys
import time
from pathlib import Path

PLACE_COORD = re.compile(r'!3d(-?\d+\.\d+)!4d(-?\d+\.\d+)')
VIEW_COORD = re.compile(r'@(-?\d+\.\d+),(-?\d+\.\d+)')
SEARCH = 'https://www.google.com/maps/search/?api=1&query={}'
# 彰化縣範圍，超出即視為找錯地方
BBOX = (120.22, 120.80, 23.72, 24.22)


def extract(url):
    m = PLACE_COORD.search(url)
    if m:
        return float(m.group(1)), float(m.group(2)), 'place'
    m = VIEW_COORD.search(url)
    if m:
        return float(m.group(1)), float(m.group(2)), 'viewport'
    return None, None, ''


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('csv_path')
    ap.add_argument('--headed', action='store_true')
    ap.add_argument('--limit', type=int)
    ap.add_argument('--delay', type=float, default=4.0)
    args = ap.parse_args()

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        sys.exit('請先安裝：pip install playwright '
                 '&& python -m playwright install chromium')

    path = Path(args.csv_path)
    rows = list(csv.DictReader(open(path, encoding='utf-8-sig')))
    cols = list(rows[0].keys())
    for c in ('google_url', 'lat', 'lng', 'note'):
        if c not in cols:
            cols.append(c)
            for r in rows:
                r.setdefault(c, '')

    todo = [r for r in rows if not (r.get('google_url') or r.get('lat'))]
    if args.limit:
        todo = todo[:args.limit]
    print(f'共 {len(rows)} 筆，待查 {len(todo)} 筆')

    def flush():
        with open(path, 'w', encoding='utf-8-sig', newline='') as f:
            w = csv.DictWriter(f, fieldnames=cols)
            w.writeheader()
            w.writerows(rows)

    ok = outside = miss = 0
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not args.headed)
        page = browser.new_page(locale='zh-TW')
        for i, r in enumerate(todo, 1):
            q = r.get('query') or r.get('address') or r.get('name')
            try:
                page.goto(SEARCH.format(q), wait_until='domcontentloaded',
                          timeout=30000)
                # 等網址由 /search 轉為 /place（含 !3d!4d）；查無結果則不會轉
                for _ in range(20):
                    if PLACE_COORD.search(page.url):
                        break
                    page.wait_for_timeout(500)
            except Exception as e:
                print(f'  [{i}] {r["id"]} 讀取失敗: {str(e)[:70]}')
                continue
            lat, lng, kind = extract(page.url)
            if lat is None:
                miss += 1
                r['note'] = 'Google 地圖查無明確地點'
                print(f'  [{i}] {r["id"]} {q[:26]} → 查無')
            elif not (BBOX[0] <= lng <= BBOX[1] and BBOX[2] <= lat <= BBOX[3]):
                outside += 1
                r['note'] = f'查得座標落在彰化縣外({lat},{lng})，未採用'
                print(f'  [{i}] {r["id"]} {q[:26]} → 界外，捨棄')
            else:
                ok += 1
                r['google_url'] = page.url
                r['note'] = f'gmaps:{kind}'
                print(f'  [{i}] {r["id"]} {q[:26]} → {lat},{lng} ({kind})')
            if i % 5 == 0:
                flush()
            time.sleep(args.delay)
        browser.close()
    flush()
    print(f'\n完成：取得 {ok} 筆｜界外捨棄 {outside}｜查無 {miss}')
    print(f'接著執行：python manual_coords.py merge {path.name} <staging路徑>')


if __name__ == '__main__':
    main()
