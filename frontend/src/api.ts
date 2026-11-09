import type { Attendee, Conference, Talk } from './conference';

const apiBase = (process.env.EXPO_PUBLIC_API_BASE_URL ?? 'http://localhost:8000').replace(/\/$/, '');

type JoinResponse = {
  conference_id: string;
  name: string;
  talks: Array<{
    talk_id: string;
    title: string;
    track?: string[];
    room?: string;
    start_time: string;
    end_time: string;
  }>;
};

export type OrganizerSession = { conferenceId: string; organizerToken: string; name: string };
export type ParsedTalk = {
  title: string; abstract?: string; speakers?: string[]; room?: string; track?: string[];
  start_time: string; end_time: string;
};

function venueMinutes(timestamp: string) {
  const date = new Date(timestamp);
  if (Number.isNaN(date.getTime())) return 0;
  const parts = new Intl.DateTimeFormat('en-US', {
    timeZone: 'America/Denver', hour: '2-digit', minute: '2-digit', hourCycle: 'h23',
  }).formatToParts(date);
  const value = (type: string) => Number(parts.find((part) => part.type === type)?.value ?? 0);
  return value('hour') * 60 + value('minute');
}

function conferenceId(value: string) {
  const trimmed = value.trim();
  try {
    const url = new URL(trimmed);
    const match = /^\/join\/([^/]+)$/.exec(url.pathname);
    if (match) return decodeURIComponent(match[1]);
  } catch {
    // A typed conference code is expected to be an ID, not a URL.
  }
  return trimmed;
}

export async function joinLiveConference(value: string): Promise<Conference> {
  const id = conferenceId(value);
  if (!id) throw new Error('Enter the conference code or scan its QR code.');
  const response = await fetch(`${apiBase}/join/${encodeURIComponent(id)}`);
  if (!response.ok) {
    throw new Error(response.status === 404 ? 'That conference is not available yet.' : 'Could not reach the conference server.');
  }
  const data = await response.json() as JoinResponse;
  const talks: Talk[] = data.talks.map((talk) => ({
    id: talk.talk_id,
    title: talk.title,
    track: talk.track?.join(', ') || 'Conference session',
    room: talk.room || 'Room to be announced',
    start: venueMinutes(talk.start_time),
    end: venueMinutes(talk.end_time),
  }));
  return { name: data.name, code: data.conference_id, talks };
}

export async function saveLiveProfile(
  conference: Conference,
  profile: Attendee,
  attendeeToken?: string,
) {
  const profileData = {
    conference_id: conference.code,
    name: profile.name,
    bio: profile.bio,
    interests: profile.interests.split(',').map((item) => item.trim()).filter(Boolean),
    linkedin_url: profile.linkedin || undefined,
    discovery_opt_in: profile.discoverable,
    share_resume: profile.resumePublic,
    // Time ranges are currently entered as clock times without a date/time zone. They remain
    // local until the UI collects timezone-aware timestamps for the API.
    blockout_times: [],
  };
  const headers: Record<string, string> = attendeeToken
    ? { Authorization: `Bearer ${attendeeToken}` }
    : {};
  let body: BodyInit;
  if (profile.resumeUri) {
    const file = await (await fetch(profile.resumeUri)).blob();
    const form = new FormData();
    form.append('profile', JSON.stringify(profileData));
    form.append('resume', file, profile.resumeName);
    body = form;
  } else {
    headers['Content-Type'] = 'application/json';
    body = JSON.stringify(profileData);
  }
  const response = await fetch(`${apiBase}/save-user-data`, { method: 'POST', headers, body });
  if (!response.ok) throw new Error('Could not save your profile to the conference server.');
  return response.json() as Promise<{ attendee_token?: string }>;
}

async function apiError(response: Response, fallback: string) {
  const body = await response.json().catch(() => null) as { detail?: string } | null;
  return new Error(body?.detail || fallback);
}

export async function createLiveConference(name: string): Promise<OrganizerSession> {
  const response = await fetch(`${apiBase}/conferences`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name }),
  });
  if (!response.ok) throw await apiError(response, 'Could not create the conference.');
  const body = await response.json() as { conference_id: string; organizer_token: string };
  return { conferenceId: body.conference_id, organizerToken: body.organizer_token, name };
}

export async function parseLiveSchedule(
  session: OrganizerSession, sourceUrl?: string, asset?: { uri: string; name: string },
): Promise<{ talks: ParsedTalk[]; warnings: string[] }> {
  const query = new URLSearchParams({ conference_id: session.conferenceId });
  const headers = { 'X-Organizer-Token': session.organizerToken };
  let options: RequestInit = { method: 'POST', headers };
  if (sourceUrl) query.set('source_url', sourceUrl);
  else if (asset) {
    const file = await (await fetch(asset.uri)).blob();
    const body = new FormData();
    body.append('file', file, asset.name);
    options = { ...options, body };
  } else throw new Error('Choose a schedule link, image, or PDF first.');
  const response = await fetch(`${apiBase}/upload-schedule?${query}`, options);
  if (!response.ok) throw await apiError(response, 'Could not parse the schedule.');
  return response.json() as Promise<{ talks: ParsedTalk[]; warnings: string[] }>;
}

export async function confirmLiveSchedule(session: OrganizerSession, talks: ParsedTalk[]) {
  const response = await fetch(`${apiBase}/confirm-schedule`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-Organizer-Token': session.organizerToken },
    body: JSON.stringify({ conference_id: session.conferenceId, talks }),
  });
  if (!response.ok) throw await apiError(response, 'Could not publish the schedule.');
  return response.json() as Promise<{ join_url: string; qr_code_data_url: string }>;
}
