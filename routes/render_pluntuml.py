from fastapi import APIRouter, HTTPException, Body, Response
import requests
import os

router = APIRouter()

PLANTUML_URL = os.getenv("PLANTUML_URL", "https://my-plantuml.onrender.com").rstrip("/")

@router.post("/render_pluntuml")
def render_plantuml(
    fmt: str,
    code: str = Body(..., embed=True, description="PlantUML code as raw string"),
):
    """
    POST /render/png  или  /render/svg
    Body: {"code": "@startuml\nAlice -> Bob: Hi\n@enduml"}
    """
    fmt = fmt.lower()
    if fmt not in ("png", "svg", "txt"):
        raise HTTPException(400, detail="format must be png/svg/txt")

    if not code.strip():
        raise HTTPException(400, detail="Empty PlantUML code")

    try:
        resp = requests.post(
            f"{PLANTUML_URL}/{fmt}",
            data=code.encode("utf-8"),
            headers={"Content-Type": "text/plain"},
            timeout=20,
        )
    except requests.RequestException as e:
        raise HTTPException(502, detail=f"PlantUML server error: {e}")

    if resp.status_code != 200:
        raise HTTPException(502, detail=resp.text or f"PlantUML returned {resp.status_code}")

    media_type = (
        "image/png" if fmt == "png" else "image/svg+xml" if fmt == "svg" else "text/plain"
    )
    return Response(content=resp.content, media_type=media_type)
