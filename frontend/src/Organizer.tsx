import { useState } from 'react';
import { StyleSheet, Text, View } from 'react-native';
import QRCode from 'react-native-qrcode-svg';

import { formatTime, parseSchedule } from './conference';
import type { Conference } from './conference';
import { sampleSchedule } from './demoConference';
import { Flow } from './Flow';
import { joinUrl } from './joinLink';
import { Action, colors, Copy, Field, Heading, Label, Message, Section, styles } from './ui';

export function Organizer({ onPublish }: { onPublish: (name: string, talks: Conference['talks']) => Conference }) {
  const [name, setName] = useState('');
  const [source, setSource] = useState('');
  const [preview, setPreview] = useState<ReturnType<typeof parseSchedule>>();
  const [published, setPublished] = useState<Conference>();

  if (published) {
    return (
      <Flow step="published" style={styles.section}>
        <Label>ATTENDEE ENTRY PASS</Label>
        <Heading large>{published.name}</Heading>
        <View style={passStyles.pass}>
          <View accessible accessibilityRole="image" accessibilityLabel={`QR code linking to ${joinUrl(published.code)}`}>
            <QRCode value={joinUrl(published.code)} size={132} quietZone={28} />
          </View>
          <View style={passStyles.details}>
            <Label>JOIN CODE</Label>
            <Text selectable style={passStyles.code}>{published.code}</Text>
            <Text selectable style={passStyles.link}>{joinUrl(published.code)}</Text>
            <Copy>Scan with your phone camera to open the join link, or type the code at check-in.</Copy>
          </View>
        </View>
        <Copy>Demo events are available in this app session. Joining a newly created event on another device requires the live backend.</Copy>
        <Action title="Create another conference" onPress={() => {
          setPublished(undefined);
          setPreview(undefined);
          setName('');
          setSource('');
        }} secondary />
      </Flow>
    );
  }

  return (
    <Flow step="schedule" style={styles.stack}>
      <Heading large>Create a conference</Heading>
      <Copy>Paste a schedule and review the talks before publishing. This demo imports text for a single day in Mountain Time.</Copy>
      <Section>
        <Field label="Conference name" value={name} onChangeText={setName} maxLength={100} />
        <Copy>One talk per line in the format start | end | title | topic | room. Use 24-hour times.</Copy>
        <Field label="Schedule text" value={source} onChangeText={(text) => { setSource(text); setPreview(undefined); }} multiline maxLength={20000} />
        <View style={styles.row}>
          <Action title="Load sample schedule" onPress={() => { setSource(sampleSchedule); setPreview(undefined); }} secondary />
          <Action title="Preview schedule" onPress={() => setPreview(parseSchedule(source))} />
        </View>
      </Section>
      {preview ? (
        <Section>
          <Heading>Schedule preview</Heading>
          {preview.warnings.map((warning) => <Message key={warning} error>{warning}</Message>)}
          {preview.talks.length === 0 ? <Message error>Add at least one valid talk to publish.</Message> : null}
          {preview.talks.map((talk) => (
            <Copy key={talk.id}>{formatTime(talk.start)} to {formatTime(talk.end)} · {talk.title} · {talk.track} · {talk.room}</Copy>
          ))}
          {!name.trim() ? <Copy>Enter a conference name to publish.</Copy> : null}
          <Action title="Publish conference" disabled={!name.trim() || !preview.talks.length || !!preview.warnings.length}
            onPress={() => setPublished(onPublish(name.trim(), preview.talks))} />
        </Section>
      ) : null}
    </Flow>
  );
}

const passStyles = StyleSheet.create({
  pass: { flexDirection: 'row', alignItems: 'center', flexWrap: 'wrap', columnGap: 20, rowGap: 12 },
  details: { flexGrow: 1, flexBasis: 185, gap: 6, paddingVertical: 12 },
  code: { color: colors.ink, fontSize: 32, fontWeight: '700', fontVariant: ['tabular-nums'] },
  link: { color: colors.muted, fontSize: 13 },
});
