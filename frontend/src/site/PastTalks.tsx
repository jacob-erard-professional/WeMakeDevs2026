// Past talks across all sample events with a text filter and a track filter.
import { useEffect, useMemo, useState } from 'react';
import { Pressable, Text, View } from 'react-native';

import { Action, Copy, Field, Heading, Label, Message } from '../ui';
import { SampleBadge, TalkCard, page } from './PastEvents';
import type { PastTalk } from './sampleEvents';
import { eventName, loadPastTalks } from './sampleEvents';
import { Container } from './SiteShell';

function Chip({ title, selected, onPress }: { title: string; selected: boolean; onPress: () => void }) {
  const [focused, setFocused] = useState(false);
  return (
    <Pressable accessibilityRole="button" aria-pressed={selected} onPress={onPress}
      onFocus={() => setFocused(true)} onBlur={() => setFocused(false)}
      style={[page.chip, selected && page.chipSelected, focused && page.focused]}>
      <Text style={[page.chipText, selected && page.chipTextSelected]}>{title}</Text>
    </Pressable>
  );
}

export function PastTalks({ onBrowseSchedule }: { onBrowseSchedule: () => void }) {
  const [talks, setTalks] = useState<PastTalk[]>();
  const [failed, setFailed] = useState(false);
  const [query, setQuery] = useState('');
  const [track, setTrack] = useState<string>();

  useEffect(() => {
    let active = true;
    loadPastTalks().then((items) => { if (active) setTalks(items); }).catch(() => { if (active) setFailed(true); });
    return () => { active = false; };
  }, []);

  const tracks = useMemo(() => Array.from(new Set((talks ?? []).map((talk) => talk.track))).sort(), [talks]);
  const visible = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return (talks ?? []).filter((talk) => (!track || talk.track === track) && (!needle
      || [talk.title, talk.abstract, ...talk.speakers, eventName(talk.eventId)].some((text) => text.toLowerCase().includes(needle))));
  }, [talks, query, track]);

  return (
    <Container style={page.block}>
      <Label>Past talks</Label>
      <Heading large>Talks from events on the platform.</Heading>
      <Copy>Looking for recordings related to a session? Start with your conference schedule.</Copy>
      <Action title="Browse my event schedule" onPress={onBrowseSchedule} secondary />
      <SampleBadge />
      <Field label="Search talks, speakers, or events" value={query} onChangeText={setQuery} autoCorrect={false} />
      {tracks.length ? (
        <View accessibilityLabel="Filter by track" style={page.filters}>
          <Chip title="All tracks" selected={!track} onPress={() => setTrack(undefined)} />
          {tracks.map((item) => <Chip key={item} title={item} selected={track === item} onPress={() => setTrack(track === item ? undefined : item)} />)}
        </View>
      ) : null}
      {failed ? <Message error>Couldn't load past talks. Try again in a moment.</Message> : null}
      {!talks && !failed ? <Message>Loading talks…</Message> : null}
      {talks ? <Message>{visible.length === 0 ? 'No talks match these filters.' : `${visible.length} of ${talks.length} talks`}</Message> : null}
      <View style={page.list}>
        {visible.map((talk) => <TalkCard key={talk.id} talk={talk} event={eventName(talk.eventId)} />)}
      </View>
    </Container>
  );
}
