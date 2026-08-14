# Design-Spec: Frontend-Konsistenz & Navigations-Überarbeitung

## Kontext

Die App ist über mehrere Umsetzungsrunden (Mandantenfähigkeit, Public Auth)
gewachsen — jede Runde hat neue Seiten/Nav-Elemente in eine einzige,
zunehmend bedingungslastige `Layout.tsx`-Komponente gepresst. Das hat zu
sichtbaren Inkonsistenzen geführt:

- Der "← Dashboard"-Link im Header taucht auch an, wenn man schon auf dem
  Dashboard ist.
- Abstände unterscheiden sich je nachdem, ob man in einem Kunden-Kontext
  ist (Navi-Leiste sichtbar) oder nicht (Dashboard/Account) — nicht durch
  Absicht, sondern weil `Layout.tsx`s Bedingungen das so ergeben.
- Jede Unterseite (Timeline, Unprocessed, Compare, Statistics, Settings,
  Dashboard, Account) hat ihre eigene, leicht abweichende
  Überschriften-/Abstands-Umsetzung.
- Die Kunden-Navi (Timeline/Import/Compare/Statistik/Settings) liegt
  horizontal oben, was bei mehr Einträgen/breiteren Labels eng wird und
  optisch nicht klar vom Account-übergreifenden Header getrennt ist.

Dieses Dokument spezifiziert eine strukturelle Überarbeitung der
Layout-Schicht (keine neuen Backend-Features) plus ein Redesign der
Kundenübersicht (Suche, Filter, modernere Karten).

## Architektur-Entscheidung

**Verschachtelte Layouts über React-Router-Nesting**, statt eine große
Bedingungs-Komponente weiter auszubauen. Zwei neue Layout-Komponenten
ersetzen das bisherige `Layout.tsx`:

- **`AppShell`** — äußerer Rahmen, identisch auf jeder eingeloggten Seite.
- **`ClientShell`** — nur aktiv innerhalb `/clients/:clientId/*`, fügt die
  vertikale Kunden-Navi + Mini-Header hinzu.

Das ist das idiomatische React-Router-v6-Muster für verschachtelte
Layouts (`<Outlet />` in `AppShell` rendert entweder direkt eine Seite
oder `ClientShell`, das wiederum seinen eigenen `<Outlet />` für die
Kunden-Unterseiten hat) und behebt die Abstands-Inkonsistenzen
strukturell: jede Seite bekommt automatisch exakt den Rahmen, der zu
ihrer Position in der Routen-Hierarchie passt, keine Bedingungen mehr
nötig.

## `AppShell` (oberer Header)

Identisch auf allen eingeloggten Seiten (Dashboard, Account, alle
Kunden-Unterseiten):

- Links: "BodyComp Tracker"-Logo/Titel
- Dashboard-Link (nur `account_type === "coach"`) — jetzt mit korrektem
  "aktuelle Seite"-Zustand: hervorgehoben und nicht klickbar (`aria-disabled`,
  keine Navigation ausgelöst), wenn man sich bereits auf `/dashboard`
  befindet. Gleiches Prinzip gilt konsequent auch für die
  `ClientShell`-Navi-Einträge weiter unten.
- Rechts: Account-Link, Logout-Button
- Fester, einheitlicher Innenabstand (`px-4 py-3 sm:px-6`, wie bisher) und
  eine einheitliche maximale Inhaltsbreite (`max-w-6xl`), die für ALLE
  Unterseiten gilt — keine Seite definiert ihre eigene Breite mehr.

Kein Kundenname, keine Kunden-Navi mehr in `AppShell` — das liegt
vollständig in `ClientShell`.

## `ClientShell` (vertikale Kunden-Navi)

Nur aktiv innerhalb `/clients/:id/*`-Routen. Struktur: zweispaltiges
Flex-Layout — Sidebar links, Inhalt rechts, darüber ein schmaler
Mini-Header über die volle Breite.

**Mini-Header** (immer sichtbar, unabhängig vom Sidebar-Zustand):
Schmaler Streifen ganz oben im Inhaltsbereich, zeigt den Namen des
aktuell ausgewählten Kunden. Bleibt sichtbar, auch wenn die Sidebar
eingeklappt ist.

**Sidebar — Desktop/breite Screens (`sm:` und größer):**
- Standardmäßig ausgeklappt, mit Toggle-Button einklappbar auf eine
  schmale Icon-only-Leiste (mehr Platz für den Inhalt)
- Zustand (ein-/ausgeklappt) wird in `localStorage` gemerkt, gilt seiten-
  und sitzungsübergreifend
