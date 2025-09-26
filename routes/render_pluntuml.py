# routes/render_plantuml.py
# -*- coding: utf-8 -*-

from fastapi import APIRouter, HTTPException, Body, Response
import requests, os, logging

router = APIRouter()
log = logging.getLogger("plantuml")

# === КОНФИГ, идентичный скрипту ===
RAW_BASE = os.getenv("PLANTUML_URL", "https://my-pluntuml.onrender.com/uml").strip()

CONNECT_TIMEOUT = 10
READ_TIMEOUT = 60
TIMEOUT = (CONNECT_TIMEOUT, READ_TIMEOUT)
ERR_PREVIEW = 800

# === ТОЧНО как в скрипте: нормализация базового URL и формата ===
def _join_endpoint(base: str, fmt: str) -> str:
    base = base.rstrip("/")
    for suffix in ("/png", "/svg", "/txt"):
        if base.endswith(suffix):
            base = base[: -len(suffix)]
    return f"{base}/{fmt.lstrip('/')}"

def _request_upstream(fmt: str, code: str):
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

    try:
        resp = requests.post(
            url,
            data=code.encode("utf-8"),
            headers=headers,
            timeout=TIMEOUT,
        )
    except requests.RequestException as e:
        raise HTTPException(502, detail=f"PlantUML network error: {e}")

    ctype = (resp.headers.get("Content-Type") or "").lower()

    # ТОЧНО как в скрипте: если HTML — значит не тот путь (например, забыли /uml)
    if "text/html" in ctype:
        preview = (resp.text or "")[:ERR_PREVIEW]
        raise HTTPException(
            502,
            detail=(
                "Upstream returned HTML UI instead of image/text. "
                f"Check PLANTUML_URL ('{RAW_BASE}') and context path (/uml). "
                f"Requested: {url}. Preview: {preview}"
            ),
        )

    if resp.status_code != 200:
        preview = (resp.text or "")[:ERR_PREVIEW]
        raise HTTPException(502, detail=f"PlantUML {resp.status_code}: {preview}")

    return resp

# === ЭНДПОЙНТ 1: точная копия интерфейса (fmt в query, body = {"code": "..."} ) ===
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
        # пробрасываем content-type апстрима, если задан; иначе дефолт
        return Response(content=resp.content, media_type=resp.headers.get("Content-Type", "image/svg+xml"))
    else:  # txt
        return Response(content=resp.text, media_type="text/plain; charset=utf-8")
