def flatten_xmind_nodes(data):
    def walk(node, parent_id="", level=1):
        node_id = node.get("labels", [""])[0] or node.get("id")
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

    # 🔥 Фильтруем только те, у кого есть children.attached (реальное дерево)
    top_nodes = [item for item in data if item.get("children", {}).get("attached")]

    all_nodes = []
    for root in top_nodes:
        all_nodes.extend(walk(root))

    return all_nodes
