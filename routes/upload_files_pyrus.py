# routers/pyrus_simple.py
import json
from typing import Union
import requests
from fastapi import APIRouter, HTTPException, Query, Body

from utils.data_loader import get_pyrus_token

router = APIRouter()
PYRUS_API = "https://pyrus.sovcombank.ru/api/v4"

def _pyrus_headers():
    return {"Authorization": f"Bearer {get_pyrus_token()}"}

@router.post("/upload_files_pyrus")
def upload_to_pyrus(
    task_id: int = Query(..., description="ID задачи в Pyrus"),
    filename: str = Query("artifact.json", description="Имя файла в Pyrus"),
    payload: Union[dict, list] = Body(..., description="JSON-данные для загрузки"),
):
    # 1) Подготавливаем данные файла
    try:
        data = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Некорректный JSON: {e}")

    # 2) Загружаем файл в Pyrus
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

    # 3) Прикрепляем к задаче
    try:
        cm = requests.post(
            f"{PYRUS_API}/tasks/{task_id}/comments",
            headers={**_pyrus_headers(), "Content-Type": "application/json"},
            json={"text": "Файл из Dify", "attachments": [guid]},
            timeout=60,
        )
        cm.raise_for_status()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Ошибка прикрепления к задаче: {e}")

    return {"status": "ok", "task_id": task_id, "filename": filename, "guid": guid}
