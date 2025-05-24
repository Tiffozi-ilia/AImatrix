from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from utils.data_loader import build_df_from_api
import xml.etree.ElementTree as ET
import io

router = APIRouter()

@router.get("/opml")
def export_opml():
    df = build_df_from_api()
    root = ET.Element("opml", version="2.0")
    body = ET.SubElement(root, "body")
    for _, row in df.iterrows():
        ET.SubElement(body, "outline", text=row["title"], _note=row["body"], id=row["id"])
    tree = ET.ElementTree(root)
    xml_buf = io.BytesIO()
    tree.write(xml_buf, encoding="utf-8", xml_declaration=True)
    xml_buf.seek(0)
    return StreamingResponse(xml_buf, media_type="text/xml", headers={
        "Content-Disposition": "attachment; filename=Matrix.opml"
    })