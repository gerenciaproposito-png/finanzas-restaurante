import os
from contextlib import asynccontextmanager
from pathlib import Path

# Allow OAuth over http for local development
os.environ.setdefault("OAUTHLIB_INSECURE_TRANSPORT", "1")

from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app import models
from app.database import engine
from app.seeds import seed_categorias
from app.utils import cop
from app.routers import (
    dashboard, ventas, gastos, proveedores, categorias,
    configuracion, facturas, precios,
    inventario, nomina, reportes, ventas_pendientes, ventas_productos,
)

BASE_DIR = Path(__file__).resolve().parent
UPLOADS_DIR = Path(os.getenv("UPLOADS_DIR", str(BASE_DIR.parent / "uploads")))

# En cloud: escribe las credenciales de Google desde variables de entorno
_DATA_DIR = BASE_DIR.parent / "data"
_DATA_DIR.mkdir(exist_ok=True)
for _env_var, _filename in [
    ("GOOGLE_CREDENTIALS_JSON", "google_credentials.json"),
    ("GOOGLE_TOKEN_JSON",       "google_token.json"),
]:
    _content = os.getenv(_env_var)
    if _content:
        (_DATA_DIR / _filename).write_text(_content, encoding="utf-8")


@asynccontextmanager
async def lifespan(app: FastAPI):
    from app.services.scheduler import start as start_scheduler
    start_scheduler()
    yield


app = FastAPI(title="Finanzas Restaurante", lifespan=lifespan)

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    import traceback
    return PlainTextResponse(f"ERROR DETALLADO:\n{traceback.format_exc()}", status_code=500)

models.Base.metadata.create_all(bind=engine)
from app.database import run_migrations
run_migrations()
seed_categorias()

import json as _json
templates = Jinja2Templates(directory=BASE_DIR / "templates", auto_reload=True)
templates.env.filters["cop"] = cop
templates.env.filters["from_json"] = lambda s: _json.loads(s) if s else {}
app.state.templates = templates

UPLOADS_DIR.mkdir(exist_ok=True)
(UPLOADS_DIR / "ventas").mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
app.mount("/uploads", StaticFiles(directory=UPLOADS_DIR), name="uploads")

app.include_router(dashboard.router)
app.include_router(ventas.router)
app.include_router(gastos.router)
app.include_router(proveedores.router)
app.include_router(categorias.router)
app.include_router(configuracion.router)
app.include_router(facturas.router)
app.include_router(precios.router)
app.include_router(inventario.router)
app.include_router(nomina.router)
app.include_router(reportes.router)
app.include_router(ventas_pendientes.router)
app.include_router(ventas_productos.router)
