from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse
from utils.data_loader import build_df_from_api
from typing import Set, List, Dict, Any
import json, math, re

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

def _is_na(v) -> bool:
    try:
        import pandas as pd
        return pd.isna(v)
    except Exception:
        return v is None or (isinstance(v, float) and math.isnan(v))

def _try_parse_json(text: str):
    """Пытаемся превратить строку в JSON-объект/массив.
    1) сначала прямой json.loads
    2) если не вышло — вырезаем первый сбалансированный блок {...} или [...]
    Возвращаем (obj, True) если получилось, иначе (исходный_text, False).
    """
    if not isinstance(text, str) or not text.strip():
        return text, False

    # прямая попытка
    try:
        return json.loads(text), True
    except Exception:
        pass

    # вырезать кодовые блоки 
json ... 
    fenced = re.search(r"
(?:json)?\s*(.*?)\s*", text, re.S | re.I)
    if fenced:
        inner = fenced.group(1)
        try:
            return json.loads(inner), True
        except Exception:
            text = inner  # продолжим поиском скобок

    # поиск первого сбалансированного JSON-блока
    start_match = re.search(r'[\{\[]', text)
    if not start_match:
        return text, False

    start = start_match.start()
    stack = []
    for i in range(start, len(text)):
        ch = text[i]
        if ch in "{[":
            stack.append(ch)
        elif ch in "}]":
            if not stack:
                break
            top = stack[-1]
            if (top == "{" and ch == "}") or (top == "[" and ch == "]"):
                stack.pop()
                if not stack:
                    candidate = text[start:i+1]
                    try:
                        return json.loads(candidate), True
                    except Exception:
                        break
    return text, False

@router.get("/json/clean_depth")
def export_json_clean(
    root_id: str = Query(..., description="Root ID to filter by"),
    depth: int = Query(-1, description="How many levels down to go (-1 = full depth)")
):
    df = build_df_from_api()
    valid_ids = {root_id}
    valid_ids.update(collect_children_ids(df, root_id, set(), 0, depth))

    filtered_df = df[df['id'].isin(valid_ids)].sort_values(by=['parent_id', 'id'])

    if filtered_df.empty:
        return JSONResponse({"detail": "No matching nodes found"}, status_code=404)

    nodes: List[Dict[str, Any]] = []
    for _, row in filtered_df.iterrows():
        node_id = "" if _is_na(row.get("id")) else str(row.get("id"))
        parent_id = "" if _is_na(row.get("parent_id")) else str(row.get("parent_id"))
        title = None if _is_na(row.get("title")) else str(row.get("title"))
        raw_body = "" if _is_na(row.get("body")) else str(row.get("body"))

        body_parsed, ok = _try_parse_json(raw_body)
        # если ok == True — body_parsed это dict/list; иначе — исходная строка
        nodes.append({
            "id": node_id,
            "parent_id": parent_id,
            "title": title,
            "body": body_parsed
        })

    payload = {
        "root_id": root_id,
        "depth": depth,
        "count": len(nodes),
        "nodes": nodes
    }
    return JSONResponse(payload)
