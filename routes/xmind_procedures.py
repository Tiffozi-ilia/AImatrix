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

    # ⬇️ Сортировка по уровню и порядку следования
    flat_xmind.sort(key=lambda n: (int(n.get("level", 0)), int(n.get("order", 0))))

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

# === APPLY CHANGES TO PYRUS ===================================================
import httpx  # Заменим requests на асинхронный httpx
import asyncio

@router.post("/xmind_apply")
async def xmind_apply(url: str = Body(...)):
    from utils.data_loader import get_pyrus_token

    # 1. Загружаем XMind с таймаутом
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url)
            response.raise_for_status()
            content = response.content
        with zipfile.ZipFile(io.BytesIO(content)) as z:
            content_json = json.loads(z.read("content.json"))
    except Exception as e:
        return {"error": f"Ошибка при загрузке XMind: {e}"}

    # 2. Парсим данные
    flat_xmind = flatten_xmind_nodes(content_json)
    
    # 3. Получаем данные Pyrus
    try:
        raw_data = get_data()
        raw_data = json.loads(raw_data) if isinstance(raw_data, str) else raw_data
        pyrus_df = extract_pyrus_data()
    except Exception as e:
        return {"error": f"Ошибка при загрузке данных Pyrus: {e}"}

    # 4. Определяем изменения (оптимизированная версия)
    # --- Создаем DataFrame из XMind
    xmind_df = pd.DataFrame(flat_xmind)
    
    # --- Список всех ID в Pyrus
    pyrus_ids = set(pyrus_df["id"].unique())
    
    # --- UPDATED: находим изменения в title/body
    updated_mask = (
        (xmind_df["title"] != pyrus_df.set_index("id")["title"]) |
        (xmind_df["body"] != pyrus_df.set_index("id")["body"])
    )
    updated_records = xmind_df[updated_mask].to_dict(orient="records")
    
    # --- DELETED: отсутствующие в XMind
    deleted_records = pyrus_df[~pyrus_df["id"].isin(xmind_df["id"])].to_dict(orient="records")
    
    # --- NEW: генерируем ID для новых элементов
    new_items = []
    for node in flat_xmind:
        if not node.get("id") or node["id"] not in pyrus_ids:
            parent_id = node.get("parent_id", "x")
            base = parent_id if parent_id else "x"
            
            # Генерация нового ID
            if base not in max_numbers:
                # Находим максимальный номер для этого префикса
                prefix_ids = [id for id in pyrus_ids if id.startswith(f"{base}.")]
                if prefix_ids:
                    max_num = max(int(id.split(".")[-1]) for id in prefix_ids)
                else:
                    max_num = 0
                max_numbers[base] = max_num
            
            max_numbers[base] += 1
            new_id = f"{base}.{str(max_numbers[base]).zfill(2)}"
            node["id"] = new_id
            node["generated"] = True
            new_items.append(node)

    # 5. Получаем token
    token = get_pyrus_token()
    headers_api = {"Authorization": f"Bearer {token}"}
    
    # 6. Создаем асинхронные задачи
    async with httpx.AsyncClient(timeout=30.0) as client:
        # Создаем новые задачи
        created_tasks = [
            client.post(
                "https://api.pyrus.com/v4/tasks",
                headers=headers_api,
                json={
                    "form_id": 2309262,
                    "fields": [
                        {"id": 1, "value": item["id"]},
                        {"id": 2, "value": item.get("level", "")},
                        {"id": 3, "value": item.get("title", "")},
                        {"id": 4, "value": item.get("parent_id", "")},
                        {"id": 5, "value": item.get("body", "")},
                    ]
                }
            )
            for item in new_items
        ]
        
        # Обновляем задачи (комментарии)
        updated_tasks = []
        for item in updated_records:
            task_id = task_map.get(item["id"])
            if task_id:
                updated_tasks.append(
                    client.post(
                        f"https://api.pyrus.com/v4/tasks/{task_id}/comments",
                        headers=headers_api,
                        json={"text": f"🔄 Обновление из XMind\nTitle: {item['title']}\nBody: {item['body']}"}
                    )
                )
        
        # Удаляем задачи
        deleted_tasks = []
        for item in deleted_records:
            task_id = task_map.get(item["id"])
            if task_id:
                deleted_tasks.append(
                    client.delete(f"https://api.pyrus.com/v4/tasks/{task_id}", headers=headers_api)
                )
        
        # Выполняем все операции параллельно
        created_responses = await asyncio.gather(*created_tasks, return_exceptions=True)
        updated_responses = await asyncio.gather(*updated_tasks, return_exceptions=True)
        deleted_responses = await asyncio.gather(*deleted_tasks, return_exceptions=True)
    
    # 7. Обрабатываем результаты
    created = []
    for i, response in enumerate(created_responses):
        item_id = new_items[i]["id"]
        if isinstance(response, Exception):
            created.append({"id": item_id, "error": str(response)})
        else:
            created.append({"id": item_id, "response": response.status_code})
    
    updated = []
    for i, response in enumerate(updated_responses):
        item_id = updated_records[i]["id"]
        task_id = task_map.get(item_id)
        if isinstance(response, Exception):
            updated.append({"id": item_id, "task_id": task_id, "error": str(response)})
        else:
            updated.append({"id": item_id, "task_id": task_id, "response": response.status_code})
    
    deleted = []
    for i, response in enumerate(deleted_responses):
        item_id = deleted_records[i]["id"]
        task_id = task_map.get(item_id)
        if isinstance(response, Exception):
            deleted.append({"id": item_id, "task_id": task_id, "error": str(response)})
        else:
            deleted.append({"id": item_id, "task_id": task_id, "response": response.status_code})

    return {
        "created": created,
        "updated": updated,
        "deleted": deleted
    }
