# routes/render_plantuml.py
# -*- coding: utf-8 -*-

from fastapi import APIRouter, HTTPException, Body, Response
import os, zlib, logging, requests, re
from typing import Literal, Optional
from urllib.parse import urljoin, urlparse

router = APIRouter()
log = logging.getLogger("plantuml")

# Базовые адреса
PLANTUML_URL = os.getenv("PLANTUML_URL", "https://my-pluntuml.onrender.com").strip().rstrip("/")
PLANTUML_ALT_URL = os.getenv("PLANTUML_ALT_URL", "").strip().rstrip("/")  # опция
KROKI_URL = os.getenv("KROKI_URL", "").strip().rstrip("/")                # опция (напр., https://kroki.io)

CONNECT_TIMEOUT = 10
READ_TIMEOUT = 60
TIMEOUT = (CONNECT_TIMEOUT, READ_TIMEOUT)

# ---------- helpers ----------
def _accept_for(fmt: Literal["png","svg","txt"]) -> str:
    return "image/png" if fmt == "png" else ("image/svg+xml" if fmt == "svg" else "text/plain; charset=utf-8")

def _ensure_with_ctx(base: str, ctx: bool) -> str:
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

def _normalize_code(code: str) -> str:
    """
    Упрощенная нормализация:
    - Если код пустой - возвращаем как есть
    - Если уже есть @startuml и @enduml - не трогаем
    - Если есть @startuml но нет @enduml - добавляем
    - В остальных случаях оборачиваем в @startuml/@enduml
    """
    s = code.strip()
    if not s:
        return s

    has_startuml = "@startuml" in s.lower()
    has_enduml = "@enduml" in s.lower()

    if has_startuml and has_enduml:
        return s

    if has_startuml and not has_enduml:
        return s + "\n@enduml"

    # Если есть любой другой @startX маркер - не трогаем (это может быть mindmap, wbs и т.д.)
    if re.search(r'@start\w+', s, re.IGNORECASE):
        return s

    return f"@startuml\n{s}\n@enduml"

def _looks_like_html_text(s: str) -> bool:
    t = s.lstrip().lower()
    return t.startswith("<!doctype") or t.startswith("<html")

def _is_html_response(resp: requests.Response) -> bool:
    ct = (resp.headers.get("Content-Type") or "").lower()
    return "text/html" in ct

def _build_headers(fmt: Literal["png","svg","txt"]) -> dict:
    return {
        "Accept": _accept_for(fmt),
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
        "X-Requested-With": "XMLHttpRequest",
        "User-Agent": "sotiio-render/1.0",
    }

def _try_get_raw(base: str, use_ctx: bool, fmt: Literal["png","svg","txt"], encoded: str) -> Optional[requests.Response]:
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
    if fmt == "txt" and _looks_like_html_text(r.text):
        return None
    if _is_html_response(r):  # ← ВАЖНО: проверяем HTML!
        return None
    return r

def _try_post_then_follow(base: str, use_ctx: bool, fmt: Literal["png","svg","txt"], code: str) -> Optional[requests.Response]:
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

    if resp.status_code not in (301, 302, 303) or not resp.headers.get("Location"):
        if resp.status_code == 200:
            if fmt != "txt" or not _looks_like_html_text(resp.text):
                if not _is_html_response(resp):  # ← ВАЖНО: проверяем HTML!
                    return resp
        return None

    loc = resp.headers["Location"]
    abs_loc = urljoin(post_url, loc)
    parsed = urlparse(abs_loc)
    path = parsed.path
    marker = "/uml/"
    if marker in path:
        tail = path.split(marker, 1)[1]
    else:
        tail = path[1:] if path.startswith("/") else path

    if "/" in tail:
        head, maybe_id = tail.split("/", 1)
        id_part = maybe_id if head in ("png", "svg", "txt") else tail
    else:
        id_part = tail

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
    if _is_html_response(r):  # ← ВАЖНО: проверяем HTML!
        return None
    return r

def _try_kroki(fmt: Literal["png","svg","txt"], code: str) -> Optional[requests.Response]:
    if not KROKI_URL:
        return None
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
    if _is_html_response(r):  # ← ВАЖНО: проверяем HTML!
        return None
    return r

def _finish(fmt: Literal["png","svg","txt"], resp: requests.Response) -> Response:
    if fmt == "png":
        return Response(content=resp.content, media_type="image/png")
    if fmt == "svg":
        return Response(content=resp.content, media_type="image/svg+xml")
    return Response(content=resp.text, media_type="text/plain; charset=utf-8")

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

    log.info("CODE len=%d head=%r", len(code), code[:120].replace("\n", "\\n"))

    # Упрощенная нормализация - только базовые случаи
    normalized = _normalize_code(code)

    try:
        encoded = plantuml_encode(normalized)
    except Exception as e:
        raise HTTPException(400, detail=f"Encode error: {e}")

    # 1) GET raw: сначала БЕЗ /uml, затем С /uml
    for base in filter(None, [PLANTUML_URL, PLANTUML_ALT_URL]):
        r = _try_get_raw(base, False, fmt, encoded)   # без /uml
        if r is not None:
            return _finish(fmt, r)
        r = _try_get_raw(base, True, fmt, encoded)    # с /uml
        if r is not None:
            return _finish(fmt, r)

    # 2) POST → Location → GET (без /uml, затем с /uml)
    for base in filter(None, [PLANTUML_URL, PLANTUML_ALT_URL]):
        r = _try_post_then_follow(base, False, fmt, normalized)
        if r is not None:
            return _finish(fmt, r)
        r = _try_post_then_follow(base, True, fmt, normalized)
        if r is not None:
            return _finish(fmt, r)

    # 3) Фолбэк Kroki
    r = _try_kroki(fmt, normalized)
    if r is not None:
        return _finish(fmt, r)

    raise HTTPException(
        502,
        detail=(
            "Upstream returned HTML UI instead of raw diagram for all attempts. "
            "Check PlantUML server routing or set KROKI_URL."
        ),
    )
