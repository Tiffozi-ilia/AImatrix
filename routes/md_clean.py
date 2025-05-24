from fastapi import APIRouter
from fastapi.responses import PlainTextResponse
from utils.data_loader import fetch_data, extract_rows

router = APIRouter()

@router.get("/md-clean")
def get_md_clean():
    rows = extract_rows(fetch_data())
    clean_md = "\n\n".join(
        f"# {row['title']}\n\n{row['body']}\n\n---" for row in rows
    )
    return PlainTextResponse(clean_md)