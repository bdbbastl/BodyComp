# Client-Profil bearbeiten (Settings) — Design

## Ziel

Vervollständigt die Client-CRUD-Funktionalität im Frontend. Backend (`PATCH /api/clients/{id}` via `ClientUpdate`) unterstützt bereits Name/Geburtsdatum/Gender-Updates — es fehlte nur die UI dafür. Read (Liste/Detail), Create (Add-Client-Modal) und Delete (Danger Zone) existieren bereits.

## Design

Neue Karte **"Client Profile"** ganz oben auf `Settings.tsx`, vor dem bestehenden Magic-Link-Bereich. Drei Felder, gleiches Muster wie `AddClientModal`: Name (Text, Pflicht), Date of Birth (`type="date"`), Gender (`<select>`: Male/Female/Other). Eigener "Save"-Button, eigene Mutation (nutzt den bereits vorhandenen `updateClientMutation`-Aufbau, erweitert um die drei neuen Felder statt eine zweite Mutation zu bauen). Vorbefüllt aus `clientQuery.data` beim Laden, analog zum bestehenden `useEffect`, der schon `coachNote`/`clientEmail`/`reminderDays` vorbefüllt.

Kein Modal — Inline-Karte wie der Rest der Settings-Seite, passt zum bestehenden Muster (Magic-Link-Karte, Danger-Zone-Karte sind auch alle Inline).

## Sichtbarkeit

Anders als die coach-spezifischen Bereiche (Magic-Link, E-Mail/Reminder/Notiz) wird die neue "Client Profile"-Karte für **beide** Kontotypen gezeigt — Name/Geburtsdatum/Gender sind auch für Single-Accounts (Selbst-Tracking des eigenen Profils) relevante, sinnvoll editierbare Angaben, nur die coach-spezifischen Felder (Klienten-E-Mail, private Notiz) bleiben hinter `!isSingleAccount` versteckt.

## Out of Scope

- Keine Änderung an Height/Start Date - die bleiben wie besprochen ungenutzt/nicht editierbar (siehe frühere Design-Entscheidung im Onboarding-Tour-v2-Spec).
