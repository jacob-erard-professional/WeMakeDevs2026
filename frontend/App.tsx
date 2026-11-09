import { StatusBar } from 'expo-status-bar';
import { useEffect, useRef, useState } from 'react';
import type { ComponentRef } from 'react';
import { Platform, ScrollView, StyleSheet, Text, View } from 'react-native';
import { SafeAreaProvider, SafeAreaView } from 'react-native-safe-area-context';

import type { Attendee, Conference } from './src/conference';
import { demoConference } from './src/demoConference';
import { joinLiveConference, saveLiveProfile } from './src/api';
import { Flow, MotionPreferences } from './src/Flow';
import { JoinScanner } from './src/JoinScanner';
import { joinPath, parseJoinCode, parseJoinPath } from './src/joinLink';
import type { JoinStep } from './src/joinLink';
import { Organizer } from './src/Organizer';
import { ProfileForm } from './src/ProfileForm';
import type { PreviousResume } from './src/ProfileForm';
import { Recommendations } from './src/Recommendations';
import { attendeeSessions, fromStoredProfile, toStoredProfile } from './src/session';
import { Landing } from './src/site/Landing';
import { OrganizersPage } from './src/site/OrganizersPage';
import { PastEvents } from './src/site/PastEvents';
import { PastTalks } from './src/site/PastTalks';
import { paths, useRoute } from './src/site/router';
import { Container, SiteShell } from './src/site/SiteShell';
import { Action, colors, Copy, Field, Heading, Label, Message, Section, styles } from './src/ui';

function JoinConference({ initialCode, error, busy, onJoin, onInvalid }: {
  initialCode: string;
  error: string;
  busy: boolean;
  onJoin: (code: string) => void;
  onInvalid: (message: string) => void;
}) {
  const [code, setCode] = useState(initialCode);
  const [scanning, setScanning] = useState(false);

  function join(value: string) {
    // Accepts a bare conference id or a scanned/pasted /join/<id> link.
    const parsed = parseJoinCode(value);
    if (!parsed) { onInvalid('Enter the conference code or scan its QR code.'); return; }
    onJoin(parsed);
  }

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
                maxLength={100} onChangeText={(value) => { setCode(value); onInvalid(''); }} onSubmitEditing={() => join(code)} />
              {error ? <Message error>{error}</Message> : null}
              <View style={styles.row}>
                <Action title={busy ? 'Joining…' : 'Join conference'} onPress={() => join(code)} disabled={busy} />
                {Platform.OS !== 'web' ? <Action title="Scan QR code" onPress={() => setScanning(true)} secondary /> : null}
              </View>
              <Action title="Join sample conference" onPress={() => onJoin(demoConference.code)} secondary disabled={busy} />
            </Section>
          </View>
        </>
      )}
    </Flow>
  );
}

