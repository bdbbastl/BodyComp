# Compare-Export für Social Media — Konzept (für später)

> **Status: Konzept, noch nicht geplant/umgesetzt.** Dient als Ausgangspunkt für einen künftigen Brainstorming→Plan→Umsetzungs-Durchlauf. Nicht direkt implementieren, ohne vorher nochmal durch den normalen Brainstorming-Prozess zu gehen (Details können sich bis dahin ändern).

## Ziel

Ein "Export Comparison"-Button auf der Compare-Seite, der die aktuelle Vorher/Nachher-Gegenüberstellung als EIN Bild herunterlädt — exakt im Zustand, den der Coach/User gerade eingestellt hat (Zoom, Belichtung, Drehung, Pan-Position). Gedacht für Social-Media-Posts (Instagram etc.), kein Server-Speichern, reiner Client-seitiger Export.

## Umfang

- **Beide Compare-Modi** (Side-by-Side UND Slider/Überlagerung) bekommen einen Export-Button. Im Slider-Modus wird der aktuelle Slider-Stand als Momentaufnahme exportiert (die Wisch-Interaktion geht naturgemäß verloren, das Bild zeigt den Zustand zum Klick-Zeitpunkt).
- **Zwei Seitenverhältnisse** zur Auswahl:
  - **1:1** (quadratisch) — für Instagram-Feed-Posts.
  - **4:3** (breiter, weniger Höhe) — Alternative für andere Plattformen/Formate.
- **Trennlinie** zwischen den beiden Fotos (Side-by-Side: vertikale Linie in der Mitte; im Slider-Modus ggf. keine Trennlinie nötig, da bereits überlagert - genauer Look wird beim Brainstorming geklärt).
- **Wasserzeichen-Regel** (klar bestätigt):
  - Coach-Account mit aktivem bezahltem Abo → **kein** Wasserzeichen.
  - Alle anderen Fälle → **mit** Wasserzeichen, explizit inklusive Single-Account mit aktivem bezahltem Plan (bewusste Ausnahme - Single-User zahlen zwar, aber die Wasserzeichen-Befreiung ist ausdrücklich nur für zahlende Coaches gedacht).
- **Exakter Zustand:** Zoom (`scale`/`translate` aus dem bestehenden `usePanZoom`-Hook), Belichtung (`brightness`-Filter), Rotation (`rotation`-State) - all das ist bereits pro Bild als Frontend-State auf `Compare.tsx` vorhanden (siehe `frontend/src/pages/Compare.tsx`, z.B. `brightnessX`/`brightnessY`, `rotationX`/`rotationY`, `usePanZoom()`). Export muss diese Werte 1:1 übernehmen, kein Nachbearbeiten.
- **Kein Server-Roundtrip:** Export läuft komplett im Browser (z.B. via `<canvas>` - beide Bilder werden mit ihren aktuellen CSS-Transforms/Filtern auf einen Canvas gezeichnet, dann `canvas.toBlob()` → Download-Link, kein Backend-Endpunkt nötig).

## Offene Fragen für den Brainstorming-Durchlauf

- Exakte Canvas-Umsetzung: wie werden CSS-`transform`/`filter`-Werte (die aktuell für die Live-Vorschau genutzt werden) 1:1 auf Canvas-Zeichenoperationen übertragen (Canvas kennt CSS-Filter nicht direkt, ggf. via `ctx.filter` - Browser-Support prüfen).
- Trennlinien-Stil (Farbe, Dicke, ggf. mit BodyComp-Branding) und genaues Wasserzeichen-Design/Platzierung (Ecke unten rechts? Transparenz-Grad?).
- Dateiname-Konvention für den Download.
- Ob ein Vorschau-Dialog vor dem eigentlichen Download gezeigt wird oder der Download sofort losläuft.
