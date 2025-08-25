# routes/download_files_pyrus.py
# -*- coding: utf-8 -*-
from typing import Dict, List, Any
from urllib.parse import quote
import io, zipfile, requests, logging, re
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse, JSONResponse
from utils.data_loader import get_pyrus_token

router = APIRouter()
logger = logging.getLogger(__name__)

BASE = "https://pyrus.sovcombank.ru/api/v4"
READ_TIMEOUT = 300
LIST_TIMEOUT = 60
CHUNK = 8192

GUID_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")

def _auth() -> Dict[str, str]:
    return {"Authorization": f"Bearer {get_pyrus_token()}"}

def _pick_name(attachment: Dict[str, Any]) -> str | None:
    """Извлекает имя файла из объекта вложения, учитывая разные форматы Pyrus API."""
    possible_names = [
        attachment.get("file_name"),
        attachment.get("fileName"),
        attachment.get("name"),
        attachment.get("filename"),
        attachment.get("display_name"),
        attachment.get("displayName"),
        attachment.get("original_name"),
        attachment.get("originalName"),
    ]
    file_obj = attachment.get("file")
    if isinstance(file_obj, dict):
        possible_names.extend([
            file_obj.get("file_name"),
            file_obj.get("fileName"),
            file_obj.get("name"),
            file_obj.get("filename"),
            file_obj.get("display_name"),
            file_obj.get("displayName"),
            file_obj.get("original_name"),
            file_obj.get("originalName"),
        ])
    for name in possible_names:
        if name:
            return str(name)
    return None

def _pick_guid(attachment: Dict[str, Any]) -> str | None:
    """
    Возвращает ТОЛЬКО реальный file GUID (а не id вложения/коммента).
    Сначала пытаемся поля guid/file_guid/fileGuid;
    если нет — пробуем выдёрнуть из download_url.
    """
    def _from(d: Dict[str, Any] | None) -> str | None:
        if not isinstance(d, dict):
            return None
        for k in ("file_guid", "fileGuid", "guid"):
            v = d.get(k)
            if isinstance(v, str) and GUID_RE.match(v):
                return v
        for k in ("download_url", "downloadUrl", "url"):
            v = d.get(k)
            if isinstance(v, str) and "/files/download/" in v:
                cand = v.rsplit("/", 1)[-1]
                if GUID_RE.match(cand):
                    return cand
        return None

    return _from(attachment) or _from(attachment.get("file"))

def _safe(s: str) -> str:
    return "".join(ch for ch in s if ch.isalnum() or ch in ("-", "_", ".", " ")).strip().replace(" ", "_")

def _content_disposition(filename: str) -> Dict[str, str]:
    quoted_utf8 = quote(filename)
    return {"Content-Disposition": f'attachment; filename="{filename}"; filename*=UTF-8\'\'{quoted_utf8}'}

