from fastapi import FastAPI, UploadFile, File
import zipfile, io, json
import pandas as pd

app = FastAPI()


def extract_xmind_nodes(xmind_file: UploadFile):
    content = xmind_file.file.read()
    with zipfile.ZipFile(io.BytesIO(content)) as z:
        content_json = json.loads(z.read("content.json"))

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

    root_topic = content_json[0].get("rootTopic", {})
    return pd.DataFrame(walk(root_topic))


def get_pyrus_mock_data():
    # Пример имитации Pyrus JSON
    return [
        {
            "fields": [
                {"name": "matrix_id", "value": "a.a"},
                {"name": "title", "value": "Заголовок A"},
                {"name": "body", "value": "Описание A"},
                {"name": "level", "value": "1"},
                {"name": "parent_id", "value": "+"}
            ]
        },
        {
            "fields": [
                {"name": "matrix_id", "value": "a.b"},
                {"name": "title", "value": "Заголовок B"},
                {"name": "body", "value": "Описание B"},
                {"name": "level", "value": "1"},
                {"name": "parent_id", "value": "+"}
            ]
        }
    ]


def extract_pyrus_data():
    raw = get_pyrus_mock_data()
    rows = []
    for task in raw:
        fields = {field["name"]: field.get("value", "") for field in task.get("fields", [])}
        rows.append({
            "id": fields.get("matrix_id", "").strip(),
            "title": fields.get("title", "").strip(),
            "body": fields.get("body", "").strip(),
            "level": str(fields.get("level", "")).strip(),
            "parent_id": fields.get("parent_id", "").strip()
        })
    return pd.DataFrame(rows)


@app.post("/xmind-delete")
async def detect_deleted_items(xmind: UploadFile = File(...)):
    xmind_df = extract_xmind_nodes(xmind)
    pyrus_df = extract_pyrus_data()
    deleted = pyrus_df[~pyrus_df["id"].isin(xmind_df["id"])]
    return {
        "deleted": deleted[["id", "parent_id", "level", "title", "body"]].to_dict(orient="records")
    }
