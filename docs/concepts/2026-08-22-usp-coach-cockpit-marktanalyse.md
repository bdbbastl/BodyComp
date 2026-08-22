# Marktanalyse & USP-Konzept: Was BodyComp zum Muss-Haben macht

> Strategie-Dokument, kein Umsetzungs-Spec. Ziel: ein Alleinstellungsmerkmal
> identifizieren, das die App komplettiert, Desktop-Stärken nutzt und für
> Coaches von Physique-/Bodybuilding-Athleten ein echtes Kaufargument ist.
> Stand: 2026-08-22.

---

## 1. Wo wir stehen

BodyComp hat heute eine Kombination, die sonst niemand hat:

- **Pose-normalisierte Foto-Serien** (MediaPipe) — Fotos werden ausgerichtet und skaliert, statt nur nebeneinandergelegt
- **Magic-Link-Check-ins** — Athlet lädt Gewicht + Fotos hoch, ohne Account, ohne App-Download
- **KI-Analyse ("Judge Rating")** auf Bildpaaren
- **Compare mit Slider/Overlay**, Zoom, Rotation, Belichtung, Ausrichtungsraster
- Timeline, Gewichtstrend, Feedback-Loop (Text + Loom), Erinnerungen

Was fehlt: das alles ist **Werkzeug**, aber noch kein **Arbeitsablauf**. Der
Coach muss sich jeden Wochenschluss selbst durch die Klientenliste klicken,
pro Athlet die Compare-Seite manuell einrichten (Pose wählen, zwei Daten
wählen, Zoom justieren), zurücknavigieren, Feedback tippen, nächster Athlet.

---

## 2. Was der Markt macht

### Generalisten-Plattformen (Trainerize, TrueCoach, My PT Hub, Everfit)
Alles-in-einem für Personal Trainer: Programme, Ernährung, Messaging.
Fortschrittsfotos existieren, aber als Nebenschauplatz.

### Coach-fokussiert (Kahunas)
Bewirbt explizit ein **"Progress Overlay"** — zwei Fotos übereinanderlegen
per Klick. Das ist der aktuelle Marktstandard für Foto-Vergleich. Keine
Normalisierung, keine Analyse.

### KI-Körperfett-Apps (GainFrame, PhysiqueAI, bodyfatAI, LeanLens)
Schätzen Körperfett aus einem Foto. Wichtig zu verstehen: **das sind
Consumer-Apps für Einzelpersonen, kein Coach ist im Spiel.** Und die
Genauigkeit ist das bekannte Problem: ±4–5 % absoluter Fehler gegenüber
DEXA bei Einzelfotos; Licht, Haltung und Kleidung verschieben den Wert.
Die Anbieter selbst sagen: Schätzung, kein Messgerät.

**Fazit Wettbewerb:** Zwei getrennte Märkte. Die Coach-Plattformen können
Workflow, aber keine Bild-Intelligenz. Die KI-Apps können Bild-Analyse,
aber haben keinen Coach und keine konsistenten Serien. **Der Schnittpunkt
ist unbesetzt — und genau dort steht BodyComp schon.**

---

## 3. Die harte Zahl, auf der alles aufbaut

Aus der Recherche zum Check-in-Aufwand von Online-Coaches:

> Gut aufgesetzt dauert ein Check-in **2–3 Minuten** pro Klient. Mit
> Tabs und Screenshots dauert derselbe Check-in **10–15 Minuten**. Bei 50
> Klienten pro Woche ist das der Unterschied zwischen einem **90-Minuten-
> Sonntag und einem 6-Stunden-Sonntag**.
>
> Und: *"Die Langsamkeit ist nicht das Coaching. Es ist der Arbeitsablauf
> um das Coaching herum."*

Das ist das Verkaufsargument. Nicht "wir haben KI", sondern:

> **"Dein Sonntag dauert 90 Minuten statt 6 Stunden — und jede Entscheidung
> ist durch das gedeckt, was die Fotos wirklich zeigen."**

Ein Coach mit 30 Athleten à 150 €/Monat macht 4.500 €/Monat. Vier gesparte
Stunden pro Woche sind für den entweder mehr Athleten oder ein freier
Sonntag. Ein 49-€-Abo ist dagegen keine Diskussion. Genau diese Rechnung
muss die Landing-Page machen.

---

