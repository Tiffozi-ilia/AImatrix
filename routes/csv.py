from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from utils.data_loader import build_df_from_api
import io

router = APIRouter()

@router.get("/csv")
def get_csv():
    df = build_df_from_api()
    df = df[["id", "title", "body", "level", "parent_id", "parent_name", "child_id"]]
    csv_stream = io.StringIO()
    df.to_csv(csv_stream, index=False)
    return StreamingResponse(io.BytesIO(csv_stream.getvalue().encode("utf-8")), media_type="text/csv", headers={
        "Content-Disposition": "attachment; filename=matrix.csv"
    })