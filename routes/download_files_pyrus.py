# routes/download_files_pyrus.py
# -*- coding: utf-8 -*-
from typing import Dict, List, Any, Tuple
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

GUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)
NAME_KEYS = ("file_name","fileName","name","filename","display_name","displayName","original_name","originalName")
GUID_KEYS = ("file_guid","fileGuid","guid")

def _auth() -> Dict[str, str]:
    return {"Authorization": f"Bearer {get_pyrus_token()}"}

def _unwrap(a: Dict[str, Any] | None) -> Dict[str, Any]:
    if not a:
        return {}
    return a["file"] if isinstance(a.get("file"), dict) else a

def _pick(a: Dict[str, Any], keys: Tuple[str, ...]) -> Tuple[str | None, str | None]:
    a = _unwrap(a)
    for k in keys:
        v = a.get(k)
        if v:
            return str(v), k
    return None, None

def _pick_name(att: Dict[str, Any]) -> Tuple[str | None, str | None]:
    return _pick(att, NAME_KEYS)

def _pick_guid(att: Dict[str, Any]) -> Tuple[str | None, str | None]:
    # сначала пытаемся взять настоящий GUID из поля
    v, k = _pick(att, GUID_KEYS)
    if isinstance(v, str) and GUID_RE.match(v):
        return v, k
    # иначе пробуем вытащить из downloadUrl
    a = _unwrap(att)
    for urlk in ("download_url","downloadUrl","url"):
        url = a.get(urlk)
        if isinstance(url, str) and "/files/download/" in url:
            cand = url.rsplit("/", 1)[-1]
            if GUID_RE.match(cand):
                return cand, urlk
    return None, None

def _ts(obj: Dict[str, Any]) -> str:
    o = _unwrap(obj)
    return o.get("created") or o.get("created_at") or o.get("createdAt") or o.get("date") or ""

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
    debug: bool = Query(False, description="диагностика: показать список и метаданные"),
):
    match_mode = (match_mode or "exact").lower()
    if match_mode not in ("exact", "contains"):
        raise HTTPException(400, "match_mode must be 'exact' or 'contains'")

    q = (filename or "").strip()
    if not q:
        raise HTTPException(400, "filename is empty")

    # 1) Запрашиваем задачу с нужными блоками
    r = requests.get(f"{BASE}/tasks/{task_id}?include=comments,files",
                     headers=_auth(), timeout=LIST_TIMEOUT)
    if r.status_code >= 400:
        raise HTTPException(502, f"Pyrus list error: {r.text}")
    data = r.json() or {}
    task = data.get("task", data)

    # 2) Собираем все возможные файлы
    collected: List[Dict[str, Any]] = []

    # top-level: files и attachments
    for src_key in ("files", "attachments"):
        for att in (task.get(src_key) or []):
            name, name_key = _pick_name(att)
            guid, guid_key = _pick_guid(att)
            if name and guid:
                collected.append({
                    "name": name, "guid": guid, "ts": _ts(att),
                    "name_key": name_key, "guid_key": guid_key, "src": f"task.{src_key}"
                })

    # комментарии: attachments и files
    for c in (task.get("comments") or []):
        ts = _ts(c)
        for src_key in ("attachments", "files"):
            for att in (c.get(src_key) or []):
                name, name_key = _pick_name(att)
                guid, guid_key = _pick_guid(att)
                if name and guid:
                    collected.append({
                        "name": name, "guid": guid, "ts": ts,
                        "name_key": name_key, "guid_key": guid_key, "src": f"comment.{src_key}"
                    })

    # 3) Фильтруем и дедупим по GUID
    seen, files = set(), []
    for f in collected:
        if f["guid"] in seen:
            continue
        seen.add(f["guid"])
        files.append(f)

    if debug:
        return {
            "task_id": task_id,
            "requested_filename": filename,
            "match_mode": match_mode,
            "count": len(files),
            "items": files
        }

    names_all = [f["name"] for f in files]
    qlow = q.lower()
    matches = [f for f in files if f["name"].lower() == qlow] if match_mode == "exact" \
        else [f for f in files if qlow in f["name"].lower()]

    logger.info(f"Found matches: {[m['name'] for m in matches]}")

    if not matches:
        return JSONResponse(
            status_code=404,
            content={"detail": "file_not_found", "requested": filename, "available_files": names_all},
        )

    # 4) Если один файл — отдаем его напрямую (JSON -> правильный Content-Type)
    if len(matches) == 1:
        m = matches[0]
        rr = requests.get(f"{BASE}/files/download/{quote(m['guid'])}",
                          headers=_auth(), stream=True, timeout=READ_TIMEOUT)
        if rr.status_code >= 400:
            raise HTTPException(502, f"Pyrus download error: {rr.text}")

        ctype = "application/json; charset=utf-8" if m["name"].lower().endswith(".json") \
                else rr.headers.get("Content-Type", "application/octet-stream")
        headers = _content_disposition(m["name"])
        headers["X-Pyrus-Name-Key"] = m.get("name_key") or ""
        headers["X-Pyrus-Guid-Key"] = m.get("guid_key") or ""
        headers["X-Pyrus-Source"]   = m.get("src") or ""
        return StreamingResponse(rr.iter_content(CHUNK), media_type=ctype, headers=headers)

    # 5) Иначе — ZIP всех совпадений; пропускаем неуспешные скачивания
    buf = io.BytesIO()
    failed = []
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        used = set()
        for m in matches:
            rr = requests.get(f"{BASE}/files/download/{quote(m['guid'])}",
                              headers=_auth(), timeout=READ_TIMEOUT)
            if rr.status_code >= 400:
                failed.append({"name": m["name"], "guid": m["guid"], "code": rr.status_code})
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

    if used == set() and failed:
        return JSONResponse(status_code=502, content={"detail": "download_failed", "failed": failed})

    buf.seek(0)
    zip_name = f"pyrus_{task_id}_{_safe(q)}_bundle.zip"
    headers = _content_disposition(zip_name)
    headers["X-Pyrus-Match-Count"] = str(len(matches))
    if failed:
        headers["X-Pyrus-Failed-Count"] = str(len(failed))
    return StreamingResponse(buf, media_type="application/zip", headers=headers)
