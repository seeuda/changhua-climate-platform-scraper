#!/usr/bin/env python3
"""One-shot autopilot: discover the data source, scrape all metadata,
and (optionally) download everything — in a single local run.

    python autopilot.py            # metadata only
    python autopilot.py --full     # metadata + download + all views

Strategy, fully automatic:
  1. Fetch the page. If it already contains File/Get links, use them.
  2. Otherwise discover the AJAX API: decode hidden config inputs, read
     the API base from apiurl.js, mine every external script for
     endpoint paths, add pattern-based guesses (the known File URL is
     {base}/File/Get/cca/zh-tw/<token>, so list endpoints likely follow
     {base}/{Controller}/{Action}/cca/zh-tw/...), then try candidates
     with GET/POST × several parameter shapes.
  3. A response counts as a hit if it yields File/Get URLs — whether it
     is JSON or a rendered HTML fragment (both are handled).
  4. Page through the working endpoint, build documents, classify, and
     write CSV/JSON/report.

Everything is logged to autopilot.log — if the run fails, paste that
single file back to the developer.
"""

import argparse
import html as html_mod
import json
import logging
import re
import sys
from pathlib import Path
from urllib.parse import urljoin

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from bs4 import BeautifulSoup  # noqa: E402

from http_client import make_session  # noqa: E402
from rate_limiter import GLOBAL_RATE_LIMITER  # noqa: E402
from scraper import ClimateDocumentScraper  # noqa: E402
from output_formatter import DocumentOutputFormatter  # noqa: E402
from report_generator import ReportGenerator  # noqa: E402

BASE = 'https://www.cca.gov.tw'
PAGE_URL = f'{BASE}/information-service/info/2095.html'
API_BASE = 'https://service.cca.gov.tw'
DATA_DIR = Path('data')
MAX_PROBE_REQUESTS = 40
MAX_PAGES = 60

# Confirmed from apifun.js on the real site:
#   var Url = GetApiUrl().concat("/WebAPI/WebsiteList/NewsList");
#   d = {...QueryData, MainSN: parseInt(key), p: parseInt(p), dc: parseInt(dc)}
#   $.ajax({url: Url, method:'POST', contentType:'application/json',
#           dataType:'html', data: JSON.stringify(d), ...})
# The response is a rendered HTML list fragment containing File/Get links.
KNOWN_ENDPOINT = API_BASE + '/WebAPI/WebsiteList/NewsList'

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.FileHandler('autopilot.log', mode='w', encoding='utf-8'),
              logging.StreamHandler()])
log = logging.getLogger('autopilot')

session = make_session()
session.headers.update({'Referer': PAGE_URL})
FILE_RE = re.compile(r'https?://[^"\'\s\\]+/File/Get/[^"\'\s\\]+|/File/Get/[^"\'\s\\]+')

TITLE_KEYS = ['Title', 'Subject', 'Name', 'InfoTitle', 'ItemTitle', 'title']
DATE_KEYS = ['PublishDate', 'PostDate', 'StartDate', 'Date', 'UpdateTime',
             'CreateDate', 'publishDate']
UNIT_KEYS = ['Unit', 'UnitName', 'Org', 'OrgName', 'Dept', 'County', 'City',
             'Place', 'Area', 'Publisher']


def polite(method, url, **kw):
    GLOBAL_RATE_LIMITER.acquire()
    fn = session.get if method == 'GET' else session.post
    resp = fn(url, timeout=15, **kw)
    resp.encoding = 'utf-8'  # server may omit charset; avoid mojibake
    return resp


def file_urls_in(text: str):
    urls = []
    for u in FILE_RE.findall(text):
        u = u.replace('\\/', '/')
        if u.startswith('/'):
            u = API_BASE + u
        if u not in urls:
            urls.append(u)
    return urls


# ----------------------------------------------------------------------
# Step 1: page fetch + static extraction
# ----------------------------------------------------------------------

def fetch_main_page():
    scraper = ClimateDocumentScraper()
    resp = scraper.fetch_page(PAGE_URL)
    if not resp:
        log.error("Cannot fetch the main page — see errors above")
        return None, scraper
    scraper.save_snapshot('page_1.html', resp.text)
    return resp.text, scraper


# ----------------------------------------------------------------------
# Step 2: endpoint discovery
# ----------------------------------------------------------------------

