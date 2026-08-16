# Design-Spec: Billing & Pläne (Stufe 4)

## Kontext

Bisher ist BodyComp Tracker komplett kostenlos, ohne jede Nutzungs-
begrenzung. Diese Runde führt echtes Billing über Stripe ein: gestaffelte
Coach-Abos nach Klientenzahl, ein nutzungsbasiertes Freikontingent für
Single-Accounts, und die technische Durchsetzung beider Modelle
(Limits, Trial, Downgrade-Verhalten). `account_type` (bereits seit
Stufe 1 vorhanden) ist der Dreh- und Angelpunkt: Coach- und
Single-Accounts bekommen unterschiedliche Billing-Logik.

Voraussetzung ist eine funktionierende Produktionsumgebung mit echter
Zahlungsabwicklung — genau das liefert Stufe 3.

## Preismodell-Struktur

**Coach-Accounts — 3 Staffeln nach Klientenzahl** (genaue Preise noch
offen, eigene Recherche):
- Starter: bis 5 Klienten
- Pro: bis 20 Klienten
- Business: unbegrenzt

**Single-Accounts — nutzungsbasiertes Freikontingent statt Zeit-Trial:**
- **2 kostenlose Check-ins, kumulativ gezählt** (nicht "aktuell
  vorhandene" Check-ins) — ein einmal verbrauchtes Kontingent wird durch
  Löschen von Check-ins NICHT zurückgesetzt. Das verhindert den
  Lösch-und-neu-anlegen-Missbrauch, den ein reines "1 aktueller
  Check-in"-Limit ermöglichen würde, und lässt gleichzeitig genug Raum,
  das Compare-Feature (braucht mindestens 2 Check-ins) im kostenlosen
  Rahmen tatsächlich auszuprobieren.
- Ab dem 3. Versuch, einen Check-in einzureichen: Paywall, ein einziges
  bezahltes Single-Abo (keine Staffelung nötig, da ein Single-Account
  strukturell immer nur einen Klienten hat).

## Trial (nur Coach-Accounts)

- **14 Tage**, nicht 30 — branchenüblicher Standard für B2B-SaaS, begrenzt
  das Missbrauchsfenster (Speicher/Rechenzeit für MediaPipe-Verarbeitung/
  E-Mail-Versand) ohne den Nutzer im Alltag mit mehreren Klienten
  einzuschränken.
- **Kreditkarte wird direkt bei Trial-Start hinterlegt** (Stripe
  `trial_period_days`), automatische Abbuchung nach Ablauf ohne
  weiteres Zutun des Nutzers. Filtert unseriöse Signups strukturell
  heraus und erhöht die Trial→zahlend-Konversion gegenüber einem
  Kein-Karte-Trial, bei dem der Nutzer am Ende aktiv etwas tun müsste.
- Single-Accounts durchlaufen KEINEN Zeit-Trial — das kumulative
  Check-in-Kontingent übernimmt strukturell dieselbe Funktion.

## Limit-Durchsetzung

- **Hartes Limit** beim Anlegen eines weiteren Klienten über der
  aktuellen Coach-Staffel hinaus: Anlegen wird serverseitig blockiert,
  Frontend zeigt "Limit erreicht" mit direktem Link zum
  Stripe-Checkout für die nächsthöhere Staffel.
- **Downgrade/Kündigung mit zu vielen Klienten** (z.B. 15 Klienten bei
  Rückstufung auf "bis 5"): überzählige Klienten werden
  **schreibgeschützt**, nicht gelöscht oder versteckt. Alle
  bestehenden Daten (Fotos, Check-ins, Timeline) bleiben einsehbar;
  neue Fotos/Check-ins für diese Klienten sind gesperrt, bis entweder
  wieder aufgestockt oder die Klientenzahl manuell reduziert wird. Kein
  Datenverlust-Schock bei einem Downgrade.
- **Fehlgeschlagene Zahlung**: Stripes eingebaute Smart-Retry-Logik
  übernimmt die Wiederholungsversuche; schlagen die endgültig fehl,
  greift derselbe Schreibschutz-Zustand wie bei einem Downgrade - kein
  separater Mechanismus nötig.

## Ausnahme: Betreiber-Account

`basti.auer@outlook.com` ist fest im Code von JEDER Billing-Prüfung
ausgenommen (unbegrenzte Klienten, kein Trial-Ablauf, keine
Check-in-Paywall) - eine einfache E-Mail-Allowlist-Konstante, die jede
Limit-Prüfung als Erstes abfragt. Bewusst eine Code-Konstante, kein
DB-Flag - für diesen einen bekannten Sonderfall ausreichend, kein
allgemeines "Accounts von Billing befreien"-Feature.

## Zahlungsanbieter & Verwaltung

- **Stripe** als alleiniger Zahlungsanbieter.
- **Stripe Customer Portal** (Stripes gehostete, fertige Oberfläche)
  für Plan-Wechsel, Kündigung, Zahlungsmittel-Verwaltung - kein Eigenbau
  einer Billing-UI. Ein Link aus `Account.tsx` öffnet das Portal in
  einem neuen Tab.
- **Stripe Webhooks** synchronisieren alle Abo-Status-Änderungen
  (Trial läuft, Zahlung erfolgreich, Zahlung fehlgeschlagen, gekündigt)
  in `User.subscription_status`/`subscription_tier`.

## Datenmodell (grob, Details im Implementierungsplan)

`User` bekommt neue Felder:
- `stripe_customer_id`
- `subscription_status` (`trialing` / `active` / `past_due` / `canceled`)
- `subscription_tier` (für Coach: `starter`/`pro`/`business`; für
  Single: `free`/`paid`)
- `trial_ends_at`
- `free_checkins_used` (kumulativer Zähler, ausschließlich für
  Single-Accounts relevant, sinkt nie)

## Ausdrücklich nicht Teil dieser Umsetzung

- Konkrete Preise pro Staffel (eigene Recherche des Nutzers, wird
  später als reine Konfiguration nachgetragen - der Code arbeitet mit
  Stripe-Preis-IDs, nicht mit hartkodierten Beträgen)
- Jährliche Abo-Laufzeiten/Rabatte (nur monatlich in dieser Runde)
- Allgemeines "Accounts von Billing befreien"-Feature (nur die eine
  hartkodierte Ausnahme oben)
- Nutzungsbasierte Abrechnung über das Klienten-Staffel-Modell hinaus
  (z.B. Abrechnung pro Foto/Speicherverbrauch)
- Eigene Rechnungs-/Abrechnungs-UI (Stripe Customer Portal übernimmt
  das vollständig)
