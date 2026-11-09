import { getDocumentAsync } from 'expo-document-picker';
import { useEffect, useRef, useState } from 'react';
import { View } from 'react-native';

import { parseResume } from './api';
import { AvailabilityTimeline } from './AvailabilityTimeline';
import { formatTime, parseTime, talkDay } from './conference';
import type { Attendee, Conference, TimeRange } from './conference';
import { sampleAttendee } from './demoConference';
import { Flow } from './Flow';
import { Action, Copy, Field, Heading, Label, Message, Section, styles } from './ui';

const blank: Attendee = {
  name: '', email: '', bio: '', interests: '', lookingFor: '', linkedin: '',
  resumePublic: false, discoverable: false, unavailable: [],
};

type ProfileStep = 'about' | 'availability';

// A picked file cannot be restored after reload. A saved résumé remains on the server.
export type PreviousResume = { name: string; onServer: boolean };

export function ProfileForm({ initial, conference, previousResume, step, onSave, onStepChange, onChange, onCancel }: {
  initial?: Attendee;
  conference: Conference;
  previousResume?: PreviousResume;
  step: ProfileStep;
  onSave: (profile: Attendee) => Promise<void>;
  onStepChange: (step: ProfileStep) => void;
  onChange: (profile: Attendee) => void;
  onCancel?: () => void;
}) {
  const [profile, setProfile] = useState(initial ?? blank);
  const latest = useRef(profile);
  const saveInProgress = useRef(false);
  const [start, setStart] = useState('');
  const [end, setEnd] = useState('');
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);
  const [mode, setMode] = useState<'available' | 'unavailable'>('unavailable');
  const [reading, setReading] = useState(false);
  const [pickedUp, setPickedUp] = useState<string[]>([]);
  const [resumeNote, setResumeNote] = useState('');
  const parseRequest = useRef(0);
  useEffect(() => () => { parseRequest.current += 1; }, []);
  const days = [...new Set(conference.talks.flatMap((talk) => talkDay(talk.startsAt) ?? []))].sort();
  const [day, setDay] = useState(days[0]);
  const dayTalks = conference.talks.filter((talk) => !day || talkDay(talk.startsAt) === day);
  const timelineStart = Math.floor(Math.min(8 * 60, ...dayTalks.map((talk) => talk.start)) / 15) * 15;
  const timelineEnd = Math.ceil(Math.max(18 * 60, ...dayTalks.map((talk) => talk.end)) / 15) * 15;

  function update(changes: Partial<Attendee>) {
    const next = { ...latest.current, ...changes };
    latest.current = next;
    setProfile(next);
    onChange(next);
  }

  async function pickResume() {
    setError('');
    try {
      const result = await getDocumentAsync({
        type: 'application/pdf', copyToCacheDirectory: false, base64: false,
      });
      if (!result.canceled) {
        const { uri, name, mimeType, file } = result.assets[0];
        const resume = { uri, name, mimeType, file };
        update({ resume });
        if (!conference.sample) void prefillFromResume(resume);
      }
    } catch {
      setError('Could not open the file picker. Try again or continue with a bio.');
    }
  }

  // Fill only fields the attendee has not typed in; never overwrite their words.
  async function prefillFromResume(resume: NonNullable<Attendee['resume']>) {
    const requestId = ++parseRequest.current;
    setReading(true);
    setPickedUp([]);
    setResumeNote('');
    try {
      const { resume_profile: parsed, contact } = await parseResume(resume);
      if (requestId !== parseRequest.current) return;
      const current = latest.current;
      const changes: Partial<Attendee> = {};
      const found: string[] = [];
      if (contact?.name && !current.name.trim()) { changes.name = contact.name; found.push('your name'); }
      if (contact?.email && !current.email.trim()) { changes.email = contact.email; found.push('your email'); }
      if (contact?.linkedin_url && !current.linkedin.trim()) { changes.linkedin = contact.linkedin_url; found.push('your LinkedIn'); }
      const summary = parsed.summary.trim()
        || [parsed.headline.trim(), parsed.working_on.trim()].filter(Boolean).join('. ');
      if (!current.bio.trim() && summary) { changes.bio = summary; found.push('a bio'); }
      const topics = [...parsed.interests, ...parsed.skills].map((item) => item.trim()).filter(Boolean);
      const unique = topics.filter((item, index) => topics.findIndex((other) => other.toLowerCase() === item.toLowerCase()) === index);
      if (!current.interests.trim() && unique.length) { changes.interests = unique.join(', '); found.push(`${unique.length} interests`); }
      if (Object.keys(changes).length) update(changes);
      setPickedUp(found);
      setResumeNote(found.length ? '' : 'We couldn’t pull anything new from that file. Add a bio and interests below.');
    } catch (reason) {
      if (requestId !== parseRequest.current) return;
      setResumeNote(reason instanceof Error
        ? `${reason.message} Your résumé will still be used when you save.`
        : 'We couldn’t read the résumé now. It will still be used when you save.');
    } finally {
      if (requestId === parseRequest.current) setReading(false);
    }
  }

  function removeResume() {
    parseRequest.current += 1;
    setReading(false);
    setPickedUp([]);
    setResumeNote('');
    update({ resume: undefined, resumePublic: false });
  }

  function addBlock() {
    const from = parseTime(start);
    const to = end.trim() === '24:00' ? 1440 : parseTime(end);
    if (from === null || to === null || from >= to) {
      setError('Enter a start and a later end in 24-hour HH:MM format.');
      return;
    }
    if (!markRange({ start: from, end: to })) return;
    setStart('');
    setEnd('');
    setError('');
  }

  function markRange({ start: from, end: to }: TimeRange) {
    const otherDays = profile.unavailable.filter((range) => range.date !== day);
    const ranges = profile.unavailable.filter((range) => range.date === day);
    const selection = { date: day, start: from, end: to };
    const updated = mode === 'available'
      ? ranges.flatMap((range) => {
          if (range.end <= from || range.start >= to) return [range];
          return [
            ...(range.start < from ? [{ ...range, end: from }] : []),
            ...(range.end > to ? [{ ...range, start: to }] : []),
          ];
        })
      : [...ranges, selection].sort((a, b) => a.start - b.start).reduce<TimeRange[]>((merged, range) => {
          const last = merged.at(-1);
          if (last && range.start <= last.end) last.end = Math.max(last.end, range.end);
          else merged.push({ ...range });
          return merged;
        }, []);
    if (otherDays.length + updated.length > 100) {
      setError('Remove an unavailable time before adding another.');
      return false;
    }
    update({ unavailable: [...otherDays, ...updated] });
    setError('');
    return true;
  }

  function changeStep(next: ProfileStep) {
    setError('');
    onStepChange(next);
  }

  // A saved résumé still counts: the server kept its text and reuses it when none is sent.
  const resumeOnServer = !profile.resume && previousResume?.onServer;

  function continueToAvailability() {
    if (!profile.name.trim() || (!profile.bio.trim() && !profile.resume && !resumeOnServer)) {
      setError('Enter your name and add a bio or choose a résumé.');
      return;
    }
    const email = profile.email.trim();
    if (email && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
      setError('Enter a valid email address or leave it blank.');
      return;
    }
    const linkedin = profile.linkedin.trim();
    if (linkedin && !/^https:\/\/(?:[a-z0-9-]+\.)?linkedin\.com\/in\/[a-z0-9_%.-]+\/?$/i.test(linkedin)) {
      setError('Enter a LinkedIn profile URL such as https://www.linkedin.com/in/sample or leave it blank.');
      return;
    }
    update({ name: profile.name.trim(), email, linkedin });
    changeStep('availability');
  }

  async function save() {
    if (saveInProgress.current) return;
    if (start.trim() || end.trim()) {
      const from = parseTime(start);
      const to = end.trim() === '24:00' ? 1440 : parseTime(end);
      if (from === null || to === null || from >= to) {
        setError('Enter a complete time range or clear both time fields.');
        return;
      }
      if (!markRange({ start: from, end: to })) return;
      setStart('');
      setEnd('');
    }
    saveInProgress.current = true;
    setSaving(true);
    setError('');
    try {
      await onSave(latest.current);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Could not save your profile.');
    } finally {
      saveInProgress.current = false;
      setSaving(false);
    }
  }

  return (
    <Flow step={step}>
      {step === 'about' ? <Section>
        <Label>Step 1 of 2 · About you</Label>
        <Heading large>Tell us about yourself</Heading>
        {conference.sample ? (
          <Action title="Use sample profile" onPress={() => { update({ ...sampleAttendee, unavailable: profile.unavailable }); setError(''); }} secondary />
        ) : null}
        <Copy>Use sample information for this demo. Your interests help tailor your recommendations.</Copy>
        <Copy>Start with your résumé or LinkedIn PDF (Profile → More → Save to PDF) and we’ll fill in what we can. It is sent once when you save; the server keeps only its extracted text, never the file.</Copy>
        {previousResume && !profile.resume ? (
          <Message>
            {previousResume.onServer
              ? `Your résumé ${previousResume.name} is already on file from your last save. Re-attach it only if it changed.`
              : `Files don’t survive between visits, so ${previousResume.name} needs to be re-attached before you save.`}
          </Message>
        ) : null}
        <View style={styles.row}>
          <Action title={previousResume && !profile.resume ? 'Re-attach résumé PDF' : 'Choose résumé PDF'} onPress={pickResume} secondary />
          {profile.resume ? <Action title="Remove résumé" onPress={removeResume} secondary /> : null}
        </View>
        {profile.resume ? (
          <View style={styles.stack}>
            <Copy>Selected file: {profile.resume.name}</Copy>
            {reading ? <Message>Reading your résumé… you can keep filling in the form.</Message> : null}
            {pickedUp.length ? <Message>We picked up {pickedUp.join(' and ')} from your résumé. Edit anything below.</Message> : null}
            {resumeNote ? <Message>{resumeNote}</Message> : null}
            <View style={styles.row}>
              <Action title="Private résumé" selected={!profile.resumePublic} onPress={() => update({ resumePublic: false })} secondary />
              <Action title="Public résumé" selected={profile.resumePublic} onPress={() => update({ resumePublic: true })} secondary />
            </View>
            <Copy>Sharing preference: {profile.resumePublic ? 'Public' : 'Private'}. The live sharing policy is pending.</Copy>
          </View>
        ) : null}
        <Field label="Name (required)" value={profile.name} onChangeText={(name) => update({ name })} maxLength={80} />
        <Field label="Email (optional, shared only with connections you accept)" value={profile.email} onChangeText={(email) => update({ email })} autoCapitalize="none" autoCorrect={false} keyboardType="email-address" maxLength={320} />
        <Field label="Bio" multiline value={profile.bio} onChangeText={(bio) => update({ bio })} maxLength={1000} />
        <Field label="Interests, separated by commas" value={profile.interests} onChangeText={(interests) => update({ interests })} placeholder="Kubernetes, Observability" maxLength={200} />
        <Field label="What do you want to see?" multiline value={profile.lookingFor} onChangeText={(lookingFor) => update({ lookingFor })} placeholder="Talks, people, or topics you’re here for" maxLength={2000} />
        <Field label="LinkedIn profile URL (optional)" value={profile.linkedin} onChangeText={(linkedin) => update({ linkedin })} autoCapitalize="none" keyboardType="url" maxLength={300} />
        <Action title={profile.discoverable ? 'Discovery on' : 'Discovery off'} selected={profile.discoverable}
          onPress={() => update({ discoverable: !profile.discoverable })} secondary />
        <Copy>Turn on discovery to appear in and receive people suggestions for this conference.</Copy>
        {error ? <Message error>{error}</Message> : null}
        <Action title="Continue to availability" onPress={continueToAvailability} />
      </Section> : <Section>
        <Label>Step 2 of 2 · Availability</Label>
        <Heading large>Make time for what matters</Heading>
        <Copy>Block out times you’re busy, or continue if you’re free all day. Times are in Mountain Time.</Copy>
        {days.length > 1 ? (
          <View style={styles.row}>
            {days.map((date) => <Action key={date} title={date} selected={date === day} disabled={saving}
              onPress={() => setDay(date)} secondary />)}
          </View>
        ) : day ? <Label>{day}</Label> : null}
        <View style={styles.row}>
          <Action title="Mark unavailable" selected={mode === 'unavailable'} disabled={saving}
            onPress={() => setMode('unavailable')} secondary />
          <Action title="Mark available" selected={mode === 'available'} disabled={saving}
            onPress={() => setMode('available')} secondary />
        </View>
        <AvailabilityTimeline start={timelineStart} end={timelineEnd} disabled={saving}
          blocked={profile.unavailable.filter((range) => range.date === day)} mode={mode} onSelect={markRange} />
        <Field label={mode === 'available' ? 'Available from' : 'Unavailable from'} value={start} onChangeText={setStart} placeholder="11:00" maxLength={5} editable={!saving} />
        <Field label={mode === 'available' ? 'Available until' : 'Unavailable until'} value={end} onChangeText={setEnd} placeholder="12:00" maxLength={5} editable={!saving} />
        <Action title={mode === 'available' ? 'Clear unavailable time' : 'Add unavailable time'} onPress={addBlock} disabled={saving} secondary />
        {profile.unavailable.map((range) => {
          const time = `${days.length > 1 && range.date ? `${range.date} · ` : ''}${formatTime(range.start)} to ${formatTime(range.end)}`;
          return (
            <View key={`${range.date}-${range.start}-${range.end}`} style={styles.row}>
              <Copy>{time}</Copy>
              <Action title={`Remove ${time}`} onPress={() => update({ unavailable: profile.unavailable.filter((item) => item !== range) })} disabled={saving} secondary />
            </View>
          );
        })}
        {error ? <Message error>{error}</Message> : null}
        <View style={styles.row}>
          <Action title={saving ? 'Saving profile…' : 'See my recommendations'} onPress={save} disabled={saving} />
          <Action title="Back to profile" onPress={() => changeStep('about')} disabled={saving} secondary />
        </View>
      </Section>}
      {onCancel ? <Action title="Cancel edit and return to plan" onPress={onCancel} disabled={saving} secondary /> : null}
    </Flow>
  );
}
