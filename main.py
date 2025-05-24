from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
import requests
import pandas as pd
import io
import zipfile
import os

app = FastAPI()

@app.get("/generate-matrix")
def generate_matrix():
    PYRUS_TOKEN = os.environ.get("PYRUS_TOKEN")
    if not PYRUS_TOKEN:
        raise HTTPException(status_code=500, detail="PYRUS_TOKEN не задан")

    url = "https://api.pyrus.com/v4/forms/2309262/register"
    headers = {"Authorization": f"Bearer {PYRUS_TOKEN}"}
    resp = requests.get(url, headers=headers)

    try:
        data = resp.json()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка чтения JSON: {str(e)}")

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
        # Matrix_md/*.md
        for _, row in df.iterrows():
            md_content = f"# {row['title']}\n\n**id:** {row['id']}\n\n{row['body']}\n"
            zipf.writestr(f"Matrix_md/{row['id']}.md", md_content)

        # Matrix_clean_id.md
        clean_md = "\n\n".join(
            f"# {row['title']}\n\n**id:** {row['id']}\n\n{row['body']}\n\n---"
            for _, row in df.iterrows()
        )
        zipf.writestr("Matrix_clean_id.md", clean_md)

        # Matrix_full.md (с мета-блоками)
        full_md = "\n\n".join(
            f"# {row['title']}\n\n<!-- METADATA -->\nmeta:\n  id: {row['id']}\n  title: {row['title']}\n  linked: []\n\n{row['body']}\n\n---"
            for _, row in df.iterrows()
        )
        zipf.writestr("Matrix_full.md", full_md)

    zip_buf.seek(0)
    return StreamingResponse(zip_buf, media_type="application/zip", headers={
        "Content-Disposition": "attachment; filename=Matrix.zip"
    })
