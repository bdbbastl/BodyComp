# Usability-Fixes Runde 2 (Stufe 5d) — Design-Spec

**Datum:** 2026-08-18
**Status:** Genehmigt

## Kontext

Nach dem ersten echten Testlauf auf Staging/Production (Login, Onboarding, Foto-Upload) wurden vier konkrete Usability-Probleme gefunden:

1. Der "Check-ins"-Tab sowie der Magic-Link-Bereich und das Erinnerungs-Feld in den Settings werden auch bei Single-Accounts angezeigt, obwohl diese Features rein für die Coach↔Klient-Beziehung gedacht sind und für Single-Accounts (die sich selbst tracken) keinen Sinn ergeben.
2. Gewichtseingaben akzeptieren nur den Punkt als Dezimaltrennzeichen, deutsche Nutzer tippen aber gewohnheitsmäßig Komma.
3. Beim Foto-Upload gibt es keine sichtbare Rückmeldung über den Fortschritt - nur eine Button-Zustandsänderung.
4. Beim "Save all assigned" (Bulk-Zuordnung) kann der Nutzer währenddessen weiter editieren, ohne zu sehen, dass gerade etwas passiert.

## Ziel

Alle vier Punkte beheben, ohne bestehende Funktionalität für Coach-Accounts zu verändern.

## Design im Detail

### 1. Coach-only Sichtbarkeit (Check-ins-Tab, Magic-Link, Reminder)

Reine Sichtbarkeits-Umschaltung basierend auf `user.account_type === "coach"` (NICHT auf `clients.length` oder ähnlichem) - keine Datenlöschung, keine Backend-Änderung. Wechselt ein Single-Account später zum Coach, sind Magic-Link/Reminder-Konfiguration weiterhin vorhanden und sofort sichtbar.

- `ClientShell.tsx`: `NAV_ITEMS` wird gefiltert, "Check-ins" nur wenn `user.account_type === "coach"` (Desktop- UND Mobile-Nav)
- `Settings.tsx`: Check-in-Link-Block UND Reminder-Feld-Block nur wenn `!isSingleAccount` (Variable existiert bereits aus der vorherigen UX-Runde)

### 2. Gewichts-Eingabe: Komma/Punkt, 2 Nachkommastellen, Rundung auf 0,05-Schritte

Neuer Helper `frontend/src/utils/weight.ts`:
```ts
/** Parst eine Gewichts-Nutzereingabe (Komma ODER Punkt als Dezimaltrennzeichen,
 * z.B. "76,05" oder "76.05") zu einer Zahl, gerundet auf die naechsten 0,05 kg -
 * siehe Design-Spec "Usability-Fixes Runde 2". Gibt null bei leerem/ungueltigem
 * Input zurueck (== "kein Wert eingegeben", nicht "Fehler"). */
export function parseWeightInput(raw: string): number | null {
  const trimmed = raw.trim();
  if (trimmed === "") return null;
  const normalized = trimmed.replace(",", ".");
  const value = Number(normalized);
  if (!Number.isFinite(value)) return null;
  return Math.round(value / 0.05) * 0.05;
}
```
Betroffene Inputs (alle auf `type="text" inputMode="decimal"` statt `type="number"` umgestellt, Wert on-submit/on-blur durch `parseWeightInput` geschickt):
- `Timeline.tsx` `WeightEditor`
- `Unprocessed.tsx` (Gewicht pro Tag)
- `CheckinSubmit.tsx` (öffentliches Check-in-Formular)

Backend-Defensive (v.a. für den öffentlichen, unauthentifizierten Check-in-Endpoint, der nicht zwingend über unser Frontend läuft): Pydantic `@field_validator` auf `weight_kg` in den betroffenen Schemas, der einen String mit Komma zusätzlich zu einer Zahl toleriert und ebenfalls auf 0,05-Schritte rundet - selbe Rundungslogik wie im Frontend, damit beide Seiten konsistent sind.

### 3. Upload-Overlay mit Fortschrittsanzeige

Neuer `BusyOverlayContext` (`frontend/src/contexts/BusyOverlayContext.tsx`), um den App-Baum gelegt (analog `OnboardingProvider`):
```ts
interface BusyOverlayContextValue {
  show: (label: string, progressPercent?: number) => void;
  updateProgress: (progressPercent: number) => void;
  hide: () => void;
}
```
Neue Komponente `BusyOverlay.tsx`: Vollbild, abgedunkelter Hintergrund (gleicher Look wie das Onboarding-Modal), Label-Text + optionaler Fortschrittsbalken/Prozentzahl, blockiert komplett (kein Klick durch, kein Escape/Abbrechen).

`Unprocessed.tsx`s Upload-Mutation ruft `show("Uploading...", 0)` beim Start, `updateProgress(percent)` über `onUploadProgress` (axios unterstützt das nativ als Request-Option), `hide()` bei Erfolg/Fehler. `api.photos.upload` in `client.ts` bekommt dafür einen optionalen `onUploadProgress`-Parameter durchgereicht.

### 4. "Save all assigned"-Overlay

Gleicher `BusyOverlayContext`, aber ohne Fortschrittsbalken (ein einzelner Batch-Request, kein granularer Fortschritt messbar) - nur Label "Saving..." bis die Response da ist. `bulkAssignMutation` in `Unprocessed.tsx` ruft `show("Saving...")` bei Start, `hide()` bei Erfolg/Fehler.

## Out of Scope

- Kein Abbrechen-Button für laufende Uploads/Saves (explizit vom Nutzer ausgeschlossen)
- Keine Änderung an bestehenden Backend-Limits/Validierungen außer der Komma-Toleranz
- Keine generelle i18n-Zahlenformatierung (das ist reine Eingabe-Normalisierung, keine Anzeige-Formatierung)

## Testing-Ansatz

- Backend: Unit-Tests für den neuen `weight_kg`-Validator (Komma-String, Punkt-String, Rundung auf 0,05-Schritte, ungültiger String)
- Frontend: `npx tsc --noEmit`; manuelle Durchsicht (Single-Account sieht keinen Check-ins-Tab/Magic-Link/Reminder mehr, Coach-Account weiterhin schon; Gewichtseingabe mit Komma funktioniert; Upload zeigt Fortschritt; Save-all blockiert während der Anfrage)
