"""
KI-gestützte Bewertung zweier Fortschrittsfotos im Stil eines Bodybuilding-
Judges, über Googles kostenlose Gemini-API (Vision-fähig, großzügige
Free-Tier-Limits, kein Kreditkarte nötig - siehe aistudio.google.com/apikey).
Läuft ausschließlich auf Knopfdruck (siehe routers/comparisons.py) - nie
automatisch beim bloßen Auswählen zweier Bilder.

Der API-Key kommt entweder aus der DB (App-Settings, vom User in der UI
eingetragen - siehe routers/settings.py) oder als Fallback aus
GEMINI_API_KEY in backend/.env. DB-Wert hat Vorrang, damit jeder User der
App seinen eigenen Key hinterlegen kann, ohne die .env anzufassen.
"""
import io
import os
import time
from datetime import date as date_
from pathlib import Path

from google import genai
from google.genai import errors as genai_errors
from google.genai import types
from PIL import Image
from sqlalchemy.orm import Session

# Key des AppSetting-Eintrags, unter dem der User-eigene Gemini-Key in der
# DB liegt (siehe models/app_setting.py, routers/settings.py).
GEMINI_KEY_SETTING = "gemini_api_key"

# Für die Bewertung reicht eine moderate Auflösung völlig aus und hält
# Latenz/Kosten gering - ein Judge muss keine 12-MP-Nahaufnahme sehen.
MAX_EDGE_PX = 1200
JPEG_QUALITY = 85

# "-latest"-Alias statt fixer Versionsnummer: zeigt immer auf Googles
# aktuelles Flash-Modell, damit der Code nicht bei jedem Modell-Refresh
# (wie z.B. bei gemini-2.5-flash geschehen: "no longer available to new
# users") manuell nachgezogen werden muss.
MODEL = "gemini-flash-latest"

# Gemini meldet bei Überlastung einen ServerError ("This model is currently
# experiencing high demand..."). Das ist laut Google-Doku meist temporär,
# daher hier automatisch mit kurzem Backoff erneut versuchen, bevor der
# Fehler an den User durchgereicht wird.
MAX_RETRIES = 3
RETRY_BACKOFF_SECONDS = 2.0

JUDGE_PROMPT = """\
Du bist Judge bei einem Bodybuilding-Wettkampf und bewertest zwei Fotos \
derselben Person in der Pose "{pose}", aufgenommen an zwei unterschiedlichen \
Terminen (Bild A: {date_x}{weight_x}, Bild B: {date_y}{weight_y}). Zwischen \
den beiden Aufnahmen liegen {time_delta}. Bewerte den Fortschritt zwischen \
den beiden Aufnahmen exakt so, wie ein erfahrener Judge das bei einem \
Vergleichs-Callout tun würde - sachlich, konkret, fachsprachlich \
(Muskelgruppen, Definition, Symmetrie, konditionelle Verfassung/KFA-\
Einschätzung, Posing). Berücksichtige den Zeitraum und die Körpergewichte \
(falls angegeben) explizit bei der Einordnung, was in dieser Zeit realistisch \
an Veränderung zu erwarten bzw. bereits erkennbar ist.

Antworte auf Deutsch, in exakt zwei Abschnitten mit diesen Überschriften:

## Unterschiede
Liste die konkret sichtbaren Unterschiede zwischen Bild A und Bild B auf \
(Muskelgruppe für Muskelgruppe, wo relevant: Definition, Masse, Vaskularität, \
Symmetrie, Körperfettanteil/Konditionierung, Haltung/Posing). Ordne die \
Unterschiede wo möglich in Bezug zum Zeitraum und zur Gewichtsveränderung \
ein. Wenn eine Muskelgruppe kaum beurteilbar ist (z.B. durch Blickwinkel/\
Pose verdeckt), sag das explizit statt zu raten.

## Verbesserungspotenziale
Liste konkrete, umsetzbare Ansatzpunkte auf, die aus den Bildern erkennbar \
sind (z.B. unterentwickelte Muskelgruppen, Symmetrie-Baustellen, \
Konditionierung, Posing-Ausführung). Bleib bei dem, was aus den Fotos \
tatsächlich ableitbar ist - keine allgemeinen Trainingsratschläge, die \
nicht durch das Bildmaterial gestützt sind.

Nutze Stichpunkte pro Abschnitt. Sei ehrlich und direkt wie ein echter \
Judge, aber nicht unnötig hart - konstruktiv und konkret."""

