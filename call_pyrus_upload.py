import requests
import json
from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI()

class UploadInput(BaseModel):
    xmind_url: str

@app.post("/call_pyrus_upload")
async def call_pyrus_upload(payload: UploadInput):
    api_url = "https://aimatrix-e8zs.onrender.com/pyrus_mapping"
    headers = {"Content-Type": "application/json"}
    payload_json = json.dumps(payload.xmind_url)

    try:
        res = requests.post(api_url, data=payload_json, headers=headers)
        res.raise_for_status()
        data = res.json()
        return {
            "status": "✅ Успешно передано в Pyrus",
            "new": len(data.get("for_pyrus", {}).get("new", [])),
            "updated": len(data.get("for_pyrus", {}).get("updated", [])),
            "deleted": len(data.get("for_pyrus", {}).get("deleted", [])),
        }
    except Exception as e:
        return {"status": "❌ Ошибка", "details": str(e)}
