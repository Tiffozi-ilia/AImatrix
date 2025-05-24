from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from utils.data_loader import fetch_data, extract_rows
import pandas as pd
import io

router = APIRouter()

@router.get("/excel")
def get_excel():
    rows = extract_rows(fetch_data())
    df = pd.DataFrame(rows)
    stream = io.BytesIO()
    with pd.ExcelWriter(stream, engine="openpyxl") as writer:
        df.to_excel(writer, index=False)
    stream.seek(0)
    return StreamingResponse(stream, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", headers={
        "Content-Disposition": "attachment; filename=matrix.xlsx"
    })