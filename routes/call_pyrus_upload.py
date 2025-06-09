import json
import requests
from fastapi import APIRouter
from fastapi.responses import PlainTextResponse

router = APIRouter()

@router.get("/call-pyrus-upload", response_class=PlainTextResponse)
def run_script():
    xmind_url = "https://raw.githubusercontent.com/Tiffozi-ilia/AImatrix/all-in/matrix.xmind"
    headers = {"Content-Type": "application/json"}
    payload = json.dumps(xmind_url)

    base = "https://aimatrix-e8zs.onrender.com"
    endpoints = {
        "DIFF": f"{base}/xmind-diff",
        "UPDATED": f"{base}/xmind-updated",
        "DELETED": f"{base}/xmind-delete",
        "MAPPING": f"{base}/pyrus_mapping"
    }

    results = {}
    logs = []

    def log(msg):
        print(msg)
        logs.append(msg)

    for name, url in endpoints.items():
        log(f"\n\n=== {name} ===")
        try:
            response = requests.post(url, data=payload, headers=headers)
            log(f"Status code: {response.status_code}")

            if response.status_code != 200:
                log(f"Response error:\n{response.text}")
                continue

            data = response.json()
            results[name] = data

            if "content" in data:
                log("Markdown preview:\n" + data["content"][:1000])

            for key in ["json", "rows", "actions", "created", "updated", "deleted", "markdown", "error"]:
                if key in data:
                    val = data[key]
                    count = len(val) if isinstance(val, list) else "-"
                    log(f"{key.capitalize()}: {count}")

        except Exception as e:
            log(f"❌ Request failed: {str(e)}")

    log("\n\n=== ИТОГОВАЯ СБОРКА JSON ДЛЯ PYRUS ===")

    create_data = results.get("DIFF", {}).get("json", [])
    update_data = results.get("UPDATED", {}).get("json", [])
    delete_data = results.get("DELETED", {}).get("json", [])
    mapping_data = results.get("MAPPING", {}).get("for_pyrus", {})

    log(f"\n--- CREATE ({len(create_data)}) ---")
    for row in create_data:
        log(json.dumps(row, ensure_ascii=False))

    log(f"\n--- UPDATE ({len(update_data)}) ---")
    for row in update_data:
        log(json.dumps(row, ensure_ascii=False))

    log(f"\n--- DELETE ({len(delete_data)}) ---")
    for row in delete_data:
        log(json.dumps(row, ensure_ascii=False))

    for section in ["new", "updated", "deleted"]:
        items = mapping_data.get(section, [])
        log(f"\n--- {section.upper()} ({len(items)}) ---")
        for item in items:
            log(json.dumps(item, ensure_ascii=False))

    log("\n✅ Сборка завершена. Готово к передаче в pyrus_create / update / delete")
    return "\n".join(logs[-200:])  # ограничим вывод
