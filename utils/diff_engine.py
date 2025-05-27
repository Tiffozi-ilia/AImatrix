def find_new_nodes(flat_xmind, existing_ids):
    return [node for node in flat_xmind if node["id"] not in existing_ids]

def format_as_markdown(nodes):
    if not nodes:
        return "Новых элементов не найдено."

    header = "| id | parent_id | level | title | body |\n|---|---|---|---|---|"
    rows = [f"| {n['id']} | {n['parent_id']} | {n['level']} | {n['title']} | {n['body']} |" for n in nodes]
    return "\n".join([header] + rows)
