from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse
from utils.data_loader import build_df_from_api

router = APIRouter()

@router.get("/md/clean_multiple")
def export_md_multiple_nodes(
    node_ids: str = Query(..., description="Comma-separated node IDs, e.g. 02.02,03.03.03")
):
    # Разбиваем строку на список
    ids = [id.strip() for id in node_ids.split(",") if id.strip()]
    
    df = build_df_from_api()
    filtered_df = df[df['id'].isin(ids)]

    if filtered_df.empty:
        return JSONResponse(
            content={"error": "No matching nodes found"},
            status_code=404
        )

    # Формируем массив объектов
    result = [
        {
            "id": row["id"],
            "markdown": (
                f"# {row['title']}\n\n"
                f"**id:** {row['id']}\n\n"
                f"**parent_id:** {row['parent_id']}\n\n"
                f"{row['body']}\n\n---"
            )
        }
        for _, row in filtered_df.iterrows()
    ]

    return JSONResponse(content=result)
