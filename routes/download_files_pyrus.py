# routes/download_files_pyrus.py
# -*- coding: utf-8 -*-
from typing import Dict, List, Any, Tuple
from urllib.parse import quote
import io, zipfile, requests, logging
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse, JSONResponse
from utils.data_loader import get_pyrus_token

router = APIRouter()
logger = logging.getLogger(__name__)

BASE = "https://pyrus.sovcombank.ru/api/v4"
READ_TIMEOUT = 300
LIST_TIMEOUT = 60
CHUNK = 8192

# ----------------- helpers -----------------

def _auth() -> Dict[str, str]:
    return {"Authorization": f"Bearer {get_pyrus_token()}"}

def _unwrap(a: Dict[str, Any] | None) -> Dict[str, Any]:
    """Некоторые аттачи приходят как {'file': {...}}."""
    if not a:
        return {}
    return a["file"] if isinstance(a.get("file"), dict) else a

def _pick_name(att: Dict[str, Any]) -> str | None:
    """Имя файла с поддержкой camelCase и вложенного 'file'."""
    candidates = []
    for src in (att, _unwrap(att)):
        if not isinstance(src, dict):
            continue
        candidates.extend([
            src.get("file_name"), src.get("fileName"),
            src.get("name"), src.get("filename"),
            src.get("display_name"), src.get("displayName"),
            src.get("original_name"), src.get("originalName"),
        ])
    for v in candidates:
        if v:
            return str(v)
    return None

def _pick_download_id(att: Dict[str, Any]) -> Tuple[str | None, str | None]:
    """
    Идентификатор, который реально подходит для /files/download/{id}.
    Порядок приоритета:
      1) file_guid | fileGuid | guid
      2) id | file_id | fileId
      3) хвост из download_url / downloadUrl / url
    Возвращает (value, source_key) для диагностики.
    """
    for src in (att, _unwrap(att)):
        if not isinstance(src, dict):
            continue
        for k in ("file_guid", "fileGuid", "guid"):
            v = src.get(k)
            if v:
                return str(v), k
        for k in ("id", "file_id", "fileId"):
            v = src.get(k)
            if v:
                return str(v), k
        for k in ("download_url", "downloadUrl", "url"):
            v = src.get(k)
            if isinstance(v, str) and "/files/download/" in v:
                tail = v.rstrip("/").rsplit("/", 1)[-1]
                if tail:
                    return tail, k
    return None, None

def _ts(obj: Dict[str, Any]) -> str:
    """Грубая метка времени для выбора 'последней' версии."""
    o = _unwrap(obj)
    return o.get("created") or o.get("created_at") or o.get("createdAt") or o.get("date") or ""

def _safe(s: str) -> str:
    return "".join(ch for ch in s if ch.isalnum() or ch in ("-", "_", ".", " ")).strip().replace(" ", "_")

def _content_disposition(filename: str) -> Dict[str, str]:
    quoted_utf8 = quote(filename)
    return {"Content-Disposition": f'attachment; filename="{filename}"; filename*=UTF-8\'\'{quoted_utf8}'}

# ----------------- endpoint -----------------

