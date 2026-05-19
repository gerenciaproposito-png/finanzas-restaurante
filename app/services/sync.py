import json
from datetime import datetime
from pathlib import Path

from app.database import SessionLocal
from app.models import Configuracion, DriveSyncLog, FacturaPendiente
from app.services import drive, ocr

UPLOADS_DIR = Path(__file__).resolve().parent.parent.parent / "uploads" / "facturas"
MIME_EXT = {
    "image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp",
    "image/gif": ".gif", "image/heic": ".heic", "image/heif": ".heif",
    "application/pdf": ".pdf",
}


def get_cfg(db, clave: str) -> str | None:
    c = db.get(Configuracion, clave)
    return c.valor if c else None


def run_sync() -> dict:
    """Download new Drive photos, OCR them, add to review queue. Returns stats dict."""
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    stats = {"nuevas": 0, "ya_procesadas": 0, "errores": 0}

    with SessionLocal() as db:
        folder_id = get_cfg(db, "drive_folder_id")
        api_key = get_cfg(db, "anthropic_api_key")

    if not folder_id or not api_key or not drive.is_connected():
        return stats

    files = drive.list_images_in_folder(folder_id)

    for f in files:
        file_id = f["id"]
        with SessionLocal() as db:
            already = db.query(DriveSyncLog).filter_by(drive_file_id=file_id).first()
            if already:
                stats["ya_procesadas"] += 1
                continue

        ext = MIME_EXT.get(f.get("mimeType", ""), ".jpg")
        local_path = UPLOADS_DIR / f"{file_id}{ext}"

        try:
            drive.download_file(file_id, local_path)
            datos = ocr.extract_invoice(local_path, api_key)

            # Claude may return a list when a PDF contains multiple invoices
            invoices = datos if isinstance(datos, list) else [datos]

            with SessionLocal() as db:
                for inv in invoices:
                    db.add(FacturaPendiente(
                        drive_file_id=file_id,
                        nombre_archivo=f["name"],
                        archivo_local=str(local_path),
                        datos_json=json.dumps(inv, ensure_ascii=False),
                        fecha_sync=datetime.now(),
                        estado="pendiente",
                    ))
                db.add(DriveSyncLog(
                    drive_file_id=file_id,
                    nombre=f["name"],
                    fecha_sync=datetime.now(),
                    estado="procesado",
                ))
                db.commit()
            stats["nuevas"] += len(invoices)

        except Exception as e:
            with SessionLocal() as db:
                db.add(DriveSyncLog(
                    drive_file_id=file_id,
                    nombre=f["name"],
                    fecha_sync=datetime.now(),
                    estado="error",
                    error=str(e)[:1000],
                ))
                db.commit()
            stats["errores"] += 1

    return stats


