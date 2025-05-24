import requests

PYRUS_TOKEN = "ВСТАВЬ_СЮДА_АКТУАЛЬНЫЙ_ТОКЕН"

def fetch_data():
    url = "https://api.pyrus.com/v4/forms/2309262/register"
    headers = {"Authorization": f"Bearer {PYRUS_TOKEN}"}
    resp = requests.get(url, headers=headers)
    return resp.json()

def extract(fields, key):
    for field in fields:
        if field.get("name") == key:
            return field.get("value", "")
    return ""

def extract_rows(data):
    rows = []
    for task in data.get("tasks", []):
        fields = task.get("fields", [])
        rows.append({
            "id": extract(fields, "matrix_id"),
            "title": extract(fields, "title"),
            "body": extract(fields, "body")
        })
    return rows