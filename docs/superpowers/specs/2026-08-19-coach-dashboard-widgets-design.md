# Coach-Dashboard: 4-Widget-Layout (Stufe 7d) — Design-Spec

**Datum:** 2026-08-19
**Status:** Genehmigt

## Kontext

Das bestehende Coach-Dashboard (`frontend/src/pages/Dashboard.tsx`) zeigt eine volle Kachel-Ansicht aller Klienten mit Suche/Filter. Der Nutzer möchte stattdessen ein kompaktes 4-Widget-Layout (2x2), das auf einen Blick die wichtigsten Informationen liefert, statt scrollend durch alle Klienten-Kacheln zu gehen. Entwickelt mit dem Visual-Companion-Tool (Mockup-Runde bestätigt).

## Ziel

Das bestehende Klienten-Grid komplett durch 4 Widgets ersetzen: Quick-Client-Liste (mit Suche), ungesehene Check-ins, "Needs attention" (stille Klienten), und eine Wochen-Statistik-Kachel.

## Datenmodell / Backend

### Neuer Aggregations-Endpunkt: `GET /api/dashboard/coach-summary`

Neue Datei `backend/app/routers/dashboard.py`, neuer Router `prefix="/api/dashboard"`. Nur für eingeloggte Coach-Accounts sinnvoll (Single-Accounts haben nur einen impliziten Klienten - der Endpunkt wird vom Frontend nur im Coach-Kontext aufgerufen, serverseitig aber nicht auf `account_type == "coach"` beschränkt, da er rein auf `current_user`s eigene Klienten scoped und für einen Single-Account einfach leere/triviale Listen liefert - keine Sicherheitsrelevanz, kein Grund für eine künstliche Sperre).

Response-Schema (`backend/app/schemas/dashboard.py`, neu):

```python
class PendingCheckinSummary(BaseModel):
    id: int
    client_id: int
    client_name: str
    submitted_at: datetime
    weight_kg: float | None

class NeedsAttentionClient(BaseModel):
    client_id: int
    client_name: str
    days_since_activity: int | None  # None = noch NIE Aktivität (kein last_activity)

class WeekStats(BaseModel):
    checkins: int
    photos: int
    active_clients: int

class CoachDashboardSummary(BaseModel):
    pending_checkins: list[PendingCheckinSummary]
    needs_attention: list[NeedsAttentionClient]
    week_stats: WeekStats
```

Logik im Router:
- `pending_checkins`: alle `CheckinSubmission` mit `status == PENDING` über ALLE Klienten des eingeloggten Users (`Client.owner_id == current_user.id`), sortiert `submitted_at` absteigend (neueste zuerst).
- `needs_attention`: für jeden Klienten des Users, dessen `last_activity` (wiederverwendet aus der bestehenden Berechnung in `routers/clients.py list_clients` - siehe dort, gleiche Subquery-Logik) entweder `None` ist ODER mehr als 7 Tage in der Vergangenheit liegt. `days_since_activity` = `None` falls `last_activity` nie gesetzt war, sonst `(heute - last_activity).days`. Sortiert absteigend nach `days_since_activity` (am längsten stille Klienten zuerst, `None`-Werte - "nie aktiv" - ganz oben).
- `week_stats.checkins`: Anzahl `CheckinSubmission` mit `submitted_at >= (jetzt - 7 Tage)` über alle Klienten des Users.
- `week_stats.photos`: Anzahl `Photo` mit `taken_at >= (jetzt - 7 Tage)` über alle Klienten des Users.
- `week_stats.active_clients`: Anzahl DISTINCT Klienten mit mindestens einem `CheckinSubmission` ODER `Photo` in den letzten 7 Tagen (Union der beiden vorherigen Mengen, nach `client_id` dedupliziert).

7-Tage-Schwelle als benannte Konstante `NEEDS_ATTENTION_THRESHOLD_DAYS = 7` im Router-Modul, nicht magisch inline.

### "Mark as seen"

Keine neue Backend-Logik - nutzt den bestehenden `PATCH /api/clients/{client_id}/checkins/{checkin_id}` mit `{"mark_reviewed": true}` (bereits vorhanden in `routers/checkins.py`, bisher nur von der Coach-Klient-Detailseite genutzt).

### Klienten-Liste selbst

Kein neuer Endpunkt nötig - `GET /api/clients` (bestehend, `api.clients.list()`) liefert bereits `name`, `pending_checkins_count`, `last_activity` - alles, was das Quick-List-Widget braucht.

## Frontend

### `frontend/src/api/client.ts`

