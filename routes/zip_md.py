from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from utils.data_loader import fetch_data, extract_rows
import io
import zipfile

router = APIRouter()

@router.get("/zip-md")
def get_zip_md():
    rows = extract_rows(fetch_data())
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for row in rows:
            content = f"# {row['title']}\n\n**id:** {row['id']}\n\n{row['body']}"
            z.writestr(f"Matrix_md/{row['id']}.md", content)
    buf.seek(0)
    return StreamingResponse(buf, media_type="application/zip", headers={
        "Content-Disposition": "attachment; filename=Matrix_md.zip"
    })