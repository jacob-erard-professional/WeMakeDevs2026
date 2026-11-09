export type TimeRange = { start: number; end: number; date?: string };

export type Talk = TimeRange & {
  id: string;
  title: string;
  track: string;
  room: string;
  abstract?: string;
  startsAt?: string;
  endsAt?: string;
};

export type Conference = { name: string; code: string; talks: Talk[] };

// A picked résumé. expo-document-picker gives a `file` on web and a `uri` on native; the
// document itself is only ever sent to /save-user-data, which extracts text and discards it.
export type ResumeAsset = { uri: string; name: string; mimeType?: string; file?: File };

export type Attendee = {
  name: string;
  email: string;
  bio: string;
  interests: string;
  lookingFor: string;
  linkedin: string;
  resume?: ResumeAsset;
  resumePublic: boolean;
  discoverable: boolean;
  unavailable: TimeRange[];
};

export function parseTime(value: string) {
  const match = /^(\d{2}):(\d{2})$/.exec(value.trim());
  if (!match || Number(match[1]) > 23 || Number(match[2]) > 59) return null;
  return Number(match[1]) * 60 + Number(match[2]);
}

export function formatTime(minutes: number) {
  const hour = Math.floor(minutes / 60) % 24;
  return `${hour % 12 || 12}:${String(minutes % 60).padStart(2, '0')} ${hour < 12 ? 'AM' : 'PM'}`;
}

const venueDay = new Intl.DateTimeFormat('en-CA', {
  timeZone: 'America/Denver', year: 'numeric', month: '2-digit', day: '2-digit',
});

export function talkDay(timestamp?: string) {
  const time = Date.parse(timestamp ?? '');
  if (!Number.isFinite(time)) return undefined;
  const parts = venueDay.formatToParts(time);
  return ['year', 'month', 'day'].map((type) => parts.find((part) => part.type === type)?.value).join('-');
}

export function parseSchedule(text: string) {
  const talks: Talk[] = [];
  const warnings: string[] = [];
  text.split(/\r?\n/).forEach((row, index) => {
    if (!row.trim()) return;
    const [startText, endText, title, track, room, extra] = row.split('|').map((part) => part.trim());
    const start = parseTime(startText ?? '');
    const end = parseTime(endText ?? '');
    if (start === null || end === null || end <= start || !title || !track || !room || extra !== undefined) {
      warnings.push(`Line ${index + 1} needs a valid start, end, title, topic, and room.`);
      return;
    }
    talks.push({ id: String(index), title, track, room, start, end });
  });
  return { talks, warnings };
}
