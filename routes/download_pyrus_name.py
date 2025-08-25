from fastapi import APIRouter, Query, HTTPException
from fastapi.responses import StreamingResponse, JSONResponse
import httpx, os, io, zipfile
from typing import List, Dict, Any

router = APIRouter()
PYRUS_API = "https://api.pyrus.com/v4"
PYRUS_TOKEN = os.getenv("PYRUS_API_TOKEN")
if not PYRUS_TOKEN:
    raise RuntimeError("Set PYRUS_API_TOKEN in env")

HEADERS = {"Authorization": f"Bearer {PYRUS_TOKEN}"}


def _pick_name(att: Dict[str, Any]) -> str | None:
    return att.get("file_name") or att.get("name") or att.get("filename")


def _pick_guid(att: Dict[str, Any]) -> str | None:
    return att.get("guid") or att.get("file_guid") or att.get("id")


async def _list_task_files(client: httpx.AsyncClient, task_id: int) -> List[Dict[str, str]]:
    # Берём всю задачу и вытаскиваем attachments из comments
    r = await client.get(f"{PYRUS_API}/tasks/{task_id}", headers=HEADERS, timeout=60)
    if r.status_code >= 400:
        raise HTTPException(status_code=502, detail=f"pyrus_error: {r.text}")
    task = r.json() or {}
    files: List[Dict[str, str]] = []
    for c in task.get("comments", []):
        # время комментария — может пригодиться как uploaded_at
        uploaded_at = c.get("created") or c.get("date") or ""
        for a in c.get("attachments", []) or []:
            name = _pick_name(a)
            guid = _pick_guid(a)
            if name and guid:
                files.append({"name": str(name), "guid": str(guid), "uploaded_at": uploaded_at})
    return files


async def _download_one(client: httpx.AsyncClient, guid: str) -> httpx.Response:
    # Документация: GET /files/download/{file-id}
    return await client.get(f"{PYRUS_API}/files/download/{guid}", headers=HEADERS, timeout=300)


def _sanitize_for_zip(s: str) -> str:
    # простая санация для имени архива
    return "".join(ch for ch in s if ch.isalnum() or ch in ("-", "_", ".", " ")).strip().replace(" ", "_")


@router.get("/download_pyrus_name")
async def pyrus_file_by_name(
    task_id: int = Query(..., description="ID задачи Pyrus"),
    filename: str = Query(..., description="Искомое имя файла"),
    match_mode: str = Query("exact", regex="^(exact|contains)$", description="Режим сопоставления: exact|contains")
):
    """
    Поиск файла(ов) по имени в задаче Pyrus.
    - 0 совпадений -> 404 + список доступных имён
    - 1 совпадение -> отдаем файл (stream)
    - >1 совпадений:
        * exact и имена идентичны -> отдаем последнюю версию
        * иначе -> ZIP всех совпавших
    """
    filename_q = filename.strip()
    if not filename_q:
        raise HTTPException(400, "filename is empty")

    async with httpx.AsyncClient() as client:
        files = await _list_task_files(client, task_id)
        names_all = [f["name"] for f in files]

        fn_l = filename_q.lower()
        if match_mode == "exact":
            matches = [f for f in files if f["name"].lower() == fn_l]
        else:  # contains
            matches = [f for f in files if fn_l in f["name"].lower()]

        # 0 совпадений
        if not matches:
            return JSONResponse(
                status_code=404,
                content={"detail": "file_not_found", "requested": filename_q, "available_files": names_all},
            )

        # 1 совпадение -> отдаем файл
        if len(matches) == 1:
            one = matches[0]
            r = await _download_one(client, one["guid"])
            if r.status_code >= 400:
                raise HTTPException(502, f"pyrus_error: {r.text}")
            ctype = r.headers.get("Content-Type", "application/octet-stream")
            disp = r.headers.get("Content-Disposition")
            headers = {}
            if not disp or "filename=" not in disp:
                headers["Content-Disposition"] = f'attachment; filename="{one["name"]}"'
            else:
                headers["Content-Disposition"] = disp
            return StreamingResponse(iter([r.content]), media_type=ctype, headers=headers)

        # >1 совпадений
        # exact + все имена идентичны -> последняя версия
        all_same_name = match_mode == "exact" and len({m["name"].lower() for m in matches}) == 1
        if all_same_name:
            # сортировка по uploaded_at (если строка даты есть) – последние выше
            # если даты нет или не парсится – порядок останется как пришёл (обычно последним – свежий)
            def sort_key(x):
                return x.get("uploaded_at") or ""
            matches_sorted = sorted(matches, key=sort_key)  # лексикографически по дате-строке приемлемо
            last = matches_sorted[-1]
            r = await _download_one(client, last["guid"])
            if r.status_code >= 400:
                raise HTTPException(502, f"pyrus_error: {r.text}")
            ctype = r.headers.get("Content-Type", "application/octet-stream")
            headers = {
                "Content-Disposition": f'attachment; filename="{last["name"]}"',
                "X-Pyrus-Match-Count": str(len(matches)),
                "X-Pyrus-Selected": "latest"
            }
            return StreamingResponse(iter([r.content]), media_type=ctype, headers=headers)

        # иначе -> собрать ZIP из всех совпавших
        # ВНИМАНИЕ: создаём in-memory ZIP. Для очень больших файлов лучше делать потоковую упаковку.
        zip_buf = io.BytesIO()
        with zipfile.ZipFile(zip_buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
            for m in matches:
                r = await _download_one(client, m["guid"])
                if r.status_code >= 400:
                    raise HTTPException(502, f"pyrus_error: {r.text}")
                # сохраняем оригинальные имена
                arcname = m["name"]
                # избегаем дубликатов имён внутри архива
                if arcname in zf.namelist():
                    base, dot, ext = arcname.partition(".")
                    idx = 1
                    newname = f"{base} ({idx}){dot}{ext}" if dot else f"{base} ({idx})"
                    while newname in zf.namelist():
                        idx += 1
                        newname = f"{base} ({idx}){dot}{ext}" if dot else f"{base} ({idx})"
                    arcname = newname
                zf.writestr(arcname, r.content)

        zip_buf.seek(0)
        zip_name = f"pyrus_{task_id}_{_sanitize_for_zip(filename_q)}_bundle.zip"
        headers = {
            "Content-Disposition": f'attachment; filename="{zip_name}"',
            "X-Pyrus-Match-Count": str(len(matches))
        }
        return StreamingResponse(zip_buf, media_type="application/zip", headers=headers)
