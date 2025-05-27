from fastapi import APIRouter, UploadFile
from utils.xmind_parser import flatten_xmind_nodes
from utils.diff_engine import find_new_nodes, format_as_markdown
from utils.data_loader import get_data
import zipfile, io, json

router = APIRouter()

@router.post("/xmind-diff")
async def xmind_diff(file: UploadFile):
    content = await file.read()
    with zipfile.ZipFile(io.BytesIO(content)) as z:
        content_json = json.loads(z.read("content.json"))

    flat_xmind = flatten_xmind_nodes(content_json)
    pyrus_ids = {item["id"] for item in get_data()}

    new_nodes = find_new_nodes(flat_xmind, pyrus_ids)
    return {"content": format_as_markdown(new_nodes)}
