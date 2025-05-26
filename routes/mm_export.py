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

    # Добавляем корень, если его нет
    if "+" not in df["id"].values:
        df = pd.concat([
            pd.DataFrame([{
                "id": "+",
                "title": "УБАИТ",
                "body": "",
                "parent_id": "",
                "level": "0",
                "parent_name": "",
                "child_id": ""
            }]),
            df
        ], ignore_index=True)

    nodes = {}

    for _, row in df.iterrows():
        node = ET.Element("node", {
            "TEXT": row["title"],
            "ID": row["id"]
        })

        # Notes (body → richcontent)
        if row["body"]:
            rich = ET.SubElement(node, "richcontent", {"TYPE": "NOTE"})
            html = ET.SubElement(rich, "html")
            ET.SubElement(html, "head")
            body_html = ET.SubElement(html, "body")
            body_html.text = row["body"]

        # Ярлык как атрибут → сохраняется в свойствах .xmind
        label_value = f"{row['id']}|{row.get('level','')}|{row.get('parent_id','')}|{row.get('parent_name','')}|{row.get('child_id','')}"
        ET.SubElement(node, "attribute", {
            "NAME": "label",
            "VALUE": label_value
        })

        nodes[row["id"]] = node

    # Строим иерархию
    for _, row in df.iterrows():
        node = nodes[row["id"]]
        parent_id = row["parent_id"]
        if parent_id and parent_id in nodes:
            nodes[parent_id].append(node)

    # Финальный XML
    map_elem = ET.Element("map", version="1.0.1")
    root_node = nodes.get("+")
    if root_node is not None:
        map_elem.append(root_node)

    tree = ET.ElementTree(map_elem)
    output = io.BytesIO()
    tree.write(output, encoding="utf-8", xml_declaration=True)
    output.seek(0)

    return StreamingResponse(output, media_type="application/xml", headers={
        "Content-Disposition": "attachment; filename=matrix.mm"
    })
