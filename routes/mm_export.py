from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from utils.data_loader import build_df_from_api
import xml.etree.ElementTree as ET
import pandas as pd
import io

router = APIRouter()

@router.get("/mm")
def export_mm():
    df = build_df_from_api()
    df = df.sort_values(by="id")

    # Создание элементов карты MindMap (.mm)
    nodes = {}
    for _, row in df.iterrows():
        node = ET.Element("node", {
            "TEXT": str(row["title"]),
            "ID": str(row["id"]),
            "note": str(row.get("body", "")),
            "LABEL": f"{row.get('id','')}|{row.get('level','')}|{row.get('parent_id','')}|{row.get('parent_name','')}|{row.get('child_id','')}"
        })
        nodes[row["id"]] = node

    # Построение иерархии
    for _, row in df.iterrows():
        node = nodes[row["id"]]
        parent_id = row.get("parent_id")
        if parent_id and parent_id in nodes:
            nodes[parent_id].append(node)

    # Корень — узел с id == "+"
    root_node = nodes.get("+")
    map_elem = ET.Element("map", version="1.0.1")
    if root_node is not None:
        map_elem.append(root_node)

    tree = ET.ElementTree(map_elem)
    output = io.BytesIO()
    tree.write(output, encoding="utf-8", xml_declaration=True)
    output.seek(0)

    return StreamingResponse(output, media_type="application/xml", headers={
        "Content-Disposition": "attachment; filename=matrix.mm"
    })
