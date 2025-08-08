from fastapi import APIRouter, Query
from fastapi.responses import PlainTextResponse
from utils.data_loader import build_df_from_api
from typing import Set

router = APIRouter()

def collect_children_ids(df, parent_id: str, collected_ids: Set[str], level: int = 0, max_depth: int = -1) -> Set[str]:
    if max_depth != -1 and level >= max_depth:
        return collected_ids

    children = df[df['parent_id'] == parent_id]
    for _, row in children.iterrows():
        child_id = row['id']
        if child_id not in collected_ids:
            collected_ids.add(child_id)
            collect_children_ids(df, child_id, collected_ids, level + 1, max_depth)
    return collected_ids

@router.get("/md/clean_depth")
def export_md_clean(
    root_id: str = Query(..., description="Root ID to filter by"),
    depth: int = Query(-1, description="How many levels down to go (-1 = full depth)")
):
    df = build_df_from_api()
    valid_ids = {root_id}
    valid_ids.update(collect_children_ids(df, root_id, set(), 0, depth))

    filtered_df = df[df['id'].isin(valid_ids)].sort_values(by=['parent_id', 'id'])

    if filtered_df.empty:
        return PlainTextResponse(
            "No matching nodes found",
            status_code=404,
            media_type="text/plain"
        )

    content = "\n\n===== DOCUMENT BREAK =====\n\n".join(  # уникальный разделитель
        f"# {row['title']}\n\n"
        f"**id:** {row['id']}\n\n"
        f"**parent_id:** {row['parent_id']}\n\n"
        f"{row['body'] or ''}"
        for _, row in filtered_df.iterrows()
    )

    return PlainTextResponse(content, media_type="text/markdown")
