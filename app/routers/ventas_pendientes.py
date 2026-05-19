import json
from datetime import date
from decimal import Decimal
from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import VentaPendiente, Venta

router = APIRouter(prefix="/ventas-pendientes", tags=["ventas_pendientes"])

TURNOS = [
    ("almuerzo",    "Almuerzo"),
    ("cena",        "Cena"),
    ("dia_completo","Día completo"),
    ("desayuno",    "Desayuno"),
    ("otro",        "Otro"),
]

METODOS_PAGO = [
    ("efectivo",       "Efectivo"),
    ("tarjeta_debito", "Tarjeta débito"),
    ("tarjeta_credito","Tarjeta crédito"),
    ("transferencia",  "Transferencia"),
    ("mixto",          "Mixto / varios"),
]


@router.get("", response_class=HTMLResponse)
def listar(request: Request, db: Session = Depends(get_db)):
    pendientes = (
        db.query(VentaPendiente)
        .filter(VentaPendiente.estado == "pendiente")
        .order_by(VentaPendiente.fecha_sync.desc())
        .all()
    )
    return request.app.state.templates.TemplateResponse(
        "ventas_pendientes/list.html",
        {"request": request, "pendientes": pendientes},
    )


@router.get("/{vp_id}/revisar", response_class=HTMLResponse)
def revisar(vp_id: int, request: Request, db: Session = Depends(get_db)):
    vp = db.get(VentaPendiente, vp_id)
    if not vp:
        return RedirectResponse("/ventas-pendientes")

    datos = json.loads(vp.datos_json) if vp.datos_json else {}

    imagen_url = None
    is_pdf = bool(vp.nombre_archivo and vp.nombre_archivo.lower().endswith(".pdf"))

    if vp.archivo_local:
        p = Path(vp.archivo_local)
        if p.exists():
            imagen_url = f"/uploads/ventas/{p.name}"

    if imagen_url is None and vp.drive_file_id:
        imagen_url = f"/ventas-pendientes/{vp_id}/imagen"

    return request.app.state.templates.TemplateResponse("ventas_pendientes/revisar.html", {
        "request": request,
        "vp": vp,
        "datos": datos,
        "imagen_url": imagen_url,
        "is_pdf": is_pdf,
        "hoy": date.today().isoformat(),
        "turnos": TURNOS,
        "metodos_pago": METODOS_PAGO,
    })


@router.post("/{vp_id}/confirmar")
async def confirmar(vp_id: int, request: Request, db: Session = Depends(get_db)):
    vp = db.get(VentaPendiente, vp_id)
    if not vp:
        return RedirectResponse("/ventas-pendientes", status_code=303)

    form = await request.form()

    fecha = date.fromisoformat(form.get("fecha") or date.today().isoformat())
    turno = form.get("turno") or None
    total = Decimal(form.get("total") or "0")
    impoconsumo = Decimal(form.get("impoconsumo") or "0")
    efectivo = Decimal(form.get("efectivo") or "0")
    tarjeta_debito = Decimal(form.get("tarjeta_debito") or "0")
    tarjeta_credito = Decimal(form.get("tarjeta_credito") or "0")
    transferencia = Decimal(form.get("transferencia") or "0")
    domicilio = Decimal(form.get("domicilio") or "0")
    propinas = Decimal(form.get("propinas") or "0")
    notas = form.get("notas") or None

    no_cero = sum(1 for v in [efectivo, tarjeta_debito, tarjeta_credito, transferencia, domicilio] if v > 0)
    if no_cero == 1:
        metodo_pago = next(k for k, v in {
            "efectivo": efectivo, "tarjeta_debito": tarjeta_debito,
            "tarjeta_credito": tarjeta_credito, "transferencia": transferencia,
            "domicilio": domicilio,
        }.items() if v > 0)
    elif no_cero > 1:
        metodo_pago = "mixto"
    else:
        metodo_pago = None

    try:
        venta = Venta(
            fecha=fecha,
            turno=turno,
            total=total,
            impoconsumo=impoconsumo,
            efectivo=efectivo,
            tarjeta_debito=tarjeta_debito,
            tarjeta_credito=tarjeta_credito,
            transferencia=transferencia,
            domicilio=domicilio,
            metodo_pago=metodo_pago,
            propinas=propinas,
            notas=notas or None,
        )
        db.add(venta)
        db.flush()

        vp.estado = "confirmado"
        vp.venta_id = venta.id
        db.commit()
    except Exception as e:
        db.rollback()
        return request.app.state.templates.TemplateResponse(
            "error.html",
            {"request": request, "error": str(e)},
            status_code=500,
        )

    try:
        from app.services.writeback import push_pending
        push_pending(db)
    except Exception:
        pass

    return RedirectResponse("/ventas-pendientes", status_code=303)


