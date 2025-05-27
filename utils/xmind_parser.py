def flatten_xmind_nodes(data):
    def walk(node, parent_id="", level=1):
        label = node.get("labels", [""])[0]
        body = node.get("notes", {}).get("plain", {}).get("content", "")
        node_id = label or node.get("id")

        result = [{
            "id": node_id,
            "parent_id": parent_id,
            "level": level,
            "title": node.get("title", ""),
            "body": body.strip()
        }]

        for child in node.get("children", {}).get("attached", []):
            result.extend(walk(child, node_id, level + 1))

        return result

    results = []
    for root in data:
        results.extend(walk(root))
    return results
