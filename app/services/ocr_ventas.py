import base64
import json
from pathlib import Path

import anthropic

PROMPT = """Eres un asistente especializado en leer reportes de ventas y cierres de caja de un restaurante colombiano (Propósito by Patrono, gastrobar en Pereira).

Analiza el documento (puede ser una foto del cierre del POS, un reporte PDF, una planilla, etc.) y devuelve SOLO JSON válido (sin markdown, sin texto extra).

Si el reporte tiene UN turno o UN día → devuelve un objeto JSON.
Si el reporte tiene VARIOS turnos separados claramente → devuelve un arreglo [].

Estructura por turno/día:
{
  "fecha": "YYYY-MM-DD",
  "turno": "almuerzo|cena|dia_completo|desayuno|otro" (null si no se especifica),
  "total": número entero (total de ventas SIN propinas),
  "efectivo": número entero o 0,
  "tarjeta_debito": número entero o 0,
  "tarjeta_credito": número entero o 0,
  "transferencia": número entero o 0,
  "domicilio": número entero o 0,
  "propinas": número entero o 0,
  "num_transacciones": número entero o null,
  "num_clientes": número entero o null,
  "notas": "texto o null"
}

REGLAS:
- total = efectivo + tarjeta_debito + tarjeta_credito + transferencia + domicilio (SIN propinas)
- Las propinas van separadas en el campo "propinas"
- Las cifras son en pesos colombianos COP, enteros, sin puntos ni comas
- Si ves "Z report", "cierre de turno", "resumen de ventas" o similar, extrae los totales finales
- Si el documento no tiene datos de ventas claros, devuelve {"fecha": null, "total": 0, "notas": "no se pudo leer"}
- Fecha formato YYYY-MM-DD
"""

MEDIA_TYPES = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
               ".webp": "image/webp", ".heic": "image/jpeg", ".heif": "image/jpeg"}


def extract_venta(image_path: Path, api_key: str) -> dict | list:
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

    msg = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        messages=[{
            "role": "user",
            "content": [content_block, {"type": "text", "text": PROMPT}],
        }],
    )

    raw = msg.content[0].text.strip()
    if raw.startswith("```"):
        parts = raw.split("```")
        raw = parts[1].lstrip("json").strip() if len(parts) > 1 else raw
    return json.loads(raw)
