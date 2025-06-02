from fastapi import APIRouter, Body
import zipfile, io, json, requests
import pandas as pd
from utils.data_loader import get_data
from utils.diff_engine import format_as_markdown

router = APIRouter()

# === ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ==================================================

def extract_xmind_nodes(file: io.BytesIO):
    """Парсит XMind и, при необходимости, генерирует id"""
    with zipfile.ZipFile(file) as z:
        content_json = json.loads(z.read("content.json"))

    counters = {}

    def walk(node, parent_id="", level=0):
        label = node.get("labels", [])
        node_id = label[0].strip() if label else ""

        if not node_id:
            count = counters.get(parent_id, 0) + 1
            counters[parent_id] = count
            node_id = f"{parent_id}.{str(count).zfill(2)}"

            generated = True
        else:
            generated = False

        title = node.get("title", "").strip()
        body = node.get("notes", {}).get("plain", {}).get("content", "").strip()

        rows = [{
            "id": node_id,
            "title": title,
            "body": body,
            "level": level,
            "parent_id": parent_id,
            "generated": generated
        }]

        for child in node.get("children", {}).get("attached", []):
            rows.extend(walk(child, node_id, level + 1))

        return rows

    root = content_json[0].get("rootTopic", {})
    return pd.DataFrame(walk(root))


def extract_pyrus_data():
    """Парсит данные из Pyrus и возвращает DataFrame"""
    raw = get_data()
    if isinstance(raw, str):
        raw = json.loads(raw)
    if isinstance(raw, dict):
        raw = raw.get("tasks", [])

    rows = []
    for task in raw:
        fields = {f["name"]: f.get("value", "") for f in task.get("fields", [])}
        rows.append({
            "id": fields.get("matrix_id", "").strip(),
            "title": fields.get("title", "").strip(),
            "body": fields.get("body", "").strip(),
            "level": int(fields.get("level", 0)) if str(fields.get("level", "")).isdigit() else 0,
            "parent_id": fields.get("parent_id", "").strip(),
            "task_id": task.get("id")
        })
    return pd.DataFrame(rows)


def build_fields(item):
    return [
        {"id": 1, "value": item.get("id", "")},
        {"id": 2, "value": str(item.get("level", 0))},
        {"id": 3, "value": item.get("title", "")},
        {"id": 4, "value": item.get("parent_id", "")},
        {"id": 5, "value": item.get("body", "")}
    ]


# === DIFF =====================================================================

@router.post("/xmind-diff")
async def xmind_diff(url: str = Body(...)):
    content = requests.get(url).content
    xmind_df = extract_xmind_nodes(io.BytesIO(content))
    pyrus_df = extract_pyrus_data()
    existing_ids = set(pyrus_df["id"])

    new_items = xmind_df[~xmind_df["id"].isin(existing_ids)].to_dict(orient="records")

    return {
        "content": format_as_markdown(new_items),
        "json": new_items
    }


# === UPDATED ==================================================================

@router.post("/xmind-updated")
async def detect_updated_items(url: str = Body(...)):
    content = requests.get(url).content
    xmind_df = extract_xmind_nodes(io.BytesIO(content))
    pyrus_df = extract_pyrus_data()

    merged = pd.merge(xmind_df, pyrus_df, on="id", suffixes=("_x", "_p"))
    diffs = merged[
        (merged["title_x"] != merged["title_p"]) |
        (merged["body_x"] != merged["body_p"]) |
        (merged["level_x"] != merged["level_p"]) |
        (merged["parent_id_x"] != merged["parent_id_p"])
    ]

    records = diffs.rename(columns={
        "id": "id",
        "title_x": "title",
        "body_x": "body",
        "level_x": "level",
        "parent_id_x": "parent_id",
        "task_id": "task_id"
    })[["id", "parent_id", "level", "title", "body"]].to_dict(orient="records")

    return {
        "content": format_as_markdown(records),
        "json": records
    }


# === DELETE ===================================================================

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


# === MAPPING ==================================================================

@router.post("/pyrus_mapping")
async def pyrus_mapping(url: str = Body(...)):
    content = requests.get(url).content
    xmind_df = extract_xmind_nodes(io.BytesIO(content))
    pyrus_df = extract_pyrus_data()

    xmind_records = xmind_df.to_dict(orient="records")
    pyrus_records = pyrus_df.to_dict(orient="records")
    task_map = {x["id"]: x["task_id"] for x in pyrus_records if x["id"]}

    # NEW
    xmind_ids = set(xmind_df["id"])
    pyrus_ids = set(pyrus_df["id"])
    new_items = [x for x in xmind_records if x["id"] not in pyrus_ids]

    # UPDATED
    updated_items = []
    for x in xmind_records:
        if x["id"] in task_map:
            y = pyrus_df[pyrus_df["id"] == x["id"]].iloc[0]
            if (x["title"] != y["title"] or
                x["body"] != y["body"] or
                x["parent_id"] != y["parent_id"] or
                x["level"] != y["level"]):
                x["task_id"] = y["task_id"]
                updated_items.append(x)

    # DELETED
    deleted_items = [x for x in pyrus_records if x["id"] not in xmind_ids]

    # BUILD
    enriched = []

    for item in new_items:
        item["action"] = "new"
        item["task_id"] = None
        enriched.append(item)

    for item in updated_items:
        item["action"] = "update"
        enriched.append(item)

    for item in deleted_items:
        item["action"] = "delete"
        enriched.append(item)

    # FINAL PAYLOADS
    json_new = [{
        "method": "POST",
        "endpoint": "/tasks",
        "payload": {
            "form_id": 2309262,
            "fields": build_fields(x)
        }
    } for x in enriched if x["action"] == "new"]

    json_updated = [{
        "method": "POST",
        "endpoint": f"/tasks/{x['task_id']}/comments",
        "payload": {
            "field_updates": build_fields(x)
        }
    } for x in enriched if x["action"] == "update" and x.get("task_id")]

    json_deleted = [{
        "method": "DELETE",
        "endpoint": f"/tasks/{x['task_id']}"
    } for x in enriched if x["action"] == "delete" and x.get("task_id")]

    return {
        "content": format_as_markdown(enriched),
        "json": enriched,
        "rows": xmind_df[["id", "title", "body", "parent_id", "level"]].to_dict(orient="records"),
        "for_pyrus": {
            "new": json_new,
            "updated": json_updated,
            "deleted": json_deleted
        }
    }
