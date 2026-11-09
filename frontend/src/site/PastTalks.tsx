// Search the public past-talk archive (~25k KubeCon and PyVideo talks) through GET /talks/search.
// Text queries are hybrid (keyword + semantic) on the server; an empty query browses newest first.
import { useEffect, useRef, useState } from 'react';
import { Linking, Pressable, Text, View } from 'react-native';

import type { ArchiveFacet, ArchiveSearchResult, ArchiveSearchTalk } from '../api';
import { searchArchiveTalks } from '../api';
import { Action, Field, Heading, Message, TalkDetails, styles } from '../ui';
import { page } from './PastEvents';
import { Container } from './SiteShell';

const SOURCES = [{ value: 'kubecon', label: 'KubeCon' }, { value: 'pyvideo', label: 'PyVideo' }];
const count = new Intl.NumberFormat('en-US');

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

function ArchiveTalkCard({ talk }: { talk: ArchiveSearchTalk }) {
  const event = [talk.conference, talk.year].filter(Boolean).join(' · ');
  const recording = talk.video_url || talk.url;
  return (
    <View style={page.talk}>
      <View style={page.meta}>
        {talk.tracks?.[0] ? <Text style={page.track}>{talk.tracks[0]}</Text> : null}
        {event ? <Text style={page.time}>{event}</Text> : null}
      </View>
      <Text accessibilityRole="header" style={page.talkTitle}>{talk.title}</Text>
      {talk.speakers?.length ? <Text style={page.speakers}>{talk.speakers.join(', ')}</Text> : null}
      {talk.abstract ? <TalkDetails title={talk.title} abstract={talk.abstract} /> : null}
      {recording ? (
        <Action title={talk.video_url ? 'Watch recording' : 'Open talk page'} secondary
          accessibilityLabel={`${talk.video_url ? 'Watch the recording of' : 'Open the page for'} ${talk.title}`}
          onPress={() => void Linking.openURL(recording)} />
      ) : null}
    </View>
  );
}

function summary(result: ArchiveSearchResult, searching: boolean, shown: number) {
  if (!result.total) return 'No talks match. Try different words or clear a filter.';
  if (!searching) return `${count.format(result.total)} talks, newest first. Showing ${count.format(shown)}.`;
  const reachable = Math.min(result.total, 100);
  return `${count.format(result.total)} talks match. Showing ${count.format(shown)} of the top ${reachable} by relevance.`;
}

export function PastTalks({ onBrowseSchedule }: { onBrowseSchedule: () => void }) {
  const [query, setQuery] = useState('');
  const [debounced, setDebounced] = useState('');
  const [track, setTrack] = useState<string>();
  const [source, setSource] = useState<string>();
  const [pageNumber, setPageNumber] = useState(1);
  const [result, setResult] = useState<ArchiveSearchResult>();
  const [talks, setTalks] = useState<ArchiveSearchTalk[]>([]);
  const [trackOptions, setTrackOptions] = useState<ArchiveFacet[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const inFlight = useRef<AbortController>(null);

  // Wait for a pause in typing before searching, and start again from page 1.
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(query.trim()), 300);
    return () => clearTimeout(timer);
  }, [query]);
  useEffect(() => setPageNumber(1), [debounced, track, source]);

  useEffect(() => {
    inFlight.current?.abort();
    const controller = new AbortController();
    inFlight.current = controller;
    setLoading(true);
    setError('');
    searchArchiveTalks({ q: debounced, track, source, page: pageNumber }, controller.signal)
      .then((next) => {
        if (controller.signal.aborted) return;
        setResult(next);
        setTalks((previous) => (pageNumber === 1 ? next.talks : [...previous, ...next.talks]));
        // Keep the track chips stable while a track is selected (its facets only list that track).
        if (!track) setTrackOptions(next.facets.tracks);
      })
      .catch((reason: unknown) => {
        if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : 'Could not search talks.');
      })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [debounced, track, source, pageNumber]);

  const firstLoad = loading && !result;
  return (
    <Container style={page.block}>
      <Heading large>Search Talks</Heading>
      <Field label="Search talks, speakers, or events" value={query} onChangeText={setQuery} autoCorrect={false}
        placeholder="Try “something on eBPF and security”" />
      <View accessibilityLabel="Filter by source" style={page.filters}>
        <Chip title="All sources" selected={!source} onPress={() => setSource(undefined)} />
        {SOURCES.map((item) => (
          <Chip key={item.value} title={item.label} selected={source === item.value}
            onPress={() => setSource(source === item.value ? undefined : item.value)} />
        ))}
      </View>
      {trackOptions.length ? (
        <View accessibilityLabel="Filter by track" style={page.filters}>
          <Chip title="All tracks" selected={!track} onPress={() => setTrack(undefined)} />
          {trackOptions.map((item) => (
            <Chip key={String(item.value)} title={String(item.value)} selected={track === item.value}
              onPress={() => setTrack(track === item.value ? undefined : String(item.value))} />
          ))}
        </View>
      ) : null}
      <View style={styles.row}>
        <Action title="Browse my event schedule" onPress={onBrowseSchedule} secondary />
      </View>
      {error ? <Message error>{error}</Message> : null}
      {firstLoad ? <Message>Loading talks…</Message> : null}
      {result && !error ? <Message>{summary(result, Boolean(debounced), talks.length)}</Message> : null}
      <View style={page.list}>
        {talks.map((talk) => <ArchiveTalkCard key={talk.id} talk={talk} />)}
      </View>
      {result?.has_more ? (
        <Action title={loading ? 'Loading…' : 'Show more talks'} disabled={loading}
          onPress={() => setPageNumber((n) => n + 1)} secondary />
      ) : null}
    </Container>
  );
}
