from fastapi import FastAPI
from fastapi.responses import StreamingResponse
import requests
import pandas as pd
import io
import zipfile

app = FastAPI()

@app.get("/generate-matrix")
def generate_matrix():
    # 🔐 ВСТАВЬ СЮДА АКТУАЛЬНЫЙ PYRUS TOKEN
    PYRUS_TOKEN = "ВСТАВЬ_СВОЙ_ТОКЕН_СЮДА"

    url = "https://api.pyrus.com/v4/forms/2309262/register"
    headers = {"Authorization": f"Bearer {PYRUS_TOKEN}"}
    resp = requests.get(url, headers=headers)
    data = resp.json()

    def extract(fields, key):
        for field in fields:
            if field.get("name") == key:
                return field.get("value", "")
        return ""

    rows = []
    for task in data.get("tasks", []):
        fields = task.get("fields", [])
        rows.append({
            "id": extract(fields, "matrix_id"),
            "title": extract(fields, "title"),
            "body": extract(fields, "body")
        })

    df = pd.DataFrame(rows)

    zip_buf = io.BytesIO()
    with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zipf:
        for _, row in df.iterrows():
            md_content = f"# {row['title']}\n\n**id:** {row['id']}\n\n{row['body']}\n"
            zipf.writestr(f"Matrix_md/{row['id']}.md", md_content)

        full_md = "\n\n".join(
            f"# {row['title']}\n\n**id:** {row['id']}\n\n{row['body']}\n\n---"
            for _, row in df.iterrows()
        )
        zipf.writestr("Matrix_full.md", full_md)

    zip_buf.seek(0)
    return StreamingResponse(zip_buf, media_type="application/zip", headers={
        "Content-Disposition": "attachment; filename=Matrix.zip"
    })
