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

    # Гарантируем, что есть фиксированный корень "+"
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

    # Создание элементов карты MindMap (.mm)
    nodes = {
        row["id"]: ET.Element("node", {
            "TEXT": row["title"],
            "ID": row["id"],
            "note": row["body"],
            "LABEL": f"{row['id']}|{row.get('level','')}|{row.get('parent_id','')}|{row.get('parent_name','')}|{row.get('child_id','')}"
        })
        for _, row in df.iterrows()
    }

    for _, row in df.iterrows():
        node = nodes[row["id"]]
        parent_id = row["parent_id"]
        if parent_id and parent_id in nodes:
            nodes[parent_id].append(node)

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
