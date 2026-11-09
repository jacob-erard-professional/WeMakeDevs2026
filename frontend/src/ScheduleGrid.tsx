import { useState } from 'react';
import { Platform, Pressable, ScrollView, StyleSheet, Text, View, useWindowDimensions } from 'react-native';

import { formatTime } from './conference';
import { colors } from './ui';

// A session as the grid needs it. `start`/`end` are minutes since midnight in the venue's zone
// (the same convention as `Talk`); `startsAt` is the ISO timestamp used to group days.
export type GridTalk = {
  id: string;
  title: string;
  room?: string;
  track?: string;
  start: number;
  end: number;
  startsAt?: string;
  speakers?: string[];
};

const PLENARY = /\b(keynote|break|lunch|breakfast|registration|coffee|all rooms|opening|closing|welcome|reception)\b/i;
const PHONE_WIDTH = 720;
const TIME_COLUMN = 92;
const ROOM_COLUMN = 220;

// Soft tints per track; the track name is always shown as text too, colour is only an accent.
const tints = [
  { fill: '#EEEBF9', edge: '#5040AF' },
  { fill: '#E6F3EE', edge: '#1F7A5A' },
  { fill: '#FDF0E4', edge: '#B35A12' },
  { fill: '#E8F0FB', edge: '#2458A6' },
  { fill: '#FBE9EE', edge: '#A3344E' },
  { fill: '#F2EFE4', edge: '#7A6A16' },
];

function tint(track?: string) {
  if (!track) return { fill: colors.chrome, edge: colors.line };
  let hash = 0;
  for (const char of track) hash = (hash * 31 + char.charCodeAt(0)) >>> 0;
  return tints[hash % tints.length];
}

const venueDay = new Intl.DateTimeFormat('en-US', {
  timeZone: 'America/Denver', weekday: 'long', month: 'long', day: 'numeric',
});

function dayOf(talk: GridTalk) {
  const stamp = Date.parse(talk.startsAt ?? '');
  return Number.isNaN(stamp) ? '' : venueDay.format(stamp);
}

export function isPlenary(talk: GridTalk) {
  return !talk.room?.trim() || PLENARY.test(talk.title) || PLENARY.test(talk.room);
}

type Day = { label: string; rooms: string[]; slots: Array<{ start: number; plenary: GridTalk[]; byRoom: Map<string, GridTalk[]> }> };

export function layoutDays(talks: GridTalk[]): Day[] {
  const days = new Map<string, GridTalk[]>();
  for (const talk of talks) {
    const key = dayOf(talk);
    days.set(key, [...(days.get(key) ?? []), talk]);
  }
  return [...days.entries()]
    .sort(([, a], [, b]) => Date.parse(a[0].startsAt ?? '') - Date.parse(b[0].startsAt ?? ''))
    .map(([label, items]) => {
      const rooms: string[] = [];
      for (const talk of items) {
        if (!isPlenary(talk) && talk.room && !rooms.includes(talk.room)) rooms.push(talk.room);
      }
      const starts = [...new Set(items.map((talk) => talk.start))].sort((a, b) => a - b);
      const slots = starts.map((start) => {
        const inSlot = items.filter((talk) => talk.start === start);
        const byRoom = new Map<string, GridTalk[]>();
        const plenary: GridTalk[] = [];
        for (const talk of inSlot) {
          if (isPlenary(talk)) plenary.push(talk);
          else byRoom.set(talk.room!, [...(byRoom.get(talk.room!) ?? []), talk]);
        }
        return { start, plenary, byRoom };
      });
      return { label, rooms, slots };
    });
}

function SessionBox({ talk, onSelect, highlighted, showRoom, wide }: {
  talk: GridTalk;
  onSelect: (talk: GridTalk) => void;
  highlighted?: boolean;
  showRoom?: boolean;
  wide?: boolean;
}) {
  const [focused, setFocused] = useState(false);
  const { fill, edge } = tint(talk.track);
  const time = `${formatTime(talk.start)} to ${formatTime(talk.end)}`;
  const label = [talk.title, time, talk.room || 'All rooms', talk.track].filter(Boolean).join(', ');
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={label}
      onPress={() => onSelect(talk)}
      onFocus={() => setFocused(true)}
      onBlur={() => setFocused(false)}
      style={({ pressed }) => [
        grid.box,
        { backgroundColor: fill, borderLeftColor: edge },
        wide && grid.boxWide,
        highlighted && grid.boxHighlighted,
        (focused || pressed) && grid.boxFocused,
      ]}
    >
      <Text style={grid.boxTime}>{time}{showRoom ? ` · ${talk.room || 'All rooms'}` : ''}</Text>
      <Text style={grid.boxTitle}>{talk.title || 'Untitled session'}</Text>
      {talk.speakers?.length ? <Text style={grid.boxMeta} numberOfLines={2}>{talk.speakers.join(', ')}</Text> : null}
      {talk.track ? <Text style={[grid.boxTrack, { color: edge }]}>{talk.track}</Text> : null}
      {highlighted ? <Text style={grid.boxPick}>Recommended</Text> : null}
    </Pressable>
  );
}

