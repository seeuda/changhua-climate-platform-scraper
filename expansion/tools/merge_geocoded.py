#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""將 geocode.py 的結果併回各資料集，輸出前端可用的 GeoJSON。

用法：
    python merge_geocoded.py <staging目錄> <geocoded_addresses.csv> <輸出目錄>

座標系自動判斷：|x|<=180 視為 WGS84 經緯度直接使用；否則視為
TWD97 TM2（EPSG:3826）以內建公式轉 WGS84，並保留 source_x/source_y/
source_crs 溯源欄（沿用 disabled_welfare_facilities.json 的慣例）。
"""
import csv
import json
import math
import sys
from pathlib import Path

DATASETS = {
    'shelter_records.json': 'shelters_points.json',
    'relief_station_records.json': 'relief_stations_points.json',
    'care_station_records.json': 'care_stations_points.json',
    'community_assoc_records.json': 'community_assoc_points.json',
    'infant_care_records.json': 'infant_care_points.json',
    'early_intervention_records.json': 'early_intervention_points.json',
}


def twd97_to_wgs84(x, y):
    """EPSG:3826 → WGS84（GRS80 橫麥卡托反算，中央經線 121°、k0=0.9999、假東距 250km）。"""
    a, f = 6378137.0, 1 / 298.257222101
    k0, dx, lon0 = 0.9999, 250000.0, math.radians(121.0)
    e2 = 2 * f - f * f
    e1 = (1 - math.sqrt(1 - e2)) / (1 + math.sqrt(1 - e2))
    M = y / k0
    mu = M / (a * (1 - e2 / 4 - 3 * e2 ** 2 / 64 - 5 * e2 ** 3 / 256))
    p1 = mu + (3 * e1 / 2 - 27 * e1 ** 3 / 32) * math.sin(2 * mu) \
        + (21 * e1 ** 2 / 16 - 55 * e1 ** 4 / 32) * math.sin(4 * mu) \
        + (151 * e1 ** 3 / 96) * math.sin(6 * mu) \
        + (1097 * e1 ** 4 / 512) * math.sin(8 * mu)
    ep2 = e2 / (1 - e2)
    C1 = ep2 * math.cos(p1) ** 2
    T1 = math.tan(p1) ** 2
    N1 = a / math.sqrt(1 - e2 * math.sin(p1) ** 2)
    R1 = a * (1 - e2) / (1 - e2 * math.sin(p1) ** 2) ** 1.5
    D = (x - dx) / (N1 * k0)
    lat = p1 - (N1 * math.tan(p1) / R1) * (
        D ** 2 / 2
        - (5 + 3 * T1 + 10 * C1 - 4 * C1 ** 2 - 9 * ep2) * D ** 4 / 24
        + (61 + 90 * T1 + 298 * C1 + 45 * T1 ** 2 - 252 * ep2 - 3 * C1 ** 2) * D ** 6 / 720)
    lon = lon0 + (D - (1 + 2 * T1 + C1) * D ** 3 / 6
                  + (5 - 2 * C1 + 28 * T1 - 3 * C1 ** 2 + 8 * ep2 + 24 * T1 ** 2) * D ** 5 / 120) / math.cos(p1)
    return math.degrees(lon), math.degrees(lat)


def main():
    staging = Path(sys.argv[1] if len(sys.argv) > 1 else 'staging')
    geocoded_csv = Path(sys.argv[2] if len(sys.argv) > 2 else 'geocoded_addresses.csv')
    outdir = Path(sys.argv[3] if len(sys.argv) > 3 else 'geojson_out')
    outdir.mkdir(parents=True, exist_ok=True)

    coords = {}
    with open(geocoded_csv, encoding='utf-8-sig') as f:
        for row in csv.DictReader(f):
            if row['status'] == 'ok' and row['x'] and row['y']:
                coords[row['address']] = (float(row['x']), float(row['y']),
                                          row.get('full_address') or '')

    for src, dst in DATASETS.items():
        path = staging / src
        if not path.exists():
            print(f'略過 {src}（不存在）')
            continue
        d = json.loads(path.read_text(encoding='utf-8'))
        feats, misses = [], []
        for r in d['records']:
            addr = r.get('address') or ''
            hit = coords.get(addr)
            if not hit:
                misses.append(r.get('id'))
                continue
            x, y, full = hit
            props = {k: v for k, v in r.items() if k != 'seq'}
            if abs(x) <= 180:
                lon, lat = x, y
            else:
                lon, lat = twd97_to_wgs84(x, y)
                props.update(source_x=x, source_y=y,
                             source_crs='TWD97 / TM2 zone 121 (EPSG:3826)')
            props['geocoded_full_address'] = full or None
            props['coordinate_review_status'] = 'pending_review'
            feats.append({'type': 'Feature',
                          'geometry': {'type': 'Point', 'coordinates': [round(lon, 6), round(lat, 6)]},
                          'properties': props})
        out = {'type': 'FeatureCollection',
               'metadata': {'source': d.get('source'),
                            'pii_removed': d.get('pii_removed'),
                            'total_records': len(d['records']),
                            'geocoded': len(feats),
                            'geocode_missing_ids': misses},
               'features': feats}
        (outdir / dst).write_text(json.dumps(out, ensure_ascii=False, indent=1),
                                  encoding='utf-8')
        print(f'{dst}: {len(feats)}/{len(d["records"])} 筆成功定位'
              + (f'，未定位 {len(misses)} 筆' if misses else ''))


if __name__ == '__main__':
    main()
