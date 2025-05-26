from fastapi import APIRouter
from fastapi.responses import StreamingResponse
import io
import json
import zipfile
import uuid
import time

xmind_export = APIRouter()

def generate_id():
    return str(uuid.uuid4())

@xmind_export.get("/xmind")
def export_xmind():
    buffer = io.BytesIO()

    # Уникальные ID
    sheet_id = generate_id()
    root_id = "ROOT-001"
    sub1_id = "SUB-001"
    sub2_id = "SUB-002"

    # content.json
    content_json = [
        {
            "id": sheet_id,
            "class": "sheet",
            "title": "Карта с корректной структурой notes",
            "rootTopic": {
                "id": root_id,
                "class": "topic",
                "title": "Главная тема",
                "labels": [f"{root_id}|0|||"],
                "notes": {
                    "plain": {
                        "content": "Это заметка к главной теме. Она сохранена в формате notes.plain.content."
                    }
                },
                "children": {
                    "attached": [
                        {
                            "id": sub1_id,
                            "class": "topic",
                            "title": "Первая ветка",
                            "labels": [f"{sub1_id}|1|{root_id}|Главная тема|"],
                            "notes": {
                                "plain": {
                                    "content": "Это заметка к первой ветке."
                                }
                            }
                        },
                        {
                            "id": sub2_id,
                            "class": "topic",
                            "title": "Вторая ветка",
                            "labels": [f"{sub2_id}|1|{root_id}|Главная тема|"],
                            "notes": {
                                "plain": {
                                    "content": "Это заметка ко второй ветке."
                                }
                            }
                        }
                    ]
                }
            }
        }
    ]

    # metadata.json
    metadata_json = {
        "dataStructureVersion": "2",
        "creator": {
            "name": "Render API",
            "version": "1.0"
        },
        "layoutEngineVersion": "3",
        "activeSheetId": sheet_id,
        "familyId": f"local-{str(uuid.uuid4()).replace('-', '')}"
    }

    # manifest.json
    manifest_json = {
        "file-entries": {
            "content.json": {},
            "metadata.json": {}
        }
    }

    # Архивация в .xmind
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("content.json", json.dumps(content_json, ensure_ascii=False, indent=2))
        zf.writestr("metadata.json", json.dumps(metadata_json, ensure_ascii=False, indent=2))
        zf.writestr("manifest.json", json.dumps(manifest_json, ensure_ascii=False, indent=2))

    buffer.seek(0)
    return StreamingResponse(
        buffer,
        media_type="application/vnd.xmind.workbook",
        headers={"Content-Disposition": "attachment; filename=xmind_notes_plain_labels.xmind"}
    )
