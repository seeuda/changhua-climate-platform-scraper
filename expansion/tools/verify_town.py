#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""以鄉鎮界檢核座標是否落在該點位登記的鄉鎮內。

縣範圍（bbox）攔不住配到隔壁鄉鎮的錯誤——內政部 API 就有 38 筆是這樣，
Google 地圖同樣可能發生。本工具用鄉鎮界做點在多邊形內判定，是比 bbox
嚴格一級的檢核。

⚠️ 使用前務必先跑 --calibrate。data-engine 的 changhua_towns.json 實測
與真實 WGS84 位置有約 3 公里的系統性東偏（見下），直接拿來檢核會產生
大量假警報（1,189 筆權威座標只有 49.5% 相符，東移 0.03° 後升到 98.2%）。
校準模式會偵測並回報偏移量，偏移過大時本工具拒絕給判定。

用法：
    # 檢核人工/Google 補的結果
    python verify_town.py unlocated_with_links.csv staging/changhua_towns.json
    # 檢核已併入的全部座標
    python verify_town.py --accepted staging

輸出每筆的判定：符合 / 落在他鄉鎮 / 不在任何鄉鎮內（縣界外或海上）。
"""
import argparse
import csv
import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from addr_util import TOWN_RE  # noqa: E402

PLACE_COORD = re.compile(r'!3d(-?\d+\.\d+)!4d(-?\d+\.\d+)')
VIEW_COORD = re.compile(r'@(-?\d+\.\d+),(-?\d+\.\d+)')


def load_towns(path):
    d = json.loads(Path(path).read_text(encoding='utf-8'))
    out = []
    for f in d['features']:
        name = (f['properties'].get('town_name')
                or f['properties'].get('TOWNNAME')
                or f['properties'].get('name'))
        geom = f['geometry']
        polys = geom['coordinates'] if geom['type'] == 'MultiPolygon' \
            else [geom['coordinates']]
        out.append((name, polys))
    return out


def point_in_ring(lon, lat, ring):
    """射線法。ring 為 [[lon, lat], ...]。"""
    inside = False
    n = len(ring)
    j = n - 1
    for i in range(n):
        xi, yi = ring[i][0], ring[i][1]
        xj, yj = ring[j][0], ring[j][1]
        if ((yi > lat) != (yj > lat)) and \
                (lon < (xj - xi) * (lat - yi) / ((yj - yi) or 1e-12) + xi):
            inside = not inside
        j = i
    return inside


def town_of(lon, lat, towns):
    """回傳座標所在鄉鎮名，不在任何鄉鎮內則 None。"""
    for name, polys in towns:
        for poly in polys:
            if not poly:
                continue
            if point_in_ring(lon, lat, poly[0]):
                # 扣掉內環（孔洞）
                if any(point_in_ring(lon, lat, hole) for hole in poly[1:]):
                    continue
                return name
    return None


def coords_from_row(r):
    for key in ('google_url',):
        u = r.get(key) or ''
        m = PLACE_COORD.search(u) or VIEW_COORD.search(u)
        if m:
            return float(m.group(1)), float(m.group(2))
    try:
        if r.get('lat') and r.get('lng'):
            return float(r['lat']), float(r['lng'])
    except ValueError:
        pass
    return None, None


def calibrate(towns, pts, label=''):
    """估算點位與鄉鎮界之間的系統性位移。

    回傳 (dlon, dlat, 位移後相符率, 未位移相符率)。點位需為
    [(lon, lat, 應屬鄉鎮), ...]。位移量顯著不為零，代表圖資有
    georeferencing 問題，不應拿來當判準。
    """
    def score(dlon, dlat):
        return sum(1 for lon, lat, w in pts
                   if town_of(lon + dlon, lat + dlat, towns) == w)
    base = score(0.0, 0.0)
    best, best_s = (0.0, 0.0), base
    for i in range(-8, 9):
        for j in range(-4, 5):
            dlon, dlat = round(i * 0.01, 3), round(j * 0.005, 4)
            s = score(dlon, dlat)
            if s > best_s:
                best, best_s = (dlon, dlat), s
    n = len(pts) or 1
    print(f'校準{label}：樣本 {n} 筆')
    print(f'   未位移相符 {base}/{n} ({100*base/n:.1f}%)')
    print(f'   最佳位移 dlon={best[0]:+.3f} dlat={best[1]:+.4f} → '
          f'{best_s}/{n} ({100*best_s/n:.1f}%)')
    if abs(best[0]) > 0.002 or abs(best[1]) > 0.002:
        print(f'   ⚠️ 鄉鎮界相對點位東偏約 {best[0]*101700:.0f} 公尺、'
              f'北偏約 {best[1]*111000:.0f} 公尺，圖資有 georeferencing 問題')
    return (*best, best_s / n, base / n)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('src')
    ap.add_argument('towns', nargs='?')
    ap.add_argument('--accepted', action='store_true',
                    help='src 視為 staging 目錄，檢核 geocode_accepted.json')
    ap.add_argument('--calibrate', action='store_true',
                    help='只估算鄉鎮界與點位的系統性位移，不做逐筆判定')
    ap.add_argument('--force', action='store_true',
                    help='偵測到圖資偏移時仍給出逐筆判定（結果不可信）')
    args = ap.parse_args()

    if args.accepted:
        staging = Path(args.src)
        towns = load_towns(args.towns or staging / 'changhua_towns.json')
        acc = json.loads((staging / 'geocode_accepted.json')
                         .read_text(encoding='utf-8'))
        items = []
        for addr, v in acc.items():
            m = TOWN_RE.search(addr)
            items.append((addr, m.group(1) if m else '', v['lat'], v['lon']))
    else:
        towns = load_towns(args.towns or 'changhua_towns.json')
        rows = list(csv.DictReader(open(args.src, encoding='utf-8-sig')))
        items = []
        for r in rows:
            lat, lon = coords_from_row(r)
            if lat is None:
                continue
            items.append((f"{r.get('id','')} {r.get('name','')}",
                          r.get('town') or '', lat, lon))

    # 先校準：圖資若有系統性偏移，逐筆判定會產生大量假警報
    ref = [(lon, lat, want) for _, want, lat, lon in items if want]
    if ref:
        dlon, dlat, fit, base = calibrate(towns, ref[:200],
                                          '（取前 200 筆）' if len(ref) > 200 else '')
        if args.calibrate:
            return
        if (abs(dlon) > 0.002 or abs(dlat) > 0.002) and not args.force:
            print('\n鄉鎮界與點位不在同一基準，逐筆判定不具意義，已中止。')
            print('請改用位置正確的鄉鎮界圖資（內政部原始檔），'
                  '或加 --force 強制輸出（結果不可信）。')
            return
    stat = Counter()
    problems = []
    for label, want, lat, lon in items:
        got = town_of(lon, lat, towns)
        if got is None:
            stat['不在任何鄉鎮內'] += 1
            problems.append((label, want, '(縣界外)', lat, lon))
        elif want and got != want:
            stat['落在他鄉鎮'] += 1
            problems.append((label, want, got, lat, lon))
        else:
            stat['符合'] += 1
    print(f'檢核 {len(items)} 筆座標')
    for k, v in stat.most_common():
        print(f'   {k}: {v}')
    if problems:
        print('\n=== 需人工確認 ===')
        for p in problems:
            print(f'   {p[0][:34]}  登記={p[1]}  實際={p[2]}  ({p[3]}, {p[4]})')


if __name__ == '__main__':
    main()
