// Join links: the organizer QR encodes `${site}/join/<code>` so a phone camera opens the
// web app directly. The web build is served with an SPA fallback, so /join/<code> loads
// index.html and the app reads the code back out of the path on startup.
//
// The attendee flow keeps its step in the path too (/join/<code>, /join/<code>/availability,
// /join/<code>/plan) so a refresh restores the step and browser Back walks back through it.
import { Platform } from 'react-native';

const FALLBACK_SITE_URL = 'https://wearedevs.cnh.radarhq.io';

export type JoinStep = 'about' | 'availability' | 'plan';

function siteUrl(): string {
  const configured = process.env.EXPO_PUBLIC_SITE_URL;
  if (configured) return configured.replace(/\/+$/, '');
  if (Platform.OS === 'web' && typeof window !== 'undefined' && window.location?.origin) return window.location.origin;
  return FALLBACK_SITE_URL;
}

export function joinUrl(code: string): string {
  return `${siteUrl()}${joinPath(code)}`;
}

export function joinPath(code: string, step: JoinStep = 'about'): string {
  const base = `/join/${encodeURIComponent(code)}`;
  return step === 'about' ? base : `${base}/${step}`;
}

const JOIN_PATH = /\/join\/([^/?#]+)(?:\/([^/?#]*))?\/?(?:[?#]|$)/;
const HAS_SCHEME = /^[a-z][a-z0-9+.-]*:\/\//i;

function decodeCode(raw: string): string | null {
  try {
    return decodeURIComponent(raw).trim().toLowerCase() || null;
  } catch {
    return null;
  }
}

// Accepts a bare conference code or any URL whose path is /join/<code> (any host).
// Returns the normalized code, or null for a URL that is not a join link.
export function parseJoinCode(value: string): string | null {
  const text = value.trim();
  if (!text) return null;
  if (!HAS_SCHEME.test(text) && !text.startsWith('/')) return text.toLowerCase();
  const match = JOIN_PATH.exec(text);
  return match ? decodeCode(match[1]) : null;
}

// The code and step encoded in an app path such as /join/<code>/plan. Unknown steps fall back
// to the profile form; a bare /join (no code) returns null.
export function parseJoinPath(path: string): { code: string; step: JoinStep } | null {
  const match = JOIN_PATH.exec(path);
  const code = match ? decodeCode(match[1]) : null;
  if (!code) return null;
  const segment = match?.[2];
  return { code, step: segment === 'availability' || segment === 'plan' ? segment : 'about' };
}
