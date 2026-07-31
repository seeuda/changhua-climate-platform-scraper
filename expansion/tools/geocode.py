#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""內政部門牌位置查詢 API 批次地理編碼（在本機執行）。

用法（Windows PowerShell）：
    $env:MOI_API_KEY = "你的APIkey"
    python geocode.py --test                      # 先測單一地址，2 秒確認能不能通
    python geocode.py addresses_to_geocode.csv    # 正式批次

用法（Windows cmd）：
    set MOI_API_KEY=你的APIkey

- API key 只從環境變數讀取，絕不寫進程式或輸出檔。
- 查過的地址存 geocode_cache.json，中斷（Ctrl+C）也會保存，重跑不重查。
- 輸出 geocoded_addresses.csv（地址→座標對照，不含 key、不含個資）。

關於 TLS：adrid.moi.gov.tw 的憑證鏈缺少 Subject Key Identifier 擴充欄位，
不符合 RFC 5280。Python 3.13 起 ssl 預設啟用 VERIFY_X509_STRICT 會因此
拒絕連線（錯誤訊息：Missing Subject Key Identifier）。本程式只關閉這一項
嚴格擴充欄位檢查，**憑證鏈驗證、有效期、主機名稱比對全部保留**，
不使用 verify=False。若連這樣仍失敗，才用 --insecure（會顯示警告）。
"""
import argparse
import csv
import json
import os
import ssl
import sys
import time
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter

API_URL = 'https://adrid.moi.gov.tw/iisi/api/api-key/query-single'
CACHE_PATH = Path('geocode_cache.json')
OUT_PATH = Path('geocoded_addresses.csv')
DELAY_SEC = 0.6
RETRY = 3
FAIL_FAST = 5          # 連續這麼多筆連線失敗就中止，不要空跑完整份清單
TEST_ADDRESS = '彰化縣彰化市大埔路676號'


class RelaxedStrictAdapter(HTTPAdapter):
    """保留完整憑證驗證，僅關閉 RFC 5280 嚴格擴充欄位檢查。"""

    def init_poolmanager(self, *args, **kwargs):
        ctx = ssl.create_default_context()
        # 這行是唯一的放寬：政府憑證缺 Subject Key Identifier
        ctx.verify_flags &= ~getattr(ssl, 'VERIFY_X509_STRICT', 0)
        ctx.check_hostname = True
        ctx.verify_mode = ssl.CERT_REQUIRED
        kwargs['ssl_context'] = ctx
        return super().init_poolmanager(*args, **kwargs)


def make_session(insecure=False):
    s = requests.Session()
    if insecure:
        s.verify = False
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        print('警告：已停用憑證驗證（--insecure），連線內容無法防範中間人攻擊。',
              file=sys.stderr)
    else:
        s.mount('https://', RelaxedStrictAdapter())
    return s


def load_cache():
    if CACHE_PATH.exists():
        return json.loads(CACHE_PATH.read_text(encoding='utf-8'))
    return {}


def save_cache(cache):
    CACHE_PATH.write_text(json.dumps(cache, ensure_ascii=False, indent=1),
                          encoding='utf-8')


def query(session, addr, key):
    """回傳 (結果dict, 是否為連線層失敗)。"""
    headers = {'Authorization': f'Bearer {key}'}
    for attempt in range(RETRY):
        try:
            r = session.get(API_URL, headers=headers,
                            params={'singleQueryStr': addr}, timeout=15)
        except requests.exceptions.SSLError as e:
            print(f'  TLS 錯誤: {str(e)[:160]}', file=sys.stderr)
            return {'status': 'tls_error'}, True
        except requests.RequestException as e:
            print(f'  連線錯誤（第{attempt+1}次）: {str(e)[:120]}', file=sys.stderr)
            time.sleep(2 ** attempt)
            continue
        if r.status_code == 200:
            data = r.json()
            if isinstance(data, list) and data:
                d = data[0]
                return {'status': 'ok', 'x': d.get('x'), 'y': d.get('y'),
                        'address_id': d.get('addressId'),
                        'full_address': d.get('fullAddress')}, False
            return {'status': 'no_result'}, False
        if r.status_code in (401, 403):
            sys.exit(f'API 認證失敗（HTTP {r.status_code}）：'
                     f'請確認 MOI_API_KEY 是否有效或已過期。\n{r.text[:200]}')
        if r.status_code == 429:
            time.sleep(5 * (attempt + 1))
            continue
        print(f'  HTTP {r.status_code}: {r.text[:100]}', file=sys.stderr)
        time.sleep(2 ** attempt)
    return {'status': 'error'}, True


def write_output(addrs, cache):
    with open(OUT_PATH, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.writer(f)
        w.writerow(['address', 'status', 'x', 'y', 'address_id', 'full_address'])
        for a in addrs:
            c = cache.get(a, {'status': 'missing'})
            w.writerow([a, c.get('status'), c.get('x', ''), c.get('y', ''),
                        c.get('address_id', ''), c.get('full_address', '')])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('csv_path', nargs='?', default='addresses_to_geocode.csv')
    ap.add_argument('--test', action='store_true',
                    help='只查一筆測試地址，確認連線與 API key 是否正常')
    ap.add_argument('--insecure', action='store_true',
                    help='最後手段：完全停用憑證驗證（不建議）')
    args = ap.parse_args()

    key = os.getenv('MOI_API_KEY')
    if not key:
        sys.exit('請先設定環境變數 MOI_API_KEY 再執行\n'
                 '  PowerShell: $env:MOI_API_KEY = "你的key"\n'
                 '  cmd:        set MOI_API_KEY=你的key')

    session = make_session(args.insecure)

    if args.test:
        print(f'測試查詢：{TEST_ADDRESS}')
        res, failed = query(session, TEST_ADDRESS, key)
        print(json.dumps(res, ensure_ascii=False, indent=1))
        if res.get('status') == 'ok':
            print('連線與 API key 正常，可以跑正式批次。')
            return 0
        print('測試未成功。若為 TLS 錯誤，可再試 --insecure（會停用憑證驗證）。',
              file=sys.stderr)
        return 1

    with open(args.csv_path, encoding='utf-8-sig') as f:
        rows = list(csv.DictReader(f))
    addrs = sorted({r['address'] for r in rows if r.get('address')})
    cache = load_cache()
    todo = [a for a in addrs if a not in cache or
            cache[a].get('status') in ('error', 'tls_error')]
    print(f'共 {len(addrs)} 個唯一地址，其中 {len(todo)} 個待查')

    consecutive_fail = 0
    try:
        for i, addr in enumerate(todo, 1):
            cache[addr], failed = query(session, addr, key)
            consecutive_fail = consecutive_fail + 1 if failed else 0
            if consecutive_fail >= FAIL_FAST:
                save_cache(cache)
                sys.exit(f'\n連續 {FAIL_FAST} 筆連線失敗，已中止（進度已存檔）。\n'
                         f'先用 python geocode.py --test 診斷，'
                         f'確認可通後再重跑，會自動接續。')
            if i % 20 == 0 or i == len(todo):
                save_cache(cache)
                ok = sum(1 for a in todo[:i] if cache[a]['status'] == 'ok')
                print(f'  進度 {i}/{len(todo)}（成功 {ok}）')
            time.sleep(DELAY_SEC)
    except KeyboardInterrupt:
        save_cache(cache)
        write_output(addrs, cache)
        done = sum(1 for a in addrs if cache.get(a, {}).get('status') == 'ok')
        print(f'\n已中斷，進度已存檔（{done} 筆成功）。重跑會自動接續。')
        return 130

    save_cache(cache)
    write_output(addrs, cache)
    n_ok = sum(1 for a in addrs if cache.get(a, {}).get('status') == 'ok')
    print(f'完成：{n_ok}/{len(addrs)} 成功，結果在 {OUT_PATH}，'
          f'失敗清單可用 status 欄篩出人工處理')
    return 0


if __name__ == '__main__':
    sys.exit(main())
