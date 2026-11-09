// Tiny path router. On web the address bar is the source of truth (History API + popstate);
// on native the path is plain component state. No router dependency.
import { useCallback, useEffect, useState } from 'react';
import { Platform } from 'react-native';

export type Page = 'home' | 'events' | 'talks' | 'organizers' | 'join' | 'myConferences';

export const paths: Record<Page, string> = {
  home: '/',
  events: '/events',
  talks: '/talks',
  organizers: '/organizers',
  join: '/join',
  myConferences: '/my-conferences',
};

// /join and /join/<code> both belong to the attendee flow; unknown paths fall back to home.
export function pageForPath(path: string): Page {
  const clean = path.replace(/\/+$/, '') || '/';
  if (clean === '/join' || clean.startsWith('/join/')) return 'join';
  const match = (Object.keys(paths) as Page[]).find((page) => paths[page] === clean);
  return match ?? 'home';
}

const isWeb = Platform.OS === 'web' && typeof window !== 'undefined';

function currentPath(): string {
  return isWeb ? window.location.pathname : '/';
}

export function useRoute() {
  const [path, setPath] = useState(currentPath);

  useEffect(() => {
    if (!isWeb) return;
    const onPop = () => setPath(window.location.pathname);
    window.addEventListener('popstate', onPop);
    return () => window.removeEventListener('popstate', onPop);
  }, []);

  // `replace` swaps the current entry instead of pushing one, for redirects (e.g. a returning
  // attendee sent straight to their plan) that should not add a Back stop.
  const navigate = useCallback((next: string, options?: { replace?: boolean }) => {
    if (isWeb && window.location.pathname !== next) {
      if (options?.replace) window.history.replaceState(null, '', next);
      else window.history.pushState(null, '', next);
    }
    setPath(next);
    if (isWeb) window.scrollTo?.(0, 0);
  }, []);

  return { path, page: pageForPath(path), navigate };
}
