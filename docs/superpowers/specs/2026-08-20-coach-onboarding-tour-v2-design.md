# Coach-Onboarding-Tour v2 & Client-Löschen & Add-Client-Modal — Design

## Ziel

Drei zusammenhängende Verbesserungen: (1) der bestehende Coach-Onboarding-Tour-Wizard hat einen Klick-blockierenden Bug und deckt nur 3 von 7 wichtigen Bestandteilen ab — wird repariert und erweitert. (2) Ein neues Client-Löschen-Feature (existiert aktuell gar nicht), primär damit ein während der Tour angelegter Test-Klient am Ende sauber wieder entfernt werden kann, aber allgemein nutzbar. (3) "Add New Client" wird vom Inline-Formular zu einem Modal mit Save/Cancel/Spinner/Erfolgsmeldung, gleichzeitig vereinfacht (nur noch Name, Date of Birth, Gender - Height und das ungenutzte Start Date fallen raus).

## Teil 1: Tour-Bugfix

**Root Cause (gefunden):** `OnboardingTooltip.tsx`s äußerster Wrapper (`<div className="fixed inset-0 z-[100]">`) hat kein `pointer-events-none` - er liegt über der gesamten Seite und fängt dadurch JEDEN Klick ab, auch auf Flächen ohne sichtbaren Spotlight/Tooltip-Inhalt. Das ist der Grund, warum der "Add New Client"-Button während der Tour nicht klickbar war.

**Fix:** Wrapper bekommt `pointer-events-none`, die Tooltip-Sprechblase (die Skip/Next-Buttons enthält) bekommt explizit `pointer-events-auto` zurück. Der Spotlight-Rahmen selbst hatte schon `pointer-events-none`. Dadurch ist ab sofort die gesamte übrige Seite (inkl. des hervorgehobenen Ziel-Elements) normal klickbar, während Tooltip-Buttons weiter funktionieren.

## Teil 2: Tour-Erweiterung (alle Kern-Bestandteile)

Neue Schritt-Liste für `COACH_STEPS` (ersetzt die bisherigen 3 Schritte):

1. **Add your first client** (`dashboard-new-client`) - öffnet jetzt das neue Add-Client-Modal (siehe Teil 4). Tour bleibt offen, während das Modal offen ist.
2. **Open client settings** (`settings-nav`, neuer Tour-Anchor am "Settings"-Sidebar-Eintrag) - zeigt, wo man die Klienten-Einstellungen findet.
3. **The magic link** (`settings-checkin-link`, bereits vorhanden) - ausführlicher erklärt: was ein Magic Link ist, dass der Klient darüber ohne eigenen Account Check-ins einreichen kann, und dass der Link in den Settings jederzeit kopiert/neu generiert werden kann.
4. **Create a pose** (`settings-add-pose`, neuer Anchor am "Add pose"-Bereich in Settings.tsx) - erklärt, wofür Posen da sind (Vergleichspunkte für Fotos).
5. **Review check-ins** (`nav-checkins`, bereits vorhanden über ClientShell) - öffnet den Checkins-Tab.
6. **Give feedback** (`checkins-review-area`, neuer Anchor um den Haupt-Content-Bereich von `ClientCheckins.tsx`) - erklärt Feedback-Text/Loom-Link/"Mark reviewed", auch wenn noch keine echten Check-ins vorhanden sind (rein erklärender Text, kein Warten auf echte Daten nötig).
7. **Tour-Ende** - siehe Teil 3.

Die ursprünglich vorgeschlagene, redundante Doppelung ("Check-in-Link teilen" als eigener Schritt neben "Magic Link erklären", beide am selben Element) wird zu einem einzigen, ausführlicheren Schritt 3 zusammengefasst - zwei Tooltips auf demselben Element nacheinander wäre verwirrend, nicht hilfreich.

`OnboardingModal.tsx`s zweite Folie (Vorschau-Liste) wird entsprechend auf die 7 (bzw. für den Nutzer sichtbaren 6, da Schritt 7 kein Tooltip-Schritt sondern das Abschluss-Modal ist) Punkte aktualisiert.

## Teil 3: Tour-Ende mit Keep/Delete-Wahl

