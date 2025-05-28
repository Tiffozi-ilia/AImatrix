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

def extract_pyrus_data():
    raw = get_data()
    if isinstance(raw, str):
        raw = json.loads(raw)
    if isinstance(raw, dict) and "tasks" in raw:
        raw = raw["tasks"]

    rows = []
    for task in raw:
        task_id = task.get("id", "")
        fields = {field["name"]: field.get("value", "") for field in task.get("fields", [])}
        rows.append({
            "id": fields.get("matrix_id", "").strip(),
            "title": fields.get("title", "").strip(),
            "body": fields.get("body", "").strip(),
            "level": str(fields.get("level", "")).strip(),
            "parent_id": fields.get("parent_id", "").strip(),
            "pyrus_id": str(task_id)
        })
    return pd.DataFrame(rows)

@router.post("/xmind-updated")
async def xmind_updated(xmind: UploadFile = File(...)):
    xmind_df = extract_xmind_nodes(xmind)
    pyrus_df = extract_pyrus_data()

    merged = pd.merge(xmind_df, pyrus_df, on="id", suffixes=("_xmind", "_pyrus"))

    # Сравниваем поля, которые могли измениться
    changed = merged[
        (merged["title_xmind"] != merged["title_pyrus"]) |
        (merged["body_xmind"] != merged["body_pyrus"]) |
        (merged["level_xmind"] != merged["level_pyrus"]) |
        (merged["parent_id_xmind"] != merged["parent_id_pyrus"])
    ]

    records = changed[[
        "id",
        "parent_id_pyrus", "level_pyrus", "title_pyrus", "body_pyrus", "pyrus_id",  # старое
        "parent_id_xmind", "level_xmind", "title_xmind", "body_xmind"               # новое
    ]].rename(columns={
        "parent_id_pyrus": "old_parent_id",
        "level_pyrus": "old_level",
        "title_pyrus": "old_title",
        "body_pyrus": "old_body",
        "parent_id_xmind": "new_parent_id",
        "level_xmind": "new_level",
        "title_xmind": "new_title",
        "body_xmind": "new_body"
    }).to_dict(orient="records")

    return {"content": format_as_markdown(records)}
