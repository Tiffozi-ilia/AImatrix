from fastapi import APIRouter
from fastapi.responses import JSONResponse
from utils.data_loader import get_data

router = APIRouter()

@router.get("/json")
def export_json():
    data = get_data()
    return JSONResponse(content=data)