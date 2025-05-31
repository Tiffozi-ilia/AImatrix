# ====== utils/diff_engine.py ======
def flatten_xmind_nodes(content_json: list):
    # Оригинальная реализация без изменений
    nodes = []
    
    def walk(node, parent_id="", level=1):
        label = node.get("labels", [])
        node_id = label[0] if label else None
        title = node.get("title", "")
        body = node.get("notes", {}).get("plain", {}).get("content", "")
        
        nodes.append({
            "id": node_id.strip() if node_id else "",
            "parent_id": parent_id.strip(),
            "title": title.strip(),
            "body": body.strip(),
            "level": level,
            "generated": True  # Всегда True как в оригинале
        })
        
        for child in node.get("children", {}).get("attached", []):
            walk(child, node_id, level + 1)
    
    if content_json and isinstance(content_json, list):
        root_topic = content_json[0].get("rootTopic", {})
        if root_topic:
            walk(root_topic)
            
    return nodes

def find_new_nodes(flat_xmind, existing_ids):
    # Модифицированная логика генерации ID
    used_ids = set(existing_ids)
    new_nodes = []
    id_counter = {}
    
    for node in flat_xmind:
        node_id = node.get("id")
        parent_id = node.get("parent_id")
        
        # Если ID отсутствует или конфликтует
        if not node_id or node_id in used_ids:
            # Генерация нового ID вида родитель.номер
            base = parent_id if parent_id else "x"
            if base not in id_counter:
                id_counter[base] = 1
            
            while True:
                new_id = f"{base}.{str(id_counter[base]).zfill(2)}"
                if new_id not in used_ids:
                    break
                id_counter[base] += 1
            
            # Обновляем данные узла
            node["id"] = new_id
            node["generated"] = True
            id_counter[base] += 1
        
        # Добавляем в new_nodes если это новый узел
        if node["generated"] and node["id"] not in existing_ids:
            new_nodes.append(node)
            used_ids.add(node["id"])
    
    return new_nodes

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
