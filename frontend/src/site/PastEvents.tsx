// Past events that used the platform. Reads sample data through loadPastEvents() until the API lands.
import { useEffect, useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';

import { Copy, Heading, Message, TalkDetails, colors } from '../ui';
import type { PastEvent, PastTalk } from './sampleEvents';
import { loadPastEvents, sampleDataNotice } from './sampleEvents';
import { Container } from './SiteShell';

export function SampleBadge() {
  return <Text style={page.badge}>{sampleDataNotice}</Text>;
}

export function TalkCard({ talk, event }: { talk: PastTalk; event?: string }) {
  return (
    <View style={page.talk}>
      <View style={page.meta}>
        <Text style={page.track}>{talk.track}</Text>
        <Text style={page.time}>{talk.time}</Text>
        {event ? <Text style={page.time}>{event}</Text> : null}
      </View>
      <Text accessibilityRole="header" style={page.talkTitle}>{talk.title}</Text>
      <Text style={page.speakers}>{talk.speakers.join(', ')}</Text>
      <TalkDetails title={talk.title} abstract={talk.abstract} extra={talk.details} />
    </View>
  );
}

export function PastEvents() {
  const [events, setEvents] = useState<PastEvent[]>();
  const [failed, setFailed] = useState(false);
  const [open, setOpen] = useState<string>();

  useEffect(() => {
    let active = true;
    loadPastEvents().then((items) => { if (active) setEvents(items); }).catch(() => { if (active) setFailed(true); });
    return () => { active = false; };
  }, []);

  return (
    <Container style={page.block}>
      <Heading large>Event archive</Heading>
      <SampleBadge />
      {failed ? <Message error>Couldn't load past events. Try again in a moment.</Message> : null}
      {!events && !failed ? <Message>Loading events…</Message> : null}
      {events?.length === 0 ? <Message>No past events yet.</Message> : null}
      <View style={page.list}>
        {events?.map((event) => {
          const expanded = open === event.id;
          return (
            <View key={event.id} style={page.event}>
              <Pressable accessibilityRole="button" aria-expanded={expanded}
                accessibilityLabel={`${event.name}, ${expanded ? 'hide' : 'show'} ${event.talks.length} talks`}
                onPress={() => setOpen(expanded ? undefined : event.id)} style={page.eventButton}>
                <View style={page.eventHead}>
                  <Text accessibilityRole="header" style={page.eventTitle}>{event.name}</Text>
                  <Text style={page.eventMeta}>{event.dates} · {event.location} · {event.attendees.toLocaleString()} attendees</Text>
                  <Copy>{event.summary}</Copy>
                </View>
                <Text style={page.toggle}>{expanded ? 'Hide talks' : `Show ${event.talks.length} talks`}</Text>
              </Pressable>
              {expanded ? (
                <View style={page.talks}>
                  {event.talks.map((talk) => <TalkCard key={talk.id} talk={talk} />)}
                </View>
              ) : null}
            </View>
          );
        })}
      </View>
    </Container>
  );
}

export const page = StyleSheet.create({
  block: { paddingVertical: 56, gap: 22 },
  badge: { alignSelf: 'flex-start', color: colors.ink, backgroundColor: '#FFF1C2', borderColor: '#E0B93A', borderWidth: 1, borderRadius: 8, paddingHorizontal: 12, paddingVertical: 8, fontSize: 14, lineHeight: 20, fontWeight: '600' },
  list: { gap: 16 },
  event: { backgroundColor: colors.white, borderRadius: 14, borderWidth: 1, borderColor: colors.pale, overflow: 'hidden' },
  eventButton: { padding: 22, gap: 12 },
  eventHead: { gap: 6 },
  eventTitle: { color: colors.ink, fontSize: 24, fontWeight: '700', letterSpacing: -0.5, lineHeight: 30 },
  eventMeta: { color: colors.muted, fontSize: 15 },
  toggle: { color: colors.accent, fontWeight: '700', fontSize: 16 },
  talks: { padding: 22, paddingTop: 0, gap: 14 },
  talk: { gap: 6, padding: 18, backgroundColor: colors.pale, borderRadius: 12 },
  meta: { flexDirection: 'row', flexWrap: 'wrap', columnGap: 12, rowGap: 4, alignItems: 'center' },
  track: { color: colors.accent, fontSize: 13, fontWeight: '700', letterSpacing: 0.4, textTransform: 'uppercase' },
  time: { color: colors.muted, fontSize: 14 },
  talkTitle: { color: colors.ink, fontSize: 19, fontWeight: '700', lineHeight: 25 },
  speakers: { color: colors.ink, fontSize: 15, fontWeight: '600' },
  filters: { flexDirection: 'row', flexWrap: 'wrap', columnGap: 8, rowGap: 8 },
  chip: { minHeight: 40, justifyContent: 'center', paddingHorizontal: 14, borderRadius: 999, borderWidth: 1, borderColor: colors.line, backgroundColor: colors.white },
  chipSelected: { backgroundColor: colors.accent, borderColor: colors.accent },
  chipText: { color: colors.ink, fontSize: 15, fontWeight: '600' },
  chipTextSelected: { color: colors.white },
  focused: { outlineColor: colors.ink, outlineWidth: 2, outlineOffset: 2, outlineStyle: 'solid' },
});
