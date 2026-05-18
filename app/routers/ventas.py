from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Venta

router = APIRouter(prefix="/ventas", tags=["ventas"])

TURNOS = [
    ("almuerzo",     "Almuerzo"),
    ("cena",         "Cena"),
    ("dia_completo", "Día completo"),
    ("desayuno",     "Desayuno"),
    ("otro",         "Otro"),
]


def _totales(ventas: list) -> dict:
    D = Decimal("0")
    tot = sum(v.total for v in ventas)
    impo = sum(v.impoconsumo or D for v in ventas)
    return {
        "tot_filtrado":  tot,
        "tot_neta":      tot - impo,
        "tot_impo":      impo,
        "tot_efectivo":  sum(v.efectivo or D for v in ventas),
        "tot_tdebito":   sum(v.tarjeta_debito or D for v in ventas),
        "tot_tcredito":  sum(v.tarjeta_credito or D for v in ventas),
        "tot_datafonos": sum((v.tarjeta_debito or D) + (v.tarjeta_credito or D) for v in ventas),
        "tot_transf":    sum(v.transferencia or D for v in ventas),
        "tot_domicilio": sum(v.domicilio or D for v in ventas),
        "tot_propinas":  sum(v.propinas or D for v in ventas),
    }


@router.get("", response_class=HTMLResponse)
def listar(
    request: Request,
    db: Session = Depends(get_db),
    desde: str = "",
    hasta: str = "",
):
    q = db.query(Venta)
    if desde:
        q = q.filter(Venta.fecha >= date.fromisoformat(desde))
    if hasta:
        q = q.filter(Venta.fecha <= date.fromisoformat(hasta))
    ventas = q.order_by(Venta.fecha.desc(), Venta.id.desc()).limit(500).all()

    return request.app.state.templates.TemplateResponse("ventas/list.html", {
        "request": request,
        "ventas": ventas,
        "desde": desde,
        "hasta": hasta,
        **_totales(ventas),
    })


@router.get("/nueva", response_class=HTMLResponse)
def nueva_form(request: Request):
    return request.app.state.templates.TemplateResponse("ventas/form.html", {
        "request": request,
        "venta": None,
        "hoy": date.today().isoformat(),
        "turnos": TURNOS,
    })


@router.post("/nueva")
def crear(
    fecha: str = Form(...),
    turno: str = Form(""),
    total: Decimal = Form(...),
    impoconsumo: Decimal = Form(Decimal("0")),
    efectivo: Decimal = Form(Decimal("0")),
    tarjeta_debito: Decimal = Form(Decimal("0")),
    tarjeta_credito: Decimal = Form(Decimal("0")),
    transferencia: Decimal = Form(Decimal("0")),
    domicilio: Decimal = Form(Decimal("0")),
    propinas: Decimal = Form(Decimal("0")),
    notas: str = Form(""),
    db: Session = Depends(get_db),
):
    db.add(Venta(
        fecha=date.fromisoformat(fecha),
        turno=turno or None,
        total=total,
        impoconsumo=impoconsumo or Decimal("0"),
        efectivo=efectivo or Decimal("0"),
        tarjeta_debito=tarjeta_debito or Decimal("0"),
        tarjeta_credito=tarjeta_credito or Decimal("0"),
        transferencia=transferencia or Decimal("0"),
        domicilio=domicilio or Decimal("0"),
        metodo_pago="mixto" if sum(1 for v in [efectivo, tarjeta_debito, tarjeta_credito, transferencia, domicilio] if v > 0) > 1 else None,
        propinas=propinas or Decimal("0"),
        notas=notas or None,
    ))
    db.commit()
    return RedirectResponse("/ventas", status_code=303)


@router.get("/{venta_id}/editar", response_class=HTMLResponse)
def editar_form(venta_id: int, request: Request, db: Session = Depends(get_db)):
    venta = db.get(Venta, venta_id)
    if not venta:
        return RedirectResponse("/ventas")
    return request.app.state.templates.TemplateResponse("ventas/form.html", {
        "request": request,
        "venta": venta,
        "hoy": venta.fecha.isoformat(),
        "turnos": TURNOS,
    })


@router.post("/{venta_id}/editar")
def editar(
    venta_id: int,
    fecha: str = Form(...),
    turno: str = Form(""),
    total: Decimal = Form(...),
    impoconsumo: Decimal = Form(Decimal("0")),
    efectivo: Decimal = Form(Decimal("0")),
    tarjeta_debito: Decimal = Form(Decimal("0")),
    tarjeta_credito: Decimal = Form(Decimal("0")),
    transferencia: Decimal = Form(Decimal("0")),
    domicilio: Decimal = Form(Decimal("0")),
    propinas: Decimal = Form(Decimal("0")),
    notas: str = Form(""),
    db: Session = Depends(get_db),
):
    venta = db.get(Venta, venta_id)
    if venta:
        venta.fecha = date.fromisoformat(fecha)
        venta.turno = turno or None
        venta.total = total
        venta.impoconsumo = impoconsumo or Decimal("0")
        venta.efectivo = efectivo or Decimal("0")
        venta.tarjeta_debito = tarjeta_debito or Decimal("0")
        venta.tarjeta_credito = tarjeta_credito or Decimal("0")
        venta.transferencia = transferencia or Decimal("0")
        venta.domicilio = domicilio or Decimal("0")
        venta.propinas = propinas or Decimal("0")
        venta.notas = notas or None
        db.commit()
    return RedirectResponse("/ventas", status_code=303)


@router.post("/{venta_id}/eliminar")
def eliminar(venta_id: int, db: Session = Depends(get_db)):
    venta = db.get(Venta, venta_id)
    if venta:
        db.delete(venta)
        db.commit()
    return RedirectResponse("/ventas", status_code=303)
