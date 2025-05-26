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

    root_node = None
    for _, row in df.iterrows():
        node = nodes[row["id"]]
        if row["parent_id"]:
            parent = nodes.get(row["parent_id"])
            if parent is not None:
                parent.append(node)
        else:
            root_node = node

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
