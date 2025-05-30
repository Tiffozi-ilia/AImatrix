from fastapi import APIRouter, Body
import zipfile, io, json, requests
import pandas as pd
from utils.data_loader import get_data
from utils.diff_engine import format_as_markdown
from utils.xmind_parser import flatten_xmind_nodes

router = APIRouter()

# === DIFF ======================================================================
@router.post("/pyrus_mapping")
async def pyrus_mapping(url: str = Body(...)):
    import requests
    import json

    # Получаем Pyrus JSON
    try:
        raw = requests.get("https://aimatrix-e8zs.onrender.com/json")
        pyrus_json = raw.json()
    except Exception as e:
        return {"error": f"Pyrus JSON fetch failed: {str(e)}"}

    task_map = {}
    for task in pyrus_json.get("tasks", []):
        fields = {field["name"]: field.get("value", "") for field in task.get("fields", [])}
        matrix_id = fields.get("matrix_id", "").strip()
        task_id = task.get("id")
        if matrix_id:
            task_map[matrix_id] = task_id

    headers = {"Content-Type": "application/json"}
    payload = json.dumps(url)

    # UPDATED
    try:
        updated_resp = requests.post("https://aimatrix-e8zs.onrender.com/xmind-updated", data=payload, headers=headers)
        if updated_resp.status_code != 200:
            return {"error": f"updated failed: {updated_resp.status_code}", "body": updated_resp.text}
        updated = updated_resp.json().get("json", [])
    except Exception as e:
        return {"error": f"Exception in xmind-updated: {str(e)}"}

    # DELETED
    try:
        deleted_resp = requests.post("https://aimatrix-e8zs.onrender.com/xmind-delete", data=payload, headers=headers)
        if deleted_resp.status_code != 200:
            return {"error": f"deleted failed: {deleted_resp.status_code}", "body": deleted_resp.text}
        deleted = deleted_resp.json().get("json", [])
    except Exception as e:
        return {"error": f"Exception in xmind-delete: {str(e)}"}

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


# === SHARED PARSERS ============================================================
def extract_xmind_nodes(file: io.BytesIO):
    with zipfile.ZipFile(file) as z:
        content_json = json.loads(z.read("content.json"))

    def walk(node, parent_id="", level=0):
        label = node.get("labels", [])
        node_id = label[0] if label else None
        title = node.get("title", "")
        body = node.get("notes", {}).get("plain", {}).get("content", "")
        rows = []
        if node_id:
            rows.append({
                "id": node_id.strip(),
                "title": title.strip(),
                "body": body.strip(),
                "level": str(level),
                "parent_id": parent_id.strip()
            })
        for child in node.get("children", {}).get("attached", []):
            rows.extend(walk(child, node_id, level + 1))
        return rows

    root_topic = content_json[0].get("rootTopic", {})
    return pd.DataFrame(walk(root_topic))


def extract_pyrus_data():
    raw = get_data()
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            raw = [json.loads(line) for line in raw.splitlines() if line.strip()]
    if isinstance(raw, dict):
        for value in raw.values():
            if isinstance(value, list):
                raw = value
                break
    if not isinstance(raw, list):
        raise ValueError("Pyrus data is not a list")

    rows = []
    for task in raw:
        fields = {field["name"]: field.get("value", "") for field in task.get("fields", [])}
        rows.append({
            "id": fields.get("matrix_id", "").strip(),
            "title": fields.get("title", "").strip(),
            "body": fields.get("body", "").strip(),
            "level": str(fields.get("level", "")).strip(),
            "parent_id": fields.get("parent_id", "").strip()
        })
    return pd.DataFrame(rows)

# === UPDATED ===================================================================
@router.post("/xmind-updated")
async def detect_updated_items(url: str = Body(...)):
    content = requests.get(url).content
    xmind_df = extract_xmind_nodes(io.BytesIO(content))
    pyrus_df = extract_pyrus_data()

    merged = pd.merge(xmind_df, pyrus_df, on="id", suffixes=("_xmind", "_pyrus"))
    diffs = merged[(merged["title_xmind"] != merged["title_pyrus"]) |
                   (merged["body_xmind"] != merged["body_pyrus"])]

    records = diffs.rename(columns={
        "title_xmind": "title",
        "body_xmind": "body",
        "parent_id_xmind": "parent_id",
        "level_xmind": "level"
    })[["id", "parent_id", "level", "title", "body"]].to_dict(orient="records")

    return {
        "content": format_as_markdown(records),
        "json": records
    }

# === DELETE ====================================================================
@router.post("/xmind-delete")
async def detect_deleted_items(url: str = Body(...)):
    content = requests.get(url).content
    xmind_df = extract_xmind_nodes(io.BytesIO(content))
    pyrus_df = extract_pyrus_data()

    deleted = pyrus_df[~pyrus_df["id"].isin(xmind_df["id"])]
    records = deleted[["id", "parent_id", "level", "title", "body"]].to_dict(orient="records")

    return {
        "content": format_as_markdown(records),
        "json": records
    }

# === MAPPING ===================================================================
@router.post("/pyrus_mapping")
async def pyrus_mapping(url: str = Body(...)):
    import requests
    import json

    # 1. Получаем task_id из Pyrus
    try:
        raw = requests.get("https://aimatrix-e8zs.onrender.com/json")
        pyrus_json = raw.json()
    except Exception as e:
        return {"error": f"Ошибка при загрузке JSON из Pyrus: {str(e)}"}

    rows = []
    for task in pyrus_json.get("tasks", []):
        fields = {field["name"]: field.get("value", "") for field in task.get("fields", [])}
        matrix_id = fields.get("matrix_id", "").strip()
        task_id = task.get("id")
        if matrix_id:
            rows.append({"id": matrix_id, "task_id": task_id})
    task_map = {row["id"]: row["task_id"] for row in rows}

    headers = {"Content-Type": "application/json"}
    payload = json.dumps(url)

    # 2. Получаем updated
    try:
        updated_resp = requests.post("https://aimatrix-e8zs.onrender.com/xmind-updated", data=payload, headers=headers)
        updated = updated_resp.json().get("json", [])
    except Exception as e:
        return {"error": f"Ошибка при вызове xmind-updated: {str(e)}"}

    # 3. Получаем deleted
    try:
        deleted_resp = requests.post("https://aimatrix-e8zs.onrender.com/xmind-delete", data=payload, headers=headers)
        deleted = deleted_resp.json().get("json", [])
    except Exception as e:
        return {"error": f"Ошибка при вызове xmind-delete: {str(e)}"}

    # 4. Сборка enriched-таблицы
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
