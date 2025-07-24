from fastapi import APIRouter, Body
import zipfile, io, json, requests
import pandas as pd
from utils.data_loader import get_data, get_pyrus_token
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

    # Собираем все существующие ID из Pyrus как строки
    pyrus_ids = {
        str(item["id"]) for item in raw_data
        if isinstance(item, dict) and "id" in item
    }

    # Создаем словарь для отслеживания максимальных номеров для каждого родителя
    max_numbers = {}
    all_existing_ids = set(pyrus_ids)
    
    # Анализируем существующие ID, чтобы найти максимальные номера
    for item_id in all_existing_ids:
        # Проверяем, что ID содержит точку и имеет числовую часть
        if isinstance(item_id, str) and '.' in item_id:
            parts = item_id.split('.')
            # Проверяем, что последняя часть - число
            if parts[-1].isdigit():
                base = '.'.join(parts[:-1])
                number = int(parts[-1])
                if base not in max_numbers or number > max_numbers[base]:
                    max_numbers[base] = number
    
    # Анализируем ID из XMind, чтобы обновить максимальные номера
    for node in flat_xmind:
        node_id = node.get("id")
        if node_id:
            # Приводим ID к строке для единообразия
            node_id_str = str(node_id)
            if '.' in node_id_str:
                parts = node_id_str.split('.')
                if parts[-1].isdigit():
                    base = '.'.join(parts[:-1])
                    number = int(parts[-1])
                    if base not in max_numbers or number > max_numbers[base]:
                        max_numbers[base] = number
    
    used_ids = set(all_existing_ids)
    new_nodes = []
    
    for node in flat_xmind:
        node_id = node.get("id")
        parent_id = node.get("parent_id", "")
        
        # Приводим ID к строке
        node_id_str = str(node_id) if node_id else ""
        
        # Если ID отсутствует или конфликтует
        if not node_id_str or node_id_str in used_ids:
            # Определяем базовый префикс
            base = str(parent_id) if parent_id else "x"
            
            # Получаем текущий максимальный номер для этого базового префикса
            current_max = max_numbers.get(base, 0)
            new_number = current_max + 1
            
            # Генерируем новый ID
            new_id = f"{base}.{str(new_number).zfill(2)}"
            
            # Обновляем данные узла
            node["id"] = new_id
            node["generated"] = True
            
            # Обновляем максимальный номер для этого базового префикса
            max_numbers[base] = new_number
            used_ids.add(new_id)
        else:
            # Если ID валиден, сохраняем его как использованный
            used_ids.add(node_id_str)
        
        # Добавляем в new_nodes если это новый узел
        if node.get("generated") and node["id"] not in pyrus_ids:
            new_nodes.append(node)

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
            "level": n.get("level", 0),  # Сохраняем как число
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
        # Создаем копию, чтобы не изменять оригинальный элемент
        new_item = item.copy()
        new_item["task_id"] = None
        new_item["action"] = "new"
        enriched.append(new_item)
    
    # 5. Формируем CSV-таблицу всех элементов XMind
    xmind_df = extract_xmind_nodes(io.BytesIO(content))
    xmind_df["task_id"] = xmind_df["id"].map(task_map)
    csv_records = xmind_df[["id", "parent_id", "level", "title", "body", "task_id"]].to_dict(orient="records")
    
    # === 6. Готовим JSON для выгрузки в Pyrus ==================================
    def build_fields(item):
        # Преобразуем уровень в строку при формировании полей
        level_value = str(item.get("level", 0))
        return [
            {"id": 1, "value": item.get("id", "")},
            {"id": 2, "value": level_value},
            {"id": 3, "value": item.get("title", "")},
            {"id": 4, "value": item.get("parent_id", "")},
            {"id": 5, "value": item.get("body", "")},
        ]

    # Формируем JSON для новых задач (берем из обогащенных данных)
    json_new = [
        {
            "method": "POST",
            "endpoint": "/tasks",
            "payload": {
                "form_id": 484498,
                "fields": build_fields(item)
            }
        }
        for item in enriched 
        if item["action"] == "new"
    ]

    # Формируем JSON для обновлений (берем из обогащенных данных)
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

    # Формируем JSON для удалений (берем из обогащенных данных)
    json_deleted = [
        {
            "method": "DELETE",
            "endpoint": f"/tasks/{item['task_id']}"
        }
        for item in enriched 
        if item["action"] == "delete" and item.get("task_id")
    ]

    # Отладочная информация (можете убрать после тестирования)
    print(f"[DEBUG] Total new nodes: {len(new_nodes)}")
    print(f"[DEBUG] New items: {len(new_items)}")
    print(f"[DEBUG] Enriched new items: {len([x for x in enriched if x['action'] == 'new'])}")
    print(f"[DEBUG] JSON new items: {len(json_new)}")

    response_data = {
        "content": format_as_markdown(enriched),
        "json": enriched,
        "rows": csv_records,
        "for_pyrus": {
            "new": json_new,
            "updated": json_updated,
            "deleted": json_deleted
        }
    }

    # === ОТПРАВКА В PYRUS ===
    pyrus_result = await sync_with_pyrus(response_data)

    response_data["pyrus_response"] = pyrus_result

    return response_data
    
from utils.data_loader import get_pyrus_token

# === Вспомогательная функция для отправки запросов в Pyrus API ===
def send_to_pyrus(method: str, endpoint: str, payload: dict = None):
    base_url = "https://pyrus.sovcombank.ru/api/v4"
    token = get_pyrus_token()
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    url = f"{base_url}{endpoint}"

    if method.upper() == "POST":
        response = requests.post(url, headers=headers, json=payload)
    elif method.upper() == "DELETE":
        response = requests.delete(url, headers=headers)
    else:
        raise ValueError(f"Unsupported method: {method}")

    try:
        response.raise_for_status()
        return response.json()
    except requests.HTTPError as e:
        return {"error": str(e), "details": response.text}

# === Функция для отправки подготовленного JSON в Pyrus ===
async def sync_with_pyrus(data):
    results = {"created": [], "updated": [], "deleted": [], "errors": []}

    # Создание новых задач
    for item in data["for_pyrus"]["new"]:
        resp = send_to_pyrus(item["method"], item["endpoint"], item["payload"])
        results["created"].append(resp)

    # Обновление существующих задач
    for item in data["for_pyrus"]["updated"]:
        resp = send_to_pyrus(item["method"], item["endpoint"], item["payload"])
        results["updated"].append(resp)

    # Удаление задач
    for item in data["for_pyrus"]["deleted"]:
        resp = send_to_pyrus(item["method"], item["endpoint"])
        results["deleted"].append(resp)

    return results