@router.get("/download_files_pyrus")
def file_by_name(
    task_id: int = Query(..., description="ID задачи Pyrus"),
    filename: str = Query(..., description="Искомое имя файла"),
    match_mode: str = Query("exact", description="exact|contains"),
    debug: bool = Query(False, description="диагностика: показать имена"),
):
    """
    Ищет вложения в задаче Pyrus по имени:
    - 0 совпадений → 404 + список доступных имён;
    - 1 совпадение → отдаём файл (stream), для *.json ставим application/json;
    - >1 совпадений:
        * exact и все имена идентичны → отдаём последнюю версию;
        * иначе → ZIP со всеми совпавшими.
    Поиск регистронезависимый. Источники: task.files, task.attachments, comments.attachments, comments.files.
    """
    match_mode = (match_mode or "exact").lower()
    if match_mode not in ("exact", "contains"):
        raise HTTPException(400, "match_mode must be 'exact' or 'contains'")

    q = (filename or "").strip()
    if not q:
        raise HTTPException(400, "filename is empty")

    # 1) Получаем задачу с комментариями и файлами
    r = requests.get(f"{BASE}/tasks/{task_id}?include=comments,files",
                     headers=_auth(), timeout=LIST_TIMEOUT)
    if r.status_code >= 400:
        raise HTTPException(502, f"Pyrus list error: {r.text}")
    data = r.json() or {}
    task = data.get("task", data)

    files: List[Dict[str, str]] = []

    # 2) Вложения верхнего уровня (правый блок «ФАЙЛЫ»): files + attachments
    for att in (task.get("files") or []) + (task.get("attachments") or []):
        name = _pick_name(att)
        guid = _pick_guid(att)
        if name and guid:
            ts = att.get("created") or att.get("created_at") or att.get("createdAt") or att.get("date") or ""
            files.append({"name": str(name), "guid": str(guid), "ts": ts})

    # 3) Вложения в комментариях: attachments + files
    for c in (task.get("comments") or []):
        ts = c.get("created") or c.get("created_at") or c.get("createdAt") or c.get("date") or ""
        for att in (c.get("attachments") or []) + (c.get("files") or []):
            name = _pick_name(att)
            guid = _pick_guid(att)
            if name and guid:
                files.append({"name": str(name), "guid": str(guid), "ts": ts})

    # 4) Дедуп по GUID (ключевой фикс против дублей)
    seen, dedup = set(), []
    for f in files:
        g = f.get("guid")
        if not g or g in seen:
            continue
        seen.add(g)
        dedup.append(f)
    files = dedup

    names_all = [f["name"] for f in files]

    if debug:
        return {
            "task_id": task_id,
            "requested_filename": filename,
            "match_mode": match_mode,
            "all_files_count": len(files),
            "all_files": files,
            "task_structure_keys": list(task.keys()),
            "comments_count": len(task.get("comments") or []),
            "files_count": len(task.get("files") or []),
            "attachments_count": len(task.get("attachments") or []),
        }

    # 5) Поиск по имени
    q_low = q.lower()
    if match_mode == "exact":
        matches = [f for f in files if f["name"].lower() == q_low]
    else:
        matches = [f for f in files if q_low in f["name"].lower()]

    logger.info(f"Found matches: {[m['name'] for m in matches]}")

    # 6) Возврат
    if not matches:
        return JSONResponse(
            status_code=404,
            content={"detail": "file_not_found", "requested": filename, "available_files": names_all},
        )

    if len(matches) == 1:
        m = matches[0]
        rr = requests.get(f"{BASE}/files/download/{quote(m['guid'])}",
                          headers=_auth(), stream=True, timeout=READ_TIMEOUT)
        if rr.status_code >= 400:
            raise HTTPException(502, f"Pyrus download error: {rr.text}")
        # Для JSON заставляем корректный content-type
        ctype = "application/json; charset=utf-8" if m["name"].lower().endswith(".json") \
                else rr.headers.get("Content-Type", "application/octet-stream")
        return StreamingResponse(rr.iter_content(CHUNK), media_type=ctype,
                                 headers=_content_disposition(m["name"]))

    # >1 совпадений
    if match_mode == "exact" and len({m["name"].lower() for m in matches}) == 1:
        last = sorted(matches, key=lambda x: x["ts"] or "")[-1]
        rr = requests.get(f"{BASE}/files/download/{quote(last['guid'])}",
                          headers=_auth(), stream=True, timeout=READ_TIMEOUT)
        if rr.status_code >= 400:
            raise HTTPException(502, f"Pyrus download error: {rr.text}")
        ctype = "application/json; charset=utf-8" if last["name"].lower().endswith(".json") \
                else rr.headers.get("Content-Type", "application/octet-stream")
        headers = _content_disposition(last["name"])
        headers["X-Pyrus-Match-Count"] = str(len(matches))
        headers["X-Pyrus-Selected"] = "latest"
        return StreamingResponse(rr.iter_content(CHUNK), media_type=ctype, headers=headers)

    # Иначе: ZIP всех совпавших
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        used = set()
        for m in matches:
            rr = requests.get(f"{BASE}/files/download/{quote(m['guid'])}",
                              headers=_auth(), timeout=READ_TIMEOUT)
            if rr.status_code >= 400:
                raise HTTPException(502, f"Pyrus download error: {rr.text}")
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

    buf.seek(0)
    zip_name = f"pyrus_{task_id}_{_safe(q)}_bundle.zip"
    headers = _content_disposition(zip_name)
    headers["X-Pyrus-Match-Count"] = str(len(matches))
    return StreamingResponse(buf, media_type="application/zip", headers=headers)
