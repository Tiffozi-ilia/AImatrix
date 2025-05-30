from fastapi import APIRouter, Body
import requests
import json

router = APIRouter()

@router.post("/pyrus_mapping")
async def pyrus_mapping(url: str = Body(...)):
    # 1. Получаем сырые данные от Pyrus
    pyrus_json = requests.get("https://aimatrix-e8zs.onrender.com/json").json()

    # 2. Строим map: id → task_id
    task_map = {}
    for task in pyrus_json.get("tasks", []):
        fields = {field["name"]: field.get("value", "") for field in task.get("fields", [])}
        matrix_id = fields.get("matrix_id", "").strip()
        task_id = task.get("id")
        if matrix_id:
            task_map[matrix_id] = task_id

    # 3. Передаём URL в обе процедуры
    payload = json.dumps({"url": url})
    headers = {"Content-Type": "application/json"}

    try:
        updated_resp = requests.post("https://aimatrix-e8zs.onrender.com/xmind-updated", data=payload, headers=headers)
        updated_resp.raise_for_status()
        updated = updated_resp.json().get("json", [])
    except Exception as e:
        print(f"[ERROR] xmind-updated: {e}")
        updated = []

    try:
        deleted_resp = requests.post("https://aimatrix-e8zs.onrender.com/xmind-delete", data=payload, headers=headers)
        deleted_resp.raise_for_status()
        deleted = deleted_resp.json().get("json", [])
    except Exception as e:
        print(f"[ERROR] xmind-delete: {e}")
        deleted = []

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