@router.get("/{vp_id}/imagen")
def imagen(vp_id: int, db: Session = Depends(get_db)):
    vp = db.get(VentaPendiente, vp_id)
    if not vp:
        return Response(status_code=404)

    # Serve from local file if available
    if vp.archivo_local:
        p = Path(vp.archivo_local)
        if p.exists():
            suffix = p.suffix.lower()
            mime = "application/pdf" if suffix == ".pdf" else f"image/{suffix.lstrip('.') or 'jpeg'}"
            return Response(content=p.read_bytes(), media_type=mime)

    # Fall back to Drive proxy
    if vp.drive_file_id:
        from app.services import drive as _drive
        try:
            data, mime = _drive.stream_file(vp.drive_file_id)
            return Response(content=data, media_type=mime)
        except Exception:
            pass

    return Response(status_code=404)


@router.post("/{vp_id}/reprocesar")
def reprocesar(vp_id: int, db: Session = Depends(get_db)):
    vp = db.get(VentaPendiente, vp_id)
    if not vp:
        return RedirectResponse("/ventas-pendientes", status_code=303)

    cfg = db.get(__import__("app.models", fromlist=["Configuracion"]).Configuracion, "anthropic_api_key")
    api_key = cfg.valor if cfg else None
    if not api_key:
        return RedirectResponse(f"/ventas-pendientes/{vp_id}/revisar?err=sin_api_key", status_code=303)

    from pathlib import Path as _Path
    from app.services.ocr_ventas import extract_venta
    from app.services.sync_ventas import UPLOADS_DIR, MIME_EXT
    from app.services import drive
    import json as _json

    # Determine file to process: use local if available, else re-download from Drive
    archivo = _Path(vp.archivo_local) if vp.archivo_local else None
    if not archivo or not archivo.exists():
        if not vp.drive_file_id:
            return RedirectResponse(
                f"/ventas-pendientes/{vp_id}/revisar?err=Archivo+no+disponible",
                status_code=303,
            )
        if not drive.is_connected():
            return RedirectResponse(
                f"/ventas-pendientes/{vp_id}/revisar?err=Google+Drive+no+conectado",
                status_code=303,
            )
        try:
            nombre = vp.nombre_archivo or ""
            ext = ".jpg"
            for mime, e in MIME_EXT.items():
                if nombre.lower().endswith(e):
                    ext = e
                    break
            UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
            archivo = UPLOADS_DIR / f"{vp.drive_file_id}{ext}"
            drive.download_file(vp.drive_file_id, archivo)
            vp.archivo_local = str(archivo)
        except Exception as e:
            return RedirectResponse(
                f"/ventas-pendientes/{vp_id}/revisar?err={str(e)[:80]}",
                status_code=303,
            )

    try:
        datos = extract_venta(archivo, api_key)
        if isinstance(datos, list):
            datos = datos[0] if datos else {}
        vp.datos_json = _json.dumps(datos, ensure_ascii=False)
        db.commit()
    except Exception as e:
        return RedirectResponse(f"/ventas-pendientes/{vp_id}/revisar?err={str(e)[:80]}", status_code=303)

    return RedirectResponse(f"/ventas-pendientes/{vp_id}/revisar", status_code=303)


@router.post("/{vp_id}/descartar")
def descartar(vp_id: int, db: Session = Depends(get_db)):
    vp = db.get(VentaPendiente, vp_id)
    if vp:
        vp.estado = "descartado"
        db.commit()
    return RedirectResponse("/ventas-pendientes", status_code=303)
