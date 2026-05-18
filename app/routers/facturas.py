import json
from datetime import date
from decimal import Decimal
from pathlib import Path

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import (
    CatalogoItem, FacturaPendiente, Gasto, InventarioItem,
    MovimientoInventario, PrecioHistorial, Proveedor
)

router = APIRouter(prefix="/facturas", tags=["facturas"])


def _get_or_create_proveedor(db: Session, nombre: str, nit: str | None) -> Proveedor | None:
    if not nombre or not nombre.strip():
        return None
    prov = db.query(Proveedor).filter(Proveedor.nombre.ilike(nombre.strip())).first()
    if not prov:
        prov = Proveedor(nombre=nombre.strip(), nit=nit or None)
        db.add(prov)
        db.flush()
    elif nit and not prov.nit:
        prov.nit = nit
    return prov


def _ingresar_inventario(
    db: Session,
    nombre: str,
    cantidad: Decimal,
    precio_neto: Decimal,
    unidad: str | None,
    fecha: date,
    gasto_id: int,
) -> None:
    """Crea o actualiza el InventarioItem y registra el movimiento de entrada."""
    if cantidad <= 0:
        return

    inv = db.query(InventarioItem).filter(
        InventarioItem.nombre.ilike(nombre.strip())
    ).first()

    if not inv:
        inv = InventarioItem(
            nombre=nombre.strip(),
            unidad=unidad or "und",
            stock_actual=Decimal("0"),
            costo_promedio=precio_neto if precio_neto > 0 else Decimal("0"),
        )
        db.add(inv)
        db.flush()

    # Costo promedio ponderado
    if precio_neto > 0:
        old_stock = inv.stock_actual or Decimal("0")
        old_costo = inv.costo_promedio or Decimal("0")
        nueva_stock = old_stock + cantidad
        if nueva_stock > 0:
            inv.costo_promedio = (
                (old_stock * old_costo + cantidad * precio_neto) / nueva_stock
            ).quantize(Decimal("0.01"))

    inv.stock_actual = (inv.stock_actual or Decimal("0")) + cantidad

    db.add(MovimientoInventario(
        item_id=inv.id,
        fecha=fecha,
        tipo="entrada",
        cantidad=cantidad,
        costo_unitario=precio_neto if precio_neto > 0 else None,
        gasto_id=gasto_id,
    ))


def _get_or_create_item(db: Session, nombre: str, unidad: str | None) -> CatalogoItem:
    item = db.query(CatalogoItem).filter(CatalogoItem.nombre.ilike(nombre.strip())).first()
    if not item:
        item = CatalogoItem(nombre=nombre.strip(), unidad=unidad)
        db.add(item)
        db.flush()
    return item


@router.get("", response_class=HTMLResponse)
def listar(request: Request, db: Session = Depends(get_db)):
    pendientes = (
        db.query(FacturaPendiente)
        .filter(FacturaPendiente.estado == "pendiente")
        .order_by(FacturaPendiente.fecha_sync.desc())
        .all()
    )
    return request.app.state.templates.TemplateResponse(
        "facturas/list.html", {"request": request, "pendientes": pendientes}
    )


@router.get("/{factura_id}/revisar", response_class=HTMLResponse)
def revisar(factura_id: int, request: Request, db: Session = Depends(get_db)):
    factura = db.get(FacturaPendiente, factura_id)
    if not factura:
        return RedirectResponse("/facturas")

    raw = json.loads(factura.datos_json) if factura.datos_json else {}

    if isinstance(raw, list) and len(raw) > 1:
        # Multi-invoice: show split UI instead of combining.
        # Pre-compute item_count to avoid Jinja2 resolving inv.items → dict.items() method.
        invoices = [
            {**inv, "item_count": len(inv.get("items", []))}
            for inv in raw if isinstance(inv, dict)
        ]
        datos = raw[0]
        items = datos.get("items", [])
        multi_invoice = True
        invoice_count = len(raw)
    else:
        invoices = []
        datos = raw[0] if isinstance(raw, list) else raw
        items = datos.get("items", []) if isinstance(datos, dict) else []
        multi_invoice = False
        invoice_count = 1

    imagen_url = None
    if factura.archivo_local:
        p = Path(factura.archivo_local)
        if p.exists():
            imagen_url = f"/uploads/facturas/{p.name}"

    is_pdf = bool(factura.nombre_archivo and factura.nombre_archivo.lower().endswith(".pdf"))

    return request.app.state.templates.TemplateResponse("facturas/revisar.html", {
        "request": request,
        "factura": factura,
        "datos": datos,
        "imagen_url": imagen_url,
        "is_pdf": is_pdf,
        "items": items,
        "hoy": date.today().isoformat(),
        "multi_invoice": multi_invoice,
        "invoice_count": invoice_count,
        "invoices": invoices,
    })


