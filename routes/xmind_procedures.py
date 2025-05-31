# === MAPPING (Stage 1: только CSV из JSON) ====================================
@router.post("/pyrus_mapping")
async def pyrus_mapping(url: str = Body(...)):
    import requests
    import zipfile
    import io
    import json
    import pandas as pd

    # 1. Скачиваем и парсим XMind
    try:
        content = requests.get(url).content
        with zipfile.ZipFile(io.BytesIO(content)) as z:
            content_json = json.loads(z.read("content.json"))
    except Exception as e:
        return {"error": f"Не удалось загрузить XMind: {e}"}

    def walk(node, parent_id="", level=0):
        label = node.get("labels", [])
        node_id = label[0] if label else None
        title = node.get("title", "")
        body = node.get("notes", {}).get("plain", {}).get("content", "")
        rows = []
        if node_id:
            rows.append({
                "id": node_id.strip(),
                "title": title.strip(),
                "body": body.strip(),
                "level": str(level),
                "parent_id": parent_id.strip()
            })
        for child in node.get("children", {}).get("attached", []):
            rows.extend(walk(child, node_id, level + 1))
        return rows

    xmind_df = pd.DataFrame(walk(content_json[0].get("rootTopic", {})))

    # 2. Загружаем данные из Pyrus
    try:
        raw = get_data()
        if isinstance(raw, str):
            raw = json.loads(raw)
        if isinstance(raw, dict):
            raw = raw.get("tasks", [])
    except Exception as e:
        return {"error": f"Не удалось загрузить JSON из Pyrus: {e}"}

    task_map = {}
    for task in raw:
        fields = {field["name"]: field.get("value", "") for field in task.get("fields", [])}
        matrix_id = fields.get("matrix_id", "").strip()
        if matrix_id:
            task_map[matrix_id] = task.get("id")

    headers = {"Content-Type": "application/json"}
    payload = json.dumps({"url": url})

    # 3. Получаем изменения из всех трёх эндпойнтов
    updated_result = requests.post("https://aimatrix-e8zs.onrender.com/xmind-updated", data=payload, headers=headers).json()
    deleted_result = requests.post("https://aimatrix-e8zs.onrender.com/xmind-delete", data=payload, headers=headers).json()
    diff_result    = requests.post("https://aimatrix-e8zs.onrender.com/xmind-diff",    data=payload, headers=headers).json()

    enriched = []

    # === UPDATED ===
    for item in updated_result.get("json", []):
        item["task_id"] = task_map.get(item["id"])
        item["action"] = "update"
        enriched.append(item)

    # === DELETED ===
    for item in deleted_result.get("json", []):
        item["task_id"] = task_map.get(item["id"])
        item["action"] = "delete"
        enriched.append(item)

    # === DIFF (новые) ===
    for item in diff_result.get("json", []):
        enriched.append({
            "id": item.get("id", "").strip(),
            "title": item.get("title", "").strip(),
            "body": item.get("body", "").strip(),
            "level": str(item.get("level", "")).strip(),
            "parent_id": item.get("parent_id", "").strip(),
            "task_id": None,
            "action": "new"
        })

    # 4. Добавим CSV-таблицу всех элементов XMind (с task_id)
    xmind_df["task_id"] = xmind_df["id"].map(task_map)
    csv_records = xmind_df[["id", "parent_id", "level", "title", "body", "task_id"]].to_dict(orient="records")

    return {
        "content": format_as_markdown(enriched),
        "json": enriched,
        "rows": csv_records
    }