export default function App() {
  const conferences = [demoConference];
  const { path, page, navigate } = useRoute();
  // The attendee flow lives in the URL: /join/<code>[/availability|/plan]. A refresh or Back
  // re-derives the step from the path instead of losing it with React state.
  const route = page === 'join' ? parseJoinPath(path) : null;
  const [conference, setConference] = useState<Conference>();
  const [joinError, setJoinError] = useState('');
  const [failedCode, setFailedCode] = useState('');
  // `profile` is the last saved profile; `draft` carries unsaved edits across remounts.
  const [profile, setProfile] = useState<Attendee>();
  const [draft, setDraft] = useState<Attendee>();
  const [previousResume, setPreviousResume] = useState<PreviousResume>();
  const [requested, setRequested] = useState<string[]>([]);
  const [attendeeToken, setAttendeeToken] = useState<string>();
  const scroll = useRef<ComponentRef<typeof ScrollView>>(null);
  const draftTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);

  const joined = !!route && conference?.code === route.code;
  const joining = !!route && !joined;

  // Join whatever conference the path names: a QR link, the landing form, a refresh, or Back.
  // On failure the path drops back to /join so the form shows the error without retrying.
  useEffect(() => {
    const code = route?.code;
    if (!code || joined) return;
    let active = true;
    (async () => {
      try {
        const next = conferences.find((item) => item.code === code) ?? await joinLiveConference(code);
        if (active) enterConference(next, route.step);
      } catch (reason) {
        if (!active) return;
        setJoinError(reason instanceof Error ? reason.message : 'Could not join the conference.');
        setFailedCode(code);
        navigate(paths.join, { replace: true });
      }
    })();
    return () => { active = false; };
  }, [route?.code, joined]);

  function enterConference(next: Conference, step: JoinStep) {
    const stored = attendeeSessions.load(next.code);
    const saved = stored?.saved ? fromStoredProfile(stored.saved) : undefined;
    const unsaved = stored?.draft ? fromStoredProfile(stored.draft) : undefined;
    const resumeName = unsaved?.resumeName ?? saved?.resumeName;
    setConference(next);
    setRequested([]);
    setAttendeeToken(stored?.attendeeToken);
    setProfile(saved?.profile);
    setDraft(unsaved?.profile ?? saved?.profile);
    setPreviousResume(resumeName ? { name: resumeName, onServer: !unsaved && !!saved?.resumeName } : undefined);
    // A returning attendee who already saved lands on their plan, not the empty form.
    if (saved && !unsaved && step === 'about') navigate(joinPath(next.code, 'plan'), { replace: true });
  }

  const screen = page !== 'join' ? page : !joined ? 'join' : route.step === 'plan' && profile ? 'plan' : 'profile';

  function scrollToTop() {
    scroll.current?.scrollTo({ y: 0, animated: false });
  }

  function changeDraft(next: Attendee) {
    if (!conference) return;
    const code = conference.code;
    setDraft(next);
    if (next.resume) setPreviousResume(undefined);
    if (draftTimer.current) clearTimeout(draftTimer.current);
    draftTimer.current = setTimeout(() => {
      attendeeSessions.update(code, { draft: toStoredProfile(next, previousResume?.name) });
    }, 400);
  }

  async function saveProfile(next: Attendee) {
    if (!conference) return;
    let token = attendeeToken;
    if (conference.code !== demoConference.code) {
      // The bearer token makes this an update of the same attendee rather than a duplicate.
      const result = await saveLiveProfile(conference, next, attendeeToken);
      if (result.attendee_token) token = result.attendee_token;
    }
    if (draftTimer.current) clearTimeout(draftTimer.current);
    const resumeName = next.resume?.name ?? previousResume?.name;
    attendeeSessions.update(conference.code, {
      attendeeToken: token, saved: toStoredProfile(next, previousResume?.name), draft: undefined,
    });
    setAttendeeToken(token);
    setProfile(next);
    setDraft(next);
    setPreviousResume(resumeName ? { name: resumeName, onServer: true } : undefined);
    navigate(joinPath(conference.code, 'plan'));
  }

  // "Start over / not you?": forget this browser's session for the conference.
  function startOver() {
    if (!conference) return;
    if (draftTimer.current) clearTimeout(draftTimer.current);
    attendeeSessions.clear(conference.code);
    setAttendeeToken(undefined);
    setProfile(undefined);
    setDraft(undefined);
    setPreviousResume(undefined);
    setRequested([]);
    navigate(joinPath(conference.code), { replace: true });
  }

  useEffect(scrollToTop, [screen, route?.step]);

  return (
    <SafeAreaProvider>
      <SafeAreaView style={layout.screen}>
        <StatusBar style="light" />
        <MotionPreferences>
          <SiteShell page={page} navigate={navigate} scrollRef={scroll}>
            <Flow step={screen}>
              {page === 'home' ? <Landing navigate={navigate} /> : page === 'events' ? <PastEvents /> : page === 'talks' ? <PastTalks />
              : page === 'organizers' ? <OrganizersPage><Organizer /></OrganizersPage>
              : !joined || !conference ? (
                <Container style={layout.content}>
                  <JoinConference key={route?.code ?? ''} initialCode={route?.code ?? failedCode} error={joinError} busy={joining}
                    onInvalid={setJoinError}
                    onJoin={(code) => { setJoinError(''); navigate(joinPath(code)); }} />
                </Container>
              ) : (
                <Container style={layout.content}>
                <View style={styles.stack}>
                  <View style={styles.row}>
                    <Label>{conference.name}</Label>
                    <Action title="Switch conference" onPress={() => navigate(paths.join)} secondary />
                    {profile || draft || attendeeToken ? <Action title="Start over / not you?" onPress={startOver} secondary /> : null}
                  </View>
                  {screen === 'profile' ? (
                    <ProfileForm key={conference.code} initial={draft ?? profile} previousResume={previousResume}
                      step={route.step === 'availability' ? 'availability' : 'about'}
                      onChange={changeDraft} onSave={saveProfile}
                      onStepChange={(step) => navigate(joinPath(conference.code, step))} />
                  ) : profile ? (
                    <Recommendations conference={conference} profile={profile} requested={requested}
                      onEdit={() => navigate(joinPath(conference.code))}
                      onRequest={(id) => setRequested((current) => current.includes(id) ? current : [...current, id])} />
                  ) : null}
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
