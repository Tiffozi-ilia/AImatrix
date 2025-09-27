# routes/render_plantuml.py
# -*- coding: utf-8 -*-

from fastapi import APIRouter, HTTPException, Body, Response
import os, zlib, logging, requests
from typing import Literal, Optional
from urllib.parse import urljoin, urlparse

router = APIRouter()
log = logging.getLogger("plantuml")

# ВАЖНО: укажи базу БЕЗ /uml — код сам попробует и корень, и /uml
PLANTUML_URL = os.getenv("PLANTUML_URL", "https://my-pluntuml.onrender.com").strip().rstrip("/")
PLANTUML_ALT_URL = os.getenv("PLANTUML_ALT_URL", "").strip().rstrip("/")
KROKI_URL = os.getenv("KROKI_URL", "").strip().rstrip("/")

CONNECT_TIMEOUT = 10
READ_TIMEOUT = 60
TIMEOUT = (CONNECT_TIMEOUT, READ_TIMEOUT)
ERR_PREVIEW = 800


# ---------- helpers ----------
def _accept_for(fmt: Literal["png","svg","txt"]) -> str:
    return "image/png" if fmt == "png" else ("image/svg+xml" if fmt == "svg" else "text/plain; charset=utf-8")

def _with_ctx(base: str, use_ctx: bool) -> str:
    if not base:
        return ""
    if use_ctx:
        return base if base.endswith("/uml") else base + "/uml"
    else:
        return base[:-4] if base.endswith("/uml") else base

def _encode6bit(b: int) -> str:
    if b < 10:  return chr(48 + b)
    b -= 10
    if b < 26: return chr(65 + b)
    b -= 26
    if b < 26: return chr(97 + b)
    b -= 26
    return "-" if b == 0 else "_"

def _append3bytes(b1: int, b2: int, b3: int) -> str:
    c1 = (b1 >> 2) & 0x3F
    c2 = ((b1 & 0x03) << 4) | ((b2 >> 4) & 0x0F)
    c3 = ((b2 & 0x0F) << 2) | ((b3 >> 6) & 0x03)
    c4 = b3 & 0x3F
    return ''.join((_encode6bit(c1), _encode6bit(c2), _encode6bit(c3), _encode6bit(c4)))

def plantuml_encode(uml: str) -> str:
    data = uml.encode("utf-8")
    comp = zlib.compressobj(level=9, wbits=-15)  # raw deflate
    compressed = comp.compress(data) + comp.flush()
    out = []
    i = 0
    while i < len(compressed):
        b1 = compressed[i]
        b2 = compressed[i + 1] if i + 1 < len(compressed) else 0
        b3 = compressed[i + 2] if i + 2 < len(compressed) else 0
        out.append(_append3bytes(b1, b2, b3))
        i += 3
    return ''.join(out)

def _build_headers(fmt: Literal["png","svg","txt"]) -> dict:
    return {
        "Accept": _accept_for(fmt),
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
        "X-Requested-With": "XMLHttpRequest",
        "User-Agent": "sotiio-render/1.0",
    }

def _is_html_ui(resp: requests.Response, fmt: str) -> bool:
    ct = (resp.headers.get("Content-Type") or "").lower()
    if "text/html" in ct:
        return True
    # Доппроверка по телу:
    if fmt == "txt":
        t = resp.text.lstrip().lower()
        return t.startswith("<!doctype") or t.startswith("<html")
    if fmt == "png":
        # PNG всегда начинается с сигнатуры \x89PNG\r\n\x1a\n
        return not resp.content.startswith(b"\x89PNG\r\n\x1a\n")
    if fmt == "svg":
        # допустим и image/svg+xml, и text/xml; главное, чтобы было <svg
        head = resp.content[:512].lower()
        return (b"<svg" not in head)
    return False

def _try_get_raw(base: str, use_ctx: bool, fmt: Literal["png","svg","txt"], encoded: str) -> Optional[requests.Response]:
    if not base:
        return None
    root = _with_ctx(base, use_ctx)
    url = f"{root}/{fmt}/{encoded}"
    headers = _build_headers(fmt)
    log.info("GET %s", url)
    try:
        r = requests.get(url, headers=headers, timeout=TIMEOUT, allow_redirects=False)
    except requests.RequestException:
        return None

    # если редирект — один шаг добираем
    if r.status_code in (301, 302, 303, 307, 308) and r.headers.get("Location"):
        redir = urljoin(url, r.headers["Location"])
        log.info("FOLLOW REDIRECT to %s", redir)
        try:
            r = requests.get(redir, headers=headers, timeout=TIMEOUT, allow_redirects=False)
        except requests.RequestException:
            return None

    if r.status_code != 200:
        return None
    if _is_html_ui(r, fmt):
        return None
    return r

def _try_post_follow(base: str, use_ctx: bool, fmt: Literal["png","svg","txt"], code: str) -> Optional[requests.Response]:
    if not base:
        return None
    root = _with_ctx(base, use_ctx)
    post_url = f"{root}/{fmt}"
    headers = {
        "Content-Type": "text/plain; charset=utf-8",
        "Accept": _accept_for(fmt),
        "User-Agent": "sotiio-render/1.0",
    }
    log.info("POST %s (len=%d)", post_url, len(code))
    try:
        resp = requests.post(post_url, data=code.encode("utf-8"), headers=headers, timeout=TIMEOUT, allow_redirects=False)
    except requests.RequestException:
        return None

    # иногда сразу 200 raw
    if resp.status_code == 200 and not _is_html_ui(resp, fmt):
        return resp

    if resp.status_code not in (301, 302, 303) or not resp.headers.get("Location"):
        return None

    loc = resp.headers["Location"]
    abs_loc = urljoin(post_url, loc)
    parsed = urlparse(abs_loc)
    path = parsed.path

    # достаём id после /uml/ или от корня
    if "/uml/" in path:
        tail = path.split("/uml/", 1)[1]
    else:
        tail = path[1:] if path.startswith("/") else path

    # если прилетело "{fmt}/{id}" — оставим только id
    if "/" in tail:
        head, maybe_id = tail.split("/", 1)
        id_part = maybe_id if head in ("png", "svg", "txt") else tail
    else:
        id_part = tail

    get_url = f"{root}/{fmt}/{id_part}"
    log.info("FOLLOW as GET %s", get_url)
    try:
        r = requests.get(get_url, headers=_build_headers(fmt), timeout=TIMEOUT, allow_redirects=False)
    except requests.RequestException:
        return None

    if r.status_code != 200 or _is_html_ui(r, fmt):
        return None
    return r

def _try_kroki(fmt: Literal["png","svg","txt"], code: str) -> Optional[requests.Response]:
    if not KROKI_URL:
        return None
    url = f"{KROKI_URL}/plantuml/{fmt}"
    headers = {
        "Content-Type": "text/plain; charset=u