@router.get("/download_files_pyrus")
def file_by_name(
    task_id: int = Query(..., description="ID задачи Pyrus"),
    filename: str = Query(..., description="Искомое имя файла"),
    match_mode: str = Query("exact", description="exact|contains"),
    debug: bool = Query(False, description="диагностика: показать имена/идентификаторы"),
):
    """
    Ищет вложения в задаче Pyrus по имени (регистронезависимо).
      - 0 совпадений → 404 + список доступных имён;
      - 1 совпадение → отдаём файл (для *.json проставляем content-type);
      - >1:
          * exact и все имена идентичны → берём последнюю версию по времени;
          * иначе → ZIP всех совпавших.

    Источники: task.files, task.attachments, comments.attachments, comments.files.
    """
    mode = (match_mode or "exact").lower()
    if mode not in ("exact", "contains"):
        raise HTTPException(400, "match_mode must be 'exact' or 'contains'")

    q = (filename or "").strip()
    if not q:
        raise HTTPException(400, "filename is empty")

    # 1) тащим задачу с комментариями и файлами
    r = requests.get(f"{BASE}/tasks/{task_id}?include=comments,files",
                     headers=_auth(), timeout=LIST_TIMEOUT)
    if r.status_code >= 400:
        raise HTTPException(502, f"Pyrus list error: {r.text}")
    data = r.json() or {}
    task = data.get("task", data)

    # 2) собираем аттачи отовсюду
    items: List[Dict[str, Any]] = []

    def _collect(seq, origin: str):
        for att in (seq or []):
            name = _pick_name(att)
            down_id, id_key = _pick_download_id(att)
            if name and down_id:
                items.append({
                    "name": name,
                    "download_id": down_id,   # то, что подставляем в /files/download/{...}
                    "id_key": id_key,         # из какого поля взяли
                    "ts": _ts(att),
                    "src": origin,            # откуда взяли (для отладки)
                })

    _collect(task.get("files"), "task.files")
    _collect(task.get("attachments"), "task.attachments")
    for c in (task.get("comments") or []):
        _collect(c.get("attachments"), "comment.attachments")
        _collect(c.get("files"), "comment.files")

    # 3) дедуп по download_id (отсекаем дубли из top-level и комментариев)
    seen, files = set(), []
    for f in items:
        did = f["download_id"]
        if did in seen:
            continue
        seen.add(did)
        files.append(f)

    names_all = [f["name"] for f in files]

    if debug:
        return {
            "task_id": task_id,
            "requested_filename": filename,
            "match_mode": mode,
            "count_after_dedup": len(files),
            "items": files,  # тут видно name, download_id, id_key, ts, src
            "task_keys": list(task.keys()),
            "comments_count": len(task.get("comments") or []),
            "top_files_count": len(task.get("files") or []),
            "top_attachments_count": len(task.get("attachments") or []),
        }

    # 4) поиск по имени
    qlow = q.lower()
    matches = [f for f in files if f["name"].lower() == qlow] if mode == "exact" \
        else [f for f in files if qlow in f["name"].lower()]

    logger.info(f"[pyrus] task={task_id} query={filename} matches={len(matches)}")

    if not matches:
        return JSONResponse(
            status_code=404,
            content={"detail": "file_not_found", "requested": filename, "available_files": names_all},
        )

    # 5) одиночный файл → отдать сам файл, JSON → правильный content-type
    if len(matches) == 1:
        m = matches[0]
        rr = requests.get(f"{BASE}/files/download/{quote(m['download_id'])}",
                          headers=_auth(), stream=True, timeout=READ_TIMEOUT)
        if rr.status_code >= 400:
            raise HTTPException(502, f"Pyrus download error: {rr.text}")
        ctype = "application/json; charset=utf-8" if m["name"].lower().endswith(".json") \
                else rr.headers.get("Content-Type", "application/octet-stream")
        headers = _content_disposition(m["name"])
        headers["X-Pyrus-Source"]   = m.get("src") or ""
        headers["X-Pyrus-Id-Key"]   = m.get("id_key") or ""
        return StreamingResponse(rr.iter_content(CHUNK), media_type=ctype, headers=headers)

    # 6) несколько совпадений: если exact и имена одинаковые — берём «последнюю»
    if mode == "exact" and len({m["name"].lower() for m in matches}) == 1:
        last = sorted(matches, key=lambda x: x["ts"] or "")[-1]
        rr = requests.get(f"{BASE}/files/download/{quote(last['download_id'])}",
                          headers=_auth(), stream=True, timeout=READ_TIMEOUT)
        if rr.status_code >= 400:
            raise HTTPException(502, f"Pyrus download error: {rr.text}")
        ctype = "application/json; charset=utf-8" if last["name"].lower().endswith(".json") \
                else rr.headers.get("Content-Type", "application/octet-stream")
        headers = _content_disposition(last["name"])
        headers["X-Pyrus-Match-Count"] = str(len(matches))
        headers["X-Pyrus-Selected"]    = "latest"
        headers["X-Pyrus-Source"]      = last.get("src") or ""
        headers["X-Pyrus-Id-Key"]      = last.get("id_key") or ""
        return StreamingResponse(rr.iter_content(CHUNK), media_type=ctype, headers=headers)

    # 7) иначе — ZIP всех совпавших (устойчиво к частичным ошибкам)
    buf = io.BytesIO()
    failed = []
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        used = set()
        for m in matches:
            rr = requests.get(f"{BASE}/files/download/{quote(m['download_id'])}",
                              headers=_auth(), timeout=READ_TIMEOUT)
            if rr.status_code >= 400:
                failed.append({"name": m["name"], "download_id": m["download_id"], "code": rr.status_code})
                continue
            arc = m["name"]
            if arc in used:
                base, dot, ext = arc.partition(".")
                idx = 1
                n = f"{base} ({idx}){dot}{ext}" if dot else f"{base} ({idx})"
                while n in used:
                    idx += 1
                    n = f"{base} ({idx}){dot}{ext}" if dot else f"{base} ({idx})"
                arc = n
            used.add(arc)
            zf.writestr(arc, rr.content)

    if not used and failed:
        return JSONResponse(status_code=502, content={"detail": "download_failed", "failed": failed})

    buf.seek(0)
    zip_name = f"pyrus_{task_id}_{_safe(q)}_bundle.zip"
    headers = _content_disposition(zip_name)
    headers["X-Pyrus-Match-Count"] = str(len(matches))
    if failed:
        headers["X-Pyrus-Failed-Count"] = str(len(failed))
    return StreamingResponse(buf, media_type="application/zip", headers=headers)
