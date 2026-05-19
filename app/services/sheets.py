"""Write-back to a destination Google Sheet.

Each domain (gastos / ventas / ventas por producto) writes to its own tab.
The tab is auto-created with a header row the first time we touch it.
"""
import re
from googleapiclient.discovery import build

from app.services import drive as _drive


TAB_GASTOS = "Facturas"
TAB_VENTAS = "Ventas"
TAB_VENTAS_PRODUCTOS = "Ventas por producto"

HEADERS = {
    TAB_GASTOS: [
        "gasto_id", "fecha", "proveedor", "nit", "num_factura",
        "tipo_documento", "medio_pago", "estado_pago",
        "subtotal", "descuento", "iva", "total", "notas",
    ],
    TAB_VENTAS: [
        "venta_id", "fecha", "turno", "total", "impoconsumo",
        "efectivo", "tarjeta_debito", "tarjeta_credito", "transferencia", "domicilio",
        "propinas", "metodo_pago", "notas",
    ],
    TAB_VENTAS_PRODUCTOS: [
        "venta_producto_id", "fecha_corte", "negocio", "categoria",
        "producto", "cantidad", "total", "fuente",
    ],
}


def extract_sheet_id(url_or_id: str) -> str:
    """Accept either a full Sheets URL or a bare ID; return the ID."""
    s = (url_or_id or "").strip()
    if not s:
        return ""
    m = re.search(r"/spreadsheets/d/([a-zA-Z0-9_-]+)", s)
    if m:
        return m.group(1)
    return s


def _service():
    creds = _drive.get_credentials()
    if not creds:
        return None
    return build("sheets", "v4", credentials=creds, cache_discovery=False)


def is_configured(sheet_id: str | None) -> bool:
    return bool(sheet_id and _drive.is_connected())


def _ensure_tab(svc, sheet_id: str, tab: str) -> None:
    """Create the tab + write the header row if it doesn't exist yet."""
    meta = svc.spreadsheets().get(spreadsheetId=sheet_id, fields="sheets(properties(title))").execute()
    titles = {s["properties"]["title"] for s in meta.get("sheets", [])}
    if tab in titles:
        return

    svc.spreadsheets().batchUpdate(
        spreadsheetId=sheet_id,
        body={"requests": [{"addSheet": {"properties": {"title": tab}}}]},
    ).execute()

    header = HEADERS.get(tab, [])
    if header:
        svc.spreadsheets().values().update(
            spreadsheetId=sheet_id,
            range=f"'{tab}'!A1",
            valueInputOption="RAW",
            body={"values": [header]},
        ).execute()


def append_rows(sheet_id: str, tab: str, rows: list[list]) -> None:
    """Append rows to the given tab, creating it if needed."""
    if not rows:
        return
    svc = _service()
    if not svc:
        raise RuntimeError("Google no está conectado o el token no incluye permiso de Sheets")
    _ensure_tab(svc, sheet_id, tab)
    svc.spreadsheets().values().append(
        spreadsheetId=sheet_id,
        range=f"'{tab}'!A1",
        valueInputOption="USER_ENTERED",
        insertDataOption="INSERT_ROWS",
        body={"values": rows},
    ).execute()
