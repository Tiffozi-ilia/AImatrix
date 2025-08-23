from fastapi import APIRouter, HTTPException, Query, Path
from fastapi.responses import Response
import httpx
from pathlib import Path as P

router = APIRouter()

# Координаты репозитория (если хочешь — вынеси в конфиг)
OWNER = "Tiff0zi"
REPO = "sotiio_data"
DEFAULT_REF = "main"
BASE = f"https://raw.githubusercontent.com/{OWNER}/{REPO}"

EXT_TO_CT = {
    ".json": "application/json",
    ".csv":  "text/csv",
    ".md":   "text/plain",
    ".txt":  "text/plain",
    ".yaml": "text/plain",
    ".yml":  "text/plain",
}

def guess_ct(filename: str, forced: str | None) -> str:
    if forced and forced != "auto":
        return {
            "json": "application/json",
            "csv": "text/csv",
            "text": "text/plain",
            "binary": "application/octet-stream",
        }.get(forced, "application/octet-stream")
    return EXT_TO_CT.get(P(filename).suffix.lower(), "text/plain")

@router.get("/schema/{file_name}")
async def get_schema_by_name(
    file_name: str = Path(..., description="Имя файла с расширением, без слэшей"),
    dir: str = Query("", description="Необязательная поддиректория в репозитории"),
    ref: str = Query(DEFAULT_REF, description="Ветка/тег/коммит; по умолчанию main"),
    as_: str = Query("auto", alias="as", description="Тип ответа: auto|json|csv|text|binary")
):
    # Безопасность: только имя файла
    if "/" in file_name or "\\" in file_name or ".." in file_name:
        raise HTTPException(status_code=400, detail="file_name должен быть только именем файла, без слэшей")

    filepath = f"{dir.strip('/')}/{file_name}" if dir else file_name
    url = f"{BASE}/{ref}/{filepath}"

    try:
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.get(url)
            r.raise_for_status()
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            raise HTTPException(status_code=404, detail="File not found")
        raise HTTPException(status_code=500, detail=f"GitHub fetch error: {e}")
    except httpx.HTTPError as e:
        raise HTTPException(status_code=500, detail=f"GitHub fetch error: {e}")

    ct = guess_ct(file_name, as_)
    content = r.text if ct != "application/octet-stream" else r.content
    return Response(
        content=content,
        media_type=ct,
        headers={"Content-Disposition": f'inline; filename="{file_name}"'}
    )
