import base64
import json
from pathlib import Path

import anthropic

PROMPT = """Eres un asistente especializado en leer facturas y recibos de un restaurante colombiano.
Analiza el documento y devuelve SOLO JSON válido (sin markdown, sin texto extra).

REGLA PRINCIPAL: Si el documento tiene UNA factura → devuelve un objeto JSON.
Si tiene VARIAS facturas (distinto número o distinta fecha) → devuelve un arreglo JSON [].

Estructura de cada factura:
{
  "proveedor": "nombre completo del proveedor",
  "nit_proveedor": "NIT sin puntos ni guiones, o null",
  "num_factura": "número de factura o null",
  "fecha": "YYYY-MM-DD o null",
  "items": [
    {
      "nombre": "nombre completo del producto",
      "cantidad": 1.0,
      "unidad": "kg/und/lt/caja/bolsa/g/ml",
      "precio_unitario": 0,
      "descuento_unitario": 0,
      "subtotal": 0
    }
  ],
  "descuento_total": 0,
  "subtotal": 0,
  "iva": 0,
  "total": 0,
  "notas": null
}

REGLAS CRÍTICAS PARA PRECIOS (léelas con atención):

1. precio_unitario = precio por unidad ANTES de descuento, SIN IVA.
2. descuento_unitario = descuento aplicado a ese ítem (ej: "Tu Ahorro" en Makro). 0 si no hay.
3. subtotal = (precio_unitario - descuento_unitario) × cantidad. Es el valor NETO pagado por ese ítem.
4. descuento_total = suma de todos los descuentos (ej: campo "Tu Ahorro" global, o suma de descuentos por ítem).
5. subtotal (nivel factura) = suma de subtotales de ítems = total sin IVA y con descuentos.
6. iva = IVA + impoconsumo (ICO) + cualquier impuesto adicional. Si aparece retención, NO restarla.
7. total = valor TOTAL FINAL PAGADO. Debe cumplir: total ≈ subtotal + iva.

CASOS ESPECIALES:
- Makro, Panamericana, PriceSmart: muestran "Tu Ahorro" por ítem. Extráelo en descuento_unitario.
  El subtotal del ítem es el precio neto (ya con descuento). El total al final del ticket es el correcto.
- Postobon, licores: precios por ítem SIN IVA. El IVA aparece al final. subtotal = precio sin IVA.
- Recibos de caja menor / pagos de nómina / arriendos: no tienen ítems. Pon items=[], y el total pagado.
- Si no puedes leer algún ítem, omítelo y anótalo en notas.
- Todos los valores son enteros en COP (sin decimales, sin puntos de miles, sin comas).

VALIDACIÓN INTERNA (antes de responder): suma de item.subtotal ≈ subtotal de factura.
subtotal + iva ≈ total. Si no cuadra, revisa y corrige.
"""

MEDIA_TYPES = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
               ".webp": "image/webp", ".heic": "image/jpeg", ".heif": "image/jpeg"}


def extract_invoice(image_path: Path, api_key: str, hint: str = "") -> dict:
    suffix = image_path.suffix.lower()
    file_data = base64.standard_b64encode(image_path.read_bytes()).decode("utf-8")

    client = anthropic.Anthropic(api_key=api_key)

    if suffix == ".pdf":
        content_block = {
            "type": "document",
            "source": {"type": "base64", "media_type": "application/pdf", "data": file_data},
        }
    else:
        media_type = MEDIA_TYPES.get(suffix, "image/jpeg")
        content_block = {
            "type": "image",
            "source": {"type": "base64", "media_type": media_type, "data": file_data},
        }

    prompt = PROMPT
    if hint and hint.strip():
        prompt += f"\n\n⚠️ CORRECCIÓN DEL USUARIO (máxima prioridad, úsala para corregir tu extracción):\n{hint.strip()}"

    msg = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=2048,
        messages=[{
            "role": "user",
            "content": [content_block, {"type": "text", "text": prompt}],
        }],
    )

    raw = msg.content[0].text.strip()
    if raw.startswith("```"):
        parts = raw.split("```")
        raw = parts[1].lstrip("json").strip() if len(parts) > 1 else raw
    return json.loads(raw)
