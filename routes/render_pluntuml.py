from fastapi import APIRouter, HTTPException, Body, Response
import requests
import os

router = APIRouter()

PLUNTUML_URL = os.getenv("PLUNTUML_URL", "https://my-pluntuml.onrender.com").rstrip("/")


@router.post("/render_pluntuml")
def render_pluntuml(
    fmt: str,
    code: str = Body(..., embed=True, description="pluntUML code as raw string"),
):
    """
    POST /render_pluntuml?fmt=png
    Body: {"code": "@startuml\nAlice -> Bob: Hi\n@enduml"}
    """
    fmt = fmt.lower()
    if fmt not in ("png", "svg", "txt"):
        raise HTTPException(400, detail="format must be png/svg/txt")

    if not code.strip():
        raise HTTPException(400, detail="Empty PLUNTUML code")

    try:
        resp = requests.post(
            f"{PLUNTUML_URL}/{fmt}",
            data=code.encode("utf-8"),
            headers={"Content-Type": "text/plain; charset=utf-8"},
            timeout=20,
        )
    except requests.RequestException as e:
        raise HTTPException(502, detail=f"PLUNTUML server error: {e}")

    if resp.status_code != 200:
        raise HTTPException(
            502, detail=resp.text or f"pluntUML returned {resp.status_code}"
        )

    if fmt == "png":
        return Response(content=resp.content, media_type="image/png")
    elif fmt == "svg":
        return Response(content=resp.content, media_type="image/svg+xml")
    else:  # txt
        return Response(content=resp.text, media_type="text/plain; charset=utf-8")
