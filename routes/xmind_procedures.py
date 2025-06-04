from fastapi import APIRouter, Body
import zipfile, io, json, requests
import pandas as pd
from utils.data_loader import get_data, get_pyrus_token
from utils.diff_engine import format_as_markdown
from utils.xmind_parser import flatten_xmind_nodes

router = APIRouter()

# === DIFF ======================================================================
@router.post("/xmind-diff")
async def xmind_diff(url: str = Body(...)):
    content = requests.get(url).content
    with zipfile.ZipFile(io.BytesIO(content)) as z:
        content_json = json.loads(z.read("content.json"))

    flat_xmind = flatten_xmind_nodes(content_json)

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
        raise ValueError("Pyrus data is not a list")

    pyrus_ids = {
        str(item["id"]) for item in raw_data
        if isinstance(item, dict) and "id" in item
    }

    max_numbers = {}
    all_existing_ids = set(pyrus_ids)
    for item_id in all_existing_ids:
        if isinstance(item_id, str) and '.' in item_id:
            parts = item_id.split('.')
            if parts[-1].isdigit():
                base = '.'.join(parts[:-1])
                number = int(parts[-1])
                if base not in max_numbers or number > max_numbers[base]:
                    max_numbers[base] = number

    for node in flat_xmind:
        node_id = node.get("id")
        if node_id:
            node_id_str = str(node_id)
            if '.' in node_id_str:
                parts = node_id_str.split('.')
                if parts[-1].isdigit():
                    base = '.'.join(parts[:-1])
                    number = int(parts[-1])
                    if base not in max_numbers or number > max_numbers[base]:
                        max_numbers[base] = number

    used_ids = set(all_existing_ids)
    new_nodes = []

    for node in flat_xmind:
        node_id = node.get("id")
        parent_id = node.get("parent_id", "")
        node_id_str = str(node_id) if node_id else ""
        if not node_id_str or node_id_str in used_ids:
            base = str(parent_id) if parent_id else "x"
            current_max = max_numbers.get(base, 0)
            new_number = current_max + 1
            new_id = f"{base}.{str(new_number).zfill(2)}"
            node["id"] = new_id
            node["generated"] = True
            max_numbers[base] = new_number
            used_ids.add(new_id)
        else:
            used_ids.add(node_id_str)
        if node.get("generated") and node["id"] not in pyrus_ids:
            new_nodes.append(node)

    return {
        "content": format_as_markdown(new_nodes),
        "json": new_nodes
    }

# === SHARED PARSERS ============================================================
def extract_xmind_nodes(file: io.BytesIO):
    with zipfile.ZipFile(file) as z:
        content_json = json.loads(z.read("content.json"))

    def walk(node, parent_id="", level=0):
        label = node.get("labels", [])
        node_id = label[0] if label else None
        title = node.get("title", "")
        body = node.get("notes", {}).get("plain", {}).get("content", "")
        rows = []
        if node_id:
            rows.append({
                "id": node_id.strip(),
                "title": title.strip(),
                "body": body.strip(),
                "level": str(level),
                "parent_id": parent_id.strip()
            })
        for child in node.get("children", {}).get("attached", []):
            rows.extend(walk(child, node_id, level + 1))
        return rows

    root_topic = content_json[0].get("rootTopic", {})
    return pd.DataFrame(walk(root_topic))


def extract_pyrus_data():
    raw = get_data()
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            raw = [json.loads(line) for line in raw.splitlines() if line.strip()]
    if isinstance(raw, dict):
        for value in raw.values():
            if isinstance(value, list):
                raw = value
                break
    if not isinstance(raw, list):
        raise ValueError("Pyrus data is not a list")

    rows = []
    for task in raw:
        fields = {field["name"]: field.get("value", "") for field in task.get("fields", [])}
        rows.append({
            "id": fields.get("matrix_id", "").strip(),
            "title": fields.get("title", "").strip(),
            "body": fields.get("body", "").strip(),
            "level": str(fields.get("level", "")).strip(),
            "parent_id": fields.get("parent_id", "").strip()
        })
    return pd.DataFrame(rows)

# === MAPPING ==================================================================
@router.post("/pyrus_mapping")
async def pyrus_mapping(url: str = Body(...)):
    response = requests.post("https://aimatrix-e8zs.onrender.com/pyrus_mapping", json=url)
    response_data = response.json()

    from utils.data_loader import sync_with_pyrus
    response_data["pyrus_response"] = sync_with_pyrus(response_data)

    return response_data
