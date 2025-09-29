# routers/pyrus_simple.py
# -*- coding: utf-8 -*-
import json
import mimetypes
from typing import Optional, Union
import requests
from fastapi import APIRouter, HTTPException, Body

from utils.data_loader import get_pyrus_token

try:
    import yaml  # PyYAML
except Exception:
    yaml = None  # Чтобы явно подсказать об отсутствии зависимости

router = APIRouter()
PYRUS_API = "https://pyrus.sovcombank.ru/api/v4"

def _pyrus_headers():
    return {"Authorization": f"Bearer {get_pyrus_token()}"}

def _guess_content_type(filename: str, default: str = "application/octet-stream") -> str:
    # Приоритетные типы для yaml
    if filename.lower().endswith((".yaml", ".yml")):
        return "application/x-yaml"
    if filename.lower().endswith(".json"):
        return "application/json"
    ctype, _ = mimetypes.guess_type(filename)
    return ctype or default

def _normalize_json(body_data: Union[str, dict, list]) -> bytes:
    """
    Принимает dict/list или JSON-строку; возвращает байты нормализованного JSON (utf-8).
    """
    try:
        if isinstance(body_data, str):
            parsed = json.loads(body_data)
            return json.dumps(parsed, ensure_ascii=False, indent=2).encode("utf-8")
        else:
            return json.dumps(body_data, ensure_ascii=False, indent=2).encode("utf-8")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Некорректный JSON: {e}")

def _normalize_yaml(body_data: Union[str, dict, list]) -> bytes:
    """
    Принимает dict/list или YAML-строку; возвращает байты нормализованного YAML (utf-8).
    Требует PyYAML (yaml.safe_load / yaml.safe_dump).
    """
    if yaml is None:
        raise HTTPException(
            status_code=500,
            detail="Поддержка YAML недоступна: не установлен пакет PyYAML. Установите `PyYAML`."
        )
    try:
        # Разрешаем как 'сырой' YAML, так и dict/list.
        # Если пришла строка — валидируем парсером и дампим назад для нормализации.
        if isinstance(body_data, str):
            parsed = yaml.safe_load(body_data)
            # safe_load может вернуть что угодно; чаще ожидаем dict/list
            return yaml.safe_dump(parsed, allow_unicode=True, sort_keys=False).encode("utf-8")
        else:
            return yaml.safe_dump(body_data, allow_unicode=True, sort_keys=False).encode("utf-8")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Некорректный YAML: {e}")

@router.post("/upload_files_pyrus")
async def upload_to_pyrus(
    request_data: dict = Body(...)
):
    """
    Универсальная загрузка файла в Pyrus:
    - Источник ИЛИ body (dict/list/str), ИЛИ src_url (абсолютный URL или путь вида /...).
    - Поддержка форматов JSON и YAML через поле 'format' ('json'|'yaml') или по расширению filename.
    Параметры:
      - filename: имя файла (по умолчанию artifact.json)
      - task_id: ID задачи Pyrus (обязателен)
      - body: содержимое (dict/list или строка)
      - src_url: внешний URL/путь для скачивания файла
      - format: 'json' | 'yaml' | 'auto' (по умолчанию auto)
      - comment_text: текст комментария к задаче (по умолчанию "Файл из Dify")
    """
    filename: str = request_data.get("filename", "artifact.json")
    task_id = request_data.get("task_id")
    body_data = request_data.get("body")
    src_url = request_data.get("src_url")
    fmt: str = (request_data.get("format") or "auto").lower().strip()
    comment_text: str = request_data.get("comment_text") or "Файл из Dify"

    # Обязательные поля
    if task_id is None:
        raise HTTPException(status_code=400, detail="Не указан task_id")

    # Ровно один источник
    if (src_url is None) == (body_data is None):
        raise HTTPException(
            status_code=400,
            detail="Укажите либо src_url, либо body — строго один источник."
        )

    # Определим формат, если auto
    inferred_fmt = None
    if fmt == "auto":
        if filename.lower().endswith((".yaml", ".yml")):
            inferred_fmt = "yaml"
        elif filename.lower().endswith(".json"):
            inferred_fmt = "json"
    else:
        if fmt not in ("json", "yaml"):
            raise HTTPException(status_code=400, detail="format должен быть 'json', 'yaml' или 'auto'.")
        inferred_fmt = fmt

    # 1) Получаем байты файла
    if body_data is not None:
        # Если формат не задан через filename и fmt=auto, по умолчанию считаем JSON
        effective_fmt = inferred_fmt or "json"

        if effective_fmt == "json":
            data_bytes = _normalize_json(body_data)
            if filename.lower().endswith((".yaml", ".yml")):
                # если имя конфликтует с форматом — поправим
                filename = filename.rsplit(".", 1)[0] + ".json"
            content_type = "application/json"

        elif effective_fmt == "yaml":
            data_bytes = _normalize_yaml(body_data)
            if not filename.lower().endswith((".yaml", ".yml")):
                # если имя без yaml-расширения — поправим
                if filename.lower().endswith(".json"):
                    filename = filename.rsplit(".", 1)[0] + ".yaml"
                else:
                    filename = filename + ".yaml"
            content_type = "application/x-yaml"

        else:
            # На всякий
            data_bytes = _normalize_json(body_data)
            content_type = "application/json"

    else:
        # src_url-ветка: скачиваем как есть, тип по filename или по заголовку ответа
        url = src_url.strip()
        if url.startswith("/"):
            # ваш особый случай хостинга
            url = f"https://files.dify.ai{url}"
        try:
            r = requests.get(url, timeout=60)
            r.raise_for_status()
            data_bytes = r.content
        except requests.exceptions.RequestException as e:
            raise HTTPException(status_code=400, detail=f"Не удалось скачать файл по src_url={url}: {e}")

        # content_type: сначала из имени файла, затем из ответа
        content_type = _guess_content_type(filename)
        # Если сервер дал хороший content-type — используем его
        ct_from_resp = r.headers.get("Content-Type")
        if ct_from_resp:
            content_type = ct_from_resp.split(";")[0].strip()

    # 2) Загружаем файл в Pyrus (files/upload)
    try:
        up = requests.post(
            f"{PYRUS_API}/files/upload",
            headers=_pyrus_headers(),
            files={"file": (filename, data_bytes, content_type)},
            timeout=60,
        )
        up.raise_for_status()
        guid = up.json()["guid"]
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Ошибка загрузки в Pyrus: {e}")

    # 3) Прикрепляем к задаче
    try:
        cm = requests.post(
            f"{PYRUS_API}/tasks/{task_id}/comments",
            headers={**_pyrus_headers(), "Content-Type": "application/json"},
            data=json.dumps({"text": comment_text, "attachments": [guid]}, ensure_ascii=False),
            timeout=60,
        )
        cm.raise_for_status()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Ошибка прикрепления к задаче: {e}")

    return {"status": "ok", "task_id": task_id, "filename": filename}
