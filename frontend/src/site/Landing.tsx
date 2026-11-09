import { useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';

import { Action, colors, styles } from '../ui';
import { paths } from './router';
import { Container } from './SiteShell';

function RoleChoice({ title, description, onPress }: { title: string; description: string; onPress: () => void }) {
  const [focused, setFocused] = useState(false);

  return (
    <Pressable accessibilityRole="button" accessibilityLabel={title} accessibilityHint={description}
      onPress={onPress} onFocus={() => setFocused(true)} onBlur={() => setFocused(false)}
      style={({ pressed }) => [home.choice, pressed && home.active, focused && home.focused]}>
      <View style={home.choiceText}>
        <Text style={home.choiceTitle}>{title}</Text>
        <Text style={home.description}>{description}</Text>
      </View>
      <Text accessible={false} aria-hidden style={home.arrow}>→</Text>
    </Pressable>
  );
}

export function Landing({ navigate, resumeConference }: {
  navigate: (path: string) => void;
  resumeConference?: { name: string; code: string };
}) {
  return (
    <Container style={home.content}>
      <View style={home.intro}>
        <Text accessibilityRole="header" style={[styles.heading, styles.largeHeading, home.center]}>
          What would you like to do?
        </Text>
      </View>
      <View style={home.choices}>
        <RoleChoice title="I’m an attendee" description="Join a conference and explore its schedule."
          onPress={() => navigate(paths.join)} />
        <RoleChoice title="I’m an organizer" description="Set up a conference and share it with attendees."
          onPress={() => navigate(paths.organizers)} />
      </View>
      <View style={home.discovery}>
        {resumeConference ? (
          <View><Action title={`Return to ${resumeConference.name}`}
            onPress={() => navigate(`${paths.join}/${encodeURIComponent(resumeConference.code)}`)} secondary /></View>
        ) : null}
        <View><Action title="Search Talks" onPress={() => navigate(paths.talks)} /></View>
        <View><Action title="Browse the event archive" onPress={() => navigate(paths.events)} secondary /></View>
      </View>
    </Container>
  );
}

const home = StyleSheet.create({
  content: { maxWidth: 810, paddingVertical: 48, gap: 32 },
  intro: { alignItems: 'center' },
  center: { textAlign: 'center' },
  choices: { flexDirection: 'row', flexWrap: 'wrap', gap: 14 },
  choice: {
    flexBasis: 286, flexGrow: 1, flexShrink: 1, minHeight: 112, borderRadius: 8,
    flexDirection: 'row', alignItems: 'center', gap: 12, padding: 18, backgroundColor: colors.pale,
  },
  active: { backgroundColor: '#E4DFF5' },
  focused: { outlineColor: colors.accent, outlineWidth: 2, outlineOffset: 3, outlineStyle: 'solid' },
  choiceText: { flex: 1, gap: 5 },
  choiceTitle: { color: colors.ink, fontSize: 20, fontWeight: '700' },
  description: { color: colors.muted, fontSize: 15, lineHeight: 21 },
  arrow: { color: colors.accent, fontSize: 20 },
  discovery: { alignItems: 'center', gap: 4 },
});
