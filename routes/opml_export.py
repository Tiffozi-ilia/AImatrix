from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from utils.data_loader import build_df_from_api
import xml.etree.ElementTree as ET
import io

router = APIRouter()

@router.get("/opml")
def export_opml():
    df = build_df_from_api()
    df = df.sort_values(by="id")

    root = ET.Element("opml", version="2.0")
    head = ET.SubElement(root, "head")
    ET.SubElement(head, "title").text = "Matrix Export"

    body = ET.SubElement(root, "body")

    for _, row in df.iterrows():
        node = ET.SubElement(body, "outline")
        node.set("text", row["title"])
        node.set("_note", row["body"])
        node.set("id", row["id"])
        if row.get("parent_id"):
            node.set("parent_id", row["parent_id"])
        if row.get("child_id"):
            node.set("child_id", row["child_id"])
        if row.get("level"):
            node.set("level", str(row["level"]))
        if row.get("parent_name"):
            node.set("parent_name", row["parent_name"])

    tree = ET.ElementTree(root)
    output = io.BytesIO()
    tree.write(output, encoding="utf-8", xml_declaration=True)
    output.seek(0)
    return StreamingResponse(output, media_type="text/xml", headers={
        "Content-Disposition": "attachment; filename=matrix.opml"
    })
