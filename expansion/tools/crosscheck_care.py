#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""以社區發展協會名冊（m6）交叉校驗關懷據點名冊（m7）的地址。

背景：關懷據點名冊的「住址」欄有整格錯位的情形——地址被填成鄰列協會的
地點。已確認案例：

    序號348 田尾鄉溪畔村 溪畔社區發展協會
      名冊寫：據點：田中鎮大社里大社路二段649號
      實際上：田尾鄉溪畔村溪畔巷101弄4號（協會名冊）
      佐證：該列聯絡人「黃進添」正是協會名冊裡溪畔社區的理事長；
            名冊誤植的 649 號與大社社區活動中心 647 號僅差兩號。

判定準則：**地址所在鄉鎮與該列登記鄉鎮不同**才視為可疑。單純「據點地址
與活動中心不同街」很常見（據點常借用廟宇、民宅、學校），不算錯誤。

用法：
    python crosscheck_care.py <staging目錄>
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from addr_util import TOWN_RE  # noqa: E402


def main():
    staging = Path(sys.argv[1] if len(sys.argv) > 1 else 'staging')
    care_path = staging / 'care_station_records.json'
    care = json.loads(care_path.read_text(encoding='utf-8'))
    assoc = json.loads((staging / 'community_assoc_records.json')
                       .read_text(encoding='utf-8'))['records']
    idx = {(a['town'], a['community']): a for a in assoc if a.get('address')}

    fixed, flagged = [], []
    for c in care['records']:
        m = TOWN_RE.search(c.get('address') or '')
        if not m or m.group(1) == c['town']:
            continue                      # 同鄉鎮，正常
        name_m = re.match(r'^(.+?)社區發展協會$', c['name'])
        ref = idx.get((c['town'], name_m.group(1))) if name_m else None
        c['address_original'] = c['address']
        c['address_conflict_note'] = (
            f"名冊住址欄為 {m.group(1)}，與登記鄉鎮 {c['town']} 不符；"
            f"疑為來源名冊整格錯位")
        if ref and TOWN_RE.search(ref['address']) \
                and TOWN_RE.search(ref['address']).group(1) == c['town']:
            c['address'] = ref['address']
            c['address_source'] = '社區發展協會名冊（活動中心）'
            c['needs_review'] = True
            fixed.append((c['id'], c['name'], c['address_original'], c['address']))
        else:
            c['needs_manual_address'] = True
            c['needs_review'] = True
            flagged.append((c['id'], c['name'], c['address_original']))

    care.setdefault('crosscheck', {})
    care['crosscheck'] = {
        'rule': '住址欄鄉鎮 ≠ 登記鄉鎮者視為可疑，優先採用協會名冊的活動中心地址',
        'corrected': len(fixed), 'manual_needed': len(flagged)}
    care_path.write_text(json.dumps(care, ensure_ascii=False, indent=1),
                         encoding='utf-8')

    print(f'已修正 {len(fixed)} 筆（改用協會名冊活動中心地址）：')
    for f in fixed:
        print(f'  {f[0]} {f[1]}\n      原: {f[2]}\n      新: {f[3]}')
    print(f'\n無可用替代地址、需人工補 {len(flagged)} 筆：')
    for f in flagged:
        print(f'  {f[0]} {f[1]}  (名冊寫: {f[2]})')


if __name__ == '__main__':
    main()
