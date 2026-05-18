from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import CatalogoItem, PrecioHistorial, Proveedor

router = APIRouter(prefix="/precios", tags=["precios"])


@router.get("", response_class=HTMLResponse)
def listar(request: Request, db: Session = Depends(get_db)):
    items = (
        db.query(CatalogoItem)
        .filter(CatalogoItem.activo == True)
        .order_by(CatalogoItem.nombre)
        .all()
    )

    # For each item: last price, min, max, count of observations
    stats = {}
    for item in items:
        rows = (
            db.query(
                PrecioHistorial.precio_unitario,
                PrecioHistorial.fecha,
                Proveedor.nombre.label("proveedor"),
            )
            .outerjoin(Proveedor, PrecioHistorial.proveedor_id == Proveedor.id)
            .filter(PrecioHistorial.item_id == item.id)
            .order_by(PrecioHistorial.fecha.desc())
            .all()
        )
        if rows:
            precios = [float(r.precio_unitario) for r in rows]
            stats[item.id] = {
                "ultimo": rows[0],
                "min": min(precios),
                "max": max(precios),
                "observaciones": len(rows),
                "historial": rows[:10],
            }
        else:
            stats[item.id] = None

    return request.app.state.templates.TemplateResponse("precios/list.html", {
        "request": request,
        "items": items,
        "stats": stats,
    })
