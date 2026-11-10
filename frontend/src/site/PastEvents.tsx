import { useEffect, useState } from 'react';
import { StyleSheet, View } from 'react-native';

import { loadCatalogEvents } from '../api';
import type { CatalogEvent, CatalogSource } from '../api';
import { joinPath } from '../joinLink';
import { Action, colors, Copy, Heading, Label, Message, styles } from '../ui';
import { CatalogTalks } from './CatalogTalks';
import { Container } from './SiteShell';

const dateFormat = new Intl.DateTimeFormat('en-US', {
  timeZone: 'America/Denver', month: 'short', day: 'numeric', year: 'numeric',
});

function dates(event: CatalogEvent) {
  const start = Date.parse(event.first_start ?? '');
  const end = Date.parse(event.last_end ?? '');
  if (!Number.isFinite(start)) return event.year ? String(event.year) : '';
  const first = dateFormat.format(start);
  const last = Number.isFinite(end) ? dateFormat.format(end) : first;
  return first === last ? first : `${first} – ${last}`;
}

export function PastEvents({ navigate }: { navigate: (path: string) => void }) {
  const [source, setSource] = useState<CatalogSource>('published');
  const [events, setEvents] = useState<CatalogEvent[]>();
  const [failed, setFailed] = useState(false);
  const [retry, setRetry] = useState(0);
  const [open, setOpen] = useState<string>();

  function chooseSource(next: CatalogSource) {
    if (next === source) return;
    setEvents(undefined);
    setOpen(undefined);
    setFailed(false);
    setSource(next);
  }

  useEffect(() => {
    const controller = new AbortController();
    setEvents(undefined);
    setFailed(false);
    setOpen(undefined);
    loadCatalogEvents(source, controller.signal).then((items) => {
      if (!controller.signal.aborted) setEvents(items);
    }).catch(() => { if (!controller.signal.aborted) setFailed(true); });
    return () => controller.abort();
  }, [source, retry]);

  return (
    <Container style={page.block}>
      <Heading large>Event archive</Heading>
      <Copy>Browse published conferences and schedules from the historical talk archive.</Copy>
      <View style={styles.row}>
        <Action title="Published conferences" selected={source === 'published'} onPress={() => chooseSource('published')} secondary />
        <Action title="Past conferences" selected={source === 'archive'} onPress={() => chooseSource('archive')} secondary />
      </View>
      {failed ? (
        <>
          <Message error>Could not load conferences.</Message>
          <Action title="Retry loading conferences" onPress={() => setRetry((value) => value + 1)} secondary />
        </>
      ) : null}
      {!events && !failed ? <Message>Loading conferences…</Message> : null}
      {events?.length === 0 ? <Message>No conferences are available in this view yet.</Message> : null}
      {events?.map((event) => {
        const expanded = open === event.id;
        const details = [dates(event), `${event.talk_count} ${event.talk_count === 1 ? 'talk' : 'talks'}`].filter(Boolean);
        return (
          <View key={event.id} style={page.event}>
            <Heading>{event.name}</Heading>
            <Label>{details.join(' · ')}</Label>
            <View style={styles.row}>
              <Action title={expanded ? 'Hide talks' : 'Browse talks'} expanded={expanded}
                accessibilityLabel={`${expanded ? 'Hide' : 'Browse'} talks for ${event.name}`}
                onPress={() => setOpen(expanded ? undefined : event.id)} secondary />
              {source === 'published' ? (
                <Action title="Join conference" accessibilityLabel={`Join ${event.name}`}
                  onPress={() => navigate(joinPath(event.id))} secondary />
              ) : null}
            </View>
            {expanded ? <CatalogTalks key={`${source}:${event.id}`} source={source} eventId={event.id} /> : null}
          </View>
        );
      })}
    </Container>
  );
}

const page = StyleSheet.create({
  block: { paddingVertical: 48, maxWidth: 920, gap: 20 },
  event: { borderTopWidth: 1, borderColor: colors.chrome, paddingTop: 16, gap: 7 },
});
