# Cookie Consent Banner — Design

## Ziel

BodyComp Tracker hat aktuell nur notwendige Cookies (Session-Cookie für Login), die rechtlich keine Einwilligung brauchen. Plausible (Analytics, sobald eingebunden) ist cookie-frei und braucht ebenfalls keine Einwilligung. Trotzdem soll das Consent-Center jetzt vollständig gebaut werden, damit später hinzukommende nicht-notwendige Cookies (z.B. Marketing/Ads/Retargeting, oder ein cookie-basiertes Analytics-Tool als Ersatz für Plausible) ohne weiteren Umbau abgedeckt sind. International nutzbar, mit Fokus auf EU/DSGVO-Konformität (Opt-in statt Opt-out, granulare Kategorien, jederzeit widerrufbar).

## Kategorien

Drei Kategorien:
- **Necessary** — immer aktiv, nicht abwählbar (Session-Cookie).
- **Analytics** — optional, aktuell ungenutzt (Plausible braucht keine Cookies), aber vorbereitet für ein künftiges cookie-basiertes Analytics-Tool.
- **Marketing** — optional, aktuell ungenutzt, vorbereitet für künftige Ads/Retargeting-Pixel.

## Speicherung

Consent-Entscheidung wird **client-seitig in `localStorage`** gespeichert (Industriestandard bei Cookiebot/OneTrust/Osano — vermeidet das Henne-Ei-Problem, ein Cookie fürs Cookie-Consent selbst zu brauchen). Gespeicherter Wert ist versioniert:

```json
{
  "version": 1,
  "necessary": true,
  "analytics": false,
  "marketing": false,
  "decided_at": "2026-08-20T12:00:00.000Z"
}
```

Eine `version`-Konstante im Code steuert, ob gespeicherte Zustimmungen noch gültig sind — wird die Cookie-Policy inhaltlich geändert (z.B. eine neue Kategorie kommt dazu), erhöht man die Konstante im Code, und alle Nutzer werden beim nächsten Besuch erneut gefragt (alte, niedriger versionierte Einträge zählen nicht mehr).

## Komponenten

### `CookieConsentContext` (React Context + Provider)
Liest/schreibt den localStorage-Eintrag, stellt `consent` (aktueller Stand oder `null` falls noch nie entschieden) und Methoden `acceptAll()`, `rejectNonEssential()`, `setCategories({analytics, marketing})` bereit. Stellt außerdem `hasConsent(category)` bereit — ein Helper, den künftige Features (z.B. ein Marketing-Pixel) vor dem Laden eines Scripts abfragen können. Wird ganz oben im Component-Tree eingehängt (in `App.tsx`, neben den bestehenden Providern), damit Banner UND spätere Consent-Checks überall verfügbar sind.

### `CookieConsentBanner`
Schmale Leiste am unteren Bildschirmrand, erscheint nur wenn `consent === null` (noch nie entschieden) oder die gespeicherte `version` veraltet ist. Zeigt kurzen Erklärtext + drei Buttons:
- **Accept all** — setzt alle Kategorien auf `true`, schließt Banner.
- **Reject non-essential** — nur `necessary: true`, Rest `false`, schließt Banner.
- **Customize** — klappt zwei Toggles auf (Analytics, Marketing; Necessary immer an und disabled), plus ein "Save preferences"-Button darunter.

Text auf Englisch (konsistent mit dem Rest der App-UI). Rendert auf allen Seiten (Landing, Login, App), da auch eingeloggte Nutzer entscheiden müssen.

### Footer-Link "Cookie settings"
Ein dauerhafter Link im Footer der Landing-Page (`frontend/src/pages/Landing.tsx`, neben den bestehenden Legal-Links "Legal notice"/"Privacy"/"Terms") öffnet das Banner erneut im "Customize"-Zustand, damit Nutzer ihre Wahl jederzeit ändern können (DSGVO-Anforderung: Widerruf muss so einfach sein wie die Erteilung).

## Out of Scope

- Kein tatsächliches Gaten von Scripts hinter Consent-Kategorien — es gibt aktuell keine nicht-notwendigen Cookies/Scripts zu gaten. `hasConsent()` wird bereitgestellt, aber noch nirgends aufgerufen; das passiert erst, wenn ein konkretes Feature (z.B. Marketing-Pixel) eingebaut wird.
- Keine serverseitige Consent-Speicherung/-Auswertung (kein Consent-Cookie, kein Backend-Endpunkt) — reines Frontend-Feature.
- Keine Mehrsprachigkeit des Banners — Englisch, wie der Rest der App.
- Keine Änderung an Plausible-Einbindung (separates Thema, wartet auf Account-Erstellung durch den User).
