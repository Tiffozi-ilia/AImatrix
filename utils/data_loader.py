import requests
import pandas as pd
import os
from fastapi import HTTPException

def get_data():
    PYRUS_TOKEN = os.environ.get("PYRUS_TOKEN")
    if not PYRUS_TOKEN:
        raise HTTPException(status_code=500, detail="PYRUS_TOKEN не задан")

    url = "https://api.pyrus.com/v4/forms/2309262/register"
    headers = {"Authorization": f"Bearer {PYRUS_TOKEN}"}
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


