# routes/render_plantuml.py
# -*- coding: utf-8 -*-

from fastapi import APIRouter, HTTPException, Body, Response
import os, zlib, logging, requests
from typing import Literal

router = APIRouter()
log = logging.getLogger("plantuml")

# Можно без /uml — модуль сам добавит
RAW_BASE = os.getenv("PLANTUML_URL", "https://my-pluntuml.onrender.com").strip()

CONNECT_TIMEOUT = 10
READ_TIMEOUT = 60
TIMEOUT = (CONNECT_TIMEOUT, READ_TIMEOUT)
ERR_PREVIEW = 800


# ---------- helpers ----------
def _ensure_uml_base(base: str) -> str:
    base = base.rstrip("/")
    if not base.endswith("/uml"):
        base += "/uml"
    return base

def _encode6bit(b: int) -> str:
    if b < 10:   return chr(48 + b)       # 0-9
    b -= 10
    if b < 26:  return chr(65 + b)        # A-Z
    b -= 26
    if b < 26:  return chr(97 + b)        # a-z
    b -= 26
    return "-" if b == 0 else "_"         # -, _

def _append3bytes(b1: int, b2: int, b3: int) -> str:
    c1 = (b1 >> 2) & 0x3F
    c2 = ((b1 & 0x03) << 4) | ((b2 >> 4) & 0x0F)
    c3 = ((b2 & 0x0F) << 2) | ((b3 >> 6) & 0x03)
    c4 = b3 & 0x3F
    return ''.join((_encode6bit(c1), _encode6bit(c2), _encode6bit(c3), _encode6bit(c4)))

def plantuml_encode(uml: str) -> str:
    data = uml.encode("utf-8")
    # raw DEFLATE (без zlib-заголовка)
    comp = zlib.compressobj(level=9, wbits=-15)
    compressed = comp.compress(data) + comp.flush()
    out = []
    i, n = 0, len(compressed)
    while i < n:
        b1 = compressed[i]
        b2 = compressed[i + 1] if i + 1 < n else 0
        b3 = compressed[i + 2] if i + 2 < n else 0
        out.append(_append3bytes(b1, b2, b3))
        i += 3
    return ''.join(out)

def _accept_for(fmt: Literal["png","svg","txt"]) -> str:
    if fmt == "png":
        return "image/png"
    if fmt == "svg":
        return "image/svg+xml"
    return "text/plain; charset=utf-8"


def _fetch(fmt: Literal["png","svg","txt"], encoded: str) -> requests.Response:
    base = _ensure_uml_base(RAW_BASE)
    url = f"{base}/{fmt}/{encoded}"
    headers = {
        "Accept": _accept_for(fmt),
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
        "X-Requested-With": "XMLHttpRequest",
        "User-Agent": "sotiio-render/1.0",
    }

    log.info("GET %s", url)
    try:
        r = requests.get(url, headers=headers, timeout=TIMEOUT, allow_redirects=False)
    except requests.RequestException as e:
        raise HTTPException(502, detail=f"PlantUML network error: {e}")

    status = r.status_code
    ctype = (r.headers.get("Content-Type") or "")
    log.info("UPSTREAM status=%s content-type=%s len=%s", status, ctype, len(r.content))

    # На всякий случай обработаем редиректы теми же Accept
    if status in (301, 302, 303, 307, 308) and r.headers.get("Location"):
        from urllib.parse import urljoin
        redir = urljoin(url, r.headers["Location"])
        log.info("FOLLOW REDIRECT to %s", redir)
        try:
            r = requests.get(redir, headers=headers, timeout=TIMEOUT, allow_redirects=False)
        except requests.RequestException as e:
            raise HTTPException(502, detail=f"PlantUML redirect error: {e}")
        status = r.status_code
        ctype = (r.headers.get("Content-Type") or "")
        log.info("UPSTREAM(redirect) status=%s content-type=%s len=%s", status, ctype, len(r.content))

    if status != 200:
        preview = (r.text or "")[:ERR_PREVIEW]
        raise HTTPException(502, detail=f"PlantUML {status}: {preview}")

    # Доп. защита от UI для txt: проверяем реальное тело
    if fmt == "txt":
        t = r.text.lstrip().lower()
        if t.startswith("<!doctype") or t.startswith("<html"):
            preview = (r.text or "")[:ERR_PREVIEW]
            raise HTTPException(502, detail=f"Got HTML UI instead of {fmt}. Preview: {preview}")

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

    resp = _fetch(fmt, encoded)

    if fmt == "png":
        return Response(content=resp.content, media_type="image/png")
    elif fmt == "svg":
        return Response(content=resp.content, media_type="image/svg+xml")
    else:  # txt
        return Response(content=resp.text, media_type="text/plain; charset=utf-8")
