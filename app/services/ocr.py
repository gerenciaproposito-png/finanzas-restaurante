import base64
import json
from pathlib import Path

import anthropic

PROMPT = """Eres un asistente experto en leer facturas y recibos de proveedores de un restaurante colombiano (gastrobar en Pereira).

Analiza el documento y devuelve SOLO JSON válido — sin markdown, sin texto adicional, sin ```.

═══════════════════════════════════════════════════
REGLA #1 — UNA FACTURA vs VARIAS FACTURAS
═══════════════════════════════════════════════════

Si el documento tiene **UNA** factura → devuelve un OBJETO JSON `{}`.
Si tiene **VARIAS** facturas (distinto número, distinta fecha, o claramente separadas por sello/firma/cuenta cerrada) → devuelve un ARREGLO `[ {}, {}, {} ]`.

Señales de "factura nueva" dentro del mismo PDF:
  • Nuevo encabezado con logo/NIT del proveedor.
  • Distinto "N° Factura", "Orden" o "Pedido".
  • Distinta fecha.
  • Línea de "Cuenta cerrada", "ACEPTADA", o un sello/firma de recepción.
  • Recibos térmicos largos suelen ser **una factura por hoja**.

═══════════════════════════════════════════════════
REGLA #2 — ESTRUCTURA DE CADA FACTURA
═══════════════════════════════════════════════════

{
  "proveedor": "Razón social completa del que VENDE (no el que compra). En tickets térmicos suele estar en el encabezado arriba del NIT.",
  "nit_proveedor": "NIT del vendedor, sin puntos ni guiones, sin dígito de verificación. Ej: 900665499. Null si no aparece.",
  "num_factura": "Número de factura exactamente como aparece. Ej: H69E-77622, ESFE179323, 1880412233. Null si no.",
  "fecha": "YYYY-MM-DD. Si solo ves DD/MM/AAAA, conviértelo. Null si no.",
  "tipo_documento": "factura_e | factura_papel | ticket | recibo | sin_soporte",
  "items": [
    {
      "nombre": "Nombre del producto LIMPIO Y COMPLETO — ver Regla #3.",
      "cantidad": 1.0,
      "unidad": "und | kg | g | lt | ml | caja | bolsa | bot | btc | docena",
      "cantidad_empaque": 0,
      "unidad_empaque": "g | ml | kg | lt | und | null",
      "precio_unitario": 0,
      "descuento_unitario": 0,
      "subtotal": 0,
      "iva_porcentaje": 0,
      "impoconsumo_porcentaje": 0
    }
  ],
  "descuento_total": 0,
  "subtotal": 0,
  "iva": 0,
  "impoconsumo": 0,
  "total": 0,
  "notas": null,
  "notas_revision": null
}

═══════════════════════════════════════════════════
REGLA #3 — NOMBRE DEL PRODUCTO (LO MÁS IMPORTANTE)
═══════════════════════════════════════════════════

3.1 — **NOMBRES PARTIDOS EN VARIAS LÍNEAS**: en tickets térmicos angostos el nombre suele cortarse. Pégalos.
   Texto en la factura:
     `6 UN (130082) Miso Shiro Naru   $ 154,800`
     `             kome 1 kg`
   Resultado correcto:
     nombre = "Miso Shiro Naru kome"
     cantidad = 6, unidad = "UN"
     cantidad_empaque = 1000, unidad_empaque = "g"   (porque "1 kg" es el empaque)

   Texto:
     `4 UN (130021) Bisque de Lango   $ 540,000`
     `             sta 1500 g`
   Resultado:
     nombre = "Bisque de Langosta"
     cantidad_empaque = 1500, unidad_empaque = "g"

   Texto:
     `30 UN (210065) Mayonesa Japone $ 480,000`
     `              sa Ajinomoto 400 g`
   Resultado:
     nombre = "Mayonesa Japonesa Ajinomoto"
     cantidad_empaque = 400, unidad_empaque = "g"

3.2 — **NO incluyas códigos internos** (números entre paréntesis tipo `(130082)`) ni precios en el nombre.

3.3 — **NO incluyas el peso/volumen del empaque en el nombre**: sácalo a `cantidad_empaque` / `unidad_empaque`.

═══════════════════════════════════════════════════
REGLA #4 — EMPAQUE (CRÍTICO para costeo)
═══════════════════════════════════════════════════

Cada ítem debe traer cuánto contiene **una unidad del empaque vendido**, normalizado:

  • "1 kg"   → cantidad_empaque = 1000,  unidad_empaque = "g"
  • "500 g"  → cantidad_empaque = 500,   unidad_empaque = "g"
  • "1500 g" → cantidad_empaque = 1500,  unidad_empaque = "g"
  • "1 lt"   → cantidad_empaque = 1000,  unidad_empaque = "ml"
  • "750 ml" → cantidad_empaque = 750,   unidad_empaque = "ml"
  • "400 g"  → cantidad_empaque = 400,   unidad_empaque = "g"

Si NO aparece peso/volumen (ej. "Bolsa Plástica", "Servilleta"):
  cantidad_empaque = 0, unidad_empaque = null

Pistas para encontrar el empaque:
  • En el NOMBRE del producto: "Aceite Girasol 1 L", "Pollo entero 1.8 kg".
  • En la columna **Lista Empaque** o **Empaque** (facturas B2B Atlantic, Dislicores).
  • En la columna **UM** (Unidad de Medida) — si dice "KG" significa que viene por kilo suelto, no por unidad de empaque fijo: en ese caso cantidad_empaque = 1000 si la cantidad facturada está en kg.
  • Para licores: la presentación va con el producto ("Stella Artois 330ml", "Smirnoff 750ml").

═══════════════════════════════════════════════════
REGLA #5 — PRECIOS, IVA E IMPOCONSUMO
═══════════════════════════════════════════════════

5.1 — `precio_unitario` = precio por unidad ANTES de descuento, SIN IVA y SIN impoconsumo.
5.2 — `descuento_unitario` = descuento aplicado a ese ítem (ej. "Tu Ahorro" en Makro). 0 si no hay.
5.3 — `subtotal` del ítem = (precio_unitario − descuento_unitario) × cantidad.
5.4 — `iva_porcentaje` = % de IVA del ítem (0, 5, 19). En licores muchas veces es 0%.
5.5 — `impoconsumo_porcentaje` = % impoconsumo del ítem (0, 8). Aplica a bebidas alcohólicas.

A nivel de factura:
5.6 — `subtotal` = suma de subtotales de ítems (todo SIN IVA, SIN impoconsumo, ya con descuentos).
5.7 — `iva` = IVA total facturado.
5.8 — `impoconsumo` = impoconsumo total facturado (SEPARADO del IVA).
5.9 — `descuento_total` = suma de descuentos.
5.10 — `total` = valor TOTAL FINAL pagado. Debe cumplir: `total ≈ subtotal + iva + impoconsumo`.

Si la factura NO separa IVA de impoconsumo, déjalos como mejor identifiques. Si no hay impoconsumo, ponlo en 0 (no lo mezcles con IVA).

═══════════════════════════════════════════════════
REGLA #6 — FACTURAS LARGAS (CAPTURA TODAS LAS LÍNEAS)
═══════════════════════════════════════════════════

En facturas B2B verás "TOTAL NRO LINEAS: 19" o "TOTAL LISTA EMPAQUE: 25" cerca del total. **Tu lista `items` DEBE tener ese número exacto de elementos.** Si solo lees N pero el documento dice X, vuelve a revisar — probablemente la factura tiene varias páginas o ítems en columnas que omitiste.

═══════════════════════════════════════════════════
REGLA #7 — NOTAS MANUSCRITAS Y SELLOS (¡CRÍTICO!)
═══════════════════════════════════════════════════

Si ves algo **escrito a mano** sobre la factura impresa (correcciones, recortes de cantidad, "se reciben solo X", una fecha de recepción diferente, un "FALTA", "DEVUELTO", etc.) **NO MODIFIQUES los números impresos**, pero PONLO ENTERO en `notas_revision`.

Ejemplos:
  • Manuscrito "Se reciben solamente 2 cajas de Stella" → notas_revision = "MANUSCRITO: Se recibieron solo 2 cajas de Stella (revisar cantidad real recibida vs facturada)"
  • Sello "ACEPTADA" + firma con fecha 02/05/26 → notas_revision = "Aceptada el 2026-05-02 (sello manual)"
  • Tachón sobre cantidad → notas_revision = "Hay un tachón sobre la cantidad del ítem N, verificar"

Si no hay nada manuscrito ni sello relevante: notas_revision = null.

═══════════════════════════════════════════════════
REGLA #8 — CASOS ESPECIALES DE PROVEEDORES
═══════════════════════════════════════════════════

• **HIPERMAR (HICO FISH SAS) — recibo térmico angosto**:
  Formato de línea: `qty UN (codigo) NombreProducto    $ valor_total_linea`
  La segunda línea (indentada) es la **continuación del nombre** + posiblemente el peso/volumen.
  El "valor_total_linea" es el subtotal SIN IVA del ítem (no el precio unitario).
  Al final hay # BASE 19%, # IVA 19%, Subtotal, Impuestos, Total.

• **DISLICORES — factura B2B de licores**:
  Columnas: CÓDIGO BARRAS · REFERENCIA · CANT · DESCRIPCIÓN · % BASE UNIT · DESCT % · P UNIT ANTES IVA · % IVA · % CONSUMO · P FINAL UNIT · VLR NETO FINAL
  • % IVA suele ser 0 en licores; % CONSUMO suele ser 8.
  • Toma `P UNIT ANTES IVA` como `precio_unitario`.
  • Toma `VLR NETO FINAL` como `subtotal` del ítem.

• **ATLANTIC FS SAS — factura B2B de pescados/mariscos**:
  Columnas: CÓDIGO EAN · CÓDIGO · DESCRIPCIÓN · LISTA EMPAQUE · UNIDADES · UM · $ UNITARIO · $ TOTAL · DESCUENTO % · IMPUESTOS-VENTAS % · VALOR TOTAL
  • `UM` puede ser KG, UN, BTC (botella) → cópialo a `unidad` en minúsculas.
  • Si UM = KG y UNIDADES = 2.000 → cantidad = 2.0, unidad = "kg", cantidad_empaque = 1000, unidad_empaque = "g".
  • Verifica el "TOTAL NRO LINEAS" al pie y cuenta tus ítems.

• **MAKRO / PRICESMART**: columna "Tu Ahorro" → descuento_unitario.

• **OLÍMPICA / JUSTO & BUENO / SAO / D1 / similares — recibos térmicos con descuentos en línea aparte**:
  Formato típico:
    ```
    # CODIGO          IVA IPO  CANT  TOTAL_s/desc
      Nombre Producto (continúa abajo)
    Descuento XX,XX %                  VALOR-
    ```
  Ejemplo real:
    ```
    1  7700149400145   19  Ipo  1     169.800
       Sarten 28Cm Freeh VerdeCOL697
    Descuento 50,00 %                  84.900-
    ```
  Extracción correcta:
    nombre = "Sartén 28cm Freeh Verde COL697"
    cantidad = 1
    precio_unitario = 169800        ← el TOTAL_s/desc dividido entre CANT
    descuento_unitario = 84900      ← el VALOR del descuento dividido entre CANT
    subtotal = 84900                 ← (precio_unitario − descuento_unitario) × cantidad

  Otro ejemplo con cantidad > 1:
    ```
    2  7700149400138   19  0    5     524.600
       Sarten 32Cm Freeh VerdeCOL697
    Descuento 50,00 %                 262.250-
    ```
  Extracción:
    cantidad = 5
    precio_unitario = 104920        ← 524600 / 5
    descuento_unitario = 52450      ← 262250 / 5
    subtotal = 262350                ← 524600 − 262250

  ⚠️ EN ESTE FORMATO ES OBLIGATORIO LEER LA LÍNEA "Descuento XX,XX %" QUE SIGUE A CADA PRODUCTO Y EXTRAERLA. Si la ignoras, los totales no cuadran y el cliente paga el doble en la app de lo que realmente pagó. Si dudas, calcula `subtotal = TOTAL_s/desc − valor_descuento` y verifica que la suma de subtotales coincida con el total final de la factura.

  Si el descuento es **100,00 %**, el producto fue regalo: precio_unitario = TOTAL_s/desc / cantidad, descuento_unitario = igual, subtotal = 0.

• **CUENTA LOS ÍTEMS POR EL NÚMERO DE FILA**: en recibos térmicos cada línea empieza con un número correlativo (1, 2, 3, 4, …). El último número que veas es la cantidad total de productos. Si la factura tiene 8 productos y solo lees 6, **vuelve a revisar** y captura los faltantes. NUNCA omitas un ítem.

• **Recibos de caja menor / pagos sueltos / arriendos**: items = [], descripción en `notas`.

═══════════════════════════════════════════════════
REGLA #9 — FORMATO DE NÚMEROS
═══════════════════════════════════════════════════

Todos los valores monetarios son enteros en COP, SIN puntos de miles, SIN comas, SIN decimales. Ej: `1116200` (no `1.116.200` ni `1,116,200.00`).

`cantidad` y `cantidad_empaque` pueden tener decimales (ej. 1.5 kg → cantidad = 1.5).

═══════════════════════════════════════════════════
VALIDACIÓN INTERNA (antes de responder)
═══════════════════════════════════════════════════

1. ¿Suma de `item.subtotal` ≈ `subtotal` de factura?
2. ¿`subtotal` + `iva` + `impoconsumo` ≈ `total`?
3. ¿`items.length` coincide con "TOTAL NRO LINEAS" si aparece?
4. ¿Ningún `nombre` tiene números pegados sin separar, ni códigos `(123456)`, ni `$`, ni el peso del empaque?
5. ¿`cantidad_empaque` está en gramos o mililitros (unidad base), no en kilos ni litros?

Si algo no cuadra, **vuelve a revisar la imagen y corrige antes de devolver el JSON**.
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
        prompt += (
            "\n\n═══════════════════════════════════════════════════\n"
            "⚠️ CORRECCIÓN DEL USUARIO (máxima prioridad)\n"
            "═══════════════════════════════════════════════════\n"
            "Tienes una corrección explícita del humano que revisó la factura. "
            "Úsala como verdad y reajusta tu extracción a partir de ella:\n\n"
            f"{hint.strip()}"
        )

    msg = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4096,
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
