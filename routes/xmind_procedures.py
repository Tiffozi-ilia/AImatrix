from fastapi import APIRouter, Body
import zipfile, io, json, requests
import pandas as pd
from utils.data_loader import get_data, get_pyrus_token
from utils.diff_engine import format_as_markdown
from utils.xmind_parser import flatten_xmind_nodes

router = APIRouter()

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
                "parent_id": parent_id.strip() if parent_id else ""  # Исправлено: пустая строка вместо None
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

# === DIFF ======================================================================
@router.post("/xmind-diff")
async def xmind_diff(url: str = Body(...)):
    content = requests.get(url).content
    xmind_df = extract_xmind_nodes(io.BytesIO(content))  # Используем единый парсер
    flat_xmind = xmind_df.to_dict("records")

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
        str(item["id"]) for item in raw_data
        if isinstance(item, dict) and "id" in item
    }

    # Создаем словарь для отслеживания максимальных номеров для каждого родителя
    max_numbers = {}
    all_existing_ids = set(pyrus_ids)
    
    for item_id in all_existing_ids:
        if isinstance(item_id, str) and '.' in item_id:
            parts = item_id.split('.')
            if parts[-1].isdigit():
                base = '.'.join(parts[:-1])
                number = int(parts[-1])
                if base not in max_numbers or number > max_numbers[base]:
                    max_numbers[base] = number
    
    for node in flat_xmind:
        node_id = node.get("id")
        if node_id:
            node_id_str = str(node_id)
            if '.' in node_id_str and node_id_str.split('.')[-1].isdigit():
                base = '.'.join(node_id_str.split('.')[:-1])
                number = int(node_id_str.split('.')[-1])
                if base not in max_numbers or number > max_numbers[base]:
                    max_numbers[base] = number
    
    used_ids = set(all_existing_ids)
    new_nodes = []
    
    for node in flat_xmind:
        node_id = node.get("id")
        parent_id = node.get("parent_id", "")
        node_id_str = str(node_id) if node_id else ""
        
        if not node_id_str or node_id_str in used_ids:
            base = str(parent_id) if parent_id else "x"
            current_max = max_numbers.get(base, 0)
            new_number = current_max + 1
            new_id = f"{base}.{str(new_number).zfill(2)}"
            
            node["id"] = new_id
            node["generated"] = True
            max_numbers[base] = new_number
            used_ids.add(new_id)
        else:
            used_ids.add(node_id_str)
        
        if node.get("generated") and node["id"] not in pyrus_ids:
            new_nodes.append(node)

    return {
        "content": format_as_markdown(new_nodes),
        "json": new_nodes
    }

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
    try:
        content = requests.get(url).content
        xmind_df = extract_xmind_nodes(io.BytesIO(content))  # Единый источник данных
        xmind_records = xmind_df.to_dict("records")
    except Exception as e:
        return {"error": f"Не удалось загрузить XMind: {e}"}

    try:
        raw = get_data()
        if isinstance(raw, str):
            raw = json.loads(raw)
        if isinstance(raw, dict):
            raw = raw.get("tasks", [])
    except Exception as e:
        return {"error": f"Не удалось загрузить JSON из Pyrus: {e}")

    # Строим маппинг ID задач
    task_map = {}
    pyrus_ids = set()
    for task in raw:
        fields = {field["name"]: field.get("value", "") for field in task.get("fields", [])}
        matrix_id = fields.get("matrix_id", "").strip()
        if matrix_id:
            task_map[matrix_id] = task.get("id")
            pyrus_ids.add(matrix_id)

    # Получаем обновления и удаления
    updated_result = await detect_updated_items(url)
    deleted_result = await detect_deleted_items(url)
    updated_items = updated_result["json"]
    deleted_items = deleted_result["json"]

    # Находим новые элементы (те, что есть в XMind но нет в Pyrus)
    new_items = [
        {
            "id": item["id"],
            "parent_id": item["parent_id"],
            "level": int(item["level"]),  # Конвертируем в int
            "title": item["title"],
            "body": item["body"],
        }
        for item in xmind_records
        if item["id"] not in pyrus_ids
    ]

    # Обогащаем данные
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
        new_item = item.copy()
        new_item["task_id"] = None
        new_item["action"] = "new"
        enriched.append(new_item)
    
    # Формируем CSV
    xmind_df["task_id"] = xmind_df["id"].map(task_map)
    csv_records = xmind_df[["id", "parent_id", "level", "title", "body", "task_id"]].to_dict(orient="records")

    # Формируем JSON для Pyrus
    def build_fields(item):
        return [
            {"id": 1, "value": item.get("id", "")},
            {"id": 2, "value": str(item.get("level", 0))},
            {"id": 3, "value": item.get("title", "")},
            {"id": 4, "value": item.get("parent_id", "")},
            {"id": 5, "value": item.get("body", "")},
        ]

    json_new = [
        {
            "method": "POST",
            "endpoint": "/tasks",
            "payload": {
                "form_id": 2309262,
                "fields": build_fields(item)
            }
        }
        for item in enriched 
        if item["action"] == "new"
    ]

    json_updated = [
        {
            "method": "POST",
            "endpoint": f"/tasks/{item['task_id']}/comments",
            "payload": {
                "field_updates": build_fields(item)
            }
        }
        for item in enriched 
        if item["action"] == "update" and item.get("task_id")
    ]

    json_deleted = [
        {
            "method": "DELETE",
            "endpoint": f"/tasks/{item['task_id']}"
        }
        for item in enriched 
        if item["action"] == "delete" and item.get("task_id")
    ]

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
