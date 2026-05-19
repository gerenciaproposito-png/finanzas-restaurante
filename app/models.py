from datetime import date, datetime
from decimal import Decimal
from sqlalchemy import String, Integer, Date, DateTime, Numeric, ForeignKey, Text, Boolean
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Categoria(Base):
    __tablename__ = "categorias"
    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(100), unique=True)
    tipo: Mapped[str] = mapped_column(String(20))


class Proveedor(Base):
    __tablename__ = "proveedores"
    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(150))
    nit: Mapped[str | None] = mapped_column(String(20), nullable=True)
    telefono: Mapped[str | None] = mapped_column(String(30), nullable=True)
    notas: Mapped[str | None] = mapped_column(Text, nullable=True)


class Venta(Base):
    __tablename__ = "ventas"
    id: Mapped[int] = mapped_column(primary_key=True)
    fecha: Mapped[date] = mapped_column(Date, index=True)
    turno: Mapped[str | None] = mapped_column(String(20), nullable=True)
    total: Mapped[Decimal] = mapped_column(Numeric(14, 2))           # ventas sin propinas (neta + impoconsumo)
    impoconsumo: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"))
    efectivo: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"))
    tarjeta_debito: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"))
    tarjeta_credito: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"))
    transferencia: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"))
    domicilio: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"))
    metodo_pago: Mapped[str | None] = mapped_column(String(30), nullable=True)
    propinas: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"))
    notas: Mapped[str | None] = mapped_column(Text, nullable=True)
    creado: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class Gasto(Base):
    __tablename__ = "gastos"
    id: Mapped[int] = mapped_column(primary_key=True)
    fecha: Mapped[date] = mapped_column(Date, index=True)
    proveedor_id: Mapped[int | None] = mapped_column(ForeignKey("proveedores.id"), nullable=True)
    categoria_id: Mapped[int | None] = mapped_column(ForeignKey("categorias.id"), nullable=True)
    descripcion: Mapped[str | None] = mapped_column(String(255), nullable=True)
    subtotal: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    descuento: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"))
    iva: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"))
    total: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    num_factura: Mapped[str | None] = mapped_column(String(50), nullable=True)
    tipo_documento: Mapped[str | None] = mapped_column(String(40), nullable=True)   # factura_e, factura_papel, ticket, recibo, sin_soporte
    medio_pago: Mapped[str | None] = mapped_column(String(40), nullable=True)       # efectivo, transferencia, tarjeta_debito, tarjeta_credito, credito_proveedor
    estado_pago: Mapped[str] = mapped_column(String(20), default="pagado")          # pagado, pendiente, credito
    archivo_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    notas: Mapped[str | None] = mapped_column(Text, nullable=True)
    creado: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    proveedor: Mapped["Proveedor | None"] = relationship()
    categoria: Mapped["Categoria | None"] = relationship()


class InventarioItem(Base):
    __tablename__ = "inventario_items"
    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(150), unique=True)
    unidad: Mapped[str] = mapped_column(String(20))
    stock_actual: Mapped[Decimal] = mapped_column(Numeric(14, 3), default=Decimal("0"))
    costo_promedio: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"))
    stock_minimo: Mapped[Decimal | None] = mapped_column(Numeric(14, 3), nullable=True)


class MovimientoInventario(Base):
    __tablename__ = "movimientos_inventario"
    id: Mapped[int] = mapped_column(primary_key=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("inventario_items.id"))
    fecha: Mapped[date] = mapped_column(Date)
    tipo: Mapped[str] = mapped_column(String(20))
    cantidad: Mapped[Decimal] = mapped_column(Numeric(14, 3))
    costo_unitario: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    gasto_id: Mapped[int | None] = mapped_column(ForeignKey("gastos.id"), nullable=True)
    notas: Mapped[str | None] = mapped_column(Text, nullable=True)

    item: Mapped["InventarioItem"] = relationship()


class Empleado(Base):
    __tablename__ = "empleados"
    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(150))
    cedula: Mapped[str | None] = mapped_column(String(20), nullable=True)
    cargo: Mapped[str | None] = mapped_column(String(80), nullable=True)
    sueldo_base: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"))
    tipo_contrato: Mapped[str | None] = mapped_column(String(40), nullable=True)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)


