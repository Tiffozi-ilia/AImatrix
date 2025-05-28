from fastapi import APIRouter, UploadFile, File
import zipfile, io, json
import pandas as pd
from utils.data_loader import get_data
from utils.diff_engine import format_as_markdown

router = APIRouter()

def extract_pyrus_data():
    raw = get_data()

    # Строго парсим строку
    if isinstance(raw, str):
        raw = json.loads(raw)

    # 💥 Радикально: проверяем, что внутри "tasks" и выдёргиваем их
    if not isinstance(raw, dict) or "tasks" not in raw:
        raise ValueError("Pyrus JSON должен содержать ключ 'tasks'")

    raw_tasks = raw["tasks"]
    if not isinstance(raw_tasks, list):
        raise ValueError("'tasks' должен быть списком")

    # Чёткий разбор задач
    rows = []
    for task in raw_tasks:
        task_id = task.get("id")
        if not task_id:
            continue  # пропускаем мусор

        fields = {f.get("name"): f.get("value") for f in task.get("fields", [])}
        rows.append({
            "id": str(fields.get("matrix_id", "")).strip(),
            "title": str(fields.get("title", "")).strip(),
            "body": str(fields.get("body", "")).strip(),
            "level": str(fields.get("level", "")).strip(),
            "parent_id": str(fields.get("parent_id", "")).strip(),
            "pyrus_id": str(task_id)
        })

    return pd.DataFrame(rows)

@router.post("/xmind-delete")
async def detect_deleted_items(xmind: UploadFile = File(...)):
    content = await xmind.read()
    with zipfile.ZipFile(io.BytesIO(content)) as z:
        content_json = json.loads(z.read("content.json"))

    def walk(node, parent_id="", level=0):
        label = node.get("labels", [])
        node_id = label[0] if label else None
        title = node.get("title", "")
        body = node.get("notes", {}).get("plain", {}).get("content", "")
        rows = []
        if node_id:
            rows.append({
                "id": str(node_id).strip(),
                "title": title.strip(),
                "body": body.strip(),
                "level": str(level),
                "parent_id": parent_id.strip()
            })
        for child in node.get("children", {}).get("attached", []):
            rows.extend(walk(child, node_id, level + 1))
        return rows

    root_topic = content_json[0].get("rootTopic", {})
    xmind_df = pd.DataFrame(walk(root_topic))

    xmind_df["id"] = xmind_df["id"].astype(str).str.strip()
    pyrus_df = extract_pyrus_data()
    pyrus_df["id"] = pyrus_df["id"].astype(str).str.strip()

    deleted = pyrus_df[~pyrus_df["id"].isin(xmind_df["id"])].copy()
    records = deleted[["id", "parent_id", "level", "title", "body", "pyrus_id"]].to_dict(orient="records")

    return {"content": format_as_markdown(records)}
