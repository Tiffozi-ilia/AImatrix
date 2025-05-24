from fastapi import FastAPI
from fastapi.responses import StreamingResponse
import requests
import pandas as pd
import io
import zipfile
import os
import uvicorn

app = FastAPI()

@app.get("/generate-matrix")
def generate_matrix():
    # 🔐 ВСТАВЬ СЮДА АКТУАЛЬНЫЙ PYRUS TOKEN
    PYRUS_TOKEN = "eyJhbGciOiJSUzI1NiIsInR5cCI6ImF0K2p3dCJ9.eyJuYmYiOjE3NDgxMDc5MjMsImV4cCI6MTc0ODE5NDMyMywiaXNzIjoiaHR0cDovL3B5cnVzLWlkZW50aXR5LXNlcnZlci5weXJ1cy1wcm9kLnN2Yy5jbHVzdGVyLmxvY2FsIiwiYXVkIjoicHVibGljYXBpIiwiY2xpZW50X2lkIjoiMTFGRjI4OTctRDNFMS00QjAwLUJCRjYtNDFCMzhDM0EwMDcyIiwic3ViIjoiMTE0MDQ2NiIsImF1dGhfdGltZSI6MTc0ODEwNzkyMywiaWRwIjoibG9jYWwiLCJzZWNyZXQiOiI5MmY0Yzc5NjQ4MmJkMWRlNjU5ZTNhM2I5NGRlYTliYmM3M2I3ZTljZjg2MGMzZWU4MjUwNjdmMmRiOTI3ZDE1IiwidGltZXN0YW1wIjoiMTc0ODE5NDMyMyIsInNjb3BlIjpbInB1YmxpY2FwaSJdLCJhbXIiOlsicHdkIl19.JdJxy-dhtoY4jZsK49EBQql34Y6mv0CmY8v871O30FOQKT1M7CEPA-FBbRn9adyJzZCrC2xjgJWGhSFyBFIuZJpYxER-nyCzJYwqKdj8AN9PyolIk9y-dG9K-t4fGOovy7wFiwsnDPbkzYEy9ZVb_I-Yz51fzVSS6jHEM_u5hM9lwp9wMJ1feDo62Mn_t-xQK9_c-ww9fCoc8f3MhW99vcrhvYVhsd3mEaIMPklqhZJ2EKDKfkqmKUUoPYgNHXKoW1LW_Uo-0IpLBfHf6W89cvGjbhHtae_QcggNe1dCr-RllmLLoPo4ou_QmYbFCdHRh3O8dNh5cmGagdAv9xfZ5g"

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
