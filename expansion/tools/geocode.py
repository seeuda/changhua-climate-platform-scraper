#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""內政部門牌位置查詢 API 批次地理編碼（在本機執行）。

用法（Windows）：
    set MOI_API_KEY=你的APIkey
    python geocode.py addresses_to_geocode.csv

- API key 只從環境變數讀取，絕不寫進程式或輸出檔。
- 查過的地址存 geocode_cache.json，中斷重跑不重查。
- 輸出 geocoded_addresses.csv（地址→座標對照，不含 key、不含個資）。
"""
import csv
import json
import os
import sys
import time
from pathlib import Path

import requests

API_URL = 'https://adrid.moi.gov.tw/iisi/api/api-key/query-single'
CACHE_PATH = Path('geocode_cache.json')
OUT_PATH = Path('geocoded_addresses.csv')
DELAY_SEC = 0.6          # 禮貌間隔
RETRY = 3


def load_cache():
    if CACHE_PATH.exists():
        return json.loads(CACHE_PATH.read_text(encoding='utf-8'))
    return {}


def save_cache(cache):
    CACHE_PATH.write_text(json.dumps(cache, ensure_ascii=False, indent=1),
                          encoding='utf-8')


def query(addr, key):
    headers = {'Authorization': f'Bearer {key}'}
    for attempt in range(RETRY):
        try:
            r = requests.get(API_URL, headers=headers,
                             params={'singleQueryStr': addr}, timeout=15)
        except requests.RequestException as e:
            print(f'  連線錯誤（第{attempt+1}次）: {e}', file=sys.stderr)
            time.sleep(2 ** attempt)
            continue
        if r.status_code == 200:
            data = r.json()
            if isinstance(data, list) and data:
                d = data[0]
                return {'status': 'ok', 'x': d.get('x'), 'y': d.get('y'),
                        'address_id': d.get('addressId'),
                        'full_address': d.get('fullAddress')}
            return {'status': 'no_result'}
        if r.status_code in (401, 403):
            sys.exit(f'API 認證失敗（HTTP {r.status_code}），請確認 MOI_API_KEY 是否有效')
        if r.status_code == 429:
            time.sleep(5 * (attempt + 1))
            continue
        print(f'  HTTP {r.status_code}: {r.text[:100]}', file=sys.stderr)
        time.sleep(2 ** attempt)
    return {'status': 'error'}


def main():
    key = os.getenv('MOI_API_KEY')
    if not key:
        sys.exit('請先設定環境變數 MOI_API_KEY 再執行')
    src = sys.argv[1] if len(sys.argv) > 1 else 'addresses_to_geocode.csv'

    with open(src, encoding='utf-8-sig') as f:
        rows = list(csv.DictReader(f))
    addrs = sorted({r['address'] for r in rows if r.get('address')})
    cache = load_cache()
    todo = [a for a in addrs if a not in cache]
    print(f'共 {len(addrs)} 個唯一地址，其中 {len(todo)} 個未查過')

    for i, addr in enumerate(todo, 1):
        cache[addr] = query(addr, key)
        if i % 20 == 0 or i == len(todo):
            save_cache(cache)
            ok = sum(1 for a in todo[:i] if cache[a]['status'] == 'ok')
            print(f'  進度 {i}/{len(todo)}（成功 {ok}）')
        time.sleep(DELAY_SEC)
    save_cache(cache)

    with open(OUT_PATH, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.writer(f)
        w.writerow(['address', 'status', 'x', 'y', 'address_id', 'full_address'])
        for a in addrs:
            c = cache.get(a, {'status': 'missing'})
            w.writerow([a, c.get('status'), c.get('x', ''), c.get('y', ''),
                        c.get('address_id', ''), c.get('full_address', '')])
    n_ok = sum(1 for a in addrs if cache.get(a, {}).get('status') == 'ok')
    print(f'完成：{n_ok}/{len(addrs)} 成功，結果在 {OUT_PATH}，'
          f'失敗清單可用 status 欄篩出人工處理')


if __name__ == '__main__':
    main()
