import tempfile
from datetime import date
from decimal import Decimal
from pathlib import Path

from fastapi import APIRouter, Depends, Form, Request, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import VentaProducto, Configuracion
from app.services import drive as _drive
from app.services.importar_ventas_productos import (
    parse_excel, importar_lote, latest_fecha_corte, get_fechas_con_conteo, drive_import,
)

router = APIRouter(prefix="/ventas-productos", tags=["ventas_productos"])


@router.get("", response_class=HTMLResponse)
def listar(request: Request, db: Session = Depends(get_db),
           fecha_corte: str = "", categoria: str = ""):

    fechas = get_fechas_con_conteo(db)

    # Default to latest fecha_corte
    fecha_sel: date | None = None
    if fecha_corte:
        try:
            fecha_sel = date.fromisoformat(fecha_corte)
        except ValueError:
            pass
    if fecha_sel is None:
        fecha_sel = latest_fecha_corte(db)

    resumen: dict = {}
    total_unidades = 0
    total_ingresos = Decimal("0")
    categorias_list: list[str] = []

    if fecha_sel:
        q = db.query(VentaProducto).filter(VentaProducto.fecha_corte == fecha_sel)
        if categoria:
            q = q.filter(VentaProducto.categoria == categoria)
        registros = q.order_by(VentaProducto.categoria, VentaProducto.cantidad.desc()).all()

        for r in registros:
            if r.categoria not in resumen:
                resumen[r.categoria] = {"unidades": 0, "total": Decimal("0"), "productos": []}
            resumen[r.categoria]["unidades"] += r.cantidad
            resumen[r.categoria]["total"] += r.total
            resumen[r.categoria]["productos"].append(r)
            total_unidades += r.cantidad
            total_ingresos += r.total

        # All categories (unfiltered) for the dropdown
        categorias_list = sorted(set(
            r[0] for r in db.query(VentaProducto.categoria)
            .filter(VentaProducto.fecha_corte == fecha_sel)
            .distinct().all()
        ))

    return request.app.state.templates.TemplateResponse("ventas_productos/list.html", {
        "request": request,
        "resumen": resumen,
        "total_unidades": total_unidades,
        "total_ingresos": total_ingresos,
        "fecha_sel": fecha_sel,
        "fechas": fechas,
        "categorias_list": categorias_list,
        "categoria_filtro": categoria,
    })


@router.get("/importar", response_class=HTMLResponse)
def vista_importar(request: Request, db: Session = Depends(get_db)):
    def cfg(k):
        c = db.get(Configuracion, k)
        return c.valor if c else ""

    fechas = get_fechas_con_conteo(db)
    return request.app.state.templates.TemplateResponse("ventas_productos/importar.html", {
        "request": request,
        "drive_conectado": _drive.is_connected(),
        "folder_url": cfg("ventas_productos_folder_url"),
        "folder_id": cfg("ventas_productos_folder_id"),
        "fechas": fechas,
        "hoy": date.today().isoformat(),
        "msg": request.query_params.get("msg", ""),
        "err": request.query_params.get("err", ""),
    })


@router.post("/importar")
async def importar(
    request: Request,
    db: Session = Depends(get_db),
    fuente: str = Form(...),
    fecha_corte: str = Form(...),
    reemplazar: str = Form(default=""),
    archivo: UploadFile = File(default=None),
):
    try:
        fc = date.fromisoformat(fecha_corte)
    except ValueError:
        return RedirectResponse("/ventas-productos/importar?err=Fecha+inválida", status_code=303)

    replace = bool(reemplazar)

    if fuente == "drive":
        result = drive_import(db, fc, replace)
        if "error" in result:
            err = result["error"].replace(" ", "+")
            return RedirectResponse(f"/ventas-productos/importar?err={err}", status_code=303)
        n, nombre = result["filas"], result["archivo"]
        return RedirectResponse(
            f"/ventas-productos?fecha_corte={fc}&msg=ok_{n}_{nombre}",
            status_code=303,
        )

    # File upload
    if not archivo or not archivo.filename:
        return RedirectResponse("/ventas-productos/importar?err=No+se+recibió+archivo", status_code=303)

    content = await archivo.read()
    with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
        tmp.write(content)
        tmp_path = Path(tmp.name)

    try:
        rows = parse_excel(tmp_path)
        n = importar_lote(db, rows, fc, "upload", replace)
    except Exception as e:
        return RedirectResponse(f"/ventas-productos/importar?err={str(e)[:100]}", status_code=303)
    finally:
        tmp_path.unlink(missing_ok=True)

    return RedirectResponse(f"/ventas-productos?fecha_corte={fc}&msg=ok_{n}", status_code=303)


@router.post("/eliminar-corte")
def eliminar_corte(fecha_corte: str = Form(...), db: Session = Depends(get_db)):
    try:
        fc = date.fromisoformat(fecha_corte)
        db.query(VentaProducto).filter(VentaProducto.fecha_corte == fc).delete()
        db.commit()
    except Exception:
        pass
    return RedirectResponse("/ventas-productos/importar", status_code=303)
