# routes/render_plantuml.py
# -*- coding: utf-8 -*-

from fastapi import APIRouter, HTTPException, Body, Response
import os, zlib, logging, requests

router = APIRouter()
log = logging.getLogger("plantuml")

# Укажи свой PlantUML сервер; можно без /uml — добавим сами.
RAW_BASE = os.getenv("PLANTUML_URL", "https://my-pluntuml.onrender.com").strip()

CONNECT_TIMEOUT = 10
READ_TIMEOUT = 60
TIMEOUT = (CONNECT_TIMEOUT, READ_TIMEOUT)
ERR_PREVIEW = 800


# ---------- utils ----------
def _ensure_uml_base(base: str) -> str:
    base = base.rstrip("/")
    if not base.endswith("/uml"):
        base += "/uml"
    return base

def _encode6bit(b: int) -> str:
    if b < 10:  # 0-9
        return chr(48 + b)
    b -= 10
    if b < 26:  # A-Z
        return chr(65 + b)
    b -= 26
    if b < 26:  # a-z
        return chr(97 + b)
    b -= 26
    if b == 0:  # -
        return "-"
    return "_"   # 63

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
    n = len(compressed)
    i = 0
    while i < n:
        b1 = compressed[i]
        b2 = compressed[i + 1] if i + 1 < n else 0
        b3 = compressed[i + 2] if i + 2 < n else 0
        out.append(_append3bytes(b1, b2, b3))
        i += 3
    return ''.join(out)

def _fetch(fmt: str, encoded: str) -> requests.Response:
    if fmt not in ("png", "svg", "txt"):
        raise HTTPException(400, detail="format must be png/svg/txt")
    base = _ensure_uml_base(RAW_BASE)
    url = f"{base}/{fmt}/{encoded}"
    log.info("GET %s", url)
    try:
        r = requests.get(url, timeout=TIMEOUT)
    except requests.RequestException as e:
        raise HTTPException(502, detail=f"PlantUML network error: {e}")

    ctype = (r.headers.get("Content-Type") or "").lower()
    if r.status_code != 200:
        preview = (r.text or "")[:ERR_PREVIEW]
        raise HTTPException(502, detail=f"PlantUML {r.status_code}: {preview}")
    if "text/html" in ctype:
        preview = (r.text or "")[:ERR_PREVIEW]
        raise HTTPException(502, detail=f"Got HTML UI instead of {fmt}. Preview: {preview}")
    return r


# ---------- endpoint ----------
@router.post("/render_pluntuml")
def render_plantuml(
    fmt: str,
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
        return Response(content=resp.content, media_type=resp.headers.get("Content-Type", "image/svg+xml"))
    else:  # txt
        return Response(content=resp.text, media_type="text/plain; charset=utf-8")
