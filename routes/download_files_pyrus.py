# routes/download_files_pyrus.py
from fastapi import APIRouter, Query, HTTPException
from fastapi.responses import StreamingResponse, JSONResponse
import requests, io, zipfile
from utils.data_loader import get_pyrus_token  # ← токен берём отсюда
from urllib.parse import quote

router = APIRouter()
BASE = "https://pyrus.sovcombank.ru/api/v4"

def _auth():
    return {"Authorization": f"Bearer {get_pyrus_token()}"}

def _pick_name(a):  # разный нейминг у вложений
    return a.get("file_name") or a.get("name") or a.get("filename")

def _pick_guid(a):
    return a.get("guid") or a.get("file_guid") or a.get("id")

def _safe(s):
    return "".join(ch for ch in s if ch.isalnum() or ch in ("-", "_", ".", " ")).strip().replace(" ", "_")

@router.get("/pyrus/file_by_name")
def file_by_name(
    task_id: int = Query(..., description="ID задачи Pyrus"),
    filename: str = Query(..., description="Искомое имя файла"),
    match_mode: str = Query("exact", description="exact|contains"),
):
    if match_mode not in ("exact", "contains"):
        raise HTTPException(400, "match_mode must be 'exact' or 'contains'")

    q = filename.strip().lower()
    if not q:
        raise HTTPException(400, "filename is empty")

    # 1) список вложений
    r = requests.get(f"{BASE}/tasks/{task_id}", headers=_auth(), timeout=60)
    if r.status_code >= 400:
        raise HTTPException(502, f"Pyrus list error: {r.text}")
    task = r.json() or {}

    files = []
    for c in task.get("comments", []) or []:
        ts = c.get("created") or c.get("date") or ""
        for a in c.get("attachments", []) or []:
            name = _pick_name(a)
            guid = _pick_guid(a)
            if name and guid:
                files.append({"name": str(name), "guid": str(guid), "ts": ts})

    names_all = [f["name"] for f in files]

    # 2) поиск совпадений (регистронезависимо)
    if match_mode == "exact":
        matches = [f for f in files if f["name"].lower() == q]
    else:
        matches = [f for f in files if q in f["name"].lower()]

    # 3) возврат результата
    if not matches:
        return JSONResponse(
            status_code=404,
            content={"detail": "file_not_found", "requested": filename, "available_files": names_all},
        )

    if len(matches) == 1:
        m = matches[0]
        rr = requests.get(f"{BASE}/files/download/{quote(m['guid'])}", headers=_auth(), stream=True, timeout=300)
        if rr.status_code >= 400:
            raise HTTPException(502, f"Pyrus download error: {rr.text}")
        ctype = rr.headers.get("Content-Type", "application/octet-stream")
        headers = {"Content-Disposition": f'attachment; filename="{m["name"]}"'}
        return StreamingResponse(rr.iter_content(8192), media_type=ctype, headers=headers)

    # >1: exact + все имена одинаковые → последняя версия
    if match_mode == "exact" and len({m["name"].lower() for m in matches}) == 1:
        last = sorted(matches, key=lambda x: x["ts"] or "")[-1]
        rr = requests.get(f"{BASE}/files/download/{quote(last['guid'])}", headers=_auth(), stream=True, timeout=300)
        if rr.status_code >= 400:
            raise HTTPException(502, f"Pyrus download error: {rr.text}")
        ctype = rr.headers.get("Content-Type", "application/octet-stream")
        headers = {
            "Content-Disposition": f'attachment; filename="{last["name"]}"',
            "X-Pyrus-Match-Count": str(len(matches)),
            "X-Pyrus-Selected": "latest",
        }
        return StreamingResponse(rr.iter_content(8192), media_type=ctype, headers=headers)

    # иначе → ZIP всех совпавших
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        used = set()
        for m in matches:
            rr = requests.get(f"{BASE}/files/download/{quote(m['guid'])}", headers=_auth(), timeout=300)
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
    zip_name = f"pyrus_{task_id}_{_safe(filename)}_bundle.zip"
    headers = {
        "Content-Disposition": f'attachment; filename="{zip_name}"',
        "X-Pyrus-Match-Count": str(len(matches)),
    }
    return StreamingResponse(buf, media_type="application/zip", headers=headers)
