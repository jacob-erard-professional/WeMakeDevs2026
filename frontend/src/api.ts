import { Platform } from 'react-native';

import { API_BASE_URL as apiBase } from './apiBase';
import type { Attendee, Conference, ResumeAsset, Talk } from './conference';

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
  const parts = new Intl.DateTimeFormat('en-US', {
    timeZone: 'America/Denver', hour: '2-digit', minute: '2-digit', hourCycle: 'h23',
  }).formatToParts(new Date(timestamp));
  const value = (type: string) => Number(parts.find((part) => part.type === type)?.value ?? 0);
  return value('hour') * 60 + value('minute');
}

// `id` is a bare conference id; callers normalize join links with parseJoinCode first.
export async function joinLiveConference(id: string): Promise<Conference> {
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

async function resumePart(resume: ResumeAsset): Promise<Blob | { uri: string; name: string; type: string }> {
  const type = resume.mimeType || 'application/pdf';
  if (Platform.OS !== 'web') return { uri: resume.uri, name: resume.name, type };
  // Web: the picker hands over the File directly; fall back to reading the blob: URI.
  return resume.file ?? new Blob([await (await fetch(resume.uri)).arrayBuffer()], { type });
}

export async function saveLiveProfile(
  conference: Conference,
  profile: Attendee,
  attendeeToken?: string,
) {
  const payload = {
    conference_id: conference.code,
    name: profile.name,
    email: profile.email.trim() || undefined,
    bio: profile.bio,
    interests: profile.interests.split(',').map((item) => item.trim()).filter(Boolean),
    looking_for: profile.lookingFor.trim(),
    linkedin_url: profile.linkedin || undefined,
    discovery_opt_in: profile.discoverable,
    // Time ranges are currently entered as clock times without a date/time zone. They remain
    // local until the UI collects timezone-aware timestamps for the API.
    blockout_times: [],
  };
  // /save-user-data takes multipart with a JSON `profile` field plus an optional `resume` file.
  // Let fetch set Content-Type so the multipart boundary is included.
  const body = new FormData();
  body.append('profile', JSON.stringify(payload));
  if (profile.resume) {
    const part = await resumePart(profile.resume);
    if (part instanceof Blob) body.append('resume', part, profile.resume.name);
    else body.append('resume', part as unknown as Blob);
  }
  const response = await fetch(`${apiBase}/save-user-data`, {
    method: 'POST',
    headers: attendeeToken ? { Authorization: `Bearer ${attendeeToken}` } : undefined,
    body,
  });
  if (!response.ok) throw await apiError(response, 'Could not save your profile to the conference server.');
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
