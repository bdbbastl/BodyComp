"""
Einfaches In-Memory-Rate-Limiting pro IP-Adresse - siehe Design-Spec
Abschnitt "Rate-Limiting". Sliding-Window-Zähler im Prozessspeicher,
reicht für den aktuellen Single-Process-Betrieb.

Offener Punkt für Stufe 3 (siehe Design-Spec): bei Wechsel auf
Mehrprozess-/Mehrserver-Hosting muss das auf einen gemeinsamen Store
(Redis) wechseln - In-Memory funktioniert nur pro Einzelprozess.
"""
import time
from collections import defaultdict

from fastapi import HTTPException, Request


class RateLimiter:
    def __init__(self, *, max_requests: int, window_seconds: int):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._hits: dict[str, list[float]] = defaultdict(list)

    def __call__(self, request: Request) -> None:
        # Nur die Socket-Client-IP wird vertraut - X-Forwarded-For ist ein
        # vom Client frei setzbarer Header und würde das Limit ohne
        # vorgeschalteten, vertrauenswürdigen Reverse-Proxy aushebeln.
        ip = request.client.host if request.client else "unknown"
        now = time.monotonic()
        cutoff = now - self.window_seconds

        hits = self._hits[ip]
        hits[:] = [t for t in hits if t > cutoff]

        if not hits:
            # Kein Eintrag mehr im Fenster - Speicher freigeben, damit
            # _hits nicht unbegrenzt für jede jemals gesehene IP wächst.
            del self._hits[ip]

        if len(hits) >= self.max_requests:
            raise HTTPException(429, "Zu viele Versuche - bitte später erneut probieren.")

        hits.append(now)
        self._hits[ip] = hits
