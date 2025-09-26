# routes/render_plantuml.py
# -*- coding: utf-8 -*-

from fastapi import APIRouter, HTTPException, Body, Response
import os, logging, requests
from urllib.parse import urljoin, urlparse

router = APIRouter()
log = logging.getLogger("plantuml")

# =================== КОНФИГ ===================
RAW_BASE = os.getenv("PLANTUML_URL", "https://my-pluntuml.onrender.com").strip()

CONNECT_TIMEOUT = 10
READ_TIMEOUT = 60
TIMEOUT = (CONNECT_TIMEOUT, READ_TIMEOUT)
ERR_PREVIEW = 800


# =================== УТИЛИТЫ ===================
def _ensure_uml_base(base: str) -> str:
    """
    Гарантируем, что базовый URL оканчивается на /uml (т.е. контекст PlantUML).
    """
    base = base.rstrip("/")
    if not base.endswith("/uml"):
        base += "/uml"
    return base


def _join_endpoint(base: str, fmt: str) -> str:
    """
    Собираем конечную точку POST: {BASE}/uml/{fmt}
    (если кто-то случайно подал базу уже с /png|/svg|/txt — подчистим)
    """
    base = _ensure_uml_base(base)
    for suffix in ("/png", "/svg", "/txt"):
        if base.endswith(suffix):
            base = base[: -len(suffix)]
    return f"{base}/{fmt.lstrip('/')}"


def _to_raw_url_from_location(location: str, fmt: str) -> str:
    """
    Сервер на POST /uml/{fmt} отвечает 302 Location: /uml/{ID} (UI-страница).
    Нам нужен “сырой” контент: /uml/{fmt}/{ID}.
    Преобразуем Location → raw-URL.
    """
    # Делаем абсолютным (на случай относительного Location)
    dummy = _join_endpoint(RAW_BASE, "dummy")  # .../uml/dummy
    abs_loc = urljoin(dummy, location)         # .../uml/{ID}

    # Разбираем до хвоста после /uml/
    # Пример: https://host/uml/SyfFKj2... → tail = "SyfFKj2..."
    parsed = urlparse(abs_loc)
    # Ищем подстроку "/uml/"
    marker = "/uml/"
    idx = parsed.path.find(marker)
    if idx == -1:
        # Странный Location, отдаём как есть (пусть упадёт дальше по Content-Type)
        return abs_loc

    tail = parsed.path[idx + len(marker):]  # всё после /uml/
    base = _ensure_uml_base(RAW_BASE)
    # Собираем raw: {BASE}/uml/{fmt}/{tail}
    return f"{base}/{fmt}/{tail}"


def _request_upstream(fmt: str, code: str) -> requests.Response:
    if fmt not in ("png", "svg", "txt"):
        raise HTTPException(400, detail="format must be png/svg/txt")
    if not code or not code.strip():
        raise HTTPException(400, detail="Empty PlantUML code")

    url = _join_endpoint(RAW_BASE, fmt)
    headers = {
        "Content-Type": "text/plain; charset=utf-8",
        "Accept": "*/*",
    }

    log.info("POST %s (len=%d)", url, len(code))

    # ВАЖНО: не следуем редиректам автоматически
    try:
        resp = requests.post(
            url,
            data=code.encode("utf-8"),
            headers=headers,
            timeout=TIMEOUT,
            allow_redirects=False,
        )
    except requests.RequestException as e:
        raise HTTPException(502, detail=f"PlantUML network error: {e}")

    # 301/302/303 → сервер дал UI-ссылку /uml/{ID}. Переклеиваем на /uml/<fmt>/{ID} и делаем GET.
    if resp.status_code in (301, 302, 303) and resp.headers.get("Location"):
        loc = resp.headers["Location"]
        raw_url = _to_raw_url_from_location(loc, fmt)
        log.info("FOLLOW as GET %s", raw_url)
        try:
            final = requests.get(raw_url, timeout=TIMEOUT)
        except requests.RequestException as e:
            raise HTTPException(502, detail=f"PlantUML redirect fetch error: {e}")

        ctype = (final.headers.get("Content-Type") or "").lower()
        if final.status_code != 200:
            preview = (final.text or "")[:ERR_PREVIEW]
            raise HTTPException(502, detail=f"PlantUML {final.status_code}: {preview}")
        if "text/html" in ctype:
            preview = (final.text or "")[:ERR_PREVIEW]
            raise HTTPException(502, detail=f"Got HTML UI instead of {fmt}. Preview: {preview}")

        return final

    # Прямой ответ без редиректа
    ctype = (resp.headers.get("Content-Type") or "").lower()
    if resp.status_code != 200:
        preview = (resp.text or "")[:ERR_PREVIEW]
        raise HTTPException(502, detail=f"PlantUML {resp.status_code}: {preview}")
    if "text/html" in ctype:
        preview = (resp.text or "")[:ERR_PREVIEW]
        raise HTTPException(
            502,
            detail=f"Upstream returned HTML UI instead of {fmt}. Requested: {url}. Preview: {preview}"
        )

    return resp


# =================== ЭНДПОЙНТЫ ===================
@router.post("/render_pluntuml")
def render_plantuml(
    fmt: str,
    code: str = Body(..., embed=True, description="PlantUML code as raw string"),
):
    """
    POST /render_pluntuml?fmt=png|svg|txt
    Body: {"code": "@startuml\\nAlice -> Bob: Hi\\n@enduml"}
    """
    resp = _request_upstream(fmt, code)

    if fmt == "png":
        return Response(content=resp.content, media_type="image/png")
    elif fmt == "svg":
        # пробрасываем Content-Type апстрима (часто 'image/svg+xml')
        return Response(content=resp.content, media_type=resp.headers.get("Content-Type", "image/svg+xml"))
    else:  # txt
        # текст всегда в UTF-8
        return Response(content=resp.text, media_type="text/plain; charset=utf-8")