@router.post("/{factura_id}/confirmar")
async def confirmar(
    factura_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    factura = db.get(FacturaPendiente, factura_id)
    if not factura:
        return RedirectResponse("/facturas", status_code=303)

    form = await request.form()

    fecha_str = form.get("fecha") or date.today().isoformat()
    fecha = date.fromisoformat(fecha_str)
    proveedor_nombre = form.get("proveedor", "")
    nit = form.get("nit_proveedor", "")
    num_factura = form.get("num_factura", "")
    total_str = form.get("total", "0")
    subtotal_str = form.get("subtotal", "0")
    iva_str = form.get("iva", "0")
    descuento_str = form.get("descuento", "0")
    notas = form.get("notas", "")
    tipo_documento = form.get("tipo_documento", "") or None
    medio_pago = form.get("medio_pago", "") or None
    estado_pago = form.get("estado_pago", "pagado") or "pagado"

    total = Decimal(total_str or "0")
    subtotal = Decimal(subtotal_str or "0")
    iva = Decimal(iva_str or "0")
    descuento = Decimal(descuento_str or "0")

    proveedor = _get_or_create_proveedor(db, proveedor_nombre, nit or None)

    gasto = Gasto(
        fecha=fecha,
        proveedor_id=proveedor.id if proveedor else None,
        descripcion=f"Factura {num_factura}" if num_factura else "Factura importada de Drive",
        subtotal=subtotal,
        descuento=descuento,
        iva=iva,
        total=total,
        num_factura=num_factura or None,
        tipo_documento=tipo_documento,
        medio_pago=medio_pago,
        estado_pago=estado_pago,
        notas=notas or None,
    )
    db.add(gasto)
    db.flush()

    # Items de precio
    nombres    = form.getlist("item_nombre")
    cantidades = form.getlist("item_cantidad")
    unidades   = form.getlist("item_unidad")
    precios    = form.getlist("item_precio_unitario")
    descuentos = form.getlist("item_descuento_unitario")

    for nombre, cant_s, unidad, precio_s, desc_s in zip(
        nombres, cantidades, unidades, precios,
        descuentos + ["0"] * len(nombres)   # padding si faltan
    ):
        if not nombre or not nombre.strip():
            continue
        try:
            precio_bruto = Decimal(precio_s or "0")
            desc_unit    = Decimal(desc_s or "0")
            precio_neto  = precio_bruto - desc_unit   # lo que realmente se pagó
            cantidad     = Decimal(cant_s or "1")
        except Exception:
            continue

        item = _get_or_create_item(db, nombre, unidad or None)
        db.add(PrecioHistorial(
            item_id=item.id,
            proveedor_id=proveedor.id if proveedor else None,
            fecha=fecha,
            precio_unitario=precio_neto,
            cantidad=cantidad,
            unidad=unidad or item.unidad,
            gasto_id=gasto.id,
        ))

        _ingresar_inventario(db, nombre, cantidad, precio_neto, unidad or None, fecha, gasto.id)

    factura.estado = "confirmado"
    factura.gasto_id = gasto.id
    db.commit()
    return RedirectResponse("/facturas", status_code=303)


@router.post("/{factura_id}/reprocesar")
async def reprocesar(factura_id: int, request: Request, db: Session = Depends(get_db)):
    factura = db.get(FacturaPendiente, factura_id)
    if not factura or not factura.archivo_local:
        return RedirectResponse("/facturas", status_code=303)

    form = await request.form()
    hint = (form.get("hint") or "").strip()

    cfg = db.get(__import__("app.models", fromlist=["Configuracion"]).Configuracion, "anthropic_api_key")
    api_key = cfg.valor if cfg else None
    if not api_key:
        return RedirectResponse(f"/facturas/{factura_id}/revisar?err=sin_api_key", status_code=303)

    from pathlib import Path as _Path
    from app.services.ocr import extract_invoice
    import json as _json

    try:
        datos = extract_invoice(_Path(factura.archivo_local), api_key, hint=hint)
        factura.datos_json = _json.dumps(datos, ensure_ascii=False)
        db.commit()
    except Exception as e:
        return RedirectResponse(f"/facturas/{factura_id}/revisar?err={str(e)[:80]}", status_code=303)

    return RedirectResponse(f"/facturas/{factura_id}/revisar", status_code=303)


@router.post("/{factura_id}/dividir")
def dividir(factura_id: int, db: Session = Depends(get_db)):
    """Splits a multi-invoice PDF into one FacturaPendiente per detected invoice."""
    factura = db.get(FacturaPendiente, factura_id)
    if not factura or not factura.datos_json:
        return RedirectResponse("/facturas", status_code=303)

    raw = json.loads(factura.datos_json)
    if not isinstance(raw, list) or len(raw) < 2:
        return RedirectResponse(f"/facturas/{factura_id}/revisar", status_code=303)

    for i, inv in enumerate(raw, start=1):
        nombre_base = factura.nombre_archivo.rsplit(".", 1)
        nombre = f"{nombre_base[0]} — parte {i}.{nombre_base[1]}" if len(nombre_base) == 2 else f"{factura.nombre_archivo} — parte {i}"
        db.add(FacturaPendiente(
            drive_file_id=None,
            nombre_archivo=nombre,
            archivo_local=factura.archivo_local,
            datos_json=json.dumps(inv if isinstance(inv, dict) else {}, ensure_ascii=False),
            estado="pendiente",
        ))

    factura.estado = "descartado"
    db.commit()
    return RedirectResponse("/facturas", status_code=303)


@router.post("/{factura_id}/descartar")
def descartar(factura_id: int, db: Session = Depends(get_db)):
    factura = db.get(FacturaPendiente, factura_id)
    if factura:
        factura.estado = "descartado"
        db.commit()
    return RedirectResponse("/facturas", status_code=303)
