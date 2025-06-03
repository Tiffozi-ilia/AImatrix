import requests
import pandas as pd
import os
from fastapi import HTTPException
import time

_cached_token = None
_cached_expiration = 0

def get_pyrus_token():
    global _cached_token, _cached_expiration
    now = time.time()

    if _cached_token and now < _cached_expiration:
        return _cached_token

    login = os.environ.get("PYRUS_LOGIN")
    security_key = os.environ.get("PYRUS_SECURITY_KEY")

    if not login or not security_key:
        raise HTTPException(status_code=500, detail="PYRUS_LOGIN или PYRUS_SECURITY_KEY не заданы")

    auth_url = "https://accounts.pyrus.com/api/v4/auth/"
    headers = {"Content-Type": "application/json"}
    payload = {"login": login, "security_key": security_key}

    try:
        resp = requests.post(auth_url, json=payload, headers=headers)
        resp.raise_for_status()
        data = resp.json()
        _cached_token = data["access_token"]
        _cached_expiration = now + 55 * 60
        return _cached_token
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка авторизации в Pyrus: {str(e)}")
        
def get_data():
    token = get_pyrus_token()  # 🔁 вместо PYRUS_TOKEN из env
    url = "https://api.pyrus.com/v4/forms/2309262/register"
    headers = {"Authorization": f"Bearer {token}"}
    try:
        resp = requests.get(url, headers=headers)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка получения данных: {str(e)}")

def extract(fields, key):
    for field in fields:
        if field.get("name") == key:
            return field.get("value", "")
    return ""

def build_df_from_api():
    data = get_data()
    rows = []
    for task in data.get("tasks", []):
        fields = task.get("fields", [])
        rows.append({
            "id": extract(fields, "matrix_id"),
            "title": extract(fields, "title"),
            "body": extract(fields, "body"),
            "level": extract(fields, "level"),
            "parent_id": extract(fields, "parent_id"),
            "parent_name": extract(fields, "parent_name"),
            "child_id": extract(fields, "child_id")
        })
    return pd.DataFrame(rows)
# ------------------------------API---------------------------------------------------------
@router.post("/apply-to-pyrus")
async def apply_to_pyrus(mapping_data: dict = Body(...)):
    from fastapi.responses import JSONResponse
    import requests
    import logging

    # Настройка логирования
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)

    try:
        token = get_pyrus_token()
    except Exception as e:
        logger.error(f"Ошибка получения токена Pyrus: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={"error": f"Ошибка аутентификации в Pyrus: {str(e)}"}
        )

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    results = {"new": [], "updated": [], "deleted": []}
    error_count = 0

    # Обработка новых задач
    for item in mapping_data.get("new", []):
        try:
            endpoint = f"https://api.pyrus.com/v4{item['endpoint']}"
            resp = requests.post(endpoint, headers=headers, json=item["payload"])
            resp.raise_for_status()
            results["new"].append({
                "id": item["payload"]["fields"][0]["value"],
                "status": resp.status_code,
                "task_id": resp.json().get("task_id", "N/A")
            })
        except Exception as e:
            error_count += 1
            logger.error(f"Ошибка создания задачи: {str(e)}")
            results["new"].append({
                "error": str(e),
                "payload": item["payload"]
            })

    # Обработка обновлений
    for item in mapping_data.get("updated", []):
        try:
            endpoint = f"https://api.pyrus.com/v4{item['endpoint']}"
            resp = requests.post(endpoint, headers=headers, json=item["payload"])
            resp.raise_for_status()
            results["updated"].append({
                "id": item["endpoint"].split("/")[2],
                "status": resp.status_code
            })
        except Exception as e:
            error_count += 1
            logger.error(f"Ошибка обновления задачи: {str(e)}")
            results["updated"].append({
                "error": str(e),
                "payload": item["payload"]
            })

    # Обработка удалений
    for item in mapping_data.get("deleted", []):
        try:
            endpoint = f"https://api.pyrus.com/v4{item['endpoint']}"
            resp = requests.delete(endpoint, headers=headers)
            resp.raise_for_status()
            results["deleted"].append({
                "id": item["endpoint"].split("/")[2],
                "status": resp.status_code
            })
        except Exception as e:
            error_count += 1
            logger.error(f"Ошибка удаления задачи: {str(e)}")
            results["deleted"].append({
                "error": str(e),
                "endpoint": item["endpoint"]
            })

    return {
        "results": results,
        "success_count": sum(len(v) for v in results.values()) - error_count,
        "error_count": error_count
    }
