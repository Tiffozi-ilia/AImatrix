from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse
from utils.data_loader_cib import get_data
import json
import io
import math
from typing import Any, Dict, List, Optional, Tuple

router = APIRouter()

NEEDED = {"matrix_id", "title", "level", "body", "parent_id", "parent_name"}

# ---------- helpers ----------

def fields_to_map(task: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for f in task.get("fields", []):
        name = f.get("name")
        if not name or name not in NEEDED:
            continue
        out[name] = f.get("value")
    return out

def id_sort_key(id_str: Optional[str]) -> Tuple:
    if id_str is None:
        return (math.inf,)
    if id_str == "+":
        return (-1,)
    parts = id_str.split(".")
    key: List[int] = []
    for p in parts:
        if p.isdigit():
            key.append(int(p))
        else:
            key.append(10**9)
    return tuple(key)

def make_item(id_: Optional[str], title: Optional[str]) -> str:
    return f"id:{id_ or ''} - {title or ''}"

def make_markdown(id_: str, title: str, body: str) -> str:
    lines = []
    if title:
        lines.append(f"## {title}")
    if id_:
        lines.append(f"**id:** {id_}")
    if body:
        lines.append(f"### {body.strip()}")
    return "\n".join(lines)

def build_nodes(raw_tasks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Строит ПЛОСКИЙ список узлов в формате:
    {
      "item": "id:<id> - <title>",
      "data": {...},
      "data_markdown": "...",
      "children": []   # добавим сразу, чтобы удобно было собирать дерево
    }
    """
    nodes: List[Dict[str, Any]] = []
    for task in raw_tasks:
        fd = fields_to_map(task)
        _id = fd.get("matrix_id")
        if not _id:
            continue

        node = {
            "item": make_item(_id, fd.get("title")),
            "data": {
                "id": _id,
                "title": fd.get("title"),
                "level": fd.get("level"),
                "body": fd.get("body"),
                "parent_id": fd.get("parent_id") or "",
                "parent_name": fd.get("parent_name") or "",
            },
            "data_markdown": make_markdown(
                _id, fd.get("title") or "", fd.get("body") or ""
            ),
            "children": []  # ключ обязателен по ТЗ
        }
        nodes.append(node)

    # сортируем по id (стабильно)
    nodes.sort(key=lambda n: (id_sort_key(n["data"].get("id")), n["data"].get("id") or ""))
    return nodes

def build_index(flat_nodes: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    return {n["data"]["id"]: n for n in flat_nodes if "id" in n["data"] and n["data"]["id"]}

def build_forest(flat_nodes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Собирает иерархию: каждому узлу добавляет children.
    Возвращает список корневых узлов (forest).
    """
    index = build_index(flat_nodes)

    # обнулим children на всякий случай, если этот метод будут дергать повторно
    for n in flat_nodes:
        n["children"] = []

    roots: List[Dict[str, Any]] = []

    for node in flat_nodes:
        parent_id = node["data"].get("parent_id") or ""
        if parent_id and parent_id in index:
            index[parent_id]["children"].append(node)
        else:
            # нет родителя — это корень
            roots.append(node)

    # рекурсивно отсортируем детей по id
    def sort_rec(n: Dict[str, Any]):
        n["children"].sort(key=lambda c: (id_sort_key(c["data"].get("id")), c["data"].get("id") or ""))
        for ch in n["children"]:
            sort_rec(ch)

    for r in roots:
        sort_rec(r)

    return roots

def clone_node_without_children(node: Dict[str, Any]) -> Dict[str, Any]:
    """Создает 'легкую' копию узла (без ссылочного переноса children)."""
    return {
        "item": node.get("item"),
        "data": dict(node.get("data", {})),
        "data_markdown": node.get("data_markdown", ""),
        "children": []
    }

def prune_by_depth(node: Dict[str, Any], depth: int) -> Dict[str, Any]:
    """
    Возвращает НОВУЮ копию узла, обрезанную по глубине.
    depth=-1: всё вниз, 0: только этот узел, N: N уровней вниз.
    """
    new_node = clone_node_without_children(node)
    if depth == 0:
        return new_node

    next_d = -1 if depth == -1 else depth - 1
    for ch in node.get("children", []):
        new_node["children"].append(prune_by_depth(ch, next_d))
    return new_node

def pick_roots(forest: List[Dict[str, Any]], root_id: Optional[str]) -> List[Dict[str, Any]]:
    """
    Если задан root_id — вернем список из одного найденного корня (или пусто).
    Если не задан — вернем весь лес.
    """
    if not root_id:
        return forest
    # поиск узла по id в уже собранном лесу
    stack = forest[:]
    while stack:
        n = stack.pop()
        if n["data"].get("id") == root_id:
            return [n]
        stack.extend(n.get("children", []))
    return []  # не нашли

# ---------- routes ----------

@router.get("/json_n8n")
def export_json_n8n(
    root_id: Optional[str] = Query(None),
    depth: int = Query(-1, description="-1=всё вниз, 0=только root, N=уровни вниз")
):
    """
    Плоский экспорт (legacy):
    GET /json_n8n?root_id=<ID>&depth=-1|0|1|2|...
    Возвращает МАССИВ объектов без children:
      - item: "id:<id> - <title>"
      - data: словарь атрибутов
      - data_markdown: Markdown
    """
    raw = get_data()
    tasks = raw.get("tasks", [])
    flat_nodes = build_nodes(tasks)

    # Ограничение по глубине для ПЛОСКОГО вида:
    # просто берем нужные узлы обходом от root (или всех корней)
    def get_depth_nodes(
        flat_nodes_: List[Dict[str, Any]],
        root_id_: Optional[str],
        depth_: int
    ) -> List[Dict[str, Any]]:
        index = build_index(flat_nodes_)
        result: List[Dict[str, Any]] = []

        def dfs(node: Dict[str, Any], d: int):
            result.append(node)
            if d == 0:
                return
            next_d = -1 if d == -1 else d - 1
            for child in flat_nodes_:
                if child["data"]["parent_id"] == node["data"]["id"]:
                    dfs(child, next_d)

        if root_id_:
            root = index.get(root_id_)
            if not root:
                return []
            dfs(root, depth_)
        else:
            # все корни
            for n in flat_nodes_:
                if not n["data"]["parent_id"]:
                    dfs(n, depth_)

        # убираем ключ children (для совместимости со старым контрактом)
        out = []
        for n in result:
            nn = dict(n)
            if "children" in nn:
                del nn["children"]
            out.append(nn)
        return out

    result = get_depth_nodes(flat_nodes, root_id, depth)

    buf = io.BytesIO(json.dumps(result, indent=2, ensure_ascii=False).encode("utf-8"))
    return StreamingResponse(
        buf,
        media_type="application/json",
        headers={"Content-Disposition": 'attachment; filename="matrix_n8n.json"'}
    )

@router.get("/json_n8n_tree_cib")
def export_json_n8n_tree_cib(
    root_id: Optional[str] = Query(None, description="id корневого узла для экспорта одной поддеревом"),
    depth: int = Query(-1, description="-1=всё вниз, 0=только root, N=уровни вниз")
):
    """
    Иерархический экспорт:
    GET /json_n8n_tree_cib?root_id=<ID>&depth=-1|0|1|2|...

    Возвращает СТРУКТУРУ С ДЕРЕВОМ:
      - каждый объект имеет поля:
          item, data, data_markdown, children: []
      - при depth=0 узел(ы) возвращаются без детей (children=[])
      - при depth>0 дочерние уровни включаются согласно глубине
      - если root_id не указан — экспортируется лес из всех корневых узлов
    """
    raw = get_data()
    tasks = raw.get("tasks", [])
    flat_nodes = build_nodes(tasks)

    # строим полный лес
    forest = build_forest(flat_nodes)

    # выбираем корень/корни
    roots = pick_roots(forest, root_id)

    # обрезаем по глубине, возвращаем новые объекты (исключаем ссылочные циклы)
    pruned = [prune_by_depth(r, depth) for r in roots]

    buf = io.BytesIO(json.dumps(pruned, indent=2, ensure_ascii=False).encode("utf-8"))
    return StreamingResponse(
        buf,
        media_type="application/json",
        headers={"Content-Disposition": 'attachment; filename="matrix_n8n_tree.json"'}
    )
