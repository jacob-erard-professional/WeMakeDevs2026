import { getDocumentAsync } from 'expo-document-picker';
import { useState } from 'react';
import { StyleSheet, Text, View } from 'react-native';
import QRCode from 'react-native-qrcode-svg';

import { confirmLiveSchedule, createLiveConference, parseLiveSchedule } from './api';
import type { OrganizerSession, ParsedTalk } from './api';
import { Flow } from './Flow';
import { Action, colors, Copy, Field, Heading, Label, Message, Section, styles } from './ui';

type ScheduleAsset = { uri: string; name: string };

function displayTime(timestamp: string) {
  const date = new Date(timestamp);
  if (Number.isNaN(date.getTime())) return timestamp || 'Time TBA';
  return new Intl.DateTimeFormat('en-US', {
    timeZone: 'America/Denver', weekday: 'short', hour: 'numeric', minute: '2-digit',
  }).format(date);
}

export function Organizer() {
  const [name, setName] = useState('');
  const [session, setSession] = useState<OrganizerSession>();
  const [sourceUrl, setSourceUrl] = useState('');
  const [asset, setAsset] = useState<ScheduleAsset>();
  const [draft, setDraft] = useState<{ talks: ParsedTalk[]; warnings: string[] }>();
  const [published, setPublished] = useState<{ joinUrl: string }>();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  async function createConference() {
    if (!name.trim()) { setError('Enter a conference name first.'); return; }
    setBusy(true); setError('');
    try { setSession(await createLiveConference(name.trim())); }
    catch (reason) { setError(reason instanceof Error ? reason.message : 'Could not create the conference.'); }
    finally { setBusy(false); }
  }

  async function chooseFile() {
    setError('');
    const result = await getDocumentAsync({ type: ['application/pdf', 'image/*'], copyToCacheDirectory: false });
    if (!result.canceled) { setAsset(result.assets[0]); setSourceUrl(''); setDraft(undefined); }
  }

  async function parseSchedule() {
    if (!session) return;
    setBusy(true); setError('');
    try { setDraft(await parseLiveSchedule(session, sourceUrl.trim() || undefined, asset)); }
    catch (reason) { setError(reason instanceof Error ? reason.message : 'Could not parse the schedule.'); }
    finally { setBusy(false); }
  }

  async function publish() {
    if (!session || !draft?.talks.length) return;
    setBusy(true); setError('');
    try { setPublished({ joinUrl: (await confirmLiveSchedule(session, draft.talks)).join_url }); }
    catch (reason) { setError(reason instanceof Error ? reason.message : 'Could not publish the schedule.'); }
    finally { setBusy(false); }
  }

  if (published && session) return (
    <Flow step="published" style={styles.section}>
      <Label>ATTENDEE ENTRY PASS</Label><Heading large>{session.name}</Heading>
      <View style={passStyles.pass}>
        <View accessible accessibilityRole="image" accessibilityLabel={`Conference QR code for ${session.name}`}>
          <QRCode value={published.joinUrl} size={132} quietZone={28} />
        </View>
        <View style={passStyles.details}>
          <Label>JOIN LINK</Label><Text selectable style={passStyles.url}>{published.joinUrl}</Text>
          <Copy>Attendees can scan this QR code in the app, or paste this link into the app's conference code field.</Copy>
        </View>
      </View>
    </Flow>
  );

  return (
    <Flow step={session ? 'schedule' : 'create'} style={styles.stack}>
      <Heading large>{session ? `Schedule for ${session.name}` : 'Create a conference'}</Heading>
      {!session ? <Section>
        <Copy>Create a private organizer session, then import a schedule for review.</Copy>
        <Field label="Conference name" value={name} onChangeText={setName} maxLength={160} />
        <Action title={busy ? 'Creating conference…' : 'Create conference'} onPress={createConference} disabled={busy} />
      </Section> : <Section>
        <Copy>Paste a schedule link or upload a PDF/image. It stays private until you confirm it.</Copy>
        <Field label="Schedule link" value={sourceUrl} onChangeText={(value) => { setSourceUrl(value); setAsset(undefined); setDraft(undefined); }} autoCapitalize="none" keyboardType="url" placeholder="https://…" />
        <View style={styles.row}>
          <Action title="Choose PDF or image" onPress={chooseFile} secondary disabled={busy} />
          {asset ? <Copy>Selected: {asset.name}</Copy> : null}
        </View>
        <Action title={busy ? 'Parsing schedule…' : 'Parse schedule'} onPress={parseSchedule} disabled={busy || (!sourceUrl.trim() && !asset)} />
      </Section>}
      {error ? <Message error>{error}</Message> : null}
      {draft ? <Section>
        <Heading>Review parsed schedule</Heading>
        {draft.warnings.map((warning) => <Message key={warning} error>{warning}</Message>)}
        {!draft.talks.length ? <Message error>No usable sessions were found. Try another source.</Message> : null}
        {draft.talks.map((talk, index) => <Copy key={`${talk.title}-${index}`}>{displayTime(talk.start_time)} to {displayTime(talk.end_time)} · {talk.title} · {talk.room || 'Room TBA'}</Copy>)}
        <Action title={busy ? 'Publishing…' : 'Confirm and publish'} onPress={publish} disabled={busy || !draft.talks.length} />
      </Section> : null}
    </Flow>
  );
}

const passStyles = StyleSheet.create({
  pass: { flexDirection: 'row', alignItems: 'center', flexWrap: 'wrap', columnGap: 20, rowGap: 12 },
  details: { flexGrow: 1, flexBasis: 185, gap: 6, paddingVertical: 12 },
  url: { color: colors.ink, fontSize: 15, fontWeight: '700' },
});
