// Browser-local session persistence. The backend hands out bearer credentials (an attendee
// token from /save-user-data, an organizer token from /conferences) but React state alone
// loses them on refresh, Back, or a mis-tap. This module keeps them, plus in-progress drafts,
// in localStorage so a visitor can land back where they were.
//
// Limits: per browser and device only; clearing site data or a private window drops it; a
// picked file (résumé, schedule PDF) cannot be stored, so only its name is kept. Every access
// is wrapped so native (no window) or blocked storage can use the in-memory attendee list.
import { Platform } from 'react-native';

import type { OrganizerSession, ParsedTalk } from './api';
import type { Attendee } from './conference';

const VERSION = 1;
const PREFIX = 'conference-connections.';

export type StoredProfile = Omit<Attendee, 'resume'> & { resumeName?: string };

export type AttendeeSession = {
  conferenceName?: string;
  lastOpenedAt?: number;
  sample?: boolean;
  section?: string;
  draftStep?: 'about' | 'availability';
  attendeeToken?: string;
  // The profile last accepted by the server (or the demo), and any unsaved edits.
  saved?: StoredProfile;
  draft?: StoredProfile;
  // The server's recommendation payload from the last save, kept opaque so the shape can
  // change on the backend without invalidating stored sessions.
  recommendations?: Record<string, unknown>;
};

export type RememberedConference = {
  code: string;
  name: string;
  checkedIn: boolean;
  hasDraft: boolean;
  draftStep?: 'about' | 'availability';
  sample: boolean;
};

export type StoredOrganizerSession = OrganizerSession & {
  draft?: { talks: ParsedTalk[]; warnings: string[] };
  published?: boolean;
  // Event details shown on the entry pass; they live only in this organizer's browser.
  date?: string;
  venue?: string;
  description?: string;
};

function storage(): Storage | null {
  try {
    if (Platform.OS !== 'web' || typeof window === 'undefined') return null;
    return window.localStorage ?? null;
  } catch {
    return null;
  }
}

function read<T>(key: string, valid: (value: unknown) => value is T): T | undefined {
  try {
    const raw = storage()?.getItem(PREFIX + key);
    if (!raw) return undefined;
    const parsed: unknown = JSON.parse(raw);
    if (!isRecord(parsed) || parsed.v !== VERSION || !valid(parsed.data)) return undefined;
    return parsed.data;
  } catch {
    return undefined;
  }
}

function write(key: string, data: unknown): boolean {
  try {
    const store = storage();
    if (!store) return false;
    store.setItem(PREFIX + key, JSON.stringify({ v: VERSION, data }));
    return true;
  } catch {
    return false;
  }
}

function remove(key: string): void {
  try {
    storage()?.removeItem(PREFIX + key);
  } catch {
    // Nothing to clear.
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null;
}

function isString(value: unknown): value is string {
  return typeof value === 'string';
}

function isStoredProfile(value: unknown): value is StoredProfile {
  return isRecord(value) && ['name', 'email', 'bio', 'interests', 'lookingFor', 'linkedin'].every((field) => isString(value[field]))
    && typeof value.resumePublic === 'boolean' && typeof value.discoverable === 'boolean'
    && Array.isArray(value.unavailable)
    && value.unavailable.every((range) => isRecord(range) && typeof range.start === 'number' && typeof range.end === 'number')
    && (value.resumeName === undefined || isString(value.resumeName));
}

function isAttendeeSession(value: unknown): value is AttendeeSession {
  return isRecord(value)
    && (value.conferenceName === undefined || isString(value.conferenceName))
    && (value.lastOpenedAt === undefined || (typeof value.lastOpenedAt === 'number' && Number.isFinite(value.lastOpenedAt)))
    && (value.sample === undefined || typeof value.sample === 'boolean')
    && (value.section === undefined || isString(value.section))
    && (value.draftStep === undefined || value.draftStep === 'about' || value.draftStep === 'availability')
    && (value.attendeeToken === undefined || isString(value.attendeeToken))
    && (value.saved === undefined || isStoredProfile(value.saved))
    && (value.draft === undefined || isStoredProfile(value.draft))
    && (value.recommendations === undefined || (isRecord(value.recommendations) && !Array.isArray(value.recommendations)));
}

function isOrganizerSession(value: unknown): value is StoredOrganizerSession {
  return isRecord(value) && isString(value.conferenceId) && isString(value.organizerToken) && isString(value.name)
    && (value.published === undefined || typeof value.published === 'boolean')
    && ['date', 'venue', 'description'].every((field) => value[field] === undefined || isString(value[field]))
    && (value.draft === undefined || (isRecord(value.draft) && Array.isArray(value.draft.talks) && Array.isArray(value.draft.warnings)));
}

// The résumé file itself is never stored, only its name so the form can ask for it again.
export function toStoredProfile(profile: Attendee, previousResumeName?: string): StoredProfile {
  const { resume, ...rest } = profile;
  return { ...rest, resumeName: resume?.name ?? previousResumeName };
}

export function fromStoredProfile(stored: StoredProfile): { profile: Attendee; resumeName?: string } {
  const { resumeName, ...profile } = stored;
  return { profile, resumeName };
}

const attendeeKey = (conferenceId: string) => `attendee.${conferenceId}`;
const temporaryAttendees = new Map<string, AttendeeSession>();

export const attendeeSessions = {
  load(conferenceId: string): AttendeeSession | undefined {
    return temporaryAttendees.get(conferenceId) ?? read(attendeeKey(conferenceId), isAttendeeSession);
  },
  update(conferenceId: string, changes: Partial<AttendeeSession>): void {
    const current = attendeeSessions.load(conferenceId) ?? {};
    const next = { ...current, ...changes };
    // Organizer-created sample schedules only exist in the running app.
    if ((next.sample && conferenceId.startsWith('sample-')) || !write(attendeeKey(conferenceId), next)) {
      temporaryAttendees.set(conferenceId, next);
    } else {
      temporaryAttendees.delete(conferenceId);
    }
  },
  clear(conferenceId: string): void {
    temporaryAttendees.delete(conferenceId);
    remove(attendeeKey(conferenceId));
  },
  list(): RememberedConference[] {
    const codes = new Set(temporaryAttendees.keys());
    const prefix = PREFIX + attendeeKey('');
    try {
      const store = storage();
      for (let index = 0; store && index < store.length; index++) {
        const key = store.key(index);
        if (key?.startsWith(prefix)) codes.add(key.slice(prefix.length));
      }
    } catch {
      // The in-memory list still works when browser storage is unavailable.
    }
    return [...codes].flatMap((code) => {
      const session = attendeeSessions.load(code);
      if (!session || (!session.conferenceName && !session.saved && !session.draft)) return [];
      return [{
        code,
        name: session.conferenceName ?? code,
        checkedIn: !!session.saved,
        hasDraft: !!session.draft,
        draftStep: session.draftStep,
        sample: !!session.sample,
        lastOpenedAt: session.lastOpenedAt ?? 0,
      }];
    }).sort((a, b) => b.lastOpenedAt - a.lastOpenedAt || a.name.localeCompare(b.name));
  },
};

// Organizers create one conference per browser session, so a single slot is enough.
const ORGANIZER_KEY = 'organizer';

export const organizerSession = {
  load(): StoredOrganizerSession | undefined {
    return read(ORGANIZER_KEY, isOrganizerSession);
  },
  save(session: StoredOrganizerSession): void {
    write(ORGANIZER_KEY, session);
  },
  clear(): void {
    remove(ORGANIZER_KEY);
  },
};
