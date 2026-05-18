from datetime import date
from decimal import Decimal
from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Venta, Gasto, Categoria
from app.utils import primer_dia_mes

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
def index(request: Request, db: Session = Depends(get_db)):
    hoy = date.today()
    inicio_mes = primer_dia_mes(hoy)

    total_ventas_mes = db.query(func.coalesce(func.sum(Venta.total), 0)).filter(
        Venta.fecha >= inicio_mes
    ).scalar() or Decimal("0")

    total_gastos_mes = db.query(func.coalesce(func.sum(Gasto.total), 0)).filter(
        Gasto.fecha >= inicio_mes
    ).scalar() or Decimal("0")

    utilidad_mes = Decimal(total_ventas_mes) - Decimal(total_gastos_mes)

    ventas_recientes = db.query(Venta).order_by(Venta.fecha.desc(), Venta.id.desc()).limit(5).all()
    gastos_recientes = (
        db.query(Gasto).order_by(Gasto.fecha.desc(), Gasto.id.desc()).limit(5).all()
    )

    # Gastos por categoría del mes
    gastos_por_cat = (
        db.query(Categoria.nombre, func.coalesce(func.sum(Gasto.total), 0))
        .join(Gasto, Gasto.categoria_id == Categoria.id)
        .filter(Gasto.fecha >= inicio_mes)
        .group_by(Categoria.nombre)
        .order_by(func.sum(Gasto.total).desc())
        .all()
    )

    templates = request.app.state.templates
    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "total_ventas_mes": total_ventas_mes,
            "total_gastos_mes": total_gastos_mes,
            "utilidad_mes": utilidad_mes,
            "ventas_recientes": ventas_recientes,
            "gastos_recientes": gastos_recientes,
            "gastos_por_cat": gastos_por_cat,
            "hoy": hoy,
        },
    )
