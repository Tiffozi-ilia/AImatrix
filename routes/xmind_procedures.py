from fastapi import APIRouter, Body
import zipfile, io, json, requests
import pandas as pd
from utils.data_loader import get_data
from utils.diff_engine import format_as_markdown
from utils.xmind_parser import flatten_xmind_nodes

router = APIRouter()

# === DIFF ======================================================================
@router.post("/xmind-diff")
async def xmind_diff(url: str = Body(...)):
    content = requests.get(url).content
    with zipfile.ZipFile(io.BytesIO(content)) as z:
        content_json = json.loads(z.read("content.json"))

    flat_xmind = flatten_xmind_nodes(content_json)

    raw_data = get_data()
    if isinstance(raw_data, str):
        try:
            raw_data = json.loads(raw_data)
        except json.JSONDecodeError:
            raw_data = [json.loads(line) for line in raw_data.splitlines() if line.strip()]
    if isinstance(raw_data, dict):
        for value in raw_data.values():
            if isinstance(value, list):
                raw_data = value
                break
    if not isinstance(raw_data, list):
        raise ValueError("Pyrus data is not a list")

    pyrus_ids = {
        item["id"] for item in raw_data
        if isinstance(item, dict) and "id" in item
    }

    new_nodes = [
        n for n in flat_xmind
        if n.get("generated") and n["id"] not in pyrus_ids
    ]

    return {
        "content": format_as_markdown(new_nodes),
        "json": new_nodes
    }

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

# === MAPPING (Stage 1: только CSV из JSON) ====================================
# Обновлённая версия `pyrus_mapping` с добавлением diff-результатов как new
from fastapi import APIRouter, Body
import zipfile, io, json, requests
import pandas as pd
from utils.data_loader import get_data
from utils.diff_engine import format_as_markdown
from utils.xmind_parser import flatten_xmind_nodes

router = APIRouter()

@router.post("/pyrus_mapping")
async def pyrus_mapping(url: str = Body(...)):
    # === 1. Скачиваем и парсим XMind ===
    try:
        content = requests.get(url).content
        with zipfile.ZipFile(io.BytesIO(content)) as z:
            content_json = json.loads(z.read("content.json"))
    except Exception as e:
        return {"error": f"Не удалось загрузить XMind: {e}"}

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

    xmind_df = pd.DataFrame(walk(content_json[0].get("rootTopic", {})))
    xmind_ids = set(xmind_df["id"])

    # === 2. Загружаем данные из Pyrus ===
    try:
        raw = get_data()
        if isinstance(raw, str):
            raw = json.loads(raw)
        if isinstance(raw, dict):
            raw = raw.get("tasks", [])
    except Exception as e:
        return {"error": f"Не удалось загрузить JSON из Pyrus: {e}"}

    pyrus_records = []
    task_map = {}

    for task in raw:
        fields = {f["name"]: f.get("value", "") for f in task.get("fields", [])}
        matrix_id = fields.get("matrix_id", "").strip()
        if matrix_id:
            task_map[matrix_id] = task.get("id")
            pyrus_records.append({
                "id": matrix_id,
                "title": fields.get("title", ""),
                "body": fields.get("body", ""),
                "level": fields.get("level", ""),
                "parent_id": fields.get("parent_id", "")
            })

    pyrus_df = pd.DataFrame(pyrus_records)
    pyrus_ids = set(pyrus_df["id"])

    # === 3. DIFF: Новые (есть в XMind, нет в Pyrus) ===
    new_items = xmind_df[~xmind_df["id"].isin(pyrus_ids)].copy()
    new_items["action"] = "new"
    new_items["task_id"] = ""

    # === 4. UPDATED: Совпадают по ID, но отличаются title/body ===
    merged = pd.merge(xmind_df, pyrus_df, on="id", suffixes=("_x", "_y"))
    updated_df = merged[(merged["title_x"] != merged["title_y"]) | (merged["body_x"] != merged["body_y"])]
    updated_items = updated_df.rename(columns={
        "title_x": "title", "body_x": "body",
        "parent_id_x": "parent_id", "level_x": "level"
    })[["id", "parent_id", "level", "title", "body"]].copy()
    updated_items["action"] = "update"
    updated_items["task_id"] = updated_items["id"].map(task_map)

    # === 5. DELETED: Есть в Pyrus, нет в XMind ===
    deleted_items = pyrus_df[~pyrus_df["id"].isin(xmind_ids)].copy()
    deleted_items["action"] = "delete"
    deleted_items["task_id"] = deleted_items["id"].map(task_map)

    # === 6. Объединение ===
    enriched = pd.concat([new_items, updated_items, deleted_items], ignore_index=True)
    records = enriched[["id", "parent_id", "level", "title", "body", "task_id", "action"]].to_dict(orient="records")

    # === 7. CSV XMind ===
    xmind_df["task_id"] = xmind_df["id"].map(task_map)
    csv_records = xmind_df[["id", "parent_id", "level", "title", "body", "task_id"]].to_dict(orient="records")

    return {
        "content": format_as_markdown(records),
        "json": records,
        "rows": csv_records
    }
