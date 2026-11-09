import { StatusBar } from 'expo-status-bar';
import { useEffect, useRef, useState } from 'react';
import type { ComponentRef } from 'react';
import { Platform, ScrollView, StyleSheet, Text, View } from 'react-native';
import { SafeAreaProvider, SafeAreaView } from 'react-native-safe-area-context';

import type { Attendee, Conference } from './src/conference';
import { demoConference } from './src/demoConference';
import { Flow, MotionPreferences } from './src/Flow';
import { JoinScanner } from './src/JoinScanner';
import { clearJoinPath, joinCodeFromLocation, parseJoinCode } from './src/joinLink';
import { Organizer } from './src/Organizer';
import { ProfileForm } from './src/ProfileForm';
import { Recommendations } from './src/Recommendations';
import { Landing } from './src/site/Landing';
import { OrganizersPage } from './src/site/OrganizersPage';
import { PastEvents } from './src/site/PastEvents';
import { PastTalks } from './src/site/PastTalks';
import { useRoute } from './src/site/router';
import { Container, SiteShell } from './src/site/SiteShell';
import { Action, colors, Copy, Field, Heading, Label, Message, Section, styles } from './src/ui';

function JoinConference({ conferences, onJoin }: {
  conferences: Conference[];
  onJoin: (conference: Conference) => void;
}) {
  const [linkCode] = useState(joinCodeFromLocation);
  const [code, setCode] = useState(linkCode ?? '');
  const [error, setError] = useState('');
  const [scanning, setScanning] = useState(false);

  function join(value: string) {
    // Accepts a bare code or a scanned/pasted /join/<code> link.
    const parsed = parseJoinCode(value);
    const conference = parsed ? conferences.find((item) => item.code === parsed) : undefined;
    if (conference) { clearJoinPath(); onJoin(conference); }
    else setError('This code doesn’t match a conference in this session. Check the code or try the sample conference.');
  }

  // Web: opened via a /join/<code> link (e.g. from the organizer QR), so join right away.
  useEffect(() => { if (linkCode) join(linkCode); }, []);

  return (
    <Flow step={scanning ? 'scanner' : 'code'} style={scanning ? undefined : layout.entry}>
      {scanning ? <JoinScanner onClose={() => setScanning(false)} onScan={(value) => {
        setScanning(false);
        join(value);
      }} /> : (
        <>
          <View style={layout.intro}>
            <Label>Attendee check-in</Label>
            <Text accessibilityRole="header" style={layout.coverTitle}>Find your people.</Text>
            <Copy>Make time for the talks you care about and the people you want to meet.</Copy>
          </View>
          <View style={layout.checkIn}>
            <Section>
              <Heading>Join your conference</Heading>
              <Field label="Conference code" autoCapitalize="none" autoCorrect={false} value={code}
                maxLength={100} onChangeText={(value) => { setCode(value); setError(''); }} onSubmitEditing={() => join(code)} />
              {error ? <Message error>{error}</Message> : null}
              <View style={styles.row}>
                <Action title="Join conference" onPress={() => join(code)} />
                {Platform.OS !== 'web' ? <Action title="Scan QR code" onPress={() => setScanning(true)} secondary /> : null}
              </View>
              <Action title="Join sample conference" onPress={() => onJoin(demoConference)} secondary />
            </Section>
          </View>
        </>
      )}
    </Flow>
  );
}

export default function App() {
  const [conferences, setConferences] = useState([demoConference]);
  const { page, navigate } = useRoute();
  const [conference, setConference] = useState<Conference>();
  const [profile, setProfile] = useState<Attendee>();
  const [editing, setEditing] = useState(false);
  const [requested, setRequested] = useState<string[]>([]);
  const scroll = useRef<ComponentRef<typeof ScrollView>>(null);

  function publish(name: string, talks: Conference['talks']) {
    const code = `event-${conferences.length}`;
    const event = { name, talks, code };
    setConferences((items) => [...items, event]);
    scrollToTop();
    return event;
  }

  function changeConference(next?: Conference) {
    setConference(next);
    setProfile(undefined);
    setEditing(false);
    setRequested([]);
  }

  // Public site pages come from the URL; /join and /join/<code> show the attendee flow.
  const screen = page !== 'join' ? page
    : !conference ? 'join' : !profile || editing ? 'profile' : 'plan';

  function scrollToTop() {
    scroll.current?.scrollTo({ y: 0, animated: false });
  }

  useEffect(scrollToTop, [screen]);

  return (
    <SafeAreaProvider>
      <SafeAreaView style={layout.screen}>
        <StatusBar style="light" />
        <MotionPreferences>
          <SiteShell page={page} navigate={navigate} scrollRef={scroll}>
            <Flow step={screen}>
              {page === 'home' ? <Landing navigate={navigate} /> : page === 'events' ? <PastEvents /> : page === 'talks' ? <PastTalks />
              : page === 'organizers' ? <OrganizersPage><Organizer onPublish={publish} /></OrganizersPage>
              : !conference ? (
                <Container style={layout.content}>
                  <JoinConference conferences={conferences} onJoin={changeConference} />
                </Container>
              ) : (
                <Container style={layout.content}>
                <View style={styles.stack}>
                  <View style={styles.row}>
                    <Label>{conference.name}</Label>
                    <Action title="Switch conference" onPress={() => changeConference()} secondary />
                  </View>
                  {!profile || editing ? (
                    <ProfileForm initial={profile} onStepChange={scrollToTop} onSave={(next) => { setProfile(next); setEditing(false); }} />
                  ) : (
                    <Recommendations conference={conference} profile={profile} requested={requested}
                      onEdit={() => setEditing(true)}
                      onRequest={(id) => setRequested((current) => current.includes(id) ? current : [...current, id])} />
                  )}
                </View>
                </Container>
              )}
            </Flow>
          </SiteShell>
        </MotionPreferences>
      </SafeAreaView>
    </SafeAreaProvider>
  );
}

const layout = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.paper },
  content: { maxWidth: 920, paddingVertical: 48, gap: 34 },
  entry: { flexDirection: 'row', flexWrap: 'wrap', alignItems: 'flex-end', columnGap: 64, rowGap: 32 },
  intro: { flexBasis: 360, flexGrow: 1, flexShrink: 1, maxWidth: 440, gap: 12 },
  coverTitle: { color: colors.ink, fontSize: 58, fontWeight: '700', letterSpacing: -3.5 },
  checkIn: { flexBasis: 270, flexGrow: 1, flexShrink: 1, maxWidth: 380 },
});
