def flatten_xmind_nodes(data):
    def walk(node, parent_id="", level=1, index=1):
    label = node.get("labels", [])
    node_id = label[0] if label else None

    title = node.get("title", "")
    body = node.get("notes", {}).get("plain", {}).get("content", "")

    if not node_id:
        node_id = f"{parent_id}.{index:02d}" if parent_id else f"{index:02d}"

    flat = [{
        "id": node_id,
        "parent_id": parent_id,
        "level": level,
        "title": title,
        "body": body.strip()
    }]

    for i, child in enumerate(node.get("children", {}).get("attached", []), 1):
        flat.extend(walk(child, node_id, level + 1, i))

    return flat

    # 🔥 Фильтруем только те, у кого есть children.attached (реальное дерево)
    top_nodes = [item for item in data if item.get("children", {}).get("attached")]

    all_nodes = []
    for root in top_nodes:
        all_nodes.extend(walk(root))

    return all_nodes
