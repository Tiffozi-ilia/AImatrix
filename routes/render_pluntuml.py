# routes/render_plantuml.py
# -*- coding: utf-8 -*-

from fastapi import APIRouter, HTTPException, Body, Response
import os, logging, requests
from typing import Literal

router = APIRouter()
log = logging.getLogger("plantuml")

# Базовые адреса (точно такие же как в рабочем скрипте)
PLANTUML_URL = os.getenv("PLANTUML_URL", "https://my-pluntuml.onrender.com").strip()
PLANTUML_ALT_URL = os.getenv("PLANTUML_ALT_URL", "").strip()
KROKI_URL = os.getenv("KROKI_URL", "").strip()

CONNECT_TIMEOUT = 10
READ_TIMEOUT = 60
TIMEOUT = (CONNECT_TIMEOUT, READ_TIMEOUT)

# ---------- helpers ----------
def _accept_for(fmt: Literal["png","svg","txt"]) -> str:
    return "image/png" if fmt == "png" else ("image/svg+xml" if fmt == "svg" else "text/plain; charset=utf-8")

def _join_endpoint(base: str, fmt: str) -> str:
    """Точно такая же функция как в рабочем скрипте"""
    base = base.rstrip("/")
    for suffix in ("/png", "/svg", "/txt"):
        if base.endswith(suffix):
            base = base[: -len(suffix)]
    return f"{base}/{fmt.lstrip('/')}"

def _looks_like_html_text(s: str) -> bool:
    t = s.lstrip().lower()
    return t.startswith("<!doctype") or t.startswith("<html")

def _try_direct_post(base: str, fmt: Literal["png","svg","txt"], code: str):
    """Прямой POST как в рабочем скрипте"""
    if not base:
        return None
        
    url = _join_endpoint(base, fmt)
    
    headers = {
        "Content-Type": "text/plain; charset=utf-8",
        "Accept": _accept_for(fmt),
        "User-Agent": "sotiio-render/1.0",
    }
    
    log.info("DIRECT POST %s (len=%d)", url, len(code))
    
    try:
        r = requests.post(
            url,
            data=code.encode("utf-8"),
            headers=headers,
            timeout=TIMEOUT,
        )
    except requests.RequestException as e:
        log.info("POST error (%s): %s", url, e)
        return None

    ctype = r.headers.get("Content-Type", "")
    log.info("UPSTREAM status=%s content-type=%s len=%s", r.status_code, ctype, len(r.content))

    # Проверяем что это не HTML страница (как в рабочем скрипте)
    if "text/html" in ctype.lower():
        log.info("Server вернул HTML UI вместо картинки: %s", url)
        return None

    if r.status_code != 200:
        preview = r.text[:800] if r.text else ""
        log.info("Upstream error %s: %s", r.status_code, preview)
        return None

    # Для txt проверяем что это не HTML
    if fmt == "txt" and _looks_like_html_text(r.text):
        return None
        
    return r

def _try_kroki(fmt: Literal["png","svg","txt"], code: str):
    """Kroki fallback"""
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
    Body: {"code": "PlantUML code"}
    """
    if not code or not code.strip():
        raise HTTPException(400, detail="Empty PlantUML code")

    # Логируем входные данные
    log.info("CODE len=%d head=%r", len(code), code[:120].replace("\n", "\\n"))
    
    # Нормализуем код - убираем лишние пробелы, но не меняем структуру
    normalized = code.strip()
    
    # 1) Прямой POST на основные серверы (как в рабочем скрипте)
    for base in filter(None, [PLANTUML_URL, PLANTUML_ALT_URL]):
        r = _try_direct_post(base, fmt, normalized)
        if r is not None:
            return _finish(fmt, r)

    # 2) Фолбэк Kroki
    r = _try_kroki(fmt, normalized)
    if r is not None:
        return _finish(fmt, r)

    raise HTTPException(
        502,
        detail="All upstream servers failed to render the diagram"
    )
