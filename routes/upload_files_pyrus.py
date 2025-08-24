# routers/pyrus_simple.py
import json
from typing import Optional
import requests
from fastapi import APIRouter, HTTPException, Query, Request

from utils.data_loader import get_pyrus_token

router = APIRouter()
PYRUS_API = "https://pyrus.sovcombank.ru/api/v4"

def _pyrus_headers():
    return {"Authorization": f"Bearer {get_pyrus_token()}"}

@router.post("/upload_files_pyrus")
async def upload_to_pyrus(
    request: Request,
    task_id: int = Query(..., description="ID задачи в Pyrus"),
    filename: str = Query("artifact.json", description="Имя файла в Pyrus"),
    src_url: Optional[str] = Query(None, description="Presigned URL или относительный /<id>/file.json"),
):
    mode = ""
    data: bytes = b""

    # 1) URL-режим (на случай старых вызовов)
    if src_url:
        url = src_url.strip()
        if url.startswith("/"):
            url = f"https://files.dify.ai{url}"
        try:
            r = requests.get(url, timeout=60)
            r.raise_for_status()
            data = r.content
            mode = "src_url"
        except requests.exceptions.RequestException as e:
            raise HTTPException(status_code=400, detail=f"Не удалось скачать файл по src_url={url}: {e}")
    else:
        # 2) Тело запроса: извлечь «настоящий» JSON (учитываем обёртку Dify)
        ct = request.headers.get("content-type", "").lower()
        raw_body = await request.body()

        # Попробуем распарсить как JSON
        payload = None
        try:
            parsed = json.loads(raw_body.decode("utf-8"))
            # Dify-обёртка: {"uploadToPyrus": { ..., "requestBody": {...} }}
            if isinstance(parsed, dict):
                if "requestBody" in parsed:
                    payload = parsed["requestBody"]
                else:
                    # Может быть {"filename":..., "task_id":..., "requestBody": {...}}
                    # или сразу полноценный JSON отчёта
                    # Если похож на отчёт — берём его целиком
                    payload = parsed.get("uploadToPyrus", parsed)
        except Exception:
            # Не JSON (напр. multipart) — оставим raw_body как есть
            payload = None

        if payload is not None:
            try:
                data = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
                mode = "body(json)"
            except Exception as e:
                raise HTTPException(status_code=400, detail=f"Не удалось сериализовать JSON: {e}")
        else:
            # Если не распарсили JSON — шлём сырые байты (например, прислали multipart с чистым JSON-блоком)
            data = raw_body
            mode = "body(raw)"

        if not data:
            raise HTTPException(status_code=400, detail=f"Пустое тело запроса (mode={mode}).")

    # 3) Загрузка файла в Pyrus
    up = requests.post(
        f"{PYRUS_API}/files/upload",
        headers=_pyrus_headers(),
        files={"file": (filename.lstrip("\\/"), data, "application/json; charset=utf-8")},
        timeout=60,
    )
    if not up.ok:
        raise HTTPException(status_code=up.status_code, detail=f"Pyrus files/upload error: {up.text}")

    guid = up.json().get("guid")
    if not guid:
        raise HTTPException(status_code=502, detail=f"Pyrus files/upload: no guid in response: {up.text}")

    # 4) Прикрепление к задаче
    cm = requests.post(
        f"{PYRUS_API}/tasks/{task_id}/comments",
        headers={**_pyrus_headers(), "Content-Type": "application/json"},
        data=json.dumps({"text": "Файл из Dify", "attachments": [guid]}, ensure_ascii=False),
        timeout=60,
    )
    if not cm.ok:
        raise HTTPException(status_code=cm.status_code, detail=f"Pyrus tasks/{task_id}/comments error: {cm.text}")

    return {"status": "ok", "task_id": task_id, "filename": filename, "mode": mode, "bytes": len(data)}
