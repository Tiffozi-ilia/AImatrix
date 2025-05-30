from fastapi import APIRouter, Body
import pandas as pd
import requests
import json

router = APIRouter()

RENDER_URL = "https://aimatrix-e8zs.onrender.com"

@router.post("/pyrus_mapping")
async def pyrus_mapping(url: str = Body(...)):
    try:
        # 1. Получаем данные от Pyrus
        raw = requests.get(f"{RENDER_URL}/json")
        raw.raise_for_status()
        pyrus_json = raw.json()

        # 2. Строим task_map
        rows = []
        for task in pyrus_json.get("tasks", []):
            fields = {field["name"]: field.get("value", "") for field in task.get("fields", [])}
            matrix_id = fields.get("matrix_id", "").strip()
            task_id = task.get("id")
            if matrix_id:
                rows.append({"id": matrix_id, "task_id": task_id})
        task_map = {row["id"]: row["task_id"] for row in rows}

        # 3. Формируем payload как строку
        payload = json.dumps(url)
        headers = {"Content-Type": "application/json"}

        # 4. Обращаемся к updated
        updated = requests.post(f"{RENDER_URL}/xmind-updated", data=payload, headers=headers)
        updated.raise_for_status()
        updated_data = updated.json().get("json", [])

        # 5. Обращаемся к delete
        deleted = requests.post(f"{RENDER_URL}/xmind-delete", data=payload, headers=headers)
        deleted.raise_for_status()
        deleted_data = deleted.json().get("json", [])

        # 6. Обогащаем результат task_id
        enriched = []
        for item in updated_data:
            item["task_id"] = task_map.get(item["id"])
            item["action"] = "update"
            enriched.append(item)

        for item in deleted_data:
            item["task_id"] = task_map.get(item["id"])
            item["action"] = "delete"
            enriched.append(item)

        return {"actions": enriched}

    except Exception as e:
        return {"error": str(e)}
