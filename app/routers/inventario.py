from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import InventarioItem, MovimientoInventario

router = APIRouter(prefix="/inventario", tags=["inventario"])


@router.get("", response_class=HTMLResponse)
def listar(request: Request, db: Session = Depends(get_db)):
    items = db.query(InventarioItem).order_by(InventarioItem.nombre).all()
    alertas = [i for i in items if i.stock_minimo is not None and i.stock_actual <= i.stock_minimo]
    return request.app.state.templates.TemplateResponse("inventario/list.html", {
        "request": request,
        "items": items,
        "alertas": alertas,
    })


@router.get("/nuevo-item", response_class=HTMLResponse)
def nuevo_item_form(request: Request):
    return request.app.state.templates.TemplateResponse("inventario/item_form.html", {
        "request": request, "item": None,
    })


@router.post("/nuevo-item")
def crear_item(
    nombre: str = Form(...),
    unidad: str = Form("und"),
    stock_actual: Decimal = Form(Decimal("0")),
    costo_promedio: Decimal = Form(Decimal("0")),
    stock_minimo: str = Form(""),
    db: Session = Depends(get_db),
):
    db.add(InventarioItem(
        nombre=nombre,
        unidad=unidad or "und",
        stock_actual=stock_actual,
        costo_promedio=costo_promedio,
        stock_minimo=Decimal(stock_minimo) if stock_minimo else None,
    ))
    db.commit()
    return RedirectResponse("/inventario", status_code=303)


@router.get("/{item_id}/editar", response_class=HTMLResponse)
def editar_item_form(item_id: int, request: Request, db: Session = Depends(get_db)):
    item = db.get(InventarioItem, item_id)
    if not item:
        return RedirectResponse("/inventario")
    return request.app.state.templates.TemplateResponse("inventario/item_form.html", {
        "request": request, "item": item,
    })


@router.post("/{item_id}/editar")
def editar_item(
    item_id: int,
    nombre: str = Form(...),
    unidad: str = Form("und"),
    stock_minimo: str = Form(""),
    costo_promedio: Decimal = Form(Decimal("0")),
    db: Session = Depends(get_db),
):
    item = db.get(InventarioItem, item_id)
    if item:
        item.nombre = nombre
        item.unidad = unidad or "und"
        item.costo_promedio = costo_promedio
        item.stock_minimo = Decimal(stock_minimo) if stock_minimo else None
        db.commit()
    return RedirectResponse("/inventario", status_code=303)


@router.get("/{item_id}/movimiento", response_class=HTMLResponse)
def movimiento_form(item_id: int, request: Request, db: Session = Depends(get_db)):
    item = db.get(InventarioItem, item_id)
    if not item:
        return RedirectResponse("/inventario")
    movimientos = (
        db.query(MovimientoInventario)
        .filter(MovimientoInventario.item_id == item_id)
        .order_by(MovimientoInventario.fecha.desc())
        .limit(20)
        .all()
    )
    return request.app.state.templates.TemplateResponse("inventario/movimiento_form.html", {
        "request": request,
        "item": item,
        "movimientos": movimientos,
        "hoy": date.today().isoformat(),
    })


@router.post("/{item_id}/movimiento")
def registrar_movimiento(
    item_id: int,
    tipo: str = Form(...),
    cantidad: Decimal = Form(...),
    costo_unitario: str = Form(""),
    fecha: str = Form(...),
    notas: str = Form(""),
    db: Session = Depends(get_db),
):
    item = db.get(InventarioItem, item_id)
    if not item:
        return RedirectResponse("/inventario", status_code=303)

    costo = Decimal(costo_unitario) if costo_unitario else None
    mov = MovimientoInventario(
        item_id=item_id,
        tipo=tipo,
        cantidad=cantidad,
        costo_unitario=costo,
        fecha=date.fromisoformat(fecha),
        notas=notas or None,
    )
    db.add(mov)

    if tipo == "entrada":
        nuevo_stock = item.stock_actual + cantidad
        if costo:
            # Weighted average cost
            total_valor = (item.stock_actual * item.costo_promedio) + (cantidad * costo)
            item.costo_promedio = total_valor / nuevo_stock if nuevo_stock else costo
        item.stock_actual = nuevo_stock
    elif tipo == "salida":
        item.stock_actual = max(Decimal("0"), item.stock_actual - cantidad)
    elif tipo == "ajuste":
        item.stock_actual = cantidad

    db.commit()
    return RedirectResponse("/inventario", status_code=303)
