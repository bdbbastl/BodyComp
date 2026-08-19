# Single-User-Dashboard: 4-Widget-Layout (Stufe 7e) — Design-Spec

**Datum:** 2026-08-19
**Status:** Genehmigt

## Kontext

Single-Accounts (Selbst-Tracker, kein Coach) haben aktuell KEIN Dashboard - `ClientRedirect.tsx` leitet sie direkt auf `/clients/:id/timeline` weiter. Analog zum neuen Coach-Dashboard-Widget-Layout soll es ein eigenes 4-Widget-Dashboard für Single-Accounts geben. Entwickelt mit dem Visual-Companion-Tool (Mockup-Runde bestätigt, inkl. Nachtrag: Zeitraum-Umschalter beim Gewichtstrend-Widget).

## Ziel

Neue Seite `/clients/:clientId/dashboard`, neuer erster Nav-Punkt (nur für Single-Accounts sichtbar), Login/Redirect landet dort statt auf Timeline. 4 Widgets, alle aus bereits vorhandenen `DayLog`-Daten abgeleitet - kein neues Backend nötig.

## Umfang

### Routing

- `frontend/src/App.tsx`: neue verschachtelte Route `<Route path="dashboard" element={<SingleDashboard />} />` unter `<Route path="clients/:clientId" element={<ClientShell />}>`, platziert vor `timeline` (erste Route in der Liste, analog zur Nav-Reihenfolge).
- `frontend/src/components/ClientRedirect.tsx`: Zeile `return <Navigate to={`/clients/${firstClient.id}/timeline`} replace />;` wird zu `return <Navigate to={`/clients/${firstClient.id}/dashboard`} replace />;`.

### Navigation (`frontend/src/components/ClientShell.tsx`)

Neuer erster Eintrag in `NAV_ITEMS`: `{ to: "dashboard", label: "Dashboard", icon: LayoutDashboard }` (neuer lucide-react-Import `LayoutDashboard`, ergänzt zu den bestehenden Icon-Imports). Sichtbarkeitsfilterung: NUR für Single-Accounts sichtbar (`user?.account_type === "single"`) - für Coach-Accounts bleibt die Navi wie heute (kein Dashboard-Punkt pro Klient, das Coach-Dashboard ist bereits die separate `/dashboard`-Route außerhalb des Client-Kontexts). Die bestehende `visibleNavItems`-Filterlogik (aktuell: Check-ins nur für Coaches) wird um diese zweite, umgekehrte Bedingung ergänzt.

### Neue Seite: `frontend/src/pages/SingleDashboard.tsx`

Lädt `api.dayLogs.list(clientIdNum)` (bestehender Endpunkt, keine Backend-Änderung). Layout: `grid grid-cols-1 md:grid-cols-2 gap-4`, 4 `Card`-Widgets (gleiches Muster wie das Coach-Dashboard):

**Widget 1 - Weight trend:** Zeitraum-Umschalter (gleiche 5 Optionen wie in `Statistics.tsx`: 1 Month/3 Months/6 Months/1 Year/All, gleiche Filterlogik - Tage vom neuesten Datenpunkt aus zurückgerechnet), darunter eine KOMPAKTE Inline-SVG-Sparkline (neue, einfache Komponente - NICHT die bestehende `WeightChart` aus `Statistics.tsx` wiederverwendet, da diese datei-lokal ist und für eine volle Achsen-Beschriftung ausgelegt ist, die in einem kleinen Widget zu viel Platz braucht). Kein Wert unter 2 Datenpunkten anzeigbar - dann Hinweistext "Not enough data yet."

**Widget 2 - Recent entries:** Liste der letzten 5 Tage MIT Gewichtswert (`weight_kg != null`), neueste zuerst, Format `{Datum} · {Gewicht} kg` - gleicher Listen-Stil wie die Coach-Dashboard-Widgets (`max-h-64 overflow-y-auto` falls mehr Platz gebraucht wird, hier aber ohnehin nur 5 Einträge).

**Widget 3 - Progress:** 3-Kachel-Reihe (gleiche Optik wie Coach-Dashboards "This week"-Widget): aktuelles Gewicht (neuester Eintrag), Veränderung seit dem ERSTEN je erfassten Gewichtseintrag (Vorzeichen: negativ = Abnahme, grün; positiv = Zunahme, keine Werturteil-Farbe nötig, einfach als Zahl mit Vorzeichen), Maximalgewicht über den gesamten Verlauf. Wiederverwendet dieselbe Delta/Min/Max-Berechnung wie `Statistics.tsx`s `SummaryStats` (dort als Referenz-Logik, nicht als Component-Import - eigene kleine Berechnung in der neuen Datei, da `SummaryStats` dort ebenfalls datei-lokal ist).

**Widget 4 - Quick actions:** Zwei Buttons - "Upload photos" (`Link to` `/clients/:clientId/unprocessed`), "Compare" (`Link to` `/clients/:clientId/compare`) - gleicher sekundärer Button-Stil wie im restlichen Dashboard.

## Out of Scope

- Kein neuer Backend-Endpunkt - alles aus dem bestehenden `GET /clients/:id/day-logs` abgeleitet.
- Keine Änderung an `Statistics.tsx`/`WeightChart` selbst (nur als Referenz für die Berechnungslogik genutzt, nicht importiert).
- Kein Coach-seitiges Pendant zu diesem Nav-Punkt (Coaches haben bereits ihr eigenes separates Dashboard außerhalb des Client-Kontexts).

## Testing-Ansatz

- Frontend: `npx tsc --noEmit`.
- Manuell: Single-Account einloggen, landet direkt auf `/clients/:id/dashboard` statt Timeline, neuer "Dashboard"-Nav-Punkt sichtbar (nicht bei Coach-Accounts), alle 4 Widgets zeigen plausible Daten, Zeitraum-Umschalter am Gewichtstrend funktioniert, "Not enough data yet." bei < 2 Gewichtseinträgen, Quick-Action-Buttons navigieren korrekt.
