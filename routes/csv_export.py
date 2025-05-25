from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from utils.data_loader import build_df_from_api
import io

router = APIRouter()

@router.get("/csv")
def export_csv():
    df = build_df_from_api()
    csv_buf = io.StringIO()
    df.to_csv(csv_buf, index=False, sep=';')
    return StreamingResponse(io.BytesIO(csv_buf.getvalue().encode()), media_type="text/csv", headers={
        "Content-Disposition": "attachment; filename=Matrix.csv"
    })
