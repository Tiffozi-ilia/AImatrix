from fastapi import FastAPI, HTTPException
import requests

app = FastAPI()

@app.get("/generate-matrix")
def generate_matrix():
    PYRUS_TOKEN = "вставь_сюда_токен"
    url = "https://api.pyrus.com/v4/forms/2309262/register"
    headers = {"Authorization": f"Bearer {PYRUS_TOKEN}"}

    resp = requests.get(url, headers=headers)

    if resp.status_code != 200:
        raise HTTPException(status_code=resp.status_code, detail="Ошибка от Pyrus API")

    try:
        data = resp.json()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Невалидный JSON от Pyrus: {str(e)}")

    return {
        "status": "ok",
        "tasks_count": len(data.get("tasks", [])),
        "example": data.get("tasks", [])[0] if data.get("tasks") else {}
    }
