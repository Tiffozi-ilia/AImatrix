from fastapi import APIRouter, Body
import pandas as pd
import requests
import json

router = APIRouter()

@router.post("/pyrus_mapping")
async def pyrus_mapping(url: str = Body(...)):
    # Получаем задачи из Pyrus
    raw = requests.get("https://aimatrix-e8zs.onrender.com/json")
    pyrus_json = raw.json()

    # Формируем task_map: {matrix_id → task_id}
    task_map = {}
    for task in pyrus_json.get("tasks", []):
        fields = {f["name"]: f.get("value", "") for f in task.get("fields", [])}
        matrix_id = fields.get("matrix_id", "").strip()
        task_id = task.get("id")
        if matrix_id:
            task_map[matrix_id] = task_id

    # Вызываем xmind-updated и xmind-delete, передаём URL
    updated = requests.post(
        "https://aimatrix-e8zs.onrender.com/xmind-updated",
        json=url
    ).json().get("json", [])

    deleted = requests.post(
        "https://aimatrix-e8zs.onrender.com/xmind-delete",
        json=url
    ).json().get("json", [])

    # Обогащаем действия task_id
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
