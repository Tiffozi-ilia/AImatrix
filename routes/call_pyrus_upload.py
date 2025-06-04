import requests
import json
from fastapi import APIRouter, Body, HTTPException

router = APIRouter()

@router.post("/call-pyrus-upload")
async def call_pyrus_upload(url: str = Body(..., embed=True)):
    """Точная копия вашего скрипта для вызова через Dify"""
    try:
        # Используем переданный URL XMind-файла
        xmind_url = url
        headers = {"Content-Type": "application/json"}
        payload = json.dumps({"url": xmind_url})  # Исправлено формирование payload

        base = "https://aimatrix-e8zs.onrender.com"  # Ваш базовый URL

        endpoints = {
            "DIFF": f"{base}/xmind-diff",
            "UPDATED": f"{base}/xmind-updated",
            "DELETED": f"{base}/xmind-delete",
            "MAPPING": f"{base}/xmind_procedures/pyrus_mapping"  # Исправленный путь
        }

        results = {}

        # === ВЫЗОВ ОСНОВНЫХ ПРОЦЕДУР =================================
        for name, endpoint_url in endpoints.items():
            try:
                response = requests.post(endpoint_url, data=payload, headers=headers)
                response.raise_for_status()
                data = response.json()
                results[name] = data
                
            except Exception as e:
                results[name] = {"error": str(e)}
                if hasattr(e, 'response') and e.response:
                    results[name]["status_code"] = e.response.status_code
                    results[name]["response_text"] = e.response.text[:500]

        # === ФОРМИРОВАНИЕ ОТВЕТА =====================================
        response_data = {
            "status": "success",
            "results": results,
            "summary": {
                "DIFF": len(results.get("DIFF", {}).get("json", [])),
                "UPDATED": len(results.get("UPDATED", {}).get("json", [])),
                "DELETED": len(results.get("DELETED", {}).get("json", []))
            },
            "pyrus_actions": {
                "new": results.get("MAPPING", {}).get("for_pyrus", {}).get("new", []),
                "updated": results.get("MAPPING", {}).get("for_pyrus", {}).get("updated", []),
                "deleted": results.get("MAPPING", {}).get("for_pyrus", {}).get("deleted", [])
            }
        }

        return response_data

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
