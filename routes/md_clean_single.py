from fastapi import APIRouter, Query
from fastapi.responses import PlainTextResponse
from utils.data_loader import build_df_from_api

router = APIRouter()

@router.get("/md/clean_single")
def export_md_single_node(
    node_id: str = Query(..., description="Specific node ID to export")
):
    df = build_df_from_api()
    
    # Фильтруем DataFrame, оставляя только запись с указанным ID
    filtered_df = df[df['id'] == node_id]
    
    if filtered_df.empty:
        return PlainTextResponse(
            f"Node with ID {node_id} not found", 
            status_code=404,
            media_type="text/plain"
        )
    
    content = "\n\n".join(
        f"# {row['title']}\n\n**id:** {row['id']}\n\n**parent_id:** {row['parent_id']}\n\n{row['body']}\n\n---"
        for _, row in filtered_df.iterrows()
    )
    return PlainTextResponse(content, media_type="text/markdown")