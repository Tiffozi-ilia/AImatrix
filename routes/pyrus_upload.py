from fastapi import APIRouter, UploadFile, File
import requests
from utils.data_loader import get_pyrus_token
from io import BytesIO  # ← добавлено

router = APIRouter()

FIELD_IDS = {
    "matrix_id": 1,
    "level": 2,
    "title": 3,
    "parent_id": 4,
    "body": 5,
    "parent_name": 8
}

FORM_ID = 484498
PYRUS_URL = "https://pyrus.sovcombank.ru/api/v4"
LOCAL_URL = "https://aimatrix-e8zs.onrender.com"


@router.post("/pyrus_upload")
async def upload_xmind(file: UploadFile = File(...)):
    token = get_pyrus_token()
    headers = {"Authorization": f"Bearer {token}"}
    file_bytes = await file.read()

    # используем BytesIO для безопасной передачи
    files_for_diff = {"xmind": (file.filename, BytesIO(file_bytes), file.content_type)}

    # 1. Получаем diff для создания
    try:
        diff_resp = requests.post(f"{LOCAL_URL}/xmind-diff", files=files_for_diff)
        diff_resp.raise_for_status()
        diff = diff_resp.json().get("json", [])
    except Exception as e:
        return {"error": f"Ошибка на этапе diff: {e}"}

    # 2. Получаем mapping, в котором уже есть update/delete
    try:
        mapping_resp = requests.get(f"{LOCAL_URL}/pyrus_mapping")
        mapping_resp.raise_for_status()
        mapped = mapping_resp.json().get("actions", [])
    except Exception as e:
        return {"error": f"Ошибка на этапе pyrus_mapping: {e}"}

    created_ids = []
    errors = []

    # 3. Создаём новые элементы в Pyrus
    for item in diff:
        payload = {
            "form_id": FORM_ID,
            "field_values": [
                {"id": FIELD_IDS["matrix_id"], "value": item["id"]},
                {"id": FIELD_IDS["title"], "value": item["title"]},
                {"id": FIELD_IDS["body"], "value": item["body"]},
                {"id": FIELD_IDS["level"], "value": item["level"]},
                {"id": FIELD_IDS["parent_id"], "value": item["parent_id"]},
                {"id": FIELD_IDS["parent_name"], "value": item.get("parent_name", "")}
            ]
        }
        try:
            r = requests.post(f"{PYRUS_URL}/tasks", json=payload, headers=headers)
            r.raise_for_status()
            created_ids.append(item["id"])
        except Exception as e:
            errors.append({"id": item["id"], "error": str(e)})

    # 4. Выполняем update и delete
    for item in mapped:
        task_id = item.get("task_id")
        if not task_id:
            continue
        try:
            if item["action"] == "update":
                comment = f"Обновлено:\n\n**{item['title']}**\n{item['body']}"
                requests.post(
                    f"{PYRUS_URL}/tasks/{task_id}/comments",
                    json={"text": comment},
                    headers=headers
                ).raise_for_status()
            elif item["action"] == "delete":
                requests.delete(f"{PYRUS_URL}/tasks/{task_id}", headers=headers).raise_for_status()
        except Exception as e:
            errors.append({"id": item["id"], "error": str(e)})

    return {
        "status": "done",
        "created": len(created_ids),
        "updated": len([x for x in mapped if x["action"] == "update"]),
        "deleted": len([x for x in mapped if x["action"] == "delete"]),
        "pyrus": {
            "created_ids": created_ids,
            "errors": errors
        }
    }
