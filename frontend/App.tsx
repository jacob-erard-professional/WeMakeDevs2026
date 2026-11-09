import { StatusBar } from 'expo-status-bar';
import { useState } from 'react';
import { ScrollView, StyleSheet, Text, View } from 'react-native';
import { SafeAreaProvider, SafeAreaView } from 'react-native-safe-area-context';

import type { Attendee, Conference } from './src/conference';
import { demoConference } from './src/demoConference';
import { Organizer } from './src/Organizer';
import { ProfileForm } from './src/ProfileForm';
import { Recommendations } from './src/Recommendations';
import { Action, Card, colors, Copy, Field, Heading, Label, Message, styles } from './src/ui';

function JoinConference({ conferences, onJoin }: {
  conferences: Conference[];
  onJoin: (conference: Conference) => void;
}) {
  const [code, setCode] = useState('');
  const [error, setError] = useState('');

  function join() {
    const conference = conferences.find((item) => item.code === code.trim().toLowerCase());
    if (conference) onJoin(conference);
    else setError('Enter a valid conference code or join the sample conference below.');
  }

  return (
    <Card>
      <Label>FOR ATTENDEES</Label>
      <Heading>Join your conference</Heading>
      <Copy>Enter a code from your organizer or try the sample conference.</Copy>
      <Field label="Conference code" autoCapitalize="none" autoCorrect={false} value={code}
        maxLength={100} onChangeText={(value) => { setCode(value); setError(''); }} onSubmitEditing={join} />
      {error ? <Message error>{error}</Message> : null}
      <View style={styles.row}>
        <Action title="Join conference" onPress={join} />
        <Action title="Join sample conference" onPress={() => onJoin(demoConference)} secondary />
      </View>
    </Card>
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
          <View style={layout.hero}>
            <Text style={layout.eyebrow}>DEMO MODE · LOCAL SESSION</Text>
            <Text accessibilityRole="header" style={layout.title}>Conference Connections</Text>
            <Text style={layout.subtitle}>Find talks worth your time and people worth meeting.</Text>
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
  content: { width: '100%', maxWidth: 840, alignSelf: 'center', padding: 18, paddingBottom: 40, gap: 18 },
  hero: { borderRadius: 22, backgroundColor: colors.ink, paddingHorizontal: 24, paddingVertical: 30, gap: 9 },
  eyebrow: { color: '#B5DFC9', fontWeight: '700', fontSize: 13, letterSpacing: 1 },
  title: { color: colors.white, fontSize: 36, fontWeight: '800' },
  subtitle: { color: '#DCEFE4', fontSize: 17, lineHeight: 25 },
});
