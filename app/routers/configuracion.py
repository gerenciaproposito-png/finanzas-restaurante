from pathlib import Path

from fastapi import APIRouter, Depends, Form, Request, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Configuracion
from app.services import drive

router = APIRouter(prefix="/configuracion", tags=["configuracion"])
REDIRECT_URI = "http://localhost:8000/configuracion/drive/callback"


def _set_cfg(db: Session, clave: str, valor: str) -> None:
    existing = db.get(Configuracion, clave)
    if existing:
        existing.valor = valor
    else:
        db.add(Configuracion(clave=clave, valor=valor))
    db.commit()


@router.get("", response_class=HTMLResponse)
def vista(request: Request, db: Session = Depends(get_db)):
    def cfg(k):
        c = db.get(Configuracion, k)
        return c.valor if c else ""

    return request.app.state.templates.TemplateResponse("configuracion.html", {
        "request": request,
        "api_key_guardada": bool(cfg("anthropic_api_key")),
        "drive_conectado": drive.is_connected(),
        "credenciales_subidas": drive.has_credentials_file(),
        "folder_url": cfg("drive_folder_url"),
        "folder_id": cfg("drive_folder_id"),
        "ventas_folder_url": cfg("ventas_folder_url"),
        "ventas_folder_id": cfg("ventas_folder_id"),
        "vp_folder_url": cfg("ventas_productos_folder_url"),
        "vp_folder_id": cfg("ventas_productos_folder_id"),
        "sheets_destino_url": cfg("sheets_destino_url"),
        "sheets_destino_id": cfg("sheets_destino_id"),
        "msg": request.query_params.get("msg", ""),
    })


@router.post("/api-key")
def guardar_api_key(api_key: str = Form(...), db: Session = Depends(get_db)):
    _set_cfg(db, "anthropic_api_key", api_key.strip())
    return RedirectResponse("/configuracion?msg=api_key_guardada", status_code=303)


@router.post("/credenciales-google")
async def subir_credenciales(archivo: UploadFile = File(...)):
    contenido = await archivo.read()
    dest = Path("data/google_credentials.json")
    dest.parent.mkdir(exist_ok=True)
    dest.write_bytes(contenido)
    return RedirectResponse("/configuracion?msg=credenciales_subidas", status_code=303)


@router.get("/drive/autorizar")
def autorizar_drive():
    if not drive.has_credentials_file():
        return RedirectResponse("/configuracion?msg=sin_credenciales")
    url = drive.create_auth_url(REDIRECT_URI)
    from fastapi.responses import RedirectResponse as RR
    return RR(url)


@router.get("/drive/callback")
def drive_callback(code: str, db: Session = Depends(get_db)):
    drive.exchange_code(code, REDIRECT_URI)
    return RedirectResponse("/configuracion?msg=drive_conectado", status_code=303)


@router.post("/folder")
def guardar_folder(folder_url: str = Form(...), db: Session = Depends(get_db)):
    # Extract folder ID from URL (https://drive.google.com/drive/folders/FOLDER_ID)
    folder_id = folder_url.strip().rstrip("/").split("/")[-1].split("?")[0]
    _set_cfg(db, "drive_folder_url", folder_url.strip())
    _set_cfg(db, "drive_folder_id", folder_id)
    return RedirectResponse("/configuracion?msg=folder_guardado", status_code=303)


@router.get("/debug-drive")
def debug_drive(db: Session = Depends(get_db)):
    from app.services import drive
    from app.models import Configuracion
    import json

    folder_id = db.get(Configuracion, "drive_folder_id")
    folder_id = folder_id.valor if folder_id else None
    conectado = drive.is_connected()

    files = []
    error = None
    if conectado and folder_id:
        try:
            files = drive.list_images_in_folder(folder_id)
        except Exception as e:
            error = str(e)

    return {
        "conectado": conectado,
        "folder_id": folder_id,
        "archivos_encontrados": len(files),
        "archivos": [{"name": f["name"], "mimeType": f["mimeType"]} for f in files],
        "error": error,
    }


@router.post("/folder-ventas-productos")
def guardar_folder_ventas_productos(folder_url: str = Form(...), db: Session = Depends(get_db)):
    folder_id = folder_url.strip().rstrip("/").split("/")[-1].split("?")[0]
    _set_cfg(db, "ventas_productos_folder_url", folder_url.strip())
    _set_cfg(db, "ventas_productos_folder_id", folder_id)
    return RedirectResponse("/configuracion?msg=ventas_productos_folder_guardado", status_code=303)


@router.post("/folder-ventas")
def guardar_folder_ventas(folder_url: str = Form(...), db: Session = Depends(get_db)):
    folder_id = folder_url.strip().rstrip("/").split("/")[-1].split("?")[0]
    _set_cfg(db, "ventas_folder_url", folder_url.strip())
    _set_cfg(db, "ventas_folder_id", folder_id)
    return RedirectResponse("/configuracion?msg=ventas_folder_guardado", status_code=303)


@router.post("/sincronizar")
def sincronizar_ahora():
    from app.services.sync import run_sync
    stats = run_sync()
    msg = f"sync_ok_{stats['nuevas']}_{stats['errores']}"
    return RedirectResponse(f"/configuracion?msg={msg}", status_code=303)


@router.post("/sincronizar-ventas")
def sincronizar_ventas_ahora():
    from app.services.sync_ventas import run_sync_ventas
    stats = run_sync_ventas()
    msg = f"sync_ventas_ok_{stats['nuevas']}_{stats['errores']}"
    return RedirectResponse(f"/ventas-pendientes?msg={msg}", status_code=303)


@router.post("/sheets-destino")
def guardar_sheets_destino(sheet_url: str = Form(...), db: Session = Depends(get_db)):
    from app.services.sheets import extract_sheet_id
    raw = sheet_url.strip()
    sid = extract_sheet_id(raw)
    if not sid:
        return RedirectResponse("/configuracion?msg=sheets_url_invalida", status_code=303)
    _set_cfg(db, "sheets_destino_url", raw)
    _set_cfg(db, "sheets_destino_id", sid)
    return RedirectResponse("/configuracion?msg=sheets_guardado", status_code=303)


@router.post("/sheets-push")
def sheets_push_ahora(db: Session = Depends(get_db)):
    from app.services.writeback import push_pending
    try:
        stats = push_pending(db)
    except Exception as e:
        return RedirectResponse(f"/configuracion?msg=sheets_error_{str(e)[:60].replace(' ', '+')}", status_code=303)
    msg = f"sheets_push_ok_{stats['gastos']}_{stats['ventas']}_{stats['ventas_productos']}_{stats['errores']}"
    return RedirectResponse(f"/configuracion?msg={msg}", status_code=303)
