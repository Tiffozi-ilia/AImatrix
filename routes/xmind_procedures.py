from fastapi import APIRouter, Body
import zipfile, io, json, requests
import pandas as pd
from utils.data_loader import get_data
from utils.diff_engine import format_as_markdown

router = APIRouter()

# === ОБЩИЕ ФУНКЦИИ ПАРСИНГА ===================================================

def extract_xmind_nodes(file: io.BytesIO):
    """Единый парсер XMind с корректной обработкой parent_id и level"""
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
                "level": int(level),  # Гарантированное число
                "parent_id": parent_id.strip() if parent_id else ""  # Пустая строка вместо "+"
            })
            
        for child in node.get("children", {}).get("attached", []):
            rows.extend(walk(child, node_id, level + 1))
            
        return rows

    root_topic = content_json[0].get("rootTopic", {})
    return pd.DataFrame(walk(root_topic))


def extract_pyrus_data():
    """Единый парсер данных Pyrus с консистентными форматами"""
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
        
        # Преобразуем уровень в число
        level_str = fields.get("level", "")
        level = int(level_str) if level_str and level_str.isdigit() else 0
        
        rows.append({
            "id": fields.get("matrix_id", "").strip(),
            "title": fields.get("title", "").strip(),
            "body": fields.get("body", "").strip(),
            "level": level,  # Числовой формат
            "parent_id": fields.get("parent_id", "").strip(),
            "task_id": task.get("id")  # Добавляем task_id для связи
        })
        
    return pd.DataFrame(rows)


# === API ENDPOINTS =============================================================

@router.post("/xmind-diff")
async def xmind_diff(url: str = Body(...)):
    """Поиск новых элементов в XMind относительно Pyrus"""
    try:
        content = requests.get(url).content
        xmind_df = extract_xmind_nodes(io.BytesIO(content))
        xmind_records = xmind_df.to_dict(orient='records')
        
        pyrus_df = extract_pyrus_data()
        pyrus_ids = set(pyrus_df['id'])
        
        # Находим новые элементы (отсутствующие в Pyrus)
        new_items = [item for item in xmind_records if item['id'] not in pyrus_ids]
        
        return {
            "content": format_as_markdown(new_items),
            "json": new_items
        }
    except Exception as e:
        return {"error": f"XMind diff error: {str(e)}"}


@router.post("/xmind-updated")
async def detect_updated_items(url: str = Body(...)):
    """Поиск измененных элементов в XMind относительно Pyrus"""
    try:
        content = requests.get(url).content
        xmind_df = extract_xmind_nodes(io.BytesIO(content))
        pyrus_df = extract_pyrus_data()
        
        # Слияние данных по ID
        merged = pd.merge(
            xmind_df, 
            pyrus_df, 
            on="id", 
            suffixes=("_xmind", "_pyrus"),
            how="inner"
        )
        
        # Поиск изменений в основных полях
        changed_mask = (
            (merged["title_xmind"] != merged["title_pyrus"]) |
            (merged["body_xmind"] != merged["body_pyrus"]) |
            (merged["level_xmind"] != merged["level_pyrus"]) |
            (merged["parent_id_xmind"] != merged["parent_id_pyrus"])
        )
        
        diffs = merged[changed_mask]
        
        # Форматирование результата
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
    except Exception as e:
        return {"error": f"Updated items error: {str(e)}"}


@router.post("/xmind-delete")
async def detect_deleted_items(url: str = Body(...)):
    """Поиск удаленных в XMind элементов (есть в Pyrus, но нет в XMind)"""
    try:
        content = requests.get(url).content
        xmind_df = extract_xmind_nodes(io.BytesIO(content))
        pyrus_df = extract_pyrus_data()
        
        # Находим элементы, отсутствующие в XMind
        deleted = pyrus_df[~pyrus_df["id"].isin(xmind_df["id"])]
        records = deleted[["id", "parent_id", "level", "title", "body"]].to_dict(orient="records")

        return {
            "content": format_as_markdown(records),
            "json": records
        }
    except Exception as e:
        return {"error": f"Deleted items error: {str(e)}"}


@router.post("/pyrus_mapping")
async def pyrus_mapping(url: str = Body(...)):
    """Формирование полного плана синхронизации с Pyrus"""
    try:
        # 1. Загрузка и парсинг данных
        content = requests.get(url).content
        xmind_df = extract_xmind_nodes(io.BytesIO(content))
        xmind_records = xmind_df.to_dict(orient='records')
        
        pyrus_df = extract_pyrus_data()
        pyrus_records = pyrus_df.to_dict(orient='records')
        
        # 2. Построение маппинга task_id
        task_map = {item['id']: item['task_id'] for item in pyrus_records if item['id']}
        
        # 3. Определение изменений
        pyrus_ids = set(task_map.keys())
        xmind_ids = set(item['id'] for item in xmind_records)
        
        # Новые элементы (есть в XMind, но нет в Pyrus)
        new_items = [item for item in xmind_records if item['id'] not in pyrus_ids]
        
        # Удаленные элементы (есть в Pyrus, но нет в XMind)
        deleted_items = [item for item in pyrus_records if item['id'] not in xmind_ids]
        
        # Измененные элементы (есть в обоих, но различаются)
        updated_items = []
        for xmind_item in xmind_records:
            if xmind_item['id'] in pyrus_ids:
                pyrus_item = next(item for item in pyrus_records if item['id'] == xmind_item['id'])
                if (xmind_item['title'] != pyrus_item['title'] or 
                    xmind_item['body'] != pyrus_item['body'] or
                    xmind_item['level'] != pyrus_item['level'] or
                    xmind_item['parent_id'] != pyrus_item['parent_id']):
                    updated_items.append(xmind_item)
        
        # 4. Обогащение данных
        enriched = []
        for item in new_items:
            item['action'] = 'new'
            item['task_id'] = None
            enriched.append(item)
        
        for item in updated_items:
            item['action'] = 'update'
            item['task_id'] = task_map.get(item['id'])
            enriched.append(item)
        
        for item in deleted_items:
            item['action'] = 'delete'
            item['task_id'] = task_map.get(item['id'])
            enriched.append(item)
        
        # 5. Формирование запросов для Pyrus
        def build_fields(item):
            return [
                {"id": 1, "value": item.get("id", "")},
                {"id": 2, "value": str(item.get("level", 0))},  # Конвертация в строку
                {"id": 3, "value": item.get("title", "")},
                {"id": 4, "value": item.get("parent_id", "")},
                {"id": 5, "value": item.get("body", "")}
            ]
        
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
        } for item in updated_items if item.get('task_id')]
        
        json_deleted = [{
            "method": "DELETE",
            "endpoint": f"/tasks/{item['task_id']}"
        } for item in deleted_items if item.get('task_id')]
        
        # 6. Формирование CSV данных
        csv_records = []
        for item in xmind_records:
            record = {
                "id": item["id"],
                "parent_id": item["parent_id"],
                "level": item["level"],
                "title": item["title"],
                "body": item["body"],
                "task_id": task_map.get(item["id"])
            }
            csv_records.append(record)
        
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
        
    except Exception as e:
        return {"error": f"Pyrus mapping error: {str(e)}"}
