
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
import pandas as pd
import io
import zipfile

app = FastAPI()

@app.get("/generate-matrix")
def generate_matrix():
    try:
        # Эмуляция ответа Pyrus (вместо requests.get)
        rows = [
            {"id": "a.a.01", "title": "Компетенция 1", "body": "Описание 1"},
            {"id": "a.a.02", "title": "Компетенция 2", "body": "Описание 2"}
        ]

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

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
