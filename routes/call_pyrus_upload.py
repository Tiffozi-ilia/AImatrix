import requests
import json
from fastapi import FastAPI, APIRouter
from pydantic import BaseModel

router = APIRouter()

class UploadInput(BaseModel):
    xmind_url: str

@router.post("/call_pyrus_upload")
async def call_pyrus_upload(payload: UploadInput):
    api_url = "https://aimatrix-e8zs.onrender.com/pyrus_mapping"
    headers = {"Content-Type": "application/json"}
    
    # Исправленная сериализация
    payload_data = {"url": payload.xmind_url}
    payload_json = json.dumps(payload_data)

    try:
        res = requests.post(api_url, data=payload_json, headers=headers)
        res.raise_for_status()
        data = res.json()
        
        # Проверка структуры ответа
        if "for_pyrus" not in data:
            return {
                "status": "❌ Ошибка формата ответа",
                "details": "Отсутствует ключ 'for_pyrus' в ответе",
                "response": data
            }
            
        return {
            "status": "✅ Успешно передано в Pyrus",
            "new": len(data["for_pyrus"].get("new", [])),
            "updated": len(data["for_pyrus"].get("updated", [])),
            "deleted": len(data["for_pyrus"].get("deleted", [])),
        }
    except requests.exceptions.HTTPError as e:
        return {
            "status": f"❌ HTTP ошибка ({e.response.status_code})",
            "details": str(e),
            "response": e.response.text
        }
    except Exception as e:
        return {
            "status": "❌ Системная ошибка",
            "details": str(e)
        }
