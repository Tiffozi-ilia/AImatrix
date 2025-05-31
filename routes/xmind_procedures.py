from fastapi import APIRouter, Body
import zipfile, io, json, requests
import pandas as pd
from utils.data_loader import get_data
from utils.diff_engine import format_as_markdown
from utils.xmind_parser import flatten_xmind_nodes

router = APIRouter()

# === DIFF ======================================================================
# === DIFF ======================================================================
@router.post("/xmind-diff")
async def xmind_diff(url: str = Body(...)):
    content = requests.get(url).content
    with zipfile.ZipFile(io.BytesIO(content)) as z:
        content_json = json.loads(z.read("content.json"))

    # Получаем плоский список с сохранением порядка
    flat_xmind = flatten_xmind_nodes(content_json)
    
    # Сохраняем исходный порядок элементов
    node_order = {node['id']: idx for idx, node in enumerate(flat_xmind) if node.get('id')}
    
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

    # Создаем словарь для отслеживания следующего номера для каждого родителя
    next_numbers = {}
    # Собираем все существующие ID для проверки уникальности
    all_ids = set(pyrus_ids)
    
    # Первый проход: собираем информацию о существующих номерах
    for node in flat_xmind:
        node_id = node.get("id")
        if node_id and node_id in all_ids:
            # Если ID уже существует, пропускаем для первого прохода
            continue
            
        parent_id = node.get("parent_id", "") or "x"
        if node_id and '.' in node_id:
            parts = node_id.split('.')
            if parts[-1].isdigit():
                base = '.'.join(parts[:-1])
                number = int(parts[-1])
                if base not in next_numbers or number > next_numbers[base]:
                    next_numbers[base] = number
        elif node_id:
            all_ids.add(node_id)

    # Второй проход: генерация ID в порядке расположения элементов
    new_nodes = []
    
    for node in flat_xmind:
        node_id = node.get("id")
        parent_id = node.get("parent_id", "") or "x"
        
        # Пропускаем элементы, которые уже существуют в Pyrus
        if node_id and node_id in pyrus_ids:
            continue
            
        needs_new_id = False
        
        # Если ID отсутствует или конфликтует
        if not node_id or node_id in all_ids:
            needs_new_id = True
        else:
            # Проверяем, соответствует ли ID ожидаемой структуре
            if '.' in node_id:
                parts = node_id.split('.')
                if not parts[-1].isdigit():
                    needs_new_id = True
            else:
                needs_new_id = True
                
        if needs_new_id:
            # Инициализируем счетчик для родителя
            if parent_id not in next_numbers:
                next_numbers[parent_id] = 0
                
            # Находим следующий доступный номер
            while True:
                next_numbers[parent_id] += 1
                new_id = f"{parent_id}.{str(next_numbers[parent_id]).zfill(2)}"
                if new_id not in all_ids:
                    break
                    
            node_id = new_id
            node["id"] = new_id
            node["generated"] = True
        else:
            node["generated"] = False
            
        all_ids.add(node_id)
        
        # Добавляем в new_nodes если это новый узел
        if node.get("generated") and node["id"] not in pyrus_ids:
            new_nodes.append(node)
    
    # Восстанавливаем исходный порядок элементов
    new_nodes.sort(key=lambda node: node_order.get(node['id'], float('inf')))
    
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
        for n in new_nodes 
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
