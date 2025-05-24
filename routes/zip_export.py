from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from utils.data_loader import build_df_from_api
import io
import zipfile

router = APIRouter()

@router.get("/zip")
def export_zip():
    df = build_df_from_api()
    zip_buf = io.BytesIO()
    with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zipf:
        for _, row in df.iterrows():
            md_content = f"# {row['title']}\n\n**id:** {row['id']}\n\n{row['body']}\n"
            zipf.writestr(f"Matrix_md/{row['id']}.md", md_content)
    zip_buf.seek(0)
    return StreamingResponse(zip_buf, media_type="application/zip", headers={
        "Content-Disposition": "attachment; filename=Matrix.zip"
    })