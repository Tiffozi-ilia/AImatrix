from fastapi import APIRouter, Body
from pydantic import BaseModel
import requests
import json

router = APIRouter()

class UrlInput(BaseModel):
    url: str

@router.post("/pyrus_mapping")
async def pyrus_mapping(body: UrlInput):
    url = body.url

    # 1. Получаем данные из Pyrus
    pyrus_json = requests.get("https://aimatrix-e8zs.onrender.com/json").json()
    task_map = {}
    for task in pyrus_json.get("tasks", []):
        fields = {field["name"]: field.get("value", "") for field in task.get("fields", [])}
        matrix_id = fields.get("matrix_id", "").strip()
        task_id = task.get("id")
        if matrix_id:
            task_map[matrix_id] = task_id

    # 2. Передаём url в updated/delete
    headers = {"Content-Type": "application/json"}
    payload = json.dumps({"url": url})

    updated = requests.post("https://aimatrix-e8zs.onrender.com/xmind-updated", data=payload, headers=headers).json().get("json", [])
    deleted = requests.post("https://aimatrix-e8zs.onrender.com/xmind-delete", data=payload, headers=headers).json().get("json", [])

    # 3. Сборка результата
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
