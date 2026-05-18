from app.database import SessionLocal
from app.models import Categoria

CATEGORIAS_DEFAULT = [
    ("Insumos cocina", "gasto"),
    ("Bebidas y licores", "gasto"),
    ("Servicios públicos", "gasto"),
    ("Arriendo", "gasto"),
    ("Sueldos y nómina", "gasto"),
    ("Mantenimiento", "gasto"),
    ("Aseo y limpieza", "gasto"),
    ("Empaques y desechables", "gasto"),
    ("Impuestos y SIMPLE", "gasto"),
    ("Otros gastos", "gasto"),
    ("Ventas salón", "ingreso"),
    ("Ventas domicilio", "ingreso"),
    ("Otros ingresos", "ingreso"),
]


def seed_categorias() -> None:
    with SessionLocal() as db:
        if db.query(Categoria).count() > 0:
            return
        for nombre, tipo in CATEGORIAS_DEFAULT:
            db.add(Categoria(nombre=nombre, tipo=tipo))
        db.commit()
