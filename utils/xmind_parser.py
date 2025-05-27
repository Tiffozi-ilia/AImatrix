def flatten_xmind_nodes(data):
    def int_to_alpha(n):
        """Преобразует индекс в буквенный суффикс: 1 → a, 2 → b, ..., 27 → aa и т.д."""
        result = ""
        while n > 0:
            n -= 1
            result = chr(97 + (n % 26)) + result
            n //= 26
        return result

    def walk(node, parent_id="", level=1, index=1):
        label = node.get("labels", [])
        node_id = label[0].strip() if label and label[0].strip() else None

        title = node.get("title", "")
        body = node.get("notes", {}).get("plain", {}).get("content", "")

        is_generated = False
        if not node_id:
            # Вычисляем тип суффикса в зависимости от последнего компонента parent_id
            last_component = parent_id.split(".")[-1] if parent_id else ""
            if last_component.isalpha():
                suffix = int_to_alpha(index)  # буквенный
            else:
                suffix = f"{index:02d}"        # цифровой
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

    root_topic = data[0].get("rootTopic", {})
    attached = root_topic.get("children", {}).get("attached", [])

    all_nodes = []
    for i, child in enumerate(attached, 1):
        all_nodes.extend(walk(child, parent_id="a.a", level=3, index=i))

    return all_nodes
