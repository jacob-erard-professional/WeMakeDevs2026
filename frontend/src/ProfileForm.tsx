import { getDocumentAsync } from 'expo-document-picker';
import { useState } from 'react';
import { View } from 'react-native';

import { formatTime, parseTime } from './conference';
import type { Attendee } from './conference';
import { Action, Copy, Field, Heading, Message, Section, styles } from './ui';

const blank: Attendee = {
  name: '', bio: '', interests: '', linkedin: '', resumeName: '',
  resumePublic: false, discoverable: false, unavailable: [],
};

export function ProfileForm({ initial, onSave }: { initial?: Attendee; onSave: (profile: Attendee) => void }) {
  const [profile, setProfile] = useState(initial ?? blank);
  const [start, setStart] = useState('');
  const [end, setEnd] = useState('');
  const [error, setError] = useState('');

  function update(changes: Partial<Attendee>) {
    setProfile((current) => ({ ...current, ...changes }));
  }

  async function pickResume() {
    setError('');
    try {
      const result = await getDocumentAsync({
        type: 'application/pdf', copyToCacheDirectory: false, base64: false,
      });
      if (!result.canceled) update({ resumeName: result.assets[0].name });
    } catch {
      setError('Could not open the file picker. Try again or continue with a bio.');
    }
  }

  function addBlock() {
    const from = parseTime(start);
    const to = parseTime(end);
    if (from === null || to === null || from >= to) {
      setError('Enter a start and a later end in 24-hour HH:MM format.');
      return;
    }
    if (!profile.unavailable.some((range) => range.start === from && range.end === to)) {
      update({ unavailable: [...profile.unavailable, { start: from, end: to }] });
    }
    setStart('');
    setEnd('');
    setError('');
  }

  function save() {
    if (!profile.name.trim() || (!profile.bio.trim() && !profile.resumeName)) {
      setError('Enter your name and add a bio or choose a résumé.');
      return;
    }
    const linkedin = profile.linkedin.trim();
    if (linkedin && !/^https:\/\/(?:[a-z0-9-]+\.)?linkedin\.com\/in\/[a-z0-9_%.-]+\/?$/i.test(linkedin)) {
      setError('Enter a LinkedIn profile URL such as https://www.linkedin.com/in/sample or leave it blank.');
      return;
    }
    if (start.trim() || end.trim()) {
      setError('Add the pending time block or clear both time fields before continuing.');
      return;
    }
    onSave({ ...profile, name: profile.name.trim(), linkedin });
  }

  return (
    <View style={styles.stack}>
      <Heading>Tell us about yourself</Heading>
      <Copy>Use sample information for this demo. Your interests help tailor your recommendations.</Copy>
      <Section>
        <Field label="Name (required)" value={profile.name} onChangeText={(name) => update({ name })} maxLength={80} />
        <Field label="Bio" multiline value={profile.bio} onChangeText={(bio) => update({ bio })} maxLength={1000} />
        <Field label="Interests, separated by commas" value={profile.interests} onChangeText={(interests) => update({ interests })} placeholder="Kubernetes, Observability" maxLength={200} />
        <Field label="LinkedIn profile URL (optional)" value={profile.linkedin} onChangeText={(linkedin) => update({ linkedin })} autoCapitalize="none" keyboardType="url" maxLength={300} />
        <Copy>The demo remembers the résumé filename for this session. It never uploads or reads the document.</Copy>
        <View style={styles.row}>
          <Action title="Choose résumé PDF" onPress={pickResume} secondary />
          {profile.resumeName ? <Action title="Remove résumé" onPress={() => update({ resumeName: '', resumePublic: false })} secondary /> : null}
        </View>
        {profile.resumeName ? (
          <View style={styles.stack}>
            <Copy>Selected file: {profile.resumeName}</Copy>
            <View style={styles.row}>
              <Action title="Private résumé" selected={!profile.resumePublic} onPress={() => update({ resumePublic: false })} secondary />
              <Action title="Public résumé" selected={profile.resumePublic} onPress={() => update({ resumePublic: true })} secondary />
            </View>
            <Copy>Sharing preference: {profile.resumePublic ? 'Public' : 'Private'}. The live sharing policy is pending.</Copy>
          </View>
        ) : null}
        <Action title={profile.discoverable ? 'Discovery on' : 'Discovery off'} selected={profile.discoverable}
          onPress={() => update({ discoverable: !profile.discoverable })} secondary />
        <Copy>Discovery controls whether your profile may appear in other attendees’ suggestions. You can browse suggestions either way.</Copy>
      </Section>
      <Section>
        <Heading>When are you unavailable?</Heading>
        <Copy>Add same-day blocks in Mountain Time using 24-hour HH:MM.</Copy>
        <Field label="Unavailable from" value={start} onChangeText={setStart} placeholder="11:00" maxLength={5} />
        <Field label="Unavailable until" value={end} onChangeText={setEnd} placeholder="12:00" maxLength={5} />
        <Action title="Add unavailable time" onPress={addBlock} secondary />
        {profile.unavailable.map((range) => {
          const time = `${formatTime(range.start)} to ${formatTime(range.end)}`;
          return (
            <View key={`${range.start}-${range.end}`} style={styles.row}>
              <Copy>{time}</Copy>
              <Action title={`Remove ${time}`} onPress={() => update({ unavailable: profile.unavailable.filter((item) => item !== range) })} secondary />
            </View>
          );
        })}
      </Section>
      {error ? <Message error>{error}</Message> : null}
      <Action title="See my recommendations" onPress={save} />
    </View>
  );
}
