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
LOCAL_URL = "https://aimatrix-e8zs.onrender.com"

def safe_post_json(url: str, files: dict):
    try:
        resp = requests.post(url, files=files)
        resp.raise_for_status()
        return resp.json().get("json", [])
    except Exception as e:
        print(f"[ERROR] {url} →", e)
        return []

@router.post("/pyrus_upload")
async def upload_xmind(file: UploadFile = File(...)):
    token = get_pyrus_token()
    headers = {"Authorization": f"Bearer {token}"}
    file_bytes = await file.read()

    def get_files():
        return {"xmind": (file.filename, file_bytes, file.content_type)}

    # 1. diff, updated, deleted
    diff = safe_post_json(f"{LOCAL_URL}/xmind-diff", get_files())
    updated = safe_post_json(f"{LOCAL_URL}/xmind-updated", get_files())
    deleted = safe_post_json(f"{LOCAL_URL}/xmind-delete", get_files())

    # 2. mapping
    try:
        mapped = requests.get(f"{LOCAL_URL}/pyrus_mapping").json().get("actions", [])
    except Exception as e:
        print("[ERROR] /pyrus_mapping →", e)
        mapped = []

    created_ids = []
    errors = []

    # 3. create
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

    # 4. update/delete
    for item in mapped:
        task_id = item.get("task_id")
        if not task_id:
            continue
        try:
            if item["action"] == "update":
                comment = f"Обновлено:\n\n**{item['title']}**\n{item['body']}"
                requests.post(f"{PYRUS_URL}/tasks/{task_id}/comments",
                              json={"text": comment}, headers=headers).raise_for_status()
            elif item["action"] == "delete":
                requests.delete(f"{PYRUS_URL}/tasks/{task_id}", headers=headers).raise_for_status()
        except Exception as e:
            errors.append({"id": item["id"], "error": str(e)})

    return {
        "status": "done",
        "created": len(created_ids),
        "updated": len([x for x in mapped if x['action'] == 'update']),
        "deleted": len([x for x in mapped if x['action'] == 'delete']),
        "pyrus": {
            "created_ids": created_ids,
            "errors": errors
        }
    }
