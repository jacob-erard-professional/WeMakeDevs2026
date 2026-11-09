import { StatusBar } from 'expo-status-bar';
import { useEffect, useRef, useState } from 'react';
import type { ComponentRef } from 'react';
import { Platform, ScrollView, StyleSheet, Text, View } from 'react-native';
import { SafeAreaProvider, SafeAreaView } from 'react-native-safe-area-context';

import type { Attendee, Conference } from './src/conference';
import { talkDay } from './src/conference';
import { demoConference } from './src/demoConference';
import { conferenceFromSchedule, joinLiveConference, normalizeRecommendations, saveLiveProfile } from './src/api';
import type { LiveRecommendations } from './src/api';
import type { ParsedTalk } from './src/api';
import { Flow, MotionPreferences } from './src/Flow';
import { JoinScanner } from './src/JoinScanner';
import { joinPath, parseJoinCode, parseJoinPath } from './src/joinLink';
import type { JoinStep } from './src/joinLink';
import { Organizer } from './src/Organizer';
import { ProfileForm } from './src/ProfileForm';
import type { PreviousResume } from './src/ProfileForm';
import { Recommendations } from './src/Recommendations';
import type { RecommendationSection } from './src/Recommendations';
import { ScheduleBrowser } from './src/ScheduleBrowser';
import { attendeeSessions, fromStoredProfile, toStoredProfile } from './src/session';
import { Landing } from './src/site/Landing';
import { MyConferences } from './src/site/MyConferences';
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

function savedSection(value?: string): RecommendationSection {
  if (value === 'Event schedule' || value === 'Talks' || value === 'Suggested People') return value;
  return 'My schedule';
}

