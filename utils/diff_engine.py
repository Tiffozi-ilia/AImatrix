# ====== utils/diff_engine.py ======
from utils.data_loader import get_data

def flatten_xmind_nodes(content_json: list, existing_ids: set = None):
    if existing_ids is None:
        # Получаем список уже занятых id из Pyrus
        raw = get_data()
        try:
            raw = json.loads(raw) if isinstance(raw, str) else raw
            if isinstance(raw, dict):
                for value in raw.values():
                    if isinstance(value, list):
                        raw = value
                        break
            if not isinstance(raw, list):
                raise ValueError("Pyrus data is not a list")
        except Exception as e:
            raise RuntimeError(f"Ошибка при загрузке данных Pyrus: {e}")

        existing_ids = set()
        for task in raw:
            fields = {field["name"]: field.get("value", "") for field in task.get("fields", [])}
            matrix_id = fields.get("matrix_id", "").strip()
            if matrix_id:
                existing_ids.add(matrix_id)

    used_ids = set(existing_ids)
    generated_nodes = []

    def get_next_id(prefix):
        index = 1
        while True:
            candidate = f"{prefix}.{str(index).zfill(2)}"
            if candidate not in used_ids:
                used_ids.add(candidate)
                return candidate
            index += 1

    def walk(node, parent_id="", level=1):
        label = node.get("labels", [])
        node_id = label[0] if label else None
        title = node.get("title", "")
        body = node.get("notes", {}).get("plain", {}).get("content", "")

        is_generated = False
        if not node_id or node_id in used_ids:
            node_id = get_next_id(parent_id or "x")
            is_generated = True

        used_ids.add(node_id)

        current = {
            "id": node_id.strip(),
            "title": title.strip(),
            "body": body.strip(),
            "level": str(level),
            "parent_id": parent_id.strip(),
            "generated": is_generated
        }

        generated_nodes.append(current)

        for child in node.get("children", {}).get("attached", []):
            walk(child, node_id, level + 1)

    root_topic = content_json[0].get("rootTopic", {})
    walk(root_topic)
    return generated_nodes



def format_as_markdown(items: list[dict]) -> str:
    # Оригинальная реализация без изменений
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
