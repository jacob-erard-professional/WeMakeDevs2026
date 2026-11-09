import { useState } from 'react';
import { View } from 'react-native';

import { formatTime, parseSchedule } from './conference';
import type { Conference } from './conference';
import { sampleSchedule } from './demoConference';
import { Action, Card, Copy, Field, Heading, Label, Message, styles } from './ui';

export function Organizer({ onPublish }: { onPublish: (name: string, talks: Conference['talks']) => Conference }) {
  const [name, setName] = useState('');
  const [source, setSource] = useState('');
  const [preview, setPreview] = useState<ReturnType<typeof parseSchedule>>();
  const [published, setPublished] = useState<Conference>();

  if (published) {
    return (
      <Card>
        <Label>DEMO CONFERENCE PUBLISHED</Label>
        <Heading>{published.name}</Heading>
        <Copy>Join code: {published.code}</Copy>
        <Copy>Enter this code in the attendee flow. Published conferences are available in this session only.</Copy>
        <Action title="Create another conference" onPress={() => {
          setPublished(undefined);
          setPreview(undefined);
          setName('');
          setSource('');
        }} secondary />
      </Card>
    );
  }

  return (
    <View style={styles.stack}>
      <Heading>Create a conference</Heading>
      <Copy>Paste a schedule and review the talks before publishing. This demo imports text for a single day in Mountain Time.</Copy>
      <Card>
        <Field label="Conference name" value={name} onChangeText={setName} maxLength={100} />
        <Copy>One talk per line in the format start | end | title | topic | room. Use 24-hour times.</Copy>
        <Field label="Schedule text" value={source} onChangeText={(text) => { setSource(text); setPreview(undefined); }} multiline maxLength={20000} />
        <View style={styles.row}>
          <Action title="Load sample schedule" onPress={() => { setSource(sampleSchedule); setPreview(undefined); }} secondary />
          <Action title="Preview schedule" onPress={() => setPreview(parseSchedule(source))} />
        </View>
      </Card>
      {preview ? (
        <Card>
          <Heading>Schedule preview</Heading>
          {preview.warnings.map((warning) => <Message key={warning} error>{warning}</Message>)}
          {preview.talks.length === 0 ? <Message error>Add at least one valid talk to publish.</Message> : null}
          {preview.talks.map((talk) => (
            <Copy key={talk.id}>{formatTime(talk.start)} to {formatTime(talk.end)} · {talk.title} · {talk.track} · {talk.room}</Copy>
          ))}
          {!name.trim() ? <Copy>Enter a conference name to publish.</Copy> : null}
          <Action title="Publish conference" disabled={!name.trim() || !preview.talks.length || !!preview.warnings.length}
            onPress={() => setPublished(onPublish(name.trim(), preview.talks))} />
        </Card>
      ) : null}
    </View>
  );
}
