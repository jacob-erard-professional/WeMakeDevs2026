import { StatusBar } from 'expo-status-bar';
import { useEffect, useRef, useState } from 'react';
import type { ComponentRef } from 'react';
import { Platform, ScrollView, StyleSheet, Text, View } from 'react-native';
import { SafeAreaProvider, SafeAreaView } from 'react-native-safe-area-context';

import type { Attendee, Conference } from './src/conference';
import { demoConference } from './src/demoConference';
import { conferenceFromSchedule, joinLiveConference, saveLiveProfile } from './src/api';
import type { LiveRecommendations } from './src/api';
import type { ParsedTalk } from './src/api';
import { Flow, MotionPreferences } from './src/Flow';
import { JoinScanner } from './src/JoinScanner';
import { parseJoinCode } from './src/joinLink';
import { Organizer } from './src/Organizer';
import { ProfileForm } from './src/ProfileForm';
import { Recommendations } from './src/Recommendations';
import type { RecommendationSection } from './src/Recommendations';
import { ScheduleBrowser } from './src/ScheduleBrowser';
import { Landing } from './src/site/Landing';
import { OrganizersPage } from './src/site/OrganizersPage';
import { PastEvents } from './src/site/PastEvents';
import { PastTalks } from './src/site/PastTalks';
import { useRoute } from './src/site/router';
import { Container, SiteShell } from './src/site/SiteShell';
import { Action, colors, Copy, Field, Heading, Label, Message, Section, styles } from './src/ui';

function JoinConference({ conferences, linkCode, previous, onJoin, onBack }: {
  conferences: Conference[];
  linkCode?: string;
  previous?: Conference;
  onJoin: (conference: Conference) => void;
  onBack: () => void;
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
              {previous ? <Action title={`Return to ${previous.name}`} onPress={() => onJoin(previous)} disabled={busy} secondary /> : null}
              <Action title="Join sample conference" onPress={() => onJoin(demoConference)} disabled={busy} secondary />
              <Action title="Back to home" onPress={onBack} secondary />
            </Section>
          </View>
        </>
      )}
    </Flow>
  );
}

type AttendeeSession = {
  conference: Conference;
  profile?: Attendee;
  draft?: Attendee;
  token?: string;
  recommendations?: LiveRecommendations;
  requested: string[];
  section: RecommendationSection;
};

