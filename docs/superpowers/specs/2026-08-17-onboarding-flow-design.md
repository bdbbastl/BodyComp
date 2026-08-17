# Onboarding-Flow (Stufe 5b) — Design-Spec

**Datum:** 2026-08-17
**Status:** Genehmigt

## Kontext

Neue Nutzer landen nach Signup/Verifizierung direkt auf einem leeren Dashboard bzw. einer leeren Timeline ohne jede Führung, was als nächstes zu tun ist. Ziel dieser Stufe: ein modernes, kurzes Onboarding, das neue Nutzer (Coach und Single) durch die ersten nötigen Schritte führt — erklärend, aber nicht überladen.

## Ziel

- Automatisch beim ersten Login ausgelöst, danach nie wieder ungefragt
- Jederzeit über die Account-Seite erneut startbar ("Tour erneut starten")
- Zwei-teiliger Ablauf: kurzes Willkommens-Modal (Ton/Vibe + Überblick) gefolgt von einer kontextuellen Tooltip-Tour direkt in der echten App
- Unterschiedlicher Inhalt für Coach- und Single-Accounts
- Saubere Übergänge/Fade-Ins (CSS/Tailwind, keine neue Animations-Library)

## Architektur-Entscheidung

Reines CSS/Tailwind für alle Übergänge (kein `framer-motion` o.ä.) — reicht für Fade/Slide-Effekte, keine neue Abhängigkeit. Der "Spotlight"-Effekt (Rest der Seite abgedunkelt, Ziel-Element hervorgehoben) wird über einen simplen CSS-Trick gebaut: ein fixiertes Overlay-Element, positioniert exakt über dem Ziel-Element (via `getBoundingClientRect`), mit einem sehr großen `box-shadow`, der den Rest des Viewports abdunkelt, ohne ein separates SVG-Masking o.ä. zu benötigen.

## Design im Detail

### 1. Backend

Neues Feld auf `User`:
```python
onboarding_completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
```
Migration analog zu den bisherigen `_PENDING_COLUMNS`-Einträgen in `core/migrations.py`.

Neuer Endpunkt `PATCH /api/auth/onboarding-complete`: setzt `onboarding_completed_at = now()` für den eingeloggten User. Wird vom Frontend genau einmal aufgerufen, wenn der Nutzer die Tour zum ersten Mal vollständig durchläuft ODER explizit überspringt (beides zählt als "gesehen" — kein erneutes automatisches Auslösen).

`UserOut`-Schema bekommt `onboarding_completed_at: datetime | None` ergänzt, damit das Frontend beim Laden weiß, ob die Tour automatisch starten soll.

### 2. Auslösung

- **Automatisch:** Sobald der eingeloggte User geladen ist (`useCurrentUser`) und `onboarding_completed_at` `null` ist, startet die Tour automatisch (Willkommens-Modal zuerst).
- **Manuell:** Neuer Button in `Account.tsx` ("Tour erneut starten") setzt nur den lokalen Tour-State zurück und startet den Ablauf erneut — ruft NICHT erneut den Backend-Endpunkt auf (der bleibt "completed", ein manueller Replay soll nicht das automatische Auslösen für zukünftige Logins wieder aktivieren).

### 3. Ablauf

**Willkommens-Modal** (zentriert, abgedunkelter Hintergrund, 2 Slides):
- Slide 1: Kurzer Willkommensgruß ("Willkommen bei BodyComp Tracker 👋"), ein Satz Kontext
- Slide 2: 3 kurze Bullet-Punkte, was als nächstes gezeigt wird (Text unterscheidet sich je nach `account_type`)
- Fade/Slide-Transition zwischen den beiden Slides (Tailwind `transition-opacity`/`transition-transform`)
- Buttons: "Weiter" (Slide 1→2), "Los geht's" (Slide 2, schließt Modal + startet Tooltip-Tour), "Überspringen" (jederzeit sichtbar, oben rechts, beendet den gesamten Onboarding-Flow sofort und ruft den Completion-Endpunkt auf)

**Tooltip-Tour** (nach dem Modal, direkt in der App):
- Abgedunkelter Hintergrund mit "Loch" um das aktuelle Ziel-Element (Spotlight-Effekt, siehe Architektur-Entscheidung)
- Sprechblase daneben (Positionierung: bevorzugt unterhalb/rechts des Ziel-Elements, mit Kollisionsvermeidung am Viewport-Rand) mit kurzem erklärendem Text
- Buttons in der Sprechblase: "Weiter" (nächster Schritt), "Tour überspringen" (bricht ab, ruft Completion-Endpunkt)
- Letzter Schritt: Button-Text wird zu "Fertig" statt "Weiter", schließt die Tour und ruft den Completion-Endpunkt

