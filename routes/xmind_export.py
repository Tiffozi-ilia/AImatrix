import pandas as pd
import json
import io
import zipfile
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from utils.data_loader import build_df_from_api

router = APIRouter()

@router.get("/xmind")
def export_xmind():
    df = build_df_from_api()
    df = df.sort_values(by="id")

    # Обеспечим наличие корня
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

    # Готовим словарь узлов
    nodes = {}

    for _, row in df.iterrows():
        node = {
            "id": row["id"],
            "title": row["title"],
            "children": {"attached": []},
            "properties": {
                "label": f"{row['id']}|{row.get('level','')}|{row.get('parent_id','')}|{row.get('parent_name','')}|{row.get('child_id','')}"
            },
        }
        if row["body"]:
            node["notes"] = {"plain": row["body"]}

        nodes[row["id"]] = node

    # Строим иерархию
    for _, row in df.iterrows():
        parent_id = row["parent_id"]
        if parent_id and parent_id in nodes:
            nodes[parent_id]["children"]["attached"].append(nodes[row["id"]])

    root_topic = nodes.get("+", {"title": "Пусто", "children": {}})

    # content.json
    content = {
        "rootTopic": root_topic
    }

    # metadata.json
    metadata = {
        "creator": "Render XMind Generator",
    }

    # Запись ZIP-архива в память
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("content.json", json.dumps(content, ensure_ascii=False, indent=2))
        zf.writestr("metadata.json", json.dumps(metadata, ensure_ascii=False, indent=2))
    buffer.seek(0)

    return StreamingResponse(buffer, media_type="application/vnd.xmind.workbook", headers={
        "Content-Disposition": "attachment; filename=matrix.xmind"
    })
