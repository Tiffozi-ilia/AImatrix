from fastapi import APIRouter, Body
import zipfile, io, json, requests
import pandas as pd
from utils.data_loader import get_data
from utils.diff_engine import format_as_markdown

router = APIRouter()

# === ОБЩИЕ ПАРСЕРЫ =============================================================

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

# === DIFF ======================================================================

@router.post("/xmind-diff")
async def xmind_diff(url: str = Body(...)):
    content = requests.get(url).content
    xmind_df = extract_xmind_nodes(io.BytesIO(content))
    xmind_records = xmind_df.to_dict(orient='records')
    pyrus_df = extract_pyrus_data()
    pyrus_ids = set(pyrus_df['id'])

    # Генерация ID и отметка generated
    used_ids = set(pyrus_ids)
    max_numbers = {}
    for pid in used_ids:
        parts = pid.split('.')
        if len(parts) > 1 and parts[-1].isdigit():
            base = '.'.join(parts[:-1])
            max_numbers[base] = max(max_numbers.get(base, 0), int(parts[-1]))

    for node in xmind_records:
        if not node["id"] or node["id"] in used_ids:
            base = node.get("parent_id") or "x"
            number = max_numbers.get(base, 0) + 1
            new_id = f"{base}.{str(number).zfill(2)}"
            node["id"] = new_id
            node["generated"] = True
            max_numbers[base] = number
            used_ids.add(new_id)

    new_items = [item for item in xmind_records if item.get("generated")]

    return {
        "content": format_as_markdown(new_items),
        "json": new_items
    }

# === UPDATED ===================================================================

@router.post("/xmind-updated")
async def detect_updated_items(url: str = Body(...)):
    content = requests.get(url).content
    xmind_df = extract_xmind_nodes(io.BytesIO(content))
    pyrus_df = extract_pyrus_data()

    merged = pd.merge(xmind_df, pyrus_df, on="id", suffixes=("_xmind", "_pyrus"))
    changed = merged[
        (merged["title_xmind"] != merged["title_pyrus"]) |
        (merged["body_xmind"] != merged["body_pyrus"]) |
        (merged["level_xmind"] != merged["level_pyrus"]) |
        (merged["parent_id_xmind"] != merged["parent_id_pyrus"])
    ]

    records = changed.rename(columns={
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
    content = requests.get(url).content
    xmind_df = extract_xmind_nodes(io.BytesIO(content))
    xmind_records = xmind_df.to_dict(orient='records')
    pyrus_df = extract_pyrus_data()
    pyrus_records = pyrus_df.to_dict(orient='records')

    task_map = {item['id']: item['task_id'] for item in pyrus_records if item['id']}
    pyrus_ids = set(task_map.keys())
    xmind_ids = set(item['id'] for item in xmind_records)

    new_items = [item for item in xmind_records if item.get("generated") and item["id"] not in pyrus_ids]
    deleted_items = [item for item in pyrus_records if item["id"] not in xmind_ids]
    updated_items = []
    for x_item in xmind_records:
        if x_item['id'] in pyrus_ids:
            p_item = next(p for p in pyrus_records if p['id'] == x_item['id'])
            if (x_item["title"] != p_item["title"] or
                x_item["body"] != p_item["body"] or
                x_item["level"] != p_item["level"] or
                x_item["parent_id"] != p_item["parent_id"]):
                updated_items.append(x_item)

    def build_fields(item):
        return [
            {"id": 1, "value": item["id"]},
            {"id": 2, "value": str(item.get("level", 0))},
            {"id": 3, "value": item.get("title", "")},
            {"id": 4, "value": item.get("parent_id", "")},
            {"id": 5, "value": item.get("body", "")}
        ]

    enriched = []
    for item in new_items:
        item["action"] = "new"
        item["task_id"] = None
        enriched.append(item)
    for item in updated_items:
        item["action"] = "update"
        item["task_id"] = task_map.get(item["id"])
        enriched.append(item)
    for item in deleted_items:
        item["action"] = "delete"
        item["task_id"] = task_map.get(item["id"])
        enriched.append(item)

    json_new = [{
        "method": "POST",
        "endpoint": "/tasks",
        "payload": {
            "form_id": 2309262,
            "fields": build_fields(item)
        }
    } for item in new_items]

    json_updated = [{
        "method": "POST",
        "endpoint": f"/tasks/{item['task_id']}/comments",
        "payload": {
            "field_updates": build_fields(item)
        }
    } for item in updated_items if item.get("task_id")]

    json_deleted = [{
        "method": "DELETE",
        "endpoint": f"/tasks/{item['task_id']}"
    } for item in deleted_items if item.get("task_id")]

    csv_records = [{
        "id": item["id"],
        "parent_id": item["parent_id"],
        "level": item["level"],
        "title": item["title"],
        "body": item["body"],
        "task_id": task_map.get(item["id"])
    } for item in xmind_records]

    return {
        "content": format_as_markdown(enriched),
        "json": enriched,
        "rows": csv_records,
        "for_pyrus": {
            "new": json_new,
            "updated": json_updated,
            "deleted": json_deleted
        }
    }
