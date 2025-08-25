# routes/download_files_pyrus.py
# -*- coding: utf-8 -*-
from typing import Dict, List, Any
from urllib.parse import quote
import io, zipfile, requests
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse, JSONResponse
from utils.data_loader import get_pyrus_token
import logging

router = APIRouter()
logger = logging.getLogger(__name__)

BASE = "https://pyrus.sovcombank.ru/api/v4"
READ_TIMEOUT = 300
LIST_TIMEOUT = 60
CHUNK = 8192

def _auth() -> Dict[str, str]:
    return {"Authorization": f"Bearer {get_pyrus_token()}"}

def _pick_name(attachment: Dict[str, Any]) -> str | None:
    """Извлекает имя файла из объекта вложения, учитывая различные форматы Pyrus API"""
    # Попробуем все возможные варианты имен полей
    possible_names = [
        attachment.get("file_name"),
        attachment.get("fileName"),
        attachment.get("name"),
        attachment.get("filename"),
        attachment.get("display_name"),
    ]
    
    # Если есть вложенный объект file, проверим и его
    file_obj = attachment.get("file")
    if isinstance(file_obj, dict):
        file_names = [
            file_obj.get("file_name"),
            file_obj.get("fileName"),
            file_obj.get("name"),
            file_obj.get("filename"),
            file_obj.get("display_name"),
        ]
        possible_names.extend(file_names)
    
    # Вернем первое непустое значение
    for name in possible_names:
        if name:
            return str(name)
    return None

def _pick_guid(attachment: Dict[str, Any]) -> str | None:
    """Извлекает GUID файла из объекта вложения, учитывая различные форматы Pyrus API"""
    # Попробуем все возможные варианты GUID
    possible_guids = [
        attachment.get("file_guid"),
        attachment.get("fileGuid"),
        attachment.get("guid"),
        attachment.get("id"),
        attachment.get("file_id"),
        attachment.get("fileId"),
    ]
    
    # Если есть вложенный объект file, проверим и его
    file_obj = attachment.get("file")
    if isinstance(file_obj, dict):
        file_guids = [
            file_obj.get("file_guid"),
            file_obj.get("fileGuid"),
            file_obj.get("guid"),
            file_obj.get("id"),
            file_obj.get("file_id"),
            file_obj.get("fileId"),
        ]
        possible_guids.extend(file_guids)
    
    # Вернем первое непустое значение
    for guid in possible_guids:
        if guid:
            return str(guid)
    return None

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
):
    """
    Ищет вложения в задаче Pyrus по имени с учетом различных форматов данных Pyrus API
    """
    if match_mode not in ("exact", "contains"):
        raise HTTPException(400, "match_mode must be 'exact' or 'contains'")

    q = (filename or "").strip()
    if not q:
        raise HTTPException(400, "filename is empty")

    # 1) Получаем задачу с комментариями
    r = requests.get(f"{BASE}/tasks/{task_id}", headers=_auth(), timeout=LIST_TIMEOUT)
    if r.status_code >= 400:
        raise HTTPException(502, f"Pyrus list error: {r.text}")
    
    task = r.json() or {}
    logger.debug(f"Task structure: {list(task.keys())}")
    
    files: List[Dict[str, str]] = []

    # 1a) Вложения верхнего уровня (блок "ФАЙЛЫ")
    for attachment in (task.get("files") or []):
        name = _pick_name(attachment)
        guid = _pick_guid(attachment)
        if name and guid:
            ts = attachment.get("created") or attachment.get("created_at") or attachment.get("date") or ""
            files.append({"name": name, "guid": guid, "ts": ts})
            logger.debug(f"Found top-level file: {name}, guid: {guid}")

    # 1b) Вложения в комментариях
    for comment in (task.get("comments") or []):
        ts = comment.get("created") or comment.get("created_at") or comment.get("date") or ""
        
        # Проверяем все возможные места, где могут быть вложения
        for attachment in (comment.get("attachments") or []):
            name = _pick_name(attachment)
            guid = _pick_guid(attachment)
            if name and guid:
                files.append({"name": name, "guid": guid, "ts": ts})
                logger.debug(f"Found comment attachment: {name}, guid: {guid}")
        
        # Некоторые версии API могут использовать поле "files" в комментариях
        for attachment in (comment.get("files") or []):
            name = _pick_name(attachment)
            guid = _pick_guid(attachment)
            if name and guid:
                files.append({"name": name, "guid": guid, "ts": ts})
                logger.debug(f"Found comment file: {name}, guid: {guid}")

    names_all = [f["name"] for f in files]
    q_low = q.lower()
    logger.debug(f"All available files: {names_all}")

    # 2) Поиск (case-insensitive)
    if match_mode == "exact":
        matches = [f for f in files if f["name"].lower() == q_low]
    else:
        matches = [f for f in files if q_low in f["name"].lower()]
    
    logger.debug(f"Found matches: {[m['name'] for m in matches]}")

    # 3) Возврат результата
    if not matches:
        return JSONResponse(
            status_code=404,
            content={"detail": "file_not_found", "requested": filename, "available_files": names_all},
        )

    # Остальная часть кода без изменений...
    if len(matches) == 1:
        m = matches[0]
        rr = requests.get(f"{BASE}/files/download/{quote(m['guid'])}", headers=_auth(), stream=True, timeout=READ_TIMEOUT)
        if rr.status_code >= 400:
            raise HTTPException(502, f"Pyrus download error: {rr.text}")
        ctype = rr.headers.get("Content-Type", "application/octet-stream")
        return StreamingResponse(rr.iter_content(CHUNK), media_type=ctype, headers=_content_disposition(m["name"]))

    # >1 совпадений
    if match_mode == "exact" and len({m["name"].lower() for m in matches}) == 1:
        last = sorted(matches, key=lambda x: x["ts"] or "")[-1]
        rr = requests.get(f"{BASE}/files/download/{quote(last['guid'])}", headers=_auth(), stream=True, timeout=READ_TIMEOUT)
        if rr.status_code >= 400:
            raise HTTPException(502, f"Pyrus download error: {rr.text}")
        ctype = rr.headers.get("Content-Type", "application/octet-stream")
        headers = _content_disposition(last["name"])
        headers["X-Pyrus-Match-Count"] = str(len(matches))
        headers["X-Pyrus-Selected"] = "latest"
        return StreamingResponse(rr.iter_content(CHUNK), media_type=ctype, headers=headers)

    # ZIP-архив для нескольких файлов
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        used = set()
        for m in matches:
            rr = requests.get(f"{BASE}/files/download/{quote(m['guid'])}", headers=_auth(), timeout=READ_TIMEOUT)
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
