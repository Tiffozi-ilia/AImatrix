import pandas as pd
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from utils.data_loader import build_df_from_api
import xml.etree.ElementTree as ET
import io

router = APIRouter()

@router.get("/mm")
def export_mm():
    df = build_df_from_api()
    df = df.sort_values(by="id")

    # Добавим корень вручную
    root_dict = {
        "id": "+",
        "title": "Matrix Root",
        "body": "",
        "level": "0",
        "parent_id": "",
        "parent_name": "",
        "child_id": ""
    }
    df.loc[-1] = root_dict  # временная вставка
    df.index = df.index + 1
    df = df.sort_index()

    # Построение узлов
    nodes = {}
    for _, row in df.iterrows():
        node = ET.Element("node", {
            "TEXT": row["title"],
            "ID": row["id"],
            "level": str(row["level"])
        })
        note = ET.SubElement(node, "richcontent", {"TYPE": "NOTE"})
        note.text = row["body"]
        nodes[row["id"]] = node

    root_node = None
    for _, row in df.iterrows():
        current_id = row["id"]
        parent_id = row["parent_id"]
        if current_id == "+":
            root_node = nodes[current_id]
        elif parent_id in nodes:
            nodes[parent_id].append(nodes[current_id])

    map_elem = ET.Element("map", version="1.0.1")
    if root_node is not None:
        map_elem.append(root_node)

    tree = ET.ElementTree(map_elem)
    output = io.BytesIO()
    tree.write(output, encoding="utf-8", xml_declaration=True)
    output.seek(0)

    return StreamingResponse(output, media_type="text/xml", headers={
        "Content-Disposition": "attachment; filename=matrix.mm"
    })
