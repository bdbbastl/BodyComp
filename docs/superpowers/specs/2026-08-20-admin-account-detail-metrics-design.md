# Master-Admin: Account-Detail-Kennzahlen — Design

## Ziel

Der Master-Admin-Bereich (`/admin`, `/admin/accounts/:userId`) existiert bereits mit Übersichts-Kennzahlen (Total/Single/Coach-Accounts, aktive Abos, Signups), einer durchsuchbaren Accounts-Tabelle (aktiv/inaktiv-Umschalter) und einer Account-Detailseite mit Klienten-Liste (Name, Foto-Anzahl, letzte Aktivität pro Klient — bereits vollständig). Dieses Paket erweitert die Account-Detailseite um drei zusätzliche Kennzahl-Gruppen: Gesamt-Aktivität, Speicherverbrauch, Billing-Details. Ausdrücklich **nicht** Teil dieses Pakets: Zeitverlauf/Trend-Graphen und Admin-Aktionen (Upgrade/Downgrade, Passwort-Reset) — das sind eigene, später folgende Pakete.

## a) Gesamt-Check-in-Anzahl

Neues Feld `total_checkins: int` auf `AdminAccountDetailOut` — Summe aller `CheckinSubmission`-Zeilen über alle Klienten des Accounts hinweg. Reine Aggregation über bereits vorhandene Daten, kein neues Modell, kein Migrations-Aufwand.

## b) Speicherverbrauch

Neue, nullable Spalte `file_size_bytes: int | None` auf `Photo` (Alembic-Migration). Wird ab sofort beim Foto-Upload/-Sync befüllt (`os.path.getsize()` direkt nach dem Schreiben der Datei, sowohl beim manuellen Upload als auch beim Ordner-Sync — an der Stelle, wo die Datei bereits lokal auf der Platte liegt, unabhängig vom `storage_backend`).

Für bereits existierende Fotos (vor diesem Feature) ist der Wert zunächst `NULL` — kein automatisches rückwirkendes Befüllen als Teil dieses Pakets (bei `storage_backend="r2"` bräuchte das einen separaten Batch-Job mit R2-HEAD-Requests pro Objekt, das ist bewusst außerhalb des Scopes). Die Kennzahl auf der Account-Detailseite zeigt die Summe der **bekannten** Größen (`COALESCE(file_size_bytes, 0)` summiert) mit einem kleinen Hinweistext, falls Fotos ohne bekannte Größe existieren ("+N photos with unknown size"), statt fälschlich einen vollständigen Wert vorzutäuschen.

Neues Feld `total_storage_bytes: int` und `photos_with_unknown_size: int` auf `AdminAccountDetailOut`. Frontend zeigt den Wert menschenlesbar formatiert (z.B. "142 MB").

## c) Billing-Details

Werden **live von Stripe abgefragt**, nicht in der eigenen DB gespiegelt (vermeidet Stale-Data-Probleme). Nutzt die bereits auf `User.stripe_customer_id` gespeicherte Customer-ID. Neuer Endpunkt `GET /api/admin/accounts/{user_id}/billing` (statt die Haupt-Detailseite bei jedem Aufruf mit einem zusätzlichen Stripe-Roundtrip zu verlangsamen — eigener, separat ladender Bereich auf der Frontend-Seite):

- `subscription_id: str | None`
- `next_billing_date: datetime | None` (aus `subscription.current_period_end`)
- `recent_invoices: list[{amount: float, currency: str, paid_at: datetime, status: str}]` (letzte 5, aus `stripe.Invoice.list(customer=..., limit=5)`)

Gibt `null`/leere Liste zurück, wenn der Account keine `stripe_customer_id` hat (z.B. Accounts, die nie ein kostenpflichtiges Abo hatten) — kein Fehler, das ist ein normaler Zustand. Stripe-API-Fehler (Netzwerk, ungültige Customer-ID) werden abgefangen und als leerer Zustand mit einer Fehlermeldung im Frontend angezeigt, nicht als 500.

## Out of Scope

- Zeitverlauf/Trend-Graphen (Signup-Verlauf, Churn, MRR) — eigenes späteres Paket.
- Admin-Aktionen (Account upgraden/downgraden, Passwort-Reset auslösen, Nachricht an Nutzer) — eigenes späteres Paket.
- Rückwirkendes Befüllen der Dateigröße für Fotos vor diesem Feature — bewusst ausgelassen (siehe oben).
