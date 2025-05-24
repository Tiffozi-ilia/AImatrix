from fastapi import APIRouter
from fastapi.responses import PlainTextResponse
from utils.data_loader import build_df_from_api

router = APIRouter()

@router.get("/md/clean")
def export_md_clean():
    df = build_df_from_api()
    content = "\n\n".join(
        f"# {row['title']}\n\n**id:** {row['id']}\n\n{row['body']}\n\n---"
        for _, row in df.iterrows()
    )
    return PlainTextResponse(content, media_type="text/markdown")