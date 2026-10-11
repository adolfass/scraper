"""Client for the ФГИС Росаккредитации public registries (pub.fsa.gov.ru).

Transport: a persistent curl_cffi session with a real browser TLS fingerprint,
bound to the physical interface (en0) so the VPN's foreign exit is bypassed.
A persistent, keep-alive connection is essential - urllib opens a fresh TLS
connection per request and the server then throttles/stalls most of them.
Set FSA_TRANSPORT=urllib to fall back to the old behaviour.
"""
import json, os, time, urllib.request, urllib.error
import socket
import threading
import http.client
import subprocess

# Some networks advertise broken IPv6 routes; force IPv4.
_orig_gai = socket.getaddrinfo
def _gai_v4(host, port, family=0, type=0, proto=0, flags=0):
    return _orig_gai(host, port, socket.AF_INET, type, proto, flags)
socket.getaddrinfo = _gai_v4


def _detect_source():
    """Local address of the physical interface (urllib fallback path)."""
    if os.environ.get("SRC_BIND", "1") == "0":
        return None
    addr = os.environ.get("SRC_ADDR")
    if addr:
        return (addr, 0)
    for iface in ("en0", "en1", "en2", "en3"):
        try:
            ip = subprocess.check_output(
                ["ipconfig", "getifaddr", iface],
                stderr=subprocess.DEVNULL, timeout=5).decode().strip()
            if ip:
                return (ip, 0)
        except Exception:
            continue
    return None


def _iface_arg():
    """Interface name (or source IP) for curl's `interface` option."""
    if os.environ.get("SRC_BIND", "1") == "0":
        return None
    addr = os.environ.get("SRC_ADDR")
    if addr:
        return addr
    for iface in ("en0", "en1", "en2", "en3"):
        try:
            ip = subprocess.check_output(
                ["ipconfig", "getifaddr", iface],
                stderr=subprocess.DEVNULL, timeout=5).decode().strip()
            if ip:
                return iface
        except Exception:
            continue
    return None


_SOURCE = _detect_source()


class _SourceHTTPSHandler(urllib.request.HTTPSHandler):
    def https_open(self, req):
        return self.do_open(
            lambda host, **kw: http.client.HTTPSConnection(
                host, source_address=_SOURCE, **kw),
            req)


urllib.request.install_opener(urllib.request.build_opener(_SourceHTTPSHandler()))

try:
    from curl_cffi import requests as _creq
    _HAVE_CURL = True
except Exception:  # pragma: no cover
    _HAVE_CURL = False

_USE_CURL = _HAVE_CURL and os.environ.get("FSA_TRANSPORT", "curl") != "urllib"

BASE = "https://pub.fsa.gov.ru"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/153.0.0.0 Safari/537.36")

_token = {"val": "", "exp": 0}
TIMEOUT = None  # per-attempt override set by pipeline.polite (seconds)

_session = None


def _get_session(timeout):
    global _session
    if _session is None:
        kw = {"impersonate": os.environ.get("CURL_IMPERSONATE", "chrome"),
              "timeout": timeout}
        iface = _iface_arg()
        if iface:
            kw["interface"] = iface
        _session = _creq.Session(**kw)
    return _session


def _raw(method, url, data, headers, timeout):
    """Low-level request -> (status, headers, body_bytes)."""
    if _USE_CURL:
        s = _get_session(timeout)
        try:
            r = s.request(method, url, data=data, headers=headers, timeout=timeout)
        except Exception as e:
            raise RuntimeError(f"curl: {e}")
        return r.status_code, r.headers, r.content
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.headers, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.headers, e.read()


def _req(method, path, body=None, token=None, timeout=None, hard=None):
    """HTTP call with a wall-clock cap on the urllib path.

    On the curl path the request timeout is reliable, so it is called directly
    (keeping the keep-alive connection alive in this thread).
    """
    if timeout is None:
        timeout = TIMEOUT if TIMEOUT else float(os.environ.get("SOCK_TIMEOUT", "30"))
    if _USE_CURL:
        return _req_impl(method, path, body, token, timeout)
    if hard is None:
        hard = timeout + float(os.environ.get("STALL_EXTRA", "15"))
    box = {}

    def run():
        try:
            box["v"] = _req_impl(method, path, body, token, timeout)
        except Exception as e:  # pragma: no cover
            box["e"] = e

    t = threading.Thread(target=run, daemon=True, name="fsa-req")
    t.start()
    t.join(hard)
    if "v" in box:
        return box["v"]
    if "e" in box:
        raise box["e"]
    raise RuntimeError(f"request stalled >{hard}s")


def _hdrs(body, token):
    h = {
        "User-Agent": UA,
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "ru-RU,ru;q=0.9",
        "Referer": BASE + "/rss/certificate",
        "origin": BASE,
    }
    if body is not None:
        h["Content-Type"] = "application/json"
    if token:
        h["authorization"] = "Bearer " + token
    return h


