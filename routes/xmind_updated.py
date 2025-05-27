from fastapi import APIRouter, UploadFile
from utils.xmind_parser import flatten_xmind_nodes
from utils.data_loader import get_data
from utils.diff_engine import format_as_markdown
import zipfile, io, json

router = APIRouter()

@router.post("/xmind-updated")
async def xmind_updated(file: UploadFile):
    # Читаем XMind как zip
    content = await file.read()
    with zipfile.ZipFile(io.BytesIO(content)) as z:
        content_json = json.loads(z.read("content.json"))

    flat_xmind = flatten_xmind_nodes(content_json)

    # Получаем Pyrus JSON
    raw_data = get_data()
    if isinstance(raw_data, str):
        try:
            raw_data = json.loads(raw_data)
        except json.JSONDecodeError:
            raw_data = [json.loads(line) for line in raw_data.splitlines() if line.strip()]
    if isinstance(raw_data, dict):
        for value in raw_data.values():
            if isinstance(value, list):
                raw_data = value
                break
    if not isinstance(raw_data, list):
        raise ValueError(f"Pyrus data is not a list: got {type(raw_data)}")

    # Преобразуем Pyrus в словарь по id
    pyrus_map = {
        item["id"]: {"title": item.get("title", "").strip(), "body": item.get("body", "").strip()}
        for item in raw_data if isinstance(item, dict) and "id" in item
    }

    # Сравниваем: id совпадает, но title или body отличаются
    updated = []
    for node in flat_xmind:
        nid = node["id"]
        if nid in pyrus_map:
            pyrus = pyrus_map[nid]
            if node["title"].strip() != pyrus["title"] or node["body"].strip() != pyrus["body"]:
                updated.append({
                    "id": nid,
                    "parent_id": node["parent_id"],
                    "level": node["level"],
                    "title": node["title"].strip(),
                    "body": node["body"].strip()
                })

    return {"content": format_as_markdown(updated)}
