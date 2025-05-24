from fastapi import APIRouter
from fastapi.responses import PlainTextResponse
from utils.data_loader import fetch_data, extract_rows

router = APIRouter()

@router.get("/md-full")
def get_md_full():
    rows = extract_rows(fetch_data())
    full_md = "\n\n".join(
        f"# {row['title']}\n\n**id:** {row['id']}\n\n{row['body']}\n\n---"
        for row in rows
    )
    return PlainTextResponse(full_md)