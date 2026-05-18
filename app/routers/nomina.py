from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Empleado, Nomina

router = APIRouter(prefix="/nomina", tags=["nomina"])


@router.get("", response_class=HTMLResponse)
def listar(request: Request, db: Session = Depends(get_db)):
    empleados = db.query(Empleado).order_by(Empleado.nombre).all()
    pagos_recientes = (
        db.query(Nomina)
        .order_by(Nomina.fecha_fin.desc())
        .limit(30)
        .all()
    )
    return request.app.state.templates.TemplateResponse("nomina/list.html", {
        "request": request,
        "empleados": empleados,
        "pagos_recientes": pagos_recientes,
        "hoy": date.today().isoformat(),
    })


@router.post("/empleado")
def crear_empleado(
    nombre: str = Form(...),
    cedula: str = Form(""),
    cargo: str = Form(""),
    sueldo_base: Decimal = Form(Decimal("0")),
    tipo_contrato: str = Form(""),
    db: Session = Depends(get_db),
):
    db.add(Empleado(
        nombre=nombre,
        cedula=cedula or None,
        cargo=cargo or None,
        sueldo_base=sueldo_base,
        tipo_contrato=tipo_contrato or None,
    ))
    db.commit()
    return RedirectResponse("/nomina", status_code=303)


@router.post("/empleado/{empleado_id}/inactivar")
def inactivar_empleado(empleado_id: int, db: Session = Depends(get_db)):
    emp = db.get(Empleado, empleado_id)
    if emp:
        emp.activo = False
        db.commit()
    return RedirectResponse("/nomina", status_code=303)


@router.get("/pago/nuevo", response_class=HTMLResponse)
def nuevo_pago_form(request: Request, db: Session = Depends(get_db)):
    empleados = db.query(Empleado).filter(Empleado.activo == True).order_by(Empleado.nombre).all()
    return request.app.state.templates.TemplateResponse("nomina/pago_form.html", {
        "request": request,
        "empleados": empleados,
        "hoy": date.today().isoformat(),
    })


@router.post("/pago/nuevo")
def registrar_pago(
    empleado_id: int = Form(...),
    fecha_inicio: str = Form(...),
    fecha_fin: str = Form(...),
    dias_trabajados: str = Form(""),
    sueldo: Decimal = Form(...),
    propinas: Decimal = Form(Decimal("0")),
    deducciones: Decimal = Form(Decimal("0")),
    notas: str = Form(""),
    db: Session = Depends(get_db),
):
    neto = sueldo + (propinas or Decimal("0")) - (deducciones or Decimal("0"))
    db.add(Nomina(
        empleado_id=empleado_id,
        fecha_inicio=date.fromisoformat(fecha_inicio),
        fecha_fin=date.fromisoformat(fecha_fin),
        dias_trabajados=int(dias_trabajados) if dias_trabajados else None,
        sueldo=sueldo,
        propinas=propinas or Decimal("0"),
        deducciones=deducciones or Decimal("0"),
        neto_pagado=neto,
        notas=notas or None,
    ))
    db.commit()
    return RedirectResponse("/nomina", status_code=303)


@router.post("/pago/{pago_id}/eliminar")
def eliminar_pago(pago_id: int, db: Session = Depends(get_db)):
    pago = db.get(Nomina, pago_id)
    if pago:
        db.delete(pago)
        db.commit()
    return RedirectResponse("/nomina", status_code=303)
