import { StatusBar } from 'expo-status-bar';
import { useEffect, useRef, useState } from 'react';
import type { ComponentRef } from 'react';
import { Platform, ScrollView, StyleSheet, Text, View } from 'react-native';
import { SafeAreaProvider, SafeAreaView } from 'react-native-safe-area-context';

import type { Attendee, Conference } from './src/conference';
import { demoConference } from './src/demoConference';
import { conferenceFromSchedule, joinLiveConference, saveLiveProfile } from './src/api';
import type { ParsedTalk } from './src/api';
import { Flow, MotionPreferences } from './src/Flow';
import { JoinScanner } from './src/JoinScanner';
import { joinPath, parseJoinCode, parseJoinPath } from './src/joinLink';
import type { JoinStep } from './src/joinLink';
import { Organizer } from './src/Organizer';
import { ProfileForm } from './src/ProfileForm';
import type { PreviousResume } from './src/ProfileForm';
import { Recommendations } from './src/Recommendations';
import { ScheduleBrowser } from './src/ScheduleBrowser';
import { attendeeSessions, fromStoredProfile, toStoredProfile } from './src/session';
import { Landing } from './src/site/Landing';
import { OrganizersPage } from './src/site/OrganizersPage';
import { PastEvents } from './src/site/PastEvents';
import { PastTalks } from './src/site/PastTalks';
import { useRoute } from './src/site/router';
import { Container, SiteShell } from './src/site/SiteShell';
import { Action, colors, Copy, Field, Heading, Label, Message, Section, styles } from './src/ui';

function JoinConference({ conferences, linkCode, onJoin }: {
  conferences: Conference[];
  linkCode?: string;
  onJoin: (conference: Conference) => void;
}) {
  const [code, setCode] = useState(linkCode ?? '');
  const [error, setError] = useState('');
  const [scanning, setScanning] = useState(false);
  const [busy, setBusy] = useState(false);
  const request = useRef<AbortController>(null);

  async function join(value: string) {
    if (request.current) return;
    // Accepts a bare conference id or a scanned/pasted /join/<id> link.
    const parsed = parseJoinCode(value);
    if (!parsed) { setError('Enter the conference code or scan its QR code.'); return; }
    setError('');
    const controller = new AbortController();
    request.current = controller;
    setBusy(true);
    try {
      const conference = conferences.find((item) => item.code === parsed) ?? await joinLiveConference(parsed, controller.signal);
      if (!controller.signal.aborted) onJoin(conference);
    } catch (reason) {
      if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : 'Could not join the conference.');
    } finally {
      if (request.current === controller) {
        request.current = null;
        setBusy(false);
      }
    }
  }

  useEffect(() => {
    if (linkCode) void join(linkCode);
    return () => {
      request.current?.abort();
      request.current = null;
    };
  }, [linkCode]);

  return (
    <Flow step={scanning ? 'scanner' : 'code'} style={scanning ? undefined : layout.entry}>
      {scanning ? <JoinScanner onClose={() => setScanning(false)} onScan={(value) => {
        setScanning(false);
        join(value);
      }} /> : (
        <>
          <View style={layout.intro}>
            <Label>For attendees</Label>
            <Text accessibilityRole="header" style={layout.coverTitle}>Check in.</Text>
            <Copy>Open your organizer’s link or enter the code to find your conference.</Copy>
          </View>
          <View style={layout.checkIn}>
            <Section>
              <Heading>Join your conference</Heading>
              <Field label="Conference code or join link" autoCapitalize="none" autoCorrect={false} value={code} editable={!busy}
                maxLength={250} onChangeText={(value) => { setCode(value); setError(''); }} onSubmitEditing={() => join(code)} />
              {error ? <Message error>{error}</Message> : null}
              <View style={styles.row}>
                <Action title={busy ? 'Opening conference…' : 'Join conference'} onPress={() => join(code)} disabled={busy} />
                {Platform.OS !== 'web' ? <Action title="Scan QR code" onPress={() => setScanning(true)} disabled={busy} secondary /> : null}
              </View>
              <Action title="Join sample conference" onPress={() => onJoin(demoConference)} disabled={busy} secondary />
            </Section>
          </View>
        </>
      )}
    </Flow>
  );
}

