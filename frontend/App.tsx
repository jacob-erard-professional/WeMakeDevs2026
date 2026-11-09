import { StatusBar } from 'expo-status-bar';
import { useState } from 'react';
import { Platform, ScrollView, StyleSheet, Text, View } from 'react-native';
import { SafeAreaProvider, SafeAreaView } from 'react-native-safe-area-context';

import type { Attendee, Conference } from './src/conference';
import { demoConference } from './src/demoConference';
import { JoinScanner } from './src/JoinScanner';
import { Organizer } from './src/Organizer';
import { ProfileForm } from './src/ProfileForm';
import { Recommendations } from './src/Recommendations';
import { Action, colors, Copy, Field, Heading, Label, Message, Section, styles } from './src/ui';

function JoinConference({ conferences, onJoin }: {
  conferences: Conference[];
  onJoin: (conference: Conference) => void;
}) {
  const [code, setCode] = useState('');
  const [error, setError] = useState('');
  const [scanning, setScanning] = useState(false);

  function join(value: string) {
    const conference = conferences.find((item) => item.code === value.trim().toLowerCase());
    if (conference) onJoin(conference);
    else setError('This code doesn’t match a conference in this session. Check the code or try the sample conference.');
  }

  if (scanning) {
    return <JoinScanner onClose={() => setScanning(false)} onScan={(value) => {
      setScanning(false);
      join(value);
    }} />;
  }

  return (
    <Section>
      <Label>ATTENDEE CHECK-IN</Label>
      <Heading>Join your conference</Heading>
      <Copy>Get your schedule and find people to meet.</Copy>
      <Field label="Conference code" autoCapitalize="none" autoCorrect={false} value={code}
        maxLength={100} onChangeText={(value) => { setCode(value); setError(''); }} onSubmitEditing={() => join(code)} />
      {error ? <Message error>{error}</Message> : null}
      <View style={styles.row}>
        <Action title="Join conference" onPress={() => join(code)} />
        {Platform.OS !== 'web' ? <Action title="Scan QR code" onPress={() => setScanning(true)} secondary /> : null}
      </View>
      <View style={layout.sample}>
        <Copy>Just looking around?</Copy>
        <Action title="Join sample conference" onPress={() => onJoin(demoConference)} secondary />
      </View>
    </Section>
  );
}

export default function App() {
  const [conferences, setConferences] = useState([demoConference]);
  const [mode, setMode] = useState<'attendee' | 'organizer'>('attendee');
  const [conference, setConference] = useState<Conference>();
  const [profile, setProfile] = useState<Attendee>();
  const [editing, setEditing] = useState(false);
  const [requested, setRequested] = useState<string[]>([]);

  function publish(name: string, talks: Conference['talks']) {
    const code = `event-${conferences.length}`;
    const event = { name, talks, code };
    setConferences((items) => [...items, event]);
    return event;
  }

  function changeConference(next?: Conference) {
    setConference(next);
    setProfile(undefined);
    setEditing(false);
    setRequested([]);
  }

  const screen = mode === 'organizer' ? 'organizer'
    : !conference ? 'join' : !profile || editing ? 'profile' : 'plan';

  return (
    <SafeAreaProvider>
      <SafeAreaView style={layout.screen}>
        <StatusBar style="dark" />
        <ScrollView key={screen} keyboardShouldPersistTaps="handled" contentContainerStyle={layout.content}>
          <View style={layout.masthead}>
            <View style={layout.issue}>
              <Label>FIELD GUIDE</Label>
              <Label>DEMO SESSION</Label>
            </View>
            <Text accessibilityRole="header" style={[layout.title, screen === 'join' && layout.coverTitle]}>
              Conference Connections
            </Text>
            {screen === 'join' ? <Copy>A plan for your day. A reason to say hello.</Copy> : null}
          </View>
          <View style={styles.row}>
            <Action title="Attendee" selected={mode === 'attendee'} onPress={() => setMode('attendee')} secondary />
            <Action title="Organizer" selected={mode === 'organizer'} onPress={() => setMode('organizer')} secondary />
          </View>
          {mode === 'organizer' ? <Organizer onPublish={publish} /> : !conference ? (
            <JoinConference conferences={conferences} onJoin={changeConference} />
          ) : (
            <View style={styles.stack}>
              <View style={styles.row}>
                <Label>{conference.name}</Label>
                <Action title="Switch conference" onPress={() => changeConference()} secondary />
              </View>
              {!profile || editing ? (
                <ProfileForm initial={profile} onSave={(next) => { setProfile(next); setEditing(false); }} />
              ) : (
                <Recommendations conference={conference} profile={profile} requested={requested}
                  onEdit={() => setEditing(true)}
                  onRequest={(id) => setRequested((current) => current.includes(id) ? current : [...current, id])} />
              )}
            </View>
          )}
        </ScrollView>
      </SafeAreaView>
    </SafeAreaProvider>
  );
}

const layout = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.paper },
  content: { width: '100%', maxWidth: 820, alignSelf: 'center', padding: 22, paddingBottom: 48, gap: 24 },
  masthead: { gap: 10, paddingTop: 12, borderTopWidth: 5, borderTopColor: colors.accent },
  issue: { flexDirection: 'row', flexWrap: 'wrap', justifyContent: 'space-between', gap: 6 },
  title: { color: colors.ink, fontFamily: Platform.OS === 'ios' ? 'Georgia' : 'serif', fontSize: 28, fontWeight: '700' },
  coverTitle: { fontSize: 44, maxWidth: 550 },
  sample: { flexDirection: 'row', flexWrap: 'wrap', alignItems: 'center', gap: 12, marginTop: 14 },
});
