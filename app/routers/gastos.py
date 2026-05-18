from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Categoria, Gasto, Proveedor

router = APIRouter(prefix="/gastos", tags=["gastos"])

TIPOS_DOCUMENTO = [
    ("factura_e",    "Factura electrónica"),
    ("factura_papel","Factura papel"),
    ("ticket",       "Ticket / POS"),
    ("recibo",       "Recibo"),
    ("sin_soporte",  "Sin soporte"),
]

MEDIOS_PAGO = [
    ("efectivo",          "Efectivo"),
    ("transferencia",     "Transferencia"),
    ("tarjeta_debito",    "Tarjeta débito"),
    ("tarjeta_credito",   "Tarjeta crédito"),
    ("credito_proveedor", "Crédito proveedor"),
]

ESTADOS_PAGO = [
    ("pagado",   "Pagado"),
    ("pendiente","Pendiente"),
    ("credito",  "Crédito"),
]


@router.get("", response_class=HTMLResponse)
def listar(
    request: Request,
    db: Session = Depends(get_db),
    desde: str = "",
    hasta: str = "",
    categoria_id: str = "",
    proveedor_id: str = "",
    medio_pago: str = "",
    estado_pago: str = "",
):
    q = db.query(Gasto)
    if desde:
        q = q.filter(Gasto.fecha >= date.fromisoformat(desde))
    if hasta:
        q = q.filter(Gasto.fecha <= date.fromisoformat(hasta))
    if categoria_id:
        q = q.filter(Gasto.categoria_id == int(categoria_id))
    if proveedor_id:
        q = q.filter(Gasto.proveedor_id == int(proveedor_id))
    if medio_pago:
        q = q.filter(Gasto.medio_pago == medio_pago)
    if estado_pago:
        q = q.filter(Gasto.estado_pago == estado_pago)

    gastos = q.order_by(Gasto.fecha.desc(), Gasto.id.desc()).limit(500).all()
    total_filtrado = sum(g.total for g in gastos)
    total_pendiente = sum(g.total for g in gastos if g.estado_pago in ("pendiente", "credito"))

    categorias  = db.query(Categoria).filter(Categoria.tipo == "gasto").order_by(Categoria.nombre).all()
    proveedores = db.query(Proveedor).order_by(Proveedor.nombre).all()

    return request.app.state.templates.TemplateResponse("gastos/list.html", {
        "request": request,
        "gastos": gastos,
        "categorias": categorias,
        "proveedores": proveedores,
        "desde": desde,
        "hasta": hasta,
        "categoria_id": categoria_id,
        "proveedor_id": proveedor_id,
        "medio_pago": medio_pago,
        "estado_pago": estado_pago,
        "total_filtrado": total_filtrado,
        "total_pendiente": total_pendiente,
        "medios_pago": MEDIOS_PAGO,
        "estados_pago": ESTADOS_PAGO,
    })


@router.get("/nuevo", response_class=HTMLResponse)
def nuevo_form(request: Request, db: Session = Depends(get_db)):
    return request.app.state.templates.TemplateResponse("gastos/form.html", {
        "request": request,
        "gasto": None,
        "proveedores": db.query(Proveedor).order_by(Proveedor.nombre).all(),
        "categorias": db.query(Categoria).filter(Categoria.tipo == "gasto").order_by(Categoria.nombre).all(),
        "hoy": date.today().isoformat(),
        "tipos_documento": TIPOS_DOCUMENTO,
        "medios_pago": MEDIOS_PAGO,
        "estados_pago": ESTADOS_PAGO,
    })


@router.post("/nuevo")
def crear(
    fecha: str = Form(...),
    proveedor_id: str = Form(""),
    categoria_id: str = Form(""),
    descripcion: str = Form(""),
    subtotal: Decimal = Form(Decimal("0")),
    iva: Decimal = Form(Decimal("0")),
    total: Decimal = Form(...),
    num_factura: str = Form(""),
    tipo_documento: str = Form(""),
    medio_pago: str = Form(""),
    estado_pago: str = Form("pagado"),
    notas: str = Form(""),
    db: Session = Depends(get_db),
):
    db.add(Gasto(
        fecha=date.fromisoformat(fecha),
        proveedor_id=int(proveedor_id) if proveedor_id else None,
        categoria_id=int(categoria_id) if categoria_id else None,
        descripcion=descripcion or None,
        subtotal=subtotal or Decimal("0"),
        iva=iva or Decimal("0"),
        total=total,
        num_factura=num_factura or None,
        tipo_documento=tipo_documento or None,
        medio_pago=medio_pago or None,
        estado_pago=estado_pago or "pagado",
        notas=notas or None,
    ))
    db.commit()
    return RedirectResponse("/gastos", status_code=303)


@router.get("/{gasto_id}/editar", response_class=HTMLResponse)
def editar_form(gasto_id: int, request: Request, db: Session = Depends(get_db)):
    gasto = db.get(Gasto, gasto_id)
    if not gasto:
        return RedirectResponse("/gastos")
    return request.app.state.templates.TemplateResponse("gastos/form.html", {
        "request": request,
        "gasto": gasto,
        "proveedores": db.query(Proveedor).order_by(Proveedor.nombre).all(),
        "categorias": db.query(Categoria).filter(Categoria.tipo == "gasto").order_by(Categoria.nombre).all(),
        "hoy": gasto.fecha.isoformat(),
        "tipos_documento": TIPOS_DOCUMENTO,
        "medios_pago": MEDIOS_PAGO,
        "estados_pago": ESTADOS_PAGO,
    })


@router.post("/{gasto_id}/editar")
def editar(
    gasto_id: int,
    fecha: str = Form(...),
    proveedor_id: str = Form(""),
    categoria_id: str = Form(""),
    descripcion: str = Form(""),
    subtotal: Decimal = Form(Decimal("0")),
    iva: Decimal = Form(Decimal("0")),
    total: Decimal = Form(...),
    num_factura: str = Form(""),
    tipo_documento: str = Form(""),
    medio_pago: str = Form(""),
    estado_pago: str = Form("pagado"),
    notas: str = Form(""),
    db: Session = Depends(get_db),
):
    gasto = db.get(Gasto, gasto_id)
    if gasto:
        gasto.fecha = date.fromisoformat(fecha)
        gasto.proveedor_id = int(proveedor_id) if proveedor_id else None
        gasto.categoria_id = int(categoria_id) if categoria_id else None
        gasto.descripcion = descripcion or None
        gasto.subtotal = subtotal or Decimal("0")
        gasto.iva = iva or Decimal("0")
        gasto.total = total
        gasto.num_factura = num_factura or None
        gasto.tipo_documento = tipo_documento or None
        gasto.medio_pago = medio_pago or None
        gasto.estado_pago = estado_pago or "pagado"
        gasto.notas = notas or None
        db.commit()
    return RedirectResponse("/gastos", status_code=303)


@router.post("/{gasto_id}/eliminar")
def eliminar(gasto_id: int, db: Session = Depends(get_db)):
    gasto = db.get(Gasto, gasto_id)
    if gasto:
        db.delete(gasto)
        db.commit()
    return RedirectResponse("/gastos", status_code=303)