Neuer Typ `CoachDashboardSummary` (Spiegelbild des Backend-Schemas) und `api.dashboard.coachSummary(): Promise<CoachDashboardSummary>` → `GET /dashboard/coach-summary`.

### `frontend/src/pages/Dashboard.tsx`

Das bestehende volle Klienten-Grid (Kacheln mit Suche/Gender-Filter, `DashboardClientCard`) wird komplett entfernt und durch ein 2x2-Grid aus 4 neuen Widget-Komponenten ersetzt (`grid-cols-1 md:grid-cols-2 gap-4` - stapelt auf Mobile). "Add New Client"-Button + Inline-Formular bleiben unverändert oben (PageHeader-Action), stehen über dem Widget-Grid.

**Widget 1 - `ClientsWidget`:** Card mit Titel "Clients", Such-Eingabefeld oben (filtert client-seitig auf `api.clients.list()`-Daten, wie bisher, nur ohne Gender-Filter - YAGNI, nicht Teil der Spec), darunter eine Liste mit fester Höhe (`max-h-64 overflow-y-auto`) - jede Zeile klickbar (`Link to /clients/:id/timeline`), zeigt Name + `pending_checkins_count`-Badge (falls > 0, gleicher Amber-Stil wie bisher).

**Widget 2 - `PendingCheckinsWidget`:** Card mit Titel "Unseen check-ins", Liste (`max-h-64 overflow-y-auto`) aus `pending_checkins`, jede Zeile zeigt Klientenname, relatives Datum (`submitted_at`), Gewicht falls vorhanden, plus einen "Mark seen"-Button, der `api.checkins.update(clientId, checkinId, {mark_reviewed: true})` aufruft (bestehende API-Methode, geprüft dass sie existiert - falls das Signatur-Detail beim Implementieren abweicht, an die tatsächliche `api.checkins`-Methode anpassen) und danach die Widget-Daten neu lädt (`queryClient.invalidateQueries`). Leerer Zustand: "No pending check-ins" Text.

**Widget 3 - `NeedsAttentionWidget`:** Card mit Titel "Needs attention", Liste (`max-h-64 overflow-y-auto`) aus `needs_attention`, jede Zeile klickbar zum Klienten, zeigt Name + "{days_since_activity} days quiet" (oder "Never active" falls `null`), rötlich akzentuiert (`text-red-400`, analog zum Mockup). Leerer Zustand: "Everyone's on track" Text.

**Widget 4 - `WeekStatsWidget`:** Card mit Titel "This week", 3-spaltiges Grid mit den drei Zahlen aus `week_stats` (großer akzentfarbener Zahlwert + kleines gedämpftes Label darunter: "check-ins", "photos", "active clients").

Alle 4 Widgets laden über EINEN gemeinsamen `useQuery({ queryKey: ["dashboard", "coach-summary"], queryFn: api.dashboard.coachSummary })` im übergeordneten `Dashboard`-Component - die Daten werden als Props an die 4 Widget-Komponenten durchgereicht (kein eigener Query pro Widget, ein Request für alle vier).

## Out of Scope

- Kein neues Backend für die Klienten-Liste selbst (bestehender Endpunkt reicht).
- Keine Pagination in den Widget-Listen (feste Scroll-Höhe reicht für die erwartete Datenmenge - Coach-Accounts sind auf begrenzte Klientenzahlen pro Tarif limitiert).
- Kein Gender-Filter mehr (ersatzlos gestrichen mit dem alten Grid - YAGNI, nicht Teil der Anforderung).
- Keine Änderung an der Klienten-Detailseite/Check-in-Tab selbst - nur Wiederverwendung des bestehenden `mark_reviewed`-Mechanismus.

## Testing-Ansatz

- Backend: Unit-Tests für `GET /api/dashboard/coach-summary` - Coach mit mehreren Klienten, verifiziert `pending_checkins`-Inhalt/Sortierung, `needs_attention`-Schwelle (Klient mit Aktivität vor 6 Tagen taucht NICHT auf, vor 8 Tagen SCHON), `week_stats`-Zählungen korrekt über mehrere Klienten hinweg summiert, Ownership-Scoping (fremde Klienten tauchen nicht auf).
- Frontend: `npx tsc --noEmit`; manuelle Durchsicht (alle 4 Widgets laden, Suche filtert die Klienten-Liste, "Mark seen" entfernt einen Eintrag aus Widget 2 und lässt ihn nach Reload nicht wieder auftauchen, "Needs attention" zeigt tatsächlich stille Klienten, Wochen-Zahlen stimmen mit manuell gezählten Testdaten überein).
