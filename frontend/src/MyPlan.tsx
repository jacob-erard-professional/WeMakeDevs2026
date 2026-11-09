import { useState } from 'react';
import { Platform, Share, StyleSheet, Text, View } from 'react-native';

import { formatTime, talkDay } from './conference';
import type { Attendee, Talk, TimeRange } from './conference';
import { Action, colors, Copy, Heading, Label, Message, TalkDetails, styles } from './ui';

export type PlanTalk = Talk & { matched?: boolean; relevance?: number; rank?: number };

const MIN_PER_DAY = 1;
const MAX_PER_DAY = 8;
const DEFAULT_PER_DAY = 4;

const dayFormat = new Intl.DateTimeFormat('en-US', {
  timeZone: 'UTC', weekday: 'long', month: 'long', day: 'numeric',
});

function overlaps(a: TimeRange, b: TimeRange) {
  return a.start < b.end && b.start < a.end;
}

function blocked(talk: PlanTalk, unavailable: TimeRange[]) {
  const day = talkDay(talk.startsAt);
  return unavailable.some((range) => (!range.date || range.date === day) && overlaps(talk, range));
}

// Talks arrive best match first. Per day, keep the best ones that don't clash, up to the limit.
export function planByDay(talks: PlanTalk[], perDay: number, unavailable: TimeRange[]) {
  const days = new Map<string, PlanTalk[]>();
  for (const talk of talks) {
    if (blocked(talk, unavailable)) continue;
    const day = talkDay(talk.startsAt) ?? '';
    const picked = days.get(day) ?? [];
    if (picked.length < perDay && !picked.some((other) => overlaps(other, talk))) picked.push(talk);
    days.set(day, picked);
  }
  return [...days.entries()]
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([day, picked]) => ({ day, talks: picked.sort((a, b) => a.start - b.start) }));
}

function matchLabel(talk: PlanTalk) {
  if (talk.relevance === undefined) return talk.matched ? 'Matches your interests' : null;
  if (talk.rank !== undefined && talk.rank <= 3) return 'Top match';
  return `${Math.round(talk.relevance * 100)}% match`;
}

// --- Calendar export (RFC 5545) -------------------------------------------------------------

function icsDate(timestamp: string) {
  return new Date(timestamp).toISOString().replace(/[-:]/g, '').replace(/\.\d{3}/, '');
}

function icsText(value: string) {
  return value.replace(/\\/g, '\\\\').replace(/;/g, '\\;').replace(/,/g, '\\,').replace(/\r?\n/g, '\\n');
}

// Lines longer than 75 characters continue on the next line after a single space.
function fold(line: string) {
  const parts: string[] = [];
  for (let rest = line; rest.length; rest = rest.slice(73)) parts.push(rest.slice(0, 73));
  return parts.join('\r\n ');
}

export function toIcs(conferenceName: string, talks: PlanTalk[]) {
  const stamp = icsDate(new Date().toISOString());
  const events = talks
    .filter((talk) => talk.startsAt && talk.endsAt)
    .flatMap((talk) => [
      'BEGIN:VEVENT',
      `UID:${talk.id}@click-talk`,
      `DTSTAMP:${stamp}`,
      `DTSTART:${icsDate(talk.startsAt!)}`,
      `DTEND:${icsDate(talk.endsAt!)}`,
      `SUMMARY:${icsText(talk.title)}`,
      `LOCATION:${icsText(talk.room)}`,
      `DESCRIPTION:${icsText(`${conferenceName}. ${talk.abstract ?? ''}`.trim())}`,
      'END:VEVENT',
    ]);
  return [
    'BEGIN:VCALENDAR', 'VERSION:2.0', 'PRODID:-//Click Talk//Conference plan//EN', 'CALSCALE:GREGORIAN',
    `X-WR-CALNAME:${icsText(conferenceName)}`, ...events, 'END:VCALENDAR',
  ].map(fold).join('\r\n') + '\r\n';
}

async function exportPlan(conferenceName: string, talks: PlanTalk[]) {
  const ics = toIcs(conferenceName, talks);
  if (Platform.OS === 'web') {
    const url = URL.createObjectURL(new Blob([ics], { type: 'text/calendar;charset=utf-8' }));
    const link = document.createElement('a');
    link.href = url;
    link.download = `${conferenceName.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '') || 'conference'}-plan.ics`;
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 0);
  } else {
    await Share.share({ title: `${conferenceName} plan`, message: ics });
  }
}

// --- Page ---------------------------------------------------------------------------------------

