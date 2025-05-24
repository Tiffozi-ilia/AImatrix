import pandas as pd
import requests

def build_df_from_api():
    PYRUS_TOKEN = "ВСТАВЬ_СВОЙ_ТОКЕН"
    url = "https://api.pyrus.com/v4/forms/2309262/register"
    headers = {"Authorization": f"Bearer {PYRUS_TOKEN}"}
    resp = requests.get(url, headers=headers)
    data = resp.json()

    def extract(fields, key):
        for field in fields:
            if field.get("name") == key:
                return field.get("value", "")
        return ""

    rows = []
    for task in data.get("tasks", []):
        fields = task.get("fields", [])
        rows.append({
            "id": extract(fields, "matrix_id"),
            "title": extract(fields, "title"),
            "body": extract(fields, "body")
        })

    return pd.DataFrame(rows)