export default function App() {
  const [conferences, setConferences] = useState([demoConference]);
  const nextSample = useRef(1);
  const { page, path, navigate } = useRoute();
  const [conference, setConference] = useState<Conference>();
  const [profile, setProfile] = useState<Attendee>();
  const [draft, setDraft] = useState<Attendee>();
  const [previous, setPrevious] = useState<Conference>();
  const [editing, setEditing] = useState(false);
  const [requested, setRequested] = useState<string[]>([]);
  const [section, setSection] = useState<RecommendationSection>('My schedule');
  const [attendeeToken, setAttendeeToken] = useState<string>();
  const [recommendations, setRecommendations] = useState<LiveRecommendations>();
  const [browsingSchedule, setBrowsingSchedule] = useState(false);
  const [resumeTalk, setResumeTalk] = useState<string>();
  const scroll = useRef<ComponentRef<typeof ScrollView>>(null);
  const linkCode = page === 'join' ? parseJoinCode(path) ?? undefined : undefined;
  const activeConference = !linkCode || conference?.code === linkCode ? conference : undefined;
  const scope = useRef<Conference | undefined>(undefined);
  const savedSessions = useRef(new Map<string, AttendeeSession>());
  const savingProfiles = useRef(new Set<string>());

  function changeConference(next?: Conference) {
    if (conference?.code === next?.code) return;
    if (conference) {
      savedSessions.current.set(conference.code, { conference, profile, draft, token: attendeeToken, recommendations, requested, section });
      setPrevious(conference);
    }
    const saved = next && savedSessions.current.get(next.code);
    scope.current = next;
    setConference(next);
    setProfile(saved?.profile);
    setDraft(saved?.draft);
    setEditing(false);
    setRequested(saved?.requested ?? []);
    setSection(saved?.section ?? 'My schedule');
    setAttendeeToken(saved?.token);
    setRecommendations(saved?.recommendations);
    setResumeTalk(undefined);
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
    : !activeConference ? 'join' : browsingSchedule ? 'schedule' : !profile || editing ? 'profile' : 'plan';

  function scrollToTop() {
    scroll.current?.scrollTo({ y: 0, animated: false });
  }

  async function saveProfile(next: Attendee) {
    if (activeConference && !activeConference.sample) {
      const { code } = activeConference;
      if (savingProfiles.current.has(code)) throw new Error('Your profile is already being saved.');
      savingProfiles.current.add(code);
      try {
        const result = await saveLiveProfile(activeConference, next, attendeeToken);
        const token = result.attendee_token ?? attendeeToken;
        if (scope.current?.code !== code) {
          const cached = savedSessions.current.get(code);
          if (cached) savedSessions.current.set(code, { ...cached, profile: next, draft: undefined, token, recommendations: result.recommendations });
          return;
        }
        setAttendeeToken(token);
        setRecommendations(result.recommendations);
      } finally {
        savingProfiles.current.delete(code);
      }
    } else {
      setRecommendations(undefined);
    }
    setProfile(next);
    setDraft(undefined);
    setEditing(false);
    if (resumeTalk) setBrowsingSchedule(true);
  }

  function editProfile(talkId?: string) {
    setResumeTalk(talkId);
    setBrowsingSchedule(false);
    setEditing(!!profile);
  }

  useEffect(scrollToTop, [screen]);

  return (
    <SafeAreaProvider>
      <SafeAreaView style={layout.screen}>
        <StatusBar style="dark" />
        <MotionPreferences>
          <SiteShell page={page} navigate={navigate} scrollRef={scroll}>
            <Flow step={screen} fadeOnly>
              {page === 'home' ? <Landing navigate={navigate} resumeConference={conference} /> : page === 'events' ? <PastEvents /> : page === 'talks' ? (
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
                  <JoinConference key={linkCode ?? 'manual'}
                    conferences={[...conferences, ...[...savedSessions.current.values()].map((item) => item.conference)]}
                    linkCode={linkCode} previous={previous} onBack={() => navigate('/')} onJoin={(next) => {
                    changeConference(next);
                    if (linkCode !== next.code) navigate(`/join/${encodeURIComponent(next.code)}`);
                  }} />
                </Container>
              ) : (
                <Container style={[layout.content, (screen === 'schedule' || (screen === 'plan' &&
                  (section === 'My schedule' || section === 'Event schedule'))) && layout.scheduleContent]}>
                <View key={activeConference.code} style={styles.stack}>
                  <View style={styles.row}>
                    <Label>{activeConference.name}</Label>
                    <Action title="Choose another conference" onPress={() => { changeConference(); setBrowsingSchedule(false); navigate('/join'); }} secondary />
                    {!profile || browsingSchedule ? (
                      <Action title={browsingSchedule ? (profile ? 'Back to my plan' : 'Back to check-in') : 'Browse event schedule'}
                        onPress={() => { setResumeTalk(undefined); setBrowsingSchedule((current) => !current); }} secondary />
                    ) : null}
                  </View>
                  {browsingSchedule ? (
                    <ScheduleBrowser conference={activeConference} attendeeToken={attendeeToken} initialTalkId={resumeTalk}
                      onProfile={editProfile} />
                  ) : !profile || editing ? (
                    <ProfileForm initial={draft ?? profile} conference={activeConference} onDraftChange={setDraft}
                      onStepChange={scrollToTop} onSave={saveProfile}
                      onCancel={profile ? () => { setDraft(undefined); setEditing(false); setResumeTalk(undefined); } : undefined} />
                  ) : (
                    <Recommendations conference={activeConference} profile={profile} attendeeToken={attendeeToken} requested={requested}
                      recommendations={recommendations} section={section} onSection={setSection}
                      onEdit={editProfile}
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
  scheduleContent: { maxWidth: 1100 },
  entry: { flexDirection: 'row', flexWrap: 'wrap', alignItems: 'flex-end', columnGap: 64, rowGap: 32 },
  intro: { flexBasis: 360, flexGrow: 1, flexShrink: 1, maxWidth: 440, gap: 12 },
  coverTitle: { color: colors.ink, fontSize: 58, fontWeight: '700', letterSpacing: -3.5 },
  checkIn: { flexBasis: 270, flexGrow: 1, flexShrink: 1, maxWidth: 380 },
});
