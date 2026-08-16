"""
Dauerhafter Objekt-Speicher (Cloudflare R2) über einen lokalen Sync-
Cache - siehe Design-Spec Abschnitt "Datei-Speicherung" und die
Architektur-Präzisierung im Implementierungsplan. `settings.data_dir`
bleibt in BEIDEN Betriebsmodi das lokale Arbeitsverzeichnis, in dem die
bestehende Bildverarbeitung (pose_normalization.py, thumbnails.py,
heic.py) unverändert mit echten Path-Objekten arbeitet:

- storage_backend="local" (Standard, lokale Entwicklung): push/
  ensure_local/delete_remote sind No-Ops, data_dir ist die einzige
  Quelle der Wahrheit, wie bisher.
- storage_backend="r2" (Produktion): data_dir wird zum FLÜCHTIGEN
  lokalen Cache (Railways Plattenspeicher wird bei jedem Redeploy/
  Neustart geleert) - R2 ist die eigentliche Quelle der Wahrheit.
  push() lädt eine gerade geschriebene Datei sofort nach R2 hoch,
  ensure_local() holt eine (auf dieser Instanz noch nicht gecachte)
  Datei bei Bedarf von R2, delete_remote() räumt in R2 mit auf.
"""
import logging

from botocore.exceptions import ClientError

from app.core.config import settings

logger = logging.getLogger(__name__)

_client = None


def _r2_client():
    """Lazy erzeugter, gecachter boto3-S3-Client gegen den R2-Endpoint.
    Als eigene, patchbare Funktion (statt Modul-Level-Konstante), damit
    Tests sie einfach durch einen Fake ersetzen können."""
    global _client
    if _client is None:
        import boto3

        _client = boto3.client(
            "s3",
            endpoint_url=f"https://{settings.r2_account_id}.r2.cloudflarestorage.com",
            aws_access_key_id=settings.r2_access_key_id,
            aws_secret_access_key=settings.r2_secret_access_key,
            region_name="auto",
        )
    return _client


def push(rel_path: str) -> None:
    """Lädt settings.data_dir/rel_path nach R2 hoch. No-Op im lokalen
    Modus. Aufrufer: direkt nachdem eine Datei fertig geschrieben wurde
    (Upload, Thumbnail, Normalisierung, Verschieben)."""
    if settings.storage_backend != "r2":
        return
    local_path = settings.data_dir / rel_path
    try:
        _r2_client().upload_file(str(local_path), settings.r2_bucket, rel_path)
    except Exception:
        logger.exception("R2-Upload fehlgeschlagen für %s", rel_path)
        raise


def ensure_local(rel_path: str) -> None:
    """Stellt sicher, dass settings.data_dir/rel_path lokal existiert -
    lädt bei Bedarf von R2 herunter. No-Op im lokalen Modus (und wenn
    die Datei bereits lokal vorhanden ist, z.B. auf derselben Instanz,
    die sie geschrieben hat). Aufrufer: direkt VOR jedem Lesezugriff auf
    eine potenziell noch nicht lokal gecachte Datei."""
    if settings.storage_backend != "r2":
        return
    local_path = settings.data_dir / rel_path
    if local_path.exists():
        return
    try:
        _r2_client().download_file(settings.r2_bucket, rel_path, str(local_path))
    except ClientError:
        # Datei existiert auch in R2 nicht (z.B. gelöscht/nie hochgeladen) -
        # der Aufrufer behandelt eine fehlende lokale Datei bereits heute
        # als normalen Zustand (z.B. `if not source.exists(): continue`).
        logger.warning("R2-Download fehlgeschlagen (existiert nicht?) für %s", rel_path)


def delete_remote(rel_path: str) -> None:
    """Löscht rel_path aus R2. No-Op im lokalen Modus. Aufrufer: überall
    dort, wo heute schon die lokale Datei gelöscht wird."""
    if settings.storage_backend != "r2":
        return
    try:
        _r2_client().delete_object(Bucket=settings.r2_bucket, Key=rel_path)
    except Exception:
        logger.exception("R2-Löschung fehlgeschlagen für %s", rel_path)
