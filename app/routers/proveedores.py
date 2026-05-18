from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Proveedor

router = APIRouter(prefix="/proveedores", tags=["proveedores"])


@router.get("", response_class=HTMLResponse)
def listar(request: Request, db: Session = Depends(get_db)):
    proveedores = db.query(Proveedor).order_by(Proveedor.nombre).all()
    templates = request.app.state.templates
    return templates.TemplateResponse(
        "proveedores/list.html", {"request": request, "proveedores": proveedores}
    )


@router.post("")
def crear(
    nombre: str = Form(...),
    nit: str = Form(""),
    telefono: str = Form(""),
    notas: str = Form(""),
    db: Session = Depends(get_db),
):
    db.add(Proveedor(
        nombre=nombre,
        nit=nit or None,
        telefono=telefono or None,
        notas=notas or None,
    ))
    db.commit()
    return RedirectResponse("/proveedores", status_code=303)


@router.post("/{proveedor_id}/eliminar")
def eliminar(proveedor_id: int, db: Session = Depends(get_db)):
    prov = db.get(Proveedor, proveedor_id)
    if prov:
        db.delete(prov)
        db.commit()
    return RedirectResponse("/proveedores", status_code=303)
