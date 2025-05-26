import pandas as pd
import json
import io
import zipfile
import time
import uuid
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from utils.data_loader import build_df_from_api

router = APIRouter()

def generate_id():
    return str(uuid.uuid4())

@xmind_export.get("/xmind")
def export_xmind():
    df = build_df_from_api()
    df = df.sort_values(by="id")

    # Гарантируем наличие корня
    if "+" not in df["id"].values:
        df = pd.concat([
            pd.DataFrame([{
                "id": "+",
                "title": "Корень",
                "body": "",
                "parent_id": "",
                "level": "0",
                "parent_name": "",
                "child_id": ""
            }]),
            df
        ], ignore_index=True)

    node_map = {}

    for _, row in df.iterrows():
        node_id = generate_id()
        node = {
            "id": node_id,
            "title": row["title"],
            "structureClass": "org.xmind.ui.logic.right",
            "children": {"attached": []},
            "properties": {
                "label": f"{row['id']}|{row.get('level','')}|{row.get('parent_id','')}|{row.get('parent_name','')}|{row.get('child_id','')}"
            }
        }
        if row["body"]:
            node["notes"] = {"plain": row["body"]}
        node_map[row["id"]] = node

    # Построение дерева
    for _, row in df.iterrows():
        parent_id = row["parent_id"]
        if parent_id and parent_id in node_map:
            node_map[parent_id]["children"]["attached"].append(node_map[row["id"]])

    # root
    root_topic = node_map.get("+", {
        "id": generate_id(),
        "title": "Пусто",
        "structureClass": "org.xmind.ui.logic.right",
        "children": {}
    })

    # content.json
    content = {
        "rootTopic": root_topic,
        "id": generate_id()
    }

    # metadata.json
    timestamp = int(time.time() * 1000)
    metadata = {
        "creator": "Almatrix",
        "created": timestamp,
        "modified": timestamp,
        "xmindVersion": "2023",
        "platform": "windows"
    }

    # Сборка .xmind ZIP
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("content.json", json.dumps(content, ensure_ascii=False, indent=2))
        zf.writestr("metadata.json", json.dumps(metadata, ensure_ascii=False, indent=2))
    buffer.seek(0)

    return StreamingResponse(
        buffer,
        media_type="application/vnd.xmind.workbook",
        headers={"Content-Disposition": "attachment; filename=matrix.xmind"}
    )