export default function App() {
  const [conferences, setConferences] = useState([demoConference]);
  const nextSample = useRef(1);
  const { page, path, navigate } = useRoute();
  const [conference, setConference] = useState<Conference>();
  // `profile` is the last saved profile; `draft` carries unsaved edits across remounts and
  // reloads (autosaved to this browser's storage, debounced).
  const [profile, setProfile] = useState<Attendee>();
  const [draft, setDraft] = useState<Attendee>();
  const [previousResume, setPreviousResume] = useState<PreviousResume>();
  const [requested, setRequested] = useState<string[]>([]);
  const [attendeeToken, setAttendeeToken] = useState<string>();
  const [browsingSchedule, setBrowsingSchedule] = useState(false);
  const [resumeTalk, setResumeTalk] = useState<string>();
  const scroll = useRef<ComponentRef<typeof ScrollView>>(null);
  const draftTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  // The attendee step lives in the path (/join/<code>[/availability|/plan]) so a reload
  // restores it and browser Back returns to the previous step.
  const route = page === 'join' ? parseJoinPath(path) : null;
  const linkCode = route?.code;
  const step: JoinStep = route?.step ?? 'about';
  // The URL always carries the code while inside a conference, so a bare /join (e.g. after
  // Back) is the join form even when a conference is still loaded.
  const activeConference = linkCode && conference?.code === linkCode ? conference : undefined;
  const scope = useRef<Conference | undefined>(undefined);

  function changeConference(next?: Conference) {
    if (draftTimer.current) clearTimeout(draftTimer.current);
    scope.current = next;
    setConference(next);
    setRequested([]);
    setResumeTalk(undefined);
    // Restore whatever this browser remembers for the conference.
    const stored = next ? attendeeSessions.load(next.code) : undefined;
    const saved = stored?.saved ? fromStoredProfile(stored.saved) : undefined;
    const unsaved = stored?.draft ? fromStoredProfile(stored.draft) : undefined;
    const resumeName = unsaved?.resumeName ?? saved?.resumeName;
    setAttendeeToken(stored?.attendeeToken);
    setProfile(saved?.profile);
    setDraft(unsaved?.profile ?? saved?.profile);
    setPreviousResume(resumeName ? { name: resumeName, onServer: !unsaved && !!saved?.resumeName } : undefined);
    return { code: next?.code, returning: !!saved && !unsaved };
  }

  function changeDraft(next: Attendee) {
    const code = activeConference?.code;
    if (!code) return;
    setDraft(next);
    if (next.resume) setPreviousResume(undefined);
    if (draftTimer.current) clearTimeout(draftTimer.current);
    draftTimer.current = setTimeout(() => {
      attendeeSessions.update(code, { draft: toStoredProfile(next, previousResume?.name) });
    }, 400);
  }

  // "Start over / not you?": forget this browser's session for the conference.
  function startOver() {
    if (!activeConference) return;
    if (draftTimer.current) clearTimeout(draftTimer.current);
    attendeeSessions.clear(activeConference.code);
    setAttendeeToken(undefined);
    setProfile(undefined);
    setDraft(undefined);
    setPreviousResume(undefined);
    setRequested([]);
    setResumeTalk(undefined);
    setBrowsingSchedule(false);
    navigate(joinPath(activeConference.code), { replace: true });
  }

  function publishSample(name: string, talks: ParsedTalk[]) {
    const code = `sample-${nextSample.current++}`;
    const event = conferenceFromSchedule({
      conference_id: code,
      name,
      talks: talks.map((talk, index) => ({ ...talk, talk_id: `session-${index + 1}` })),
    });
    setConferences((current) => [...current, { ...event, sample: true }]);
    return code;
  }

  // Public site pages come from the URL; /join and /join/<code> show the attendee flow.
  const screen = page !== 'join' ? page
    : !activeConference ? 'join' : browsingSchedule ? 'schedule' : step === 'plan' && profile ? 'plan' : 'profile';

  function scrollToTop() {
    scroll.current?.scrollTo({ y: 0, animated: false });
  }

  async function saveProfile(next: Attendee) {
    if (!activeConference) return;
    let token = attendeeToken;
    if (!activeConference.sample) {
      // The bearer token makes this an update of the same attendee rather than a duplicate.
      const result = await saveLiveProfile(activeConference, next, attendeeToken);
      if (scope.current !== activeConference) return;
      if (result.attendee_token) token = result.attendee_token;
    }
    if (draftTimer.current) clearTimeout(draftTimer.current);
    const resumeName = next.resume?.name ?? previousResume?.name;
    attendeeSessions.update(activeConference.code, {
      attendeeToken: token, saved: toStoredProfile(next, previousResume?.name), draft: undefined,
    });
    setAttendeeToken(token);
    setProfile(next);
    setDraft(next);
    setPreviousResume(resumeName ? { name: resumeName, onServer: true } : undefined);
    if (resumeTalk) setBrowsingSchedule(true);
    else navigate(joinPath(activeConference.code, 'plan'));
  }

  function editProfile(talkId?: string) {
    setResumeTalk(talkId);
    setBrowsingSchedule(false);
    if (activeConference && step !== 'about') navigate(joinPath(activeConference.code));
  }

  useEffect(scrollToTop, [screen, step]);

  return (
    <SafeAreaProvider>
      <SafeAreaView style={layout.screen}>
        <StatusBar style="dark" />
        <MotionPreferences>
          <SiteShell page={page} navigate={navigate} scrollRef={scroll}>
            <Flow step={screen} fadeOnly>
              {page === 'home' ? <Landing navigate={navigate} /> : page === 'events' ? <PastEvents /> : page === 'talks' ? (
                <PastTalks onBrowseSchedule={() => { setBrowsingSchedule(true); navigate('/join'); }} />
              )
              : page === 'organizers' ? (
                <OrganizersPage>
                  <Organizer onPublishSample={publishSample} onTrySample={(code) => {
                    setBrowsingSchedule(false);
                    navigate(`/join/${encodeURIComponent(code)}`);
                  }} />
                </OrganizersPage>
              )
              : !activeConference ? (
                <Container style={layout.content}>
                  <JoinConference key={linkCode ?? 'manual'} conferences={conferences} linkCode={linkCode} onJoin={(next) => {
                    const { returning } = changeConference(next);
                    // A returning attendee who already saved lands on their plan, not the form.
                    if (returning && step === 'about') navigate(joinPath(next.code, 'plan'), { replace: linkCode === next.code });
                    else if (linkCode !== next.code) navigate(joinPath(next.code));
                  }} />
                </Container>
              ) : (
                <Container style={layout.content}>
                <View key={activeConference.code} style={styles.stack}>
                  <View style={styles.row}>
                    <Label>{activeConference.name}</Label>
                    <Action title="Switch conference" onPress={() => { changeConference(); navigate('/join'); }} secondary />
                    <Action title={browsingSchedule ? 'Back to check-in' : 'Browse event schedule'}
                      onPress={() => { setResumeTalk(undefined); setBrowsingSchedule((current) => !current); }} secondary />
                    {profile || draft || attendeeToken ? <Action title="Start over / not you?" onPress={startOver} secondary /> : null}
                  </View>
                  {browsingSchedule ? (
                    <ScheduleBrowser conference={activeConference} attendeeToken={attendeeToken} initialTalkId={resumeTalk}
                      onProfile={editProfile} />
                  ) : screen === 'profile' ? (
                    <ProfileForm initial={draft ?? profile} previousResume={previousResume} sample={activeConference.sample}
                      step={step === 'availability' ? 'availability' : 'about'}
                      onChange={changeDraft} onSave={saveProfile}
                      onStepChange={(next) => navigate(joinPath(activeConference.code, next))} />
                  ) : profile ? (
                    <Recommendations conference={activeConference} profile={profile} attendeeToken={attendeeToken} requested={requested}
                      onEdit={editProfile}
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
