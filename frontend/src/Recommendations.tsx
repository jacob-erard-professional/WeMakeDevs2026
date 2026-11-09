import { useEffect, useRef, useState } from 'react';
import { StyleSheet, View } from 'react-native';

import type { ApiPerson, ApiTalk, LiveRecommendations } from './api';
import { searchSuggestedPeople } from './api';
import { buildSchedule, formatTime, matchingTopics, recommendTalks } from './conference';
import type { Attendee, Conference, Talk } from './conference';
import { demoPeople } from './demoConference';
import { Flow } from './Flow';
import { ScheduleBrowser } from './ScheduleBrowser';
import { ScheduleColumns } from './ScheduleColumns';
import { Action, colors, Copy, Field, Heading, Label, Message, TalkDetails, styles } from './ui';

const sections = ['My schedule', 'Event schedule', 'Talks', 'Suggested People'] as const;
export type RecommendationSection = typeof sections[number];

type RankedTalk = Talk & { matched: boolean; relevance?: number; rank?: number };

// Minutes since midnight in the venue's zone, the same way `conferenceFromSchedule` computes it.
function venueMinutes(timestamp: string) {
  const date = new Date(timestamp);
  if (Number.isNaN(date.getTime())) return 0;
  const parts = new Intl.DateTimeFormat('en-US', {
    timeZone: 'America/Denver', hour: '2-digit', minute: '2-digit', hourCycle: 'h23',
  }).formatToParts(date);
  const value = (type: string) => Number(parts.find((part) => part.type === type)?.value ?? 0);
  return value('hour') * 60 + value('minute');
}

// Server-ranked talks carry only id, title, room and times; abstract and track come from the
// conference schedule the attendee already loaded.
export function liveTalks(conference: Conference, ranked: ApiTalk[]): RankedTalk[] {
  const known = new Map(conference.talks.map((talk) => [talk.id, talk]));
  const top = ranked.length ? ranked[0].relevance : 0;
  return ranked.map((talk, index) => {
    const local = known.get(talk.talk_id);
    return {
      id: talk.talk_id,
      title: talk.title,
      abstract: local?.abstract ?? talk.abstract,
      startsAt: talk.start_time,
      track: local?.track ?? (talk.track?.join(', ') || 'Conference session'),
      room: talk.room || local?.room || 'Room to be announced',
      start: local?.start ?? venueMinutes(talk.start_time),
      end: local?.end ?? venueMinutes(talk.end_time),
      matched: true,
      relevance: top > 0 ? Math.max(0, Math.min(1, talk.relevance / top)) : undefined,
      rank: index + 1,
    };
  });
}

export function livePeople(attendees: LiveRecommendations['attendees']): ApiPerson[] {
  const seen = new Set<string>();
  return [...attendees.matches, ...attendees.similar].filter((person) => {
    if (seen.has(person.attendee_id)) return false;
    seen.add(person.attendee_id);
    return true;
  });
}

// Semantic highlight fragments come back with <em> markup; show them as plain text.
function plainText(value?: string) {
  return value?.replace(/<[^>]+>/g, '').replace(/\s+/g, ' ').trim() ?? '';
}

function matchLabel(talk: RankedTalk) {
  if (talk.relevance === undefined) return null;
  if (talk.rank !== undefined && talk.rank <= 3) return 'Top match';
  return `${Math.round(talk.relevance * 100)}% match`;
}