### 4. Tour-Schritte

**Coach-Accounts (3 Schritte):**
1. Dashboard → `data-tour="dashboard-new-client"` (der "Neuen Kunden anlegen"-Button) — "Hier legst du deinen ersten Klienten an."
2. Settings-Seite eines Klienten → `data-tour="settings-checkin-link"` (der Check-in-Link-Bereich) — "Diesen Link teilst du mit deinem Klienten - er kann darüber Check-ins einreichen, ganz ohne eigenen Account."
3. ClientShell-Sidebar → `data-tour="nav-checkins"` (der "Check-ins"-Nav-Punkt) — "Hier siehst du eingereichte Check-ins und kannst Feedback geben."

**Single-Accounts (3 Schritte):**
1. Unprocessed-Seite → `data-tour="unprocessed-upload"` (der "Fotos hochladen"-Button) — "Lade hier deine ersten Fortschrittsfotos hoch."
2. ClientShell-Sidebar → `data-tour="nav-timeline"` (der "Timeline"-Nav-Punkt) — "Hier siehst du deinen Verlauf über die Zeit."
3. ClientShell-Sidebar → `data-tour="nav-compare"` (der "Compare"-Nav-Punkt) — "Sobald du 2 Check-ins hast, kannst du hier Vorher/Nachher vergleichen."

Schritte, die einen Routenwechsel brauchen (z.B. Coach-Schritt 1→2: Dashboard → Klient-Settings), lösen automatisch `navigate(...)` aus (mit kurzem erklärendem Zwischentext "Weiter zu den Klienten-Einstellungen") und warten per Polling (kurzes Intervall, Timeout-Fallback), bis das Ziel-Element mit dem passenden `data-tour`-Attribut im DOM erscheint, bevor die Sprechblase gezeigt wird.

Bei Coach-Accounts ohne Klienten kann Schritt 2/3 erst erreicht werden, nachdem der Nutzer in Schritt 1 tatsächlich einen Klienten angelegt hat — die Tour pausiert an dieser Stelle (kein automatisches Weiterspringen), bis der Nutzer den Klienten wirklich erstellt hat (erkennbar an einem erfolgreichen `POST /api/clients`), und navigiert danach automatisch zur neuen Klienten-Settings-Seite.

### 5. Technische Umsetzung

- Neuer `OnboardingContext` (`frontend/src/contexts/OnboardingContext.tsx`), um den App-Baum gelegt (in `App.tsx`, oberhalb der Routen), hält: `active: boolean`, `phase: "modal" | "tour" | null`, `stepIndex: number`, plus Funktionen `start()`, `next()`, `skip()`, `restart()`
- Steps als statisches Array (getrennt für Coach/Single) mit `{ id, dataTour, route?, title, body }`
- Neue Komponenten: `OnboardingModal.tsx` (die 2 Willkommens-Slides), `OnboardingTooltip.tsx` (Spotlight + Sprechblase für die Tour)
- `data-tour`-Attribute werden an den jeweiligen bestehenden Elementen ergänzt (Dashboard-Button, Settings-Check-in-Link-Bereich, ClientShell-Nav-Punkte, Unprocessed-Upload-Button) — rein additive Attribute, keine Verhaltensänderung an diesen Elementen selbst
- Kein Server-Roundtrip pro Tour-Schritt — nur einmal beim endgültigen Abschluss/Überspringen

## Out of Scope

- Keine Analytics/Tracking, welche Tour-Schritte wie oft übersprungen werden
- Keine A/B-Tests verschiedener Tour-Varianten
- Keine Mehrsprachigkeit (bleibt wie der Rest der App: Deutsch)
- Keine Persistierung des Tour-Fortschritts bei Abbruch mitten in der Tour (bei erneutem Start beginnt sie immer von vorn)
- Keine Änderung an bestehender Funktionalität der Ziel-Elemente selbst (nur zusätzliche `data-tour`-Attribute)

## Testing-Ansatz

- Backend: Unit-Test für den neuen `/api/auth/onboarding-complete`-Endpunkt (setzt Feld korrekt, erfordert Login) + Test, dass `UserOut` das Feld korrekt zurückgibt
- Frontend: `npx tsc --noEmit` zur Typsicherheit; manuelle Durchsicht des kompletten Flows für beide Account-Typen (Auto-Start bei frischem Account, manueller Replay-Button, Skip an verschiedenen Stellen)
