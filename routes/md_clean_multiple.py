from fastapi import APIRouter, Query
from fastapi.responses import PlainTextResponse
from typing import List
from utils.data_loader import build_df_from_api

router = APIRouter()

@router.get("/md/clean_multiple")
def export_md_multiple_nodes(
    node_ids: List[str] = Query(..., description="List of node IDs to export")
):
    df = build_df_from_api()
    filtered_df = df[df['id'].isin(node_ids)]

    if filtered_df.empty:
        return PlainTextResponse(
            "No matching nodes found", 
            status_code=404,
            media_type="text/plain"
        )

    content = "\n\n".join(
        f"# {row['title']}\n\n**id:** {row['id']}\n\n**parent_id:** {row['parent_id']}\n\n{row['body']}\n\n---"
        for _, row in filtered_df.iterrows()
    )
    return PlainTextResponse(content, media_type="text/markdown")
