// Join links: the organizer QR encodes `${site}/join/<code>` so a phone camera opens the
// web app directly. The web build is served with an SPA fallback, so /join/<code> loads
// index.html and the app reads the code back out of the path on startup.
import { Platform } from 'react-native';

const FALLBACK_SITE_URL = 'https://wearedevs.cnh.radarhq.io';

function siteUrl(): string {
  const configured = process.env.EXPO_PUBLIC_SITE_URL;
  if (configured) return configured.replace(/\/+$/, '');
  if (Platform.OS === 'web' && typeof window !== 'undefined' && window.location?.origin) return window.location.origin;
  return FALLBACK_SITE_URL;
}

export function joinUrl(code: string): string {
  return `${siteUrl()}/join/${encodeURIComponent(code)}`;
}

const JOIN_PATH = /\/join\/([^/?#]+)\/?(?:[?#]|$)/;
const HAS_SCHEME = /^[a-z][a-z0-9+.-]*:\/\//i;

// Accepts a bare conference code or any URL whose path is /join/<code> (any host).
// Returns the normalized code, or null for a URL that is not a join link.
export function parseJoinCode(value: string): string | null {
  const text = value.trim();
  if (!text) return null;
  if (!HAS_SCHEME.test(text) && !text.startsWith('/')) return text.toLowerCase();
  const match = JOIN_PATH.exec(text);
  if (!match) return null;
  try {
    return decodeURIComponent(match[1]).trim().toLowerCase() || null;
  } catch {
    return null;
  }
}

// Web only: the code in the current page's /join/<code> path, if any.
export function joinCodeFromLocation(): string | undefined {
  if (Platform.OS !== 'web' || typeof window === 'undefined') return undefined;
  return parseJoinCode(window.location.pathname) ?? undefined;
}

// Web only: drop the code from /join/<code> after a successful join so a remount of the join
// screen (e.g. "Switch conference") or a reload does not re-join. Stays on /join so the site
// router keeps showing the attendee flow. replaceState adds no history entry.
export function clearJoinPath(): void {
  if (Platform.OS !== 'web' || typeof window === 'undefined' || !JOIN_PATH.test(window.location.pathname)) return;
  window.history.replaceState(null, '', '/join');
}
