from datetime import date
from decimal import Decimal


def cop(value: Decimal | float | int | None) -> str:
    """Formatea un número como pesos colombianos: $ 1.234.567"""
    if value is None:
        return "$ 0"
    n = Decimal(value)
    entero = int(n)
    decimales = abs(n - entero)
    formatted = f"{entero:,}".replace(",", ".")
    if decimales:
        cents = int(round(decimales * 100))
        return f"$ {formatted},{cents:02d}"
    return f"$ {formatted}"


def primer_dia_mes(d: date) -> date:
    return d.replace(day=1)


# Tarifa SIMPLE grupo 4 (expendio de comidas y bebidas) — vigente Colombia
# Rangos en UVT anuales. UVT 2026 estimada: $49.799 (usar valor configurable).
# Tarifas: 3.4% – 7%
TARIFA_SIMPLE_GRUPO4 = [
    (6000,  Decimal("0.034")),
    (15000, Decimal("0.038")),
    (30000, Decimal("0.054")),
    (100000, Decimal("0.070")),
]


def tarifa_simple(ingresos_uvt: Decimal) -> Decimal:
    """Devuelve la tarifa SIMPLE aplicable según ingresos brutos anuales en UVT."""
    for tope, tarifa in TARIFA_SIMPLE_GRUPO4:
        if ingresos_uvt <= tope:
            return tarifa
    return Decimal("0.070")
