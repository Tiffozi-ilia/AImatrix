# routes/download_files_pyrus.py
# -*- coding: utf-8 -*-
from typing import Dict, List, Any
from urllib.parse import quote
import io, zipfile, requests, logging
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse, JSONResponse
from utils.data_loader import get_pyrus_token
from datetime import datetime
import unicodedata

router = APIRouter()
logger = logging.getLogger(__name__)

BASE = "https://pyrus.sovcombank.ru/api/v4"
READ_TIMEOUT = 300
LIST_TIMEOUT = 60
CHUNK = 8192

def _auth() -> Dict[str, str]:
    return {"Authorization": f"Bearer {get_pyrus_token()}"}

def _pick_name(a: Dict[str, Any]) -> str | None:
    names = [
        a.get("file_name"), a.get("fileName"), a.get("name"), a.get("filename"),
        a.get("display_name"), a.get("displayName"),
        a.get("original_name"), a.get("originalName"),
    ]
    f = a.get("file")
    if isinstance(f, dict):
        names.extend([
            f.get("file_name"), f.get("fileName"), f.get("name"), f.get("filename"),
            f.get("display_name"), f.get("displayName"),
            f.get("original_name"), f.get("originalName"),
        ])
    for n in names:
        if n:
            return str(n)
    return None

def _pick_guid(a: Dict[str, Any]) -> str | None:
    guids = [a.get("file_guid"), a.get("fileGuid"), a.get("guid"),
             a.get("id"), a.get("file_id"), a.get("fileId")]
    f = a.get("file")
    if isinstance(f, dict):
        guids.extend([f.get("file_guid"), f.get("fileGuid"), f.get("guid"),
                      f.get("id"), f.get("file_id"), f.get("fileId")])
    for g in guids:
        if g:
            return str(g)
    return None

def _safe(s: str) -> str:
    return "".join(ch for ch in s if ch.isalnum() or ch in ("-", "_", ".", " ")).strip().replace(" ", "_")

def _content_disposition(filename: str) -> Dict[str, str]:
    quoted_utf8 = quote(filename)
    return {"Content-Disposition": f'attachment; filename="{filename}"; filename*=UTF-8\'\'{quoted_utf8}'}

def _ts_value(ts: Any) -> float:
    if not ts:
        return 0.0
    s = str(ts)
    for fmt in ("%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%dT%H:%M:%S%z",
                "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d", "%d.%m.%Y %H:%M:%S", "%d.%m.%Y"):
        try:
            dt = datetime.strptime(s, fmt)
            return dt.timestamp()
        except Exception:
            continue
    return 0.0

def _norm_name(name: str) -> str:
    # Склеиваем «визуально одинаковые» варианты имён
    return unicodedata.normalize("NFKC", name).strip().lower()

