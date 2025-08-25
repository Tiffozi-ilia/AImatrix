# routes/download_files_pyrus.py
# -*- coding: utf-8 -*-
from typing import Dict, List, Any
from urllib.parse import quote
import io, zipfile, requests
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse, JSONResponse
from utils.data_loader import get_pyrus_token  # берём токен из твоего лоадера

router = APIRouter()

BASE = "https://pyrus.sovcombank.ru/api/v4"
READ_TIMEOUT = 300
LIST_TIMEOUT = 60
CHUNK = 8192

def _auth() -> Dict[str, str]:
    return {"Authorization": f"Bearer {get_pyrus_token()}"}

def _pick_name(a: Dict[str, Any]) -> str | None:
    return a.get("file_name") or a.get("name") or a.get("filename")

def _pick_guid(a: Dict[str, Any]) -> str | None:
    return a.get("guid") or a.get("file_guid") or a.get("id")

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
    Ищет вложения в задаче Pyrus по имени:
      - 0 совпадений → 404 + список доступных имён;
      - 1 совпадение → отдаём файл (stream);
      - >1 совпадений:
          * exact и все имена идентичны → отдаём последнюю версию;
          * иначе → ZIP всех совпавших.
    Поиск регистронезависимый.
    """
    if match_mode not in ("exact", "contains"):
        raise HTTPException(400, "match_mode must be 'exact' or 'contains'")

    q = (filename or "").strip()
    if not q:
        raise HTTPException(400, "filename is empty")

    # 1) список вложений задачи
    r = requests.get(f"{BASE}/tasks/{task_id}", headers=_auth(), timeout=LIST_TIMEOUT)
    if r.status_code >= 400:
        raise HTTPException(502, f"Pyrus list error: {r.text}")
    task = r.json() or {}

    files: List[Dict[str, str]] = []
    for c in task.get("comments", []) or []:
        ts = c.get("created") or c.get("date") or ""  # строка-время комментария
        for a in c.get("attachments", []) or []:
            name = _pick_name(a)
            guid = _pick_guid(a)
            if name and guid:
                files.append({"name": str(name), "guid": str(guid), "ts": ts})

    names_all = [f["name"] for f in files]
    q_low = q.lower()

    # 2) поиск (case-insensitive)
    if match_mode == "exact":
        matches = [f for f in files if f["name"].lower() == q_low]
    else:
        matches = [f for f in files if q_low in f["name"].lower()]

    # 3) возврат
    if not matches:
        return JSONResponse(
            status_code=404,
            content={"detail": "file_not_found", "requested": filename, "available_files": names_all},
        )

    if len(matches) == 1:
        m = matches[0]
        rr = requests.get(f"{BASE}/files/download/{quote(m['guid'])}", headers=_auth(), stream=True, timeout=READ_TIMEOUT)
        if rr.status_code >= 400:
            raise HTTPException(502, f"Pyrus download error: {rr.text}")
        ctype = rr.headers.get("Content-Type", "application/octet-stream")
        return StreamingResponse(rr.iter_content(CHUNK), media_type=ctype, headers=_content_disposition(m["name"]))

    # >1 совпадений
    if match_mode == "exact" and len({m["name"].lower() for m in matches}) == 1:
        # все имена одинаковы → последняя версия по ts (строка; если пусто — порядок API)
        last = sorted(matches, key=lambda x: x["ts"] or "")[-1]
        rr = requests.get(f"{BASE}/files/download/{quote(last['guid'])}", headers=_auth(), stream=True, timeout=READ_TIMEOUT)
        if rr.status_code >= 400:
            raise HTTPException(502, f"Pyrus download error: {rr.text}")
        ctype = rr.headers.get("Content-Type", "application/octet-stream")
        headers = _content_disposition(last["name"])
        headers["X-Pyrus-Match-Count"] = str(len(matches))
        headers["X-Pyrus-Selected"] = "latest"
        return StreamingResponse(rr.iter_content(CHUNK), media_type=ctype, headers=headers)

    # иначе — ZIP
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
