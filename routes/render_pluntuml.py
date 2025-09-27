# routes/render_plantuml.py
# -*- coding: utf-8 -*-

from fastapi import APIRouter, HTTPException, Body, Response
import os, zlib, logging, requests
from typing import Literal, Optional
from urllib.parse import urljoin, urlparse

router = APIRouter()
log = logging.getLogger("plantuml")

# Базовые адреса. Можно оставить без /uml — код сам попробует оба варианта.
PLANTUML_URL = os.getenv("PLANTUML_URL", "https://my-pluntuml.onrender.com").strip().rstrip("/")
PLANTUML_ALT_URL = os.getenv("PLANTUML_ALT_URL", "").strip().rstrip("/")  # опциональный второй инстанс
KROKI_URL = os.getenv("KROKI_URL", "").strip().rstrip("/")                # опциональный фолбэк, напр. https://kroki.io

CONNECT_TIMEOUT = 10
READ_TIMEOUT = 60
TIMEOUT = (CONNECT_TIMEOUT, READ_TIMEOUT)
ERR_PREVIEW = 800


# ---------- helpers ----------
def _accept_for(fmt: Literal["png","svg","txt"]) -> str:
    if fmt == "png": return "image/png"
    if fmt == "svg": return "image/svg+xml"
    return "text/plain; charset=utf-8"

def _ensure_with_ctx(base: str, ctx: bool) -> str:
    """
    Если ctx=True -> гарантируем {base}/uml
    Если ctx=False -> гарантируем просто {base}
    """
    if not base:
        return ""
    if ctx:
        return base if base.endswith("/uml") else base + "/uml"
    else:
        return base[:-4] if base.endswith("/uml") else base

def _encode6bit(b: int) -> str:
    if b < 10:  return chr(48 + b)   # 0-9
    b -= 10
    if b < 26: return chr(65 + b)   # A-Z
    b -= 26
    if b < 26: return chr(97 + b)   # a-z
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
    n = len(compressed)
    while i < n:
        b1 = compressed[i]
        b2 = compressed[i + 1] if i + 1 < n else 0
        b3 = compressed[i + 2] if i + 2 < n else 0
        out.append(_append3bytes(b1, b2, b3))
        i += 3
    return ''.join(out)

def _looks_like_html_text(s: str) -> bool:
    t = s.lstrip().lower()
    return t.startswith("<!doctype") or t.startswith("<html")

def _build_headers(fmt: Literal["png","svg","txt"]) -> dict:
    return {
        "Accept": _accept_for(fmt),
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
        "X-Requested-With": "XMLHttpRequest",
        "User-Agent": "sotiio-render/1.0",
    }

def _try_get_raw(base: str, use_ctx: bool, fmt: Literal["png","svg","txt"], encoded: str) -> Optional[requests.Response]:
    """Пробуем GET {base}[ /uml ]/{fmt}/{encoded}. Возвращаем r, если это НЕ HTML и статус=200, иначе None."""
    if not base:
        return None
    root = _ensure_with_ctx(base, use_ctx)
    url = f"{root}/{fmt}/{encoded}"
    headers = _build_headers(fmt)
    log.info("GET %s", url)
    try:
        r = requests.get(url, headers=headers, timeout=TIMEOUT, allow_redirects=False)
    except requests.RequestException as e:
        log.info("GET error (%s): %s", url, e)
        return None

    status = r.status_code
    ctype = (r.headers.get("Content-Type") or "")
    log.info("UPSTREAM status=%s content-type=%s len=%s", status, ctype, len(r.content))

    # иногда отдают редирект — дойдём по нему, но всё равно проверим тело
    if status in (301, 302, 303, 307, 308) and r.headers.get("Location"):
        redir = urljoin(url, r.headers["Location"])
        log.info("FOLLOW REDIRECT to %s", redir)
        try:
            r = requests.get(redir, headers=headers, timeout=TIMEOUT, allow_redirects=False)
            status = r.status_code
            ctype = (r.headers.get("Content-Type") or "")
            log.info("UPSTREAM(redirect) status=%s content-type=%s len=%s", status, ctype, len(r.content))
        except requests.RequestException as e:
            log.info("Redirect GET error (%s): %s", redir, e)
            return None

    if status != 200:
        return None

    # Для txt проверим, что не UI
    if fmt == "txt" and _looks_like_html_text(r.text):
        return None

    # для svg/png иногда ошибочный content-type — не верим заголовку, просто принимаем как есть
    return r

