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
from fastapi import APIRouter, Body
from fastapi.responses import JSONResponse
from utils.data_loader import get_pyrus_token
from routes.xmind_procedures import pyrus_mapping
import requests

router = APIRouter()

@router.post("/apply-to-pyrus")
async def apply_to_pyrus(url: str = Body(...)):
    token = get_pyrus_token()
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    mapping_result = await pyrus_mapping(url)
    if "error" in mapping_result:
        return JSONResponse(status_code=400, content={"error": mapping_result["error"]})

    for_pyrus = mapping_result.get("for_pyrus", {})
    results = {"new": [], "updated": [], "deleted": []}
    summary = {"new": 0, "updated": 0, "deleted": 0, "errors": 0}

    for section in ["new", "updated", "deleted"]:
        for item in for_pyrus.get(section, []):
            method = item.get("method", "POST")
            endpoint = item.get("endpoint")
            payload = item.get("payload", None)
            url_full = f"https://api.pyrus.com/v4{endpoint}"

            try:
                if method == "POST":
                    resp = requests.post(url_full, headers=headers, json=payload)
                elif method == "DELETE":
                    resp = requests.delete(url_full, headers=headers)
                else:
                    raise Exception(f"Unsupported method: {method}")

                result_entry = {
                    "status": resp.status_code,
                    "endpoint": endpoint,
                    "method": method,
                    "response": resp.json() if resp.content else {},
                }
                if payload:
                    result_entry["payload"] = payload

                results[section].append(result_entry)

                if resp.status_code == 200:
                    summary[section] += 1
                else:
                    summary["errors"] += 1

            except Exception as e:
                results[section].append({
                    "status": "error",
                    "method": method,
                    "endpoint": endpoint,
                    "error": str(e),
                    "payload": payload
                })
                summary["errors"] += 1

    return {
        "summary": summary,
        "results": results
    }
