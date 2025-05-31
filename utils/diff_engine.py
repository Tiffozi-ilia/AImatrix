# ====== utils/diff_engine.py ======
def flatten_xmind_nodes(content_json: list, existing_ids: set = None):
    existing_ids = existing_ids or set()
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
        else:
            used_ids.add(node_id)

        current = {
            "id": node_id,
            "parent_id": parent_id,
            "title": title,
            "body": body,
            "level": level,
            "generated": is_generated,
        }
        generated_nodes.append(current)

        for child in node.get("children", {}).get("attached", []):
            walk(child, node_id, level + 1)

    # Проверка на пустые данные
    if not content_json or not isinstance(content_json, list):
        return generated_nodes
        
    root_topic = content_json[0].get("rootTopic", {})
    if root_topic:
        walk(root_topic)
        
    return generated_nodes

# Остальной код без изменений...


def format_as_markdown(items: list[dict]) -> str:
    if not items:
        return "⚠️ Нет данных"

    # Собираем все уникальные ключи по всем строкам
    headers = set()
    for item in items:
        headers.update(item.keys())
    headers = list(headers)

    # Заголовок
    table = ["| " + " | ".join(headers) + " |",
             "| " + " | ".join(["---"] * len(headers)) + " |"]

    for item in items:
        row = [str(item.get(h, "")).replace("\n", "<br>") for h in headers]
        table.append("| " + " | ".join(row) + " |")

    return "\n".join(table)
