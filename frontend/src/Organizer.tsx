import { getDocumentAsync } from 'expo-document-picker';
import { useRef, useState } from 'react';
import { View } from 'react-native';

import { confirmLiveSchedule, createLiveConference, parseLiveSchedule } from './api';
import { venueMinutes } from './api';
import type { OrganizerSession, ParsedTalk } from './api';
import { ScheduleGrid } from './ScheduleGrid';
import type { ResumeAsset } from './conference';
import { sampleSchedule } from './demoConference';
import { EntryPass } from './EntryPass';
import { Flow } from './Flow';
import { joinUrl } from './joinLink';
import { parsePastedSchedule, validScheduleDate } from './scheduleText';
import { organizerSession } from './session';
import { Action, Copy, Field, Heading, Label, Message, Section, TalkDetails, styles } from './ui';

const sources = ['Schedule link', 'Image or PDF', 'Paste text'] as const;
type Source = typeof sources[number];
type Draft = { talks: ParsedTalk[]; warnings: string[] };
const scheduleTypes: Record<string, string> = {
  pdf: 'application/pdf', png: 'image/png', jpg: 'image/jpeg', jpeg: 'image/jpeg', webp: 'image/webp',
};

const venueTime = new Intl.DateTimeFormat('en-US', {
  timeZone: 'America/Denver', weekday: 'short', hour: 'numeric', minute: '2-digit',
});

function displayTime(timestamp: string) {
  const date = new Date(timestamp);
  return Number.isNaN(date.getTime()) ? timestamp.trim() || 'Time TBD' : venueTime.format(date);
}

function validTalk(talk: ParsedTalk) {
  const zoned = /(?:Z|[+-]\d{2}:\d{2})$/i;
  return !!talk.title.trim() && zoned.test(talk.start_time) && zoned.test(talk.end_time)
    && Date.parse(talk.end_time) > Date.parse(talk.start_time);
}

function validLink(value: string) {
  try {
    const url = new URL(value);
    return (url.protocol === 'http:' || url.protocol === 'https:') && !url.username && !url.password;
  } catch {
    return false;
  }
}

