from fastapi import FastAPI
from routes import json_export, md_full, md_clean, zip_export, csv_export, excel_export, opml_export, mm_export

app = FastAPI()

app.include_router(json_export.router)
app.include_router(md_full.router)
app.include_router(md_clean.router)
app.include_router(zip_export.router)
app.include_router(csv_export.router)
app.include_router(excel_export.router)
app.include_router(opml_export.router)
app.include_router(mm_router)
