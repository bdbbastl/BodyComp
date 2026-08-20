# Dashboard & Landing-Page Visual Refresh — Design

## Ziel

Das Coach-Dashboard wirkt aktuell leer/unfertig (viele Widgets zeigen wenig Inhalt, wenn gerade nichts ansteht). Die Landing-Page hat keine Grafiken. Beide Bereiche werden im selben Design-Durchlauf überarbeitet, weil sie dieselbe visuelle Richtung teilen sollen.

## Visuelle Richtung

**Richtung A — "Dark & Precise"**: bestehendes Dark-Theme der App bleibt Basis, ergänzt um einen klaren Cyan/Türkis-Akzentton (`#22d3ee`) für Datenlinien, Sparklines und CTAs. Wirkt technisch/seriös statt verspielt — passt zu einem Tool für Coaches, nicht zu einer Consumer-Fitness-App. Kein Bruch mit dem bestehenden `bg-background`/`bg-surface`-Farbsystem, nur konsequentere Nutzung von Akzentfarbe und Datenvisualisierung.

## Teil 1: Dashboard-Redesign

Betroffene Datei: `frontend/src/pages/Dashboard.tsx` (Coach-Dashboard), nutzt weiterhin `api.dashboard.coachSummary()`.

### 1. Begrüßung mit Tageszeit
Oben auf der Seite: "Guten Morgen/Tag/Abend, `{display_name}`" (Tageszeit aus lokaler Client-Uhrzeit abgeleitet: <12 Morgen, <18 Tag, sonst Abend) + eine Zeile Kontext darunter (z.B. "4 aktive Klienten · 2 Check-ins diese Woche" — Werte aus bereits vorhandenen `CoachDashboardSummary`-Feldern).

### 2. Sparklines in Kennzahlen-Widgets
Die bestehenden Zahlen-Widgets (z.B. "Aktive Klienten") bekommen zusätzlich eine kleine Balken-Sparkline (7 Werte, letzte 7 Tage). Erfordert einen neuen Backend-Wert: `active_clients_last_7_days: list[int]` (oder analog für die jeweilige Kennzahl) im `CoachDashboardSummary`-Response — pro Tag die Anzahl aktiver Klienten (aktiv = mind. 1 Check-in oder Foto-Upload an dem Tag). Rein additiv, kein Breaking Change am bestehenden Schema.

### 3. Avatare statt Text-Listen
Wo aktuell Klientennamen als reiner Text in Listen erscheinen (z.B. "Unseen check-ins"-Widget), wird links ein kleiner Avatar ergänzt. Kein eigenes Foto-Upload-Feature für Coach-Avatare — Platzhalter-Avatar mit Initialen (z.B. "AM" für "Anna Meier") in einem farbigen Kreis, deterministisch aus dem Namen abgeleitete Hintergrundfarbe. Kein Backend-Änderungsbedarf.

### 4. Positive Leerzustände
"Needs attention"-Widget zeigt bei leerem Zustand nicht mehr nichts/eine leere Fläche, sondern einen positiven Text mit grünem Haken-Icon, z.B. "✓ Alles im grünen Bereich — kein Klient überfällig". Reiner Frontend-Change (conditional rendering).

### 5. Activity-Feed Widget (neu)
Neues Widget "Zuletzt passiert": Liste der letzten 5 Ereignisse (neuer Check-in eingereicht, Feedback an Klient verschickt, neuer Klient angelegt), mit Avatar, kurzem Text und relativer Zeitangabe ("vor 3h", "gestern").

Erfordert neuen Backend-Endpunkt `GET /api/dashboard/activity-feed` (oder Erweiterung von `coach-summary`), der die letzten 5 Ereignisse über drei bestehende Tabellen zusammenführt (`CheckinSubmission.created_at`/`reviewed_at`, `Client.created_at`) und absteigend sortiert zurückgibt. Kein neues Datenmodell — reine Lese-Aggregation bestehender Tabellen.

### 6. Grafische Gesamt-Zusammenfassung
Neues Widget: Balkendiagramm "Check-ins pro Woche" über die letzten 6 Wochen, aggregiert über alle Klienten des Coaches. Erfordert Backend-Aggregation (`GROUP BY` Woche über `CheckinSubmission`), neuer Wert im `CoachDashboardSummary`-Response: `checkins_per_week: list[{week_start: date, count: int}]`.

## Teil 2: Landing-Page

Betroffene Datei: `frontend/src/pages/Landing.tsx` (bereits vorhanden, aktuell ohne Grafiken).

### Hero-Bereich
Trägt einen **echten Screenshot** der App (Dashboard-Ansicht, gestylt in einem schlichten Browser-Frame-Mockup) statt einer Illustration — glaubwürdiger, zeigt sofort den Produktwert. Der Screenshot wird händisch erstellt (Screenshot der laufenden App im finalen Design), nicht generiert — landet als statische Bilddatei unter `frontend/public/landing/`.

### Feature-Abschnitte
Darunter 2-3 Feature-Kacheln (Foto-Vergleich, Check-in per Link, ggf. weitere), jeweils mit kleinem Icon (kein Foto nötig) + kurzem Text. Icons: einfache Inline-SVGs im Akzentton, kein externes Icon-Set nötig.

### SEO-Verknüpfung
Sobald der Hero-Screenshot als Bilddatei existiert, wird `frontend/index.html` um ein `og:image`-Tag ergänzt (bisher bewusst ausgelassen, siehe `git log` — Basis-SEO wurde bereits separat umgesetzt).

## Out of Scope

- Cookie-Consent-Banner (separates Thema, vom User als eigenständiges Zukunfts-To-do markiert, nicht Teil dieser Spec)
- Analytics-Einbindung (Plausible) — separates Thema, wartet auf Plausible-Account-Erstellung durch den User
- Eigene Coach/Klienten-Profilbild-Upload-Funktion — Avatare bleiben Initialen-Platzhalter
- Redesign anderer Seiten (Timeline, Compare, Statistics) — nur Dashboard + Landing sind Teil dieses Durchlaufs
