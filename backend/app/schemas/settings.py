from pydantic import BaseModel


class GeminiKeyStatus(BaseModel):
    """Der echte Key wird nie ans Frontend zurückgegeben - nur ob einer
    hinterlegt ist (DB oder .env-Fallback) und die letzten 4 Zeichen zur
    Wiedererkennung ("ist das noch mein Key?")."""

    configured: bool
    source: str | None = None  # "settings" | "env" | None
    last4: str | None = None


class GeminiKeyIn(BaseModel):
    api_key: str


class DisplaySettings(BaseModel):
    """Anzeige-Präferenzen für die Timeline (siehe pages/Timeline.tsx),
    persistiert in der DB statt localStorage, damit sie geräteübergreifend
    gelten (analog zum Gemini-Key)."""

    # Max. Spaltenzahl im ausbalancierten Foto-Grid pro Tag (1-10).
    timeline_columns_max: int = 5
    # Anzahl Tages-Gruppen ("Wochen") pro Timeline-Seite, bevor Pagination
    # greift (1-25).
    timeline_weeks_per_page: int = 8
