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

def create_node(row):
    node = {
        "id": row["id"],
        "class": "topic",
        "title": row["title"],
        "labels": [f"{row['id']}"]
    }
    if pd.notna(row.get("body")) and row["body"].strip():
        node["notes"] = {
            "plain": {
                "content": row["body"]
            }
        }
    return node

@router.get("/xmind")
def export_xmind():
    df = build_df_from_api()
    df = df.sort_values(by="id")

    if "+" not in df["id"].values:
        df = pd.concat([pd.DataFrame([{
            "id": "+",
            "title": "Корень",
            "body": "",
            "parent_id": "",
            "level": "0",
            "parent_name": "",
            "child_id": ""
        }]), df], ignore_index=True)

    node_map = {row["id"]: create_node(row) for _, row in df.iterrows()}

    for _, row in df.iterrows():
        parent_id = row["parent_id"]
        if parent_id and parent_id in node_map:
            parent = node_map[parent_id]
            if "children" not in parent:
                parent["children"] = {"attached": []}
            parent["children"]["attached"].append(node_map[row["id"]])

    root_topic = node_map.get("+", {
        "id": "+",
        "class": "topic",
        "title": "Пусто"
    })

    content = [{
        "id": generate_id(),
        "class": "sheet",
        "title": "Almatrix",
        "rootTopic": root_topic
    }]

    timestamp = int(time.time() * 1000)
    metadata = {
        "dataStructureVersion": "2",
        "creator": {
            "name": "Almatrix",
            "version": "1.0"
        },
        "layoutEngineVersion": "3",
        "activeSheetId": content[0]["id"],
        "familyId": f"local-{str(uuid.uuid4()).replace('-', '')}"
    }

    manifest = {
        "file-entries": {
            "content.json": {},
            "metadata.json": {}
        }
    }

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("content.json", json.dumps(content, ensure_ascii=False, indent=2))
        zf.writestr("metadata.json", json.dumps(metadata, ensure_ascii=False, indent=2))
        zf.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))

    buffer.seek(0)
    return StreamingResponse(
        buffer,
        media_type="application/vnd.xmind.workbook",
        headers={"Content-Disposition": "attachment; filename=matrix.xmind"}
    )
