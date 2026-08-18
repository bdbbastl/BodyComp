# Sidebar-Redesign (Stufe 6b) — Design-Spec

**Datum:** 2026-08-18
**Status:** Genehmigt

## Kontext

Die bestehende vertikale Kunden-Navi (`ClientShell.tsx`, sichtbar auf allen `/clients/:id/*`-Seiten) nutzt Emoji-Icons, flache ungruppierte Nav-Punkte und einen isoliert unten stehenden Ein-/Ausklapp-Button. Der Nutzer empfindet das als "tot langweilig" und "veraltet" und wünscht ein modernes visuelles Redesign. Erarbeitet mit dem Visual-Companion-Tool (mehrere Mockup-Runden, siehe Chat-Verlauf).

## Ziel

Rein visuelles Redesign der bestehenden Navi - gleiche Nav-Punkte, gleiche Routing-/Kollaps-/Coach-Filter-Logik, aber modernere Optik: echte Outline-Icons statt Emoji, gruppierte Nav-Punkte mit Trennlinien, ein klarerer aktiver Zustand, und ein als eigene Kopfzeile gestalteter Ein-/Ausklapp-Toggle.

## Scope

**Betroffen:** Nur `frontend/src/components/ClientShell.tsx` (Desktop-Sidebar UND Mobile-Overlay-Navi, beide nutzen dieselben `NAV_ITEMS`).
**Nicht betroffen:** `AppShell.tsx` (oberer horizontaler Header mit Logo/Account/Logout) bleibt unverändert. Keine Änderung an Routing, `data-tour`-Attributen (Onboarding-Tour), Coach-only-Sichtbarkeitsfilterung, oder der Kollaps-Zustand-Persistenz (`localStorage`).

## Visuelles Design

### Icons

Neue Abhängigkeit `lucide-react` (leichtgewichtig, tree-shakeable, MIT-lizenziert) ersetzt die Emoji in `NAV_ITEMS`:

| Nav-Punkt | Bisher | Neu (lucide-react) |
|---|---|---|
| Timeline | 📅 | `Calendar` |
| Check-ins | ✅ | `ListChecks` |
| Import | 📥 | `Upload` |
| Compare | 🔍 | `GitCompare` |
| Statistics | 📊 | `BarChart3` |
| Settings | ⚙️ | `Settings` |

### Gruppierung

Die 6 Nav-Punkte werden in 3 Cluster geteilt, getrennt durch dünne Trennlinien (`border-white/10`, wie im bestehenden Toggle-Trennstrich-Stil):

1. Timeline, Check-ins, Import
2. Compare, Statistics
3. Settings

(Check-ins bleibt weiterhin nur für Coach-Accounts sichtbar - die bestehende Filterung von `visibleNavItems` ändert nichts an dieser Gruppen-Zuordnung, ein Single-Account sieht einfach Gruppe 1 ohne den mittleren Punkt.)

### Aktiver Zustand

- 2px durchgezogener Cyan-Balken (`accent`-Farbe) links am aktiven Item, plus transparent-cyaner Hintergrund-Wash (`bg-accent/10`), rechts abgerundet (`rounded-r-lg`, linke Seite eckig wegen des Balkens).
- Icon und Text in Cyan (`text-accent`).
- Inaktive Items: 2px transparenter Balken (reserviert, damit beim Zustandswechsel nichts springt), graue Icon-/Textfarbe (`text-slate-400`), Hover hellt auf `hover:text-white` auf - wie im Rest der App bereits üblich.

### Toggle-Kopfzeile

Der bisherige, isoliert unten stehende `«`/`»`-Button wird durch eine Kopfzeile ÜBER den Nav-Punkten ersetzt:
- Eigene Zeile ganz oben in der Sidebar: Hamburger-Icon (`lucide-react` `Menu`) links, daneben das Label "Navigation" (klein, gedämpft, `text-slate-400`, `text-xs font-medium`).
- Darunter eine Trennlinie (gleicher Stil wie die Gruppentrenner), dann erst die Nav-Punkte.
- Klick auf die gesamte Kopfzeile (nicht nur das Icon) toggelt ein-/ausgeklappt - größere Klickfläche als der bisherige kleine Button.
- Im eingeklappten Zustand (`w-14`): Label verschwindet, nur das zentrierte Hamburger-Icon bleibt sichtbar - exakt wie die Nav-Icons darunter sich im eingeklappten Zustand verhalten (bereits bestehende Logik, wird für die Kopfzeile übernommen).

### Mobile-Overlay

Die mobile Overlay-Navi (eigener `<nav>`-Block mit denselben `NAV_ITEMS`) bekommt dieselbe visuelle Behandlung (Icons, Gruppierung, aktiver Zustand) für Konsistenz - keine Toggle-Kopfzeile nötig, da die mobile Navi ohnehin nur im ausgeklappten Zustand existiert (Overlay öffnet/schließt komplett, kein Kollaps-Mechanismus dort).

## Out of Scope

- Kein Umbau von `AppShell.tsx` zu einer durchgehenden App-weiten Sidebar (explizit ausgeschlossen).
- Keine neuen Nav-Punkte, keine Änderung an Routing/Logik.
- Keine Änderung an der Kollaps-Persistenz (`localStorage`-Schlüssel bleibt).

## Testing-Ansatz

- Frontend: `npx tsc --noEmit`.
- Manuelle Durchsicht: Desktop-Sidebar (ein-/ausgeklappt) für Coach- UND Single-Account, Mobile-Overlay, aktiver Zustand auf jeder der 6 Unterseiten, Toggle-Kopfzeile klickbar über die gesamte Zeile, Hover-Zustände auf inaktiven Items.
