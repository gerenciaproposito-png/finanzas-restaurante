import json
from datetime import datetime
from pathlib import Path

from app.database import SessionLocal
from app.models import Configuracion, DriveSyncLog, VentaPendiente
from app.services import drive
from app.services.ocr_ventas import extract_venta

UPLOADS_DIR = Path(__file__).resolve().parent.parent.parent / "uploads" / "ventas"
MIME_EXT = {
    "image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp",
    "image/gif": ".gif", "image/heic": ".heic", "image/heif": ".heif",
    "application/pdf": ".pdf",
}


def get_cfg(db, clave: str) -> str | None:
    c = db.get(Configuracion, clave)
    return c.valor if c else None


def run_sync_ventas() -> dict:
    """Download new Drive sales reports, OCR them, add to review queue."""
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    stats = {"nuevas": 0, "ya_procesadas": 0, "errores": 0}

    with SessionLocal() as db:
        folder_id = get_cfg(db, "ventas_folder_id")
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
            datos = extract_venta(local_path, api_key)

            turnos = datos if isinstance(datos, list) else [datos]

            with SessionLocal() as db:
                for turno in turnos:
                    db.add(VentaPendiente(
                        drive_file_id=file_id,
                        nombre_archivo=f["name"],
                        archivo_local=str(local_path),
                        datos_json=json.dumps(turno, ensure_ascii=False),
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
            stats["nuevas"] += len(turnos)

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