- Vertikal: Timeline / Import / Compare / Statistik / Settings, aktiver
  Eintrag hervorgehoben (gleiche visuelle Sprache wie der
  Dashboard-Link-Zustand in `AppShell`)

**Sidebar — schmale Screens (unterhalb `sm:`):**
- Eingefahren auf eine schmale Leiste mit Toggle-Button
- Ausklappen legt die Navi als Overlay über den Inhalt (Content wird
  nicht verschoben, sondern verdeckt — `position: fixed` mit Backdrop)
- Schließt sich beim Klick auf einen Eintrag oder auf den Backdrop daneben

Gilt unverändert für Single-Accounts (kein Dashboard, aber derselbe
`ClientShell` in ihrem einen Kunden-Kontext).

## Gemeinsamer Seiten-Header & Abstände

Neue `PageHeader`-Komponente (`title`, optional `actions`-Slot rechts
daneben, z.B. der "Neuen Kunden anlegen"-Button auf dem Dashboard) —
ersetzt die bisherigen, leicht unterschiedlichen `<h1>`-Umsetzungen auf
Dashboard/Account/Timeline/Unprocessed/Compare/Statistics/Settings.
Einheitliche Schriftgröße, einheitlicher Abstand nach oben/unten,
einheitliche Position relativ zum Seitenrand.

Zusätzlich ein kleines Set fester Abstands-Konstanten (statt an jeder
Stelle neu gewählter Tailwind-Werte): Innenabstand des Content-Bereichs,
Abstand Header→erster Inhaltsblock, Abstand zwischen Karten/Listen-
Elementen. Alle Seiten referenzieren dieselben Werte.

## Kundenübersicht (Dashboard-Redesign)

- Suchfeld oben (Namenssuche, filtert live während des Tippens,
  rein clientseitig — die Kundenliste ist klein, kein Backend-Bedarf)
- Filter nach Geschlecht daneben (Dropdown mit den tatsächlich in der
  aktuellen Kundenliste vorkommenden Werten + "Alle")
- Modernere Karten: Name, Alter/Größe (wie bisher), zusätzlich Anzahl
  Fotos und Datum des letzten Timeline-Eintrags als Kontext-Hinweis, wer
  gerade "aktiv" ist
- Sauberer Leer-Zustand: "Noch keine Kunden — leg deinen ersten an" statt
  einer leeren Fläche
- Grid-Layout bleibt (responsive Spalten `sm:grid-cols-2 lg:grid-cols-3`),
  nur visuell aufgeräumter

**Datenbedarf**: "Anzahl Fotos" und "Datum des letzten Eintrags" existieren
aktuell nicht in `GET /api/clients` (nur Kunden-Metadaten, keine
Foto-Aggregation). Zwei Optionen:
1. Backend-Erweiterung: `ClientOut` bekommt `photo_count: int` und
   `last_activity: date | None`, berechnet in der `list_clients`-Query
   (kleine, performante Aggregation über `Photo`, kein N+1-Problem bei
   überschaubarer Kundenzahl).
2. Frontend lädt das separat pro Karte nach (N Requests) — deutlich
   schlechter, explizit nicht gewählt.

Diese Spec geht von **Option 1** aus (kleine, gezielte Backend-Erweiterung
der bestehenden `list_clients`-Query, kein neuer Endpunkt nötig).

## Betroffene Seiten (Migration auf `PageHeader` + neue Layout-Struktur)

Alle bestehenden Seiten behalten ihre fachliche Funktionalität
unverändert — nur die Rahmen-/Header-Einbindung wird umgestellt:
`Dashboard.tsx`, `Account.tsx`, `Timeline.tsx`, `Unprocessed.tsx`,
`Compare.tsx`, `Statistics.tsx`, `Settings.tsx`.

## Ausdrücklich nicht Teil dieser Umsetzung

- Keine neuen fachlichen Features auf den Unterseiten selbst (Timeline,
  Compare, etc.) — nur Rahmen/Header-Konsistenz
- Keine Backend-Suchfunktion (Suche bleibt rein clientseitig)
- Keine weiteren Filter-Kriterien als Name + Geschlecht (siehe
  Klärungsrunde) — z.B. kein Filter nach "hat Fotos"/Sortierung nach
  Aktivität, das wurde bewusst nicht gewählt
- Kein Dark/Light-Mode-Umschalter (App ist ohnehin durchgängig dunkel)
- Keine Änderung an Mobile-Breakpoints jenseits des beschriebenen
  Sidebar-Verhaltens
