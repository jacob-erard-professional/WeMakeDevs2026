import { useEffect, useRef, useState } from 'react';
import { Linking, StyleSheet, View } from 'react-native';

import { searchCatalogTalks } from '../api';
import type { CatalogSource, CatalogTalk } from '../api';
import { Action, colors, Copy, Heading, Label, Message, TalkDetails, styles } from '../ui';

function httpLink(value?: string) {
  try {
    const url = new URL(value ?? '');
    return url.protocol === 'https:' || url.protocol === 'http:' ? url.href : undefined;
  } catch {
    return undefined;
  }
}

function TalkRow({ talk, onConference }: { talk: CatalogTalk; onConference?: (id: string) => void }) {
  const [error, setError] = useState('');
  const event = [talk.conference, talk.year].filter(Boolean).join(' · ');
  const page = httpLink(talk.url);
  const video = httpLink(talk.video_url);
  const eventId = talk.event_id;

  async function open(url: string) {
    try { await Linking.openURL(url); }
    catch { setError('Could not open this link.'); }
  }

  return (
    <View style={catalog.row}>
      {event ? <Label>{event}</Label> : null}
      <Heading>{talk.title}</Heading>
      {talk.speakers.length ? <Copy>{talk.speakers.join(', ')}</Copy> : null}
      {talk.tracks.length ? <Copy>{talk.tracks.join(' · ')}</Copy> : null}
      {talk.room ? <Copy>{talk.room}</Copy> : null}
      {talk.abstract ? <TalkDetails title={talk.title} abstract={talk.abstract} /> : null}
      {page || video || (eventId && onConference) ? (
        <View style={styles.row}>
          {page ? <Action title="Open talk page" accessibilityLabel={`Open talk page for ${talk.title}`} onPress={() => void open(page)} secondary /> : null}
          {video ? <Action title="Watch recording" accessibilityLabel={`Watch recording for ${talk.title}`} onPress={() => void open(video)} secondary /> : null}
          {eventId && onConference ? (
            <Action title="Open event schedule" accessibilityLabel={`Open event schedule for ${talk.title}`}
              onPress={() => onConference(eventId)} secondary />
          ) : null}
        </View>
      ) : null}
      {error ? <Message error>{error}</Message> : null}
    </View>
  );
}

export function CatalogTalks({ source, query = '', eventId, onConference }: {
  source: CatalogSource;
  query?: string;
  eventId?: string;
  onConference?: (id: string) => void;
}) {
  const [talks, setTalks] = useState<CatalogTalk[]>([]);
  const [next, setNext] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const request = useRef<AbortController>(null);

  async function load(offset: number) {
    if (request.current) return;
    const controller = new AbortController();
    request.current = controller;
    setLoading(true);
    setError('');
    try {
      const result = await searchCatalogTalks(source, query, eventId, offset, controller.signal);
      if (controller.signal.aborted) return;
      setTalks((current) => offset ? [...current, ...result.talks] : result.talks);
      setNext(result.next_offset);
    } catch {
      if (!controller.signal.aborted) setError('Could not load talks. Try again.');
    } finally {
      if (request.current === controller) {
        request.current = null;
        setLoading(false);
      }
    }
  }

  useEffect(() => {
    void load(0);
    return () => {
      request.current?.abort();
      request.current = null;
    };
  }, [source, query, eventId]);

  return (
    <View style={styles.stack}>
      {talks.map((talk) => <TalkRow key={talk.id} talk={talk} onConference={onConference} />)}
      {loading ? <Message>Loading talks…</Message> : null}
      {error ? <Message error>{error}</Message> : null}
      {!loading && !error && !talks.length ? <Message>{query ? 'No talks match your search.' : 'No talks are available yet.'}</Message> : null}
      {!loading && (error || next !== null) ? (
        <Action title={error ? 'Retry loading talks' : 'Load more talks'} onPress={() => void load(next ?? 0)} secondary />
      ) : null}
    </View>
  );
}

const catalog = StyleSheet.create({
  row: { borderTopWidth: 1, borderColor: colors.chrome, paddingTop: 15, gap: 7 },
});
