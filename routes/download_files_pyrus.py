# -*- coding: utf-8 -*-
from fastapi import APIRouter, Query, HTTPException
from fastapi.responses import StreamingResponse, JSONResponse
from typing import List, Dict, Any
import requests, io, zipfile
from urllib.parse import quote

# берем токен через твой загрузчик
from data_loader import get_pyrus_token

PYRUS_BASE = "https://pyrus.sovcombank.ru/api/v4"
router = APIRouter()

def _auth_headers() -> Dict[str, str]:
    token = get_pyrus_token()
    return {"Authorization": f"Bearer {token}"}

def _pick_name(att: Dict[str, Any]) -> str | None:
    return att.get("file_name") or att.get("name") or att.get("filename")

def _pick_guid(att: Dict[str, Any]) -> str | None:
    return att.get("guid") or att.get("file_guid") or att.get("id")

def _safe(s: str) -> str:
    return "".join(ch for ch in s if ch.isalnum() or ch in ("-", "_", ".", " ")).strip().replace(" ", "_")

def _list_task_files(task_id: int) -> List[Dict[str, str]]:
    """Получаем задачу и собираем attachments из comments."""
    r = requests.get(f"{PYRUS_BASE}/tasks/{task_id}", headers=_auth_headers(), timeout=60)
    if r.status_code >= 400:
        raise HTTPException(502, f"pyrus_error (list): {r.text}")
    task = r.json() or {}
    files: List[Dict[str, str]] = []
    for c in task.get("comments", []) or []:
        uploaded_at = c.get("created") or c.get("date") or ""  # пригодится для выбора "последней версии"
        for a in c.get("attachments", []) or []:
            name = _pick_name(a)
            guid = _pick_guid(a)
            if name and guid:
                files.append({"name": str(name), "guid": str(guid), "uploaded_at": uploaded_at})
    return files

def _download_response(guid: str) -> requests.Response:
    """Возвращает streaming-ответ Pyrus для скачивания файла."""
    r = requests.get(f"{PYRUS_BASE}/files/download/{quote(guid)}", headers=_auth_headers(), stream=True, timeout=300)
    if r.status_code >= 400:
        raise HTTPException(502, f"pyrus_error (download): {r.text}")
    return r

@router.get("/download_files_pyrus")
def pyrus_file_by_name(
    task_id: int = Query(..., description="ID задачи Pyrus"),
    filename: str = Query(..., description="Искомое имя файла"),
    match_mode: str = Query("exact", pattern="^(exact|contains)$", description="Режим сопоставления: exact|contains")
):
    """
    Экспорт вложений по имени (регистронезависимо).
    - 0 совпадений -> 404 + список доступных имён
    - 1 совпадение -> отдаем файл (stream)
    - >1 совпадений:
        * exact и имена идентичны -> отдаем последнюю версию
        * иначе -> ZIP всех совпавших
    """
    filename_q = (filename or "").strip()
    if not filename_q:
        raise HTTPException(400, "filename is empty")

    files = _list_task_files(task_id)
    names_all = [f["name"] for f in files]
    q = filename_q.lower()

    if match_mode == "exact":
        matches = [f for f in files if f["name"].lower() == q]
    else:  # contains
        matches = [f for f in files if q in f["name"].lower()]

    # 0 совпадений
    if not matches:
        return JSONResponse(
            status_code=404,
            content={"detail": "file_not_found", "requested": filename_q, "available_files": names_all},
        )

    # 1 совпадение -> отдаем файл
    if len(matches) == 1:
        one = matches[0]
        r = _download_response(one["guid"])
        ctype = r.headers.get("Content-Type", "application/octet-stream")
        disp = r.headers.get("Content-Disposition")
        headers = {}
        # если имя не пришло — задаём сами
        if not disp or "filename=" not in disp:
            headers["Content-Disposition"] = f'attachment; filename="{one["name"]}"'
        else:
            headers["Content-Disposition"] = disp
        return StreamingResponse(r.iter_content(chunk_size=8192), media_type=ctype, headers=headers)

    # >1 совпадений
    # exact + все имена идентичны -> последняя версия
    all_same_name = (match_mode == "exact") and len({m["name"].lower() for m in matches}) == 1
    if all_same_name:
        # сортируем по uploaded_at как строке (если пусто — порядок API сохранится)
        matches_sorted = sorted(matches, key=lambda x: x.get("uploaded_at") or "")
        last = matches_sorted[-1]
        r = _download_response(last["guid"])
        ctype = r.headers.get("Content-Type", "application/octet-stream")
        headers = {
            "Content-Disposition": f'attachment; filename="{last["name"]}"',
            "X-Pyrus-Match-Count": str(len(matches)),
            "X-Pyrus-Selected": "latest"
        }
        return StreamingResponse(r.iter_content(chunk_size=8192), media_type=ctype, headers=headers)

    # иначе — собрать ZIP со всеми совпавшими
    zip_buf = io.BytesIO()
    with zipfile.ZipFile(zip_buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        used_names = set()
        for m in matches:
            rr = _download_response(m["guid"])
            content = rr.content  # если ожидаются большие файлы — можно заменить на потоковую упаковку
            arcname = m["name"]
            # избегаем коллизий имён внутри архива
            if arcname in used_names:
                base, dot, ext = arcname.partition(".")
                idx = 1
                newname = f"{base} ({idx}){dot}{ext}" if dot else f"{base} ({idx})"
                while newname in used_names:
                    idx += 1
                    newname = f"{base} ({idx}){dot}{ext}" if dot else f"{base} ({idx})"
                arcname = newname
            used_names.add(arcname)
            zf.writestr(arcname, content)

    zip_buf.seek(0)
    zip_name = f"pyrus_{task_id}_{_safe(filename_q)}_bundle.zip"
    headers = {
        "Content-Disposition": f'attachment; filename="{zip_name}"',
        "X-Pyrus-Match-Count": str(len(matches))
    }
    return StreamingResponse(zip_buf, media_type="application/zip", headers=headers)
