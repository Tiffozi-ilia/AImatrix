from fastapi import APIRouter, Body
import pandas as pd
import requests
import json

router = APIRouter()

@router.post("/pyrus_mapping")
async def pyrus_mapping(url: str = Body(...)):
    # 1. Получаем сырые данные от Pyrus
    raw = requests.get("https://aimatrix-e8zs.onrender.com/json")
    pyrus_json = raw.json()
    
    # 2. Строим map: id → task_id
    rows = []
    for task in pyrus_json.get("tasks", []):
        fields = {field["name"]: field.get("value", "") for field in task.get("fields", [])}
        matrix_id = fields.get("matrix_id", "").strip()
        task_id = task.get("id")
        if matrix_id:
            rows.append({"id": matrix_id, "task_id": task_id})
    task_map = {row["id"]: row["task_id"] for row in rows}

    # 3. Получаем updated и deleted по переданному url
    updated = requests.post("https://aimatrix-e8zs.onrender.com/xmind-updated", json=url).json().get("json", [])
    deleted = requests.post("https://aimatrix-e8zs.onrender.com/xmind-delete", json=url).json().get("json", [])

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
