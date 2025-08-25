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

    auth_url = "https://pyrus.sovcombank.ru/api/v4/auth/"
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
    url = "https://pyrus.sovcombank.ru/api/v4/forms/484498/register"
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
