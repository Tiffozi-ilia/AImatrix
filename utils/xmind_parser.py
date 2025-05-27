def flatten_xmind_nodes(data):
    def int_to_alpha(n):
        result = ""
        while n > 0:
            n -= 1
            result = chr(97 + (n % 26)) + result
            n //= 26
        return result

    def walk(node, parent_id="", level=1):
        label = node.get("labels", [])
        node_id = label[0].strip() if label and label[0].strip() else None

        title = node.get("title", "")
        body = node.get("notes", {}).get("plain", {}).get("content", "")

        is_generated = False

        if not node_id:
            siblings = node.get("siblings", [])
            existing_suffixes = set()
            for sibling in siblings:
                s_label = sibling.get("labels", [])
                s_id = s_label[0].strip() if s_label and s_label[0].strip() else None
                if s_id and s_id.startswith(parent_id):
                    tail = s_id[len(parent_id) + 1:]
                    existing_suffixes.add(tail)

            last_component = parent_id.split(".")[-1] if parent_id else ""
            use_alpha = last_component.isalpha()

            i = 1
            while True:
                suffix = int_to_alpha(i) if use_alpha else f"{i:02d}"
                if suffix not in existing_suffixes:
                    break
                i += 1

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

        children = node.get("children", {}).get("attached", [])
        for child in children:
            child["siblings"] = children
        for child in children:
            flat.extend(walk(child, parent_id=node_id, level=level + 1))

        return flat

    root_topic = data[0].get("rootTopic", {})
    attached = root_topic.get("children", {}).get("attached", [])

    for child in attached:
        child["siblings"] = attached

    all_nodes = []
    for child in attached:
        all_nodes.extend(walk(child, parent_id="a.a", level=3))

    return all_nodes
