import { useState } from 'react';
import type { PropsWithChildren } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';

import { formatTime, talkDay } from './conference';
import type { Talk } from './conference';
import { Action, colors, Copy, Heading, styles } from './ui';

const dayFormat = new Intl.DateTimeFormat('en-US', {
  timeZone: 'UTC', weekday: 'short', month: 'short', day: 'numeric',
});

function finish(talk: Talk) {
  return talk.end < talk.start ? 1440 : Math.max(talk.start + 1, talk.end);
}

function placeTalks(talks: Talk[]) {
  const sorted = [...talks].sort((a, b) => a.start - b.start || finish(b) - finish(a));
  const groups: Array<Array<{ talk: Talk; lane: number }>> = [];
  let laneEnds: number[] = [];
  for (const talk of sorted) {
    if (!groups.length || laneEnds.every((end) => end <= talk.start)) {
      groups.push([]);
      laneEnds = [];
    }
    const free = laneEnds.findIndex((end) => end <= talk.start);
    const lane = free === -1 ? laneEnds.length : free;
    laneEnds[lane] = finish(talk);
    groups.at(-1)?.push({ talk, lane });
  }
  return groups.flatMap((group) => {
    const lanes = Math.max(...group.map((item) => item.lane)) + 1;
    return group.map((item) => ({ ...item, lanes }));
  });
}

function Calendar({ talks, onTalk }: { talks: Talk[]; onTalk?: (talk: Talk) => void }) {
  const dates = [...new Set(talks.map((talk) => talkDay(talk.startsAt) ?? ''))].sort();
  const [selectedDate, setSelectedDate] = useState(dates[0]);
  const date = dates.includes(selectedDate) ? selectedDate : dates[0];
  const visible = talks.filter((talk) => (talkDay(talk.startsAt) ?? '') === date);
  const from = Math.floor(Math.min(...visible.map((talk) => talk.start)) / 60) * 60;
  const until = Math.ceil(Math.max(...visible.map(finish)) / 60) * 60;
  const scale = 1.25;
  const hours = Array.from({ length: (until - from) / 60 + 1 }, (_, index) => from + index * 60);

  return (
    <View style={calendar.wrap}>
      <Heading>Calendar view</Heading>
      <Copy>Mountain Time</Copy>
      {dates.length > 1 ? (
        <View style={styles.row}>
          {dates.map((day) => (
            <Action key={day} title={day ? dayFormat.format(new Date(`${day}T12:00:00Z`)) : 'Conference day'}
              selected={day === date} onPress={() => setSelectedDate(day)} secondary />
          ))}
        </View>
      ) : null}
      <View style={{ height: (until - from) * scale + 22 }}>
        {hours.map((time) => (
          <View key={time} style={[calendar.hour, { top: (time - from) * scale }]}>
            <Text style={calendar.clock}>{formatTime(time)}</Text>
            <View style={calendar.rule} />
          </View>
        ))}
        <View style={calendar.events}>
          {placeTalks(visible).map(({ talk, lane, lanes }) => {
            const duration = finish(talk) - talk.start;
            const position = {
              top: (talk.start - from) * scale,
              left: `${lane / lanes * 100}%` as const,
              width: `${100 / lanes}%` as const,
              height: duration * scale,
            };
            const label = `${talk.title}, ${formatTime(talk.start)} to ${formatTime(finish(talk))}, ${talk.room}`;
            const content = (
              <>
                <Text numberOfLines={duration >= 36 ? 2 : 1} style={calendar.title}>{talk.title}</Text>
                {duration >= 55 ? <Text numberOfLines={1} style={calendar.room}>{talk.room}</Text> : null}
              </>
            );
            return (
              <View key={talk.id} style={[calendar.eventSlot, position]}>
                {onTalk ? (
                  <Pressable accessibilityRole="button" accessibilityLabel={label} onPress={() => onTalk(talk)}
                    style={({ pressed }) => [calendar.event, pressed && calendar.pressed]}>
                    {content}
                  </Pressable>
                ) : (
                  <View accessible accessibilityLabel={label} style={calendar.event}>{content}</View>
                )}
              </View>
            );
          })}
        </View>
      </View>
    </View>
  );
}

export function ScheduleColumns({ talks, onTalk, children }: PropsWithChildren<{
  talks: Talk[];
  onTalk?: (talk: Talk) => void;
}>) {
  const [width, setWidth] = useState(0);
  const showCalendar = width >= 740 && talks.length > 0;
  return (
    <View style={showCalendar ? calendar.columns : undefined} onLayout={(event) => setWidth(event.nativeEvent.layout.width)}>
      <View style={calendar.list}>{children}</View>
      {showCalendar ? <View style={calendar.side}><Calendar talks={talks} onTalk={onTalk} /></View> : null}
    </View>
  );
}

const calendar = StyleSheet.create({
  columns: { flexDirection: 'row', alignItems: 'flex-start', gap: 26 },
  list: { flex: 1, minWidth: 0, gap: 12 },
  side: { width: '44%' },
  wrap: { backgroundColor: colors.white, borderWidth: 1, borderColor: colors.chrome, borderRadius: 8, padding: 14, gap: 9 },
  hour: { position: 'absolute', left: 0, right: 0, flexDirection: 'row', alignItems: 'center', gap: 7 },
  clock: { width: 67, color: colors.muted, fontSize: 13, fontVariant: ['tabular-nums'] },
  rule: { flex: 1, height: 1, backgroundColor: colors.chrome },
  events: { position: 'absolute', left: 74, top: 9, right: 0, bottom: 0 },
  eventSlot: { position: 'absolute', paddingRight: 3, paddingBottom: 2 },
  event: { flex: 1, overflow: 'hidden', backgroundColor: colors.chrome, borderLeftWidth: 3, borderLeftColor: colors.accent, borderRadius: 3, paddingHorizontal: 5, justifyContent: 'center' },
  pressed: { opacity: 0.7 },
  title: { color: colors.ink, fontSize: 13, fontWeight: '700' },
  room: { color: colors.muted, fontSize: 12 },
});
