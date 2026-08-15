# Design-Spec: Check-in-Einreichung & Review-Workflow

## Kontext

BodyComp Tracker ist bisher ein reines Coach-Werkzeug: der Coach (bzw.
Single-Account-Nutzer) trägt alle Daten (Fotos, Gewicht, Notizen) selbst
ein — für sich selbst oder stellvertretend für seine Klienten. Es gibt
keinerlei Kommunikations- oder Review-Schicht zwischen Coach und Klient.

Ziel dieser Runde: den Coach als Hauptzielgruppe (Bodybuilding-Coaching,
oft mehrere Klienten parallel) bei der Verwaltung, Bewertung und
Rückmeldung von Klienten-Check-ins zu entlasten — ohne dabei ein volles
Klienten-Login-/Auth-System einzuführen. Klienten reichen ihre Check-ins
stattdessen über einen dauerhaften, passwortlosen Magic-Link ein.

Bewusste Entscheidung aus der Klärungsrunde: kein selbst gehostetes
Video/Audio — der Coach verlinkt stattdessen auf externe Dienste (Loom
o.ä.), die App speichert nur die URL.

## Architektur-Entscheidung

**Neues, schlankes Modell `CheckinSubmission`** als "Posteingang"-Schicht
oberhalb der bestehenden `DayLog`/`Photo`-Tabellen, statt diese direkt um
Review-Felder zu erweitern (Alternative, die verworfen wurde — siehe
unten). Eine Einreichung über den Magic-Link schreibt zusätzlich ganz
normal in `DayLog`/`Photo`, sodass Timeline/Compare/Statistics unverändert
funktionieren. `CheckinSubmission` selbst ist der Anker für Status und
Coach-Feedback.

**Verworfene Alternative:** Review-Felder direkt an `DayLog` anhängen.
Verworfen, weil nicht jeder `DayLog`-Eintrag ein zu prüfender Check-in
sein soll (z.B. rückwirkend vom Coach selbst eingetragene historische
Gewichtsdaten) — das hätte die Review-Queue verwässert. Ein separates
Modell hält "vom Klienten aktiv eingereicht, braucht Review" sauber
getrennt von "vom Coach manuell erfasst".

## Datenmodell

### `CheckinSubmission` (neu)

- `id`
- `client_id` (FK → `Client`)
- `submitted_at` (Zeitstempel der Einreichung)
- `weight_kg` (optional, float)
- `client_note` (optional, Freitext vom Klienten, kurz)
- Verknüpfung zu den beim Einreichen hochgeladenen `Photo`-Einträgen
  (gleiche Client-Scope-Logik wie bestehende Fotos)
- `status`: `pending` | `reviewed`
- `coach_feedback_text` (optional, kurzer Freitext)
- `coach_feedback_video_url` (optional, URL — kein Upload, nur Link zu
  Loom/YouTube/etc.)
- `reviewed_at` (optional, Zeitstempel)

### `Client` — neue Felder

- `checkin_token` (einmalig generiert, eindeutig, Basis des Magic-Links;
  vom Coach im Klientenprofil neu generierbar — invalidiert den alten
  Link sofort)
- `coach_private_note` (optional, Freitext, NUR für den Coach sichtbar,
  nie Teil des Klienten-Flows — für Ziele/Cues/Kontext)
- `email` (optional — Voraussetzung für Erinnerungsmails an den Klienten)
- `checkin_reminder_days` (optional int, Default 7 — nach wie vielen
  Tagen ohne neue Einreichung eine Erinnerungsmail geht; pro Klient
  einstellbar, z.B. kürzer in der Contest Prep)

## Magic-Link-Mechanismus

- Der Link hat die Form `.../checkin/{checkin_token}` und identifiziert
  eindeutig genau einen Klienten.
- Kein Passwort, kein Ablaufdatum (im Gegensatz zu den bestehenden
  Email-Verify-/Passwort-Reset-Tokens) — der Link ist als dauerhafter,
  wiederverwendbarer Zugang gedacht, den der Klient sich einmal
  bookmarkt.
- Sicherheit: der Token ist lang und zufällig genug, um nicht erratbar zu
  sein; der Coach kann ihn im Klientenprofil jederzeit neu generieren,
  falls er versehentlich geteilt wurde.
- Technisch: ein neuer, öffentlicher Router (`/api/public/checkin/...`),
  der den Token statt der bestehenden Session-Cookie-Auth prüft. Nutzt
  dieselbe Grundtechnik (signierte/zufällige Tokens) wie die bereits
  vorhandenen `EmailToken`-Flows, aber ohne deren Ablauflogik.