export function Recommendations({ conference, profile, attendeeToken, recommendations, requested, onRequest, onEdit, section, onSection }: {
  conference: Conference;
  profile: Attendee;
  attendeeToken?: string;
  recommendations?: LiveRecommendations;
  requested: string[];
  onRequest: (id: string) => void;
  onEdit: (talkId?: string) => void;
  section: RecommendationSection;
  onSection: (section: RecommendationSection) => void;
}) {
  const [refreshed, setRefreshed] = useState(false);
  const [note, setNote] = useState('');
  const [appliedNote, setAppliedNote] = useState('');
  const [peopleResults, setPeopleResults] = useState<LiveRecommendations['attendees']>();
  const [peopleError, setPeopleError] = useState('');
  const [searching, setSearching] = useState(false);
  const peopleRequest = useRef<AbortController>(null);
  const live = !conference.sample;

  useEffect(() => () => peopleRequest.current?.abort(), []);

  async function updatePeople() {
    if (peopleRequest.current || (live && (!attendeeToken || !profile.discoverable))) return;
    const query = note.trim();
    setPeopleError('');
    if (!live) {
      setAppliedNote(query);
      setRefreshed(true);
      return;
    }
    if (!attendeeToken) return;
    const controller = new AbortController();
    peopleRequest.current = controller;
    setSearching(true);
    try {
      const results = await searchSuggestedPeople(conference.code, attendeeToken, query, controller.signal);
      if (!controller.signal.aborted) {
        setPeopleResults(results);
        setAppliedNote(query);
        setRefreshed(true);
      }
    } catch (error) {
      if (!controller.signal.aborted) setPeopleError(error instanceof Error ? error.message : 'Could not update people suggestions.');
    } finally {
      if (!controller.signal.aborted) {
        peopleRequest.current = null;
        setSearching(false);
      }
    }
  }

  let talks: RankedTalk[];
  let schedule: RankedTalk[];
  if (live) {
    talks = liveTalks(conference, recommendations?.talks ?? []);
    const planned = recommendations?.schedules[0]?.talks ?? [];
    schedule = (planned.length ? liveTalks(conference, planned) : buildSchedule(talks))
      .slice()
      .sort((a, b) => a.start - b.start);
  } else {
    talks = recommendTalks(conference.talks, profile);
    schedule = buildSchedule(talks);
  }
  const shownTalks = section === 'My schedule' ? schedule : talks;

  const samplePeople = conference.sample
    ? demoPeople.slice(0, refreshed ? demoPeople.length : 2)
      .map((person) => ({
        ...person,
        shared: matchingTopics(profile, person.topics),
        noteMatches: person.topics.filter((topic) => appliedNote.toLowerCase().includes(topic.toLowerCase())),
      }))
      .sort((a, b) => b.noteMatches.length - a.noteMatches.length || b.shared.length - a.shared.length)
    : [];
  const people = live ? livePeople(peopleResults ?? recommendations?.attendees ?? { similar: [], matches: [] }) : [];
  const peopleCount = live ? people.length : samplePeople.length;

  const emptyTalks = live
    ? 'No recommendations came back from the conference server yet. Edit your profile to add interests or a résumé.'
    : 'No talks fit your availability. Edit your profile to update your unavailable times.';
  const emptyPeople = live && !profile.discoverable
    ? 'Turn on discovery in your profile to see people to meet.'
    : 'People will appear here when this conference has discoverable attendees.';

  return (
    <View style={styles.stack}>
      <Heading large>Your conference plan</Heading>
      <Copy>Welcome, {profile.name}. Here’s what fits your day.</Copy>
      <View style={styles.row}>
        {sections.map((item) => <Action key={item} title={item} selected={section === item} onPress={() => onSection(item)} secondary />)}
        <Action title="Edit profile" onPress={() => onEdit()} secondary />
      </View>
      <Flow step={section} style={program.results}>
        {section === 'Event schedule' ? (
          <ScheduleBrowser conference={conference} attendeeToken={attendeeToken} onProfile={onEdit} />
        ) : section === 'Suggested People' ? (
          <>
            <Heading>Suggested people to talk to</Heading>
            <Copy>Add a note to refine these suggestions. It applies to this search and is separate from your profile.</Copy>
            <Field label="Who would you like to meet? (optional)" value={note} onChangeText={setNote} multiline maxLength={500}
              editable={!searching} placeholder="I’m looking for people involved in Kubernetes." />
            <Action title={searching ? 'Finding people…' : 'Update suggestions'} onPress={() => void updatePeople()}
              disabled={searching || (live && (!attendeeToken || !profile.discoverable))} />
            {live && !profile.discoverable ? <Action title="Edit discovery settings" onPress={() => onEdit()} secondary /> : null}
            {peopleError ? <Message error>{peopleError}</Message> : null}
            {refreshed && !searching && !peopleError ? <Message>{peopleCount ? 'People suggestions updated.' : 'No people are available yet.'}</Message> : null}
            {!peopleCount ? <Copy>{emptyPeople}</Copy> : null}
            {live ? people.map((person) => (
              <View key={person.attendee_id} style={program.person}>
                <Heading>{person.name}</Heading>
                {person.headline ? <Label>{person.headline}</Label> : null}
                <Copy>{person.why ? `Why: ${plainText(person.why)}` : 'Matched on your profile and what you’re looking for.'}</Copy>
                {requested.includes(person.attendee_id) ? <Message>Connection request pending</Message> : (
                  <Action title={`Request connection with ${person.name}`} onPress={() => onRequest(person.attendee_id)} />
                )}
              </View>
            )) : samplePeople.map((person) => (
              <View key={person.id} style={program.person}>
                <Heading>{person.name}</Heading>
                <Label>{person.role}</Label>
                <Copy>{person.noteMatches.length
                  ? `Matches your search for ${person.noteMatches.join(', ')}.`
                  : person.shared.length ? `Shared interests: ${person.shared.join(', ')}.`
                    : `Meet another attendee interested in ${person.topics.join(' and ')}.`}</Copy>
                <Copy>{person.opener}</Copy>
                {requested.includes(person.id) ? <Message>Connection request pending</Message> : (
                  <Action title={`Request connection with ${person.name}`} onPress={() => onRequest(person.id)} />
                )}
              </View>
            ))}
          </>
        ) : (
          <>
            <Heading>{section === 'My schedule' ? 'Suggested schedule' : 'Recommended talks'}</Heading>
            <Copy>{section === 'My schedule'
              ? 'A plan without overlapping talks. All times are Mountain Time.'
              : live ? 'Ranked by how well each talk matches your profile.' : 'Talks that fit your availability, with interest matches first.'}</Copy>
            {!shownTalks.length ? <Copy>{emptyTalks}</Copy> : null}
            <ScheduleColumns talks={section === 'My schedule' ? shownTalks : []}>
              {shownTalks.map((talk) => {
                const match = live ? matchLabel(talk) : null;
                return (
                  <View key={talk.id} style={program.slot}>
                    <View style={program.time}>
                      <Label>{formatTime(talk.start)} to {formatTime(talk.end)}</Label>
                      <Copy>{talk.room}</Copy>
                    </View>
                    <View style={program.talk}>
                      {match ? <Label>{match}</Label> : null}
                      <Heading>{talk.title}</Heading>
                      <Copy>{live
                        ? `${talk.track}.`
                        : talk.matched ? `Matches your interest in ${talk.track}.` : `Explore ${talk.track} during a time you’re available.`}</Copy>
                      <TalkDetails title={talk.title} abstract={talk.abstract || 'No session description has been provided.'} />
                    </View>
                  </View>
                );
              })}
            </ScheduleColumns>
          </>
        )}
      </Flow>
    </View>
  );
}

const program = StyleSheet.create({
  results: { gap: 12 },
  slot: { flexDirection: 'row', flexWrap: 'wrap', columnGap: 24, rowGap: 8, borderTopWidth: 1, borderColor: colors.chrome, paddingTop: 14 },
  time: { flexBasis: 165 },
  talk: { flexBasis: 260, flexGrow: 1, flexShrink: 1, gap: 4 },
  person: { marginTop: 22, gap: 7 },
});
