from fastapi import APIRouter, UploadFile, File
import zipfile, io, json
import pandas as pd
from utils.data_loader import get_data
from utils.diff_engine import format_as_markdown

router = APIRouter()

def extract_xmind_nodes(xmind_file: UploadFile):
    content = xmind_file.file.read()
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
                "id": node_id.strip(),
                "title": title.strip(),
                "body": body.strip(),
                "level": str(level),
                "parent_id": parent_id.strip()
            })
        for child in node.get("children", {}).get("attached", []):
            rows.extend(walk(child, node_id, level + 1))
        return rows

    root_topic = content_json[0].get("rootTopic", {})
    return pd.DataFrame(walk(root_topic))

def extract_pyrus_data_and_map():
    raw = get_data()
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            raw = [json.loads(line) for line in raw.splitlines() if line.strip()]
    if isinstance(raw, dict):
        for value in raw.values():
            if isinstance(value, list):
                raw = value
                break
    if not isinstance(raw, list):
        raise ValueError("Pyrus data is not a list")

    rows = []
    id_to_task = {}

    for task in raw:
        task_id = str(task.get("id", "")).strip()
        fields = {field["name"]: field.get("value", "") for field in task.get("fields", [])}
        matrix_id = str(fields.get("matrix_id", "")).strip()

        if matrix_id:
            id_to_task[matrix_id] = task_id  # <- маппинг matrix_id → pyrus task_id

        rows.append({
            "id": matrix_id,
            "title": str(fields.get("title", "")).strip(),
            "body": str(fields.get("body", "")).strip(),
            "level": str(fields.get("level", "")).strip(),
            "parent_id": str(fields.get("parent_id", "")).strip()
        })

    return pd.DataFrame(rows), id_to_task

@router.post("/xmind-delete")
async def detect_deleted_items(xmind: UploadFile = File(...)):
    xmind_df = extract_xmind_nodes(xmind)
    pyrus_df, id_to_task = extract_pyrus_data_and_map()

    # Очистка
    xmind_df["id"] = xmind_df["id"].astype(str).str.strip()
    pyrus_df["id"] = pyrus_df["id"].astype(str).str.strip()

    # Поиск удалённых
    deleted = pyrus_df[~pyrus_df["id"].isin(xmind_df["id"])].copy()

    # Восстановление pyrus_id через map
    deleted["pyrus_id"] = deleted["id"].map(id_to_task)

    # Форматированный вывод
    records = deleted[["id", "parent_id", "level", "title", "body", "pyrus_id"]].to_dict(orient="records")
    return {"content": format_as_markdown(records)}
