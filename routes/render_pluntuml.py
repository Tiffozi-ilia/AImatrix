# routes/render_plantuml.py
# -*- coding: utf-8 -*-

from fastapi import APIRouter, HTTPException, Body, Response
import os, zlib, logging, requests, re
from typing import Literal, Optional

router = APIRouter()
log = logging.getLogger("plantuml")

# ===== Конфиг =====
# Базовый адрес PlantUML-сервера БЕЗ /uml — мы добавляем его сами.
PLANTUML_URL = os.getenv("PLANTUML_URL", "https://my-pluntuml.onrender.com").strip().rstrip("/")
PLANTUML_ALT_URL = os.getenv("PLANTUML_ALT_URL", "").strip().rstrip("/")  # опционально

CONNECT_TIMEOUT = 10
READ_TIMEOUT = 60
TIMEOUT = (CONNECT_TIMEOUT, READ_TIMEOUT)

# ===== Helpers =====

def _accept_for(fmt: Literal["png","svg","txt"]) -> str:
    if fmt == "png":
        return "image/png"
    if fmt == "svg":
        return "image/svg+xml"
    return "text/plain; charset=utf-8"

def _build_headers(fmt: Literal["png","svg","txt"]) -> dict:
    return {
        "Accept": _accept_for(fmt),
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
        "X-Requested-With": "XMLHttpRequest",
        "User-Agent": "sotiio-render/1.0",
    }

