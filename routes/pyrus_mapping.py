from fastapi import APIRouter
from pydantic import BaseModel
import requests
import json

router = APIRouter()

class UrlInput(BaseModel):
    url: str

@router.post("/split_url_to_update_delete")
async def split_url(body: UrlInput):
    url = body.url
    payload = json.dumps({"url": url})
    headers = {"Content-Type": "application/json"}

    result = {}

    # xmind-updated
    try:
        updated_resp = requests.post("https://aimatrix-e8zs.onrender.com/xmind-updated", data=payload, headers=headers)
        updated_resp.raise_for_status()
        result["updated"] = updated_resp.json()
    except Exception as e:
        result["updated"] = {"error": str(e)}

    # xmind-delete
    try:
        deleted_resp = requests.post("https://aimatrix-e8zs.onrender.com/xmind-delete", data=payload, headers=headers)
        deleted_resp.raise_for_status()
        result["deleted"] = deleted_resp.json()
    except Exception as e:
        result["deleted"] = {"error": str(e)}

    return result
