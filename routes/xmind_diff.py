from fastapi import APIRouter, UploadFile
from utils.xmind_parser import flatten_xmind_nodes
from utils.diff_engine import format_as_markdown
from utils.data_loader import get_data
from fastapi import APIRouter, Body
import zipfile, io, json

router = APIRouter()

@router.post("/xmind-diff")
@router.post("/xmind-diff")
async def xmind_diff(url: str = Body(...)):
    import requests
    content = requests.get(url).content
    with zipfile.ZipFile(io.BytesIO(content)) as z:
        content_json = json.loads(z.read("content.json"))

    # Разворачиваем xmind в список
    flat_xmind = flatten_xmind_nodes(content_json)

    # Получаем и парсим данные из Pyrus
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
        raise ValueError(f"Pyrus data is not a list: got {type(raw_data)} instead")

    # Собираем ID из Pyrus
    pyrus_ids = {
        item["id"] for item in raw_data
        if isinstance(item, dict) and "id" in item
    }

    # Фильтруем только новые и сгенерированные
    new_nodes = [
        n for n in flat_xmind
        if n.get("generated") and n["id"] not in pyrus_ids
    ]

    return {
    "content": format_as_markdown(new_nodes),
    "json": new_nodes
    }
