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
# ... предыдущий код без изменений ...

# === MAPPING (Stage 1: только CSV из JSON) ====================================
@router.post("/pyrus_mapping")
async def pyrus_mapping(url: str = Body(...)):
    import requests
    import zipfile
    import io
    import json
    import pandas as pd

    # 1. Скачиваем и парсим XMind
    try:
        content = requests.get(url).content
        with zipfile.ZipFile(io.BytesIO(content)) as z:
            content_json = json.loads(z.read("content.json"))
    except Exception as e:
        return {"error": f"Не удалось загрузить XMind: {e}"}

    # Используем flatten_xmind_nodes для получения новых элементов
    flat_xmind = flatten_xmind_nodes(content_json)
    new_nodes = [n for n in flat_xmind if n.get("generated")]

    # 2. Загружаем данные из Pyrus
    try:
        raw = get_data()
        if isinstance(raw, str):
            raw = json.loads(raw)
        if isinstance(raw, dict):
            raw = raw.get("tasks", [])
    except Exception as e:
        return {"error": f"Не удалось загрузить JSON из Pyrus: {e}"}

    # Строим маппинг ID задач
    task_map = {}
    for task in raw:
        fields = {field["name"]: field.get("value", "") for field in task.get("fields", [])}
        matrix_id = fields.get("matrix_id", "").strip()
        if matrix_id:
            task_map[matrix_id] = task.get("id")

    # 3. Получаем обновления, удаления и новые элементы
    updated_result = await detect_updated_items(url)
    deleted_result = await detect_deleted_items(url)
    updated_items = updated_result["json"]
    deleted_items = deleted_result["json"]
    
    # Добавляем новые элементы (diff)
    new_items = [
        {
            "id": n["id"],
            "parent_id": n.get("parent_id", ""),
            "level": str(n.get("level", 0)),
            "title": n.get("title", ""),
            "body": n.get("body", ""),
        }
        for n in new_nodes if n["id"] not in task_map  # Только отсутствующие в Pyrus
    ]

    # 4. Обогащаем данные действиями
    enriched = []
    for item in updated_items:
        item["task_id"] = task_map.get(item["id"])
        item["action"] = "update"
        enriched.append(item)
        
    for item in deleted_items:
        item["task_id"] = task_map.get(item["id"])
        item["action"] = "delete"
        enriched.append(item)
        
    for item in new_items:
        item["task_id"] = None  # Для новых элементов task_id всегда пустой
        item["action"] = "new"
        enriched.append(item)

    # 5. Формируем CSV-таблицу всех элементов XMind
    xmind_df = extract_xmind_nodes(io.BytesIO(content))
    xmind_df["task_id"] = xmind_df["id"].map(task_map)
    csv_records = xmind_df[["id", "parent_id", "level", "title", "body", "task_id"]].to_dict(orient="records")

    return {
        "content": format_as_markdown(enriched),
        "json": enriched,
        "rows": csv_records
    }
