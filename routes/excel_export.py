from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from utils.data_loader import build_df_from_api
import pandas as pd
import io

router = APIRouter()

@router.get("/excel")
def get_excel():
    df = build_df_from_api()
    df = df[["id", "title", "body", "level", "parent_id", "parent_name", "child_id"]]
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False)
    output.seek(0)
    return StreamingResponse(output, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", headers={
        "Content-Disposition": "attachment; filename=matrix.xlsx"
    })
