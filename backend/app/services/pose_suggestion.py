"""
Pose-Vorschläge für unverarbeitete Fotos.

Heuristik: Nutzer fotografieren ihre Posen typischerweise in derselben
Reihenfolge (z.B. immer erst Front Relaxed, dann Left Side, ... zuletzt
Most Muscular) - das zeigt sich in den bereits zugeordneten Fotos früherer
Sessions. Neue, noch unzugeordnete Fotos werden nach Aufnahmedatum in
"Sessions" (Fotos desselben Kalendertags) gruppiert; das n-te Foto einer
neuen Session bekommt die Pose vorgeschlagen, die beim n-ten Foto der
zuletzt vollständig zugeordneten Session verwendet wurde.

Bewusst nur ein Vorschlag, keine automatische Zuordnung: der Nutzer sieht
die Vorauswahl im Dropdown, kann sie aber jederzeit ändern oder leer
lassen (siehe Unprocessed.tsx). Passt die Foto-Anzahl nicht zur
Referenz-Session oder gibt es noch keine zugeordneten Fotos, bleibt der
Vorschlag leer (None) - dann muss manuell zugeordnet werden.
"""
from collections import defaultdict

from sqlalchemy.orm import Session

from app.models.photo import Photo


def compute_pose_suggestions(db: Session, unprocessed_photos: list[Photo]) -> dict[int, int | None]:
    """Liefert {photo_id: vorgeschlagene pose_id oder None}."""
    if not unprocessed_photos:
        return {}

    processed = (
        db.query(Photo)
        .filter(Photo.pose_id.isnot(None))
        .order_by(Photo.taken_at)
        .all()
    )
    if not processed:
        return {photo.id: None for photo in unprocessed_photos}

    # Referenz-Session: der jüngste Kalendertag mit bereits zugeordneten
    # Fotos, in der Reihenfolge ihrer Aufnahme.
    ref_date = max(p.taken_at.date() for p in processed)
    ref_sequence = [
        p.pose_id for p in sorted(
            (p for p in processed if p.taken_at.date() == ref_date),
            key=lambda p: p.taken_at,
        )
    ]

    by_date: dict = defaultdict(list)
    for photo in unprocessed_photos:
        by_date[photo.taken_at.date()].append(photo)

    suggestions: dict[int, int | None] = {}
    for _date, group in by_date.items():
        group_sorted = sorted(group, key=lambda p: p.taken_at)
        for index, photo in enumerate(group_sorted):
            suggestions[photo.id] = ref_sequence[index] if index < len(ref_sequence) else None

    return suggestions
