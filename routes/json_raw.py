from fastapi import APIRouter
import requests
from utils.data_loader import fetch_data

router = APIRouter()

@router.get("/json-raw")
def get_json_raw():
    data = fetch_data()
    return data