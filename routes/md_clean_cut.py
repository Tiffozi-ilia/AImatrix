from fastapi import APIRouter, Query
from fastapi.responses import PlainTextResponse
from utils.data_loader import build_df_from_api
from typing import List, Set

router = APIRouter()

def collect_children_ids(df, parent_id: str, collected_ids: Set[str]) -> Set[str]:
    """Рекурсивно собирает все дочерние ID для заданного родительского ID"""
    children = df[df['parent_id'] == parent_id]
    for _, row in children.iterrows():
        child_id = row['id']
        if child_id not in collected_ids:
            collected_ids.add(child_id)
            collect_children_ids(df, child_id, collected_ids)
    return collected_ids

@router.get("/md/clean_cut")
def export_md_clean(root_id: str = Query(..., description="Root ID to filter by")):
    df = build_df_from_api()
    
    # Собираем все нужные ID (родительский + все дочерние)
    valid_ids = {root_id}
    valid_ids.update(collect_children_ids(df, root_id, valid_ids))
    
    # Фильтруем DataFrame, оставляя только нужные записи
    filtered_df = df[df['id'].isin(valid_ids) | (df['id'] == root_id)]
    
    # Сортируем, чтобы родительские элементы шли перед дочерними (опционально)
    filtered_df = filtered_df.sort_values(by=['parent_id', 'id'])
    
    content = "\n\n".join(
        f"# {row['title']}\n\n**id:** {row['id']}\n\n**parent_id:** {row['parent_id']}\n\n{row['body']}\n\n---"
        for _, row in filtered_df.iterrows()
    )
    return PlainTextResponse(content, media_type="text/markdown")