export function ScheduleGrid({ talks, onSelect, highlight, emptyMessage }: {
  talks: GridTalk[];
  onSelect: (talk: GridTalk) => void;
  highlight?: Set<string>;
  emptyMessage?: string;
}) {
  const { width } = useWindowDimensions();
  const phone = width < PHONE_WIDTH;
  const days = layoutDays(talks);
  if (!days.length) return <Text style={grid.empty}>{emptyMessage ?? 'No sessions to show.'}</Text>;

  return (
    <View style={grid.stack}>
      {days.map((day) => (
        <View key={day.label || 'schedule'} style={grid.day}>
          {day.label ? <Text accessibilityRole="header" style={grid.dayHeading}>{day.label}</Text> : null}
          {phone ? (
            day.slots.map((slot) => (
              <View key={slot.start} style={grid.phoneSlot}>
                <Text style={grid.phoneTime}>{formatTime(slot.start)}</Text>
                <View style={grid.phoneList}>
                  {slot.plenary.map((talk) => (
                    <SessionBox key={talk.id} talk={talk} onSelect={onSelect} highlighted={highlight?.has(talk.id)} showRoom />
                  ))}
                  {day.rooms.flatMap((room) => slot.byRoom.get(room) ?? []).map((talk) => (
                    <SessionBox key={talk.id} talk={talk} onSelect={onSelect} highlighted={highlight?.has(talk.id)} showRoom />
                  ))}
                </View>
              </View>
            ))
          ) : (
            <ScrollView horizontal showsHorizontalScrollIndicator contentContainerStyle={grid.sheet}>
              <View>
                <View style={[grid.row, grid.headerRow]}>
                  <View style={[grid.timeCell, grid.headerCell]}><Text style={grid.headerText}>Time</Text></View>
                  {day.rooms.map((room) => (
                    <View key={room} style={[grid.roomCell, grid.headerCell]}>
                      <Text accessibilityRole="header" style={grid.headerText}>{room}</Text>
                    </View>
                  ))}
                </View>
                {day.slots.map((slot) => (
                  <View key={slot.start}>
                    {slot.plenary.length ? (
                      <View style={grid.row}>
                        <View style={grid.timeCell}><Text style={grid.timeText}>{formatTime(slot.start)}</Text></View>
                        <View style={[grid.plenaryCell, { width: Math.max(day.rooms.length, 1) * ROOM_COLUMN }]}>
                          {slot.plenary.map((talk) => (
                            <SessionBox key={talk.id} talk={talk} onSelect={onSelect} highlighted={highlight?.has(talk.id)} wide />
                          ))}
                        </View>
                      </View>
                    ) : null}
                    {slot.byRoom.size ? (
                      <View style={grid.row}>
                        <View style={grid.timeCell}>
                          {slot.plenary.length ? null : <Text style={grid.timeText}>{formatTime(slot.start)}</Text>}
                        </View>
                        {day.rooms.map((room) => (
                          <View key={room} style={grid.roomCell}>
                            {(slot.byRoom.get(room) ?? []).map((talk) => (
                              <SessionBox key={talk.id} talk={talk} onSelect={onSelect} highlighted={highlight?.has(talk.id)} />
                            ))}
                          </View>
                        ))}
                      </View>
                    ) : null}
                  </View>
                ))}
              </View>
            </ScrollView>
          )}
        </View>
      ))}
    </View>
  );
}

const grid = StyleSheet.create({
  stack: { gap: 28 },
  day: { gap: 12 },
  dayHeading: { color: colors.ink, fontSize: 20, fontWeight: '700', letterSpacing: -0.3 },
  empty: { color: colors.muted, fontSize: 16, lineHeight: 24 },
  sheet: { paddingBottom: 8 },
  row: { flexDirection: 'row', alignItems: 'stretch', borderTopWidth: 1, borderTopColor: colors.chrome },
  headerRow: { borderTopWidth: 0 },
  headerCell: { paddingVertical: 10, backgroundColor: colors.paper },
  headerText: { color: colors.muted, fontSize: 13, fontWeight: '700', letterSpacing: 0.6, textTransform: 'uppercase' },
  timeCell: { width: TIME_COLUMN, paddingVertical: 12, paddingRight: 10 },
  timeText: { color: colors.ink, fontSize: 14, fontWeight: '700' },
  roomCell: { width: ROOM_COLUMN, padding: 6, gap: 8 },
  plenaryCell: { padding: 6, gap: 8 },
  box: {
    borderRadius: 12, borderLeftWidth: 4, padding: 12, gap: 4, minHeight: 72,
    ...(Platform.OS === 'web' ? { cursor: 'pointer' } as object : {}),
  },
  boxWide: { alignItems: 'flex-start' },
  boxHighlighted: { borderWidth: 2, borderLeftWidth: 4, borderColor: colors.accent },
  boxFocused: { outlineWidth: 3, outlineColor: colors.accent, outlineStyle: 'solid' } as object,
  boxTime: { color: colors.muted, fontSize: 12, fontWeight: '600' },
  boxTitle: { color: colors.ink, fontSize: 15, fontWeight: '600', lineHeight: 20 },
  boxMeta: { color: colors.muted, fontSize: 13 },
  boxTrack: { fontSize: 12, fontWeight: '700', letterSpacing: 0.3 },
  boxPick: { color: colors.accent, fontSize: 12, fontWeight: '700' },
  phoneSlot: { flexDirection: 'row', gap: 12, borderTopWidth: 1, borderTopColor: colors.chrome, paddingTop: 12 },
  phoneTime: { width: 72, color: colors.ink, fontSize: 14, fontWeight: '700', paddingTop: 12 },
  phoneList: { flex: 1, gap: 8 },
});