# Für den "Alle Posen"-Vergleich: statt einer einzelnen Pose bekommt Gemini
# Bildpaare mehrerer Posen auf einmal (max. ~40 Bilder bei 20 Posen) und
# soll daraus EIN gesamtheitliches Urteil über den ganzen Körper fällen,
# nicht einzelne Bewertungen pro Pose - verschiedene Blickwinkel ergänzen
# sich (z.B. zeigt eine Rückenpose Details, die eine Frontpose verdeckt).
JUDGE_PROMPT_ALL = """\
Du bist Judge bei einem Bodybuilding-Wettkampf und bewertest den GESAMTEN \
Fortschritt einer Person anhand von Fotos aus {pose_count} verschiedenen \
Posen, jeweils aufgenommen an zwei Terminen (Termin A: {date_x}{weight_x}, \
Termin B: {date_y}{weight_y}). Zwischen den beiden Terminen liegen \
{time_delta}. Die Bilder sind paarweise mit dem jeweiligen Posennamen und \
Termin gekennzeichnet.

Bewerte NICHT jede Pose einzeln nacheinander, sondern liefere ein \
GESAMTHEITLICHES Urteil über den kompletten Körper - nutze die \
unterschiedlichen Blickwinkel als Ergänzung zueinander (z.B. zeigen \
Rückenposen Details, die auf Frontposen nicht sichtbar sind). \
Berücksichtige den Zeitraum und die Körpergewichte (falls angegeben) \
explizit bei der Einordnung.

Antworte auf Deutsch, in exakt zwei Abschnitten mit diesen Überschriften:

## Unterschiede
Liste die konkret sichtbaren Unterschiede über den gesamten Körper hinweg \
auf (Muskelgruppe für Muskelgruppe, wo relevant: Definition, Masse, \
Vaskularität, Symmetrie, Körperfettanteil/Konditionierung, Haltung/Posing). \
Stütze dich dabei auf die Posen, aus denen die jeweilige Muskelgruppe am \
besten beurteilbar ist.

## Verbesserungspotenziale
Liste konkrete, umsetzbare Ansatzpunkte auf, die aus dem Gesamtbild über \
alle Posen erkennbar sind (z.B. unterentwickelte Muskelgruppen, \
Symmetrie-Baustellen, Konditionierung, Posing-Ausführung je Pose). Bleib \
bei dem, was aus den Fotos tatsächlich ableitbar ist.

Nutze Stichpunkte pro Abschnitt. Sei ehrlich und direkt wie ein echter \
Judge, aber nicht unnötig hart - konstruktiv und konkret."""


class AiComparisonError(Exception):
    """Verständliche, für den User lesbare Fehlermeldung (API-Key fehlt,
    Gemini-API-Fehler, etc.) - wird vom Router 1:1 durchgereicht."""


def resolve_gemini_api_key(db: Session) -> tuple[str | None, str | None]:
    """Liefert (key, source) - DB-Wert (source="settings") hat Vorrang vor
    GEMINI_API_KEY aus .env (source="env"). (None, None) wenn nichts gesetzt."""
    from app.models.app_setting import AppSetting  # lokal um Zirkelimporte zu vermeiden

    setting = db.get(AppSetting, GEMINI_KEY_SETTING)
    if setting and setting.value:
        return setting.value, "settings"
    env_key = os.environ.get("GEMINI_API_KEY")
    if env_key:
        return env_key, "env"
    return None, None