## 4. Kandidaten

### A) Coach Cockpit — Triage-Wand + Tastatur-Review *(Empfehlung)*

Zwei Bildschirme, ausdrücklich Desktop-only:

**Prep Board (Triage):** Eine Kachel-Wand aller Athleten. Pro Kachel: das
neueste Foto, ein 7-Tage-Gewichts-Sparkline, Tage seit letztem Check-in,
und ein berechneter Aufmerksamkeits-Score. Der Coach öffnet Sonntagmorgen
eine Seite und sieht auf einen Blick: drei Athleten stagnieren, zwei sind
überfällig, einer verliert zu schnell. Das ist etwas, das auf einem Handy
schlicht nicht geht — 20+ Athleten gleichzeitig im Blick.

**Review Flow (Abarbeiten):** Klick auf eine Kachel → Vollbild-Review für
diesen Athleten, alles vorbereitet:
- Links: Vergleich bereits fertig eingerichtet (diese Woche vs. letzte
  Woche vs. vor 4 Wochen vs. Prep-Start), Normalisierung schon an
- Rechts: Gewichtsverlauf mit geglättetem Trend (Wasser-Rauschen raus),
  Klienten-Notiz, Check-in-Historie
- Unten: Feedback-Feld mit **KI-Entwurf** (nutzt die vorhandene
  Gemini-Anbindung: schlägt auf Basis von Fotos + Gewichtstrend + Notiz
  einen Feedback-Text vor, den der Coach nur noch anpasst), Loom-Feld,
  Bausteine für wiederkehrende Formulierungen
- Tastatur: `J`/`K` nächster/vorheriger Athlet, `Cmd+Enter` senden und
  weiter, `1–5` Schnellbewertung. Fortschrittsanzeige "7 von 23 erledigt"

**Warum das:** Es greift die 6-Stunden-Zahl direkt an, es ist von Natur aus
Desktop (Fläche + Tastatur), und es besteht zu 80 % aus Bausteinen, die
schon existieren — Compare, KI-Analyse, Feedback-Felder, Check-in-Liste,
Gewichtsdaten. Es ist die Klammer, die aus Werkzeugen ein Produkt macht.

### B) Prep Replay — gegen die eigene letzte Prep antreten

Vergleicht den Athleten mit **sich selbst in der vorherigen Wettkampfvor-
bereitung, zum selben Zeitpunkt vor dem Wettkampf**. "Woche 8 vor dem Show
diese Prep vs. Woche 8 vor dem Show letzte Prep."

Die Recherche bestätigt: Coaches machen genau das — heute manuell mit
Foto-Ordnern. *"Je mehr Fotos du vom Athleten machst, desto mehr Referenz-
punkte hast du für künftige Vorbereitungen."*

**Warum stark:** Das hat kein Wettbewerber. Und es wird mit jedem Jahr
wertvoller, das ein Coach bei uns bleibt — die eigenen historischen Daten
sind der Wechselkosten-Graben. Braucht ein "Saison/Prep"-Konzept im
Datenmodell (Startdatum, Wettkampfdatum).

**Warum nicht als Aufmacher:** Funktioniert erst ab der zweiten Prep. Ein
Neukunde sieht davon in den ersten Monaten nichts. Perfekt als Bindung,
schwach als erstes Kaufargument.

### C) Wettkampf-Countdown mit Trend-Projektion

Athlet hat ein Wettkampfdatum. Die App rechnet den geglätteten Gewichts-
trend hoch: "Du bist 12 Wochen raus, brauchst −0,6 %/Woche, liegst bei
−0,4 % → du bist zwei Wochen hinter Plan."

**Warum stark:** Emotional das Thema, um das sich Prep-Coaching dreht.
**Vorsicht:** Nur die Gewichts-Projektion ist solide Mathematik. Eine
KI-gestützte "Kondition am Wettkampftag"-Vorhersage wäre nicht stabil
genug (Gemini liefert über mehrere Aufrufe keine konsistenten Zahlen) und
würde ins Gimmick kippen. Nur mit Gewichtstrend bauen, ehrlich beschriftet.

### D) Coach-Markup auf Fotos

Pfeile, Kreise, Notizen direkt aufs Vergleichsbild zeichnen, an den
Athleten schicken. Desktop-typisch (Maus-Präzision), Coaches machen das
heute in Instagram oder Photoshop.

