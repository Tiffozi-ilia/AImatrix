from fastapi import APIRouter, Query
from fastapi.responses import PlainTextResponse


router = APIRouter()

@router.get("/ping")
def render_ping():
    
    content = "Hello World !"

    return PlainTextResponse(content, media_type="text/markdown")