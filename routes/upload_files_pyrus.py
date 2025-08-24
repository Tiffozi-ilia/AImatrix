# routers/pyrus_simple.py
import json
import requests
from fastapi import APIRouter, HTTPException, Query

from utils.data_loader import get_pyrus_token

router = APIRouter()
PYRUS_API = "https://pyrus.sovcombank.ru/api/v4"

def _pyrus_headers():
    return {"Authorization": f"Bearer {get_pyrus_token()}"}

@router.post("/upload_files_pyrus")
def upload_url_to_task(
    task_id: int = Query(..., description="ID задачи в Pyrus"),
    src_url: str = Query(..., description="Ссылка на JSON (presigned)"),
    filename: str = Query("artifact.json", description="Имя файла в Pyrus"),
):
    # 1. Скачиваем файл по ссылке
    try:
        r = requests.get(src_url, timeout=60)
        r.raise_for_status()
        data = r.content
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Не удалось скачать файл: {e}")

    # 2. Загружаем файл в Pyrus
    try:
        up = requests.post(
            f"{PYRUS_API}/files/upload",
            headers=_pyrus_headers(),
            files={"file": (filename, data, "application/json")},
            timeout=60,
        )
        up.raise_for_status()
        guid = up.json()["guid"]
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Ошибка загрузки в Pyrus: {e}")

    # 3. Прикрепляем к задаче
    payload = {"text": "Файл из Dify", "attachments": [guid]}
    try:
        cm = requests.post(
            f"{PYRUS_API}/tasks/{task_id}/comments",
            headers={**_pyrus_headers(), "Content-Type": "application/json"},
            data=json.dumps(payload),
            timeout=60,
        )
        cm.raise_for_status()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Ошибка прикрепления к задаче: {e}")

    return {"status": "ok", "task_id": task_id, "filename": filename}