**Ehrliche Einordnung:** Nettes Feature, kein Kaufargument. Gehört in den
Review-Flow eingebaut, aber trägt keine Kampagne.

### E) Veränderungs-Heatmap (regionale Bild-Differenz)

Auf dem normalisierten Bildpaar visuell markieren, *wo* sich etwas
verändert hat — Taille runter, Schultern hoch, Beine unverändert. Nicht
"Körperfett = X %", sondern relative Veränderung.

**Warum das die eigentliche technische Trumpfkarte wäre:** Die
Consumer-Apps scheitern an absoluten Werten (±4–5 %). Relative Veränderung
auf einer normalisierten Serie ist ein *deutlich* robusteres Problem — und
beantwortet die Frage, die der Coach tatsächlich hat: "Ist das echter
Fortschritt oder nur Licht und Wasser?"

**Warum nicht nächste Woche:** Bild-Differenz über Fotos mit
unterschiedlichem Licht und Hintergrund ist verrauscht. Das braucht
sorgfältige Arbeit, keinen Wochen-Sprint. Aber es ist die richtige
Richtung für Q4.

---

## 5. Empfehlung

**Nächste Woche: A (Coach Cockpit).**

Begründung:
1. **Höchster Hebel pro Aufwand** — schlägt direkt auf die 6h→90min-Zahl
   durch, die sich sofort in einen Preis übersetzen lässt
2. **Nutzt alles Gebaute** — Normalisierung, KI, Compare, Feedback,
   Check-ins existieren; es fehlt die Klammer
3. **Echt Desktop** — die Triage-Wand ist auf einem Handy unmöglich, das
   rechtfertigt die Desktop-Positionierung ohne Ausrede
4. **Realistisch in einer Woche** — überwiegend Zusammenbau plus ein neuer
   Aggregations-Endpunkt

**Danach: B (Prep Replay)** als das Feature, das niemand kopieren kann,
weil es die Datenhistorie braucht. Das ist die Kundenbindung.

**Q4: E (Veränderungs-Heatmap)** als die technische Trumpfkarte.

**Was die Positionierung wird:**

> Trainerize und Co. verwalten Klienten. BodyComp verwaltet **Physiken.**
> Ein Sonntag, ein Bildschirm, jeder Athlet in drei Minuten beurteilt —
> mit ausgerichteten Fotos statt Screenshot-Collagen.

**Was ausdrücklich NICHT gebaut wird:** eine Körperfett-Prozent-Anzeige.
Der Markt ist voll davon, die Genauigkeit trägt die Behauptung nicht, und
ein Coach, der die Zahl anzweifelt, zweifelt danach am ganzen Produkt.
Relative Veränderung ja, absolute Schätzung nein.

---

## 6. Grober Zuschnitt für die Umsetzungswoche

Falls A gewählt wird — was ungefähr zu tun wäre:

**Backend**
- Ein Aggregations-Endpunkt `GET /api/dashboard/review-queue`: liefert für
  alle offenen Check-ins in einem Rutsch die Daten, die der Review-Flow
  braucht (Athlet, aktuelle Check-in-Fotos, Vergleichsfotos der Vorwoche
  und von vor 4 Wochen, Gewichtsreihe, letzte Notiz) — damit die Oberfläche
  nicht pro Athlet nachladen muss
- Aufmerksamkeits-Score pro Athlet (überfällig, Gewicht stagniert,
  Gewicht fällt zu schnell) — reine Berechnung auf vorhandenen Daten
- Optional: KI-Feedback-Entwurf über die vorhandene Gemini-Anbindung

**Frontend**
- Neue Seite "Prep Board" (Kachel-Wand, sortiert nach Aufmerksamkeit)
- Neue Seite "Review Flow" (Vollbild pro Athlet, Tastatursteuerung)
- Wiederverwendung: Compare-Komponenten, KI-Analyse, Feedback-Felder
- Bewusst Desktop-only mit sauberem Hinweis auf kleinen Bildschirmen

**Offene Fragen für das Brainstorming:**
- Wie genau wird der Aufmerksamkeits-Score gewichtet?
- Soll der KI-Feedback-Entwurf gleich in Runde eins mit rein oder erst
  danach?
- Prep Board als neue Seite oder als Ausbau des bestehenden Dashboards?
