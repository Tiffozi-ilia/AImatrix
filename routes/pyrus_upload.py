from fastapi import APIRouter, UploadFile, File
import requests
from utils.data_loader import get_pyrus_token

router = APIRouter()

FIELD_IDS = {
    "matrix_id": 1,
    "level": 2,
    "title": 3,
    "parent_id": 4,
    "body": 5,
    "parent_name": 8
}

FORM_ID = 2309262
PYRUS_URL = "https://api.pyrus.com/v4"
LOCAL_URL = "http://localhost:8000"

@router.post("/pyrus_upload")
async def upload_xmind(file: UploadFile = File(...)):
    token = get_pyrus_token()
    headers = {"Authorization": f"Bearer {token}"}

    files = {"xmind": (file.filename, await file.read(), file.content_type)}

    # 1. diff
    diff = requests.post(f"{LOCAL_URL}/xmind-diff", files=files).json().get("json", [])
    file.file.seek(0)
    # 2. updated
    updated = requests.post(f"{LOCAL_URL}/xmind-updated", files=files).json().get("json", [])
    file.file.seek(0)
    # 3. deleted
    deleted = requests.post(f"{LOCAL_URL}/xmind-delete", files=files).json().get("json", [])

    # 4. mapping
    mapped = requests.get(f"{LOCAL_URL}/pyrus_mapping").json().get("actions", [])

    created_responses = []
    errors = []

    # 5. POST new
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
            created_responses.append(item["id"])
        except Exception as e:
            errors.append({"id": item["id"], "error": str(e)})

    # 6. Update/delete
    for item in mapped:
        task_id = item.get("task_id")
        if not task_id:
            continue
        if item["action"] == "update":
            comment = f"Обновлено:\n\n**{item['title']}**\n{item['body']}"
            try:
                requests.post(f"{PYRUS_URL}/tasks/{task_id}/comments", json={"text": comment}, headers=headers).raise_for_status()
            except Exception as e:
                errors.append({"id": item["id"], "error": str(e)})
        elif item["action"] == "delete":
            try:
                requests.delete(f"{PYRUS_URL}/tasks/{task_id}", headers=headers).raise_for_status()
            except Exception as e:
                errors.append({"id": item["id"], "error": str(e)})

    return {
        "status": "done",
        "created": len(diff),
        "updated": len([x for x in mapped if x['action'] == 'update']),
        "deleted": len([x for x in mapped if x['action'] == 'delete']),
        "pyrus": {
            "created_ids": created_responses,
            "errors": errors
        }
    }
