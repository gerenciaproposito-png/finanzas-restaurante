import os
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL", "")

if DATABASE_URL:
    # Railway/cloud PostgreSQL — Railway usa "postgres://" pero SQLAlchemy necesita "postgresql://"
    if DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
    engine = create_engine(DATABASE_URL, echo=False, pool_pre_ping=True)
    IS_POSTGRES = True
else:
    DATA_DIR = Path(__file__).resolve().parent.parent / "data"
    DATA_DIR.mkdir(exist_ok=True)
    DB_PATH = DATA_DIR / "finanzas.db"
    engine = create_engine(
        f"sqlite:///{DB_PATH}",
        echo=False,
        connect_args={"check_same_thread": False},
    )
    IS_POSTGRES = False

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def _add_column(table: str, column: str, col_type: str, default: str | None = None) -> None:
    default_clause = f" DEFAULT {default}" if default is not None else ""
    try:
        with engine.connect() as conn:
            conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}{default_clause}"))
            conn.commit()
    except Exception:
        pass  # columna ya existe


def _seed_config(clave: str, valor: str) -> None:
    try:
        with engine.connect() as conn:
            if IS_POSTGRES:
                conn.execute(
                    text("INSERT INTO configuracion (clave, valor) VALUES (:c, :v) ON CONFLICT DO NOTHING"),
                    {"c": clave, "v": valor},
                )
            else:
                conn.execute(
                    text("INSERT OR IGNORE INTO configuracion (clave, valor) VALUES (:c, :v)"),
                    {"c": clave, "v": valor},
                )
            conn.commit()
    except Exception:
        pass


def run_migrations() -> None:
    _add_column("gastos", "descuento",       "NUMERIC(14,2)", "0")
    _add_column("gastos", "tipo_documento",  "VARCHAR(40)")
    _add_column("gastos", "medio_pago",      "VARCHAR(40)")
    _add_column("gastos", "estado_pago",     "VARCHAR(20)", "'pagado'")
    _add_column("ventas", "impoconsumo",     "NUMERIC(14,2)", "0")
    _add_column("ventas", "efectivo",        "NUMERIC(14,2)", "0")
    _add_column("ventas", "tarjeta_debito",  "NUMERIC(14,2)", "0")
    _add_column("ventas", "tarjeta_credito", "NUMERIC(14,2)", "0")
    _add_column("ventas", "transferencia",   "NUMERIC(14,2)", "0")
    _add_column("ventas", "domicilio",       "NUMERIC(14,2)", "0")
    _add_column("ventas", "metodo_pago",     "VARCHAR(30)")
    _add_column("ventas", "propinas",        "NUMERIC(14,2)", "0")
    _add_column("ventas", "notas",           "TEXT")
    _seed_config("ventas_folder_url", "https://drive.google.com/drive/folders/10xnBG1cle8qDiguchf4vUli1MhWw4u8v?usp=drive_link")
    _seed_config("ventas_folder_id",  "10xnBG1cle8qDiguchf4vUli1MhWw4u8v")
    _seed_config("ventas_productos_folder_id",  "")
    _seed_config("ventas_productos_folder_url", "")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
