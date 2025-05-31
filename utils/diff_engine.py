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
