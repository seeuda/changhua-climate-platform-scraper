#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""以現行驗證規則重跑 geocode.py 的原始回應，不需再打 API。

geocode.py 自快取 v3 起會把每個候選寫法的原始回應存進 raw_json 欄，
因此驗證規則修正後可直接離線重判，省去整輪重查。

用法：
    python revalidate.py geocoded_addresses.csv [輸出.csv]
"""
import csv
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from addr_util import TOWN_RE, in_changhua, validate  # noqa: E402
from merge_geocoded import twd97_to_wgs84  # noqa: E402


def revalidate_row(row):
    """回傳 (status, 採用的候選, x, y, full_address, 原因)。"""
    try:
        raw = json.loads(row.get('raw_json') or '[]')
    except json.JSONDecodeError:
        raw = []
    town = row.get('expected_town') or ''
    if not town:
        m = TOWN_RE.search(row['address'])
        town = m.group(1) if m else ''
    if not raw:                       # 舊格式沒有 raw，維持原判定
        return row['status'], row.get('accepted_variant', ''), row.get('x', ''), \
            row.get('y', ''), row.get('full_address', ''), 'no_raw'
    reasons = []
    for e in raw:
        cand, full = e.get('candidate', ''), e.get('full_address') or ''
        x, y = e.get('x'), e.get('y')
        if not x or not y:
            reasons.append(f'{cand}:no_coords')
            continue
        ok, why = validate(cand, full, town)
        if ok:
            return 'ok', cand, x, y, full, 'ok'
        reasons.append(f'{cand}:{why}')
    # 沒有 full_address 但座標落在彰化縣內：位置可用、門牌無法核對
    for e in raw:
        x, y = e.get('x'), e.get('y')
        if x and y and not (e.get('full_address') or ''):
            lon, lat = twd97_to_wgs84(float(x), float(y))
            if in_changhua(lon, lat):
                return 'ok_unverified', e.get('candidate', ''), x, y, '', \
                    '無 full_address 可核對，但座標落在彰化縣內'
    return 'rejected', '', '', '', (raw[-1].get('full_address') or ''), \
        ' | '.join(reasons)


def main():
    src = Path(sys.argv[1] if len(sys.argv) > 1 else 'geocoded_addresses.csv')
    dst = Path(sys.argv[2] if len(sys.argv) > 2 else 'geocoded_revalidated.csv')
    rows = list(csv.DictReader(open(src, encoding='utf-8-sig')))
    before = Counter(r['status'] for r in rows)
    out, after = [], Counter()
    for r in rows:
        st, cand, x, y, full, why = revalidate_row(r)
        after[st] += 1
        out.append({'address': r['address'], 'expected_town': r.get('expected_town', ''),
                    'status': st, 'accepted_variant': cand, 'x': x, 'y': y,
                    'address_id': r.get('address_id', ''), 'full_address': full,
                    'reject_reason': why})
    with open(dst, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(out[0].keys()))
        w.writeheader()
        w.writerows(out)
    print(f'重判前: {dict(before)}')
    print(f'重判後: {dict(after)}')
    print(f'結果寫入 {dst}')


if __name__ == '__main__':
    main()
