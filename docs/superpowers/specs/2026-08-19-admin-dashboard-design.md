# Master-Admin-Dashboard — Design-Spec

**Datum:** 2026-08-19
**Status:** Genehmigt

## Kontext

Der Betreiber der App hat aktuell keinen Überblick über alle registrierten Accounts (Signups, aktive/inaktive Nutzung, Subscription-Verteilung) außer per direktem DB-Zugriff. Es gibt kein Rollen-Konzept im `User`-Modell - jeder eingeloggte User sieht nur seinen eigenen Bereich.

## Ziel

Ein eigenständiger, per direkter URL erreichbarer `/admin`-Bereich (kein sichtbarer Nav-Link), der dem Betreiber eine Übersicht über alle Accounts gibt und erlaubt, einzelne Accounts zu deaktivieren/reaktivieren.

## Backend

### `User`-Modell-Erweiterung (`backend/app/models/user.py`)

Zwei neue Spalten:

```python
is_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
```

`is_admin` wird NIE über einen API-Endpunkt gesetzt - nur manuell in der DB (kein Self-Signup-Pfad zu Admin-Rechten). `is_active` startet bei `True` für alle bestehenden und neuen Accounts (Alembic-Migration mit `server_default=true` für Bestandsdaten).

### Login-Sperre für inaktive Accounts

In `backend/app/routers/auth.py`: sowohl der Passwort-Login (`POST /auth/login`) als auch der Google-OAuth-Callback prüfen nach erfolgreicher Authentifizierung zusätzlich `user.is_active` - bei `False` wird kein Session-Cookie gesetzt, stattdessen `403` mit einer klaren Fehlermeldung ("This account has been disabled. Contact support."). Bereits bestehende Sessions eines gerade deaktivierten Accounts bleiben bis zum nächsten Login-Versuch oder Cookie-Ablauf gültig (kein aktives Session-Invalidieren nötig für v1 - konsistent mit dem bestehenden `sessions_invalidated_at`-Mechanismus, der hierfür wiederverwendet werden könnte, aber aus Scope-Gründen nicht in v1 verdrahtet wird).

### `require_admin`-Dependency (`backend/app/core/deps.py` oder wo `get_current_user` bereits liegt)

```python
def require_admin(user: User = Depends(get_current_user)) -> User:
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    return user
```

### Neuer Router `backend/app/routers/admin.py`, gemountet unter `/api/admin`, alle Routen hinter `Depends(require_admin)`

**`GET /api/admin/overview`** → `AdminOverviewOut`:
```python
class AdminOverviewOut(BaseModel):
    total_accounts: int
    single_accounts: int
    coach_accounts: int
    active_subscriptions: int
    signups_this_week: int
    signups_this_month: int
```
Alles einfache `COUNT`-Queries auf `User` (Zeitraum-Grenzen: "diese Woche" = letzte 7 Tage ab jetzt, "diesen Monat" = letzte 30 Tage ab jetzt - konsistent mit der restlichen Codebase, die überall rollierende Zeitfenster statt Kalendermonate nutzt, z.B. `services/billing.py`).

**`GET /api/admin/accounts`** → `list[AdminAccountOut]`:
```python
class AdminAccountOut(BaseModel):
    id: int
    email: str
    display_name: str
    account_type: AccountType
    created_at: datetime
    subscription_status: str | None
    subscription_tier: str | None
    client_count: int
    is_active: bool
    is_admin: bool
    last_activity_at: datetime | None
    activity_status: Literal["active", "inactive", "never"]
```
`last_activity_at` = `MAX()` über die neuesten Zeitstempel aller `DayLog.date`/`Photo.taken_at`/`CheckinSubmission.submitted_at` aller Clients dieses Users (drei separate `MAX()`-Subqueries pro Kategorie, dann in Python das jüngste Datum nehmen - kein komplexer UNION-Query nötig bei der aktuellen Datenmenge). `activity_status`: `"active"` wenn `last_activity_at` innerhalb der letzten 14 Tage, `"inactive"` wenn älter, `"never"` wenn `None` (Account ohne jede Aktivität).

**`GET /api/admin/accounts/{user_id}`** → `AdminAccountDetailOut` (erweitert `AdminAccountOut` um):
```python
class AdminAccountDetailOut(AdminAccountOut):
    clients: list[AdminClientSummaryOut]

class AdminClientSummaryOut(BaseModel):
    id: int
    name: str
    photo_count: int
    last_activity_at: datetime | None
```
404 falls `user_id` nicht existiert.

**`PATCH /api/admin/accounts/{user_id}`** — Body `{"is_active": bool}`, setzt das Feld, gibt den aktualisierten `AdminAccountOut` zurück. 404 falls `user_id` nicht existiert. Ein Admin kann sich nicht selbst deaktivieren (`user_id == current_admin.id` → 400 "Cannot deactivate your own account").

