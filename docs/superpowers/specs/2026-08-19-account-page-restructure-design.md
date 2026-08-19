# Account-Seite: Neustrukturierung (Stufe 7c) — Design-Spec

**Datum:** 2026-08-19
**Status:** Genehmigt

## Kontext

Die Account-Seite (`frontend/src/pages/Account.tsx`) zeigt aktuell "Change password" und "Change email" als zwei permanent sichtbare, eigene `Card`-Blöcke unterhalb des Profil-Headers. Das wirkt unnötig sperrig, wenn man diese Aktionen nur gelegentlich braucht. Außerdem steht die Subscription/Billing-Box aktuell erst nach dem Profil-Header - sie soll ganz oben stehen.

## Ziel

1. Billing-Box (`BillingSection`) ganz oben auf der Seite.
2. "Change password" und "Change email" nicht mehr als permanente Cards, sondern als zwei Buttons direkt im Profil-Header-Kasten (unterhalb der E-Mail/"Member since"-Zeile). Klick auf einen Button blendet das zugehörige Formular INNERHALB desselben Kastens ein. Nur eine Aktion gleichzeitig offen - Klick auf den jeweils anderen Button schließt die erste und öffnet die zweite; erneuter Klick auf die aktive Aktion schließt sie wieder.

## Umfang

Alles in `frontend/src/pages/Account.tsx`, `ProfileSection`- und `Account`-Komponenten betroffen.

### Reihenfolge in `Account`

Aktuell: `PageHeader` → `ProfileSection` → `BillingSection` → "Need a refresher?" → Account-type → GeminiKeySettings → DisplaySettingsSection → DangerZoneSection.

Neu: `PageHeader` → `BillingSection` → `ProfileSection` → "Need a refresher?" → Account-type → GeminiKeySettings → DisplaySettingsSection → DangerZoneSection. (Nur `BillingSection` und `ProfileSection` tauschen die Position, alles andere bleibt gleich.)

### `ProfileSection`

Neuer State: `const [activeAction, setActiveAction] = useState<"password" | "email" | null>(null);`

Struktur des EINEN verbleibenden `Card` (ersetzt die bisherigen 3 separaten Cards - Profil-Anzeige, "Change password", "Change email"):

```
Card:
  Zeile: E-Mail (links, groß) + "Member since ..." (rechts, gedämpft) - unverändert
  Button-Zeile (nur wenn mind. 1 Button sichtbar):
    "Change password"-Button (nur wenn user.has_password) -
      onClick: setActiveAction(a => a === "password" ? null : "password")
    "Change email"-Button (nur wenn !user.has_google_account) -
      onClick: setActiveAction(a => a === "email" ? null : "email")
  Bedingter Bereich darunter (nur wenn activeAction gesetzt):
    activeAction === "password" -> das bestehende Passwort-Formular (Felder, Validierung,
      Mutation, Erfolgs-/Fehlertext) unverändert in der Logik, nur ohne die umschließende
      eigene Card (die äußere Card ist jetzt der Profil-Kasten selbst).
    activeAction === "email" -> das bestehende E-Mail-Formular (inkl. emailRequested-
      Erfolgsanzeige) unverändert in der Logik, ebenfalls ohne eigene Card.
  Nach erfolgreicher Passwort-Änderung (passwordSuccess) ODER nach Absenden der
  E-Mail-Änderungsanfrage (emailRequested gesetzt): activeAction bleibt wie es ist
  (zeigt weiterhin den Erfolgstext/-hinweis im selben Bereich) - der Nutzer schließt
  selbst über den Button, kein automatisches Zuklappen.
```

Button-Optik: sekundärer Stil (Rahmen, kein durchgängiges Akzent-Fill), analog zu anderen sekundären Buttons in der App (z.B. "Restart tour"-Button-Stil: `rounded-lg border border-white/10 px-4 py-2 text-sm font-medium text-white hover:bg-white/5`), NICHT der primäre Akzent-Button-Stil (der bleibt den Formular-Submit-Buttons selbst vorbehalten).

Alle bestehenden Datenfelder, Mutations, Fehlerbehandlung, Erfolgstexte bleiben inhaltlich exakt wie heute - diese Änderung ist rein strukturell/visuell (Sichtbarkeit + Layout), keine Logikänderung.

## Out of Scope

- Keine Änderung an den Formularfeldern selbst, Validierung, oder API-Aufrufen.
- Keine Änderung an `BillingSection`, `GeminiKeySettings`, `DisplaySettingsSection`, `DangerZoneSection` außer der Reihenfolge.
- Kein automatisches Schließen nach Erfolg (bewusste Entscheidung, siehe oben).

## Testing-Ansatz

- Frontend: `npx tsc --noEmit`.
- Manuell: Account-Seite öffnen, Billing-Box ganz oben, Profil-Kasten zeigt initial nur E-Mail + Buttons (keine Formulare), Klick auf "Change password" zeigt Passwort-Formular, Klick auf "Change email" schließt Passwort-Formular und zeigt E-Mail-Formular, erneuter Klick auf "Change email" schließt es wieder. Für Google-only-Accounts nur "Change password" sichtbar (falls Passwort vorhanden) bzw. gar keine Buttons wenn beides fehlt (unverändert bestehende Sichtbarkeitsregeln).
