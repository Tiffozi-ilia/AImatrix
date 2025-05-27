def flatten_xmind_nodes(data):
    def walk(node, parent_id="", level=1):
        node_id = node.get("labels", [""])[0] or node.get("id")  # правильный ID
        title = node.get("title", "")
        body = node.get("notes", {}).get("plain", {}).get("content", "")

        flat = [{
            "id": node_id,
            "parent_id": parent_id,
            "level": level,
            "title": title,
            "body": body.strip()
        }]

        for child in node.get("children", {}).get("attached", []):
            flat.extend(walk(child, node_id, level + 1))

        return flat

    # ⚠️ data — это список корневых узлов, обрабатываем всех
    all_nodes = []
    for root in data:
        all_nodes.extend(walk(root))
    return all_nodes
