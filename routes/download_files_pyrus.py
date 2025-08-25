# routes/download_files_pyrus.py
# -*- coding: utf-8 -*-
from typing import Dict, List, Any
from urllib.parse import quote
import io, zipfile, requests
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse, JSONResponse
from utils.data_loader import get_pyrus_token
import logging
import json

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
        file_names = [
            file_obj.get("file_name"),
            file_obj.get("fileName"),
            file_obj.get("name"),
            file_obj.get("filename"),
            file_obj.get("display_name"),
            file_obj.get("displayName"),
            file_obj.get("original_name"),
            file_obj.get("originalName"),
        ]
        possible_names.extend(file_names)
    for name in possible_names:
        if name:
            return str(name)
    return None

def _pick_guid(attachment: Dict[str, Any]) -> str | None:
    """Извлекает GUID файла из объекта вложения, учитывая различные форматы Pyrus API"""
    possible_guids = [
        attachment.get("file_guid"),
        attachment.get("fileGuid"),
        attachment.get("guid"),
        attachment.get("id"),
        attachment.get("file_id"),
        attachment.get("fileId"),
    ]
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
    debug: bool = Query(False, description="диагностика: показать имена"),
):
    """
    Ищет вложения в задаче Pyrus по имени с учетом различных форматов данных Pyrus API
    """
    match_mode = match_mode.lower()
    if match_mode not in ("exact", "contains"):
        raise HTTPException(400, "match_mode must be 'exact' or 'contains'")

    q = (filename or "").strip()
    if not q:
        raise HTTPException(400, "filename is empty")

    # 1) Просим сервер вернуть комментарии и файлы
    try:
        r = requests.get(
            f"{BASE}/tasks/{task_id}?include=comments,files",
            headers=_auth(), timeout=LIST_TIMEOUT
        )
        if r.status_code >= 400:
            raise HTTPException(502, f"Pyrus list error: {r.text}")
        data = r.json() or {}
        task = data.get("task", data)  # иногда обёртка {"task": {...}}
    except Exception as e:
        logger.error(f"Error fetching task: {e}")
        raise HTTPException(500, f"Error fetching task: {e}")

    files: List[Dict[str, str]] = []

    # 2) Сбор top-level: files + attachments
    for att in (task.get("files") or []) + (task.get("attachments") or []):
        name = _pick_name(att)
        guid = _pick_guid(att)
        if name and guid:
            ts = (att.get("created") or att.get("created_at") or att.get("createdAt")
                  or att.get("date") or "")
            files.append({"name": name, "guid": guid, "ts": ts})
            logger.debug(f"Added top-level file: {name}, guid: {guid}")

    # 3) Сбор из комментариев
    for c in (task.get("comments") or []):
        ts = (c.get("created") or c.get("created_at") or c.get("createdAt")
              or c.get("date") or "")
        for att in (c.get("attachments") or []) + (c.get("files") or []):
            name = _pick_name(att)
            guid = _pick_guid(att)
            if name and guid:
                files.append({"name": name, "guid": guid, "ts": ts})
                logger.debug(f"Added comment file: {name}, guid: {guid}")

    # 3.5) ДЕДУП по GUID (оставляем запись с более свежим ts)
    files_before = len(files)
    by_guid: Dict[str, Dict[str, str]] = {}
    for f in files:
        g = f["guid"]
        if g not in by_guid or (f.get("ts") or "") > (by_guid[g].get("ts") or ""):
            by_guid[g] = f
    files = list(by_guid.values())
    logger.debug(f"Dedup by guid: {files_before} -> {len(files)}")

    # для 404-ответа — список имён уже после дедупа
    names_all = [f["name"] for f in files]

    # Режим отладки
    if debug:
        return {
            "task_id": task_id,
            "requested_filename": filename,
            "match_mode": match_mode,
            "all_files_count": len(files),
            "all_files": [{"name": f["name"], "guid": f["guid"], "ts": f.get("ts", "")} for f in files],
            "task_structure_keys": list(task.keys()),
            "comments_count": len(task.get("comments", [])),
            "files_count": len(task.get("files", [])),
            "attachments_count": len(task.get("attachments", [])),
        }

    # 4) Фильтрация по режиму сопоставления
    q_low = q.lower()
    if match_mode == "exact":
        matches = [f for f in files if f["name"].lower() == q_low]
    else:
        matches = [f for f in files if q_low in f["name"].lower()]

    # Доп. дедуп уже в совпадениях (на случай, если где-то выше пропустили)
    m_before = len(matches)
    uniq_matches: Dict[str, Dict[str, str]] = {}
    for m in matches:
        g = m["guid"]
        if g not in uniq_matches or (m.get("ts") or "") > (uniq_matches[g].get("ts") or ""):
            uniq_matches[g] = m
    matches = list(uniq_matches.values())

    logger.info(f"Found matches (unique): {[m['name'] for m in matches]} (was {m_before})")

    # 5) Возврат результата
    if not matches:
        return JSONResponse(
            status_code=404,
            content={"detail": "file_not_found", "requested": filename, "available_files": names_all},
        )

    # Один совпавший файл — возвращаем его напрямую
    if len(matches) == 1:
        m = matches[0]
        rr = requests.get(f"{BASE}/files/download/{quote(m['guid'])}",
                          headers=_auth(), stream=True, timeout=READ_TIMEOUT)
        if rr.status_code >= 400:
            raise HTTPException(502, f"Pyrus download error: {rr.text}")
        ctype = rr.headers.get("Content-Type", "application/octet-stream")
        return StreamingResponse(rr.iter_content(CHUNK), media_type=ctype,
                                 headers=_content_disposition(m["name"]))

    # Несколько совпадений
    if match_mode == "exact" and len({m["name"].lower() for m in matches}) == 1:
        # Если имена одинаковые — взять самый свежий
        last = sorted(matches, key=lambda x: x.get("ts") or "")[-1]
        rr = requests.get(f"{BASE}/files/download/{quote(last['guid'])}",
                          headers=_auth(), stream=True, timeout=READ_TIMEOUT)
        if rr.status_code >= 400:
            raise HTTPException(502, f"Pyrus download error: {rr.text}")
        ctype = rr.headers.get("Content-Type", "application/octet-stream")
        headers = _content_disposition(last["name"])
        headers["X-Pyrus-Match-Count"] = str(len(matches))
        headers["X-Pyrus-Selected"] = "latest"
        return StreamingResponse(rr.iter_content(CHUNK), media_type=ctype, headers=headers)

    # ZIP-архив для нескольких файлов (разные имена/версии)
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
