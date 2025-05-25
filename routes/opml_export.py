from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from utils.data_loader import build_df_from_api
import xml.etree.ElementTree as ET
import io

router = APIRouter()

@router.get("/opml")
def export_opml():
    df = build_df_from_api()

    # Приведение типов
    df["id"] = df["id"].astype(str)
    df["parent_id"] = df["parent_id"].astype(str)
    df["title"] = df["title"].astype(str)
    df["body"] = df["body"].fillna("").astype(str)

    # Создание вспомогательных словарей
    title_map = dict(zip(df["id"], df["title"]))
    body_map = dict(zip(df["id"], df["body"]))

    children_map = {}
    for _, row in df.iterrows():
        pid = row["parent_id"]
        children_map.setdefault(pid, []).append(row["id"])

    # Формирование OPML
    root = ET.Element("opml", version="2.0")
    head = ET.SubElement(root, "head")
    ET.SubElement(head, "title").text = "Карта УБАиТ"
    body = ET.SubElement(root, "body")

    def build_outline(parent_el, node_id):
        node = ET.SubElement(
            parent_el,
            "outline",
            text=title_map.get(node_id, node_id),
            _note=body_map.get(node_id, ""),
            id=node_id
        )
        for child_id in sorted(children_map.get(node_id, [])):
            build_outline(node, child_id)

    # Корень и вложенность
    root_outline = ET.SubElement(body, "outline", text=title_map.get("+", "УБАиТ"), id="+")
    for top_id in sorted(children_map.get("+", [])):
        build_outline(root_outline, top_id)

    # Выгрузка
    buf = io.BytesIO()
    tree = ET.ElementTree(root)
    tree.write(buf, encoding="utf-8", xml_declaration=True)
    buf.seek(0)
    return StreamingResponse(buf, media_type="text/xml", headers={
        "Content-Disposition": "attachment; filename=Matrix.opml"
    })
