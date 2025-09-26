from fastapi import APIRouter, HTTPException, Body, Response
import requests
import os

router = APIRouter()

RAW_BASE = os.getenv("PLANTUML_URL", "https://my-pluntuml.onrender.com").strip()

CONNECT_TIMEOUT = 10
READ_TIMEOUT = 60
TIMEOUT = (CONNECT_TIMEOUT, READ_TIMEOUT)
ERR_PREVIEW = 800

def _join_endpoint(base: str, fmt: str) -> str:
    base = base.rstrip("/")
    # Срежем случайные форматы на конце, если вдруг задали криво
    for suffix in ("/png", "/svg", "/txt"):
        if base.endswith(suffix):
            base = base[: -len(suffix)]
    return f"{base}/{fmt.lstrip('/')}"

@router.post("/render_pluntuml")
def render_plantuml(
    fmt: str,
    code: str = Body(..., embed=True, description="PlantUML code as raw string"),
):
    """
    POST /render_pluntuml?fmt=png|svg|txt
    Body: {"code": "@startuml\\nAlice -> Bob: Hi\\n@enduml"}
    """
    fmt = fmt.lower()
    if fmt not in ("png", "svg", "txt"):
        raise HTTPException(400, detail="format must be png/svg/txt")

    if not code or not code.strip():
        raise HTTPException(400, detail="Empty PlantUML code")

    url = _join_endpoint(RAW_BASE, fmt)

    try:
        resp = requests.post(
            url,
            data=code.encode("utf-8"),
            headers={"Content-Type": "text/plain; charset=utf-8", "Accept": "*/*"},
            timeout=TIMEOUT,
        )
    except requests.RequestException as e:
        raise HTTPException(502, detail=f"PlantUML network error: {e}")

    # Если сервер вернул HTML (UI) — значит URL не тот (например, забыли /uml)
    ctype = resp.headers.get("Content-Type", "")
    if "text/html" in ctype.lower():
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

    if fmt == "png":
        return Response(content=resp.content, media_type="image/png")
    if fmt == "svg":
        # пробросим исходный медиа-тип, если пришёл корректный
        return Response(content=resp.content, media_type=resp.headers.get("Content-Type", "image/svg+xml"))
    # txt
    return Response(content=resp.text, media_type="text/plain; charset=utf-8")
