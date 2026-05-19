"""Push confirmed records (Gastos, Ventas, VentasProducto) to a Google Sheet.

Dedup is enforced by SheetsSyncLog (tipo, entidad_id) — once a row is logged
"ok" for a (tipo, entidad_id), it is never sent again.
"""
from datetime import datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models import (
    Configuracion, Gasto, Proveedor, SheetsSyncLog, Venta, VentaProducto,
)
from app.services import sheets


def _get_sheet_id(db: Session) -> str:
    cfg = db.get(Configuracion, "sheets_destino_id")
    return cfg.valor if cfg and cfg.valor else ""


def _d(v) -> float:
    if v is None:
        return 0.0
    if isinstance(v, Decimal):
        return float(v)
    try:
        return float(v)
    except Exception:
        return 0.0


def _already_synced_ids(db: Session, tipo: str) -> set[int]:
    rows = db.query(SheetsSyncLog.entidad_id).filter(
        SheetsSyncLog.tipo == tipo,
        SheetsSyncLog.estado == "ok",
    ).all()
    return {r[0] for r in rows}


def _row_gasto(g: Gasto, proveedor_nombre: str, proveedor_nit: str) -> list:
    return [
        g.id,
        g.fecha.isoformat() if g.fecha else "",
        proveedor_nombre or "",
        proveedor_nit or "",
        g.num_factura or "",
        g.tipo_documento or "",
        g.medio_pago or "",
        g.estado_pago or "",
        _d(g.subtotal),
        _d(g.descuento),
        _d(g.iva),
        _d(g.total),
        g.notas or "",
    ]


def _row_venta(v: Venta) -> list:
    return [
        v.id,
        v.fecha.isoformat() if v.fecha else "",
        v.turno or "",
        _d(v.total),
        _d(v.impoconsumo),
        _d(v.efectivo),
        _d(v.tarjeta_debito),
        _d(v.tarjeta_credito),
        _d(v.transferencia),
        _d(v.domicilio),
        _d(v.propinas),
        v.metodo_pago or "",
        v.notas or "",
    ]


def _row_vp(vp: VentaProducto) -> list:
    return [
        vp.id,
        vp.fecha_corte.isoformat() if vp.fecha_corte else "",
        vp.negocio or "",
        vp.categoria or "",
        vp.producto or "",
        vp.cantidad or 0,
        _d(vp.total),
        vp.fuente or "",
    ]


def _log(db: Session, tipo: str, entidad_id: int, sheet_id: str, tab: str,
         estado: str = "ok", error: str | None = None) -> None:
    db.add(SheetsSyncLog(
        tipo=tipo,
        entidad_id=entidad_id,
        sheet_id=sheet_id,
        tab=tab,
        fecha_sync=datetime.now(),
        estado=estado,
        error=error,
    ))


def push_pending(db: Session) -> dict:
    """Push everything not yet synced. Returns counts per tipo."""
    stats = {"gastos": 0, "ventas": 0, "ventas_productos": 0, "errores": 0}

    sheet_id = _get_sheet_id(db)
    if not sheets.is_configured(sheet_id):
        return stats

    # Gastos
    synced = _already_synced_ids(db, "gasto")
    gastos = db.query(Gasto).filter(~Gasto.id.in_(synced) if synced else True).all()
    if gastos:
        prov_ids = {g.proveedor_id for g in gastos if g.proveedor_id}
        provs = {p.id: p for p in db.query(Proveedor).filter(Proveedor.id.in_(prov_ids)).all()} if prov_ids else {}
        rows = []
        for g in gastos:
            p = provs.get(g.proveedor_id) if g.proveedor_id else None
            rows.append(_row_gasto(g, p.nombre if p else "", p.nit if p else ""))
        try:
            sheets.append_rows(sheet_id, sheets.TAB_GASTOS, rows)
            for g in gastos:
                _log(db, "gasto", g.id, sheet_id, sheets.TAB_GASTOS)
            stats["gastos"] = len(gastos)
        except Exception as e:
            for g in gastos:
                _log(db, "gasto", g.id, sheet_id, sheets.TAB_GASTOS, "error", str(e)[:500])
            stats["errores"] += 1

    # Ventas
    synced = _already_synced_ids(db, "venta")
    ventas = db.query(Venta).filter(~Venta.id.in_(synced) if synced else True).all()
    if ventas:
        rows = [_row_venta(v) for v in ventas]
        try:
            sheets.append_rows(sheet_id, sheets.TAB_VENTAS, rows)
            for v in ventas:
                _log(db, "venta", v.id, sheet_id, sheets.TAB_VENTAS)
            stats["ventas"] = len(ventas)
        except Exception as e:
            for v in ventas:
                _log(db, "venta", v.id, sheet_id, sheets.TAB_VENTAS, "error", str(e)[:500])
            stats["errores"] += 1

    # Ventas por producto
    synced = _already_synced_ids(db, "venta_producto")
    vps = db.query(VentaProducto).filter(~VentaProducto.id.in_(synced) if synced else True).all()
    if vps:
        # Push in chunks to avoid huge requests
        CHUNK = 500
        ok_ids: list[int] = []
        try:
            for i in range(0, len(vps), CHUNK):
                batch = vps[i:i + CHUNK]
                sheets.append_rows(sheet_id, sheets.TAB_VENTAS_PRODUCTOS, [_row_vp(x) for x in batch])
                ok_ids.extend(x.id for x in batch)
            for vid in ok_ids:
                _log(db, "venta_producto", vid, sheet_id, sheets.TAB_VENTAS_PRODUCTOS)
            stats["ventas_productos"] = len(ok_ids)
        except Exception as e:
            for vid in ok_ids:
                _log(db, "venta_producto", vid, sheet_id, sheets.TAB_VENTAS_PRODUCTOS)
            for vp in vps[len(ok_ids):]:
                _log(db, "venta_producto", vp.id, sheet_id, sheets.TAB_VENTAS_PRODUCTOS, "error", str(e)[:500])
            stats["errores"] += 1

    db.commit()
    return stats