def discover_candidates(page_html: str):
    soup = BeautifulSoup(page_html, 'html.parser')

    sqn = '2095'
    sqn_input = soup.find('input', {'id': 'sqn'})
    if sqn_input and sqn_input.get('value'):
        sqn = sqn_input['value'].strip()
    log.info(f"page sqn = {sqn}")

    config_names = set()
    for inp in soup.find_all('input', {'type': 'hidden'}):
        value = html_mod.unescape(inp.get('value', '') or '')
        if value.startswith(('[', '{')):
            log.info(f"hidden config ({inp.get('id') or 'no-id'}): {value[:2000]}")
            for name in re.findall(r'"P?Name"\s*:\s*"([A-Za-z]\w+)"', value):
                config_names.add(name)
            for path in re.findall(r'"(/[A-Za-z][\w/.-]{2,80})"', value):
                config_names.add(path)
    log.info(f"config names/paths: {sorted(config_names)}")

    # QueryData template from the page
    query_template = {}
    m = re.search(r"QueryData\s*=\s*JSON\.parse\('([^']+)'\)", page_html)
    if m:
        try:
            query_template = json.loads(m.group(1).replace('\\/', '/')
                                        .replace('\\"', '"'))
        except ValueError:
            pass
    log.info(f"QueryData template keys: {list(query_template)}")

    # mine every external script
    paths = set()
    for s in soup.find_all('script', src=True):
        url = urljoin(PAGE_URL, s['src'])
        name = Path(s['src'].split('?')[0]).name
        try:
            resp = polite('GET', url)
        except Exception as e:
            log.warning(f"script {name}: fetch failed {e}")
            continue
        if resp.status_code != 200:
            continue
        text = resp.text
        DATA_DIR.mkdir(exist_ok=True)
        (DATA_DIR / name).write_text(text, encoding='utf-8')
        found = set(re.findall(r'''["'](/[A-Za-z][\w/.-]{2,80})["']''', text))
        api_found = {p for p in found if re.search(
            r'api|list|query|get|search|info', p, re.IGNORECASE)}
        if api_found:
            log.info(f"script {name}: paths {sorted(api_found)}")
        paths.update(api_found)
        for kw in ['service.cca', 'apiurl', 'QueryData', '.ajax', 'fetch(']:
            i = text.find(kw)
            if i >= 0:
                window = ' '.join(text[max(0, i - 150):i + 300].split())
                log.info(f"script {name} [{kw}]: …{window[:350]}…")

    # pattern guesses modeled on the known File URL shape
    guesses = []
    controllers = ['Info', 'InfoList', 'News', 'Query', 'Search', 'List'] + \
        [n for n in config_names if not n.startswith('/')]
    for c in controllers:
        for action in ['GetList', 'Get', 'List', 'Query', 'Search']:
            guesses.append(f'/{c}/{action}/cca/zh-tw/{sqn}')
            guesses.append(f'/{c}/{action}/cca/zh-tw')
            guesses.append(f'/api/{c}/{action}')
    candidates = [p for p in sorted(paths) if not p.endswith(
        ('.js', '.css', '.html', '.png', '.jpg'))] + guesses

    return sqn, query_template, candidates


def build_body(sqn, cga='all', p=1, dc=60):
    """Exact request body reverse-engineered from SearchData()/SearchAjax()
    in apifun.js and the page's default form state.

    Every filter must be its default 'everything selected' value — empty
    strings and nulls mean 'match nothing' server-side, which is why
    earlier attempts got 查無任何資訊. Lang must be a string (null gives
    HTTP 500) and dc must be one of the whitelisted page sizes
    (15/30/45/60 — dc=500 also gives HTTP 500).
    """
    return {
        'MainSN': int(sqn), 'Lang': 'zh-tw', 'q': '',
        'c4': '', 'c5': '', 'c6': '', 'ct': '', 'zc': '', 'mc': '',
        'p': p, 'dc': dc,
        'cga': cga,          # all | ClimateGovernanceCentral | ClimateGovernancePlace
        'cgp': '', 'cgac': '',
        'gt': 'GT1,GT2',     # 溫室氣體減量 + 氣候變遷調適
        'cgd': 'all',        # 部門 D1-D6
        'cgf': 'all',        # 調適類別 F1-F9
        'cgr': 'all',        # 報告類型 R1-R7
        'cgs': 'S1,S2,S3',   # 進度狀態
        'cgys': '', 'cgye': '',
        'bilingualkeyword': '',
    }


