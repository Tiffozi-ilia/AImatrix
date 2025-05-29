from fastapi import APIRouter
import pandas as pd
import requests
import io
import json

router = APIRouter()

@router.get("/pyrus_mapping")
async def pyrus_mapping():
    # 1. Получаем сырые данные от Pyrus (JSON → CSV)
    raw = requests.get("https://aimatrix-e8zs.onrender.com/json")  # ← если у тебя есть endpoint для json из Pyrus
    pyrus_json = raw.json()
    
    # 2. Парсим в task_map
    rows = []
    for task in pyrus_json.get("tasks", []):
        fields = {field["name"]: field.get("value", "") for field in task.get("fields", [])}
        matrix_id = fields.get("matrix_id", "").strip()
        task_id = task.get("id")
        if matrix_id:
            rows.append({"id": matrix_id, "task_id": task_id})
    
    task_map = {row["id"]: row["task_id"] for row in rows}

    # 3. Получаем изменения из Render-API
    updated = requests.get("https://aimatrix-e8zs.onrender.com/xmind-updated").json().get("json", [])
    deleted = requests.get("https://aimatrix-e8zs.onrender.com/xmind-delete").json().get("json", [])

    # 4. Сборка результата
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
