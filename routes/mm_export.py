# Пересоздание маршрута /mm после сброса состояния
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
import pandas as pd
import xml.etree.ElementTree as ET
import io

router = APIRouter()

def build_df_from_api():
    # Мок-данные для демонстрации
    return pd.DataFrame([
        {"id": "a.a.01", "title": "Заголовок 1", "body": "Описание 1", "level": "2"},
        {"id": "a.a.01.01", "title": "Заголовок 1.1", "body": "Описание 1.1", "level": "3"},
    ])

@router.get("/mm")
def export_mm():
    df = build_df_from_api()
    df = df.sort_values(by="id")

    root = ET.Element("map", version="1.0.1")

    for _, row in df.iterrows():
        node = ET.SubElement(root, "node")
        node.set("TEXT", row["title"])

        label_value = f"id: {row.get('id', '')} | level: {row.get('level', '')}"
        node.set("LABEL", label_value)

        if row.get("body"):
            richcontent = ET.SubElement(node, "richcontent", TYPE="NOTE")
            html = ET.SubElement(richcontent, "html")
            body = ET.SubElement(html, "body")
            body.text = row["body"]

    tree = ET.ElementTree(root)
    output = io.BytesIO()
    tree.write(output, encoding="utf-8", xml_declaration=True)
    output.seek(0)

    return StreamingResponse(output, media_type="application/x-freemind", headers={
        "Content-Disposition": "attachment; filename=matrix.mm"
    })
