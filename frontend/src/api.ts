import { Platform } from 'react-native';

import { API_BASE_URL as apiBase } from './apiBase';
import type { Attendee, Conference, ResumeAsset, Talk } from './conference';

type JoinResponse = {
  conference_id: string;
  name: string;
  talks: Array<{
    talk_id: string;
    title: string;
    abstract?: string;
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
export type ArchiveTalk = { title: string; conference?: string; year?: number; url?: string; video_url?: string };

async function request(url: string, options: RequestInit = {}, timeoutMs = 15000) {
  const controller = new AbortController();
  const cancel = () => controller.abort();
  if (options.signal?.aborted) cancel();
  options.signal?.addEventListener('abort', cancel);
  const timer = setTimeout(cancel, timeoutMs);
  try {
    return await fetch(url, { ...options, signal: controller.signal });
  } catch (error) {
    if (controller.signal.aborted && !options.signal?.aborted) throw new Error('The server took too long. Try again.');
    throw error;
  } finally {
    clearTimeout(timer);
    options.signal?.removeEventListener('abort', cancel);
  }
}

function venueMinutes(timestamp: string) {
  const date = new Date(timestamp);
  if (Number.isNaN(date.getTime())) return 0;
  const parts = new Intl.DateTimeFormat('en-US', {
    timeZone: 'America/Denver', hour: '2-digit', minute: '2-digit', hourCycle: 'h23',
  }).formatToParts(date);
  const value = (type: string) => Number(parts.find((part) => part.type === type)?.value ?? 0);
  return value('hour') * 60 + value('minute');
}

// `id` is a bare conference id; callers normalize join links with parseJoinCode first.
export async function joinLiveConference(id: string, signal?: AbortSignal): Promise<Conference> {
  const response = await request(`${apiBase}/join/${encodeURIComponent(id)}`, { signal });
  if (!response.ok) {
    throw new Error(response.status === 404 ? 'That conference is not available yet.' : 'Could not reach the conference server.');
  }
  return conferenceFromSchedule(await response.json() as JoinResponse);
}

export function conferenceFromSchedule(data: JoinResponse): Conference {
  const talks: Talk[] = data.talks.map((talk) => ({
    id: talk.talk_id,
    title: talk.title,
    abstract: talk.abstract,
    startsAt: talk.start_time,
    track: talk.track?.join(', ') || 'Conference session',
    room: talk.room || 'Room to be announced',
    start: venueMinutes(talk.start_time),
    end: venueMinutes(talk.end_time),
  }));
  return { name: data.name, code: data.conference_id, talks };
}

export async function loadRelatedTalks(conferenceId: string, talkId: string, token: string, signal: AbortSignal) {
  const response = await request(
    `${apiBase}/conferences/${encodeURIComponent(conferenceId)}/talks/${encodeURIComponent(talkId)}/related-archive`,
    { headers: { Authorization: `Bearer ${token}` }, signal },
  );
  if (!response.ok) throw await apiError(response, 'Could not load similar past talks.');
  const result = await response.json() as { talks: ArchiveTalk[] };
  return result.talks;
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
  const response = await request(`${apiBase}/save-user-data`, {
    method: 'POST',
    headers: attendeeToken ? { Authorization: `Bearer ${attendeeToken}` } : undefined,
    body,
  });
  if (!response.ok) throw await apiError(response, 'Could not save your profile to the conference server.');
  return response.json() as Promise<{ attendee_token?: string }>;
}

async function apiError(response: Response, fallback: string) {
  const body = await response.json().catch(() => null) as { detail?: unknown } | null;
  return new Error(typeof body?.detail === 'string' ? body.detail : fallback);
}

export async function createLiveConference(name: string): Promise<OrganizerSession> {
  const response = await request(`${apiBase}/conferences`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name }),
  });
  if (!response.ok) throw await apiError(response, 'Could not create the conference.');
  const body = await response.json() as { conference_id: string; organizer_token: string };
  return { conferenceId: body.conference_id, organizerToken: body.organizer_token, name };
}

export async function parseLiveSchedule(
  session: OrganizerSession, sourceUrl?: string, asset?: ResumeAsset,
): Promise<{ talks: ParsedTalk[]; warnings: string[] }> {
  const query = new URLSearchParams({ conference_id: session.conferenceId });
  const headers = { 'X-Organizer-Token': session.organizerToken };
  let options: RequestInit = { method: 'POST', headers };
  if (sourceUrl) query.set('source_url', sourceUrl);
  else if (asset) {
    const file = await resumePart(asset);
    const body = new FormData();
    if (Platform.OS === 'web') body.append('file', file as Blob, asset.name);
    else body.append('file', file as unknown as Blob);
    options = { ...options, body };
  } else throw new Error('Choose a schedule link, image, or PDF first.');
  const response = await request(`${apiBase}/upload-schedule?${query}`, options, 90000);
  if (!response.ok) throw await apiError(response, 'Could not parse the schedule.');
  return response.json() as Promise<{ talks: ParsedTalk[]; warnings: string[] }>;
}

export async function confirmLiveSchedule(session: OrganizerSession, talks: ParsedTalk[]) {
  const response = await request(`${apiBase}/confirm-schedule`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-Organizer-Token': session.organizerToken },
    body: JSON.stringify({ conference_id: session.conferenceId, talks }),
  }, 90000);
  if (!response.ok) throw await apiError(response, 'Could not publish the schedule.');
  return response.json() as Promise<{ join_url: string; qr_code_data_url: string }>;
}
