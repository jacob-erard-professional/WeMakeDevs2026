import type { ParsedTalk } from './api';
import { parseSchedule } from './conference';

const mountainClock = new Intl.DateTimeFormat('en-CA', {
  timeZone: 'America/Denver', year: 'numeric', month: '2-digit', day: '2-digit',
  hour: '2-digit', minute: '2-digit', hourCycle: 'h23',
});

export function validScheduleDate(date: string) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(date)) return false;
  const timestamp = Date.parse(`${date}T00:00:00Z`);
  return Number.isFinite(timestamp) && new Date(timestamp).toISOString().startsWith(date);
}

export function venueTimestamp(date: string, minutes: number): string | undefined {
  if (!validScheduleDate(date)) return undefined;
  if (minutes === 1440) {
    const next = new Date(Date.parse(`${date}T00:00:00Z`) + 86400000).toISOString().slice(0, 10);
    return venueTimestamp(next, 0);
  }
  const hour = String(Math.floor(minutes / 60)).padStart(2, '0');
  const minute = String(minutes % 60).padStart(2, '0');
  const local = `${date}T${hour}:${minute}`;
  const wallClock = Date.parse(`${local}:00Z`);
  // Modern Denver wall time maps to either UTC−06:00 or UTC−07:00. Round-trip to
  // detect nonexistent and ambiguous times around daylight saving changes.
  const matches = [6, 7].map((offset) => new Date(wallClock + offset * 3600000)).filter((candidate) => {
    const parts = Object.fromEntries(mountainClock.formatToParts(candidate).map(({ type, value }) => [type, value]));
    return `${parts.year}-${parts.month}-${parts.day}T${parts.hour}:${parts.minute}` === local;
  });
  return matches.length === 1 ? matches[0].toISOString() : undefined;
}

export function parsePastedSchedule(text: string, date: string): { talks: ParsedTalk[]; warnings: string[] } {
  if (!validScheduleDate(date)) return { talks: [], warnings: ['Enter the schedule date in YYYY-MM-DD format.'] };
  const parsed = parseSchedule(text);
  const talks: ParsedTalk[] = [];
  for (const talk of parsed.talks) {
    const start = venueTimestamp(date, talk.start);
    const end = venueTimestamp(date, talk.end);
    if (!start || !end || Date.parse(end) <= Date.parse(start)) {
      parsed.warnings.push(`Line ${Number(talk.id) + 1} has a time that is ambiguous or unavailable in Mountain Time.`);
      continue;
    }
    talks.push({ title: talk.title, room: talk.room, track: [talk.track], start_time: start, end_time: end });
  }
  return { talks, warnings: parsed.warnings };
}
