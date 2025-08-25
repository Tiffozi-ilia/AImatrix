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

# --- heuristics / keys ----------------------------------------------------

GUID_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
NAME_KEYS = ("file_name","fileName","name","filename","display_name","displayName","original_name","originalName")
GUID_KEYS = ("file_guid","fileGuid","guid")

# --- helpers --------------------------------------------------------------

def _auth() -> Dict[str, str]:
    return {"Authorization": f"Bearer {get_pyrus_token()}"}

def _unwrap(a: Dict[str, Any] | None) -> Dict[str, Any]:
    """Некоторые ответы приходят как {'file': {...}}"""
    if not a:
        return {}
    return a["file"] if isinstance(a.get("file"), dict) else a

def _pick_value(a: Dict[str, Any], keys: Tuple[str, ...]) -> Tuple[str | None, str | None]:
    """Вернуть (значение, имя_ключа) для первого непустого ключа из списка (с учетом обёртки file)."""
    a = _unwrap(a)
    for k in keys:
        v = a.get(k)
        if v:
            return str(v), k
    return None, None

def _pick_name(att: Dict[str, Any]) -> Tuple[str | None, str | None]:
    return _pick_value(att, NAME_KEYS)

def _pick_guid(att: Dict[str, Any]) -> Tuple[str | None, str | None]:
    """
    Возвращает только реальный file GUID:
      - сначала поля guid/file_guid/fileGuid
      - если нет — пробуем извлечь из downloadUrl
    НЕ используем id/fileId, чтобы не плодить псевдодубли.
    """
    v, k = _pick_value(att, GUID_KEYS)
    if isinstance(v, str) and GUID_RE.match(v):
        return v, k
    a = _unwrap(att)
    for urlk in ("download_url","downloadUrl","url"):
        url = a.get(urlk)
        if isinstance(url, str) and "/files/download/" in url:
            cand = url.rsplit("/", 1)[-1]
            if GUID_RE.match(cand):
                return cand, urlk
    return None, None

def _ts(obj: Dict[str, Any]) -> str:
    """Пытаемся извлечь метку времени (для выбора «последней версии»)."""
    o = _unwrap(obj)
    return o.get("created") or o.get("created_at") or o.get("createdAt") or o.get("date") or ""

def _safe(s: str) -> str:
    return "".join(ch for ch in s if ch.isalnum() or ch in ("-", "_", ".", " ")).strip().replace(" ", "_")

def _content_disposition(filename: str) -> Dict[str, str]:
    quoted_utf8 = quote(filename)
    return {"Content-Disposition": f'attachment; filename="{filename}"; filename*=UTF-8\'\'{quoted_utf8}'}

# --- endpoint -------------------------------------------------------------