## Klienten-Ansicht (`/checkin/{token}`)

Eigenständige, öffentliche Seite ohne App-Login — kein `AppShell`/
`ClientShell`, kein Zugriff auf Timeline/Compare/Statistics/Settings.
Handy-tauglich, minimalistisch.

**Einreichen-Formular (oben):**
- Gewicht (optional)
- Foto-Upload (vereinfachte Variante des bestehenden Upload-Mechanismus —
  der Klient lädt nur hoch, die Posen-Zuordnung bleibt weiterhin
  Coach-Aufgabe im bestehenden Import-Screen)
- Kurze Notiz (optional)
- Absenden → legt `CheckinSubmission` (status `pending`) plus die
  zugehörigen `DayLog`-/`Photo`-Einträge an

**Historie (darunter): "Meine bisherigen Check-ins"**
- Liste, neueste zuerst: Datum, Status-Badge (⏳ Ausstehend / ✅ Geprüft)
- Bei geprüften Einträgen: Coach-Feedback-Text (falls vorhanden) und ein
  anklickbarer Video-Link (falls vorhanden)

## Coach-Ansicht

**Dashboard — Review-Queue:**
- Jede Klienten-Karte bekommt ein drittes Badge neben Fotoanzahl/letzter
  Aktivität: Anzahl offener Check-ins (z.B. "3 offene Check-ins"),
  visuell hervorgehoben wenn > 0. Erweitert dieselbe
  Aggregations-Query, die schon `photo_count`/`last_activity` liefert.
- Optionaler zusätzlicher Filter: "Nur mit offenen Check-ins".

**Neuer Tab "Check-ins"** in der `ClientShell`-Navi (neben
Timeline/Import/Compare/Statistik/Settings):
- Liste aller `CheckinSubmission`s dieses Klienten, offene zuerst
- Pro Eintrag aufklappbar: eingereichtes Gewicht/Notiz/Fotos (Vorschau)
  sowie die Antwort-Felder:
  - Kurzes Freitext-Feedback
  - Video-Link-Feld (reine URL, kein Upload)
  - Button "Als geprüft markieren" (setzt `status=reviewed`,
    `reviewed_at`)
- Compliance-Kennzahl oben auf dem Tab: z.B. "Check-in-Rate letzte 4
  Wochen: 6/8", berechnet direkt aus den vorhandenen
  `CheckinSubmission`-Zeitstempeln (kein neues Datenmodell nötig)

**Coach-Notizfeld:**
- `coach_private_note` editierbar z.B. im "Check-ins"-Tab oder in
  `Settings.tsx` — rein intern, nie Teil des Klienten-Flows

**Magic-Link-Verwaltung:**
- In `Settings.tsx`: fertiger Link zum Kopieren, Button "Link neu
  generieren"

## Benachrichtigungen (E-Mail über bestehende Resend-Anbindung)

- **Bei Einreichung:** E-Mail an den Coach ("Max hat einen neuen Check-in
  eingereicht") mit Direkt-Link zum "Check-ins"-Tab des jeweiligen
  Klienten.
- **Erinnerung an Klient:** täglicher Hintergrund-Check verschickt eine
  kurze Erinnerungsmail (mit Magic-Link) an die im `Client`-Profil
  hinterlegte `email`, wenn seit der letzten `CheckinSubmission` mehr als
  `checkin_reminder_days` Tage vergangen sind. Ohne hinterlegte
  `Client.email` wird keine Erinnerung verschickt (kein Fehlerzustand,
  einfach übersprungen).

## Ausdrücklich nicht Teil dieser Umsetzung

- Kein volles Klienten-Login/Passwort/Account — bewusst durch den
  Magic-Link ersetzt
- Kein selbst gehostetes Video/Audio — nur URL-Feld zu externen Diensten
- Keine strukturierte Bewertung (Sterne/Tags/Zahlen-Rating) — bewusst nur
  kurzer Freitext plus Video-Link
- Kein fest vorgegebener Check-in-Rhythmus (z.B. "immer wöchentlich") —
  Kadenz ist implizit durch das Einreichverhalten des Klienten bestimmt,
  nur die Erinnerungsmail-Schwelle (`checkin_reminder_days`) ist
  konfigurierbar
- Keine Posen-Zuordnung im Klienten-Upload-Formular — bleibt
  Coach-Aufgabe im bestehenden Import-Screen
- Keine Push-Benachrichtigungen — nur E-Mail