def _req_impl(method, path, body=None, token=None, timeout=60):
    url = path if path.startswith("http") else BASE + path
    data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
    st, _h, content = _raw(method, url, data, _hdrs(body, token), timeout)
    return st, content


def login(force=False):
    """Login; returns a bearer token (valid ~8h).

    Set FSA_USER / FSA_PASS (required; the anonymous credentials are not
    hardcoded - supply them via the environment).
    """
    now = time.time()
    if not force and _token["val"] and now < _token["exp"] - 300:
        return _token["val"]
    user = os.environ.get("FSA_USER", "anonymous")
    pw = os.environ.get("FSA_PASS")
    if pw is None:
        raise RuntimeError(
            "FSA_PASS is not set. The FSA registry API login\n"
            "requires credentials - set FSA_USER / FSA_PASS in the\n"
            "environment (password is intentionally not hardcoded).")
    data = json.dumps({"username": user, "password": pw}).encode()
    headers = {"User-Agent": UA, "Content-Type": "application/json",
               "Accept": "application/json", "origin": BASE,
               "Referer": BASE + "/rss/certificate"}
    st, hdrs, content = _raw("POST", BASE + "/login", data, headers,
                             float(os.environ.get("SOCK_TIMEOUT", "45")))
    tok = hdrs.get("Authorization") if hasattr(hdrs, "get") else None
    if not tok or "eyJ" not in tok:
        raise RuntimeError(f"login failed: {st} {content[:200]!r}")
    import base64
    payload = tok.split(".")[1]
    payload += "=" * (-len(payload) % 4)
    claims = json.loads(base64.urlsafe_b64decode(payload))
    _token.update(val=tok, exp=claims.get("exp", now + 3600))
    return tok


def _call(method, path, body=None, retries=4):
    st, data = None, None
    for i in range(retries):
        tok = login()
        st, data = _req(method, path, body, token=tok)
        if st == 401:
            login(force=True)
            st, data = _req(method, path, body, token=login())
        if st in (200, 400, 404) or (st < 500 and st != 429):
            try:
                return st, json.loads(data)
            except Exception:
                return st, data
        time.sleep(1.5 * (i + 1))
    return st, data


def search_certificates(page=0, size=100, columns_search=None, columns_sort=None,
                        extra_filter=None):
    """POST /api/v1/rss/common/certificates/get"""
    filt = {"idCertScheme": [], "regDate": {"startDate": None, "endDate": None},
            "endDate": {"startDate": None, "endDate": None},
            "columnsSearch": columns_search or []}
    if extra_filter:
        filt.update(extra_filter)
    body = {"size": size, "page": page, "filter": filt,
            "columnsSort": columns_sort or [{"column": "date", "sort": "DESC"}]}
    return _call("POST", "/api/v1/rss/common/certificates/get", body)


def get_certificate(cert_id):
    """GET /api/v1/rss/common/certificates/{id}"""
    return _call("GET", f"/api/v1/rss/common/certificates/{cert_id}")


# --------------------------------------------------------------- declarations
DECL_ARTICLE_COLUMN = "productIdentificationArticle"


def search_declarations(columns_search, size=100, page=0, columns_sort=None):
    """POST /api/v1/rds/common/declarations/get  (public, anonymous).

    Unlike the certificates endpoint, this one only filters when it receives the
    EXACT minimal body the web app sends - extra top-level filter fields make it
    silently return the unfiltered newest list.  A columnsSearch entry is
    {"name": <col>, "search": <val>, "type": 0} and matches the column as a
    case-insensitive substring.  NB: the response "total" is a bogus constant
    1000 - page until fewer than `size` items come back.
    """
    filt = {"status": [], "idDeclType": [], "idCertObjectType": [],
            "idProductType": [], "idGroupRU": [], "idGroupEEU": [],
            "idTechReg": [], "idApplicantType": [],
            "regDate": {"minDate": "", "maxDate": ""},
            "endDate": {"minDate": "", "maxDate": ""},
            "columnsSearch": columns_search}
    body = {"size": size, "page": page, "count": 1000, "filter": filt,
            "columnsSort": columns_sort or [{"column": "id", "sort": "ASC"}]}
    return _call("POST", "/api/v1/rds/common/declarations/get", body)


def get_declaration(decl_id):
    """GET /api/v1/rds/common/declarations/{id}"""
    return _call("GET", f"/api/v1/rds/common/declarations/{decl_id}")


if __name__ == "__main__":
    tok = login()
    print(f"transport={'curl' if _USE_CURL else 'urllib'} iface={_iface_arg()} "
          f"token ok, len {len(tok)}")
    st, res = search_certificates(
        columns_search=[{"column": "number", "search": "ЕАЭС RU С-DE.АД50.В.05524/23"}],
        size=5)
    print("certs:", st, json.dumps(res, ensure_ascii=False)[:400])
    st, res = search_declarations(
        columns_search=[{"name": DECL_ARTICLE_COLUMN, "search": "фильтр", "type": 0}],
        size=2)
    print("decls:", st, json.dumps(res, ensure_ascii=False)[:300])
