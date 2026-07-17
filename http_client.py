"""Shared requests.Session factory with TLS settings for Taiwan gov sites.

Python 3.13 enables ssl.VERIFY_X509_STRICT by default, which rejects any
certificate lacking a Subject Key Identifier extension. The certificate
chain used by www.cca.gov.tw trips this check, so requests fail with
    SSLError: certificate verify failed: Missing Subject Key Identifier

The adapter below relaxes ONLY that strict-extension flag. Full chain
validation and hostname verification remain enabled — this is not
verify=False. Both certifi's bundle and the OS trust store are loaded so
the government root CA is found wherever it is installed.
"""

import ssl

import requests
from requests.adapters import HTTPAdapter

BROWSER_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                  '(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36',
    'Accept-Language': 'zh-TW,zh;q=0.9,en;q=0.5',
}


def _build_context() -> ssl.SSLContext:
    ctx = ssl.create_default_context()  # loads OS trust store
    try:
        import certifi
        ctx.load_verify_locations(certifi.where())
    except ImportError:
        pass
    if hasattr(ssl, 'VERIFY_X509_STRICT'):  # Python 3.13+
        ctx.verify_flags &= ~ssl.VERIFY_X509_STRICT
    return ctx


class _RelaxedStrictAdapter(HTTPAdapter):
    def init_poolmanager(self, *args, **kwargs):
        kwargs['ssl_context'] = _build_context()
        return super().init_poolmanager(*args, **kwargs)


def make_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(BROWSER_HEADERS)
    session.mount('https://', _RelaxedStrictAdapter())
    return session
