def find_new_nodes(flat_xmind, existing_ids):
    new_nodes = []
    for node in flat_xmind:
        node_id = node.get("id")

        # Пропускаем мусор (все должны иметь id после генерации)
        if not node_id:
            continue

        # Сравниваем с тем, что пришло из Pyrus
        if node_id not in existing_ids:
            new_nodes.append(node)

    return new_nodes


def format_as_markdown(nodes):
    if not nodes:
        return "Новых элементов не найдено."

    header = "| id | parent_id | level | title | body |\n|---|---|---|---|---|"
    rows = [
        f"| {n['id']} | {n['parent_id']} | {n['level']} | {n['title']} | {n['body']} |"
        for n in nodes
    ]
    return "\n".join([header] + rows)
