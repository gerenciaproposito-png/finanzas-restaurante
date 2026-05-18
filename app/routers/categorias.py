from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Categoria

router = APIRouter(prefix="/categorias", tags=["categorias"])


@router.get("", response_class=HTMLResponse)
def listar(request: Request, db: Session = Depends(get_db)):
    categorias = db.query(Categoria).order_by(Categoria.tipo, Categoria.nombre).all()
    templates = request.app.state.templates
    return templates.TemplateResponse(
        "categorias/list.html", {"request": request, "categorias": categorias}
    )


@router.post("")
def crear(
    nombre: str = Form(...),
    tipo: str = Form(...),
    db: Session = Depends(get_db),
):
    db.add(Categoria(nombre=nombre, tipo=tipo))
    db.commit()
    return RedirectResponse("/categorias", status_code=303)


@router.post("/{categoria_id}/eliminar")
def eliminar(categoria_id: int, db: Session = Depends(get_db)):
    cat = db.get(Categoria, categoria_id)
    if cat:
        db.delete(cat)
        db.commit()
    return RedirectResponse("/categorias", status_code=303)
