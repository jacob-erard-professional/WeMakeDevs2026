export type TimeRange = { start: number; end: number };

export type Talk = TimeRange & {
  id: string;
  title: string;
  track: string;
  room: string;
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
  const hour = Math.floor(minutes / 60);
  return `${hour % 12 || 12}:${String(minutes % 60).padStart(2, '0')} ${hour < 12 ? 'AM' : 'PM'}`;
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

function overlaps(a: TimeRange, b: TimeRange) {
  return a.start < b.end && b.start < a.end;
}

export function matchingTopics(profile: Attendee, topics: string[]) {
  const interests = profile.interests.toLowerCase().split(',').map((value) => value.trim());
  const bio = profile.bio.toLowerCase();
  return topics.filter((topic) => interests.includes(topic.toLowerCase()) || bio.includes(topic.toLowerCase()));
}

export function recommendTalks(talks: Talk[], profile: Attendee) {
  return talks
    .filter((talk) => !profile.unavailable.some((range) => overlaps(talk, range)))
    .map((talk) => ({ ...talk, matched: matchingTopics(profile, [talk.track]).length > 0 }))
    .sort((a, b) => Number(b.matched) - Number(a.matched) || a.start - b.start);
}

export function buildSchedule(talks: ReturnType<typeof recommendTalks>) {
  const schedule: typeof talks = [];
  for (const talk of talks) {
    if (!schedule.some((scheduled) => overlaps(scheduled, talk))) schedule.push(talk);
  }
  return schedule.sort((a, b) => a.start - b.start);
}
