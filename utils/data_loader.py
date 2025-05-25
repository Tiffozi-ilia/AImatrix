import requests
import pandas as pd
import os
import time
from fastapi import HTTPException

# Простейший in-memory кэш
_cached_token = None
_cached_expiration = 0

def get_pyrus_token():
    global _cached_token, _cached_expiration
    now = time.time()

    if _cached_token and now < _cached_expiration:
        return _cached_token

    login = os.environ.get("PYRUS_LOGIN")
    security_key = os.environ.get("PYRUS_SECURITY_KEY")

    if not login or not security_key:
        raise HTTPException(status_code=500, detail="PYRUS_LOGIN или PYRUS_SECURITY_KEY не заданы")

    auth_url = "https://accounts.pyrus.com/api/v4/auth/"
    headers = {"Content-Type": "application/json"}
    payload = {"login": login, "security_key": security_key}

    try:
        resp = requests.post(auth_url, json=payload, headers=headers)
        resp.raise_for_status()
        data = resp.json()
        _cached_token = data["access_token"]
        _cached_expiration = now + 55 * 60  # токен живёт 55 минут
        return _cached_token
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка авторизации в Pyrus: {str(e)}")
