from fastapi import APIRouter, Body
import pandas as pd
import requests
import json

router = APIRouter()

@router.get("/pyrus_mapping")
async def pyrus_mapping(payload: dict = Body(...)):
    url = payload.get("url")
    if not url:
        return {"error": "Missing 'url' in request body"}

    # 1. Получаем JSON из Pyrus (через Render endpoint)
    raw = requests.get("https://aimatrix-e8zs.onrender.com/json")
    pyrus_json = raw.json()

    # 2. Строим карту task_id по matrix_id
    rows = []
    for task in pyrus_json.get("tasks", []):
        fields = {f["name"]: f.get("value", "") for f in task.get("fields", [])}
        matrix_id = fields.get("matrix_id", "").strip()
        task_id = task.get("id")
        if matrix_id:
            rows.append({"id": matrix_id, "task_id": task_id})

    task_map = {row["id"]: row["task_id"] for row in rows}

    # 3. Отправляем URL в updated и delete
    updated = requests.post(
        "https://aimatrix-e8zs.onrender.com/xmind-updated",
        json={"url": url}
    ).json().get("json", [])

    deleted = requests.post(
        "https://aimatrix-e8zs.onrender.com/xmind-delete",
        json={"url": url}
    ).json().get("json", [])

    # 4. Обогащаем результат
    enriched = []
    for item in updated:
        item["task_id"] = task_map.get(item["id"])
        item["action"] = "update"
        enriched.append(item)

    for item in deleted:
        item["task_id"] = task_map.get(item["id"])
        item["action"] = "delete"
        enriched.append(item)

    return {"actions": enriched}