### `UserOut`-Schema (bestehend, für `/auth/me`)

Bekommt ein neues Feld `is_admin: bool`, damit das Frontend weiß, ob es den Admin-Einstieg anzeigen darf.

## Frontend

### Routing (`frontend/src/App.tsx`)

Neue, komplett eigenständige Top-Level-Route `/admin` - AUSSERHALB von `AppShell`/`ClientShell`, kein gemeinsames Layout mit dem restlichen Produkt (eigene minimalistische Seite, ähnlich isoliert wie `CheckinSubmit.tsx` heute schon ist).

### `frontend/src/components/AdminGuard.tsx`

Analog zum bestehenden Auth-Guard-Pattern: lädt den aktuellen User (`api.auth.me()`, bereits vorhanden), zeigt einen Ladezustand, und leitet mit `<Navigate to="/login" />` weg, falls kein User eingeloggt ODER `user.is_admin !== true`. Kein Unterschied in der Fehlermeldung zwischen "nicht eingeloggt" und "kein Admin" - beides landet auf der normalen Login-Seite, um keine Information über die Existenz des Admin-Bereichs preiszugeben.

### `frontend/src/pages/Admin.tsx`

- Oben: 5 Stats-Kacheln aus `GET /api/admin/overview` (Total Accounts, Single, Coach, Active Subscriptions, Signups this week/month als zwei Kacheln oder eine kombinierte - Umsetzungsdetail).
- Darunter: Tabelle aller Accounts aus `GET /api/admin/accounts` - Spalten: E-Mail, Typ, Signup-Datum, Subscription, Clients, Aktivität (farbiger Punkt/Badge: grün=active, grau=inactive, für "never" ein neutrales Icon), Status (Active/Disabled Badge).
- Einfaches Text-Suchfeld, das clientseitig nach E-Mail filtert (kein neuer Backend-Parameter nötig - Datenmenge ist klein genug für v1, siehe Out of Scope).
- Klick auf eine Zeile → `frontend/src/pages/AdminAccountDetail.tsx` unter `/admin/accounts/:userId`, lädt `GET /api/admin/accounts/{userId}`, zeigt die Client-Liste + einen "Deactivate"/"Reactivate"-Button, der `PATCH /api/admin/accounts/{userId}` aufruft und danach die Detailansicht neu lädt.

### `frontend/src/api/client.ts`

Neuer `api.admin`-Namespace: `overview()`, `listAccounts()`, `getAccount(userId)`, `setAccountActive(userId, isActive)`.

### `frontend/src/types/index.ts`

Neue Typen `AdminOverview`, `AdminAccount`, `AdminAccountDetail`, `AdminClientSummary` passend zu den Backend-Schemas oben. `User`-Typ bekommt `is_admin: boolean`.

## Out of Scope

- Keine Paginierung der Account-Liste (bei aktueller/naher Account-Zahl unnötig - als Follow-up vermerkt, falls die Nutzerzahl deutlich wächst).
- Kein Impersonate-Feature (als Admin "als User X einloggen").
- Keine Bearbeitung von Subscription/Billing-Daten aus dem Admin-Bereich (bleibt Stripe-Dashboard/Stripe-Portal).
- Kein Löschen von Accounts aus dem Admin-Bereich (bestehender Selbst-Löschweg des Users bleibt der einzige Lösch-Pfad).
- Kein Audit-Log von Admin-Aktionen (wer hat wann welchen Account deaktiviert).
- Kein aktives Invalidieren bestehender Sessions beim Deaktivieren eines Accounts (Sperre greift erst beim nächsten Login-Versuch).
- Server-seitige Such-/Sortier-Parameter für die Account-Liste (clientseitige Filterung reicht für v1).

## Testing-Ansatz

- Backend: Tests für `require_admin` (403 für Nicht-Admins, Zugriff für Admins), `GET /api/admin/overview` (korrekte Counts), `GET /api/admin/accounts` (korrekte `activity_status`-Berechnung: active/inactive/never Fälle), `GET /api/admin/accounts/{id}` (404 bei unbekannter ID), `PATCH /api/admin/accounts/{id}` (Deaktivierung, Reaktivierung, 400 bei Selbst-Deaktivierung, 404 bei unbekannter ID), Login-Ablehnung für `is_active=False` (Passwort-Pfad; Google-OAuth-Pfad ebenfalls, falls testbar ohne echten Google-Call).
- Frontend: `npx tsc --noEmit`; manuelle Durchsicht (Nicht-Admin landet beim Aufruf von `/admin` auf Login, Admin sieht Stats+Tabelle, Suche filtert, Detailseite zeigt Clients, Deactivate/Reactivate-Button funktioniert und aktualisiert die Ansicht, deaktivierter Account kann sich nicht mehr einloggen).