def _try_post_then_follow(base: str, use_ctx: bool, fmt: Literal["png","svg","txt"], code: str) -> Optional[requests.Response]:
    """POST {base}[ /uml ]/{fmt} с кодом, без редиректов; если вернули Location с {id}, добираем GET сырой."""
    if not base:
        return None
    root = _ensure_with_ctx(base, use_ctx)
    post_url = f"{root}/{fmt}"
    headers = {
        "Content-Type": "text/plain; charset=utf-8",
        "Accept": _accept_for(fmt),
        "User-Agent": "sotiio-render/1.0",
    }
    log.info("POST %s (len=%d)", post_url, len(code))
    try:
        resp = requests.post(post_url, data=code.encode("utf-8"), headers=headers, timeout=TIMEOUT, allow_redirects=False)
    except requests.RequestException as e:
        log.info("POST error (%s): %s", post_url, e)
        return None

    # ожидаем 302 Location: {root}/{id}
    if resp.status_code not in (301, 302, 303) or not resp.headers.get("Location"):
        # некоторые нестандартные сборки сразу 200 отдают, попробуем принять
        if resp.status_code == 200:
            # txt: проверим, что не html
            if fmt != "txt" or not _looks_like_html_text(resp.text):
                return resp
        return None

    loc = resp.headers["Location"]
    abs_loc = urljoin(post_url, loc)
    # вытащим хвост после /uml/ или после корня — это и есть {id}
    parsed = urlparse(abs_loc)
    path = parsed.path
    # сперва ищем /uml/
    marker = "/uml/"
    if marker in path:
        tail = path.split(marker, 1)[1]  # может быть "{id}" или "{fmt}/{id}"
    else:
        # без контекста — всё после ведущего слеша
        tail = path[1:] if path.startswith("/") else path

    # если вдруг прилетело "{fmt}/{id}" — оставим только {id}
    if "/" in tail:
        head, maybe_id = tail.split("/", 1)
        # иногда head == fmt, иногда сразу id — нормализуем
        id_part = maybe_id if head in ("png", "svg", "txt") else tail
    else:
        id_part = tail

    # теперь пробуем сырой GET
    get_url = f"{root}/{fmt}/{id_part}"
    log.info("FOLLOW as GET %s", get_url)
    try:
        r = requests.get(get_url, headers=_build_headers(fmt), timeout=TIMEOUT, allow_redirects=False)
    except requests.RequestException as e:
        log.info("GET after POST error (%s): %s", get_url, e)
        return None

    if r.status_code != 200:
        return None
    if fmt == "txt" and _looks_like_html_text(r.text):
        return None
    return r

def _try_kroki(fmt: Literal["png","svg","txt"], code: str) -> Optional[requests.Response]:
    if not KROKI_URL:
        return None
    # Kroki: POST {KROKI_URL}/plantuml/{fmt} body = plain text
    url = f"{KROKI_URL}/plantuml/{fmt}"
    headers = {
        "Content-Type": "text/plain; charset=utf-8",
        "Accept": _accept_for(fmt),
        "User-Agent": "sotiio-render/1.0",
    }
    log.info("KROKI POST %s (len=%d)", url, len(code))
    try:
        r = requests.post(url, data=code.encode("utf-8"), headers=headers, timeout=TIMEOUT)
    except requests.RequestException as e:
        log.info("KROKI error (%s): %s", url, e)
        return None

    if r.status_code != 200:
        return None
    if fmt == "txt" and _looks_like_html_text(r.text):
        return None
    return r


# ---------- endpoint ----------
@router.post("/render_pluntuml")
def render_plantuml(
    fmt: Literal["png","svg","txt"],
    code: str = Body(..., embed=True, description="PlantUML code as raw string"),
):
    """
    POST /render_pluntuml?fmt=png|svg|txt
    Body: {"code": "@startuml\\nAlice -> Bob: Hi\\n@enduml"}
    """
    if not code or not code.strip():
        raise HTTPException(400, detail="Empty PlantUML code")

    try:
        encoded = plantuml_encode(code)
    except Exception as e:
        raise HTTPException(400, detail=f"Encode error: {e}")

    # 1) GET raw: base with /uml, затем без /uml
    for base in filter(None, [PLANTUML_URL, PLANTUML_ALT_URL]):
        r = _try_get_raw(base, True, fmt, encoded)    # с /uml
        if r is not None:
            return _finish(fmt, r)
        r = _try_get_raw(base, False, fmt, encoded)   # без /uml
        if r is not None:
            return _finish(fmt, r)

    # 2) POST → Location → GET raw  (с /uml, затем без /uml)
    for base in filter(None, [PLANTUML_URL, PLANTUML_ALT_URL]):
        r = _try_post_then_follow(base, True, fmt, code)
        if r is not None:
            return _finish(fmt, r)
        r = _try_post_then_follow(base, False, fmt, code)
        if r is not None:
            return _finish(fmt, r)

    # 3) Фолбэк на Kroki (если задан)
    r = _try_kroki(fmt, code)
    if r is not None:
        return _finish(fmt, r)

    # Если дошли сюда — апстрим ведёт себя как чистый UI.
    raise HTTPException(
        502,
        detail=(
            "Upstream returned HTML UI instead of raw diagram for all attempts. "
            "Check PlantUML server routing. "
            "Tried: GET /{fmt}/{encoded} with and without /uml, and POST+Location follow; "
            "set KROKI_URL to enable fallback."
        ),
    )

def _finish(fmt: Literal["png","svg","txt"], resp: requests.Response) -> Response:
    if fmt == "png":
        return Response(content=resp.content, media_type="image/png")
    if fmt == "svg":
        return Response(content=resp.content, media_type="image/svg+xml")
    return Response(content=resp.text, media_type="text/plain; charset=utf-8")
