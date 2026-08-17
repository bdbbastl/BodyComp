"""Gespiegelte Logik zu frontend/src/utils/weight.ts - Komma/Punkt als
Dezimaltrennzeichen tolerieren, auf 0,05kg-Schritte runden. Siehe
Design-Spec "Usability-Fixes Runde 2" Abschnitt 2. Als Defensive-
Maßnahme gedacht (v.a. für Endpunkte, die direkt per API ohne unser
Frontend aufgerufen werden koennten) - das Frontend normalisiert schon
selbst, bevor es sendet."""


def parse_weight_kg(value: float | str | None) -> float | None:
    """Akzeptiert float, int, oder String mit Komma/Punkt. Gibt None bei
    None/leerem String zurueck. Wirft ValueError bei nicht parsbarem
    String (Aufrufer entscheidet, wie das dem Nutzer gemeldet wird)."""
    if value is None:
        return None
    if isinstance(value, str):
        trimmed = value.strip()
        if trimmed == "":
            return None
        value = float(trimmed.replace(",", "."))
    return round(float(value) / 0.05) * 0.05