def _build_client(api_key: str) -> genai.Client:
    return genai.Client(api_key=api_key)


def _encode_image(path: Path) -> bytes:
    with Image.open(path) as img:
        img = img.convert("RGB")
        width, height = img.size
        scale = MAX_EDGE_PX / max(width, height)
        if scale < 1:
            img = img.resize((int(width * scale), int(height * scale)), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=JPEG_QUALITY)
        return buf.getvalue()


def _format_time_delta(date_x: date_, date_y: date_) -> str:
    days = abs((date_y - date_x).days)
    if days == 0:
        return "0 Tagen (gleicher Tag)"
    weeks, rem_days = divmod(days, 7)
    if days < 14:
        return f"{days} Tag{'en' if days != 1 else ''}"
    months = days / 30.44
    if months >= 2:
        return f"ca. {months:.1f} Monaten ({days} Tage)"
    return f"{weeks} Wochen{f' {rem_days} Tage' if rem_days else ''} ({days} Tage)"


def _generate_with_retries(client: genai.Client, contents: list) -> str:
    """Ruft Gemini auf und versucht bei ServerError (meist "high demand",
    laut Google i.d.R. temporär) automatisch mit kurzem Backoff erneut,
    bevor der Fehler an den User durchgereicht wird. Von compare_photos und
    compare_photos_all gemeinsam genutzt."""
    response = None
    last_server_error: genai_errors.ServerError | None = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = client.models.generate_content(model=MODEL, contents=contents)
            last_server_error = None
            break
        except genai_errors.ClientError as exc:
            # 401/403 = ungültiger Key, 429 = Free-Tier-Limit erreicht -
            # beides macht ein Retry sinnlos, sofort durchreichen.
            if exc.code in (401, 403):
                raise AiComparisonError(
                    "Der hinterlegte Gemini-API-Key ist ungültig oder hat keine "
                    "Berechtigung. Bitte in den Settings prüfen."
                ) from exc
            if exc.code == 429:
                raise AiComparisonError(
                    "Gemini-Free-Tier-Limit erreicht (Rate Limit). Bitte kurz warten "
                    "und erneut versuchen."
                ) from exc
            raise AiComparisonError(f"Gemini-API-Fehler ({exc.code}): {exc.message}") from exc
        except genai_errors.ServerError as exc:
            last_server_error = exc
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_BACKOFF_SECONDS * attempt)
                continue
        except Exception as exc:
            raise AiComparisonError(f"Unerwarteter Fehler bei der Gemini-Anfrage: {exc}") from exc

    if response is None:
        message = getattr(last_server_error, "message", str(last_server_error))
        raise AiComparisonError(
            f"Gemini-Server-Fehler nach {MAX_RETRIES} Versuchen: {message} "
            "Der Dienst ist aktuell überlastet - bitte in ein paar Minuten erneut "
            "versuchen."
        )

    text = getattr(response, "text", None)
    if not text:
        # z.B. wenn Gemini die Anfrage aus Sicherheitsgründen blockiert hat
        feedback = getattr(response, "prompt_feedback", None)
        raise AiComparisonError(
            f"Die KI-Antwort enthielt keinen auswertbaren Text (Feedback: {feedback})."
        )
    return text


def _require_client(db: Session) -> genai.Client:
    api_key, _source = resolve_gemini_api_key(db)
    if not api_key:
        raise AiComparisonError(
            "Kein Gemini-API-Key konfiguriert. Kostenlosen Key unter "
            "https://aistudio.google.com/apikey erstellen und in den Settings "
            "der App hinterlegen."
        )
    return _build_client(api_key)


