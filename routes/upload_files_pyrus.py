# routers/pyrus_simple.py
import json
from typing import Optional, Union
import requests
from fastapi import APIRouter, HTTPException, Query, Body

from utils.data_loader import get_pyrus_token

router = APIRouter()
PYRUS_API = "https://pyrus.sovcombank.ru/api/v4"

def _pyrus_headers():
    return {"Authorization": f"Bearer {get_pyrus_token()}"}

@router.post("/upload_files_pyrus")
async def upload_to_pyrus(
    request_data: dict = Body(...)  # Принимаем все данные из тела запроса
):
    # Извлекаем параметры из тела запроса
    filename = request_data.get("filename", "artifact.json")
    task_id = request_data.get("task_id")
    body_data = request_data.get("body")
    src_url = request_data.get("src_url")
    
    # Проверяем обязательные параметры
    if task_id is None:
        raise HTTPException(status_code=400, detail="Не указан task_id")
    
    # Проверяем, что указан ровно один источник данных
    if (src_url is None) == (body_data is None):
        raise HTTPException(status_code=400, detail="Укажите либо src_url, либо body — строго один источник.")

    # 1) Получаем байты файла
    if body_data is not None:
        try:
            # Если body_data уже является строкой, пытаемся ее распарсить
            if isinstance(body_data, str):
                parsed_data = json.loads(body_data)
                data = json.dumps(parsed_data, ensure_ascii=False).encode("utf-8")
            else:
                data = json.dumps(body_data, ensure_ascii=False, indent=2).encode("utf-8")
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Некорректный JSON: {e}")
    else:
        url = src_url.strip()
        if url.startswith("/"):
            url = f"https://files.dify.ai{url}"
        try:
            r = requests.get(url, timeout=60)
            r.raise_for_status()
            data = r.content
        except requests.exceptions.RequestException as e:
            raise HTTPException(status_code=400, detail=f"Не удалось скачать файл по src_url={url}: {e}")

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
            data=json.dumps({"text": "Файл из Dify", "attachments": [guid]}, ensure_ascii=False),
            timeout=60,
        )
        cm.raise_for_status()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Ошибка прикрепления к задаче: {e}")

    return {"status": "ok", "task_id": task_id, "filename": filename}
