from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from utils.data_loader import build_df_from_api
import pandas as pd
import io

router = APIRouter()

@router.get("/excel")
def export_excel():
    df = build_df_from_api()
    xlsx_buf = io.BytesIO()
    with pd.ExcelWriter(xlsx_buf, engine="openpyxl") as writer:
        df.to_excel(writer, index=False)
    xlsx_buf.seek(0)
    return StreamingResponse(xlsx_buf, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", headers={
        "Content-Disposition": "attachment; filename=Matrix.xlsx"
    })