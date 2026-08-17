# Öffentliche Landingpage (Stufe 5f) — Design-Spec

**Datum:** 2026-08-18
**Status:** Genehmigt

## Kontext

Die App hat bisher keine öffentliche Marketing-Seite - `/` ist die geschützte Auto-Weiterleitung für eingeloggte Nutzer, nicht eingeloggte landen direkt auf `/login`. Für Weiterempfehlung, SEO und einen professionellen ersten Eindruck fehlt eine echte Landingpage.

## Ziel

Eine öffentliche Landingpage unter `/`, die Coaches (Hauptzielgruppe, führt inhaltlich) und Single-Nutzer (gleichwertig sichtbare zweite Spur) anspricht und zu Signup führt. Bereits eingeloggte Nutzer werden sofort automatisch weitergeleitet, sehen die Marketing-Seite nie.

## Routing-Umbau

- `/` wird neu `Landing.tsx` (öffentlich, außerhalb `RequireAuth`)
- Die bisherige Root-Weiterleitungslogik (`ClientRedirect`) zieht von Index-`/` auf einen neuen geschützten Pfad `/app` um (bleibt inhaltlich unverändert - Coach → `/dashboard`, Single → eigener Client)
- `Landing.tsx` selbst: lädt `useCurrentUser()`, ist ein User eingeloggt → sofortiges `<Navigate to="/app" replace />`, sonst Marketing-Inhalt
- `Login.tsx`s `navigate("/")` nach erfolgreichem Login wird zu `navigate("/app")` (vermeidet unnötigen Zwischenstopp auf der Landingpage)
- `AppShell.tsx`s Logo-Link für Single-Accounts (aktuell `to="/"`) wird zu `to="/app"`

## Content-Struktur

1. **Hero** - Headline für Coaches, Subheadline erwähnt explizit auch Solo-Tracking, zwei CTAs ("Start as a coach" / "Track yourself") → beide zu `/signup`
2. **Feature-Grid** (4 Karten) - Klienten-Verwaltung + Magic-Link-Check-ins, KI-gestützter Foto-Vergleich, Verlauf & Statistiken, automatische Erinnerungen
3. **"How it works"** - 3 Schritte, Coach-Variante im Vordergrund, Single-Variante als kompakte Ergänzung
4. **Preise** - Statische Karten (Starter/Pro/Business + Single), gleiche Preise wie in `Account.tsx`s `COACH_PLANS` (als Referenz übernehmen, nicht neu erfinden), führen zu `/signup` statt Checkout (kein eingeloggter Kontext vorhanden)
5. **Schluss-CTA + Footer** - Links zu `/login`, `/datenschutz`, `/impressum`, `/agb`

**Kein** Testimonial-Bereich mit erfundenen Kundenstimmen - stattdessen ein neutraler, nicht-quantifizierter Trust-Satz.

## Design-Sprache

Bestehender App-Look (dunkler Hintergrund, Cyan-Akzent `#22d3ee`, Tailwind) - keine neue Farbpalette, keine neuen Abhängigkeiten. Freiere/größere Typografie als in der eingeloggten App üblich (Marketing-Kontext erlaubt mehr visuelle Großzügigkeit als die dichten Dashboard-Screens).

## Out of Scope

- Keine echten Kundenstimmen/Case Studies (gibt es noch nicht)
- Kein A/B-Testing, kein Tracking/Analytics auf der Landingpage
- Keine mehrsprachige Version (bleibt Englisch wie der Rest der App)
- Keine Änderung an den bestehenden Preisen selbst - reine Anzeige der schon feststehenden Beträge

## Testing-Ansatz

- Frontend: `npx tsc --noEmit`
- Manuelle Durchsicht: `/` als Gast zeigt die Landingpage, `/` als eingeloggter Nutzer leitet sofort zu `/app` weiter, Login-Flow landet korrekt in der App (nicht auf der Landingpage), alle CTA-Links funktionieren, mobile Ansicht (schmale Breite) bleibt nutzbar