class Nomina(Base):
    __tablename__ = "nomina"
    id: Mapped[int] = mapped_column(primary_key=True)
    empleado_id: Mapped[int] = mapped_column(ForeignKey("empleados.id"))
    fecha_inicio: Mapped[date] = mapped_column(Date)
    fecha_fin: Mapped[date] = mapped_column(Date)
    dias_trabajados: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sueldo: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    propinas: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"))
    deducciones: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"))
    neto_pagado: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    notas: Mapped[str | None] = mapped_column(Text, nullable=True)

    empleado: Mapped["Empleado"] = relationship()


# ── Drive sync & price tracking ──────────────────────────────────────────────

class Configuracion(Base):
    __tablename__ = "configuracion"
    clave: Mapped[str] = mapped_column(String(100), primary_key=True)
    valor: Mapped[str | None] = mapped_column(Text, nullable=True)


class CatalogoItem(Base):
    __tablename__ = "catalogo_items"
    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(200), unique=True)
    unidad: Mapped[str | None] = mapped_column(String(20), nullable=True)
    categoria_id: Mapped[int | None] = mapped_column(ForeignKey("categorias.id"), nullable=True)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)

    categoria: Mapped["Categoria | None"] = relationship()


class PrecioHistorial(Base):
    __tablename__ = "precio_historial"
    id: Mapped[int] = mapped_column(primary_key=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("catalogo_items.id"), index=True)
    proveedor_id: Mapped[int | None] = mapped_column(ForeignKey("proveedores.id"), nullable=True)
    fecha: Mapped[date] = mapped_column(Date, index=True)
    precio_unitario: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    cantidad: Mapped[Decimal | None] = mapped_column(Numeric(14, 3), nullable=True)
    unidad: Mapped[str | None] = mapped_column(String(20), nullable=True)
    gasto_id: Mapped[int | None] = mapped_column(ForeignKey("gastos.id"), nullable=True)

    item: Mapped["CatalogoItem"] = relationship()
    proveedor: Mapped["Proveedor | None"] = relationship()


class VentaPendiente(Base):
    __tablename__ = "ventas_pendientes"
    id: Mapped[int] = mapped_column(primary_key=True)
    drive_file_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    nombre_archivo: Mapped[str] = mapped_column(String(500))
    archivo_local: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    datos_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    fecha_sync: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    estado: Mapped[str] = mapped_column(String(20), default="pendiente")  # pendiente, confirmado, descartado
    venta_id: Mapped[int | None] = mapped_column(ForeignKey("ventas.id"), nullable=True)


class DriveSyncLog(Base):
    __tablename__ = "drive_sync_log"
    id: Mapped[int] = mapped_column(primary_key=True)
    drive_file_id: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    nombre: Mapped[str] = mapped_column(String(500))
    fecha_sync: Mapped[datetime] = mapped_column(DateTime)
    estado: Mapped[str] = mapped_column(String(20))  # procesado, error
    error: Mapped[str | None] = mapped_column(Text, nullable=True)


class FacturaPendiente(Base):
    __tablename__ = "facturas_pendientes"
    id: Mapped[int] = mapped_column(primary_key=True)
    drive_file_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    nombre_archivo: Mapped[str] = mapped_column(String(500))
    archivo_local: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    datos_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    fecha_sync: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    estado: Mapped[str] = mapped_column(String(20), default="pendiente")  # pendiente, confirmado, descartado
    gasto_id: Mapped[int | None] = mapped_column(ForeignKey("gastos.id"), nullable=True)


class VentaProducto(Base):
    __tablename__ = "ventas_productos"
    id: Mapped[int] = mapped_column(primary_key=True)
    fecha_corte: Mapped[date] = mapped_column(Date, index=True)
    negocio: Mapped[str | None] = mapped_column(String(150), nullable=True)
    categoria: Mapped[str] = mapped_column(String(150), index=True)
    producto: Mapped[str] = mapped_column(String(300))
    cantidad: Mapped[int] = mapped_column(Integer)
    total: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    fuente: Mapped[str | None] = mapped_column(String(50), nullable=True)  # upload, drive
    importado: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
