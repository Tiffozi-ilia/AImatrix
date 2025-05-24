from fastapi import APIRouter
from fastapi.responses import PlainTextResponse
from utils.data_loader import build_df_from_api

router = APIRouter()

@router.get("/md-full")
def export_md_full():
    df = build_df_from_api()
    df = df.sort_values(by="id")

    content = ""
    for _, row in df.iterrows():
        content += (
            f"<!-- METADATA\n"
            f"id: {row.get('id', '')}\n"
            f"title: {row.get('title', '')}\n"
            f"level: {row.get('level', '')}\n"
            f"parent_id: {row.get('parent_id', '')}\n"
            f"parent_name: {row.get('parent_name', '')}\n"
            f"child_id: {row.get('child_id', '')}\n"
            f"--->\n\n"
            f"# {row.get('title', '')}\n\n"
            f"**id:** {row.get('id', '')}\n\n"
            f"{row.get('body', '')}\n\n"
            f"---\n\n"
        )

    return PlainTextResponse(content, media_type="text/markdown")
