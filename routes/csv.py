from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from utils.data_loader import fetch_data, extract_rows
import pandas as pd
import io

router = APIRouter()

@router.get("/csv")
def get_csv():
    rows = extract_rows(fetch_data())
    df = pd.DataFrame(rows)
    stream = io.StringIO()
    df.to_csv(stream, index=False)
    stream.seek(0)
    return StreamingResponse(iter([stream.read()]), media_type="text/csv", headers={
        "Content-Disposition": "attachment; filename=matrix.csv"
    })