export default function App() {
  const [conferences, setConferences] = useState([demoConference]);
  const nextSample = useRef(1);
  const { page, path, navigate } = useRoute();
  const [conference, setConference] = useState<Conference>();
  // Saved profile and draft are scoped to the conference in the current route.
  const [profile, setProfile] = useState<Attendee>();
  const [draft, setDraft] = useState<Attendee>();
  const [previousResume, setPreviousResume] = useState<PreviousResume>();
  const [requested, setRequested] = useState<string[]>([]);
  const [section, setSection] = useState<RecommendationSection>('My schedule');
  const [remembered, setRemembered] = useState(attendeeSessions.list);
  const [attendeeId, setAttendeeId] = useState<string>();
  const [attendeeToken, setAttendeeToken] = useState<string>();
  const [recommendations, setRecommendations] = useState<LiveRecommendations>();
  const [resumeTalk, setResumeTalk] = useState<string>();
  const scroll = useRef<ComponentRef<typeof ScrollView>>(null);
  const savingProfiles = useRef(new Set<string>());
  const currentPath = useRef(path);
  currentPath.current = path;
  // The attendee step lives in the path (/join/<code>[/availability|/plan]) so a reload
  // restores it and browser Back returns to the previous step.
  const route = page === 'join' ? parseJoinPath(path) : null;
  const linkCode = route?.code;
  const step: JoinStep = route?.step ?? 'about';
  // The URL always carries the code while inside a conference, so a bare /join (e.g. after
  // Back) is the join form even when a conference is still loaded.
  const activeConference = linkCode && conference?.code === linkCode ? conference : undefined;
  const scope = useRef<Conference | undefined>(undefined);

  function changeConference(next: Conference) {
    scope.current = next;
    setConference(next);
    setRequested([]);
    setResumeTalk(undefined);
    const stored = attendeeSessions.load(next.code);
    const firstDay = next.talks.flatMap((talk) => talkDay(talk.startsAt) ?? []).sort()[0];
    function restore(storedProfile: Parameters<typeof fromStoredProfile>[0]) {
      const result = fromStoredProfile(storedProfile);
      // Older availability drafts did not capture the day. Assign them to the first event day.
      if (firstDay) {
        result.profile.unavailable = result.profile.unavailable.map((range) => ({ ...range, date: range.date ?? firstDay }));
      }
      return result;
    }
    const saved = stored?.saved ? restore(stored.saved) : undefined;
    const unsaved = stored?.draft ? restore(stored.draft) : undefined;
    const resumeName = unsaved?.resumeName ?? saved?.resumeName;
    setAttendeeId(stored?.attendeeId);
    setAttendeeToken(stored?.attendeeToken);
    setRecommendations(saved && stored?.recommendations ? normalizeRecommendations(stored.recommendations) : undefined);
    setProfile(saved?.profile);
    setDraft(unsaved?.profile ?? saved?.profile);
    setPreviousResume(resumeName ? { name: resumeName, onServer: resumeName === saved?.resumeName && !next.sample } : undefined);
    setSection(savedSection(stored?.section));
    attendeeSessions.update(next.code, { conferenceName: next.name, sample: !!next.sample, lastOpenedAt: Date.now() });
    setRemembered(attendeeSessions.list());
    return { returning: !!saved && !unsaved };
  }

  function changeDraft(next: Attendee) {
    const code = activeConference?.code;
    if (!code || scope.current?.code !== code) return;
    setDraft(next);
    if (next.resume) setPreviousResume(undefined);
    attendeeSessions.update(code, {
      draft: toStoredProfile(next, previousResume?.name),
      draftStep: step === 'availability' ? 'availability' : 'about',
    });
  }

  function forgetConference(code: string) {
    if (savingProfiles.current.has(code)) return false;
    attendeeSessions.clear(code);
    if (conference?.code === code) {
      scope.current = undefined;
      setConference(undefined);
      setAttendeeId(undefined);
    }
    setRemembered(attendeeSessions.list());
    return true;
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
    : !activeConference ? 'join' : step === 'schedule' ? 'schedule' : step === 'plan' && profile ? 'plan' : 'profile';

  function scrollToTop() {
    scroll.current?.scrollTo({ y: 0, animated: false });
  }

  async function saveProfile(next: Attendee) {
    if (!activeConference) return;
    const { code } = activeConference;
    if (savingProfiles.current.has(code)) throw new Error('Your profile is already being saved.');
    savingProfiles.current.add(code);
    let token = attendeeToken;
    let id = attendeeId;
    let live: LiveRecommendations | undefined;
    try {
      if (!activeConference.sample) {
        const result = await saveLiveProfile(activeConference, next, attendeeToken);
        token = result.attendee_token ?? token;
        id = result.attendee_id;
        live = result.recommendations;
      }
    } finally {
      savingProfiles.current.delete(code);
    }
    const resumeName = next.resume?.name ?? previousResume?.name;
    attendeeSessions.update(code, {
      attendeeId: id, attendeeToken: token, saved: toStoredProfile(next, previousResume?.name),
      draft: undefined, draftStep: undefined, recommendations: live,
    });
    setRemembered(attendeeSessions.list());
    if (scope.current?.code !== code) return;
    const saved = { ...next, resume: undefined };
    setRecommendations(live);
    setAttendeeId(id);
    setAttendeeToken(token);
    setProfile(saved);
    setDraft(saved);
    setPreviousResume(resumeName ? { name: resumeName, onServer: !activeConference.sample } : undefined);
    if (currentPath.current === path) navigate(joinPath(code, resumeTalk ? 'schedule' : 'plan'));
  }

  // Refreshed people replace the stored copy so a reload keeps showing them.
  function keepPeople(attendees: LiveRecommendations['attendees']) {
    if (!activeConference) return;
    const next = { ...normalizeRecommendations(recommendations), attendees };
    setRecommendations(next);
    attendeeSessions.update(activeConference.code, { recommendations: next });
  }

  function cancelDraft() {
    if (!activeConference || !profile) return;
    const stored = attendeeSessions.load(activeConference.code);
    attendeeSessions.update(activeConference.code, { draft: undefined, draftStep: undefined });
    setDraft(profile);
    const name = stored?.saved?.resumeName;
    setPreviousResume(name ? { name, onServer: !activeConference.sample } : undefined);
    setResumeTalk(undefined);
    setRemembered(attendeeSessions.list());
    navigate(joinPath(activeConference.code, 'plan'), { replace: true });
  }

  function editProfile(talkId?: string) {
    setResumeTalk(talkId);
    if (activeConference && step !== 'about') navigate(joinPath(activeConference.code));
  }

  useEffect(scrollToTop, [screen, step]);
  useEffect(() => {
    if (page === 'myConferences') setRemembered(attendeeSessions.list());
  }, [page]);
  useEffect(() => {
    if (activeConference && step === 'availability' && !draft && !profile) {
      navigate(joinPath(activeConference.code), { replace: true });
    }
  }, [activeConference, draft, navigate, profile, step]);

  return (
    <SafeAreaProvider>
      <SafeAreaView style={layout.screen}>
        <StatusBar style="dark" />
        <MotionPreferences>
          <SiteShell page={page} navigate={navigate} scrollRef={scroll}>
            <Flow step={screen} fadeOnly>
              {page === 'home' ? <Landing navigate={navigate} hasConferences={remembered.length > 0}
                resumeConference={conference ? { name: conference.name, path: joinPath(conference.code, profile ? 'plan' : 'about') } : undefined} />
              : page === 'events' ? <PastEvents /> : page === 'talks' ? (
                <PastTalks onBrowseSchedule={() => navigate(conference ? joinPath(conference.code, 'schedule') : '/join')} />
              )
              : page === 'myConferences' ? <MyConferences conferences={remembered} navigate={navigate} onForget={forgetConference} />
              : page === 'organizers' ? (
                <OrganizersPage>
                  <Organizer onPublishSample={publishSample} onTrySample={(code) => navigate(joinPath(code))} />
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
                <Container style={[layout.content, (screen === 'schedule' || (screen === 'plan' &&
                  (section === 'My schedule' || section === 'Event schedule'))) && layout.scheduleContent]}>
                <View key={activeConference.code} style={styles.stack}>
                  <View style={styles.row}>
                    <Label>{activeConference.name}</Label>
                    <Action title="Switch conference" onPress={() => navigate('/my-conferences')} secondary />
                    {screen === 'schedule' ? (
                      <Action title={profile ? 'Back to my plan' : 'Back to check-in'}
                        onPress={() => { setResumeTalk(undefined); navigate(joinPath(activeConference.code, profile ? 'plan' : 'about')); }} secondary />
                    ) : !profile ? (
                      <Action title="Browse event schedule"
                        onPress={() => navigate(joinPath(activeConference.code, 'schedule'))} secondary />
                    ) : null}
                  </View>
                  {screen === 'schedule' ? (
                    <ScheduleBrowser conference={activeConference} attendeeToken={attendeeToken} initialTalkId={resumeTalk}
                      onProfile={editProfile} />
                  ) : screen === 'profile' ? (
                    <ProfileForm initial={draft ?? profile} previousResume={previousResume} conference={activeConference}
                      step={step === 'availability' && (draft || profile) ? 'availability' : 'about'}
                      onChange={changeDraft} onSave={saveProfile}
                      onStepChange={(next) => {
                        attendeeSessions.update(activeConference.code, { draftStep: next });
                        navigate(joinPath(activeConference.code, next));
                      }}
                      onCancel={profile ? cancelDraft : undefined} />
                  ) : profile ? (
                    <Recommendations conference={activeConference} profile={profile} attendeeToken={attendeeToken} requested={requested}
                      recommendations={recommendations} section={section} onSection={(next) => {
                        setSection(next);
                        attendeeSessions.update(activeConference.code, { section: next });
                      }}
                      onEdit={editProfile} onPeople={keepPeople}
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
  scheduleContent: { maxWidth: 1100 },
  entry: { flexDirection: 'row', flexWrap: 'wrap', alignItems: 'flex-end', columnGap: 64, rowGap: 32 },
  intro: { flexBasis: 360, flexGrow: 1, flexShrink: 1, maxWidth: 440, gap: 12 },
  coverTitle: { color: colors.ink, fontSize: 58, fontWeight: '700', letterSpacing: -3.5 },
  checkIn: { flexBasis: 270, flexGrow: 1, flexShrink: 1, maxWidth: 380 },
});
