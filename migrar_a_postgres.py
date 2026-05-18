"""
Migra todos los datos del SQLite local al PostgreSQL de Railway.

Uso:
  $env:DATABASE_URL = "postgresql://usuario:pass@host:5432/railway"
  .venv\Scripts\python.exe migrar_a_postgres.py
"""
import os
import sys
from pathlib import Path

DATABASE_URL = os.getenv("DATABASE_URL", "")
if not DATABASE_URL:
    print("ERROR: Define DATABASE_URL con la URL de PostgreSQL de Railway.")
    sys.exit(1)

if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

sys.path.insert(0, str(Path(__file__).parent))

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# Motor local SQLite
LOCAL_DB = Path(__file__).parent / "data" / "finanzas.db"
if not LOCAL_DB.exists():
    print(f"ERROR: No se encontró {LOCAL_DB}")
    sys.exit(1)

src_engine = create_engine(f"sqlite:///{LOCAL_DB}", connect_args={"check_same_thread": False})
dst_engine = create_engine(DATABASE_URL, pool_pre_ping=True)

# Crear tablas en PostgreSQL
from app.models import Base
Base.metadata.create_all(dst_engine)
print("✓ Tablas creadas en PostgreSQL")

# Tablas a migrar (en orden para respetar FK)
TABLES = [
    "categorias", "proveedores", "configuracion",
    "ventas", "gastos",
    "inventario_items", "movimientos_inventario",
    "empleados", "nomina",
    "catalogo_items", "precio_historial",
    "facturas_pendientes", "ventas_pendientes",
    "drive_sync_log",
]

SrcSession = sessionmaker(bind=src_engine)
DstSession = sessionmaker(bind=dst_engine)

total_rows = 0
with SrcSession() as src, DstSession() as dst:
    for table in TABLES:
        try:
            rows = src.execute(text(f"SELECT * FROM {table}")).mappings().all()
            if not rows:
                print(f"  {table}: vacío, omitido")
                continue
            # Limpiar destino y reinsertar
            dst.execute(text(f"DELETE FROM {table}"))
            dst.execute(text(f"INSERT INTO {table} ({', '.join(rows[0].keys())}) VALUES ({', '.join(':' + k for k in rows[0].keys())})"),
                        [dict(r) for r in rows])
            dst.commit()
            print(f"  ✓ {table}: {len(rows)} filas migradas")
            total_rows += len(rows)
        except Exception as e:
            print(f"  ✗ {table}: {e}")

print(f"\nMigración completada: {total_rows} filas en total.")