Neue `OnboardingContext`-Phase `"end"` (zusätzlich zu `"modal"`/`"tour"`/`null`). Ablauf:
- Beim Klick auf "Add New Client" während Tour-Schritt 1 wird die neu angelegte `client.id` in einem neuen Context-State `tourClientId` gemerkt.
- Wenn der letzte Tour-Schritt (6, "Give feedback") mit "Done" abgeschlossen wird, wechselt die Phase zu `"end"` statt sofort `completeMutation` auszulösen.
- Neue Komponente `OnboardingEndModal` (analog zu `OnboardingModal` gestylt) zeigt: "You're all set! Want to keep [Client Name] or delete it to start clean?" mit zwei Buttons: **"Keep this client"** (schließt Tour, `completeMutation`) und **"Delete this client"** (ruft den neuen Lösch-Endpunkt für `tourClientId` auf, Spinner während des Löschens, danach `completeMutation`, schließt Tour). Falls `tourClientId` aus irgendeinem Grund `null` ist (z.B. Tour wurde nicht bis zum Ende durchlaufen oder erneut über "Replay tour" gestartet, ohne dass Schritt 1 einen neuen Klienten anlegte), wird nur "Keep this client"/"Close" angezeigt, kein Löschen-Button.

## Teil 4: Client-Löschen (allgemeines Feature)

**Backend:** Neuer Endpunkt `DELETE /api/clients/{client_id}` (in `routers/clients.py`, hinter `get_owned_client` - ein Coach kann nur eigene Klienten löschen). Löscht zuerst alle Datei-Assets aller Fotos des Klienten (Original, Vorschau, normalisiert, Thumbnail - wiederverwendet den bestehenden `_delete_photo_files`-Helper aus `routers/photos.py`, dafür wird dieser in eine gemeinsame Datei `services/photo_files.py` verschoben und von beiden Routern importiert, um Duplikation zu vermeiden). Danach `db.delete(client)` - die Datenbank-Ebene übernimmt automatisch das kaskadierende Löschen aller abhängigen Zeilen (Photos, Poses, DayLogs, CheckinSubmissions - alle bereits mit `ondelete="CASCADE"` auf dem Foreign Key definiert, sowohl auf SQLite mit aktiviertem `PRAGMA foreign_keys=ON` als auch nativ auf Postgres in Produktion).

**Frontend:** Neue "Danger Zone"-Sektion auf `Settings.tsx`, exakt nach dem bestehenden Muster der `DangerZoneSection` in `Account.tsx` (roter `Card danger`, zweistufige Bestätigung: Klick auf "Delete client" zeigt einen Warntext + finalen "Delete permanently"-Button mit Spinner). Nach erfolgreichem Löschen: Redirect zu `/dashboard`, Klienten-Liste wird invalidiert.

Diese Lösch-Funktion wird von zwei Stellen genutzt: (a) manuell über die Settings-Seite jedes Klienten, (b) automatisch vom `OnboardingEndModal` aus Teil 3.

## Teil 5: Add-Client-Modal

`showForm`-Inline-Block auf `Dashboard.tsx` wird durch ein zentriertes Modal ersetzt (gleiches visuelles Muster wie `OnboardingModal`: `fixed inset-0` dunkles Overlay + zentrierte Karte). Formular-Felder reduziert auf **nur drei, alle untereinander**: Name (Pflichtfeld), Date of Birth (natives `<input type="date">`, liefert plattformweiten Kalender-Picker ohne neue Dependency), Gender (jetzt `<select>` statt Freitext-Input, Optionen "Male"/"Female"/"Other" - international statt nur M/W/D). **Height und Start Date entfallen ersatzlos** (Height wird nirgends verwendet und war ohnehin optional; Start Date war komplett unbenutzter toter Code - siehe Diskussion). Kein Gewichtsfeld (passt zur bestehenden Regel "Gewicht nur mit Foto-Upload", bleibt unverändert).

Modal-Verhalten: "Cancel"-Button und Klick auf den dunklen Hintergrund schließen das Modal ohne zu speichern. "Save"-Button zeigt während der Mutation einen Spinner + "Saving…", ist währenddessen disabled. Nach Erfolg: kurze grüne Erfolgsmeldung ("Client added!") für ~1.5s, dann schließt das Modal automatisch (bzw. während der Tour: bleibt die Tour-Logik wie bisher - navigiert sofort zu `/clients/:id/settings`, siehe Teil 3).

## Out of Scope

- Keine Änderungen an der Single-Account-Tour (`SINGLE_STEPS`) - nur die Coach-Tour wird erweitert.
- Kein "Undo" für gelöschte Klienten - Löschen ist endgültig, wie bei Account-Löschung auch.
- Keine Bulk-Lösch-Funktion für mehrere Klienten gleichzeitig.
