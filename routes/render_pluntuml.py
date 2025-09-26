from fastapi import APIRouter, HTTPException, Body, Response
import requests
import os
import logging

# Базовая конфигурация логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

router = APIRouter()

# Опечатка исправлена
PLANTUML_URL = os.getenv("PLANTUML_URL", "https://www.plantuml.com/plantuml").rstrip("/")


# Опечатки исправлены
@router.post("/render_plantuml")
def render_plantuml(
    fmt: str,
    code: str = Body(..., embed=True, description="PlantUML code as raw string"),
):
    """
    POST /render_plantuml?fmt=png
    Body: {"code": "@startuml\\nAlice -> Bob: Hi\\n@enduml"}
    """
    fmt = fmt.lower()
    logging.info(f"Received request to render PlantUML with format: {fmt}")

    if fmt not in ("png", "svg", "txt"):
        raise HTTPException(400, detail="format must be png/svg/txt")

    if not code.strip():
        raise HTTPException(400, detail="Empty PlantUML code")

    target_url = f"{PLANTUML_URL}/{fmt}"
    
    logging.info(f"Proxying request to upstream PlantUML server: {target_url}")

    try:
        resp = requests.post(
            target_url,
            data=code.encode("utf-8"),
            headers={"Content-Type": "text/plain; charset=utf-8"},
            timeout=20,
        )
    except requests.RequestException as e:
        logging.error(f"Failed to connect to PlantUML server at {target_url}. Error: {e}")
        # Опечатка исправлена
        raise HTTPException(502, detail=f"PlantUML server connection error: {e}")

    if resp.status_code != 200:
        logging.error(f"Upstream PlantUML server returned non-200 status: {resp.status_code}")
        logging.error(f"Upstream response body: {resp.text[:500]}")
        # Опечатка исправлена
        raise HTTPException(
            502, detail=resp.text or f"PlantUML server returned status {resp.status_code}"
        )

    logging.info(f"Successfully rendered PlantUML diagram. Returning {fmt} content.")

    if fmt == "png":
        return Response(content=resp.content, media_type="image/png")
    elif fmt == "svg":
        return Response(content=resp.content, media_type="image/svg+xml")
    else:  # txt
        return Response(content=resp.text, media_type="text/plain; charset=utf-8")