def compare_photos(
    db: Session,
    path_x: Path,
    path_y: Path,
    pose_name: str,
    date_x: date_,
    date_y: date_,
    weight_x: float | None = None,
    weight_y: float | None = None,
) -> str:
    """Sendet beide Bilder an Gemini und liefert die Judge-Bewertung als
    Markdown-Text (zwei Abschnitte: Unterschiede, Verbesserungspotenziale).
    weight_x/weight_y (Körpergewicht am jeweiligen Tag, aus DayLog) und die
    Zeitdifferenz zwischen date_x/date_y fließen mit in den Prompt ein,
    damit die KI Veränderungen korrekt im zeitlichen Kontext einordnet."""
    if not path_x.exists() or not path_y.exists():
        raise AiComparisonError("Eines der Bilder konnte auf der Platte nicht gefunden werden.")

    client = _require_client(db)

    try:
        bytes_x = _encode_image(path_x)
        bytes_y = _encode_image(path_y)
    except Exception as exc:
        raise AiComparisonError(f"Bild konnte nicht verarbeitet werden: {exc}") from exc

    weight_x_str = f", {weight_x:.1f} kg" if weight_x is not None else ""
    weight_y_str = f", {weight_y:.1f} kg" if weight_y is not None else ""
    time_delta = _format_time_delta(date_x, date_y)

    prompt = JUDGE_PROMPT.format(
        pose=pose_name,
        date_x=date_x.isoformat(),
        date_y=date_y.isoformat(),
        weight_x=weight_x_str,
        weight_y=weight_y_str,
        time_delta=time_delta,
    )
    contents = [
        f"Bild A (aufgenommen am {date_x.isoformat()}{weight_x_str}):",
        types.Part.from_bytes(data=bytes_x, mime_type="image/jpeg"),
        f"Bild B (aufgenommen am {date_y.isoformat()}{weight_y_str}):",
        types.Part.from_bytes(data=bytes_y, mime_type="image/jpeg"),
        prompt,
    ]
    return _generate_with_retries(client, contents)


def compare_photos_all(
    db: Session,
    pairs: list[tuple[str, Path, Path]],
    date_x: date_,
    date_y: date_,
    weight_x: float | None = None,
    weight_y: float | None = None,
) -> str:
    """Wie compare_photos, aber für "Alle Posen" auf einmal: pairs ist eine
    Liste aus (pose_name, path_x, path_y) - eine pro Pose, die an beiden
    Terminen ein Foto hat. Liefert EIN gesamtheitliches Urteil über den
    ganzen Körper (siehe JUDGE_PROMPT_ALL), keine Einzelbewertung pro Pose."""
    if not pairs:
        raise AiComparisonError(
            "Für keine Pose existieren Fotos an beiden gewählten Terminen."
        )

    client = _require_client(db)

    weight_x_str = f", {weight_x:.1f} kg" if weight_x is not None else ""
    weight_y_str = f", {weight_y:.1f} kg" if weight_y is not None else ""
    time_delta = _format_time_delta(date_x, date_y)

    prompt = JUDGE_PROMPT_ALL.format(
        pose_count=len(pairs),
        date_x=date_x.isoformat(),
        date_y=date_y.isoformat(),
        weight_x=weight_x_str,
        weight_y=weight_y_str,
        time_delta=time_delta,
    )

    contents: list = []
    for pose_name, path_x, path_y in pairs:
        if not path_x.exists() or not path_y.exists():
            continue
        try:
            bytes_x = _encode_image(path_x)
            bytes_y = _encode_image(path_y)
        except Exception as exc:
            raise AiComparisonError(f"Bild konnte nicht verarbeitet werden: {exc}") from exc
        contents.append(f"Pose \"{pose_name}\", Bild A (aufgenommen am {date_x.isoformat()}{weight_x_str}):")
        contents.append(types.Part.from_bytes(data=bytes_x, mime_type="image/jpeg"))
        contents.append(f"Pose \"{pose_name}\", Bild B (aufgenommen am {date_y.isoformat()}{weight_y_str}):")
        contents.append(types.Part.from_bytes(data=bytes_y, mime_type="image/jpeg"))

    if not contents:
        raise AiComparisonError("Keines der Bilder konnte auf der Platte gefunden werden.")

    contents.append(prompt)
    return _generate_with_retries(client, contents)
