from fastapi import APIRouter, UploadFile, File
import pandas as pd
import requests
import io

router = APIRouter()

@router.post("/pyrus_mapping")
async def pyrus_mapping(task_csv: UploadFile = File(...)):
    csv_data = pd.read_csv(io.StringIO((await task_csv.read()).decode("utf-8")))
    task_map = {row["id"]: row["task_id"] for _, row in csv_data.iterrows()}

    updated = requests.get("https://aimatrix-e8zs.onrender.com/xmind-updated").json().get("updated", [])
    deleted = requests.get("https://aimatrix-e8zs.onrender.com/xmind-delete").json().get("deleted", [])

    enriched = []

    for item in updated:
        item["task_id"] = task_map.get(item["id"])
        item["action"] = "update"
        enriched.append(item)

    for item in deleted:
        item["task_id"] = task_map.get(item["id"])
        item["action"] = "delete"
        enriched.append(item)

    return {"actions": enriched}
