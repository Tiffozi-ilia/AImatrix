from fastapi import APIRouter
import pandas as pd
import httpx
from utils.data_loader import get_pyrus_token
import logging

router = APIRouter()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def enrich_parent_name(df: pd.DataFrame) -> pd.DataFrame:
    df["id"] = df["id"].astype(str).str.strip()
    df["parent_id"] = df["parent_id"].astype(str).str.strip()
    df["parent_name"] = df["parent_name"].astype(str).str.replace(r"\s+", "", regex=True)
    
    parent_map = dict(zip(df["id"], df["title"]))
    df["new_parent_name"] = df["parent_id"].map(parent_map)
    
    mask = (
        (df["parent_name"] == "") &
        (df["new_parent_name"].notna()) &
        (df["id"] != "+") &
        (df["parent_id"] != "+")
    )
    
    return df[mask][["task_id", "id", "title", "parent_id", "new_parent_name"]]

@router.get("/update_parent_names")
async def update_parent_names():
    logger.info("🔄 Запуск обновления parent_name...")

    json_url = "https://aimatrix-e8zs.onrender.com/json"
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.get(json_url)
            response.raise_for_status()
            json_data = response.json()
            
            if "tasks" not in json_data:
                logger.error("❌ Неверная структура JSON: отсутствует ключ 'tasks'")
                return {"status": "error", "details": "Invalid JSON structure: missing 'tasks' key"}
            
            rows = []
            for task in json_data["tasks"]:
                task_id = task["id"]
                fields = {f["name"]: f.get("value", "") for f in task.get("fields", [])}
                
                rows.append({
                    "task_id": task_id,
                    "id": fields.get("matrix_id", "").strip(),
                    "title": fields.get("title", "").strip(),
                    "parent_id": fields.get("parent_id", "").strip(),
                    "parent_name": fields.get("parent_name", "").strip(),
                })
            
            df = pd.DataFrame(rows)
            logger.info(f"📥 Загружено {len(df)} записей.")
            
    except Exception as e:
        logger.error(f"❌ Ошибка загрузки JSON: {e}")
        return {"status": "error", "details": f"JSON load error: {e}"}

    required_columns = ["task_id", "id", "title", "parent_id", "parent_name"]
    missing = [col for col in required_columns if col not in df.columns]
    if missing:
        logger.error(f"❌ Отсутствуют обязательные колонки: {missing}")
        return {"status": "error", "details": f"Missing columns: {missing}"}
    
    try:
        to_update = enrich_parent_name(df)
        logger.info(f"🔍 Найдено для обновления: {len(to_update)}")
    except Exception as e:
        logger.error(f"❌ Ошибка при подготовке данных: {e}")
        return {"status": "error", "details": f"enrichment error: {e}"}

    if to_update.empty:
        return {"status": "success", "updated": 0, "details": "No updates needed"}

    headers = {
        "Authorization": f"Bearer {get_pyrus_token()}",
        "Content-Type": "application/json"
    }

    results = []
    successful_updates = []
    
    async with httpx.AsyncClient(timeout=10.0) as client:
        for _, row in to_update.iterrows():
            task_id = row["task_id"]
            matrix_id = row["id"]
            title = row["title"]
            parent_id = row["parent_id"]
            parent_name = row["new_parent_name"]

            payload = {
                "field_updates": [
                    {"id": 8, "value": parent_name}
                ]
            }

            try:
                logger.info(f"➡️ Обновление [M:{matrix_id}, T:{task_id}] → {parent_name}")
                res = await client.post(
                    f"https://pyrus.sovcombank.ru/api/v4/tasks/{task_id}/comments",
                    headers=headers,
                    json=payload
                )
                res.raise_for_status()
                
                # Добавляем детали успешного обновления
                successful_updates.append({
                    "matrix_id": matrix_id,
                    "task_id": task_id,
                    "task_title": title,
                    "parent_id": parent_id,
                    "new_parent_name": parent_name
                })
                
                results.append({
                    "matrix_id": matrix_id,
                    "task_id": task_id,
                    "status": "success"
                })
                
            except httpx.HTTPStatusError as e:
                try:
                    error_body = e.response.json()
                except:
                    error_body = e.response.text
                error_msg = f"{e.response.status_code}: {error_body}"
                logger.error(f"❌ Ошибка {matrix_id}/{task_id}: {error_msg}")
                results.append({
                    "matrix_id": matrix_id,
                    "task_id": task_id,
                    "status": "error",
                    "details": error_msg
                })
            except Exception as e:
                logger.error(f"❌ Неожиданная ошибка {matrix_id}/{task_id}: {str(e)}")
                results.append({
                    "matrix_id": matrix_id,
                    "task_id": task_id,
                    "status": "error",
                    "details": str(e)
                })

    success = [r for r in results if r["status"] == "success"]
    errors = [r for r in results if r["status"] == "error"]

    logger.info(f"✅ Успешно: {len(success)}, ❌ Ошибки: {len(errors)}")

    # Формируем детализированный ответ
    response = {
        "status": "completed",
        "updated": len(success),
        "errors": len(errors),
        "successful_updates": successful_updates,
        "error_details": [r for r in results if r["status"] == "error"]
    }

    # Добавляем статистику в логи
    logger.info(f"📊 Статистика обновлений: {response}")

    return response