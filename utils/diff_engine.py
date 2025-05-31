# ====== utils/diff_engine.py ======
import json
from utils.data_loader import get_data

def find_new_nodes(flat_xmind, existing_ids):
    new_nodes = []
    for node in flat_xmind:
        node_id = node.get("id")
        if not node_id:
            continue
        if node_id not in existing_ids:
            new_nodes.append(node)
    return new_nodes

def format_as_markdown(items: list[dict]) -> str:
    if not items:
        return "⚠️ Нет данных"

    headers = set()
    for item in items:
        headers.update(item.keys())
    headers = list(headers)

    table = ["| " + " | ".join(headers) + " |",
             "| " + " | ".join(["---"] * len(headers)) + " |"]

    for item in items:
        row = [str(item.get(h, "")).replace("\n", "<br>") for h in headers]
        table.append("| " + " | ".join(row) + " |")

    return "\n".join(table)
