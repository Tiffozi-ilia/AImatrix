# ====== utils/diff_engine.py ======
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
            # Для корневых элементов используем "x", для остальных - parent_id
            prefix = parent_id if parent_id else "x"
            node_id = get_next_id(prefix)
            is_generated = True
        else:
            # Если ID уже использован, генерируем новый
            if node_id in used_ids:
                prefix = parent_id if parent_id else "x"
                node_id = get_next_id(prefix)
                is_generated = True
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

    # Безопасная обработка входных данных
    if content_json and isinstance(content_json, list):
        root_topic = content_json[0].get("rootTopic", {})
        if root_topic:
            walk(root_topic)
            
    return generated_nodes

def find_new_nodes(flat_xmind, existing_ids):
    return [n for n in flat_xmind if n["generated"]]

# format_as_markdown остается без изменений

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