def _is_html_response(resp: requests.Response) -> bool:
    ct = (resp.headers.get("Content-Type") or "").lower()
    return "text/html" in ct

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
    comp = zlib.compressobj(level=9, wbits=-15)  # raw DEFLATE (без zlib header)
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
    Нормализация:
    - Пустой: вернуть как есть
    - Есть @startuml и @enduml: не трогаем
    - Есть @startuml без @enduml: дописываем
    - Есть @startX (mindmap, wbs, ...): не трогаем
    - Иначе: оборачиваем в @startuml/@enduml
    """
    s = code.strip()
    if not s:
        return s

    low = s.lower()
    if "@startuml" in low and "@enduml" in low:
        return s
    if "@startuml" in low and "@enduml" not in low:
        return s + "\n@enduml"
    if re.search(r'@start\w+', s, re.IGNORECASE):
        return s
    return f"@startuml\n{s}\n@enduml"

def _unescape_backslashes(s: str) -> str:
    """
    Разэкранируем \\r\\n, \\n, \\r, \\t ТОЛЬКО ВНЕ двойных кавычек.
    Внутри "..." оставляем \\n как литерал — PlantUML сам превратит его в перенос строки.
    """
    out = []
    i = 0
    n = len(s)
    in_str = False  # внутри двойных кавычек
    while i < n:
        ch = s[i]

        # вход/выход из строки с учётом экранирования кавычек
        if ch == '"':
            bs = 0
            j = i - 1
            while j >= 0 and s[j] == '\\':
                bs += 1
                j -= 1
            if bs % 2 == 0:  # неэкранированная кавычка
                in_str = not in_str
            out.append(ch)
            i += 1
            continue

        # вне строк — разэкранируем управляющие последовательности
        if not in_str and ch == '\\' and i + 1 < n:
            nxt = s[i + 1]
            # \r\n
            if nxt == 'r' and i + 3 < n and s[i + 2] == '\\' and s[i + 3] == 'n':
                out.append('\r\n')
                i += 4
                continue
            # \n
            if nxt == 'n':
                out.append('\n')
                i += 2
                continue
            # \r
            if nxt == 'r':
                out.append('\r')
                i += 2
                continue
            # \t
            if nxt == 't':
                out.append('\t')
                i += 2
                continue
            # прочее — оставить как есть
            out.append(ch)
            i += 1
            continue

        out.append(ch)
        i += 1

    return ''.join(out)

def _strip_invisibles(s: str) -> str:
    """Убираем BOM/ZWSP/LRM/RLM — иногда прилетают при копипасте."""
    return (s.replace('\ufeff', '')
             .replace('\u200b', '')
             .replace('\u200e', '')
             .replace('\u200f', ''))

def _finish(fmt: Literal["png","svg","txt"], resp: requests.Response) -> Response:
    if fmt == "png":
        return Response(content=resp.content, media_type="image/png")
    if fmt == "svg":
        return Response(content=resp.content, media_type="image/svg+xml")
    return Response(content=resp.text, media_type="text/plain; charset=utf-8")

def _get_encoded(base: str, fmt: Literal["png","svg","txt"], encoded: str) -> Optional[requests.Response]:
    if not base:
        return None
    url = f"{base}/uml/{fmt}/{encoded}"
    headers = _build_headers(fmt)
    log.info("GET %s", url)
    try:
        r = requests.get(url, headers=headers, timeout=TIMEOUT, allow_redirects=True)
    except requests.RequestException as e:
        log.info("GET error (%s): %s", url, e)
        return None

    log.info("UPSTREAM status=%s content-type=%s len=%s",
             r.status_code, r.headers.get("Content-Type"), len(r.content))
    if r.status_code != 200:
        return None
    if _is_html_response(r):
        return None
    return r

def _post_raw(base: str, fmt: Literal["png","svg","txt"], code: str) -> Optional[requests.Response]:
    if not base:
        return None
    url = f"{base}/uml/{fmt}"
    headers = {
        "Content-Type": "text/plain; charset=utf-8",
        "Accept": _accept_for(fmt),
        "User-Agent": "sotiio-render/1.0",
    }
    log.info("POST %s (len=%d)", url, len(code))
    try:
        r = requests.post(url, data=code.encode("utf-8"),
                          headers=headers, timeout=TIMEOUT,
                          allow_redirects=True)
    except requests.RequestException as e:
        log.info("POST error (%s): %s", url, e)
        return None

    log.info("UPSTREAM(POST) status=%s content-type=%s len=%s",
             r.status_code, r.headers.get("Content-Type"), len(r.content))
    if r.status_code != 200:
        return None
    if _is_html_response(r):
        return None
    return r

# ===== Endpoint =====

@router.post("/render_pluntuml")
def render_plantuml(
    fmt: Literal["png","svg","txt"],
    code: str = Body(..., embed=True, description="PlantUML code as raw string"),
):
    """
    POST /render_pluntuml?fmt=png|svg|txt
    Body: {"code": "@startuml\\nAlice -> Bob: Hi\\n@enduml"}
    """
    if fmt not in ("png", "svg", "txt"):
        raise HTTPException(400, detail="format must be png/svg/txt")
    if not code or not code.strip():
        raise HTTPException(400, detail="Empty PlantUML code")

    # 0) Разэкранируем управляющие последовательности и чистим невидимые
    raw = _strip_invisibles(_unescape_backslashes(code))
    log.info("CODE len=%d head=%r", len(raw), raw[:160].replace("\n", "\\n"))

    # 1) Нормализуем @startuml/@enduml
    normalized = _normalize_code(raw)

    # 2) Сначала быстрый GET по короткому ID
    try:
        encoded = plantuml_encode(normalized)
    except Exception as e:
        raise HTTPException(400, detail=f"Encode error: {e}")

    for base in filter(None, [PLANTUML_URL, PLANTUML_ALT_URL]):
        r = _get_encoded(base, fmt, encoded)
        if r:
            return _finish(fmt, r)

    # 3) Затем POST (лучше для ОЧЕНЬ больших диаграмм/сетапов)
    for base in filter(None, [PLANTUML_URL, PLANTUML_ALT_URL]):
        r = _post_raw(base, fmt, normalized)
        if r:
            return _finish(fmt, r)

    # 4) Всё плохо
    raise HTTPException(
        502,
        detail="PlantUML upstream error: GET/POST failed (no Kroki fallback).",
    )
