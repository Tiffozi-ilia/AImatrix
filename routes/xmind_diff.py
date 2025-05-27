from fastapi import APIRouter, UploadFile
from utils.xmind_parser import flatten_xmind_nodes
from utils.diff_engine import find_new_nodes, format_as_markdown
from utils.data_loader import get_data
import zipfile, io, json

router = APIRouter()

@router.post("/xmind-diff")
async def xmind_diff(file: UploadFile):
    # Читаем .xmind файл как zip
    content = await file.read()
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
            # Если пришла строка с несколькими json-объектами построчно
            raw_data = [json.loads(line) for line in raw_data.splitlines() if line.strip()]

    if not isinstance(raw_data, list):
        raise ValueError("Pyrus data is not a list")

    # Собираем ID
    pyrus_ids = {item["id"] for item in raw_data if isinstance(item, dict) and "id" in item}

    # Вычисляем только новые
    new_nodes = find_new_nodes(flat_xmind, pyrus_ids)

    # Отдаём markdown
    return {"content": format_as_markdown(new_nodes)}
