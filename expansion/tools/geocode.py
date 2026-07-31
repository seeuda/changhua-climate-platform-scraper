#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""內政部門牌位置查詢 API 批次地理編碼（在本機執行）。

用法（Windows PowerShell）：
    $env:MOI_API_KEY = "你的APIkey"
    python geocode.py --test                   # 先測連線，2 秒
    python geocode.py addresses_retry.csv      # 批次

重要：內政部 query-single 是**模糊比對**，找不到精確門牌時會拿路名/號碼
在全台猜一個最像的回傳，且不附信心度。第一輪 1,395 筆中有 96 筆配到
別的鄉鎮或別的縣市（例：彰化縣二水鄉上豐村山腳路113-5號 →
苗栗縣通霄鎮南和113之5號）。因此本程式：

  1. 送查前先用 addr_util.clean() 正規化（去重複鄉鎮前綴、剝樓層/雜訊、
     破折號轉「之」），並產生候選寫法依序嘗試；
  2. 收到回應後用 addr_util.validate() 比對縣市/鄉鎮/門牌號/路名，
     **不通過就拒收**，不會把猜出來的座標當成功；
  3. status 欄只有真的拿到通過驗證的座標才是 ok。

需要 addr_util.py 與本檔放在同一資料夾。
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

sys.path.insert(0, str(Path(__file__).resolve().parent))
from addr_util import TOWN_RE, clean, validate, variants  # noqa: E402

API_URL = 'https://adrid.moi.gov.tw/iisi/api/api-key/query-single'
CACHE_PATH = Path('geocode_cache.json')
# 快取結構版本。第一輪的快取是「未經驗證」的結果（status=ok 只代表 API
# 有回傳，不代表配對正確），若被沿用會讓整輪重試變成空跑，所以版本不符
# 一律作廢重查。
CACHE_VERSION = 3
OUT_PATH = Path('geocoded_addresses.csv')
DELAY_SEC = 0.6
RETRY = 3
FAIL_FAST = 5
TEST_ADDRESS = '彰化縣彰化市大埔路676號'


class RelaxedStrictAdapter(HTTPAdapter):
    """保留完整憑證驗證，僅關閉 RFC 5280 嚴格擴充欄位檢查。

    adrid.moi.gov.tw 憑證鏈缺 Subject Key Identifier，Python 3.13 起
    ssl 預設啟用 VERIFY_X509_STRICT 會拒絕連線。
    """

    def init_poolmanager(self, *args, **kwargs):
        ctx = ssl.create_default_context()
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
        print('警告：已停用憑證驗證（--insecure），無法防範中間人攻擊。',
              file=sys.stderr)
    else:
        s.mount('https://', RelaxedStrictAdapter())
    return s


def load_cache():
    if not CACHE_PATH.exists():
        return {'_version': CACHE_VERSION}
    try:
        raw = json.loads(CACHE_PATH.read_text(encoding='utf-8'))
    except json.JSONDecodeError:
        print('快取檔毀損，重新建立', file=sys.stderr)
        return {'_version': CACHE_VERSION}
    if raw.get('_version') != CACHE_VERSION:
        n = len([k for k in raw if not k.startswith('_')])
        bak = CACHE_PATH.with_suffix('.v1.bak.json')
        CACHE_PATH.replace(bak)
        print(f'偵測到舊版快取（{n} 筆，未經驗證），已備份為 {bak.name} 並全部重查')
        return {'_version': CACHE_VERSION}
    return raw


def save_cache(cache):
    CACHE_PATH.write_text(json.dumps(cache, ensure_ascii=False, indent=1),
                          encoding='utf-8')


def raw_query(session, addr, key):
    """單次查詢。回傳 (資料dict或None, 是否連線層失敗)。"""
    headers = {'Authorization': f'Bearer {key}'}
    for attempt in range(RETRY):
        try:
            r = session.get(API_URL, headers=headers,
                            params={'singleQueryStr': addr}, timeout=20)
        except requests.exceptions.SSLError as e:
            print(f'  TLS 錯誤: {str(e)[:150]}', file=sys.stderr)
            return None, True
        except requests.RequestException as e:
            print(f'  連線錯誤（第{attempt+1}次）: {str(e)[:110]}', file=sys.stderr)
            time.sleep(2 ** attempt)
            continue
        if r.status_code == 200:
            data = r.json()
            return (data[0] if isinstance(data, list) and data else {}), False
        if r.status_code in (401, 403):
            sys.exit(f'API 認證失敗（HTTP {r.status_code}）：'
                     f'MOI_API_KEY 可能無效或過期。\n{r.text[:200]}')
        if r.status_code == 429:
            time.sleep(5 * (attempt + 1))
            continue
        print(f'  HTTP {r.status_code}: {r.text[:90]}', file=sys.stderr)
        time.sleep(2 ** attempt)
    return None, True


