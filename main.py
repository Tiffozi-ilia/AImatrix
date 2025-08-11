from fastapi import FastAPI
from routes import json_export, md_full, md_clean, md_clean_cut, md_clean_single, md_clean_depth, md_clean_multiple, zip_export, csv_export, excel_export, opml_export, mm_export, xmind_export, pyrus_upload, xmind_procedures, generate_kpi, xmind_sync_github, update_parent_names, api_ping
from routes.call_pyrus_upload import router as call_pyrus_upload_router

app = FastAPI()

app.include_router(json_export.router)
app.include_router(md_full.router)
app.include_router(md_clean.router)
app.include_router(md_clean_cut.router)
app.include_router(md_clean_single.router)
app.include_router(md_clean_depth.router)
app.include_router(md_clean_multiple.router)
app.include_router(zip_export.router)
app.include_router(csv_export.router)
app.include_router(excel_export.router)
app.include_router(opml_export.router)
app.include_router(mm_export.router)
app.include_router(xmind_export.router)
app.include_router(pyrus_upload.router)
app.include_router(xmind_procedures.router)
app.include_router(call_pyrus_upload_router)
app.include_router(generate_kpi.router)
app.include_router(xmind_sync_github.router)
app.include_router(update_parent_names.router)
app.include_router(api_ping.router)
