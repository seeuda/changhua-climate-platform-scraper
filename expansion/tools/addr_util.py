# -*- coding: utf-8 -*-
"""地址正規化與地理編碼結果驗證。

內政部 query-single 是模糊比對：找不到精確門牌時會拿路名/號碼在全台
猜一個最像的回傳，且不附信心度。實測 1,395 筆有 96 筆配到別的鄉鎮甚至
別的縣市（例：彰化縣二水鄉上豐村山腳路113-5號 → 苗栗縣通霄鎮南和113之5號）。
因此**必須在收到回應時驗證**，不能直接採信。
"""
import re

TOWNS = ('彰化市', '鹿港鎮', '和美鎮', '線西鄉', '伸港鄉', '福興鄉', '秀水鄉',
         '花壇鄉', '芬園鄉', '員林市', '溪湖鎮', '田中鎮', '大村鄉', '埔鹽鄉',
         '埔心鄉', '永靖鄉', '社頭鄉', '二水鄉', '北斗鎮', '二林鎮', '田尾鄉',
         '埤頭鄉', '芳苑鄉', '大城鄉', '竹塘鄉', '溪州鄉')
TOWN_RE = re.compile('(' + '|'.join(TOWNS) + ')')
FULLWIDTH = str.maketrans('０１２３４５６７８９', '0123456789')
SEC_NUM = {'一': '1', '二': '2', '三': '3', '四': '4', '五': '5',
           '六': '6', '七': '7', '八': '8', '九': '9'}
# 常見異體字：地政資料與名冊寫法不一致，同一條路
VARIANT_CHARS = str.maketrans({'脚': '腳', '苳': '苳', '厝': '厝'})

NOT_ADDRESS = re.compile(r'^(無|同上|同會址|社區自行興建|待確認|-|—)$')
LANDMARK_ONLY = re.compile(r'(社區活動中心|活動中心|廣場|集會所)$')


def clean(addr, town=None):
    """正規化地址。回傳 (清理後地址, 狀態)。

    狀態：'ok' 可送查 / 'not_address' 非地址 / 'parcel' 地號（需另一支 API）。
    """
    if not addr or not addr.strip():
        return '', 'not_address'
    a = addr.strip().translate(FULLWIDTH)

    if '地號' in a:
        return '', 'parcel'

    a = a.replace('彰化縣', '')
    a = re.sub(r'^\d{3,5}', '', a)                       # 郵遞區號
    a = re.sub(r'^(公文|據點\d*|通訊地址|會址|地址)[^:：]{0,6}[:：]', '', a)
    a = re.sub(r'\d{1,3}鄰', '', a)                      # 鄰別
    a = re.sub(r'[（(]巷[）)]', '', a)                    # 「(巷)」佔位符
    # 重複鄉鎮前綴：彰化市彰化市… / 員林市員林市…
    while True:
        m = TOWN_RE.match(a)
        if m and TOWN_RE.match(a[len(m.group(1)):]) \
                and TOWN_RE.match(a[len(m.group(1)):]).group(1) == m.group(1):
            a = a[len(m.group(1)):]
        else:
            break

    core = a.strip()
    if NOT_ADDRESS.match(core) or LANDMARK_ONLY.search(core):
        return '', 'not_address'

    # 多門牌（一址跨兩戶，例：長壽街161、163號）→ 取第一個
    a = re.sub(r'(\d+)\s*[、,，]\s*\d+號', r'\1號', a)
    # 門牌數字間的異常符號（例：2'2號，輸入法誤觸）→ 先併成 22號，
    # 另一種讀法「2之2號」由 variants() 併送，交給門牌 API 裁決
    a = re.sub(r"(\d)['’‘`\"]+(\d)", r'\1\2', a)
    # 截到第一個「號」，剝除樓層／「旁」「對面」／括號註記
    m = re.search(r'^(.*?\d+(?:[之\-]\d+)?號(?:之\d+)?)', a)
    if m:
        a = m.group(1)
    a = re.sub(r'[（(][^）)]*[）)]', '', a)
    a = re.sub(r'\s+', '', a)
    a = re.sub(r'(\d+)-(\d+)號', r'\1之\2號', a)          # 破折號→之

    if not a or not re.search(r'\d', a) or '號' not in a:
        return '', 'not_address'
    if not TOWN_RE.match(a):
        a = (town or '') + a
    if not TOWN_RE.match(a):
        return '', 'not_address'
    return '彰化縣' + a, 'ok'


def variants(addr, town=None):
    """候選寫法，依序嘗試；第一個通過驗證的即採用。"""
    base, st = clean(addr, town)
    if st != 'ok':
        return [], st
    out = [base]
    # 去掉村里（村里與路名並存時 API 常失配）
    v = re.sub(r'^(彰化縣' + TOWN_RE.pattern + r')[^\d]{1,4}?[村里]', r'\1', base)
    if v != base and re.search(r'[路街巷道]', v):
        out.append(v)
    # 「之」還原成「-」
    if '之' in base:
        out.append(base.replace('之', '-'))
    # 原地址門牌含異常符號時，另備「N之N」讀法一併送查
    m = re.search(r"(\d)['’‘`\"]+(\d+)號", addr or '')
    if m:
        alt = re.sub(r'(\d+)號', f'{m.group(1)}之{m.group(2)}號', base, count=1)
        if alt != base:
            out.append(alt)
    return list(dict.fromkeys(out)), 'ok'


def _norm_for_compare(s):
    s = (s or '').translate(FULLWIDTH).translate(VARIANT_CHARS)
    s = re.sub(r'\d{1,3}鄰', '', s)
    s = s.replace('彰化縣', '')
    s = TOWN_RE.sub('', s)
    s = re.sub(r'[^\d路街巷道段號之]{1,4}[村里]', '', s)
    s = re.sub(r'([一二三四五六七八九])段',
               lambda m: SEC_NUM[m.group(1)] + '段', s)
    return s


def house_number(s):
    """取門牌號（含之N），用於比對。"""
    m = re.search(r'(\d+)(?:之(\d+))?號(?:之(\d+))?', _norm_for_compare(s))
    if not m:
        return None
    sub = m.group(2) or m.group(3)
    return (m.group(1), sub)


def road_names(s):
    return set(re.findall(r'([^\d\s]{1,6}?(?:路|街|巷|道))', _norm_for_compare(s)))


def validate(requested, full_address, expected_town=None):
    """驗證 API 回傳是否可信。回傳 (是否接受, 原因)。"""
    if not full_address:
        return False, 'no_full_address'
    if not full_address.startswith('彰化縣'):
        return False, 'wrong_county'
    want = expected_town or (TOWN_RE.search(requested).group(1)
                             if TOWN_RE.search(requested) else None)
    got = TOWN_RE.search(full_address)
    if want and got and want != got.group(1):
        return False, f'wrong_town:{got.group(1)}'
    hn_a, hn_b = house_number(requested), house_number(full_address)
    if hn_a and hn_b and hn_a != hn_b:
        return False, 'house_number_mismatch'
    ra, rb = road_names(requested), road_names(full_address)
    if ra and rb and not (ra & rb):
        return False, 'road_mismatch'
    return True, 'ok'


def in_changhua(lon, lat):
    return 120.22 <= lon <= 120.80 and 23.72 <= lat <= 24.22