def geocode_one(session, addr, town, key):
    """依序試候選寫法，回傳第一個通過驗證的結果。

    每個候選的**原始回應**都會保存在 raw 裡。驗證邏輯日後若修正，可直接
    對 raw 重跑（revalidate.py），不必再打一次 API。
    """
    cands, st = variants(addr, town)
    if st != 'ok':
        return {'status': st, 'raw': []}, False
    raw, reasons = [], []
    for cand in cands:
        data, failed = raw_query(session, cand, key)
        if failed:
            return {'status': 'error', 'raw': raw}, True
        entry = {'candidate': cand,
                 'x': (data or {}).get('x'), 'y': (data or {}).get('y'),
                 'address_id': (data or {}).get('addressId'),
                 'full_address': (data or {}).get('fullAddress') or ''}
        raw.append(entry)
        if not data:
            reasons.append(f'{cand}:no_result')
            time.sleep(DELAY_SEC)
            continue
        accepted, why = validate(cand, entry['full_address'], town)
        if accepted and entry['x'] and entry['y']:
            return {'status': 'ok', 'accepted_variant': cand,
                    'x': entry['x'], 'y': entry['y'],
                    'address_id': entry['address_id'],
                    'full_address': entry['full_address'], 'raw': raw}, False
        reasons.append(f'{cand}:{why if not accepted else "no_coords"}')
        time.sleep(DELAY_SEC)
    last = raw[-1] if raw else {}
    return {'status': 'rejected', 'reject_reason': ' | '.join(reasons),
            'full_address': last.get('full_address', ''),
            'x': last.get('x'), 'y': last.get('y'), 'raw': raw}, False


def write_output(rows, cache):
    cols = ['address', 'expected_town', 'status', 'accepted_variant', 'x', 'y',
            'address_id', 'full_address', 'reject_reason', 'raw_json']
    with open(OUT_PATH, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for addr, town in rows:
            c = dict(cache.get(addr, {'status': 'missing'}))
            c['address'], c['expected_town'] = addr, town
            c['raw_json'] = json.dumps(c.get('raw', []), ensure_ascii=False)
            w.writerow({k: c.get(k, '') for k in cols})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('csv_path', nargs='?', default='addresses_retry.csv')
    ap.add_argument('--test', action='store_true', help='只查一筆測試地址')
    ap.add_argument('--insecure', action='store_true', help='最後手段：停用憑證驗證')
    args = ap.parse_args()

    key = os.getenv('MOI_API_KEY')
    if not key:
        sys.exit('請先設定環境變數 MOI_API_KEY\n'
                 '  PowerShell: $env:MOI_API_KEY = "你的key"\n'
                 '  cmd:        set MOI_API_KEY=你的key')
    session = make_session(args.insecure)

    if args.test:
        print(f'測試查詢：{TEST_ADDRESS}')
        res, _ = geocode_one(session, TEST_ADDRESS, '彰化市', key)
        print(json.dumps(res, ensure_ascii=False, indent=1))
        if res.get('status') == 'ok':
            print('連線與 API key 正常。')
            return 0
        print('測試未成功；若為 TLS 錯誤可再試 --insecure。', file=sys.stderr)
        return 1

    with open(args.csv_path, encoding='utf-8-sig') as f:
        raw = list(csv.DictReader(f))
    pairs, seen = [], set()
    for r in raw:
        a = (r.get('address') or '').strip()
        if not a or a in seen:
            continue
        seen.add(a)
        t = (r.get('expected_town') or '').strip()
        if not t:
            m = TOWN_RE.search(a)
            t = m.group(1) if m else ''
        pairs.append((a, t))

    cache = load_cache()
    todo = [(a, t) for a, t in pairs
            if a not in cache or cache[a].get('status') in ('error',)]
    # '_version' 是結構標記，不是地址，不參與統計與輸出
    print(f'共 {len(pairs)} 個唯一地址，其中 {len(todo)} 個待查'
          f'（每筆最多嘗試 3 種寫法，回應會逐一驗證）')

    consecutive = 0
    try:
        for i, (addr, town) in enumerate(todo, 1):
            cache[addr], failed = geocode_one(session, addr, town, key)
            consecutive = consecutive + 1 if failed else 0
            if consecutive >= FAIL_FAST:
                save_cache(cache)
                sys.exit(f'\n連續 {FAIL_FAST} 筆連線失敗，已中止（進度已存檔）。\n'
                         f'先用 python geocode.py --test 診斷。')
            if i % 20 == 0 or i == len(todo):
                save_cache(cache)
                ok = sum(1 for a, _ in todo[:i] if cache[a].get('status') == 'ok')
                print(f'  進度 {i}/{len(todo)}（通過驗證 {ok}）')
    except KeyboardInterrupt:
        save_cache(cache)
        write_output(pairs, cache)
        print('\n已中斷，進度已存檔，重跑會自動接續。')
        return 130

    save_cache(cache)
    write_output(pairs, cache)
    from collections import Counter
    st = Counter(cache.get(a, {}).get('status', 'missing') for a, _ in pairs)
    st.pop('_version', None)
    print(f'完成，結果在 {OUT_PATH}')
    for k, v in st.most_common():
        print(f'   {k}: {v}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
