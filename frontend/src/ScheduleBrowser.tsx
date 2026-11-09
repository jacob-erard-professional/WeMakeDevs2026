import { useEffect, useState } from 'react';
import { Linking, View } from 'react-native';

import { loadRelatedTalks } from './api';
import type { ArchiveTalk } from './api';
import { formatTime } from './conference';
import type { Conference, Talk } from './conference';
import { demoConference } from './demoConference';
import { Flow } from './Flow';
import { Action, Copy, Field, Heading, Label, Message, styles } from './ui';

const venueDate = new Intl.DateTimeFormat('en-US', { timeZone: 'America/Denver', weekday: 'short', month: 'short', day: 'numeric' });

function when(talk: Talk) {
  const timestamp = Date.parse(talk.startsAt ?? '');
  const date = Number.isNaN(timestamp) ? '' : `${venueDate.format(timestamp)} · `;
  return `${date}${formatTime(talk.start)} to ${formatTime(talk.end)} · ${talk.room}`;
}

function safeLink(value?: string) {
  if (!value) return undefined;
  try {
    const url = new URL(value);
    if ((url.protocol === 'https:' || url.protocol === 'http:') && url.hostname) return url.href;
  } catch {
    return undefined;
  }
  return undefined;
}

function RelatedTalks({ conference, talk, token, onProfile }: {
  conference: Conference;
  talk: Talk;
  token?: string;
  onProfile: () => void;
}) {
  const [items, setItems] = useState<ArchiveTalk[]>();
  const [error, setError] = useState('');
  const [linkError, setLinkError] = useState('');
  const [retry, setRetry] = useState(0);

  useEffect(() => {
    if (!token) return;
    const controller = new AbortController();
    setItems(undefined);
    setError('');
    loadRelatedTalks(conference.code, talk.id, token, controller.signal)
      .then((result) => { if (!controller.signal.aborted) setItems(result); })
      .catch(() => { if (!controller.signal.aborted) setError('Could not load related talks. Try again in a moment.'); });
    return () => controller.abort();
  }, [conference.code, talk.id, token, retry]);

  async function open(url: string) {
    setLinkError('');
    try { await Linking.openURL(url); }
    catch { setLinkError('Could not open that archive link.'); }
  }

  return (
    <View style={styles.stack}>
      <Heading>Similar past talks</Heading>
      {!token ? (
        conference.code === demoConference.code ? <Copy>The sample conference does not query the live talk archive.</Copy> : (
          <>
            <Copy>Complete your attendee profile to search the archive for this session.</Copy>
            <Action title="Complete attendee profile" onPress={onProfile} />
          </>
        )
      ) : null}
      {token && !items && !error ? <Message>Finding similar past talks…</Message> : null}
      {error ? (
        <>
          <Message error>{error}</Message>
          <Action title="Retry similar talks" onPress={() => setRetry((current) => current + 1)} secondary />
        </>
      ) : null}
      {items?.length === 0 ? <Copy>No similar talks were found in the archive.</Copy> : null}
      {linkError ? <Message error>{linkError}</Message> : null}
      {items?.map((item, index) => {
        const page = safeLink(item.url);
        const video = safeLink(item.video_url);
        return (
          <View key={`${item.title}-${index}`} style={styles.stack}>
            <Heading>{item.title}</Heading>
            <Copy>{[item.conference, item.year].filter(Boolean).join(' · ')}</Copy>
            <View style={styles.row}>
              {page ? <Action title={`Open talk page: ${item.title}`} onPress={() => void open(page)} secondary /> : null}
              {video ? <Action title={`Watch recording: ${item.title}`} onPress={() => void open(video)} secondary /> : null}
            </View>
          </View>
        );
      })}
    </View>
  );
}

export function ScheduleBrowser({ conference, attendeeToken, initialTalkId, onProfile }: {
  conference: Conference;
  attendeeToken?: string;
  initialTalkId?: string;
  onProfile: (talkId: string) => void;
}) {
  const [selected, setSelected] = useState(() => conference.talks.find((talk) => talk.id === initialTalkId));
  const [query, setQuery] = useState('');
  const needle = query.trim().toLowerCase();
  const visible = conference.talks.filter((talk) => [talk.title, talk.track, talk.room]
    .some((text) => text.toLowerCase().includes(needle)));

  return (
    <Flow step={selected?.id ?? 'schedule'} style={styles.stack}>
      {selected ? (
        <>
          <Action title="Back to event schedule" onPress={() => setSelected(undefined)} secondary />
          <Label>{when(selected)}</Label>
          <Heading large>{selected.title}</Heading>
          <Copy>{selected.abstract || selected.track}</Copy>
          <RelatedTalks key={selected.id} conference={conference} talk={selected} token={attendeeToken}
            onProfile={() => onProfile(selected.id)} />
        </>
      ) : (
        <>
          <Heading>Event schedule</Heading>
          <Copy>Choose a session to see its details and find related recordings. All times are Mountain Time.</Copy>
          <Field label="Search the event schedule" value={query} onChangeText={setQuery} />
          {!visible.length ? <Message>No sessions match your search.</Message> : null}
          {visible.map((talk) => (
            <View key={talk.id}>
              <Label>{when(talk)}</Label>
              <Action title={talk.title} onPress={() => setSelected(talk)} secondary />
            </View>
          ))}
        </>
      )}
    </Flow>
  );
}