def try_known_endpoint(sqn, query_template):
    """POST the exact default-search body to the NewsList endpoint.

    A hit is a 200 whose body contains either direct File/Get links or
    方案成果 rows linking to detail pages (the actual production shape)."""
    for dc in (60, 15):
        body = build_body(sqn, dc=dc)
        try:
            resp = polite('POST', KNOWN_ENDPOINT, json=body)
        except Exception as e:
            log.warning(f"known endpoint failed: {e}")
            continue
        urls = file_urls_in(resp.text)
        details = len(set(DETAIL_RE.findall(resp.text)))
        log.info(f"POST NewsList cga=all dc={dc} -> HTTP "
                 f"{resp.status_code}, {len(resp.text):,}B, "
                 f"{len(urls)} File/Get urls, {details} detail links")
        (DATA_DIR / 'newslist_p1.html').write_text(resp.text,
                                                   encoding='utf-8')
        if resp.status_code == 200 and (urls or details):
            log.info("HIT on known endpoint")
            return KNOWN_ENDPOINT, 'POST', 'known', body, resp
        log.info(f"response head: {resp.text[:300]!r}")
    return None


def try_candidates(sqn, query_template, candidates):
    """Return (url, method, params_style, first_response_docs) or None."""
    base_query = dict(query_template) if query_template else {}
    base_query.update({'MainSN': sqn, 'p': 1})
    param_variants = [
        ('query-sqn', {'sqn': sqn, 'p': 1}),
        ('querydata', base_query),
    ]
    attempts = 0
    for path in candidates:
        url = path if path.startswith('http') else API_BASE + path
        for method in ('GET', 'POST'):
            for style, params in param_variants:
                if attempts >= MAX_PROBE_REQUESTS:
                    log.warning("probe request budget exhausted")
                    return None
                attempts += 1
                try:
                    kw = {'params': params} if method == 'GET' else \
                        {'json': params}
                    resp = polite(method, url, **kw)
                except Exception as e:
                    log.info(f"{method} {url} [{style}] -> error {e}")
                    continue
                text = resp.text
                urls = file_urls_in(text)
                log.info(f"{method} {url} [{style}] -> HTTP "
                         f"{resp.status_code}, {len(text):,}B, "
                         f"{len(urls)} File/Get urls")
                if resp.status_code == 200 and urls:
                    log.info(f"HIT: {method} {url} [{style}]")
                    log.info(f"response head: {text[:600]!r}")
                    return url, method, style, params, resp
    return None


# ----------------------------------------------------------------------
# Step 3: harvest all pages from the working endpoint
# ----------------------------------------------------------------------

def docs_from_payload(text: str, scraper: ClimateDocumentScraper):
    """Build document dicts from a JSON or HTML payload."""
    try:
        data = json.loads(text)
    except ValueError:
        # HTML fragment rendered by the service host: resolve relative
        # links against it, not against the www page.
        return scraper.extract_documents(text, API_BASE + '/')

    # JSON: find the item list anywhere in the structure
    items = None
    if isinstance(data, list):
        items = data
    elif isinstance(data, dict):
        for v in data.values():
            if isinstance(v, list) and v and isinstance(v[0], dict):
                items = v
                break
    if items is None:
        items = []

    docs = []
    for item in items:
        blob = json.dumps(item, ensure_ascii=False)
        urls = file_urls_in(blob)
        title = next((str(item[k]) for k in TITLE_KEYS if item.get(k)), '')
        date_raw = next((str(item[k]) for k in DATE_KEYS if item.get(k)), '')
        unit = next((str(item[k]) for k in UNIT_KEYS if item.get(k)), '')
        for u in urls:
            row_text = f"{title} {unit} {date_raw}"
            doc = {
                'title': title or u,
                'type': scraper.classify_type(title, blob),
                'category': '',
                'organization': (unit if unit else
                                 scraper.classify_organization(title, blob)),
                'org_type': '', 'county': '',
                'publish_date': scraper.find_date(date_raw) or
                                scraper.find_date(blob),
                'status': '已公開',
                'download_url': u,
                'file_format': '', 'file_size': '',
                'raw_item': item,
            }
            docs.append(doc)
    return docs


def finalize_org(doc, scraper):
    org = doc.get('organization') or ''
    norm = scraper.classify_organization(org or doc.get('title', ''), '')
    if norm != '未識別':
        doc['organization'] = norm
    doc['org_type'] = ('地方政府' if str(doc['organization']).endswith('政府')
                       else '中央部會' if doc['organization'] != '未識別'
                       else '未識別')
    doc['county'] = (doc['organization'].replace('政府', '')
                     if doc['org_type'] == '地方政府' else '中央')


