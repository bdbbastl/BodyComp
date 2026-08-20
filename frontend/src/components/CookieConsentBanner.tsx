// frontend/src/components/CookieConsentBanner.tsx
import { useEffect, useState } from "react";
import { useCookieConsent } from "../contexts/CookieConsentContext";

/** Schmales Consent-Banner am unteren Bildschirmrand - siehe Design-Spec
 * "Cookie Consent Banner" Abschnitt "CookieConsentBanner". Wird einmal in
 * App.tsx eingehängt (analog zu BusyOverlay) und rendert dadurch auf
 * jeder Seite - auch eingeloggte Nutzer müssen entscheiden. */
export function CookieConsentBanner() {
  const { bannerVisible, consent, acceptAll, rejectNonEssential, savePreferences } = useCookieConsent();
  const [customizing, setCustomizing] = useState(false);
  const [analytics, setAnalytics] = useState(consent?.analytics ?? false);
  const [marketing, setMarketing] = useState(consent?.marketing ?? false);

  useEffect(() => {
    if (bannerVisible) {
      setAnalytics(consent?.analytics ?? false);
      setMarketing(consent?.marketing ?? false);
      setCustomizing(false);
    }
  }, [bannerVisible, consent]);

  if (!bannerVisible) return null;

  return (
    <div className="fixed inset-x-0 bottom-0 z-50 border-t border-white/10 bg-surface px-4 py-4 shadow-2xl shadow-black/40 sm:px-6">
      <div className="mx-auto flex max-w-4xl flex-col gap-3">
        <p className="text-sm text-slate-300">
          We use necessary cookies to run this site. With your permission, we'd also like to use
          optional cookies for analytics and marketing - you can change this anytime.
        </p>

        {customizing && (
          <div className="space-y-2 rounded-lg border border-white/10 bg-black/20 p-3">
            <label htmlFor="cookie-necessary" className="flex items-center justify-between text-sm text-slate-300">
              <span>
                Necessary <span className="text-slate-500">(always on)</span>
              </span>
              <input id="cookie-necessary" type="checkbox" checked disabled className="h-4 w-4" aria-label="Necessary cookies (always enabled)" />
            </label>
            <label htmlFor="cookie-analytics" className="flex items-center justify-between text-sm text-slate-300">
              <span>Analytics</span>
              <input
                id="cookie-analytics"
                type="checkbox"
                checked={analytics}
                onChange={(e) => setAnalytics(e.target.checked)}
                className="h-4 w-4"
              />
            </label>
            <label htmlFor="cookie-marketing" className="flex items-center justify-between text-sm text-slate-300">
              <span>Marketing</span>
              <input
                id="cookie-marketing"
                type="checkbox"
                checked={marketing}
                onChange={(e) => setMarketing(e.target.checked)}
                className="h-4 w-4"
              />
            </label>
          </div>
        )}

        <div className="flex flex-wrap items-center gap-2">
          {customizing ? (
            <button
              type="button"
              onClick={() => savePreferences({ analytics, marketing })}
              className="rounded-lg bg-accent px-4 py-2 text-sm font-medium text-slate-900 hover:opacity-90"
            >
              Save preferences
            </button>
          ) : (
            <>
              <button
                type="button"
                onClick={acceptAll}
                className="rounded-lg bg-accent px-4 py-2 text-sm font-medium text-slate-900 hover:opacity-90"
              >
                Accept all
              </button>
              <button
                type="button"
                onClick={rejectNonEssential}
                className="rounded-lg border border-white/15 px-4 py-2 text-sm font-medium text-white hover:bg-white/5"
              >
                Reject non-essential
              </button>
              <button
                type="button"
                onClick={() => setCustomizing(true)}
                className="rounded-lg border border-white/15 px-4 py-2 text-sm font-medium text-white hover:bg-white/5"
              >
                Customize
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
