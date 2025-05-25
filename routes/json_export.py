from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from utils.data_loader import get_data
import json
import io


router = APIRouter()

@router.get("/json")
def export_json():
    raw = get_data()  # ✅ используем как есть
    buffer = io.BytesIO(json.dumps(raw, indent=2, ensure_ascii=False).encode("utf-8"))
    return StreamingResponse(
        buffer,
        media_type="application/json",
        headers={"Content-Disposition": "attachment; filename=matrix_raw.json"}
    )
