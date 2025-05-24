from fastapi import FastAPI
from routes.json_raw import router as json_router
from routes.md_full import router as md_full_router
from routes.md_clean import router as md_clean_router
from routes.zip_md import router as zip_router
from routes.csv import router as csv_router
from routes.excel import router as excel_router
from routes.opml_export import router as opml_router

app = FastAPI()
app.include_router(json_router)
app.include_router(md_full_router)
app.include_router(md_clean_router)
app.include_router(zip_router)
app.include_router(csv_router)
app.include_router(excel_router)
app.include_router(opml_router)