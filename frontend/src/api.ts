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

function venueMinutes(timestamp: string) {
  const parts = new Intl.DateTimeFormat('en-US', {
    timeZone: 'America/Denver', hour: '2-digit', minute: '2-digit', hourCycle: 'h23',
  }).formatToParts(new Date(timestamp));
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
  const response = await fetch(`${apiBase}/save-user-data`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(attendeeToken ? { Authorization: `Bearer ${attendeeToken}` } : {}),
    },
    body: JSON.stringify({
      conference_id: conference.code,
      name: profile.name,
      bio: profile.bio,
      interests: profile.interests.split(',').map((item) => item.trim()).filter(Boolean),
      linkedin_url: profile.linkedin || undefined,
      discovery_opt_in: profile.discoverable,
      // Time ranges are currently entered as clock times without a date/time zone. They remain
      // local until the UI collects timezone-aware timestamps for the API.
      blockout_times: [],
    }),
  });
  if (!response.ok) throw new Error('Could not save your profile to the conference server.');
  return response.json() as Promise<{ attendee_token?: string }>;
}