# Detail-page links inside 方案成果 rows: /information-service/info/13445.html
# or /information-service/publications/<slug>/34874.html. Exclude /events/
# (that pattern belongs to the meetings table on the same page).
DETAIL_RE = re.compile(r'/information-service/(?!events)[\w/-]*?(\d+)\.html')


def stub_docs_from_fragment(text, scraper):
    """Parse 方案成果 rows: div[role=row] with data-title cells
    (項次/報告名稱/類型/報告/進度/公開年度) linking to a detail page."""
    soup = BeautifulSoup(text, 'html.parser')
    stubs, seen = [], set()
    for a in soup.find_all('a', href=True):
        if not DETAIL_RE.search(a['href']):
            continue
        url = urljoin(BASE + '/', a['href'])
        if url in seen:
            continue
        seen.add(url)

        row = (a.find_parent(attrs={'role': 'row'})
               or a.find_parent(['tr', 'li']) or a.parent)
        cells = {}
        if row:
            for cell in row.find_all(attrs={'data-title': True}):
                cells[cell['data-title']] = cell.get_text(' ', strip=True)

        year = ''
        m = re.search(r'\d{2,4}', cells.get('公開年度', ''))
        if m:
            y = int(m.group(0))
            year = str(y + 1911 if y < 1000 else y)

        title_guess = cells.get('報告名稱') or scraper.derive_title(a, row)
        stubs.append({
            'title': title_guess,
            'detail_url': url,
            'row_text': row.get_text(' ', strip=True) if row else '',
            'category': cells.get('類型', ''),   # 溫室氣體減量 / 氣候變遷調適
            'rtype': cells.get('報告', ''),      # 清冊 / 設立/方案 / 成果報告…
            'status': cells.get('進度', ''),     # 已核定…
            'unit': cells.get('主辦單位', ''),
            'year': year,
            'has_cells': bool(cells),
        })

    # Sidebar/nav anchors also match DETAIL_RE but sit outside the
    # data-title table rows. When genuine table rows exist in this
    # fragment, everything without cells is navigation noise.
    if any(st['has_cells'] for st in stubs):
        stubs = [st for st in stubs if st['has_cells']]
    return stubs


def harvest(url, method, param_sets, first_resp, scraper):
    """Page through every parameter set, dedupe by download URL, and —
    when rows link to detail pages rather than files — fetch each detail
    page and extract its attachments."""
    all_docs, seen, stubs, seen_detail = [], set(), [], set()

    def absorb(text):
        new = 0
        payload_docs = docs_from_payload(text, scraper)
        for doc in payload_docs:
            key = doc['download_url']
            if key not in seen:
                seen.add(key)
                all_docs.append(doc)
                new += 1
        if not payload_docs:
            for stub in stub_docs_from_fragment(text, scraper):
                if stub['detail_url'] not in seen_detail:
                    seen_detail.add(stub['detail_url'])
                    stubs.append(stub)
                    new += 1
        return new

    for set_no, base_params in enumerate(param_sets, 1):
        for page in range(1, MAX_PAGES + 1):
            if set_no == 1 and page == 1:
                text = first_resp.text
            else:
                p = dict(base_params)
                p['p'] = page
                try:
                    kw = {'params': p} if method == 'GET' else {'json': p}
                    resp = polite(method, url, **kw)
                except Exception as e:
                    log.warning(f"set {set_no} page {page} failed: {e}")
                    break
                if resp.status_code != 200:
                    log.info(f"set {set_no} page {page}: "
                             f"HTTP {resp.status_code}, stopping set")
                    break
                text = resp.text
            new = absorb(text)
            log.info(f"set {set_no} page {page}: +{new} "
                     f"(files {len(all_docs)}, detail-links {len(stubs)})")
            if new == 0:
                break

    if stubs:
        eta = len(stubs) * GLOBAL_RATE_LIMITER.min_interval / 60
        log.info(f"Rows link to {len(stubs)} detail pages; "
                 f"fetching each (~{eta:.0f} min)...")
        for i, stub in enumerate(stubs, 1):
            try:
                resp = polite('GET', stub['detail_url'])
            except Exception as e:
                log.warning(f"detail {stub['detail_url']}: {e}")
                continue
            if resp.status_code != 200:
                continue
            found = 0
            for doc in scraper.extract_documents(resp.text,
                                                 stub['detail_url']):
                key = doc['download_url']
                if key in seen:
                    continue
                seen.add(key)
                # The list row carries authoritative metadata the
                # attachment anchor lacks — prefer it.
                if len(doc.get('title', '')) < 8 <= len(stub['title']):
                    doc['title'] = stub['title']
                doc['list_title'] = stub['title']
                if stub.get('category'):
                    doc['category'] = stub['category']
                if stub.get('rtype'):
                    doc['type'] = stub['rtype']
                if stub.get('status'):
                    doc['status'] = stub['status']
                if not doc.get('publish_date'):
                    # The 公開年度 cell is authoritative; row-text date
                    # parsing can misfire on period ranges like 115-119年
                    doc['publish_date'] = (stub.get('year', '')
                                           or scraper.find_date(stub['row_text']))
                if doc.get('organization') == '未識別':
                    org = scraper.classify_organization(
                        stub.get('unit', '') + ' ' + stub['title'], '')
                    if org != '未識別':
                        doc['organization'] = org
                doc['detail_url'] = stub['detail_url']
                all_docs.append(doc)
                found += 1
            log.info(f"detail {i}/{len(stubs)}: +{found} files "
                     f"({stub['title'][:40]})")

    for idx, doc in enumerate(all_docs, 1):
        doc['id'] = idx
        finalize_org(doc, scraper)
        doc.pop('raw_item', None)
    return all_docs


