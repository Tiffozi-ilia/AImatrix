from fastapi import APIRouter
from fastapi.responses import PlainTextResponse
from utils.data_loader import fetch_data, extract_rows

router = APIRouter()

@router.get("/opml")
def get_opml():
    rows = extract_rows(fetch_data())
    body = "\n".join(f'<outline text="{row["title"]}" />' for row in rows)
    opml = f'<?xml version="1.0"?><opml version="2.0"><body>{body}</body></opml>'
    return PlainTextResponse(opml, media_type="text/xml")