@router.get("/download_files_pyrus")
def file_by_name(
    task_id: int = Query(..., description="ID задачи Pyrus"),
    filename: str = Query(..., description="Искомое имя файла"),
    match_mode: str = Query("exact", description="exact|contains"),
    versions: str = Query("latest", description="latest|all — для contains: только последняя версия имени или все"),
    debug: bool = Query(False, description="диагностика: показать имена"),
):
    match_mode = match_mode.lower()
    if match_mode not in ("exact", "contains"):
        raise HTTPException(400, "match_mode must be 'exact' or 'contains'")
    versions = versions.lower()
    if versions not in ("latest", "all"):
        raise HTTPException(400, "versions must be 'latest' or 'all'")

    q = (filename or "").strip()
    if not q:
        raise HTTPException(400, "filename is empty")

    # 1) Получаем задачу
    try:
        r = requests.get(
            f"{BASE}/tasks/{task_id}?include=comments,files",
            headers=_auth(), timeout=LIST_TIMEOUT
        )
        if r.status_code >= 400:
            raise HTTPException(502, f"Pyrus list error: {r.text}")
        data = r.json() or {}
        task = data.get("task", data)
    except Exception as e:
        logger.error(f"Error fetching task: {e}")
        raise HTTPException(500, f"Error fetching task: {e}")

    files: List[Dict[str, str]] = []

    # 2) Top-level
    for att in (task.get("files") or []) + (task.get("attachments") or []):
        name, guid = _pick_name(att), _pick_guid(att)
        if name and guid:
            ts = att.get("created") or att.get("created_at") or att.get("createdAt") or att.get("date") or ""
            files.append({"name": name, "guid": guid, "ts": ts})

    # 3) Из комментариев
    for c in (task.get("comments") or []):
        ts = c.get("created") or c.get("created_at") or c.get("createdAt") or c.get("date") or ""
        for att in (c.get("attachments") or []) + (c.get("files") or []):
            name, guid = _pick_name(att), _pick_guid(att)
            if name and guid:
                files.append({"name": name, "guid": guid, "ts": ts})

    # 3.5) Дедуп по GUID → оставляем самый свежий
    by_guid: Dict[str, Dict[str, str]] = {}
    for f in files:
        g = f["guid"]
        if g not in by_guid or _ts_value(f.get("ts")) > _ts_value(by_guid[g].get("ts")):
            by_guid[g] = f
    files = list(by_guid.values())

    names_all = [f["name"] for f in files]

    if debug:
        return {
            "task_id": task_id, "requested_filename": filename, "match_mode": match_mode, "versions": versions,
            "all_files_count": len(files),
            "all_files": [{"name": f["name"], "guid": f["guid"], "ts": f.get("ts", "")} for f in files],
            "task_structure_keys": list(task.keys()),
            "comments_count": len(task.get("comments", [])),
            "files_count": len(task.get("files", [])),
            "attachments_count": len(task.get("attachments", [])),
        }

    # 4) Фильтрация по имени
    q_low = _norm_name(q)
    if match_mode == "exact":
        matches = [f for f in files if _norm_name(f["name"]) == q_low]
    else:
        matches = [f for f in files if q_low in _norm_name(f["name"])]

    # 4.1) Дедуп внутр. совпадений по GUID (гарнтии)
    uniq_by_guid: Dict[str, Dict[str, str]] = {}
    for m in matches:
        g = m["guid"]
        if g not in uniq_by_guid or _ts_value(m.get("ts")) > _ts_value(uniq_by_guid[g].get("ts")):
            uniq_by_guid[g] = m
    matches = list(uniq_by_guid.values())

    # 4.2) В contains по умолчанию (versions=latest) оставляем по одному на имя (самый свежий)
    if match_mode == "contains" and versions == "latest":
        by_name: Dict[str, Dict[str, str]] = {}
        for m in matches:
            key = _norm_name(m["name"])
            if key not in by_name or _ts_value(m.get("ts")) > _ts_value(by_name[key].get("ts")):
                by_name[key] = m
        matches = list(by_name.values())

    logger.info(f"Found matches (unique): {[m['name'] for m in matches]}")

    # 5) Нет совпадений
    if not matches:
        return JSONResponse(
            status_code=404,
            content={"detail": "file_not_found", "requested": filename, "available_files": names_all},
        )

    # 5.1) Один файл → отдаём напрямую
    if len(matches) == 1:
        m = matches[0]
        rr = requests.get(f"{BASE}/files/download/{quote(m['guid'])}",
                          headers=_auth(), stream=True, timeout=READ_TIMEOUT)
        if rr.status_code >= 400:
            raise HTTPException(502, f"Pyrus download error: {rr.text}")
        ctype = rr.headers.get("Content-Type", "application/octet-stream")
        headers = _content_disposition(m["name"])
        headers["X-Pyrus-Versions"] = versions
        return StreamingResponse(rr.iter_content(CHUNK), media_type=ctype, headers=headers)

    # 5.2) exact с одинаковыми именами → берём самый свежий
    if match_mode == "exact" and len({ _norm_name(m["name"]) for m in matches }) == 1:
        last = sorted(matches, key=lambda x: _ts_value(x.get("ts")))[-1]
        rr = requests.get(f"{BASE}/files/download/{quote(last['guid'])}",
                          headers=_auth(), stream=True, timeout=READ_TIMEOUT)
        if rr.status_code >= 400:
            raise HTTPException(502, f"Pyrus download error: {rr.text}")
        ctype = rr.headers.get("Content-Type", "application/octet-stream")
        headers = _content_disposition(last["name"])
        headers["X-Pyrus-Match-Count"] = str(len(matches))
        headers["X-Pyrus-Selected"] = "latest"
        headers["X-Pyrus-Versions"] = versions
        return StreamingResponse(rr.iter_content(CHUNK), media_type=ctype, headers=headers)

    # 5.3) ZIP для нескольких файлов
    buf = io.BytesIO()
    ok_count = 0
    skip_count = 0
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        used = set()
        for m in matches:
            rr = requests.get(f"{BASE}/files/download/{quote(m['guid'])}",
                              headers=_auth(), timeout=READ_TIMEOUT)
            if rr.status_code >= 400:
                logger.warning(f"Skip failed download: name={m['name']} guid={m['guid']} code={rr.status_code}")
                skip_count += 1
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
            ok_count += 1

    if ok_count == 0:
        raise HTTPException(502, "Pyrus download error: all matched files failed")

    buf.seek(0)
    zip_name = f"pyrus_{task_id}_{_safe(q)}_bundle.zip"
    headers = _content_disposition(zip_name)
    headers["X-Pyrus-Match-Count"] = str(len(matches))
    headers["X-Pyrus-Zip-Ok"] = str(ok_count)
    headers["X-Pyrus-Zip-Skipped"] = str(skip_count)
    headers["X-Pyrus-Versions"] = versions
    return StreamingResponse(buf, media_type="application/zip", headers=headers)
