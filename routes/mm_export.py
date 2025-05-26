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
    df["id"] = df["id"].astype(str).str.strip()
    df["parent_id"] = df["parent_id"].astype(str).str.strip()

    # Словари
    title_map = {row["id"]: row["title"] for _, row in df.iterrows()}
    node_data_map = {row["id"]: row for _, row in df.iterrows()}
    children_map = {}

    for _, row in df.iterrows():
        pid = row["parent_id"]
        cid = row["id"]
        children_map.setdefault(pid, []).append(cid)

    # Построение узла с richcontent note и LABEL
    def build_node(node_id):
        row = node_data_map[node_id]
        node_elem = ET.Element("node", {
            "TEXT": str(row.get("title", "")),
            "ID": str(row["id"]),
            "LABEL": f"{row['id']}|{row.get('level','')}|{row.get('parent_id','')}|{row.get('parent_name','')}|{row.get('child_id','')}"
        })

        # Корректное добавление заметки (note)
        if row.get("body", "").strip():
            rc = ET.SubElement(node_elem, "richcontent", TYPE="NOTE")
            html = ET.SubElement(rc, "html")
            body = ET.SubElement(html, "body")
            body.text = str(row["body"])

        for child_id in sorted(children_map.get(node_id, [])):
            node_elem.append(build_node(child_id))

        return node_elem

    # Формирование карты
    map_elem = ET.Element("map", version="1.0.1")
    root_node = ET.SubElement(map_elem, "node", {
        "TEXT": title_map.get("+", "УБАиТ"),
        "ID": "+",
        "LABEL": "+|0|||"
    })

    if "+" in children_map:
        for top_id in sorted(children_map["+"]):
            root_node.append(build_node(top_id))

    tree = ET.ElementTree(map_elem)
    output = io.BytesIO()
    tree.write(output, encoding="utf-8", xml_declaration=True)
    output.seek(0)

    return StreamingResponse(output, media_type="application/xml", headers={
        "Content-Disposition": "attachment; filename=matrix.mm"
    })