export function Organizer({ onPublishSample, onTrySample }: {
  onPublishSample: (name: string, talks: ParsedTalk[]) => string;
  onTrySample: (code: string) => void;
}) {
  // A refresh must not lock the organizer out of the conference they just created: live
  // sessions (token, event details, parsed draft, published flag) are restored from this
  // browser's storage. Sample sessions stay in-app only.
  const [stored] = useState(organizerSession.load);
  const [name, setName] = useState('');
  const [date, setDate] = useState(stored?.date ?? '');
  const [venue, setVenue] = useState(stored?.venue ?? '');
  const [description, setDescription] = useState(stored?.description ?? '');
  const [session, setSession] = useState<OrganizerSession | { name: string; sample: true } | undefined>(stored && {
    conferenceId: stored.conferenceId, organizerToken: stored.organizerToken, name: stored.name,
  });
  const [sampleMode, setSampleMode] = useState(false);
  const [source, setSource] = useState<Source>('Schedule link');
  const [sourceUrl, setSourceUrl] = useState('');
  const [asset, setAsset] = useState<ResumeAsset>();
  const [text, setText] = useState('');
  const [draft, setDraft] = useState<Draft | undefined>(stored?.draft);
  const [editingTalk, setEditingTalk] = useState<number>();
  const [publishedCode, setPublishedCode] = useState<string | undefined>(stored?.published ? stored.conferenceId : undefined);

  function persist(live: OrganizerSession, changes: { draft?: Draft; published?: boolean }) {
    organizerSession.save({ ...live, draft, published: !!publishedCode, date, venue, description, ...changes });
  }
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const inProgress = useRef(false);

  async function run(operation: () => Promise<void>, fallback: string) {
    if (inProgress.current) return;
    inProgress.current = true;
    setBusy(true);
    setError('');
    try { await operation(); }
    catch (reason) { setError(reason instanceof Error ? reason.message : fallback); }
    finally { inProgress.current = false; setBusy(false); }
  }

  function createConference() {
    if (!name.trim()) { setError('Enter a conference name first.'); return; }
    if (date && !validScheduleDate(date)) { setError('Enter the event date in YYYY-MM-DD format.'); return; }
    if (sampleMode) {
      setError('');
      setSession({ name: name.trim(), sample: true });
      return;
    }
    void run(async () => {
      const created = await createLiveConference(name.trim());
      setSession(created);
      persist(created, {});
    }, 'Could not create the conference.');
  }

  async function chooseFile() {
    setError('');
    try {
      const result = await getDocumentAsync({
        type: ['application/pdf', 'image/png', 'image/jpeg', 'image/webp'],
        copyToCacheDirectory: true,
        base64: false,
      });
      if (result.canceled) return;
      const selected = result.assets[0];
      if ((selected.size ?? 0) > 10 * 1024 * 1024) { setError('Choose a file under 10 MiB.'); return; }
      const detectedType = selected.mimeType || selected.file?.type;
      const mimeType = detectedType && detectedType !== 'application/octet-stream' ? detectedType
        : scheduleTypes[selected.name.split('.').pop()?.toLowerCase() ?? ''];
      if (!Object.values(scheduleTypes).includes(mimeType)) {
        setError('Choose a PDF, PNG, JPEG, or WebP schedule.');
        return;
      }
      setAsset({ ...selected, mimeType });
      setDraft(undefined);
    } catch {
      setError('Could not open the file picker.');
    }
  }

  function reviewSchedule() {
    if (!session) return;
    setError('');
    setEditingTalk(undefined);
    if ('sample' in session || source === 'Paste text') {
      setDraft(parsePastedSchedule(text, date));
      return;
    }
    if (source === 'Schedule link' && !validLink(sourceUrl.trim())) {
      setError('Enter a public HTTP or HTTPS schedule link.');
      return;
    }
    void run(async () => {
      const parsed = await parseLiveSchedule(session, source === 'Schedule link' ? sourceUrl.trim() : undefined, source === 'Image or PDF' ? asset : undefined);
      setDraft(parsed);
      persist(session, { draft: parsed });
    }, 'Could not import the schedule.');
  }

  function editTalk(index: number, update: Partial<ParsedTalk>) {
    setDraft((current) => current && {
      ...current, talks: current.talks.map((talk, position) => position === index ? { ...talk, ...update } : talk),
    });
  }

  function publish() {
    if (!session || !draft?.talks.length) return;
    if ('sample' in session) {
      setPublishedCode(onPublishSample(session.name, draft.talks));
      return;
    }
    void run(async () => {
      await confirmLiveSchedule(session, draft.talks);
      setPublishedCode(session.conferenceId);
      persist(session, { published: true });
    }, 'Could not publish the schedule.');
  }

  // Also "Start a new conference": forgets this browser's organizer session.
  function reset() {
    organizerSession.clear();
    setPublishedCode(undefined);
    setSampleMode(false);
    setSession(undefined);
    setDraft(undefined);
    setEditingTalk(undefined);
    setAsset(undefined);
    setSourceUrl('');
    setText('');
    setName('');
    setVenue('');
    setDate('');
    setDescription('');
    setSource('Schedule link');
    setError('');
  }

  function loadSample() {
    setSampleMode(true);
    setName('Sample Cloud Native Conference');
    setDate('2026-11-09');
    setVenue('Summit Conference Center');
    setDescription('A day of talks for people who build and operate software platforms.');
    setSource('Paste text');
    setText(sampleSchedule);
    setError('');
  }

  if (publishedCode && session) {
    return (
      <Flow step="published">
        <EntryPass name={session.name} code={publishedCode} link={joinUrl(publishedCode)}
          details={[date, venue, description].filter(Boolean).join(' · ')} onReset={reset}
          onTrySample={'sample' in session ? () => onTrySample(publishedCode) : undefined} />
      </Flow>
    );
  }

  const canReview = source === 'Schedule link' ? !!sourceUrl.trim() : source === 'Image or PDF' ? !!asset : !!text.trim();
  const invalidTalks = draft?.talks.some((talk) => !validTalk(talk));
  const canPublish = !!draft?.talks.length && (source !== 'Paste text' || !draft.warnings.length) && !invalidTalks;

  return (
    <Flow step={session ? 'schedule' : 'details'} style={styles.stack}>
      <Label>{session ? 'Step 2 of 2 · Schedule' : 'Step 1 of 2 · Event details'}</Label>
      <Heading large>{session ? 'Add your sessions' : 'Create a conference'}</Heading>
      {sampleMode ? <Message>Sample mode. This conference stays in this app session.</Message> : null}
      {!session ? <Section>
        <Action title={sampleMode ? 'Switch to live setup' : 'Try sample organizer flow'} disabled={busy}
          onPress={sampleMode ? reset : loadSample} secondary />
        <Field label="Conference name" value={name} onChangeText={setName} maxLength={160} editable={!busy} />
        <Field label="Event date (optional)" placeholder="YYYY-MM-DD" value={date} onChangeText={setDate} maxLength={10} editable={!busy} />
        <Field label="Venue or location (optional)" value={venue} onChangeText={setVenue} maxLength={160} editable={!busy} />
        <Field label="Description (optional)" value={description} onChangeText={setDescription} maxLength={600} multiline editable={!busy} />
        <Copy>The date, venue, and description stay in this organizer session. Attendees see the conference name and published schedule.</Copy>
        <Action title={busy ? 'Creating conference…' : 'Continue to schedule'} onPress={createConference} disabled={busy} />
      </Section> : <Section>
        <Copy>Import a schedule for {session.name}. Review the sessions before sharing the event.</Copy>
        {sampleMode ? null : <View style={styles.row}>
          {sources.map((item) => <Action key={item} title={item} selected={source === item} disabled={busy}
            onPress={() => { setSource(item); setDraft(undefined); setEditingTalk(undefined); setError(''); }} secondary />)}
        </View>}
        {source === 'Schedule link' ? (
          <Field label="Public schedule URL" value={sourceUrl} autoCapitalize="none" keyboardType="url"
            placeholder="https://…" maxLength={2000} editable={!busy}
            onChangeText={(value) => { setSourceUrl(value); setDraft(undefined); }} />
        ) : source === 'Image or PDF' ? (
          <>
            <Copy>Use a PDF, PNG, JPEG, or WebP file up to 10 MiB.</Copy>
            <Action title="Choose schedule file" onPress={() => void chooseFile()} disabled={busy} secondary />
            {asset ? <Copy>Selected: {asset.name}</Copy> : null}
          </>
        ) : (
          <>
            <Copy>Paste one session per line as start | end | title | track | room. Use 24-hour Mountain Time.</Copy>
            <Field label="Schedule date" value={date} placeholder="YYYY-MM-DD" maxLength={10} editable={!busy}
              onChangeText={(value) => { setDate(value); setDraft(undefined); }} />
            <Field label="Schedule text" value={text} placeholder="09:00 | 09:45 | Opening keynote | General | Main hall" multiline maxLength={20000}
              editable={!busy} onChangeText={(value) => { setText(value); setDraft(undefined); }} />
          </>
        )}
        <Action title={busy ? 'Working…' : 'Preview schedule'} onPress={reviewSchedule} disabled={busy || !canReview} />
        {'sample' in session ? null : <Action title="Start a new conference" onPress={reset} disabled={busy} secondary />}
      </Section>}
      {draft ? <Section>
        <Heading>Review schedule</Heading>
        {draft.warnings.map((warning, index) => <Message key={index} error>{warning}</Message>)}
        {!draft.talks.length ? <Message error>No usable sessions were found. Try another source.</Message> : null}
        <Copy>Sessions are laid out by time and room. Choose a session to edit it.</Copy>
        <ScheduleGrid
          talks={draft.talks.map((talk, index) => ({
            id: String(index),
            title: talk.title,
            room: talk.room,
            track: talk.track?.join(', '),
            speakers: talk.speakers,
            start: venueMinutes(talk.start_time),
            end: venueMinutes(talk.end_time),
            startsAt: talk.start_time,
          }))}
          onSelect={(talk) => { if (!busy) setEditingTalk(editingTalk === Number(talk.id) ? undefined : Number(talk.id)); }}
        />
        {editingTalk !== undefined && draft.talks[editingTalk] ? (() => {
          const index = editingTalk;
          const talk = draft.talks[index];
          return (
            <View style={styles.stack}>
              <Heading>{talk.title || 'Untitled session'}</Heading>
              <Copy>{displayTime(talk.start_time)} to {displayTime(talk.end_time)} · {talk.room || 'Room TBA'}</Copy>
              <Action title="Done editing" onPress={() => setEditingTalk(undefined)} disabled={busy} secondary />
              <Field label="Session title" value={talk.title} editable={!busy} onChangeText={(title) => editTalk(index, { title })} />
              <Field label="Room" value={talk.room ?? ''} editable={!busy} onChangeText={(room) => editTalk(index, { room })} />
              <Field label="Starts at (ISO timestamp)" value={talk.start_time} editable={!busy} autoCapitalize="none"
                onChangeText={(start_time) => editTalk(index, { start_time })} />
              <Field label="Ends at (ISO timestamp)" value={talk.end_time} editable={!busy} autoCapitalize="none"
                onChangeText={(end_time) => editTalk(index, { end_time })} />
              <Field label="Abstract" multiline value={talk.abstract ?? ''} editable={!busy} onChangeText={(abstract) => editTalk(index, { abstract })} />
            </View>
          );
        })() : null}
        {invalidTalks ? <Message error>Each session needs a title and valid start and end times with a time zone offset.</Message> : null}
        <Action title={busy ? 'Publishing…' : 'Confirm and publish'} onPress={publish} disabled={busy || !canPublish} />
      </Section> : null}
      {error ? <Message error>{error}</Message> : null}
    </Flow>
  );
}