export function MyPlan({ conferenceName, talks, profile, emptyText }: {
  conferenceName: string;
  talks: PlanTalk[];
  profile: Attendee;
  emptyText: string;
}) {
  const [perDay, setPerDay] = useState(DEFAULT_PER_DAY);
  const [exported, setExported] = useState('');
  const days = planByDay(talks, perDay, profile.unavailable);
  const planned = days.flatMap((day) => day.talks);
  const exportable = planned.filter((talk) => talk.startsAt && talk.endsAt);

  async function onExport() {
    setExported('');
    try {
      await exportPlan(conferenceName, exportable);
      setExported(`Exported ${exportable.length} talks. Open the file to add them to your calendar.`);
    } catch {
      setExported('Could not export the plan. Try again.');
    }
  }

  return (
    <View style={plan.page}>
      <View style={plan.toolbar}>
        <View style={plan.stepper}>
          <Text nativeID="per-day-label" style={plan.stepperLabel}>Talks per day</Text>
          <Action title="−" accessibilityLabel="Fewer talks per day" secondary
            disabled={perDay <= MIN_PER_DAY} onPress={() => setPerDay((n) => Math.max(MIN_PER_DAY, n - 1))} />
          <Text accessibilityLabelledBy="per-day-label" accessibilityLiveRegion="polite" style={plan.count}>{perDay}</Text>
          <Action title="+" accessibilityLabel="More talks per day" secondary
            disabled={perDay >= MAX_PER_DAY} onPress={() => setPerDay((n) => Math.min(MAX_PER_DAY, n + 1))} />
        </View>
        <Action title="Export to calendar (.ics)" disabled={!exportable.length} onPress={() => void onExport()} />
      </View>
      {exported ? <Message error={exported.startsWith('Could not')}>{exported}</Message> : null}
      <Copy>
        {planned.length
          ? `${planned.length} talks across ${days.length} ${days.length === 1 ? 'day' : 'days'}: your best matches, with no overlaps and around your unavailable times.`
          : emptyText}
      </Copy>

      {days.map(({ day, talks: dayTalks }) => (
        <View key={day || 'day'} style={plan.day} accessibilityRole="summary">
          <View style={plan.dayHeader}>
            <Heading>{day ? dayFormat.format(new Date(`${day}T12:00:00Z`)) : 'Conference day'}</Heading>
            <Label>
              {dayTalks.length < perDay
                ? `${dayTalks.length} of ${perDay}: no more matches fit this day`
                : `${dayTalks.length} ${dayTalks.length === 1 ? 'talk' : 'talks'}`}
            </Label>
          </View>
          {dayTalks.map((talk) => {
            const match = matchLabel(talk);
            return (
              <View key={talk.id} style={plan.slot}>
                <View style={plan.time}>
                  <Text style={plan.clock}>{formatTime(talk.start)}</Text>
                  <Text style={plan.until}>to {formatTime(talk.end)}</Text>
                </View>
                <View style={plan.talk}>
                  {match ? <Label>{match}</Label> : null}
                  <Text accessibilityRole="header" style={plan.title}>{talk.title}</Text>
                  <Copy>{talk.room} · {talk.track}</Copy>
                  <TalkDetails title={talk.title} abstract={talk.abstract || 'No session description has been provided.'} />
                </View>
              </View>
            );
          })}
        </View>
      ))}
    </View>
  );
}

const plan = StyleSheet.create({
  page: { gap: 14 },
  toolbar: { ...styles.row, alignItems: 'center', justifyContent: 'space-between', rowGap: 10 },
  stepper: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  stepperLabel: { color: colors.ink, fontSize: 16, fontWeight: '600', marginRight: 4 },
  count: { minWidth: 28, textAlign: 'center', color: colors.ink, fontSize: 20, fontWeight: '700', fontVariant: ['tabular-nums'] },
  day: { backgroundColor: colors.white, borderWidth: 1, borderColor: colors.chrome, borderRadius: 8, padding: 16, gap: 4 },
  dayHeader: { flexDirection: 'row', flexWrap: 'wrap', alignItems: 'baseline', justifyContent: 'space-between', gap: 8, marginBottom: 4 },
  slot: { flexDirection: 'row', gap: 16, borderTopWidth: 1, borderColor: colors.chrome, paddingVertical: 12 },
  time: { width: 82, borderLeftWidth: 3, borderLeftColor: colors.accent, paddingLeft: 8 },
  clock: { color: colors.ink, fontSize: 15, fontWeight: '700', fontVariant: ['tabular-nums'] },
  until: { color: colors.muted, fontSize: 13, fontVariant: ['tabular-nums'] },
  talk: { flex: 1, minWidth: 0, gap: 3 },
  title: { color: colors.ink, fontSize: 18, fontWeight: '700', lineHeight: 24 },
});
