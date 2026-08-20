// frontend/src/contexts/CookieConsentContext.tsx
import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";

export type CookieCategory = "analytics" | "marketing";

interface StoredConsent {
  version: number;
  necessary: true;
  analytics: boolean;
  marketing: boolean;
  decided_at: string;
}

// Erhöhen, wenn sich die Cookie-Policy inhaltlich ändert (z.B. eine neue
// Kategorie kommt dazu) - ältere gespeicherte Einträge mit niedrigerer
// Version gelten dann als "noch nicht entschieden" und das Banner
// erscheint erneut. Siehe Design-Spec "Cookie Consent Banner" Abschnitt
// "Speicherung".
const CONSENT_VERSION = 1;
const STORAGE_KEY = "bodycomp_cookie_consent";

function loadStoredConsent(): StoredConsent | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as StoredConsent;
    if (parsed.version !== CONSENT_VERSION) return null;
    return parsed;
  } catch {
    return null;
  }
}

function saveConsent(consent: StoredConsent) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(consent));
  } catch {
    // localStorage kann in Private-Browsing/mit deaktiviertem Storage
    // fehlschlagen - dann zeigt das Banner beim nächsten Laden einfach
    // erneut an, kein harter Fehler nötig.
  }
}

interface CookieConsentContextValue {
  consent: StoredConsent | null;
  bannerVisible: boolean;
  acceptAll: () => void;
  rejectNonEssential: () => void;
  savePreferences: (prefs: { analytics: boolean; marketing: boolean }) => void;
  openSettings: () => void;
  hasConsent: (category: CookieCategory) => boolean;
}

const CookieConsentContext = createContext<CookieConsentContextValue | null>(null);

/** App-weites Cookie-Consent-Management - siehe Design-Spec "Cookie
 * Consent Banner". Speichert die Entscheidung in localStorage (nicht in
 * einem Cookie - vermeidet das Henne-Ei-Problem, ein Cookie fürs
 * Cookie-Consent selbst zu brauchen). Aktuell ruft noch kein Feature
 * hasConsent() auf (es gibt noch keine nicht-notwendigen Cookies/
 * Scripts), aber der Helper steht für künftige Marketing/Analytics-
 * Integrationen bereit. */
export function CookieConsentProvider({ children }: { children: ReactNode }) {
  const [consent, setConsent] = useState<StoredConsent | null>(loadStoredConsent);
  const [bannerVisible, setBannerVisible] = useState(consent === null);

  const persistAndClose = useCallback((analytics: boolean, marketing: boolean) => {
    const next: StoredConsent = {
      version: CONSENT_VERSION,
      necessary: true,
      analytics,
      marketing,
      decided_at: new Date().toISOString(),
    };
    saveConsent(next);
    setConsent(next);
    setBannerVisible(false);
  }, []);

  const acceptAll = useCallback(() => persistAndClose(true, true), [persistAndClose]);
  const rejectNonEssential = useCallback(() => persistAndClose(false, false), [persistAndClose]);
  const savePreferences = useCallback(
    (prefs: { analytics: boolean; marketing: boolean }) =>
      persistAndClose(prefs.analytics, prefs.marketing),
    [persistAndClose]
  );
  const openSettings = useCallback(() => setBannerVisible(true), []);

  const hasConsent = useCallback(
    (category: CookieCategory) => consent !== null && consent[category] === true,
    [consent]
  );

  const value = useMemo<CookieConsentContextValue>(
    () => ({
      consent,
      bannerVisible,
      acceptAll,
      rejectNonEssential,
      savePreferences,
      openSettings,
      hasConsent,
    }),
    [consent, bannerVisible, acceptAll, rejectNonEssential, savePreferences, openSettings, hasConsent]
  );

  return <CookieConsentContext.Provider value={value}>{children}</CookieConsentContext.Provider>;
}

/** Für Komponenten, die den Consent-Status lesen oder ändern wollen
 * (Banner, Footer-Link, künftige Feature-Gates via hasConsent()). */
export function useCookieConsent(): CookieConsentContextValue {
  const ctx = useContext(CookieConsentContext);
  if (!ctx) throw new Error("useCookieConsent must be used within CookieConsentProvider");
  return ctx;
}