@router.get("/download_files_pyrus")
def file_by_name(
    task_id: int = Query(..., description="ID задачи Pyrus"),
    filename: str = Query(..., description="Искомое имя файла"),
    match_mode: str = Query("exact", description="exact|contains"),
    scope: str = Query("top", description="Где искать: top | comments | all"),
    prefer_latest: bool = Query(True, description="Если exact и имена одинаковы — взять последнюю версию"),
    debug: bool = Query(False, description="Вернуть диагностический JSON вместо скачивания"),
):
    """
    Ищет вложения по имени. По умолчанию (scope=top) ищет только в блоке «ФАЙЛЫ» задачи:
      - task.files и task.attachments
    При scope=comments — только в комментариях,
    При scope=all — и там, и там.

    Поиск регистронезависимый; exact | contains.
    Если после дедупа по GUID найден 1 файл — отдаем сам файл (JSON -> правильный Content-Type).
    Иначе — ZIP.
    """
    match_mode = (match_mode or "exact").lower()
    if match_mode not in ("exact", "contains"):
        raise HTTPException(400, "match_mode must be 'exact' or 'contains'")

    scope = (scope or "top").lower()
    if scope not in ("top", "comments", "all"):
        raise HTTPException(400, "scope must be 'top', 'comments', or 'all'")

    q = (filename or "").strip()
    if not q:
        raise HTTPException(400, "filename is empty")

    # 1) Просим сервер вернуть нужные блоки
    r = requests.get(f"{BASE}/tasks/{task_id}?include=comments,files",
                     headers=_auth(), timeout=LIST_TIMEOUT)
    if r.status_code >= 400:
        raise HTTPException(502, f"Pyrus list error: {r.text}")

    data = r.json() or {}
    task = data.get("task", data)

    # 2) Собираем кандидатов
    collected: List[Dict[str, Any]] = []

    def _add_from(seq: List[Dict[str, Any]] | None, origin: str):
        for att in (seq or []):
            name, name_key = _pick_name(att)
            guid, guid_key = _pick_guid(att)
            if name and guid:
                collected.append({
                    "name": name,
                    "guid": guid,
                    "ts": _ts(att),
                    "name_key": name_key,
                    "guid_key": guid_key,
                    "src": origin,
                })

    if scope in ("top", "all"):
        _add_from(task.get("files"), "task.files")
        _add_from(task.get("attachments"), "task.attachments")

    if scope in ("comments", "all"):
        for c in (task.get("comments") or []):
            # прикреплённые к комментам
            _add_from(c.get("attachments"), "comment.attachments")
            _add_from(c.get("files"), "comment.files")

    # 3) Дедуп по GUID
    seen, files = set(), []
    for f in collected:
        g = f["guid"]
        if g in seen:
            continue
        seen.add(g)
        files.append(f)

    # Диагностика
    if debug:
        return {
            "task_id": task_id,
            "requested_filename": filename,
            "match_mode": match_mode,
            "scope": scope,
            "count_after_dedup": len(files),
            "items": files,
            "task_keys": list(task.keys()),
            "comments_count": len(task.get("comments") or []),
            "top_files_count": len(task.get("files") or []),
            "top_attachments_count": len(task.get("attachments") or []),
        }

    # 4) Поиск по имени
    names_all = [f["name"] for f in files]
    qlow = q.lower()
    matches = [f for f in files if f["name"].lower() == qlow] if match_mode == "exact" \
        else [f for f in files if qlow in f["name"].lower()]

    logger.info(f"[pyrus] task={task_id} scope={scope} query={filename} matches={len(matches)}")

    if not matches:
        return JSONResponse(
            status_code=404,
            content={"detail": "file_not_found", "requested": filename, "available_files": names_all},
        )

    # 5) Если один файл — отдаем напрямую (JSON -> правильный Content-Type)
    if len(matches) == 1:
        m = matches[0]
        rr = requests.get(f"{BASE}/files/download/{quote(m['guid'])}",
                          headers=_auth(), stream=True, timeout=READ_TIMEOUT)
        if rr.status_code >= 400:
            raise HTTPException(502, f"Pyrus download error: {rr.text}")

        ctype = "application/json; charset=utf-8" if m["name"].lower().endswith(".json") \
                else rr.headers.get("Content-Type", "application/octet-stream")

        headers = _content_disposition(m["name"])
        headers["X-Pyrus-Source"]   = m.get("src") or ""
        headers["X-Pyrus-Name-Key"] = m.get("name_key") or ""
        headers["X-Pyrus-Guid-Key"] = m.get("guid_key") or ""
        return StreamingResponse(rr.iter_content(CHUNK), media_type=ctype, headers=headers)

    # 6) Если exact и все имена одинаковы — можно взять «последнюю» (если prefer_latest=True)
    if prefer_latest and match_mode == "exact" and len({m["name"].lower() for m in matches}) == 1:
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
        headers["X-Pyrus-Source"]   = last.get("src") or ""
        headers["X-Pyrus-Name-Key"] = last.get("name_key") or ""
        headers["X-Pyrus-Guid-Key"] = last.get("guid_key") or ""
        return StreamingResponse(rr.iter_content(CHUNK), media_type=ctype, headers=headers)

    # 7) Иначе — ZIP всех совпадений; не валимся, если какой-то файл не скачался
    buf = io.BytesIO()
    failed = []
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        used_names = set()
        for m in matches:
            rr = requests.get(f"{BASE}/files/download/{quote(m['guid'])}",
                              headers=_auth(), timeout=READ_TIMEOUT)
            if rr.status_code >= 400:
                failed.append({"name": m["name"], "guid": m["guid"], "code": rr.status_code})
                continue
            arc = m["name"]
            if arc in used_names:
                base, dot, ext = arc.partition(".")
                idx = 1
                n = f"{base} ({idx}){dot}{ext}" if dot else f"{base} ({idx})"
                while n in used_names:
                    idx += 1
                    n = f"{base} ({idx}){dot}{ext}" if dot else f"{base} ({idx})"
                arc = n
            used_names.add(arc)
            zf.writestr(arc, rr.content)

    if not used_names and failed:
        return JSONResponse(status_code=502, content={"detail": "download_failed", "failed": failed})

    buf.seek(0)
    zip_name = f"pyrus_{task_id}_{_safe(q)}_bundle.zip"
    headers = _content_disposition(zip_name)
    headers["X-Pyrus-Match-Count"] = str(len(matches))
    if failed:
        headers["X-Pyrus-Failed-Count"] = str(len(failed))
    return StreamingResponse(buf, media_type="application/zip", headers=headers)
