import requests
from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()

class UploadInput(BaseModel):
    xmind_url: str

@router.post("/call_pyrus_upload")
async def call_pyrus_upload(payload: UploadInput):
    api_url = "https://aimatrix-e8zs.onrender.com/pyrus_mapping"
    
    try:
        res = requests.post(api_url, json={"url": payload.xmind_url})
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
