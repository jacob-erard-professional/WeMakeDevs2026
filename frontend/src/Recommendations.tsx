import { useState } from 'react';
import { StyleSheet, View } from 'react-native';

import { buildSchedule, formatTime, matchingTopics, recommendTalks } from './conference';
import type { Attendee, Conference } from './conference';
import { demoConference, demoPeople } from './demoConference';
import { Action, colors, Copy, Heading, Label, Message, Section, styles } from './ui';

const sections = ['My schedule', 'Talks', 'People'] as const;
type Section = typeof sections[number];

export function Recommendations({ conference, profile, requested, onRequest, onEdit }: {
  conference: Conference;
  profile: Attendee;
  requested: string[];
  onRequest: (id: string) => void;
  onEdit: () => void;
}) {
  const [section, setSection] = useState<Section>('My schedule');
  const [refreshed, setRefreshed] = useState(false);
  const talks = recommendTalks(conference.talks, profile);
  const shownTalks = section === 'My schedule' ? buildSchedule(talks) : talks;
  const people = conference.code === demoConference.code
    ? demoPeople.slice(0, refreshed ? demoPeople.length : 2)
      .map((person) => ({ ...person, shared: matchingTopics(profile, person.topics) }))
      .sort((a, b) => b.shared.length - a.shared.length)
    : [];

  return (
    <View style={styles.stack}>
      <Heading>Your conference plan</Heading>
      <Copy>Welcome, {profile.name}. Find sessions that fit your day and people you might want to meet.</Copy>
      <View style={styles.row}>
        {sections.map((item) => <Action key={item} title={item} selected={section === item} onPress={() => setSection(item)} secondary />)}
        <Action title="Edit profile" onPress={onEdit} secondary />
      </View>
      {section === 'People' ? (
        <>
          <Heading>People to meet</Heading>
          <Action title="Refresh people" onPress={() => setRefreshed(true)} secondary />
          {refreshed ? <Message>{people.length ? 'People suggestions updated.' : 'No people are available yet.'}</Message> : null}
          {!people.length ? <Copy>People will appear here when this conference has discoverable attendees.</Copy> : null}
          {people.map((person) => (
            <Section key={person.id}>
              <Label>{person.role}</Label>
              <Heading>{person.name}</Heading>
              <Copy>{person.shared.length ? `Shared interests: ${person.shared.join(', ')}.` : `Meet another attendee interested in ${person.topics.join(' and ')}.`}</Copy>
              <Copy>{person.opener}</Copy>
              {requested.includes(person.id) ? <Message>Connection request pending</Message> : (
                <Action title={`Request connection with ${person.name}`} onPress={() => onRequest(person.id)} />
              )}
            </Section>
          ))}
        </>
      ) : (
        <>
          <Heading>{section === 'My schedule' ? 'Suggested schedule' : 'Recommended talks'}</Heading>
          <Copy>{section === 'My schedule' ? 'A plan without overlapping talks. All times are Mountain Time.' : 'Talks that fit your availability, with interest matches first.'}</Copy>
          {!shownTalks.length ? <Copy>No talks fit your availability. Edit your profile to update your unavailable times.</Copy> : null}
          {shownTalks.map((talk) => (
            <View key={talk.id} style={program.slot}>
              <View style={program.time}>
                <Label>{formatTime(talk.start)} to {formatTime(talk.end)}</Label>
                <Copy>{talk.room}</Copy>
              </View>
              <View style={program.talk}>
                <Heading>{talk.title}</Heading>
                <Copy>{talk.matched ? `Matches your interest in ${talk.track}.` : `Explore ${talk.track} during a time you’re available.`}</Copy>
              </View>
            </View>
          ))}
        </>
      )}
    </View>
  );
}

const program = StyleSheet.create({
  slot: { flexDirection: 'row', flexWrap: 'wrap', columnGap: 20, rowGap: 8, borderTopWidth: 1, borderColor: colors.line, paddingVertical: 14 },
  time: { flexBasis: 165 },
  talk: { flexBasis: 225, flexGrow: 1, flexShrink: 1, gap: 4 },
});
