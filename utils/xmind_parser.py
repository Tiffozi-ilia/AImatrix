def flatten_xmind_nodes(data):
    def walk(node, parent_id="", level=1, index=1):
        label = node.get("labels", [])
        node_id = label[0].strip() if label and label[0].strip() else None

        title = node.get("title", "")
        body = node.get("notes", {}).get("plain", {}).get("content", "")

        is_generated = False
        if not node_id:
            suffix = f"{index:02d}"
            node_id = f"{parent_id}.{suffix}" if parent_id else f"a.a.{suffix}"
            is_generated = True

        flat = [{
            "id": node_id,
            "parent_id": parent_id,
            "level": level,
            "title": title.strip(),
            "body": body.strip(),
            "generated": is_generated
        }]

        for i, child in enumerate(node.get("children", {}).get("attached", []), 1):
            flat.extend(walk(child, parent_id=node_id, level=level + 1, index=i))

        return flat

    # Начинаем обход с rootTopic.children.attached
    root_topic = data[0].get("rootTopic", {})
    attached = root_topic.get("children", {}).get("attached", [])

    all_nodes = []
    for i, child in enumerate(attached, 1):
        all_nodes.extend(walk(child, parent_id="", level=1, index=i))

    return all_nodes