# ----------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--full', action='store_true',
                        help='after metadata, also download everything and '
                             'build all classification views')
    parser.add_argument('--probe-files', action='store_true',
                        help='HEAD each file for real format/size')
    args = parser.parse_args()

    log.info("=" * 60)
    log.info("AUTOPILOT START")
    log.info("=" * 60)

    page_html, scraper = fetch_main_page()
    if page_html is None:
        return 1

    docs = scraper.extract_documents(page_html, PAGE_URL)
    if docs:
        log.info(f"Static page already contains {len(docs)} documents")
    else:
        log.info("No static File/Get links; using the NewsList API")
        sqn, query_template, candidates = discover_candidates(page_html)
        hit = try_known_endpoint(sqn, query_template)
        if not hit:
            log.info("Known endpoint gave nothing; trying generic discovery "
                     f"across {len(candidates)} candidates")
            hit = try_candidates(sqn, query_template, candidates)
        if not hit:
            log.error("No endpoint produced File/Get URLs. "
                      "Paste autopilot.log back to the developer.")
            return 1
        url, method, style, params, first_resp = hit
        if style == 'known':
            # Union the 全部/中央/地方 tabs in case cga=all misses rows
            dc = params.get('dc', 15)
            param_sets = [params,
                          build_body(int(params['MainSN']),
                                     cga='ClimateGovernanceCentral', dc=dc),
                          build_body(int(params['MainSN']),
                                     cga='ClimateGovernancePlace', dc=dc)]
        else:
            param_sets = [params]
        docs = harvest(url, method, param_sets, first_resp, scraper)

    if not docs:
        log.error("Discovery succeeded but produced no documents — "
                  "paste autopilot.log back")
        return 1

    scraper.documents = docs
    log.info(f"TOTAL DOCUMENTS: {len(docs)}")

    if args.probe_files:
        log.info(f"Probing {len(docs)} files (~{len(docs)*2/60:.0f} min)...")
        for doc in docs:
            scraper.probe_file(doc)

    DocumentOutputFormatter.save_csv(docs)
    DocumentOutputFormatter.save_json(docs)
    stats = scraper.get_statistics()
    ReportGenerator(docs, stats, scraper.errors, 0.0) \
        .generate_markdown_report()

    log.info("Metadata written to output/climate_docs_metadata.{csv,json}")
    for key in ('by_org_type', 'by_type'):
        log.info(f"{key}: {stats.get(key)}")
    unident = stats.get('by_organization', {}).get('未識別', 0)
    if unident:
        log.warning(f"{unident} documents have unidentified organization")

    if args.full:
        from phase2_download import download_phase, organize_phase
        from download_manager import ORGANIZE_METHODS
        log.info("FULL MODE: downloading everything...")
        if download_phase(docs, max_workers=3):
            organize_phase(docs, ORGANIZE_METHODS)
        log.info("Download + all views complete")
    else:
        log.info("Next: python phase2_download.py --organize-by all")

    log.info("AUTOPILOT DONE")
    return 0


if __name__ == '__main__':
    sys.exit(main())
