# UX-Politur (Stufe 5a) — Design-Spec

**Datum:** 2026-08-17
**Status:** Genehmigt

## Kontext

Nach Abschluss von Stufe 4 (Billing) wurde die App produktiv genutzt. Dabei sind mehrere UX-Schwachstellen aufgefallen, die die App "unfertig" wirken lassen, obwohl sie funktional komplett ist:

- Die linke Kunden-Sidebar (`ClientShell.tsx`) wirkt lieblos: der Ein-/Ausklapp-Toggle "hängt" isoliert oben ohne klaren visuellen Rahmen
- Das Logo im Header (`AppShell.tsx`) ist reiner Text, kein Link zurück zum Dashboard
- Die Account-Seite (`Account.tsx`) ist linksbündig statt zentriert, Abschnitte gehen ohne klare Trennung ineinander über
- Leere Zustände (kein Klient, keine Check-ins, keine Fotos) zeigen aktuell nur leere Listen/Tabellen ohne Führung
- Ladezustände sind uneinheitlich (mal Spinner, mal nichts)
- Der öffentliche Check-in-Flow (Magic Link, `CheckinSubmit.tsx`) wurde nie explizit auf schmalen Viewports durchgetestet
- Das Dashboard zeigt Trial-Banner, Near-Limit-Banner, Pending-Check-ins-Hinweis und Klienten-Liste ohne erkennbare Priorität nebeneinander

## Ziel

Die bestehende Funktionalität bleibt unverändert — es geht ausschließlich um visuelle Politur und Konsistenz. Kein Feature-Umbau, keine neuen Backend-Endpunkte.

## Architektur-Entscheidung

Statt jede Seite einzeln ad-hoc zu stylen, werden drei neue wiederverwendbare Komponenten eingeführt (nach dem Vorbild des bestehenden `PageHeader`-Patterns):

- **`EmptyState`** — Icon/Emoji + Überschrift + Text + optionaler CTA-Button
- **`Skeleton`** — einfache pulsierende Platzhalter-Blöcke (Balken/Karten-Form) für Ladezustände
- **`Card`** — visueller Container mit Titel + Inhalt, für die Account-Seiten-Abschnitte

Diese leben in `frontend/src/components/` neben den bestehenden gemeinsamen Komponenten.

## Design im Detail

### 1. Navigation

**Header (`AppShell.tsx`):**
- "BodyComp Tracker"-Schriftzug wird zu einem `<Link>` (nicht `<NavLink>`, da hier keine aktive-Route-Logik nötig ist) zu `/dashboard` für Coach-Accounts bzw. `/` für Single-Accounts (nutzt die bestehende `ClientRedirect`-Logik unter `/`)
- Hover-State (leichtes Aufhellen) signalisiert Klickbarkeit

**Sidebar (`ClientShell.tsx`):**
- Toggle-Button (`«`/`»`) wandert ans untere Ende der Nav-Liste, getrennt durch einen dezenten Trennstrich (`border-t border-white/10`), statt oben isoliert zu stehen
- Die gesamte Sidebar bekommt einen leichten Hintergrund-Container (`bg-surface/40 rounded-xl p-2`), damit sie sich als zusammenhängender Block vom Content abhebt statt "nackt" im Whitespace zu stehen
- Aktiver Nav-Punkt bleibt wie bisher (`bg-accent`), nur der umgebende Rahmen wird konsistenter

### 2. Account-Seite (`Account.tsx`)

- Äußerer Container wird zentriert: `mx-auto max-w-2xl` statt der aktuellen Breite über die volle verfügbare Spalte
- Jeder bestehende Abschnitt (Account-Typ-Umschaltung, Billing-Sektion, Gemini-Key, Display-Settings) wird in die neue `Card`-Komponente gewrappt: dezenter Rahmen, Innenabstand, Abschnittsüberschrift oben
- Abstand zwischen den Cards vereinheitlicht (`space-y-6`)

### 3. Empty States (neue `EmptyState`-Komponente)

Props: `icon` (Emoji-String), `title`, `description`, optional `action` (Label + Link/Onclick).

Eingesetzt an:
- **Dashboard** ohne Klienten: 🚀 "Noch kein Klient an Bord" / "Leg deinen ersten Klienten an und starte den Check-in-Flow." / CTA "Ersten Klienten anlegen"
- **Timeline** ohne Einträge: 📸 "Hier ist noch nichts zu sehen" / "Sobald der erste Check-in oder Foto-Import da ist, taucht er hier auf."
- **Unprocessed** ohne offene Fotos: ✨ "Alles einsortiert!" / "Keine unbearbeiteten Fotos mehr übrig."
- **ClientCheckins** ohne Einreichungen: 📭 "Noch keine Einreichungen" / "Teile den Check-in-Link mit deinem Klienten."

Genaue Texte können beim Bauen noch leicht verfeinert werden, Grundton bleibt: freundlich, kurz, ein CTA wo sinnvoll.

### 4. Loading-Skeletons (neue `Skeleton`-Komponente)

- Einfache Bausteine: `SkeletonLine` (schmaler Balken), `SkeletonCard` (Karten-Form mit Bild-Platzhalter oben, Zeilen darunter) — animiert mit Tailwinds `animate-pulse`
- Ersetzt bestehende Spinner/leere Zwischenzustände in: Dashboard-Klientenliste, Timeline-Einträge, Compare-Fotoauswahl (nur beim initialen Laden, nicht bei jeder Interaktion)

### 5. Mobile-Check Magic-Link (`CheckinSubmit.tsx`)

- Manuelle Durchsicht bei schmaler Viewport-Breite (375px), Fixes für konkret gefundene Probleme (z. B. abgeschnittene Buttons, zu kleine Touch-Targets, Overflow bei langen Coach-Feedback-Texten)
- Kein neues Feature, nur Layout-Fixes am bestehenden Formular

### 6. Dashboard-Priorisierung (`Dashboard.tsx`)

Neue visuelle Reihenfolge von oben nach unten:
1. Trial-Countdown-Banner (bleibt im `AppShell`, unverändert)
2. Near-Limit-Upgrade-Banner (falls zutreffend)
3. Pending-Check-ins-Hinweis (falls vorhanden)
4. Klienten-Liste (bzw. `EmptyState` falls leer)

Aktuell stehen manche dieser Elemente nebeneinander/ungeordnet — Ziel ist eine klare vertikale Hierarchie ohne die Elemente selbst inhaltlich zu verändern.

## Out of Scope

- Keine neuen Backend-Endpunkte oder Datenmodell-Änderungen
- Keine Änderung der Farbpalette/Design-Tokens
- Keine Änderung der Sidebar-Struktur (Nav-Punkte bleiben wie sie sind, siehe Nutzer-Entscheidung: "bleibt so, will nur das Design tweaken")
- Onboarding-Wizard, Landingpage, E-Mail-Sequenzen — eigene Folge-Stufen (5b/5c/5d)

## Testing-Ansatz

Da es sich um reines Frontend-Styling handelt (kein neuer Business-Logic-Code), keine neuen Vitest/Unit-Tests nötig. Sicherstellung über:
- `npx tsc --noEmit` (Typsicherheit)
- Manuelle Durchsicht der geänderten Seiten (Screenshots/Beschreibung durch den Implementer-Subagent)
