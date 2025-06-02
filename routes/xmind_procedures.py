from fastapi import APIRouter, Body
import zipfile, io, json, requests
import pandas as pd
from utils.data_loader import get_data
from utils.diff_engine import format_as_markdown

router = APIRouter()

# === HELPERS ===

def extract_xmind_nodes(file: io.BytesIO):
    with zipfile.ZipFile(file) as z:
        content_json = json.loads(z.read("content.json"))

    def walk(node, parent_id="", level=0):
        label = node.get("labels", [])
        node_id = label[0].strip() if label else ""
        title = node.get("title", "").strip()
        body = node.get("notes", {}).get("plain", {}).get("content", "").strip()
        rows = []
        if node_id:
            rows.append({
                "id": node_id,
                "title": title,
                "body": body,
                "level": int(level),
                "parent_id": parent_id.strip() if parent_id else ""
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
        level = int(fields.get("level", 0)) if str(fields.get("level", "")).isdigit() else 0
        rows.append({
            "id": fields.get("matrix_id", "").strip(),
            "title": fields.get("title", "").strip(),
            "body": fields.get("body", "").strip(),
            "level": level,
            "parent_id": fields.get("parent_id", "").strip(),
            "task_id": task.get("id")
        })
    return pd.DataFrame(rows)

def build_fields(item):
    return [
        {"id": 1, "value": item["id"]},
        {"id": 2, "value": str(item.get("level", 0))},
        {"id": 3, "value": item.get("title", "")},
        {"id": 4, "value": item.get("parent_id", "")},
        {"id": 5, "value": item.get("body", "")},
    ]

# === ROUTES ===

@router.post("/xmind-diff")
async def xmind_diff(url: str = Body(...)):
    content = requests.get(url).content
    xmind_df = extract_xmind_nodes(io.BytesIO(content))
    pyrus_df = extract_pyrus_data()

    xmind_ids = set(xmind_df["id"])
    pyrus_ids = set(pyrus_df["id"])

    task_map = {row["id"]: row["task_id"] for _, row in pyrus_df.iterrows()}

    new_items = xmind_df[~xmind_df["id"].isin(pyrus_ids)]
    updated_items = pd.merge(xmind_df, pyrus_df, on="id", suffixes=("_xmind", "_pyrus"))
    updated_items = updated_items[(updated_items["title_xmind"] != updated_items["title_pyrus"]) |
                                   (updated_items["body_xmind"] != updated_items["body_pyrus"]) |
                                   (updated_items["level_xmind"] != updated_items["level_pyrus"]) |
                                   (updated_items["parent_id_xmind"] != updated_items["parent_id_pyrus"])]

    deleted_items = pyrus_df[~pyrus_df["id"].isin(xmind_ids)]

    enriched = []

    for _, row in new_items.iterrows():
        enriched.append({**row.to_dict(), "action": "new", "task_id": None})

    for _, row in updated_items.iterrows():
        enriched.append({
            "id": row["id"],
            "title": row["title_xmind"],
            "body": row["body_xmind"],
            "level": row["level_xmind"],
            "parent_id": row["parent_id_xmind"],
            "action": "update",
            "task_id": task_map.get(row["id"])
        })

    for _, row in deleted_items.iterrows():
        enriched.append({**row.to_dict(), "action": "delete"})

    enriched = [e for e in enriched if not e["id"].startswith(("x.", "+."))]

    json_new = [
        {
            "method": "POST",
            "endpoint": "/tasks",
            "payload": {
                "form_id": 2309262,
                "fields": build_fields(item)
            }
        } for item in enriched if item["action"] == "new"]

    json_updated = [
        {
            "method": "POST",
            "endpoint": f"/tasks/{item['task_id']}/comments",
            "payload": {
                "field_updates": build_fields(item)
            }
        } for item in enriched if item["action"] == "update" and item.get("task_id")]

    json_deleted = [
        {
            "method": "DELETE",
            "endpoint": f"/tasks/{item['task_id']}"
        } for item in enriched if item["action"] == "delete" and item.get("task_id")]

    return {
        "content": format_as_markdown(enriched),
        "json": enriched,
        "for_pyrus": {
            "new": json_new,
            "updated": json_updated,
            "deleted": json_deleted
        }
    }
