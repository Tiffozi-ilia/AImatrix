# routes/render_plantuml.py
# -*- coding: utf-8 -*-

from fastapi import APIRouter, HTTPException, Body, Response
import os, zlib, logging, requests, re
from typing import Literal, Optional
from urllib.parse import urljoin, urlparse

router = APIRouter()
log = logging.getLogger("plantuml")

# Базовые адреса (можно без /uml — код сам попробует оба варианта)
PLANTUML_URL = os.getenv("PLANTUML_URL", "https://my-pluntuml.onrender.com").strip().rstrip("/")
PLANTUML_ALT_URL = os.getenv("PLANTUML_ALT_URL", "").strip().rstrip("/")  # опция
KROKI_URL = os.getenv("KROKI_URL", "").strip().rstrip("/")                # опция (напр., https://kroki.io)

CONNECT_TIMEOUT = 10
READ_TIMEOUT = 60
TIMEOUT = (CONNECT_TIMEOUT, READ_TIMEOUT)

# Предпочитать контекстный путь /uml первее (судя по логам у тебя он стабильнее)
PREFER_CTX = True

# ---------- helpers ----------

def _accept_for(fmt: Literal["png","svg","txt"]) -> str:
    # некоторые PlantUML сборки странно реагируют на узкий Accept, ставим */*
    return "*/*"

def _ensure_with_ctx(base: str, ctx: bool) -> str:
    if not base:
        return ""
    if ctx:
        return base if base.endswith("/uml") else base + "/uml"
    else:
        return base[:-4] if base.endswith("/uml") else base

def _encode6bit(b: int) -> str:
    if b < 10:  return chr(48 + b)   # 0-9
    b -= 10
    if b < 26: return chr(65 + b)   # A-Z
    b -= 26
    if b < 26: return chr(97 + b)   # a-z
    b -= 26
    return "-" if b == 0 else "_"

def _append3bytes(b1: int, b2: int, b3: int) -> str:
    c1 = (b1 >> 2) & 0x3F
    c2 = ((b1 & 0x03) << 4) | ((b2 >> 4) & 0x0F)
    c3 = ((b2 & 0x0F) << 2) | ((b3 >> 6) & 0x03)
    c4 = b3 & 0x3F
    return ''.join((_encode6bit(c1), _encode6bit(c2), _encode6bit(c3), _encode6bit(c4)))

def plantuml_encode(uml: str) -> str:
    data = uml.encode("utf-8")
    comp = zlib.compressobj(level=9, wbits=-15)  # raw deflate
    compressed = comp.compress(data) + comp.flush()
    out = []
    i = 0
    n = len(compressed)
    while i < n:
        b1 = compressed[i]
        b2 = compressed[i + 1] if i + 1 < n else 0
        b3 = compressed[i + 2] if i + 2 < n else 0
        out.append(_append3bytes(b1, b2, b3))
        i += 3
    return ''.join(out)

def _normalize_code(code: str) -> str:
    """
    Нормализация:
    - Если есть @startuml и @enduml — не трогаем
    - Если только @startuml — добавляем @enduml
    - Если есть @startX (mindmap, wbs и т.п.) — не трогаем
    - Иначе оборачиваем в @startuml/@enduml
    """
    s = code.strip()
    if not s:
        return s

    has_startuml = "@startuml" in s.lower()
    has_enduml = "@enduml" in s.lower()

    if has_startuml and has_enduml:
        return s
    if has_startuml and not has_enduml:
        return s + "\n@enduml"
    if re.search(r'@start\w+', s, re.IGNORECASE):
        return s
    return f"@startuml\n{s}\n@enduml"

def _looks_like_html_text(s: str) -> bool:
    t = s.lstrip().lower()
    return t.startswith("<!doctype") or t.startswith("<html")

def _is_html_response(resp: requests.Response) -> bool:
    ct = (resp.headers.get("Content-Type") or "").lower()
    return "text/html" in ct

def _build_headers(fmt: Literal["png","svg","txt"]) -> dict:
    return {
        "Accept": _accept_for(fmt)
