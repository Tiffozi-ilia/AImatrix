# routes/render_plantuml_yaml.py
# -*- coding: utf-8 -*-
from fastapi import APIRouter, HTTPException, Body, Response
import os, requests
from typing import Literal

router = APIRouter()

# 1: как в локальном — берём BASE из окружения, БЕЗ автоматического /uml
PLANTUML_URL = os.getenv("PLANTUML_URL", "https://my-pluntuml.onrender.com").strip()

# 2: таймауты — 10/60, как в локальном
CONNECT_TIMEOUT = 10
READ_TIMEOUT = 60
TIMEOUT = (CONNECT_TIMEOUT, READ_TIMEOUT)

# 3: сколько текста показывать при ошибке — 800, как в локальном
ERR_PREVIEW = 800


def _join_endpoint(base: str, fmt: str) -> str:
    """Идентично локальному скрипту: срезаем хвосты /png|/svg|/txt и добавляем /{fmt}."""
    base = base.rstrip("/")
    for suffix in ("/png", "/svg", "/txt"):
        if base.endswith(suffix):
            base = base[: -len(suffix)]
    return f"{base}/{fmt.lstrip('/')}"


@router.post("/render_plantuml_yaml")
def render_plantuml_yaml(
    fmt: Literal["png", "svg", "txt"],
    code: str = Body(..., media_type="text/plain", description="Сырой PlantUML-текст (text/plain или application/x-yaml)."),
):
    """
    Точная аналогия локальному скрипту:
    - Только прямой POST на {PLANTUML_URL}/{fmt}
    - Content-Type: text/plain; charset=utf-8
    - Accept: */*
    - НИКАКИХ нормализаций/разэкранирований/GET-encode/контекстов
    - Ошибки и проверки Content-Type как в локальном
    """
    code = (code or "")
    if not code.strip():
        raise HTTPException(400, "Empty PlantUML code")

    # Собираем URL как в локальном
    url = _join_endpoint(PLANTUML_URL, fmt)

    headers = {
        "Content-Type": "text/plain; charset=utf-8",
        "Accept": "*/*",  # как в локальном
    }

    try:
        resp = requests.post(url, data=code.encode("utf-8"), headers=headers, timeout=TIMEOUT)
    except requests.RequestException as e:
        # Тот же тип сообщения, что в локальном (Network error ...)
        raise HTTPException(502, f"Network error while POST {url}: {e!r}")

    ctype = (resp.headers.get("Content-Type") or "")
    # Сначала проверка на HTML UI — как в локальном
    if "text/html" in ctype.lower():
        raise HTTPException(
            502,
            detail=(
                "Server вернул HTML UI вместо картинки. "
                f"Эндпойнт неправильный: {url}. "
                "Попробуй BASE с /uml или без — зависит от твоего сервера."
            ),
        )

    # Затем статус-код — как в локальном
    if resp.status_code != 200:
        preview = resp.text[:ERR_PREVIEW] if resp.text else ""
        raise HTTPException(502, f"Upstream error {resp.status_code}: {preview}")

    # Возвращаем как в локальном: txt -> text, иначе -> bytes
    if fmt == "txt":
        return Response(content=resp.text, media_type="text/plain; charset=utf-8")
    elif fmt == "svg":
        return Response(content=resp.content, media_type="image/svg+xml")
    else:
        return Response(content=resp.content, media_type="image/png")
