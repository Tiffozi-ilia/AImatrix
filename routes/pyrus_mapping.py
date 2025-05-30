from fastapi import APIRouter, Body
import requests

router = APIRouter()

RENDER_URL = "https://aimatrix-e8zs.onrender.com"

@router.post("/pyrus_mapping")
async def pyrus_mapping(url: str = Body(...)):
    payload = {"url": url}

    try:
        # 1. xmind-updated
        updated_resp = requests.post(f"{RENDER_URL}/xmind-updated", json=payload)
        updated_resp.raise_for_status()
        updated_json = updated_resp.json()

        # 2. xmind-delete
        deleted_resp = requests.post(f"{RENDER_URL}/xmind-delete", json=payload)
        deleted_resp.raise_for_status()
        deleted_json = deleted_resp.json()

        # 3. pyrus_mapping (map) — id → task_id
        map_resp = requests.get(f"{RENDER_URL}/pyrus_mapping")
        map_resp.raise_for_status()
        task_map = map_resp.json()

        # 4. enrichment
        enriched = []
        for item in updated_json.get("json", []):
            item["task_id"] = task_map.get(item["id"])
            item["action"] = "update"
            enriched.append(item)

        for item in deleted_json.get("json", []):
            item["task_id"] = task_map.get(item["id"])
            item["action"] = "delete"
            enriched.append(item)

        return {
            "actions": enriched,
            "markdown": {
                "updated": updated_json.get("content", ""),
                "deleted": deleted_json.get("content", "")
            }
        }

    except Exception as e:
        return {"error": str(e)}
