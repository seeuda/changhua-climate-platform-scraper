#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""從內政部全國村里界 GeoJSON 篩出彰化縣水患自主防災社區 21 村里。

用法：
    python extract_villages.py 全國村里界.geojson flood_resilient_villages.json

村里界下載（需在本機，政府網站擋雲端 IP）：
    data.gov.tw 資料集「村(里)界 (TWD97經緯度)」，下載 GeoJSON 版
    （若只有 SHP，可先用 QGIS 或 ogr2ogr 轉 GeoJSON / WGS84）。
屬性欄位名稱依內政部慣例：COUNTYNAME / TOWNNAME / VILLNAME。
"""
import json
import sys
from pathlib import Path

TARGET = {
    '大城鄉': ['東城村', '東港村', '西港村', '潭墘村'],
    '芳苑鄉': ['崙腳村', '新生村', '永興村', '漢寶村'],
    '永靖鄉': ['五福村', '港西村'],
    '員林市': ['新生里'],
    '鹿港鎮': ['洋厝里', '頭南里'],
    '二林鎮': ['華崙里'],
    '埔鹽鄉': ['埔南村', '廍子村'],
    '溪湖鎮': ['西勢里', '湖東里'],
    '伸港鄉': ['海尾村'],
    '福興鄉': ['福寶村', '橋頭村'],
}
COMMUNITIES = {('大城鄉', '潭墘村'): ['潭墘社區', '尤士社區']}


def main():
    src = Path(sys.argv[1])
    dst = Path(sys.argv[2] if len(sys.argv) > 2 else 'flood_resilient_villages.json')
    data = json.loads(src.read_text(encoding='utf-8'))
    feats = []
    for f in data['features']:
        p = f['properties']
        town = p.get('TOWNNAME') or p.get('townname') or ''
        vill = p.get('VILLNAME') or p.get('villname') or ''
        county = p.get('COUNTYNAME') or p.get('countyname') or ''
        if county == '彰化縣' and vill in TARGET.get(town, []):
            comms = COMMUNITIES.get((town, vill), [f'{vill[:-1]}社區'])
            feats.append({'type': 'Feature', 'geometry': f['geometry'],
                          'properties': {'town': town, 'village': vill,
                                         'communities': comms,
                                         'category': '水患自主防災社區'}})
    expect = sum(len(v) for v in TARGET.values())
    found = {(f['properties']['town'], f['properties']['village']) for f in feats}
    missing = [(t, v) for t, vs in TARGET.items() for v in vs if (t, v) not in found]
    out = {'type': 'FeatureCollection',
           'metadata': {'source': '彰化縣水患自主防災社區（村里界：內政部）',
                        'expected': expect, 'found': len(feats), 'missing': missing},
           'features': feats}
    dst.write_text(json.dumps(out, ensure_ascii=False), encoding='utf-8')
    print(f'{len(feats)}/{expect} 村里，缺漏: {missing or "無"}')


if __name__ == '__main__':
    main()
